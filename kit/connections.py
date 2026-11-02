"""The channels an agent is live on, kept in the database beside its switches (engine/switches.py)
and its pause switch (kit/switch.py). DECISIONS item 77: deploy is the user's step after the Arena.

1. Live means connected. An agent is live on a channel from the moment the user connects it there
   until Pull. Real chats are history, never the switch: an agent with chats and no connection is
   not live (reflection/morning.py Morning._live).
2. Connect. On the agent's page, Connect to WhatsApp unlocks only when the agent's latest Arena
   gate passed (reflection/morning.py Morning.gate). The row keeps the gate result that unlocked
   it, as why, so the page can say what let it go live.
3. Pull. Takes the agent off every channel it is live on, one row a channel.
4. The channel reads it. channels/whatsapp.py answers only while the Sales agent is live on
   WhatsApp; when it is not, it sends nothing and logs one line.

CHANNELS: the channels an agent can ask for, by the tool name a card names (reflection/quickstart.py
TOOLS). WORKS: the channels built so far and the agents each one runs: channels/whatsapp.py runs only
the Sales agent's loop (sales/loop.py). Any later agent asks for the channels its card needs the same
way; a channel not built yet is not connected yet.

Every connect and Pull is one row in agent_connections: the agent, the channel, on or off, why, who
and when. The latest row of an agent and channel wins. Rows are never changed, deleted or replaced.
An agent with no row is on no channel. A read never makes the table, so a page view or a channel's
check on a new database changes nothing and reads as not live.
"""
import time

CHANNELS = {"whatsapp": "WhatsApp", "email": "Email"}  # tool name: the name the page shows
WHATSAPP = "whatsapp"
WORKS = {WHATSAPP: ("sales",)}  # the channels built, and the agents each one runs
ON, OFF = "on", "off"
MAX_WHY = 400

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_connections (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL CHECK (length(trim(agent)) > 0),
  channel TEXT NOT NULL CHECK (length(trim(channel)) > 0),
  value TEXT NOT NULL CHECK (value IN ('on', 'off')),
  why TEXT NOT NULL CHECK (length(trim(why)) > 0),
  by TEXT NOT NULL CHECK (length(trim(by)) > 0),
  at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS agent_connections_latest ON agent_connections (agent, channel, id);
CREATE TRIGGER IF NOT EXISTS agent_connections_never_changed BEFORE UPDATE ON agent_connections
BEGIN SELECT RAISE(ABORT, 'a connection row is never changed; add a new one'); END;
CREATE TRIGGER IF NOT EXISTS agent_connections_never_deleted BEFORE DELETE ON agent_connections
BEGIN SELECT RAISE(ABORT, 'a connection row is never deleted'); END;
CREATE TRIGGER IF NOT EXISTS agent_connections_never_replaced BEFORE INSERT ON agent_connections
WHEN EXISTS (SELECT 1 FROM agent_connections WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'a connection row is never replaced'); END;
"""


def works(agent, channel):
    """Is the channel built, and does it run this agent?"""
    return agent in WORKS.get(channel, ())


def connect(db, agent, channel, *, why, by, now=None):
    """Put the agent live on a channel that works for it. why: the gate result that unlocked it.
    Returns the new reading of that channel ({on, at, why, by})."""
    if channel not in CHANNELS or not works(agent, channel):
        raise ValueError(f"{channel!r} is not a channel {agent!r} can go live on yet")
    return _add(db, agent, channel, ON, why, by, now)


def disconnect(db, agent, channel, *, why, by, now=None):
    """Take the agent off a channel. Returns the new reading of that channel."""
    return _add(db, agent, channel, OFF, why, by, now)


def state(db, agent):
    """{channel: {on, at, why, by}}: the latest row of each channel the agent ever had; {} with none."""
    with db.tx() as c:
        if not _has_table(c):
            return {}
        rows = c.execute("SELECT * FROM agent_connections WHERE id IN (SELECT MAX(id) FROM agent_connections "
                         "WHERE agent = ? GROUP BY channel)", (agent,)).fetchall()
    return {r["channel"]: _reading(r) for r in rows}


def live(db, agent, channel):
    """True while the agent is live on the channel. Reads only."""
    got = state(db, agent).get(channel)
    return bool(got and got["on"])


def live_agents(db):
    """The agents live on at least one channel. Reads only."""
    with db.tx() as c:
        if not _has_table(c):
            return set()
        return {r["agent"] for r in c.execute(
            "SELECT agent FROM agent_connections WHERE id IN (SELECT MAX(id) FROM agent_connections "
            "GROUP BY agent, channel) AND value = 'on'")}


def history(db, agent):
    """Every connect and Pull of the agent, oldest first, as {channel, on, at, why, by}."""
    with db.tx() as c:
        if not _has_table(c):
            return []
        return [dict(_reading(r), channel=r["channel"])
                for r in c.execute("SELECT * FROM agent_connections WHERE agent = ? ORDER BY id", (agent,))]


def _add(db, agent, channel, value, why, by, now):
    agent, channel = _line(agent, "agent", 80), _line(channel, "channel", 40)
    why, by = _line(why, "why", MAX_WHY), _line(by, "by", 80)
    at = time.time() if now is None else float(now)
    db.script(SCHEMA)
    with db.tx() as c:
        c.execute("INSERT INTO agent_connections (agent, channel, value, why, by, at) VALUES (?, ?, ?, ?, ?, ?)",
                  (agent, channel, value, why, by, at))
    return state(db, agent)[channel]


def _reading(r):
    return {"on": r["value"] == ON, "at": r["at"], "why": r["why"], "by": r["by"]}


def _has_table(c):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'agent_connections'").fetchone() is not None


def _line(v, what, most):
    if not isinstance(v, str) or not v.strip() or "\n" in v or "\r" in v or len(v) > most:
        raise ValueError(f"{what}: one line of text, at most {most} characters")
    return v.strip()
