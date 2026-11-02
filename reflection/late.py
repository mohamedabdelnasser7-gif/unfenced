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
person or the webhook that came first wins. Each is saved BEFORE seconds ahead of the night's own
time, since the study reads rows before that time (engine/log.py window): tonight's study sees what
this check brought. At most MAX_ASKS calls a run, one at a time; a call
that fails is counted and the run goes on. With no BOSTA_API_KEY the check does nothing and says
so. Nothing here prints the key.
"""
import hashlib
import hmac
import re
import secrets

from engine.log import Log, case_key, is_history
from engine.study import GOOD, PENDING, read_days, settle
from reflection.results import late

DAY = 86400.0
MAX_ASKS = 200
BEFORE = 0.001       # seconds: an API result is saved this much before the night's own time
COURIER = ("delivered", "refused")
_REF = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
REF_SCHEMA = "CREATE TABLE IF NOT EXISTS case_ref_key (id INTEGER PRIMARY KEY CHECK (id = 1), key TEXT NOT NULL)"


def takes(plug):
    """(deciding, second): the late results of this plug (Plug.late) that may come on their own,
    so a webhook, the API or a person may add them (results.late refuses one that ends an action)."""
    return tuple(tuple(r for r in group if plug.result(r).after is None) for group in plug.late())


def open_cases(db, plug, *, since, now, log=None):
    """[(case id, rows, names)] this plug's cases with a row in [since, now) that still wait on a
    late result, in the window's order: a pending case (no deciding result, no cause) takes the
    deciding results; a good case with no second signal result yet takes the second signal's. A case
    imported from the past is never one. names: the results that case may take."""
    deciding, second = takes(plug)
    if not deciding and not second:
        return []
    out = []
    for case_id, rows in (log or Log(db, plug)).window(since, now).items():
        if any(is_history(r) for r in rows):
            continue
        status = settle(plug, rows, now)[0]
        if status == PENDING and deciding:
            names = deciding
        elif status == GOOD and second and not {r["result"] for r in rows} & set(second):
            names = second
        else:
            continue
        out.append((case_key(case_id), rows, names))
    return out


def ref_key(db, *, make=None):
    """The key behind made references (case_ref): made once at random and kept in the database
    (one row in case_ref_key), so a reference cannot be worked back to its case id by trying every
    phone number. Two writers at the same moment still keep one key. make: gives a new key as 64
    hex letters (the made-up sample days give a fixed one, so the same seed gives the same days)."""
    with db.tx() as c:
        c.execute(REF_SCHEMA)
        c.execute("INSERT OR IGNORE INTO case_ref_key (id, key) VALUES (1, ?)", ((make or _new_key)(),))
        return bytes.fromhex(c.execute("SELECT key FROM case_ref_key WHERE id = 1").fetchone()["key"])


def _new_key():
    return secrets.token_hex(32)


def case_ref(plug, case_id, rows, key):
    """What a person calls a case on the morning page and in a sheet: its order number when a row
    names one ("#1001" is 1001), else c- and ten letters, an HMAC SHA256 of the agent and the case
    id under key (ref_key), so no raw case id (a phone number, say) is ever on the page or can be
    worked out from it."""
    for r in reversed(rows):
        ref = norm_ref((r["detail"] or {}).get("order"))
        if ref:
            return ref
    return "c-" + hmac.new(key, f"{plug.agent}\0{case_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:10]


def norm_ref(value):
    """A case reference as typed or saved, checked: "#1001" and " 1001 " are 1001; "" when it is
    not one (letters, digits, dot, dash and underscore only, at most 40)."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    ref = str(value).strip().lstrip("#").strip()
    return ref if _REF.match(ref) else ""


def waiting(db, plug, now):
    """[(case id, tracking number)] this plug's cases that wait on a courier result, newest first."""
    since = now - 2 * read_days(plug) * DAY
    out = []
    for case_id, rows, names in sorted(open_cases(db, plug, since=since, now=now), key=lambda c: -c[1][-1]["at"]):
        tracking = next((t for r in reversed(rows) for t in [_tracking(r)] if t), None)
        if set(COURIER) & set(names) and tracking:
            out.append((case_id, tracking))
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
            row = late(db, plug, case_id, outcome, by="api", now=now - BEFORE,
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
    if rep.get("broke"):
        return f'courier API check: stopped ({rep["broke"]}); the night went on'
    return (f'courier API check: {rep["asked"]} asked, {rep["recorded"]} results recorded, '
            f'{rep["already"]} already had one, {rep["failed"]} calls failed')

