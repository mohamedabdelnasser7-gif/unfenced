"""Try again (new, 2026-11-02; Mohamed: "when a human do some corrections and the matches finished. he
can run another match", "i don't think it needs full run", "try again make sense"; DECISIONS item 80).

After an Arena run has stopped and the user corrected some lost replies (Correct this on the Arena
screen), Try again plays only the practice matches that run lost again, against the same practice
customers: each lost card's saved match (arena-matches.jsonl, the run's last lost match with that
card) is played once more from the same customer opening with the same customer prompt, as the eval
gate reruns a past win (arena/gate.py Gate). The agent plays with its kept lessons and, first, the
corrections that passed their exam and run live as a hotfix (arena/rounds.py live_hotfixes and Pool,
read again before every match). Each match is judged the way the Arena judges it (arena/verdict.py,
with the run's fact checks) and every model call is counted on the Arena's own count file and cap
(arena/run.py Calls), so Try again shares the day's cap with the Arena and the night.

It writes one item next to the database, kind arena_retry: the run it retried and, for each card,
won or lost with a quote for a lost one, or why it was not played. It never holds gate counts and
the retried matches are not saved as past wins, so Try again never unlocks Connect: only a full
Arena run's gate does (reflection/morning.py Morning.gate). The Morning page starts it
(Morning.try_again) in a background thread and reads the item back (Morning.read_arena).
"""
import json
import time
from pathlib import Path

from arena import factcheck, gate as gate_mod, match as match_mod, run as run_mod, verdict

KIND = "arena_retry"
PREFIX = "retry-"  # the retry's run id starts with it: arena-<agent>-retry-<time>.json beside the run's item
STARTED = "Trying the lost matches again with your corrections. This takes a few minutes."
NOT_SAVED = "its saved match was not found"
WON_AGAIN, STILL_LOST, NOT_PLAYED = "won", "lost", "not_played"


def lost_cards(lost):
    """The card ids of an Arena item's lost matches (Morning.read_arena lost), each once, in order."""
    out = []
    for x in lost or []:
        card = str((x or {}).get("card") or "")
        if card and card not in out:
            out.append(card)
    return out


def saved_lost(state, run, cards):
    """{card: the run's last lost match with that card} from the matches saved in state. A match is
    the run's when its id starts with the run's id; a line that cannot be read is skipped."""
    want, out = set(cards), {}
    try:
        lines = (Path(state) / run_mod.MATCHES_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            m = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(m, dict) or m.get("won") is not False or m.get("card") not in want:
            continue
        if isinstance(m.get("id"), str) and m["id"].startswith(f"{run}-") and m.get("turns"):
            out[m["card"]] = m
    return out


def has_room(state, cap=run_mod.DEFAULT_CAP):
    """Does the day's call count in state have room for one more model call? A count file that
    cannot be read has none (Calls fails closed)."""
    calls = run_mod.Calls(Path(state) / run_mod.CALLS_FILE, cap)
    return calls.problem is None and calls.count < calls.cap


def retry(*, agent, run, cards, state, reports, pool, agent_model, customer_model, facts=True,
          cap=run_mod.DEFAULT_CAP, now=time.time):
    """Play each card's lost match of run again and write the arena_retry item. pool: the lessons the
    matches hand (arena/rounds.py Pool on the agent's kept lessons, with its live hotfixes). Stops at
    the call cap or at a model that does not answer; the cards left are not played. Returns the item,
    with "file" set to its name."""
    from reflection.exam import _Lessons
    calls = run_mod.Calls(Path(state) / run_mod.CALLS_FILE, cap)
    a_model, c_model = calls.model(agent_model), calls.model(customer_model)
    lessons = _Lessons(pool, None)
    saved = saved_lost(state, run, cards)
    results, stopped, error = [], None, ""
    for card in cards:
        if stopped:
            results.append({"card": card, "result": NOT_PLAYED, "why": "the try stopped before it"})
            continue
        past = saved.get(card)
        persona = past.get("persona") if past else None
        prompt = gate_mod._prompt_of(past) if isinstance(persona, dict) else None
        if past is None or not isinstance(persona, dict):
            results.append({"card": card, "result": NOT_PLAYED, "why": NOT_SAVED})
            continue
        if prompt is None:
            results.append({"card": card, "result": NOT_PLAYED, "why": gate_mod.PROMPT_GONE})
            continue
        pool.refresh()  # the corrections that passed since the last match
        try:
            m = match_mod.play(persona, agent_model=a_model, customer_model=c_model, prompt=prompt, lessons=lessons,
                               seed=past.get("id"), opening=match_mod.first_line(past), checker=factcheck.check,
                               stop=verdict.closed)
        except run_mod.CapReached:
            m = None
        if m is None or calls.reached:
            stopped = run_mod.CAP
        elif m.get("ended") == match_mod.VOID:
            stopped, error = run_mod.MODEL_ERROR, m.get("error") or ""
        if stopped:
            results.append({"card": card, "result": NOT_PLAYED, "why": "the try stopped here"})
            continue
        judged = verdict.judge(m, facts=facts)
        got = {"card": card, "result": WON_AGAIN if judged["won"] else STILL_LOST, "why": judged["why"]}
        if not judged["won"]:
            got["quote"] = judged["quote"]
        results.append(got)
    at = now()
    rid = PREFIX + time.strftime("%Y%m%dT%H%M%S", time.gmtime(at))
    won = sum(r["result"] == WON_AGAIN for r in results)
    played = sum(r["result"] != NOT_PLAYED for r in results)
    item = {"agent": agent, "kind": KIND, "at": at, "run": rid, "retried": run, "results": results,
            "stopped": stopped, "hotfixes": list(pool.seen), "calls": calls.taken,
            "line": f"Try again played {played} of the {len(cards)} lost matches of run {run}: {won} won this time."}
    if error:
        item["error"] = error
    folder = Path(reports)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"arena-{agent}-{rid}.json"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    item["file"] = path.name
    return item
