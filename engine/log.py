"""The log: every action an agent takes in a case, with the ids of the lessons it was
given, and every result, at once or days later.

A case is one unit of an agent's work; the agent names it (its plug says what one case
is). A row is one of three things:
  an action with its fast result, when the plug says that result ends the action;
  an action whose result is not known yet;
  a result that comes on its own and attaches by case (every slow result does).
Every name is checked against the agent's plug; a cause can go with a result when the
result was not the agent's fault. The night study reads this log by agent, case,
action, result, source and time; window() gives it every case touched in a time window.

Every row has a source: who or what its case comes from (the plug's source says what one
is). When the plug says the case id names its source, the log keeps the case id as the
source. When each row names it, an action is saved with its source, and a result that
comes on its own takes the source its case already has (none when the case has no row
yet; the result is still saved). A log made before sources gets the column on its first
start, and the case id as the source of each row whose case names it.
"""
import json
import time

from engine.plug import CASE

SCHEMA = """
CREATE TABLE IF NOT EXISTS trace (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  case_id TEXT NOT NULL,
  action TEXT,
  result TEXT,
  cause TEXT,
  lessons TEXT NOT NULL DEFAULT '[]',
  stage TEXT,
  step INTEGER,
  detail TEXT,
  at REAL NOT NULL,
  source TEXT,
  CHECK (action IS NOT NULL OR result IS NOT NULL),
  CHECK (cause IS NULL OR result IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS trace_case ON trace (agent, case_id);
CREATE INDEX IF NOT EXISTS trace_result ON trace (agent, result, at);
CREATE INDEX IF NOT EXISTS trace_at ON trace (agent, at);
"""
SOURCE_INDEX = "CREATE INDEX IF NOT EXISTS trace_source ON trace (agent, source)"


class Log:
    """One agent's view of the log: it writes only under its own plug's name and names."""

    def __init__(self, db, plug):
        self.db = db
        self.plug = plug
        self.db.script(SCHEMA)
        with self.db.tx() as c:
            if "source" not in {r["name"] for r in c.execute("PRAGMA table_info(trace)")}:
                c.execute("ALTER TABLE trace ADD COLUMN source TEXT")  # a log made before sources
            c.execute(SOURCE_INDEX)
        self.fill_sources()

    def fill_sources(self):
        """When the case names its source: each of this agent's rows with no source takes its case id."""
        if self.plug.source.known_by == CASE:
            with self.db.tx() as c:
                c.execute("UPDATE trace SET source = case_id WHERE agent = ? AND source IS NULL", (self.plug.agent,))

    def act(self, case, action, *, lessons=(), result=None, cause=None, stage=None, step=None, detail=None,
            at=None, source=None):
        """Save one action in a case with the ids of the lessons it was given, and its result when
        the plug says that result ends this action. source: needed when each row names its
        source; when the case names it, left out or the case id. Returns the row id."""
        self.plug.action(action)
        if result is not None and self.plug.result(result).after != action:
            raise ValueError(f"{result!r} does not end the action {action!r}")
        if cause is not None:
            if result is None:
                raise ValueError("a cause goes with a result")
            self.plug.cause(cause)
        source = self._source(case, source, needed=True)
        return self._add(case, action, result, cause, lessons, stage, step, detail, at, source)

    def result(self, case, result, *, cause=None, stage=None, step=None, detail=None, at=None, source=None):
        """Save a result that comes on its own; it attaches to the case. source: optional; when
        left out, the source the case already has. Returns the row id."""
        after = self.plug.result(result).after
        if after is not None:
            raise ValueError(f"{result!r} ends the action {after!r}; save it with act")
        if cause is not None:
            self.plug.cause(cause)
        source = self._source(case, source, needed=False)
        return self._add(case, None, result, cause, (), stage, step, detail, at, source)

    def query(self, *, agent=None, case=None, action=None, result=None, source=None, since=None, until=None):
        """Rows oldest first. agent: this plug's agent unless named. since and until are times in
        seconds; since is included, until is not."""
        agent = self.plug.agent if agent is None else agent
        if agent == self.plug.agent:  # a typo in one of our own names fails loudly
            if action is not None:
                self.plug.action(action)
            if result is not None:
                self.plug.result(result)
        sql, args = "SELECT * FROM trace WHERE agent = ?", [agent]
        for column, op, value in (("case_id", "=", None if case is None else case_key(case)), ("action", "=", action),
                                  ("result", "=", result), ("source", "=", None if source is None else source_key(source)),
                                  ("at", ">=", since), ("at", "<", until)):
            if value is not None:
                sql += f" AND {column} {op} ?"
                args.append(value)
        with self.db.tx() as c:
            rows = c.execute(sql + " ORDER BY id", args).fetchall()
        return [_row(r) for r in rows]

    def case(self, case):
        """Everything in one case, oldest first."""
        return self.query(case=case)

    def window(self, since, until, *, agent=None, plug=None):
        """Every case with a row in the window, as {case id: its rows, oldest first}, each case
        where it first showed. Rows go by their time, then by when they were saved, so a row
        timed after a case's deciding result never reads as before it. Each case is read up to
        until, rows from before since too; a row at or after until is not known yet. agent:
        this plug's agent unless named.

        A second signal result saved on its own (plug.second_signal, DECISIONS item 67) never
        brings a case into the window: it shows how an older good case held, so one saved tonight
        on a case from last month leaves that case out of tonight's study. A slow deciding result
        still brings its case in. plug: the plug of the agent read, for its
        second signal; this log's plug for its own agent."""
        agent = self.plug.agent if agent is None else agent
        if plug is None and agent == self.plug.agent:
            plug = self.plug
        second = () if plug is None or plug.second_signal is None else \
            (plug.second_signal.good, *plug.second_signal.bad)
        skip = (" AND NOT (action IS NULL AND result IN (" + ", ".join("?" * len(second)) + "))") if second else ""
        with self.db.tx() as c:
            rows = c.execute("SELECT * FROM trace WHERE agent = ? AND at < ? AND case_id IN "
                             "(SELECT case_id FROM trace WHERE agent = ? AND at >= ? AND at < ?" + skip + ") "
                             "ORDER BY at, id",
                             (agent, float(until), agent, float(since), float(until), *second)).fetchall()
        out = {}
        for r in rows:
            row = _row(r)
            out.setdefault(row["case_id"], []).append(row)
        return out

    def agents(self, since, until):
        """Every agent with a row in the window, by name."""
        with self.db.tx() as c:
            rows = c.execute("SELECT DISTINCT agent FROM trace WHERE at >= ? AND at < ? ORDER BY agent",
                             (float(since), float(until))).fetchall()
        return [r["agent"] for r in rows]

    def _source(self, case, source, *, needed):
        """The source a new row is saved with, from the plug's rule."""
        key = case_key(case)
        if self.plug.source.known_by == CASE:
            if source is not None and source_key(source) != key:
                raise ValueError(f"for {self.plug.agent} the case id names the source; leave source out")
            return key
        if source is not None:
            return source_key(source)
        if needed:
            raise ValueError(f"{self.plug.agent} saves each action with its source")
        with self.db.tx() as c:  # a result on its own: the source its case already has
            row = c.execute("SELECT source FROM trace WHERE agent = ? AND case_id = ? AND source IS NOT NULL "
                            "ORDER BY id DESC LIMIT 1", (self.plug.agent, key)).fetchone()
        return row["source"] if row else None

    def _add(self, case, action, result, cause, lessons, stage, step, detail, at, source):
        ids = lesson_ids(lessons)
        with self.db.tx() as c:
            cur = c.execute(
                "INSERT INTO trace (agent, case_id, action, result, cause, lessons, stage, step, detail, at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.plug.agent, case_key(case), action, result, cause, json.dumps(ids), stage, step,
                 json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                 time.time() if at is None else float(at), source))
            return cur.lastrowid


def case_key(case):
    """A case id as the log keeps it: text, never empty."""
    if isinstance(case, bool) or not isinstance(case, (str, int)) or not str(case).strip():
        raise ValueError(f"a case id is text or a whole number, not {case!r}")
    return str(case)


def source_key(source):
    """A source as the log keeps it: text, never empty."""
    if isinstance(source, bool) or not isinstance(source, (str, int)) or not str(source).strip():
        raise ValueError(f"a source is text or a whole number, not {source!r}")
    return str(source)


def lesson_ids(lessons):
    """Sorted unique lesson ids; each a whole number."""
    ids = set()
    for x in lessons or ():
        if isinstance(x, bool) or not isinstance(x, int):
            raise ValueError(f"a lesson id is a whole number, not {x!r}")
        ids.add(x)
    return sorted(ids)


def is_history(row):
    """True for a row imported from a business's past data: its detail has "history": true. The
    night study reads it, so it can suggest a lesson; a trial never counts it (engine/trial.py)."""
    detail = row.get("detail")
    return isinstance(detail, dict) and detail.get("history") is True


def _row(r):
    d = dict(r)
    d["lessons"] = json.loads(d["lessons"]) if d["lessons"] else []
    d["detail"] = json.loads(d["detail"]) if d["detail"] else None
    return d
