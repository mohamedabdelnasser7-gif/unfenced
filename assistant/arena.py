"""The assistant's Arena (new, 2026-10-31; DECISIONS items 18, 30, 32, 36).

    python3 -I assistant/arena.py [--trust FILE] [--state DIR] [--picture FILE] [--seed 0] [--cap 1000] [--json]

The gate plays the assistant's trust level of simulated days (assistant/simday.py) against the
simulated user, each judged by the six code checks (assistant/checks.py); a day is won only when
all six pass, and the gate passes at the level's wins.

Trust levels stay out of the repo (DECISIONS item 17), the way the Sales agent keeps its own:
--trust names the same JSON file outside the repo that arena/run.py reads, with this agent's
level under "assistant" ({"assistant": {"matches": D, "wins": W}}; matches counts days here).
With no file, or no level for this agent, the public placeholder asks every day won
(arena/run.py PUBLIC_TRUST), so the real level never sits in a public file.

Both sides grow (items 30, 32). A day that beats the assistant comes back more often: the pool
(assistant-days.json in the state folder) counts each seed's losses, and a lost seed is drawn
LOST_WEIGHT times as often per loss. Real days join the pool through add_day (days the user
lived, read back by Reflection with their answers), and a user picture (assistant/mbox.py) seeds
the simulated days with the user's own hours and people.

close_day writes a played day's results to the engine log, so the night study reads them: a
failed urgent check is urgent_missed, a failed clash check is clash, and a won day with no
correction from the user is day_clean. Lessons come only from the user's corrections (item 36):
the plug settles a day as bad only on corrected, so urgent_missed and clash stay Arena win checks,
harm while a lesson is on trial, and signs that a day is worth practising. A lost day the user
did not correct gets day_missed with the cause only_code, so the night study leaves it out of
every count and a miss only the code found never becomes a lesson.

Model calls go through kit/model.py (Muse Spark Open) and count against the Arena's daily cap
(arena/run.py Calls, arena-calls.json in the state folder). A model that does not answer, or the
cap, stops the gate; that day is dropped, never a loss.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I
    sys.path.insert(0, str(ROOT))

from arena import paths  # noqa: E402
from arena import run as arena_run  # noqa: E402
from assistant import checks, simday  # noqa: E402
from assistant.desk import Desk  # noqa: E402
from assistant.loop import run_day  # noqa: E402
from assistant.modes import Modes  # noqa: E402
from kit.model import ModelError  # noqa: E402

AGENT = "assistant"
DAYS_FILE = "assistant-days.json"
LOST_WEIGHT = 3
POOL_SIZE = 50


def load_trust(path):
    """This agent's level from the trust file outside the repo, or the public placeholder."""
    return arena_run.load_trust(path, agent=AGENT)


def case_of(day):
    return f"day:{day['date']}"


def play_day(day, *, model, lessons=None, log=None, added=()):
    """One simulated day with the real loop. Returns (desk, modes, judged)."""
    view = simday.visible(day)
    desk = Desk(items=[e for e in view if e["type"] == "item"], calendar=day["calendar"], rules=day["rules"],
                user_address=day["user"], date=day["date"], contacts=day["contacts"], log=log,
                case=case_of(day) if log is not None else None)
    modes = Modes(day["start_modes"], added=added)
    run_day(view, model=model, desk=desk, modes=modes, user=simday.SimUser(day), lessons=lessons,
            style=day.get("style"))
    return desk, modes, checks.judge(day, desk)


def close_day(log, case, desk, judged):
    """The day's results to the engine log (see the module line)."""
    rows = []
    for f in judged["failed"]:
        name = {"urgent": "urgent_missed", "clash": "clash"}.get(f["check"])
        if name:
            rows.append(log.result(case, name, detail={"item": f.get("item"), "check": f["check"]}))
    corrected = any(a["kind"] == "corrected" for a in desk.answers)
    if judged["won"] and not corrected:
        rows.append(log.result(case, "day_clean"))
    elif not corrected:
        found = sorted({f["check"] for f in judged["failed"]})
        rows.append(log.result(case, "day_missed", cause="only_code", detail={"checks": found}))
    return rows


class Pool:
    """Seeds of simulated days and real days, with how often each beat the assistant."""

    def __init__(self, state):
        self.path = Path(state) / DAYS_FILE
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.seeds = {str(k): v for k, v in (data.get("seeds") or {}).items() if isinstance(v, dict)}
        self.real = [d for d in (data.get("real") or []) if isinstance(d, dict)]

    def weight(self, seed):
        return 1 + LOST_WEIGHT * int(self.seeds.get(str(seed), {}).get("lost", 0))

    def draw(self, rng, seeds):
        seeds = list(seeds)
        return rng.choices(seeds, weights=[self.weight(s) for s in seeds])[0]

    def record(self, seed, won):
        row = self.seeds.setdefault(str(seed), {"played": 0, "lost": 0})
        row["played"] += 1
        row["lost"] += 0 if won else 1

    def add_day(self, day):
        """A real day, cleaned by Reflection and shaped like a simulated one, joins the pool."""
        if not isinstance(day, dict) or "events" not in day or "hidden" not in day:
            raise ValueError("a real day has events and hidden answers, like a simulated one")
        self.real.append(day)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"seeds": self.seeds, "real": self.real}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


def gate(trust, *, model, pool, seeds, rng, picture=None, play=play_day, lessons=None):
    """Play trust["matches"] days; passed when trust["wins"] are won. Stops at a model error or the cap."""
    rep = {"played": 0, "won": 0, "lost": [], "passed": False, "stopped": None,
           "needs": trust["wins"], "of": trust["matches"]}
    drawn = list(seeds) + [f"real:{i}" for i in range(len(pool.real))]
    for _ in range(trust["matches"]):
        seed = pool.draw(rng, drawn)
        day = pool.real[int(seed[5:])] if str(seed).startswith("real:") else simday.build_day(seed, picture)
        try:
            _, _, judged = play(day, model=model, lessons=lessons)
        except (ModelError, arena_run.CapReached) as e:
            rep["stopped"] = type(e).__name__
            break
        rep["played"] += 1
        rep["won"] += judged["won"]
        pool.record(seed, judged["won"])
        if not judged["won"]:
            rep["lost"].append({"seed": seed, "failed": [f["check"] for f in judged["failed"]][:6]})
    rep["passed"] = rep["won"] >= trust["wins"]
    return rep


def main(argv=None, *, model=None):
    ap = argparse.ArgumentParser(prog="assistant/arena.py")
    ap.add_argument("--trust", default=None, help="the trust levels file, outside the repo")
    ap.add_argument("--state", default=str(paths.DATA / "assistant"), help="the Arena's folder: outside the repo or in data/")
    ap.add_argument("--picture", default=None, help="a user picture from assistant/mbox.py")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cap", type=int, default=arena_run.DEFAULT_CAP)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        trust = load_trust(args.trust)
        state = Path(args.state).expanduser().resolve()
        if paths.inside_repo(state) and not paths.within(state, paths.DATA):
            raise arena_run.Refused("the Arena's folder sits inside the repo outside data/")
        picture = json.loads(Path(args.picture).read_text(encoding="utf-8")) if args.picture else None
        calls = arena_run.Calls(state / arena_run.CALLS_FILE, args.cap)
    except (arena_run.Refused, OSError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    if model is None:
        from kit.model import Model
        model = Model()
    pool = Pool(state)
    rep = gate(trust, model=calls.model(model), pool=pool, seeds=range(args.seed, args.seed + POOL_SIZE),
               rng=random.Random(f"assistant-gate:{args.seed}"), picture=picture)
    pool.save()
    if args.json:
        print(json.dumps(rep, ensure_ascii=False))
    else:
        print(f"Assistant Arena: {rep['won']} of {rep['played']} days won, {rep['needs']} of {rep['of']} needed: "
              + ("passed" if rep["passed"] else "not passed") + (f" (stopped: {rep['stopped']})" if rep["stopped"] else ""))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
