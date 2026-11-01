"""The pause switch for an agent (DECISIONS item 54: Pull on the agent page is a real pause).

A paused agent sends nothing: no reply and no quiet notice, and no chat closes while it is
paused. Messages that come in are still saved, so the chat is whole when it resumes. After a
resume, quiet is counted from the resume (sales/quiet.py), so no chat closes at once for the
time it was paused.

pause, resume and is_paused are plain functions a page can call (Pull and Resume on the agent page,
reflection/pages.py); by names who flipped it. The switch lives in the agent_switch table, one row per
agent; an agent with no row runs. HONOURED: the agents whose code reads the switch, so a page offers
Pull only for them.
"""
import time

from kit.db import Db

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_switch (
  agent TEXT PRIMARY KEY,
  paused INTEGER NOT NULL CHECK (paused IN (0, 1)),
  at REAL NOT NULL,
  set_by TEXT
);
"""
AGENT = "sales"
HONOURED = (AGENT,)  # sales/loop.py and sales/quiet.py read the switch; no other agent does yet


def _db(db):
    db = db if db is not None else Db()
    db.script(SCHEMA)
    with db.tx() as c:  # a switch table made before set_by
        if "set_by" not in {r["name"] for r in c.execute("PRAGMA table_info(agent_switch)")}:
            c.execute("ALTER TABLE agent_switch ADD COLUMN set_by TEXT")
    return db


def _set(agent, paused, db, now, by):
    if not isinstance(agent, str) or not agent.strip():
        raise ValueError("agent is a name")
    if by is not None and (not isinstance(by, str) or not by.strip() or "\n" in by or len(by) > 80):
        raise ValueError("by is a short name on one line")
    db = _db(db)
    at = time.time() if now is None else float(now)
    with db.tx() as c:
        c.execute("INSERT INTO agent_switch (agent, paused, at, set_by) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (agent) DO UPDATE SET paused = excluded.paused, at = excluded.at, set_by = excluded.set_by",
                  (agent, 1 if paused else 0, at, by))


def pause(agent=AGENT, *, db=None, now=None, by=None):
    """Pause the agent: from now it sends nothing until resume. by: who paused it."""
    _set(agent, True, db, now, by)


def resume(agent=AGENT, *, db=None, now=None, by=None):
    """Resume the agent: it answers the next message, and quiet counts from now. by: who resumed it."""
    _set(agent, False, db, now, by)


def is_paused(agent=AGENT, *, db=None):
    """True while the agent is paused."""
    with _db(db).tx() as c:
        row = c.execute("SELECT paused FROM agent_switch WHERE agent = ?", (agent,)).fetchone()
    return bool(row and row["paused"])


def resumed_at(agent=AGENT, *, db=None):
    """When the agent was last resumed, or None when it never was (or is paused now)."""
    with _db(db).tx() as c:
        row = c.execute("SELECT paused, at FROM agent_switch WHERE agent = ?", (agent,)).fetchone()
    return row["at"] if row and not row["paused"] else None


def set_by(agent=AGENT, *, db=None):
    """Who last paused or resumed the agent, or None (no row, or flipped with no name)."""
    with _db(db).tx() as c:
        row = c.execute("SELECT set_by FROM agent_switch WHERE agent = ?", (agent,)).fetchone()
    return row["set_by"] if row else None
