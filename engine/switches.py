"""The switches a person flips for one agent, kept in the database: the trial level and
Accept high risk, plus the level a person picks for one waiting lesson.

1. The level switch. Which of the plug's two trial levels (fast or careful, plug.py) a new
   trial takes. careful until a person flips it. A trial takes the level at the moment it
   starts and keeps its share and days after that (Lessons fixes them at the start), so a
   flip moves no trial already running.
2. A lesson's own level. A person can pick a level for one lesson while it waits, for a
   yes or for its turn. It wins over the switch when that lesson's trial starts. Numbers a
   person gives with the yes itself (Lessons.approve share or days) win over both.
3. Accept high risk. Off until a person turns it on. While it is on, a high risk lesson
   the study writes goes on trial with no yes, at the level that applies, like a low risk
   one; as its trial starts, Lessons writes the person who turned it on, marked "(Accept
   high risk)", as its yes, and its trial carries the switch row it started under. A lesson
   that waits its turn has no yes until then: the switch is read again at its turn, and when
   it is off or ran out by then, the lesson waits for a person's yes. The person turning it on
   may give a number of days, 1 to 90; after that it reads as off by itself, since every
   read compares the end time with now, so no job has to turn it off. A line close to a
   pulled one, or one that goes against a live one, still waits for a yes, and so does a
   lesson that is high because it copies a run of words from a case (the copy check).

Every flip is one row in trial_switches: who, when, the value and, for Accept high risk,
the end time. The latest row of a kind wins; an Accept high risk row counts as on only from
its own time, so a read at an earlier time finds it off. Rows are never changed, deleted
or replaced, and the database refuses a lesson's own level once the lesson no longer waits.
"""
import time

from engine.plug import CAREFUL, LEVEL_NAMES

DAY = 86400
MOST_DAYS = 90  # the longest Accept high risk can be turned on for, in days
LEVEL, ACCEPT, LESSON = "level", "accept_high", "lesson_level"
ON, OFF = "on", "off"
MARK = "Accept high risk"  # added to the yes of a lesson that went on trial under it

SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_switches (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('level', 'accept_high', 'lesson_level')),
  lesson_id INTEGER REFERENCES lessons (id),
  value TEXT NOT NULL,
  until REAL,
  by TEXT NOT NULL CHECK (length(trim(by)) > 0),
  at REAL NOT NULL,
  CHECK ((kind = 'lesson_level') = (lesson_id IS NOT NULL)),
  CHECK (CASE kind WHEN 'accept_high' THEN value IN ('on', 'off') ELSE value IN ('fast', 'careful') END),
  CHECK (until IS NULL OR (kind = 'accept_high' AND value = 'on' AND until > at))
);
CREATE INDEX IF NOT EXISTS trial_switches_latest ON trial_switches (agent, kind, lesson_id, id);
CREATE TRIGGER IF NOT EXISTS trial_switches_never_changed BEFORE UPDATE ON trial_switches
BEGIN SELECT RAISE(ABORT, 'a switch row is never changed; add a new one'); END;
CREATE TRIGGER IF NOT EXISTS trial_switches_never_deleted BEFORE DELETE ON trial_switches
BEGIN SELECT RAISE(ABORT, 'a switch row is never deleted'); END;
CREATE TRIGGER IF NOT EXISTS trial_switches_never_replaced BEFORE INSERT ON trial_switches
WHEN EXISTS (SELECT 1 FROM trial_switches WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'a switch row is never replaced'); END;
CREATE TRIGGER IF NOT EXISTS trial_switches_lesson_waits BEFORE INSERT ON trial_switches
WHEN NEW.kind = 'lesson_level' AND NOT EXISTS (SELECT 1 FROM lessons WHERE id = NEW.lesson_id
                                               AND agent = NEW.agent AND state = 'waiting')
BEGIN SELECT RAISE(ABORT, 'a level is set on a lesson only while it waits'); END;
"""


class Switches:
    """One agent's switches. Every read and every flip is limited to its own agent."""

    def __init__(self, db, plug):
        self.db = db
        self.plug = plug
        self.db.script(SCHEMA)

    @property
    def agent(self):
        return self.plug.agent

    def level(self):
        """The level a new trial takes now: {level, share, days, by, at}; by and at are None
        while no person has flipped it (careful)."""
        with self.db.tx() as c:
            row = latest(c, self.agent, LEVEL)
        name = CAREFUL if row is None else row["value"]
        lv = self.plug.level(name)
        return {"level": name, "share": lv.share, "days": lv.days,
                "by": None if row is None else row["by"], "at": None if row is None else row["at"]}

    def set_level(self, level, by, *, now=None):
        """Flip the level switch. by: the person. Returns the new reading."""
        level, by = self._level(level), _by(by)
        with self.db.tx() as c:
            _add(c, self.agent, LEVEL, level, by, _now(now))
        return self.level()

    def accept_high(self, now=None):
        """Accept high risk as it reads at `now` (the clock when left out): {on, by, at, until,
        ran_out, id}. on is False when it was turned off, never turned on (by None), or turned on
        with days that have run out (ran_out True)."""
        now = _now(now)
        with self.db.tx() as c:
            row = latest(c, self.agent, ACCEPT)
        if row is None:
            return {"on": False, "by": None, "at": None, "until": None, "ran_out": False, "id": None}
        ran_out = row["value"] == ON and row["until"] is not None and now >= row["until"]
        return {"on": accept_on(row, now), "by": row["by"], "at": row["at"], "until": row["until"],
                "ran_out": ran_out, "id": row["id"]}

    def set_accept_high(self, on, by, *, days=None, now=None):
        """Turn Accept high risk on or off. by: the person. days: only when turning it on, a whole
        number from 1 to 90 after which it reads as off by itself; None keeps it on until a person
        turns it off. Returns the new reading at now."""
        if not isinstance(on, bool):
            raise ValueError("on: True or False")
        by, now = _by(by), _now(now)
        until = None
        if days is not None:
            if not on:
                raise ValueError("days are given only when turning Accept high risk on")
            until = now + _days(days) * DAY
        with self.db.tx() as c:
            _add(c, self.agent, ACCEPT, ON if on else OFF, by, now, until=until)
        return self.accept_high(now)

    def lesson_level(self, lesson_id):
        """{level, by, at}: the level a person picked for this lesson, the latest one; None when
        none was picked."""
        with self.db.tx() as c:
            row = latest(c, self.agent, LESSON, lesson_id)
        return None if row is None else {"level": row["value"], "by": row["by"], "at": row["at"]}

    def set_lesson_level(self, lesson_id, level, by, *, now=None):
        """A person picks the level for one lesson that waits, for a yes or for its turn; it wins
        over the switch when the lesson's trial starts. True when written; False when the lesson
        is not this agent's or no longer waits (its level is then fixed or it is pulled), or its
        share and days came with its yes (a trial queued at the given level keeps them)."""
        level, by = self._level(level), _by(by)
        with self.db.tx() as c:
            row = c.execute("SELECT state FROM lessons WHERE id = ? AND agent = ?", (lesson_id, self.agent)).fetchone()
            if row is None or row["state"] != "waiting":
                return False
            if c.execute("SELECT 1 FROM trials WHERE lesson_id = ? AND started_at IS NULL AND level = 'given'",
                         (lesson_id,)).fetchone():  # 'given' is engine/lessons.py GIVEN
                return False
            _add(c, self.agent, LESSON, level, by, _now(now), lesson_id=lesson_id)
        return True

    def history(self, kind=None):
        """Every flip of this agent, oldest first, as {id, kind, lesson_id, value, until, by, at};
        one kind only when named."""
        if kind is not None and kind not in (LEVEL, ACCEPT, LESSON):
            raise ValueError(f"a switch kind is {LEVEL}, {ACCEPT} or {LESSON}")
        sql, args = "SELECT * FROM trial_switches WHERE agent = ?", [self.agent]
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        with self.db.tx() as c:
            return [{k: r[k] for k in ("id", "kind", "lesson_id", "value", "until", "by", "at")}
                    for r in c.execute(sql + " ORDER BY id", args)]

    def reading(self, now=None):
        """Both switches at `now`, as the night report names them: {level, share, days, accept_high}."""
        lv = self.level()
        acc = self.accept_high(now)
        return {"level": lv["level"], "share": lv["share"], "days": lv["days"],
                "accept_high": {k: acc[k] for k in ("on", "by", "until", "ran_out")}}

    def _level(self, level):
        if not isinstance(level, str) or level not in LEVEL_NAMES:
            raise ValueError(f"a trial level is {' or '.join(LEVEL_NAMES)}, not {level!r}")
        return level


def latest(c, agent, kind, lesson_id=None):
    """The latest row of a kind for the agent (for one lesson, for its own level), or None."""
    if kind == LESSON:
        return c.execute("SELECT * FROM trial_switches WHERE agent = ? AND kind = ? AND lesson_id = ? "
                         "ORDER BY id DESC LIMIT 1", (agent, kind, lesson_id)).fetchone()
    return c.execute("SELECT * FROM trial_switches WHERE agent = ? AND kind = ? ORDER BY id DESC LIMIT 1",
                     (agent, kind)).fetchone()


def accept_on(row, now):
    """Does this Accept high risk row read as on at `now`? On, written at or before `now`, and
    its end time not reached. A row written after `now` does not count yet."""
    return (row is not None and row["value"] == ON and row["at"] <= now
            and (row["until"] is None or now < row["until"]))


def _add(c, agent, kind, value, by, now, *, until=None, lesson_id=None):
    c.execute("INSERT INTO trial_switches (agent, kind, lesson_id, value, until, by, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (agent, kind, lesson_id, value, until, by, now))


def _by(by):
    if not isinstance(by, str) or not by.strip() or "\n" in by or "\r" in by:
        raise ValueError("by: the person, one line of text")
    return by.strip()


def _days(days):
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MOST_DAYS:
        raise ValueError(f"days: a whole number from 1 to {MOST_DAYS}")
    return days


def _now(now):
    return time.time() if now is None else float(now)
