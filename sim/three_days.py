"""Three sample days for the two tab page (reflection/pages.py), made up and labelled simulated.

    python3 -I sim/three_days.py DIR [--seed N]
    python3 -m reflection.morning --demo-days DIR

It writes DIR/day1, DIR/day2 and DIR/day3, each with ascent.db, the night reports saved next to it
and day.json (the morning the day shows, marked simulated). The Sales agent's cases come from
sim/scenarios/sales.json through the engine's own API (sim/simulate.py); the night is the real night
runner (reflection/night.py night) with scripted model parts (sim/scripted.py), so no model is
called and the same seed gives the same days. The answers are the page's own (reflection/morning.py
Morning), made by a simulated user. No raw SQL: copies are taken with SQLite's backup.

Day 1: the Sales agent's first week, then its first night (the trial check, then the study). Its
lesson waits for a yes on Today: the scripted judge says high to every line the code check passes.
The personal assistant's night writes a new mode card from made-up moments, played in a scripted
Arena. The made-up lines are in sim/three_days.json.
Day 2: on day 1's page the simulated user said yes to the top card and sent a correction on the
Sales agent's page, which took a scripted exam; it is high risk, so it waits for a yes on Today.
Then the next night.
Day 3: on day 2's page the user said yes to the correction. The nights run on until the first one
whose trial check keeps, pulls or finds unclear a lesson; the morning after it. The mode card stays
open all three days: a day with no answer changes nothing.
Every row is simulated: the cases are sim-, the answers and the switch are signed "simulated user",
and each night report and mode card says simulated.

The level switch is set to fast by the simulated user before the first night, so a trial ends
inside the scenario's days (sim/score.py --level does the same in its own log).
"""
import argparse
import calendar
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assistant import newmode  # noqa: E402
from engine import exam as exam_mod  # noqa: E402
from engine import plug as plug_mod  # noqa: E402
from engine import risk  # noqa: E402
from engine import trial as trial_mod  # noqa: E402
from engine.lessons import Lessons  # noqa: E402
from kit.db import Db  # noqa: E402
from reflection import morning as mo  # noqa: E402
from reflection import night as night_runner  # noqa: E402
from sim import score, scripted, simulate  # noqa: E402

DAY = simulate.DAY
BY = "simulated user"
DAYS = 3
MOST_NIGHTS = 14  # day 3 comes at the latest this many nights after the first
DECIDED = (trial_mod.KEPT, trial_mod.PULLED, trial_mod.UNCLEAR)
# The made-up lines: the correction the user sends, the personal assistant's moments that fit no mode
# (assistant/newmode.py; kept before the first night, which makes a mode card from them) and the past
# days its Arena plays without and with that mode (a day that needs it is won only with it).
SAMPLE = ROOT / "sim" / "three_days.json"


def judge_says_high(text, high_about, low_about):
    """The scripted judge for the sample: high for every line, so each new lesson waits for a yes."""
    return risk.HIGH


def examiner(text, tags):
    """The scripted exam the correction takes: passed, one situation, no model call."""
    return exam_mod.Result(True, [exam_mod.Row(1, "simulated situation", "guard", True)], calls=0)


def play(day, added):
    """The scripted Arena play of one past day: won when the day needs no new mode or has it."""
    return day["needs"] is None or any(a["name"] == day["needs"] for a in added)


def build(folder, *, seed=None):
    """Write DIR/day1..day3. Refused when a day folder is there already. Returns the folders."""
    folder = Path(folder)
    days = [folder / f"day{d}" for d in range(1, DAYS + 1)]
    if any(d.exists() for d in days):
        raise ValueError(f"{folder} has a day folder already; name an empty folder")
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    plug, scenario = score.pair(sample["agent"])
    sc = simulate.check(plug, scenario)
    start = float(calendar.timegm(time.strptime(sc["start"], "%Y-%m-%d")))
    split = start + score.WEEK * DAY
    plugs = mo.repo_plugs()
    with tempfile.TemporaryDirectory(prefix="three-days-") as tmp:
        stage = Path(tmp)
        state = stage / "assistant"
        db = Db(":memory:")
        try:
            hand = Lessons(db, plug, judge=judge_says_high)
            hand.switches.set_level(plug_mod.FAST_LEVEL, BY, now=start)
            page = mo.Morning(db, plugs, reports=stage, by=BY, judge=judge_says_high, exams={plug.agent: examiner},
                              modes_state=state)
            proposer, tagger, fit, adapter = scripted.parts(scenario)
            made = {"nights": 0, "day": 0}

            def night(t):
                n = made["nights"]
                if made["day"] >= DAYS:
                    return
                rep = night_runner.night(db, plug, until=t, others=[], judge=judge_says_high, proposer=proposer,
                                         tagger=tagger, fit=fit, adapter=adapter)
                rep["simulated"] = True
                night_runner.save(rep, stage / "ascent.db")
                if n == 0:
                    newmode.keep_moments(state, [{"said": m["said"], "date": _date(start + m["day"] * DAY),
                                                  "simulated": True} for m in sample["moments"]])
                card = newmode.night(state, sample["past_days"], play, reports=stage, now=t)
                if card is not None:  # the card file says it is simulated too
                    data = json.loads(card.read_text(encoding="utf-8"))
                    card.write_text(json.dumps(dict(data, simulated=True), ensure_ascii=False, indent=1),
                                    encoding="utf-8")
                decided = any(x.get("status") in DECIDED for x in rep["trials"].get("trials") or [])
                made["nights"] += 1
                if made["day"] < 2 or decided or made["nights"] > MOST_NIGHTS:
                    _copy(db, stage, days[made["day"]], t, made["day"] + 1, seed)
                    made["day"] += 1
                if n < 2:  # the mornings of day 1 and day 2, after their copies
                    _answers(page, plug.agent, sample["correction"], t, n + 1)

            nights = [split + d * DAY for d in range(MOST_NIGHTS + 1)]
            simulate.simulate(db, plug, scenario, seed=seed, lessons=hand, hand_from=split, nights=nights,
                              night=night, until=max(nights[-1] + DAY, start + sc["days"] * DAY))
        finally:
            db.close()
    return days


def _answers(page, agent, correction, t, day):
    """The simulated user's answers on a day's page: yes on the top card; on day 1, then a correction
    on the Sales agent's page (high risk, so it is day 2's top card). The mode card is left open."""
    view = page.view(now=t)
    if view["cards"]:
        top = view["cards"][0]
        page.yes(top["id"], ",".join(str(r["id"]) for r in top["replaces"]), now=t + 60)
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
    (out / "day.json").write_text(json.dumps({"day": day, "at": t + 6 * 3600, "seed": seed, "simulated": True},
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
