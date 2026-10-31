"""Run the night study on the simulated scenarios and print, for each agent, what it found,
what it ignored, what it held for a yes and what it refused. Every case is made up and labelled
simulated. The study is the real one (engine/study.py); its model parts are scripted
(sim/scripted.py), so the run makes no model call and gives the same answer every time for the
same seed. The scripted candidates match what was planted, plus one per scenario that matches
nothing planted; the study only counts and decides.

    python3 -I sim/run.py [--seed N] [--json]

It runs every scenario file in sim/scenarios, each with the plug in the folder its agent
names (<agent>/plug.json), so it names no agent itself.

found: the lesson cards the study wrote, with their state, the pattern each came from,
whether that pattern helps or hurts, and its numbers. An adapted card's numbers are the
other agent's, counted on its cases with its own good result, and say so.
ignored: the cases left out because their result had a cause outside the agent, by cause.
held for a yes: lessons that copy words from the cases they came from. For an agent whose
case id names its source, one line under them says that the copied words mark, not the
sources rule, holds a ring of cases there.
refused: patterns stopped because too few different sources stood behind them.
not proven: every other candidate, with why and its numbers.

All scenarios go into one log, held in memory and closed when the run ends, so each agent's
study also reads the others' cases. --json prints the same summary as data, for the morning
page.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import plug as plug_mod  # noqa: E402
from engine import risk  # noqa: E402
from engine import study as study_mod  # noqa: E402
from engine.lessons import Lessons  # noqa: E402
from engine.study import Study  # noqa: E402
from kit.db import Db  # noqa: E402
from sim import scripted, simulate  # noqa: E402



def _agents():
    """(plug path, scenario path) for every scenario file, sorted. The plug is the one in the
    folder the scenario's agent names."""
    pairs = []
    for path in (ROOT / "sim" / "scenarios").glob("*.json"):
        agent = json.loads(path.read_text(encoding="utf-8")).get("agent")
        if not isinstance(agent, str) or not agent.isidentifier():
            raise ValueError(f"{path.name}: the agent must be a plain name")
        pairs.append((f"{agent}/plug.json", f"sim/scenarios/{path.name}"))
    return tuple(sorted(pairs))


AGENTS = _agents()
NOT_PROVEN = (study_mod.FEW_CASES, study_mod.NO_GAP)
HELD = "it copies words from the cases it came from"


def night(pairs=AGENTS, *, seed=None):
    """Simulate every scenario into one log held in memory, then run each agent's night study
    in turn, with the other agents given. Returns [(plug, manifest, report)]. The log is closed
    before it returns, so no lesson from simulated cases outlives the run."""
    db = Db(":memory:")
    try:
        loaded = [(plug_mod.load(ROOT / p), simulate.load(ROOT / s)) for p, s in pairs]
        manifests = [simulate.simulate(db, p, sc, seed=seed) for p, sc in loaded]
        since = min(m["since"] for m in manifests)
        until = max(m["until"] for m in manifests)
        proposer, tagger, fit, adapter = scripted.parts(*(sc for _, sc in loaded))
        out = []
        for (p, _), man in zip(loaded, manifests):
            others = [q for q, _ in loaded if q.agent != p.agent]
            lessons = Lessons(db, p, judge=scripted.judge_says_low)
            rep = Study(db, p, proposer=proposer, tagger=tagger, fit=fit, adapter=adapter, others=others,
                        lessons=lessons).run(since, until, now=until)
            out.append((p, man, rep))
        return out
    finally:
        db.close()


def summary(plug, manifest, rep, plugs=()):
    """One agent's night as plain data: found, ignored, held, refused and not proven. plugs: every
    agent of the run; an adapted card's numbers are named with its source agent's good result,
    and an agent whose case names its source is told which agents show the sources rule."""
    by_agent = {p.agent: p for p in plugs}
    by_agent[plug.agent] = plug
    found, held, refused, not_proven = [], [], [], []
    behind = {c["lesson_id"]: c for c in rep["candidates"] + [c for a in rep["across"] for c in a["candidates"]]
              if c.get("lesson_id") is not None}  # the candidate each card came from, here or there
    for card in rep["cards"]:
        at = card["from"]["agent"] if card["from"] else plug.agent
        counted = {"agent": at, "good": by_agent[at].decides.good if at in by_agent else None}
        cand = behind.get(card["lesson_id"], {})
        item = {"lesson": card["change"], "pattern": cand.get("pattern"), "helps": cand.get("helps"),
                "state": card["state"], "risk": card["risk"], "why": card["risk_why"],
                "sure": card["sure"], "cases": card["cases"], "counted": counted, "from": card["from"],
                "close_to_pulled": card["close_to_pulled"], "waits_for": card.get("waits_for"),
                "replace": card.get("replace")}
        if risk.COPIED in (card["risk_why"] or ""):
            held.append(dict(item, held=HELD))
        else:
            found.append(item)
    for c in rep["candidates"]:
        if c["verdict"] == study_mod.FEW_SOURCES:
            refused.append({"pattern": c["pattern"], "lesson": c["lesson"], "with": c["with"], "without": c["without"],
                            "sure": c["chance"],
                            "refused": f"only {min(c['with']['sources'], c['without']['sources'])} different "
                                       f"source(s) behind one side; {study_mod.MIN_SOURCES} are needed"})
        elif c["verdict"] in NOT_PROVEN:
            not_proven.append({"pattern": c["pattern"], "why": c["verdict"], "with": c["with"], "without": c["without"],
                               "sure": c["chance"]})
    note = None
    if plug.source.known_by == plug_mod.CASE:
        shown = sorted(a for a, p in by_agent.items() if p.source.known_by == plug_mod.ROW)
        note = (f"One case is one source here, so a ring of cases is held by the copied words mark, not the "
                f"{study_mod.MIN_SOURCES} sources rule" + (f"; that rule is shown on {', '.join(shown)}." if shown
                                                           else "."))
    return {"agent": plug.agent, "simulated": True, "seed": manifest["seed"],
            "window": rep["window"], "good": plug.decides.good,
            "read": rep["read"]["cases"], "settled": rep["decided"], "pending": rep["pending"],
            "found": found,
            "ignored": {"cases": rep["left_out"]["count"],
                        "by_cause": {k: {"cases": n, "about": plug.causes.get(k, "")}
                                     for k, n in sorted(rep["left_out"]["by_cause"].items())}},
            "held": held, "sources_note": note, "refused": refused, "not_proven": not_proven}


def text(s):
    """One agent's summary as plain lines."""
    w = s["window"]
    lines = [f'{s["agent"]}: {s["read"]} simulated cases (seed {s["seed"]}), {_day(w["since"])} to {_day(w["until"])}',
             f'  settled {s["settled"]["good"] + s["settled"]["bad"]} ({s["settled"]["good"]} {s["good"]}, '
             f'{s["settled"]["bad"]} not), pending {s["pending"]}',
             f'  found {len(s["found"])}']
    for f in s["found"]:
        held = "on trial" if f["state"] == "trying" else f'waits for a yes ({f["risk"]} risk: {f["why"]})'
        if f.get("close_to_pulled"):
            held = f'waits for a yes (close to the pulled line "{f["close_to_pulled"]}")'
        if f.get("waits_for"):
            held = "waits its turn behind lesson " + ", ".join(str(i) for i in f["waits_for"])
        if f.get("replace"):
            held = f'waits for a yes: replace lesson {f["replace"]["lesson_id"]} "{f["replace"]["line"]}"?'
        came = f' (adapted from {f["from"]["agent"]})' if f["from"] else ""
        lines.append(f'    - "{f["lesson"]}"{came}: {held}')
        if f["cases"]:
            c, at = f["cases"], f["counted"]
            there = "" if at["agent"] == s["agent"] else f'from {at["agent"]}\'s cases: '
            way = "helps" if f["helps"] else "hurts"
            lines.append(f'      {there}pattern "{f["pattern"]}" {way}: with it {c["good_with"]} of {c["with"]} '
                         f'{at["good"] or "good"}, without it {c["good_without"]} of {c["without"]}; chance it '
                         f'{way} {_pct(f["sure"])}')
    lines.append(f'  ignored {s["ignored"]["cases"]} cases with a cause outside the agent')
    for cause, v in s["ignored"]["by_cause"].items():
        lines.append(f'    - {cause}: {v["cases"]} ({v["about"]})')
    lines.append(f'  held for a yes {len(s["held"])}')
    for h in s["held"]:
        lines.append(f'    - "{h["lesson"]}": {h["held"]}')
    if s["sources_note"]:
        lines.append(f'    {s["sources_note"]}')
    lines.append(f'  refused {len(s["refused"])}')
    for r in s["refused"]:
        lines.append(f'    - "{r["lesson"]}": {r["refused"]}')
    if s["not_proven"]:
        lines.append(f'  not proven {len(s["not_proven"])}')
        left = s["ignored"]["cases"]
        for n in s["not_proven"]:
            w, wo = n["with"], n["without"]
            line = (f'    - "{n["pattern"]}": {n["why"]}; with the pattern {w["good"]} of {w["cases"]} '
                    f'{s["good"] or "good"}, without it {wo["good"]} of {wo["cases"]}')
            if n["why"] == study_mod.FEW_CASES and left:
                line += f"; the {left} cases left out for a cause outside the agent are not counted"
            lines.append(line)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The night study on simulated cases: found, ignored, refused.")
    ap.add_argument("--seed", type=int, default=None, help="one seed for every scenario; each file's own by default")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = ap.parse_args(argv)
    nights = night(seed=args.seed)
    plugs = [p for p, _, _ in nights]
    out = [summary(p, man, rep, plugs) for p, man, rep in nights]
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print("Simulated data: every case below is made up. Model parts are scripted; no model was called.\n"
              "Candidates are scripted to match what was planted; the study only counts and decides.\n")
        print("\n\n".join(text(s) for s in out))
    return 0


def _pct(x):
    """A chance as a whole percent. One that rounds to 100 prints "over 99%": the study is never
    sure."""
    n = round(x * 100)
    return "over 99%" if n >= 100 else f"{n}%"


def _day(t):
    return time.strftime("%d %b %Y", time.gmtime(t))


if __name__ == "__main__":
    sys.exit(main())
