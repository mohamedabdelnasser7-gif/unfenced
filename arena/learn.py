"""A lost Arena match as a Sales agent case the night study reads (new, 2026-10-30; DECISIONS
items 6 and 7: Reflection sends lessons back to the Arena, and the Arena's losses feed Reflection).

No second case shape: the match is written into the Sales agent's log (engine/log.py through
reflection/results.py, the rows sales/loop.py writes live), one row a turn with the action and
result the turn ended with, under the case id "arena-<match id>". Each row's detail holds the
customer's line and the agent's reply (the text the study's proposer and tagger read), the
failed fact checks and, on the last row, the verdict and its quote. arena/run.py hands it the
Arena's own copy of the database (<db>.arena, DECISIONS item 46), so the case never reaches the
live agent's log.

An Arena match has no courier: it is written as a chat that closed with no order, its last row
followed by chat_closed, which engine/study.py settle reads as not good, the same as a live chat
that closed after quiet and an imported chat with no order (no timer settles a case, DECISIONS
item 66). Its rows are timed one day past study.read_days before now, so a live read of the last
days never meets them. Every row
says "arena": true and "history": true, so a trial never counts it (engine/trial.py: only live
results judge a trial). An off topic match (arena/scope.py) has "kind": "scope" on every row too, so the
study writes from it only its general decline line, never a refusal of a topic (engine/study.py, see 9).
"""
import time

from engine.study import SCOPE, read_days
from reflection import PLUG
from reflection.results import Results

DAY = 86400.0
TURN_SECONDS = 60.0


def case_id(match_id):
    return f"arena-{match_id}"


def to_case(db, match, judged, match_id, *, now=None):
    """Write one lost match into the log. Returns its case id; refuses a won match."""
    if judged.get("won"):
        raise ValueError("only a lost match becomes a case")
    log = Results(db)
    now = time.time() if now is None else float(now)
    start = now - (read_days(PLUG) + 1) * DAY
    case = case_id(match_id)
    turns = match.get("turns") or []
    kind = {"kind": SCOPE} if match.get("off_scope") else {}  # an off topic match (engine/study.py, see 9)
    for i, t in enumerate(turns):
        outcome = t.get("outcome")
        declared = PLUG.results.get(outcome)
        if declared is None or not declared.after:
            outcome = "replied"
        detail = {"arena": True, "history": True, "match": match_id, "card": match.get("card"),
                  "worry": match.get("worry"), "customer": t.get("customer"), "reply": " ".join(t.get("replies") or []),
                  **kind}
        if t.get("failed"):
            detail["failed_checks"] = t["failed"]
        if i == len(turns) - 1:
            detail["verdict"] = judged.get("why")
            detail["quote"] = judged.get("quote")
        log.act(case, PLUG.result(outcome).after, result=outcome, stage="asking", step=i + 1, detail=detail,
                at=start + i * TURN_SECONDS)
    log.result(case, "chat_closed", step=len(turns) + 1, at=start + len(turns) * TURN_SECONDS,
               detail={"arena": True, "history": True, "match": match_id, **kind})
    return case
