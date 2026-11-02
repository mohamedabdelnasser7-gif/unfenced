"""The night's API check (DECISIONS item 66): before the study, ask the courier's API for the
result of each case still waiting on one, so a result the webhook missed still lands.

For each agent whose plug names delivered or refused among its late results (engine/plug.py
Plug.late): its cases with no result of that group yet (no deciding result, when delivered or
refused decides; a good case with no second signal yet, when they are its second signal, as for
Sales), read over the plug's days (engine/study.py read_days) twice over, newest first. A case is
asked about only when one of its rows names a tracking number: "tracking" in an action's detail,
or "bosta" on a row the webhook saved (a failed attempt or another result). The Sales agent's
order rows carry the store's order number and no tracking number, so for Sales the API check
reaches only orders Bosta already told the webhook about; the rest wait for the webhook or for a
person on the morning page (docs/known-limits.md).

What the API can say is in channels/bosta.py api_outcome: delivered, or returned to the business
(recorded as refused). A refusal at the door is not in the API's view and never comes from here.
Each answer goes through reflection/results.py late(), by "api", once a case for its group, so a
person or the webhook that came first wins. At most MAX_ASKS calls a run, one at a time; a call
that fails is counted and the run goes on. With no BOSTA_API_KEY the check does nothing and says
so. Nothing here prints the key.
"""
from engine.log import Log, case_key
from engine.study import GOOD, read_days, settle
from reflection.results import late

DAY = 86400.0
MAX_ASKS = 200
COURIER = ("delivered", "refused")


def waiting(db, plug, now):
    """[(case id, tracking number)] this plug's cases that wait on a courier result, newest first."""
    deciding, second = plug.late()
    groups = [g for g in (deciding, second) if set(COURIER) & set(g)]
    if not groups:
        return []
    since = now - 2 * read_days(plug) * DAY
    out = []
    cases = Log(db, plug).window(since, now)
    for case_id, rows in sorted(cases.items(), key=lambda kv: -kv[1][-1]["at"]):
        if any((r["detail"] or {}).get("history") for r in rows):
            continue
        have = {r["result"] for r in rows}
        need = False
        if deciding in groups and not have & set(deciding):
            need = True
        if second in groups and not have & set(second) and settle(plug, rows, now)[0] == GOOD:
            need = True
        tracking = next((t for r in reversed(rows) for t in [_tracking(r)] if t), None)
        if need and tracking:
            out.append((case_key(case_id), tracking))
    return out


def _tracking(row):
    d = row["detail"] or {}
    t = d.get("tracking") if row["action"] is not None else d.get("bosta")
    t = str(t) if isinstance(t, (str, int)) and not isinstance(t, bool) else ""
    return t if t.isalnum() and len(t) <= 64 else ""


def check(db, plugs, fetch, *, now, limit=MAX_ASKS):
    """Ask fetch(tracking) -> (outcome or None, state code) for each waiting case of each plug, at
    most limit calls in all. Returns {asked, recorded, already, failed, by_agent}."""
    rep = {"asked": 0, "recorded": 0, "already": 0, "failed": 0, "by_agent": {}}
    for plug in plugs:
        mine = rep["by_agent"].setdefault(plug.agent, 0)
        takes = {r for g in plug.late() for r in g}
        for case_id, tracking in waiting(db, plug, now):
            if rep["asked"] >= limit:
                return rep
            rep["asked"] += 1
            try:
                outcome, code = fetch(tracking)
            except Exception:
                rep["failed"] += 1
                continue
            if outcome not in takes:
                continue
            row = late(db, plug, case_id, outcome, by="api", now=now,
                       detail={"bosta": tracking, "state": code, "from": "api"})
            if row is None:
                rep["already"] += 1
            else:
                rep["recorded"] += 1
                mine += 1
                rep["by_agent"][plug.agent] = mine
    return rep


def run(db, plugs, *, now, key=None, opener=None):
    """The night's check with Bosta's API: None when BOSTA_API_KEY is not set (nothing asked)."""
    from channels import bosta
    from kit import env
    key = env.get(bosta.API_KEY) if key is None else key
    if not key:
        return None
    return check(db, plugs, lambda t: bosta.api_outcome(t, key, opener=opener), now=now)


def line(rep):
    """One plain line for the night report."""
    if rep is None:
        return "courier API check: not run, no BOSTA_API_KEY"
    return (f'courier API check: {rep["asked"]} asked, {rep["recorded"]} results recorded, '
            f'{rep["already"]} already had one, {rep["failed"]} calls failed')

