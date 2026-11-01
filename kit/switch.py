"""The pause switch for an agent (DECISIONS item 54: Pull on the agent page is a real pause).

A paused agent sends nothing: no reply and no quiet notice, and no chat closes while it is
paused. Messages that come in are still saved, so the chat is whole when it resumes. After a
resume, quiet is counted from the resume (sales/quiet.py), so no chat closes at once for the
time it was paused.

pause, resume and is_paused are plain functions a page can call. The switch lives in the
agent_switch table, one row per agent; an agent with no row runs.
"""
import time

from kit.db import Db

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_switch (
  agent TEXT PRIMARY KEY,
  paused INTEGER NOT NULL CHECK (paused IN (0, 1)),
  at REAL NOT NULL
);
"""
AGENT = "sales"


def _db(db):
    db = db if db is not None else Db()
    db.script(SCHEMA)
    return db


def _set(agent, paused, db, now):
    if not isinstance(agent, str) or not agent.strip():
        raise ValueError("agent is a name")
    db = _db(db)
    at = time.time() if now is None else float(now)
    with db.tx() as c:
        c.execute("INSERT INTO agent_switch (agent, paused, at) VALUES (?, ?, ?) "
                  "ON CONFLICT (agent) DO UPDATE SET paused = excluded.paused, at = excluded.at",
                  (agent, 1 if paused else 0, at))


def pause(agent=AGENT, *, db=None, now=None):
    """Pause the agent: from now it sends nothing until resume."""
    _set(agent, True, db, now)


def resume(agent=AGENT, *, db=None, now=None):
    """Resume the agent: it answers the next message, and quiet counts from now."""
    _set(agent, False, db, now)


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
