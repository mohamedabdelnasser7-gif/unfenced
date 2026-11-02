"""The score: does an agent do better once it has learned? Every case is made up and labelled
simulated. The log, the lessons, the trial check and the night study are the engine's own;
the model parts are scripted (sim/scripted.py) and the judge says low to every lesson, as in
sim/run.py, so a run makes no model call and the same seed gives the same numbers.

    python3 -I sim/score.py [--plug AGENT] [--seed N] [--weeks N] [--level fast|careful] [--json]

One run, in a log held in memory and closed when it ends:
1. Week 1, days 1 to 7. The scenario's cases that start these days, written through the
   engine's own API by sim/simulate.py. No lesson exists before the end of day 7.
2. Each night from the end of day 7: the trial check (engine/trial.py) first, then the night
   study (engine/study.py) over the days before it, as reflection/night.py runs them, its window
   reflection.night.default_days.
3. Each action from the end of day 7 on, by its own time, is handed its lessons by
   Lessons.hand, which gives a lesson on trial only in its share of cases (lessons.in_share)
   and a kept one in all but its holdback, and is saved with their ids. A week 1 case still
   running then can be given a lesson at its later steps. The scenario's lift says how a case
   reacts to a lesson it was given; with no lift, a lesson changes nothing.
4. The results go on coming after the last day, and so do the nights. The score is read
   study.read_days after the last day, when the simulated results have come; a case with no
   deciding result is still pending then and is not scored (no timer settles a case, item 66).

The score is the share of settled cases that ended good, week by week, each week against
week 1. Each case counts in the week of its first action; a case left out for a cause outside
the agent is not counted. Beside each week, the chance it beats week 1 (study.chance_better):
how sure the gap is, not what caused it; the run with the lessons pulled is the check of
cause. Then each trial's own count: the cases of its trial given the lesson against those
not given it, as the trial check read them for its verdict.

--weeks: 2 by default, the scenario's own 14 days. More weeks run the scenario longer at the
same cases a day (its days and its cases times weeks / 2, its seed the same), so the last week
comes after a trial has ended and its kept lesson reaches all but its holdback. These are
other cases than the two week run's, drawn from the same seed.

The proof runs the same seed again, with every lesson the first run gave in any case, and
every lesson a lift names, pulled the night it is written, before any case is given it:
before day 8 for a lesson written on night 7. Up to that night the two runs are the same, so
week 1 is the same but for a week 1 case still open that night, which a lesson can reach in
the first run only, and every later week should fall back to what it is with no lessons at
all. Its nights can write a line the first run never gave; no lift names it, so it changes
no case, and when it was given all the same the score says so plainly.

--level: the trial level every trial in the run takes, careful by default, as the level
switch reads before a person flips it. The run flips the switch in its own log before the
first night (engine/switches.py), so the share and days come from the plug's level, read
the same way a live night reads them. Both runs of one score take the same level.

--plug names the agent: its plug is <agent>/plug.json and its scenario the one in
sim/scenarios for that agent, as sim/run.py pairs them. By default, the first agent whose
scenario plants a lift.
"""
import argparse
import calendar
import copy
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import plug as plug_mod  # noqa: E402
from engine import risk  # noqa: E402
from engine import trial as trial_mod  # noqa: E402
from engine.lessons import WAITING, Lessons  # noqa: E402
from engine.log import Log  # noqa: E402
from engine.plug import ALL  # noqa: E402
from engine.study import BAD, GOOD, LEFT_OUT, PENDING, Study, chance_better, read_days, settle  # noqa: E402
from engine.trial import Trials  # noqa: E402
from kit.db import Db  # noqa: E402
from reflection import night as night_runner  # noqa: E402
from sim import run, scripted, simulate  # noqa: E402

DAY = simulate.DAY
WEEK = 7
WEEKS, MOST_WEEKS = 2, 8  # the scenario's own days are WEEKS weeks: one with no lessons, one with them
LEARNED, PULLED_FIRST, NONE = "learned", "pulled", "none"
MODES = (LEARNED, PULLED_FIRST, NONE)
WHY_PULLED = "Pulled for the proof the night it was written, before any case was given it."
ENDED = (trial_mod.KEPT, trial_mod.PULLED, trial_mod.PAUSED, trial_mod.UNCLEAR)
SIDE = ("cases", "settled", "good")
BY = "sim/score.py --level"  # who flips the level switch in a run's own log


def pair(agent=None):
    """(plug, scenario) for the agent named: <agent>/plug.json and its scenario in sim/scenarios.
    None: the first agent whose scenario plants a lift."""
    if agent is None:
        for p, s in run.AGENTS:
            if simulate.load(ROOT / s).get("lift"):
                return plug_mod.load(ROOT / p), simulate.load(ROOT / s)
        raise ValueError("no scenario in sim/scenarios plants a lift")
    if not isinstance(agent, str) or not agent.isidentifier():
        raise ValueError("--plug: the agent's plain name")
    for p, s in run.AGENTS:
        if p == f"{agent}/plug.json":
            return plug_mod.load(ROOT / p), simulate.load(ROOT / s)
    raise ValueError(f"no scenario in sim/scenarios for {agent!r}")


def check_weeks(weeks):
    if isinstance(weeks, bool) or not isinstance(weeks, int) or not WEEKS <= weeks <= MOST_WEEKS:
        raise ValueError(f"weeks: a whole number from {WEEKS} to {MOST_WEEKS}")
    return weeks


def stretched(plug, scenario, weeks=WEEKS):
    """The scenario checked, over weeks weeks at the same cases a day: its days and its cases
    times weeks / 2, everything else kept, its seed too. Two weeks give the scenario itself."""
    weeks = check_weeks(weeks)
    sc = simulate.check(plug, scenario)
    if sc["days"] != WEEKS * WEEK:
        raise ValueError(f"the scenario's days: {WEEKS * WEEK}, one week with no lessons and one with them")
    if weeks == WEEKS:
        return scenario
    out = copy.deepcopy(scenario)
    out["days"] = weeks * WEEK
    out["cases"] = round(sc["cases"] * weeks / WEEKS)
    return out


def check_level(level):
    if level not in plug_mod.LEVEL_NAMES:
        raise ValueError(f"level: {' or '.join(plug_mod.LEVEL_NAMES)}")
    return level


def one_run(plug, scenario, *, seed=None, mode=LEARNED, pull=(), weeks=WEEKS, level=plug_mod.CAREFUL):
    """One run in a fresh log held in memory. mode: learned, every night as it comes; pulled,
    every lesson whose line is in pull or named by a lift is pulled the night it is written,
    so no case is given it; none, no night at all, so no lesson is ever written. weeks: see
    stretched. level: the trial level the switch is set to before the first night. Returns the
    run as plain data."""
    check_level(level)
    if mode not in MODES:
        raise ValueError(f"mode: one of {', '.join(MODES)}")
    pull = set(pull)
    if pull and mode != PULLED_FIRST:
        raise ValueError("pull: only in the pulled run")
    scenario = stretched(plug, scenario, weeks)
    sc = simulate.check(plug, scenario)
    if mode == PULLED_FIRST:
        pull |= {r["lesson"] for r in sc["lift"]}  # written first in this run too, it is pulled
    start = float(calendar.timegm(time.strptime(sc["start"], "%Y-%m-%d")))
    split = start + WEEK * DAY
    read_at = start + sc["days"] * DAY + read_days(plug) * DAY
    window = night_runner.default_days(plug) * DAY  # the night runner's own window
    db = Db(":memory:")
    try:
        lessons = Lessons(db, plug, judge=scripted.judge_says_low)
        if level != plug_mod.CAREFUL:  # careful is how the switch reads before anyone flips it
            lessons.switches.set_level(level, BY, now=start)
        trials = Trials(db, plug, lessons=lessons)
        proposer, tagger, _, _ = scripted.parts(scenario)
        study = Study(db, plug, proposer=proposer, tagger=tagger, lessons=lessons)
        nights, pulled = [], []

        def night(t):
            checked = trials.check(t)
            rep = study.run(t - window, t, now=t)
            for les in lessons.mine():
                if les["text"] in pull and lessons.pull(les["id"], WHY_PULLED, now=t):
                    pulled.append({"lesson_id": les["id"], "line": les["text"], "night": round((t - start) / DAY)})
            nights.append({"night": round((t - start) / DAY), "trials": checked["trials"], "cards": rep["cards"]})

        times = [] if mode == NONE else [split + d * DAY for d in range(round((read_at - split) / DAY) + 1)]
        man = simulate.simulate(db, plug, scenario, seed=seed, lessons=None if mode == NONE else lessons,
                                hand_from=split, nights=times, night=night, until=read_at)
        out = _tally(db, plug, lessons, man, split, read_at, weeks)
        out.update(mode=mode, level=lessons.switches.level()["level"], seed=man["seed"], since=start, split=split,
                   end=man["end"], read_at=read_at,
                   nights=len(nights), pulled=pulled,
                   lessons=_lessons(lessons, nights, out.pop("by_lesson"), out.pop("by_week")),
                   lifted=[{"case": c["id"], "drawn": c["lifted"], "now": {k: c["traits"][k] for k in c["lifted"]}}
                           for c in man["cases"] if c["lifted"]])
        return out
    finally:
        db.close()


def _tally(db, plug, lessons, man, split, read_at, weeks=WEEKS):
    """Every week's numbers from the log as it stands when the score is read, each week against
    week 1, each lesson's two sides in week 2, and how many cases each week gave each lesson."""
    rows_by = [{"week": n, "days": [WEEK * (n - 1) + 1, WEEK * n], "cases": 0, "settled": 0, "good": 0,
                "left_out": 0, "pending": 0, "given": 0} for n in range(1, weeks + 1)]
    second, by_week = [], {}
    for case_id, rows in Log(db, plug).window(man["since"], read_at).items():
        if not case_id.startswith(simulate.PREFIX) or not all((r["detail"] or {}).get(simulate.LABEL) is True
                                                              for r in rows):
            raise ValueError(f"{case_id}: a case not labelled simulated")
        acts = [r for r in rows if r["action"] is not None]
        status = settle(plug, rows, read_at)[0]
        given = {i for r in rows for i in r["lessons"]}
        at = acts[0]["at"]
        k = 0 if at < split else min(1 + int((at - split) // (WEEK * DAY)), weeks - 1)
        w = rows_by[k]
        w["cases"] += 1
        w["settled"] += status in (GOOD, BAD)
        w["good"] += status == GOOD
        w["left_out"] += status == LEFT_OUT
        w["pending"] += status == PENDING
        w["given"] += bool(given)
        for i in given:
            by_week.setdefault(i, Counter())[w["week"]] += 1
        if w["week"] == 2:
            second.append({"status": status, "given": given, "stages": {r["stage"] for r in acts}})
    for w in rows_by:
        w["share"] = w["good"] / w["settled"] if w["settled"] else None
    one = rows_by[0]
    against = [{"week": w["week"], "gain": _gain(one, w),
                "chance": chance_better(w["good"], w["settled"], one["good"], one["settled"])
                if w["settled"] and one["settled"] else None} for w in rows_by[1:]]
    by_lesson = {}
    for les in lessons.mine():
        fits = [c for c in second if ALL in les["stages"] or c["stages"] & set(les["stages"])]
        sides = {"with": [c for c in fits if les["id"] in c["given"]],
                 "without": [c for c in fits if les["id"] not in c["given"]]}
        num = {k: {"cases": len(v), "settled": sum(c["status"] in (GOOD, BAD) for c in v),
                   "good": sum(c["status"] == GOOD for c in v)} for k, v in sides.items()}
        w, wo = num["with"], num["without"]
        num["chance"] = chance_better(w["good"], w["settled"], wo["good"], wo["settled"]) if (
            w["settled"] and wo["settled"]) else None
        by_lesson[les["id"]] = num
    return {"weeks": rows_by, "gain": against[-1]["gain"], "chance": against[-1]["chance"], "against": against,
            "by_lesson": by_lesson,
            "by_week": {i: [c[n] for n in range(1, weeks + 1)] for i, c in by_week.items()}}


def _gain(one, w):
    return None if one["share"] is None or w["share"] is None else round((w["share"] - one["share"]) * 100, 1)


def _lessons(lessons, nights, by_lesson, by_week):
    """Every lesson the nights wrote: its line, the night it was written, its state when the
    score is read, its trial's share, the trial check's first end for it with the trial's own
    count, its two sides in week 2, and how many cases were given it each week."""
    written = {c["lesson_id"]: n["night"] for n in nights for c in n["cards"]}
    ended = {}
    for n in nights:
        for e in n["trials"]:
            if e["status"] in ENDED and e["lesson_id"] not in ended:
                ended[e["lesson_id"]] = {"status": e["status"], "night": n["night"], "why": e["why"],
                                         "with": {k: e["with"][k] for k in SIDE},
                                         "without": {k: e["without"][k] for k in SIDE}, "chance": e["chance"]}
    out = []
    for les in lessons.mine():
        trial = lessons.trial(les["id"])
        state = les["state"]
        if state == WAITING:
            state = "waits its turn" if les["id"] in lessons.turns() else "waits for a yes"
        out.append({"lesson_id": les["id"], "line": les["text"], "stages": les["stages"],
                    "night": written.get(les["id"]), "state": state, "risk": les["risk"], "risk_why": les["risk_why"],
                    "share": None if trial is None else trial["share"], "trial": ended.get(les["id"]),
                    "week_2": by_lesson[les["id"]], "given_by_week": by_week.get(les["id"]),
                    "cases_given": sum(by_week.get(les["id"], ()))})
    return out


def score(plug, scenario, *, seed=None, weeks=WEEKS, level=plug_mod.CAREFUL):
    """The score as plain data: the run as it learned and the run with every lesson it gave
    pulled the night it was written, side by side, both at the same trial level."""
    first = one_run(plug, scenario, seed=seed, mode=LEARNED, weeks=weeks, level=level)
    reached = [les["line"] for les in first["lessons"] if les["cases_given"]]
    runs = {LEARNED: first,
            PULLED_FIRST: one_run(plug, scenario, seed=seed, mode=PULLED_FIRST, pull=reached, weeks=weeks,
                                  level=level)}
    lv = plug.level(level)
    return {"agent": plug.agent, "simulated": True, "seed": first["seed"], "good": plug.decides.good,
            "weeks": weeks, "level": {"name": level, "share": lv.share, "days": lv.days},
            "measure": f"week 1 (days 1 to {WEEK}, before any lesson) against week {weeks} "
                       f"(days {WEEK * (weeks - 1) + 1} to {WEEK * weeks})",
            "since": first["since"], "split": first["split"], "end": first["end"], "read_at": first["read_at"],
            "runs": runs}


def text(s):
    """The score as plain lines."""
    good, n = s["good"], s["weeks"]
    a = s["runs"][LEARNED]
    lines = [f'{s["agent"]}, seed {s["seed"]}: {sum(w["cases"] for w in a["weeks"])} simulated cases from '
             f'{_day(s["since"])} to {_day(s["end"] - DAY)}, scored on {_day(s["read_at"])} when every result was in.',
             f'The score: the share of settled cases that ended {good}, {s["measure"]}.',
             f'Trial level {s["level"]["name"]}: each trial gives its lesson in {_pct(s["level"]["share"])} of the '
             f'cases at its stages for {s["level"]["days"]} days.',
             "Cases left out for a cause outside the agent are not counted.",
             "",
             f'  {"":34}' + "".join(f'{"week " + str(w["week"]):20}' for w in a["weeks"]) +
             f'{"gain":14}chance week {n} beats week 1']
    for mode, label in ((LEARNED, "with what the nights learned"), (PULLED_FIRST, "the same, its lessons pulled")):
        r = s["runs"][mode]
        lines.append(f'  {label:34}' + "".join(f"{_share(w):20}" for w in r["weeks"]) +
                     f'{_points(r["gain"]):14}{_pct(r["chance"])}')
    lines += ["", f'  {"cases":34}' + "".join(f'{w["cases"]:<20}' for w in a["weeks"]).rstrip(),
              f'  {"given a lesson":34}' + "".join(f'{w["given"]:<20}' for w in a["weeks"]).rstrip()]
    if n > WEEKS:
        lines += ["", "Each week against week 1, in the run with what the nights learned:"]
        for x, w in zip(a["against"], a["weeks"][1:]):
            lines.append(f'  week {x["week"]}: {_share(w)} against {_share(a["weeks"][0])}, '
                         f'{_points(x["gain"])}, chance week {x["week"]} beats week 1 {_pct(x["chance"])}')
    tried = [les for les in a["lessons"] if les["trial"]]
    lines += ["", "Each trial's own count, on the cases of its trial, with the lesson against without it:"]
    for les in tried:
        t = les["trial"]
        lines.append(f'  lesson {les["lesson_id"]}, on trial from night {les["night"]}: with it {_share(t["with"])}, '
                     f'without it {_share(t["without"])}; chance it is better {_pct(t["chance"])}; '
                     f'{t["status"]} on night {t["night"]}')
    if not tried:
        lines.append("  no trial had ended when the score was read")
    lines += ["", f'What the nights wrote, in the run with them. A lesson changed {len(a["lifted"])} of the cases '
                  "it was given in."]
    for les in a["lessons"]:
        lines.append(f'  - lesson {les["lesson_id"]}, night {les["night"]}: "{les["line"]}"')
        lines.append(f'    {_state(les)}')
        w2 = les["week_2"]
        w, wo = w2["with"], w2["without"]
        if not w["cases"]:
            lines.append("    week 2: given in no case")
        else:
            lines.append(f'    week 2: given in {w["cases"]} cases; with it {w["good"]} of {w["settled"]} settled cases '
                         f'ended {good}, without it {wo["good"]} of {wo["settled"]}; chance it is better '
                         f'{_pct(w2["chance"])}')
        if n > WEEKS and les["given_by_week"]:
            lines.append("    cases given it, week by week: " + ", ".join(str(x) for x in les["given_by_week"]))
        if les["trial"]:
            lines.append(f'    trial check, night {les["trial"]["night"]}: {les["trial"]["why"]}')
    second = s["runs"][PULLED_FIRST]
    pulled = second["pulled"]
    lines += ["", "In the second run, pulled the night it was written, before any case was given it: " +
              (", ".join(f'lesson {p["lesson_id"]} (night {p["night"]})' for p in pulled) if pulled
               else "nothing, since no lesson reached a case") + "."]
    still = [les for les in second["lessons"] if les["cases_given"]]
    if still:
        lines.append(f'Given all the same in the second run, in {sum(w["given"] for w in second["weeks"])} cases: '
                     "a line the first run gave in no case and no lift names, so it was not pulled. A lesson "
                     f'changed {len(second["lifted"])} of the cases in that run.')
        for les in still:
            lines.append(f'  - lesson {les["lesson_id"]}, night {les["night"]}: "{les["line"]}", given in '
                         f'{les["cases_given"]} cases, week by week: ' + ", ".join(str(x) for x in les["given_by_week"]))
    return "\n".join(lines)


def _state(les):
    """Where the lesson went: its trial, from the night it started to how it ended, or why it waits."""
    if les["state"] == "waits for a yes":
        why = run.HELD if risk.COPIED in (les["risk_why"] or "") else les["risk_why"]
        return f'waits for a yes ({les["risk"]} risk: {why})'
    if les["share"] is None:
        return les["state"]
    out = f'on trial from night {les["night"]}, given in {_pct(les["share"])} of the cases at its stages'
    if les["trial"]:
        return f'{out}; {les["trial"]["status"]} by its trial on night {les["trial"]["night"]}'
    return f'{out}; {les["state"]} when the score was read'


def _share(w):
    if not w["settled"]:
        return "none settled"
    return f'{w["good"]} of {w["settled"]} ({round(w["good"] / w["settled"] * 100)}%)'


def _points(x):
    return "none" if x is None else f"{x:+.1f} points"


def _pct(x):
    """A chance as a whole percent; one that rounds to 100 prints "over 99%", as sim/run.py does."""
    return "none" if x is None else run._pct(x)


def _day(t):
    return time.strftime("%d %b %Y", time.gmtime(t))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Week 1 against later weeks on simulated cases, and the proof.")
    ap.add_argument("--plug", default=None,
                    help="the agent: <agent>/plug.json; by default the first whose scenario plants a lift")
    ap.add_argument("--seed", type=int, default=None, help="the scenario's own seed by default")
    ap.add_argument("--weeks", type=int, default=WEEKS,
                    help=f"weeks to run, {WEEKS} to {MOST_WEEKS}; {WEEKS} by default, the scenario's own days")
    ap.add_argument("--level", choices=plug_mod.LEVEL_NAMES, default=plug_mod.CAREFUL,
                    help=f"the trial level every trial takes; {plug_mod.CAREFUL} by default, as the switch reads "
                         "before a person flips it")
    ap.add_argument("--json", action="store_true", help="print the score as JSON")
    args = ap.parse_args(argv)
    try:
        plug, scenario = pair(args.plug)
        s = score(plug, scenario, seed=args.seed, weeks=args.weeks, level=args.level)
    except ValueError as e:
        print(f"sim/score.py: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
    else:
        print("Simulated data: every case below is made up. Model parts are scripted; no model was called.\n")
        print(text(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
