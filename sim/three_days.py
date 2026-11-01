"""Three sample days for the two tab page (reflection/pages.py), made up and labelled simulated.

    python3 -I sim/three_days.py DIR [--seed N]
    python3 -m reflection.morning --demo-days DIR

It writes DIR/day1, DIR/day2 and DIR/day3, each with ascent.db, the files saved next to it and
day.json (the morning the day shows, marked simulated). The days are three working mornings in a
row (the Egypt week runs Sunday to Thursday), 09:00 Cairo, from sim/three_days.json first_morning.
The Sales agent's cases come from sim/scenarios/sales.json through the engine's own API
(sim/simulate.py), moved so its first week ends the night before the first morning; the night is
the real night runner (reflection/night.py night) with scripted model parts (sim/scripted.py), so
no model is called and the same seed gives the same days. The answers are the page's own
(reflection/morning.py Morning), made by a simulated user after 09:00. No raw SQL: copies are
taken with SQLite's backup.

Each night, for the Sales agent: the hotfix notes on the cases that ended without the good result
(engine/fast.py sweep with a scripted writer, one fixed line from the sample), the night study (trial
check, then study), and a small practice run in the Arena (arena/run.py Arena on the made-up cards in
demo/personas/cards, the scripted pair in arena/scripted.py, saved by the Arena's own stuck_item). For the personal assistant:
its new mode step (assistant/newmode.py night) on made-up moments, played in a scripted Arena.

Night 1, before day 1: the Sales agent's first week is read; its lesson waits for a yes on Today
(the scripted judge says high to every line the code check passes); the assistant finds a mode.
Day 1: the simulated user says yes to the mode card, leaves the lesson for a day and sends a
correction on the Sales agent's page; it takes a scripted exam and is high risk, so it waits for a
yes on day 2. Night 2: the hotfix notes, the study and the Arena again; the assistant finds a second mode.
Day 2: yes to every card, the correction first, so it runs on trial and the lesson
waits its turn behind it (one trial on a stage at a time).
Night 3: the night checks the correction on trial; the assistant finds a third mode.
Every row is simulated: the cases are sim-, the answers and the switch are signed "simulated user",
and each night report, mode card and Arena item says simulated.

The level switch is set to fast by the simulated user before the first night (sim/score.py
--level does the same in its own log).
"""
import argparse
import calendar
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arena import run as arena_run  # noqa: E402
from arena import scripted as arena_scripted  # noqa: E402
from assistant import newmode  # noqa: E402
from engine import exam as exam_mod  # noqa: E402
from engine import plug as plug_mod  # noqa: E402
from engine import risk  # noqa: E402
from engine.fast import FastNotes  # noqa: E402
from engine.lessons import Lessons  # noqa: E402
from kit.db import Db  # noqa: E402
from reflection import morning as mo  # noqa: E402
from reflection import night as night_runner  # noqa: E402
from sim import score, scripted, simulate  # noqa: E402

DAY = simulate.DAY
BY = "simulated user"
DAYS = 3
MORNING_HOUR = 9  # Cairo
WORK_DAYS = (6, 0, 1, 2, 3)  # Sunday to Thursday, as datetime.weekday() counts them
# The made-up lines: the first morning, the correction the user sends, the hotfix note's line, the
# personal assistant's moments that fit no mode (each said on a day, counted from the first morning,
# and kept before the night after the morning it names, 0 for before the first night) and the past
# days its Arena plays without and with a mode (a day that needs one is won only with it).
SAMPLE = ROOT / "sim" / "three_days.json"
ARENA_TRUST = {"matches": 5, "wins": 5, "zero_failed_checks": True}  # the practice run's small gate
ARENA_HELD = ["persona-01", "persona-02", "persona-05"]  # the made-up personas its gate plays, three worries


def judge_says_high(text, high_about, low_about):
    """The scripted judge for the sample: high for every line, so each new lesson waits for a yes."""
    return risk.HIGH


def examiner(text, tags):
    """The scripted exam the correction takes: passed, one situation, no model call."""
    return exam_mod.Result(True, [exam_mod.Row(1, "simulated situation", "guard", True)], calls=0)


def play(day, added):
    """The scripted Arena play of one past day: won when the day needs no new mode or has it."""
    return day["needs"] is None or any(a["name"] == day["needs"] for a in added)


def hotfix_writer(line):
    """The scripted writer of a hotfix note (engine/fast.py): the same line for every case."""
    return lambda plug, view: line


def mornings(first):
    """The three mornings, 09:00 Cairo on working days in a row from first ("YYYY-MM-DD")."""
    day = datetime.strptime(first, "%Y-%m-%d").date()
    out = []
    while len(out) < DAYS:
        if day.weekday() in WORK_DAYS:
            out.append(datetime(day.year, day.month, day.day, MORNING_HOUR, tzinfo=mo.CAIRO).timestamp())
        elif out:
            raise ValueError("the sample's mornings run past the work week; move first_morning")
        day += timedelta(days=1)
    return out


def build(folder, *, seed=None):
    """Write DIR/day1..day3. Refused when a day folder is there already. Returns the folders."""
    folder = Path(folder)
    days = [folder / f"day{d}" for d in range(1, DAYS + 1)]
    if any(d.exists() for d in days):
        raise ValueError(f"{folder} has a day folder already; name an empty folder")
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    at = mornings(sample["first_morning"])
    if any(b - a != DAY for a, b in zip(at, at[1:])):
        raise ValueError("the sample's mornings are not days in a row")
    nights = [float(calendar.timegm(time.gmtime(t)[:3] + (0, 0, 0))) for t in at]  # midnight UTC before each
    plug, scenario = score.pair(sample["agent"])
    start = nights[0] - score.WEEK * DAY  # the scenario moved: its first week ends at the first night
    scenario = dict(scenario, start=time.strftime("%Y-%m-%d", time.gmtime(start)))
    sc = simulate.check(plug, scenario)
    cards = arena_run.load_cards(arena_run.DEMO_CARDS)  # the made-up cards, never the real ones
    plugs = mo.repo_plugs()
    with tempfile.TemporaryDirectory(prefix="three-days-") as tmp:
        stage, aside = Path(tmp) / "stage", Path(tmp) / "aside"
        stage.mkdir()
        state = stage / "assistant"
        db = Db(":memory:")
        try:
            hand = Lessons(db, plug, judge=judge_says_high)
            hand.switches.set_level(plug_mod.FAST_LEVEL, BY, now=start)
            page = mo.Morning(db, plugs, reports=stage, by=BY, judge=judge_says_high, exams={plug.agent: examiner},
                              modes_state=state)
            notes = FastNotes(db, plug, writer=hotfix_writer(sample["hotfix"]))
            proposer, tagger, fit, adapter = scripted.parts(scenario)

            def moments(kept):
                newmode.keep_moments(state, [{"said": m["said"], "date": _date(at[0] + m["on"] * DAY), "simulated": True}
                                             for m in sample["moments"] if m["kept"] == kept])

            def night(n, t):
                notes.sweep(now=t)
                rep = night_runner.night(db, plug, until=t, others=[], judge=judge_says_high, proposer=proposer,
                                         tagger=tagger, fit=fit, adapter=adapter)
                rep["simulated"] = True
                night_runner.save(rep, stage / "ascent.db")
                if n == 0:
                    moments(0)
                card = newmode.night(state, sample["past_days"], play, reports=stage, now=t)
                if card is not None:
                    _label(card)
                _practice(cards, aside / f"night{n}", stage, n if seed is None else seed * 10 + n, t)

            def morning(n, t):
                _copy(db, stage, days[n], t, n + 1, seed)
                if n < DAYS - 1:
                    _answers(page, plug.agent, sample["correction"], t, n + 1, stage)
                    moments(n + 1)

            def step(t):
                if t in nights:
                    night(nights.index(t), t)
                else:
                    morning(at.index(t), t)

            simulate.simulate(db, plug, scenario, seed=seed, lessons=hand, hand_from=nights[0],
                              nights=sorted(nights + at), night=step,
                              until=max(at[-1] + DAY, start + sc["days"] * DAY))
        finally:
            db.close()
    return days


def _practice(cards, aside, reports, seed, t):
    """A small simulated practice run in the Arena at night: the Arena's own run and its own saved
    item (stuck_item, next to the database), labelled simulated. The matches stay aside."""
    calls = arena_run.Calls(aside / "calls.json", arena_run.DEFAULT_CAP, day=_date(t))
    rep = arena_run.Arena(cards, agent_model=arena_scripted.PracticeAgent(), customer_model=arena_scripted.PracticePersona(), calls=calls,
                          trust=dict(ARENA_TRUST), held_out=list(ARENA_HELD), matches=2, rounds=3, seed=seed, state=aside, reports=reports,
                          now=lambda: t).run()
    item = rep.get("stuck") or rep.get("item")
    if item is None:
        raise ValueError(f"the practice run saved no item: it stopped {rep['stopped']}")
    _label(Path(reports) / item["file"])


def _label(path):
    """Mark a saved file simulated, keeping what it says."""
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(dict(data, simulated=True), ensure_ascii=False, indent=1), encoding="utf-8")


def _answers(page, agent, correction, t, day, reports):
    """The simulated user's answers on a day's page, after 09:00. Day 1: yes on the mode card, the
    lesson left for a day (skip a day and nothing breaks), then a correction on the Sales agent's
    page (high risk, so it waits for day 2's yes). Day 2: yes on each lesson card, the correction
    first, so it starts its trial and the lesson waits its turn behind it; yes on the mode card."""
    view = page.view(now=t)
    cards = sorted(view["cards"], key=lambda c: c.get("origin") != "person") if day > 1 else []
    for k, card in enumerate(cards):
        page.yes(card["id"], ",".join(str(r["id"]) for r in card["replaces"]), now=t + 60 + k)
    for a in view["agents"]:
        mode = a.get("mode_card")
        if mode is not None:
            page.answer_mode(a["agent"], mode["file"], "yes", now=t + 90)
            path = Path(reports) / mode["file"]  # the answer's time on the sample's own clock
            data = json.loads(path.read_text(encoding="utf-8"))
            data["answer"]["at"] = t + 90
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if day == 1:
        page.correct(agent, correction, now=t + 120)


def _copy(db, stage, out, t, day, seed):
    """One day's folder: the database (SQLite backup), the files saved next to it, and day.json."""
    out.mkdir(parents=True)
    copy = Db(str(out / "ascent.db"))
    try:
        with db.tx() as src:
            src.backup(copy.conn)
    finally:
        copy.close()
    for path in sorted(stage.iterdir()):
        if path.is_dir():
            shutil.copytree(path, out / path.name)
        elif path.name != "ascent.db":
            shutil.copy2(path, out / path.name)
    (out / "day.json").write_text(json.dumps({"day": day, "at": t, "seed": seed, "simulated": True},
                                             indent=1), encoding="utf-8")


def _date(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Three made-up sample days for the two tab page.")
    ap.add_argument("folder", help="an empty folder, outside the repo or in data/")
    ap.add_argument("--seed", type=int, default=None, help="the scenario's seed unless given")
    args = ap.parse_args(argv)
    try:
        days = build(args.folder, seed=args.seed)
    except ValueError as e:
        print(f"Not built: {e}.", file=sys.stderr)
        return 2
    for d in days:
        print(f"written: {d}")
    print(f"Serve them: python3 -m reflection.morning --demo-days {args.folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
