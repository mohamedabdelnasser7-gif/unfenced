"""Won or lost for one Arena match (new, 2026-10-30), decided in code and quoting the turn it
decides on.

A match is won only when the agent's draft_order placed the order (kit/tools/draft_order.py
created), quoting the customer's line on that turn. The customer's yes or address alone is not a
win: the agent still has to place the order, the way a real store would (strict win rule after
review round 3, 2026-10-30). The agent's own words that the order is placed never count; with no
order made they fail the order fact check (arena/factcheck.py claims_order). The replay labels
(arena/label.py) still read the customer's words on real chats, where the store is a person.
With fact checks on (the default; facts=False turns it off), a match with any failed fact
check (arena/factcheck.py) is lost, quoting the first reply that failed, whatever else happened.
Lost otherwise, quoting the turn the match ended on: the reply the customer left after, the
turn with no safe reply (nothing was sent, so its quote is empty), or the last reply when the
turns ran out. A match recorded before DECISIONS item 53 may end "handed_off"; it reads as before.

A match on a close card (no offer covers its need, arena/offers.py; the match's "close") that ended
with no sale and no failed check, and not with no safe reply, is lost as above with "needs_close": True,
so arena/run.py Arena.play asks the close judge (arena/close.py) whether it was a correct close; with
no close judge the loss stands (decision 105).

judge(match, facts=True) -> {"won": bool, "why": str, "quote": {"turn", "who", "text"}}.
"""
from arena.match import plain

WON_ORDER = "order placed on the customer's yes"
FAILED = "failed fact check"
LEFT = "the customer left after this reply"
HANDED = "the chat went to a person"  # matches recorded before item 53
NO_SAFE = "no safe reply could be sent"
OUT_OF_TURNS = "no sale within the turns"
NO_TURNS = "no customer line"


def closed(turns):
    """True once a tool placed the order, fact checks aside: the match can end there."""
    return judge({"turns": turns, "ended": "turns"}, facts=False)["won"]


def _quote(turn, who, text):
    return {"turn": turn, "who": who, "text": plain(text)}


def judge(match, facts=True):
    turns = match.get("turns") or []
    if not turns:
        return {"won": False, "why": NO_TURNS, "quote": _quote(0, "customer", "")}
    if facts:
        for t in turns:
            if t.get("failed"):
                f = t["failed"][0]
                return {"won": False, "why": f"{FAILED}: {f['check']}: {f['why']}",
                        "quote": _quote(t["n"], "agent", " ".join(t["replies"]))}
    for t in turns:
        if t.get("order"):
            return {"won": True, "why": WON_ORDER, "quote": _quote(t["n"], "customer", t["customer"])}
    last = turns[-1]
    why = {"left": LEFT, "no_safe_reply": NO_SAFE, "handed_off": HANDED}.get(match.get("ended"), OUT_OF_TURNS)
    out = {"won": False, "why": why, "quote": _quote(last["n"], "agent", " ".join(last["replies"]))}
    if match.get("close") is True and match.get("ended") != "no_safe_reply":
        out["needs_close"] = True
    return out
