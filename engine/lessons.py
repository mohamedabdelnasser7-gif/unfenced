"""Lessons: one line each, for one agent, never rewritten.

A lesson belongs to the agent whose plug added it and is never given to another agent.
Its risk comes from that agent's risk list (risk.py) when it is added, and never changes.
Its state:
  waiting  not given. A high risk lesson waits here for a person's yes, and a lesson waits
           here for its turn.
  trying   given in a share of cases until its end date. A low risk lesson starts here,
           and so does a high risk one after its yes, or with no yes while Accept high risk
           is on (switches.py), and a person's own line. Accept high risk is read when the
           trial actually starts: a high risk lesson that waits its turn under it has no yes,
           and when its turn comes with the switch off or run out, its turn is dropped and it
           waits for a person's yes. A lesson high because it copies a run of words from a
           case always waits for a person's yes, switch or not.
  kept     given in every case, or in all but a small holdback when a trial kept it.
  pulled   never given again.
One trial per stage at a time: a lesson that would start a trial while another lesson's
trial is live on one of its stages ("all" meets every stage), or while an older lesson
waits its turn there, waits its turn instead. start_turns() starts the waiting ones, the
oldest first, once their stages are free; the trial's nightly check calls it. pause()
ends a trial early: the lesson stays on trial, is given in no new case, and waits for a
person. extend() gives an ended trial a later end date, on a person's word (trial.py). A
person's own line (add) needs no yes, a person wrote it: it starts a trial like any other
lesson, or waits its turn. Each lesson saves whose idea it is (origin): a person's or the
agent's. And its kind: a pattern, found in past cases and counted by the study, or an idea, a
lesson with no past cases behind it, a path to try. A person's own line is an idea; the study
writes ideas too (study.py). Both kinds go the same way: the risk check, a yes when high, a
trial at the level that applies.
A trial's share and days come from a trial level (plug.py: fast or careful), taken when
the trial starts: numbers a person gave with the yes, else the lesson's own level, else the
level switch (switches.py). A lesson waiting its turn takes them when its turn comes. Once
started they are fixed like the rest of the trial.
The same case always gets the same answer for a lesson on trial. The database refuses
a high risk lesson given without a yes, a trial with no end date, any change to a
lesson's text, tags, agent, risk, source or origin, a yes taken back, any way back from
pulled, a lesson replaced or deleted, and any change to a trial once it starts. To change
what a lesson says, pull it and add a new one.
bring_back() is a person's way back for a pulled lesson: the pulled one stays pulled and
unchanged, and a new lesson with the same text and stages, linked to it (lesson_returns) and
signed with the person's yes, goes on trial or waits its turn. Only one lesson of a line's
bring back family (every lesson linked to it by Bring back, either way) is not pulled at a time.

Field tags come from the agent's plug. Another agent in the same field can borrow a
kept lesson (one that proved itself): it becomes a new lesson of the borrowing agent, linked by source_lesson_id,
risk checked by the borrower's own list, and it starts like any new lesson. The night study
learns across fields with adapt(): a lesson in this agent's own words, from another agent's
cases or kept lesson in any field, its source line naming where it came from.

hand() picks the lessons for one action in one case and adds their ids to the set the
action is saved with; slot() writes them under the plug's slot line for the agent's
prompt. The agent's own checks run after, so a lesson can never loosen a check.
"""
import hashlib
import json
import math
import re
import time
from contextlib import contextmanager

from engine import exam as exam_mod
from engine import risk as risk_mod
from engine import switches as switches_mod
from engine.plug import ALL

MAX_PICK = 8
MAX_LEN = 300
DAY = 86400
WAITING, TRYING, KEPT, PULLED = "waiting", "trying", "kept", "pulled"
PERSON, AGENT = "person", "agent"  # whose idea a lesson is: a person's own line, or the agent's study
# Who takes the exam before a trial (engine/exam.py): the agent's new lessons, and a person's own
# line too (Mohamed, 29 Oct: "A"). A person's line that fails waits with its line shown, and Yes on
# its card still starts it. Edit, Bring back and Yes run no exam. False: only the agent's lessons.
PERSON_TAKES_EXAM = True


def takes_exam(origin):
    """True when a new lesson of this origin takes the exam before its trial: the one switchable place."""
    return origin == AGENT or (origin == PERSON and PERSON_TAKES_EXAM)

PATTERN, IDEA = "pattern", "idea"  # its kind: found in past cases, or a lesson with no past cases behind it
KINDS = (PATTERN, IDEA)
FROM_STUDY = ("night study of ", "adapted ", "borrowed from ")  # how the study's own source lines start
GIVEN = "given"  # a trial's level when a person gave its share or days with the yes

TABLE = """
CREATE TABLE IF NOT EXISTS lessons (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  text TEXT NOT NULL,
  stages TEXT NOT NULL,
  fields TEXT NOT NULL,
  risk TEXT NOT NULL CHECK (risk IN ('low', 'high')),
  risk_why TEXT,
  state TEXT NOT NULL CHECK (state IN ('waiting', 'trying', 'kept', 'pulled')),
  share REAL NOT NULL DEFAULT 1 CHECK (share > 0 AND share <= 1),
  ends_at REAL,
  score REAL NOT NULL DEFAULT 0,
  source TEXT,
  source_lesson_id INTEGER REFERENCES lessons (id),
  origin TEXT CHECK (origin IN ('person', 'agent')),
  kind TEXT CHECK (kind IN ('pattern', 'idea')),
  yes_by TEXT,
  yes_at REAL,
  added_at REAL NOT NULL,
  pulled_at REAL,
  pulled_why TEXT,
  CHECK (risk = 'low' OR state IN ('waiting', 'pulled') OR yes_at IS NOT NULL),
  CHECK (state != 'trying' OR ends_at IS NOT NULL),
  CHECK ((yes_by IS NULL) = (yes_at IS NULL))
)"""

SCHEMA = TABLE + """;
CREATE INDEX IF NOT EXISTS lessons_agent ON lessons (agent, state);
CREATE TRIGGER IF NOT EXISTS lessons_never_rewritten
BEFORE UPDATE OF agent, text, stages, fields, risk, risk_why, source, source_lesson_id, added_at ON lessons
BEGIN SELECT RAISE(ABORT, 'a lesson is never rewritten; pull it and add a new one'); END;
CREATE TRIGGER IF NOT EXISTS lessons_stay_pulled
BEFORE UPDATE OF state ON lessons WHEN OLD.state = 'pulled'
BEGIN SELECT RAISE(ABORT, 'a pulled lesson stays pulled'); END;
CREATE TRIGGER IF NOT EXISTS lessons_yes_stays
BEFORE UPDATE OF yes_by, yes_at ON lessons WHEN OLD.yes_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a yes is never taken back; pull the lesson instead'); END;
CREATE TRIGGER IF NOT EXISTS lessons_borrowed_from_another_agent
BEFORE INSERT ON lessons WHEN NEW.source_lesson_id IS NOT NULL
  AND (SELECT agent FROM lessons WHERE id = NEW.source_lesson_id) = NEW.agent
BEGIN SELECT RAISE(ABORT, 'a lesson is borrowed from another agent'); END;
CREATE TRIGGER IF NOT EXISTS lessons_never_replaced
BEFORE INSERT ON lessons WHEN EXISTS (SELECT 1 FROM lessons WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'a lesson is never replaced; pull it and add a new one'); END;
CREATE TRIGGER IF NOT EXISTS lessons_never_deleted
BEFORE DELETE ON lessons
BEGIN SELECT RAISE(ABORT, 'a lesson is never deleted; pull it instead'); END;
CREATE TABLE IF NOT EXISTS trials (
  lesson_id INTEGER PRIMARY KEY REFERENCES lessons (id),
  agent TEXT NOT NULL,
  share REAL NOT NULL CHECK (share > 0 AND share <= 1),
  days REAL NOT NULL CHECK (days > 0),
  queued_at REAL,
  started_at REAL,
  worst_cost REAL,
  good TEXT,
  bad TEXT,
  harm TEXT,
  serious TEXT,
  windows TEXT,
  level TEXT,
  accept_high_id INTEGER REFERENCES trial_switches (id),
  CHECK (queued_at IS NOT NULL OR started_at IS NOT NULL),
  CHECK (started_at IS NULL OR (worst_cost IS NOT NULL AND good IS NOT NULL AND bad IS NOT NULL
                                AND harm IS NOT NULL AND serious IS NOT NULL AND windows IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS trials_fixed_once_started
BEFORE UPDATE ON trials WHEN OLD.started_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a trial is fixed once it starts'); END;
CREATE TRIGGER IF NOT EXISTS trials_kept_once_started
BEFORE DELETE ON trials WHEN OLD.started_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a trial is fixed once it starts'); END;
CREATE TRIGGER IF NOT EXISTS trials_never_replaced_once_started
BEFORE INSERT ON trials WHEN EXISTS (SELECT 1 FROM trials WHERE lesson_id = NEW.lesson_id AND started_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'a trial is fixed once it starts'); END;
CREATE TABLE IF NOT EXISTS lesson_clashes (
  lesson_id INTEGER NOT NULL REFERENCES lessons (id),
  live_id INTEGER NOT NULL REFERENCES lessons (id),
  agent TEXT NOT NULL,
  at REAL NOT NULL,
  PRIMARY KEY (lesson_id, live_id)
);
CREATE TABLE IF NOT EXISTS lesson_returns (
  lesson_id INTEGER PRIMARY KEY REFERENCES lessons (id),
  from_id INTEGER NOT NULL REFERENCES lessons (id),
  agent TEXT NOT NULL,
  by TEXT NOT NULL,
  at REAL NOT NULL
);
CREATE TRIGGER IF NOT EXISTS lesson_returns_from_a_pulled_lesson
BEFORE INSERT ON lesson_returns
WHEN (SELECT state FROM lessons WHERE id = NEW.from_id AND agent = NEW.agent) IS NOT 'pulled'
  OR NOT EXISTS (SELECT 1 FROM lessons WHERE id = NEW.lesson_id AND agent = NEW.agent AND state = 'waiting'
                 AND yes_by IS NOT NULL AND text = (SELECT text FROM lessons WHERE id = NEW.from_id))
  OR EXISTS (SELECT 1 FROM trials WHERE lesson_id = NEW.lesson_id)
  OR EXISTS (SELECT 1 FROM lesson_returns r JOIN lessons l ON l.id = r.lesson_id
             WHERE r.from_id = NEW.from_id AND l.state != 'pulled')
BEGIN SELECT RAISE(ABORT, 'a lesson comes back as a new lesson of its agent, from a pulled one not back already'); END;
CREATE TRIGGER IF NOT EXISTS lesson_returns_never_changed BEFORE UPDATE ON lesson_returns
BEGIN SELECT RAISE(ABORT, 'a bring back link is never changed'); END;
CREATE TRIGGER IF NOT EXISTS lesson_returns_never_deleted BEFORE DELETE ON lesson_returns
BEGIN SELECT RAISE(ABORT, 'a bring back link is never deleted'); END;
CREATE TRIGGER IF NOT EXISTS lesson_returns_never_replaced BEFORE INSERT ON lesson_returns
WHEN EXISTS (SELECT 1 FROM lesson_returns WHERE lesson_id = NEW.lesson_id)
BEGIN SELECT RAISE(ABORT, 'a bring back link is never replaced'); END;
"""
# trials: one row for each lesson that went on trial or waits its turn, fixed before the
# trial starts: its share and days, when it began waiting (queued_at, none when it started
# at once) and when its trial started (started_at, none while it waits its turn). When it
# starts, what it is judged by is copied from the plug: the worst likely cost it may have,
# the good and bad results that settle a case with the days each takes to show (windows,
# a JSON object {result: [least, most]}), and the harm and serious results. The database
# refuses any change to the row once the trial has started. A trials table from before the
# windows were copied gets the column empty, and its started trials read the plug's.
# level: the trial level its share and days came from (fast, careful, or given when a person
# gave them with the yes), set when it starts; while it waits its turn only "given" is kept,
# since the others are read again at its start. Empty on a trial from before the levels.
# accept_high_id: the trial_switches row of Accept high risk it went on trial under, for a
# high risk lesson that had no person's yes; while it waits its turn, the row it began waiting
# under, and the switch is read again at its start; empty otherwise.
# lesson_clashes: a new lesson (lesson_id) that goes against a live one (live_id), named on
# its "replace it?" card.
# lesson_returns: a lesson a person brought back (lesson_id, new, with the same text) from a
# pulled one (from_id), who brought it back and when. The database refuses a link from a
# lesson that is not pulled, to a lesson that is not new (waiting, signed with a yes, with no
# trial row yet), of another agent or with another text, a second link while a lesson brought back from the same one is not pulled, and any
# change, deletion or replacement of a link.
# lessons.origin: whose idea the lesson is, "person" (a person's own line, add) or "agent" (the
# agent's study: propose, adapt, borrow). It is set when the lesson is written and never changes.
# A lesson written before the column existed is read once, when Lessons opens the database
# (_fill_origin): "person" when it has a yes that is not marked "(Accept high risk)", came from
# no other agent's lesson and its source does not start like the study's own source lines
# (FROM_STUDY), else "agent".
ORIGIN_COLUMN = "ALTER TABLE lessons ADD COLUMN origin TEXT CHECK (origin IN ('person', 'agent'))"
ORIGIN_STAYS = """
CREATE TRIGGER IF NOT EXISTS lessons_origin_stays
BEFORE UPDATE OF origin ON lessons WHEN OLD.origin IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a lesson is never rewritten; pull it and add a new one'); END"""
# lessons.kind: "pattern" (found in past cases: propose, adapt, borrow) or "idea" (a lesson with no
# past cases behind it: a person's own line, or an idea the study writes). Set when the lesson is
# written and never changed. A lesson written before the column existed is read once, when
# Lessons opens the database (_fill_kind): "idea" when its origin is "person", else "pattern".
KIND_COLUMN = "ALTER TABLE lessons ADD COLUMN kind TEXT CHECK (kind IN ('pattern', 'idea'))"
KIND_STAYS = """
CREATE TRIGGER IF NOT EXISTS lessons_kind_stays
BEFORE UPDATE OF kind ON lessons WHEN OLD.kind IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a lesson is never rewritten; pull it and add a new one'); END"""

_WORD = re.compile(r"[\w؀-ۿ]+")


class Lessons:
    """One agent's lessons. Every read and every change is limited to its own agent."""

    def __init__(self, db, plug, judge=risk_mod.no_judge, exam=None):
        """exam: the examiner, callable(text, stages) -> engine.exam.Result, run on a new lesson
        before its trial starts (see _new); None, the default, runs no exam."""
        self.db = db
        self.plug = plug
        self.judge = judge
        self.examiner = exam
        self.db.script(SCHEMA)
        self.db.script(exam_mod.TABLE)
        self.switches = switches_mod.Switches(db, plug)
        with self.db.tx() as c:  # a trials table from before these columns gets them empty
            have = {r["name"] for r in c.execute("PRAGMA table_info(trials)")}
            for col, kind in (("windows", "TEXT"), ("level", "TEXT"),
                              ("accept_high_id", "INTEGER REFERENCES trial_switches (id)")):
                if col not in have:
                    c.execute(f"ALTER TABLE trials ADD COLUMN {col} {kind}")
            cols = {r["name"] for r in c.execute("PRAGMA table_info(lessons)")}
            if "origin" not in cols:
                c.execute(ORIGIN_COLUMN)  # lessons from before their origin was saved
            _fill_origin(c)
            c.execute(ORIGIN_STAYS)
            if "kind" not in cols:
                c.execute(KIND_COLUMN)  # lessons from before their kind was saved
            _fill_kind(c)
            c.execute(KIND_STAYS)

    @property
    def agent(self):
        return self.plug.agent

    def propose(self, text, stages, *, source="", sources, trial=True, kind=PATTERN, now=None):
        """A new lesson from the agent's study, with no yes yet. kind: PATTERN for one found in
        past cases, IDEA for one with no past cases behind it; both go the same way. Low risk: goes on trial at
        the level that applies, or waits its turn. High risk: waits for a yes, unless Accept high
        risk is on: then it goes on trial like a low risk one, and the person who turned the
        switch on, marked "(Accept high risk)", is written as its yes as the trial starts. When
        it waits its turn instead, it waits with no yes, and the switch is read again at its
        turn (start_turns). A lesson high because it copies words from a case (copied())
        always waits for a person's yes, switch or not. sources: the texts of the cases it
        came from; a lesson that copies a run of words from one is high. It has no default, so a
        caller cannot skip the copy check by leaving it out; [] when none. trial False: it waits
        for a yes whatever its risk (a line close to a pulled one, or one against a live one).
        Returns its id."""
        return self._new(text, stages, source=source, sources=sources, trial=trial, kind=_kind(kind), now=now)

    def adapt(self, text, stages, *, source, sources, source_lesson_id=None, trial=True, now=None):
        """A new lesson in this agent's own words, learned from another agent in any field. source:
        one line naming that agent and its cases or lesson. sources: as in propose, no default.
        source_lesson_id: when it came from another agent's lesson, that lesson, which must be
        kept. It passes this agent's own risk check and starts like any proposed lesson.
        Returns its id."""
        source = _line(source, "source")
        if source_lesson_id is not None:
            self._from_other(source_lesson_id)
        return self._new(text, stages, source=source, sources=sources, source_lesson_id=source_lesson_id,
                         trial=trial, now=now)

    def add(self, text, stages, source="", score=0.0, *, yes_by, exam=None, skip_exam=False, now=None):
        """A person's own line. It needs no yes, a person wrote it, so it starts a trial like any
        other lesson, at whatever risk, at the level that applies when its trial starts (see the
        top); or it waits its turn when its stage has a trial. With a person's yes it never needs
        Accept high risk. yes_by: the person who wrote it, saved as its yes. Its risk is still
        checked and saved, its origin is "person" and its kind is "idea": no past cases stand behind it.
        It takes the exam first when takes_exam(PERSON) says so: a fail waits for Yes on its card.
        exam: a Result already run on this text (a page that runs it outside its own transaction);
        skip_exam: True for an edited line (Edit runs no exam). Returns its id."""
        return self._new(text, stages, source=source, score=score, yes_by=_line(yes_by, "yes_by"), origin=PERSON,
                         kind=IDEA, exam_given=exam, skip_exam=skip_exam, now=now)

    def borrow(self, source_id, stages, *, source="", now=None):
        """A new lesson for this agent from another agent's lesson in the same field. It keeps the
        text and links its source; risk, stage tags and state are this agent's own."""
        src = self._from_other(source_id)
        if not set(src["fields"]) & set(self.plug.fields):
            raise ValueError(f"{src['agent']} works in no field of {self.agent}")
        return self._new(src["text"], stages, source=source or f"borrowed from {src['agent']} lesson {src['id']}",
                         source_lesson_id=src["id"], now=now)

    def _from_other(self, source_id):
        """Another agent's kept lesson; ValueError when it is missing, this agent's own or not kept."""
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM lessons WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise ValueError(f"no lesson {source_id!r}")
        src = _row(row)
        if src["agent"] == self.agent:
            raise ValueError("a lesson is borrowed from another agent")
        if src["state"] != KEPT:
            raise ValueError("only a kept lesson is borrowed")
        return src

    def exam_of(self, lesson_id):
        """The exam the lesson took before its trial, as a dict, or None when it took none."""
        with self.db.tx() as c:
            return exam_mod.of(c, self.agent, lesson_id)

    def approve(self, lesson_id, yes_by, *, share=None, days=None, now=None):
        """A person's yes on a waiting lesson: it is tried in a share of cases until its end date,
        or waits its turn with its yes when its stage has a trial. Its share and days come from
        the level that applies when its trial starts (see the top), unless the person gives them
        here: share more than 0 and at most 1, days more than 0; one given alone takes the other
        from the level that applies now. True when the lesson moved."""
        now = _now(now)
        if share is not None or days is not None:
            share = None if share is None else float(share)
            days = None if days is None else float(days)
            if share is not None and not 0 < share <= 1 or days is not None and not (days > 0 and math.isfinite(days)):
                raise ValueError("share is more than 0 and at most 1; days is more than 0")
        yes_by = _line(yes_by, "yes_by")
        with self.db.tx() as c:
            row = c.execute(  # no yes yet, or a person's line its exam held (PERSON_TAKES_EXAM)
                "SELECT * FROM lessons WHERE id = ? AND agent = ? AND state = 'waiting' AND (yes_at IS NULL OR ("
                "id IN (SELECT lesson_id FROM lesson_exams WHERE passed = 0) AND id NOT IN (SELECT lesson_id FROM trials)))",
                (lesson_id, self.agent)).fetchone()
            if row is None:
                return False
            given = None
            if share is not None or days is not None:
                lv_share, lv_days, _ = self._level_now(c, lesson_id)
                given = (lv_share if share is None else share, lv_days if days is None else days)
            c.execute("UPDATE lessons SET yes_by = ?, yes_at = ? WHERE id = ? AND yes_at IS NULL",
                      (yes_by, now, lesson_id))  # a person's held line keeps its writer as its yes
            self._try(c, lesson_id, _row(row)["stages"], now, given=given)
            return True

    def keep(self, lesson_id, holdback=0.0, *, c=None):
        """A lesson on trial that proved itself: given with no end date, in every case but a
        holdback, a share of cases that keep the old way (0 by default, every case). c: the
        caller's transaction, when the change and its record go in together."""
        holdback = float(holdback)
        if not 0 <= holdback < 1:
            raise ValueError("holdback is at least 0 and under 1")
        return self._update("state = 'kept', share = ?, ends_at = NULL", (1 - holdback,), lesson_id,
                            "state = 'trying'", c)

    def pull(self, lesson_id, why="", *, now=None, on_trial=False, c=None):
        """Never given again. True when the lesson was not pulled already; with on_trial, only
        a lesson still on trial. c: as in keep."""
        with self._in(c) as c:
            cur = c.execute("UPDATE lessons SET state = 'pulled', pulled_at = ?, pulled_why = ? WHERE id = ? AND "
                            "agent = ? AND " + ("state = 'trying'" if on_trial else "state != 'pulled'"),
                            (_now(now), why, lesson_id, self.agent))
            if cur.rowcount == 1:  # a turn it was still waiting for is gone
                c.execute("DELETE FROM trials WHERE lesson_id = ? AND started_at IS NULL", (lesson_id,))
            return cur.rowcount == 1

    def pause(self, lesson_id, now=None, *, c=None):
        """A lesson on trial is given in no new case from now: its trial ends early. It stays on
        trial, waiting for a person to keep it or pull it. True when its trial was live. c: as
        in keep."""
        now = _now(now)
        with self._in(c) as c:
            cur = c.execute("UPDATE lessons SET ends_at = ? WHERE id = ? AND agent = ? AND state = 'trying' "
                            "AND ends_at > ?", (now, lesson_id, self.agent, now))
            return cur.rowcount == 1

    def extend(self, lesson_id, ends_at, *, was, now=None, c=None):
        """A lesson on trial whose end date `was` has passed is given again in its share of cases
        until a later end date. Its trial keeps its start, share and what it is judged by. True
        when the lesson was still on trial with that end date. c: as in keep."""
        now, ends_at = _now(now), float(ends_at)
        if not (math.isfinite(ends_at) and ends_at > now):
            raise ValueError("the new end date is later than now")
        with self._in(c) as c:
            cur = c.execute("UPDATE lessons SET ends_at = ? WHERE id = ? AND agent = ? AND state = 'trying' "
                            "AND ends_at = ? AND ends_at <= ?", (ends_at, lesson_id, self.agent, was, now))
            return cur.rowcount == 1

    @contextmanager
    def _in(self, c):
        """The caller's transaction when given, else a new one."""
        if c is not None:
            yield c
            return
        with self.db.tx() as c:
            yield c

    def clash(self, lesson_id, live_id, now=None):
        """Note that a new lesson goes against a live one; its card asks "replace it?"."""
        if self.get(lesson_id) is None or self.get(live_id) is None or lesson_id == live_id:
            raise ValueError("a clash is between two lessons of this agent")
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO lesson_clashes (lesson_id, live_id, agent, at) VALUES (?, ?, ?, ?)",
                      (lesson_id, live_id, self.agent, _now(now)))

    def clashes(self, lesson_id):
        """{replaces: the live lessons this one goes against, replaced_by: the new lessons that go
        against this one}, as ids named on "replace it?" cards."""
        with self.db.tx() as c:
            out = [r["live_id"] for r in c.execute("SELECT live_id FROM lesson_clashes WHERE lesson_id = ? AND agent = ? "
                                                    "ORDER BY live_id", (lesson_id, self.agent))]
            back = [r["lesson_id"] for r in c.execute("SELECT lesson_id FROM lesson_clashes WHERE live_id = ? AND "
                                                       "agent = ? ORDER BY lesson_id", (lesson_id, self.agent))]
        return {"replaces": out, "replaced_by": back}

    def replace(self, lesson_id, yes_by, *, now=None):
        """A person's yes on a "replace it?" card: each live lesson this one goes against is
        pulled, naming it, and this one goes on trial, or waits its turn. True when it moved."""
        les = self.get(lesson_id)
        if les is None or les["state"] != WAITING or les["yes_at"] is not None:
            return False
        for old in self.clashes(lesson_id)["replaces"]:
            self.pull(old, f"replaced by lesson {lesson_id}", now=now)
        return self.approve(lesson_id, yes_by, now=now)

    def bring_back(self, lesson_id, by, *, now=None, c=None):
        """A person brings a pulled lesson back. The pulled one stays pulled and unchanged; a new
        lesson with its text and stages is added, linked to it, signed with the person's yes (a
        person asked for it, so it waits for no other yes, even though its line is a pulled
        one), and goes on trial at the level that applies when its trial starts (see the top), or
        waits its turn when its stages have a trial; with a person's yes it never needs Accept
        high risk. Its risk is the pulled one's, or high when the code check on
        today's risk list finds a mark. ValueError, with nothing changed, for a lesson that is
        unknown, another agent's or not pulled, an empty by, or a line whose bring back family
        already has a lesson that is not pulled (named). c: the caller's transaction, when the
        bring back goes in with other changes. Returns the new lesson's id."""
        by = _line(by, "by")
        now = _now(now)
        with self._in(c) as c:
            if not c.in_transaction:  # read and write under one write lock: two clicks never bring back twice
                c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM lessons WHERE id = ? AND agent = ?", (lesson_id, self.agent)).fetchone()
            if row is None:
                raise ValueError(f"no lesson {lesson_id!r} of {self.agent}")
            old = _row(row)
            if old["state"] != PULLED:
                raise ValueError(f"lesson {old['id']} is not pulled")
            states = {r["id"]: r["state"] for r in c.execute("SELECT id, state FROM lessons WHERE agent = ?",
                                                             (self.agent,))}
            copy = back_copy(returns_in(c, self.agent), states, old["id"])
            if copy is not None:
                raise ValueError(f"lesson {old['id']} is back already as lesson {copy} ({_STATE_WORDS[states[copy]]})")
            stages = self.plug.stage_tags(old["stages"])
            found = [] if old["risk"] == risk_mod.HIGH else risk_mod.code_check(old["text"], self.plug.risk)
            level = risk_mod.HIGH if found else old["risk"]
            cur = c.execute(
                "INSERT INTO lessons (agent, text, stages, fields, risk, risk_why, state, share, ends_at, score, source, "
                "yes_by, yes_at, origin, kind, added_at) VALUES (?, ?, ?, ?, ?, ?, 'waiting', 1, NULL, 0, ?, ?, ?, ?, ?, ?)",
                (self.agent, old["text"], tag_text(stages), tag_text(self.plug.fields), level,
                 "; ".join(found) if found else old["risk_why"], f"brought back by {by} from lesson {old['id']}", by,
                 now, old.get("origin"), old.get("kind"), now))  # the idea stays whose it was, and its kind
            new_id = cur.lastrowid
            c.execute("INSERT INTO lesson_returns (lesson_id, from_id, agent, by, at) VALUES (?, ?, ?, ?, ?)",
                      (new_id, old["id"], self.agent, by, now))
            self._try(c, new_id, stages, now)
            return new_id

    def back_links(self, lesson_id):
        """{from: the pulled lesson this one was brought back from, or None; as: the lessons it was
        brought back as, oldest first}, for the morning page and the night report."""
        with self.db.tx() as c:
            links = returns_in(c, self.agent)
        return {"from": links.get(lesson_id), "as": sorted(n for n, o in links.items() if o == lesson_id)}

    def trial(self, lesson_id):
        """The lesson's trial as fixed before it started: {share, days, queued_at, started_at,
        worst_cost, good, bad, harm, serious, windows, level, accept_high}, worst_cost to windows
        copied from the plug when it started (None while it waits its turn; windows: {deciding
        result: [least, most] days}), or None when it never went on trial nor waited its turn.
        level: fast, careful or given, the level its share and days came from; while it waits its
        turn, the share, days and level it would start with now. accept_high: {id, by, at, until}
        of the Accept high risk row a high risk lesson went on trial under with no person's yes
        (while it waits its turn, the row it began waiting under; the switch is read again at its
        turn), else None. A trial from before this record has its start read from its yes, else
        from when it was added, and nothing copied; one from before the windows were copied has
        windows None, and one from before the levels has level None."""
        with self.db.tx() as c:
            row = c.execute("SELECT t.share, t.days, t.queued_at, t.started_at, t.worst_cost, t.good, t.bad, t.harm, "
                            "t.serious, t.windows, t.level, t.accept_high_id, s.by AS a_by, s.at AS a_at, "
                            "s.until AS a_until, l.state, l.yes_at, l.added_at FROM lessons l LEFT JOIN trials t "
                            "ON t.lesson_id = l.id LEFT JOIN trial_switches s ON s.id = t.accept_high_id "
                            "WHERE l.id = ? AND l.agent = ?", (lesson_id, self.agent)).fetchone()
            if row is None or row["days"] is None and row["state"] != TRYING:
                return None
            out = {k: row[k] for k in ("share", "days", "queued_at", "started_at", "worst_cost", "good", "level")}
            if row["started_at"] is None and row["days"] is not None and row["level"] != GIVEN:
                out["share"], out["days"], out["level"] = self._level_now(c, lesson_id)
        out.update({k: None if row[k] is None else _tags(row[k]) for k in ("bad", "harm", "serious")})
        out["windows"] = None if row["windows"] is None else json.loads(row["windows"])
        out["accept_high"] = None if row["accept_high_id"] is None else {
            "id": row["accept_high_id"], "by": row["a_by"], "at": row["a_at"], "until": row["a_until"]}
        if row["days"] is None:
            out["started_at"] = row["yes_at"] if row["yes_at"] is not None else row["added_at"]
        return out

    def turns(self):
        """{lesson id: when it began waiting} for this agent's lessons waiting their turn."""
        with self.db.tx() as c:
            rows = c.execute("SELECT t.lesson_id, t.queued_at FROM trials t JOIN lessons l ON l.id = t.lesson_id "
                             "WHERE t.agent = ? AND t.started_at IS NULL AND l.state = 'waiting'",
                             (self.agent,)).fetchall()
        return {r["lesson_id"]: r["queued_at"] for r in rows}

    def waits_for(self, lesson_id, now=None):
        """None when the lesson is not waiting its turn; else the ids of the lessons ahead of it:
        the live trials on its stages, then the older lessons waiting their turn there."""
        now = _now(now)
        with self.db.tx() as c:
            row = c.execute("SELECT l.stages, t.queued_at FROM trials t JOIN lessons l ON l.id = t.lesson_id "
                            "WHERE t.lesson_id = ? AND t.agent = ? AND t.started_at IS NULL AND l.state = 'waiting'",
                            (lesson_id, self.agent)).fetchone()
            if row is None:
                return None
            return self._ahead(c, _tags(row["stages"]), now, lesson_id, before=(row["queued_at"], lesson_id))

    def start_turns(self, now=None):
        """Start the trials of the lessons waiting their turn whose stages are free, the oldest
        first; a lesson waits behind any older one on its stages. A high risk lesson waiting
        under Accept high risk with no person's yes starts only if the switch reads on now, and
        then gets its marked yes; when it is off or ran out, its turn is dropped and it waits for
        a person's yes. Returns the ids started."""
        now = _now(now)
        started = []
        with self.db.tx() as c:
            if not c.in_transaction:  # read and start under one write lock: two nights never start two trials
                c.execute("BEGIN IMMEDIATE")
            busy = [_tags(r["stages"]) for r in c.execute(_LIVE, (self.agent, now, now, -1))]
            turns = c.execute("SELECT t.*, l.stages, l.yes_at, l.risk_why FROM trials t JOIN lessons l "
                              "ON l.id = t.lesson_id WHERE t.agent = ? AND t.started_at IS NULL "
                              "AND l.state = 'waiting' AND t.queued_at <= ? "
                              "ORDER BY t.queued_at, t.lesson_id", (self.agent, now)).fetchall()
            for t in turns:
                stages = _tags(t["stages"])
                if any(meet(stages, b) for b in busy):
                    busy.append(stages)  # still waiting, it is ahead of the ones behind it
                    continue
                accept = None
                if t["accept_high_id"] is not None and t["yes_at"] is None:  # no person's yes: the switch, read now
                    copy = copied_saved(t["risk_why"])  # a copy never starts under the switch
                    accept = None if copy else switches_mod.latest(c, self.agent, switches_mod.ACCEPT)
                    if not switches_mod.accept_on(accept, now):  # its turn goes; it waits for a person's yes
                        c.execute("DELETE FROM trials WHERE lesson_id = ? AND started_at IS NULL", (t["lesson_id"],))
                        continue
                    self._accept_yes(c, t["lesson_id"], accept, now)
                if t["level"] == GIVEN:  # numbers a person gave with the yes
                    share, days, level = t["share"], t["days"], GIVEN
                else:  # the level that applies now, not when it began waiting
                    share, days, level = self._level_now(c, t["lesson_id"])
                c.execute("UPDATE lessons SET state = 'trying', share = ?, ends_at = ? WHERE id = ?",
                          (share, now + days * DAY, t["lesson_id"]))
                c.execute("UPDATE trials SET started_at = ?, share = ?, days = ?, level = ?, accept_high_id = ?, "
                          "worst_cost = ?, good = ?, bad = ?, harm = ?, serious = ?, windows = ? WHERE lesson_id = ?",
                          (now, share, days, level, None if accept is None else accept["id"], *self._judged_by(),
                           t["lesson_id"]))
                started.append(t["lesson_id"])
                busy.append(stages)  # started, it is ahead of the ones behind it
        return started

    def _accept_yes(self, c, lesson_id, row, now):
        """The standing yes of a high risk lesson whose trial starts now under Accept high risk
        (row): the person who turned it on, marked, written only as the trial starts."""
        c.execute("UPDATE lessons SET yes_by = ?, yes_at = ? WHERE id = ?",
                  (f'{row["by"]} ({switches_mod.MARK})', now, lesson_id))

    def _try(self, c, lesson_id, stages, now, *, given=None, accept=None):
        """Start the lesson's trial now, or have it wait its turn when another lesson is ahead of
        it on its stages. A lesson already waiting keeps its place. given: (share, days) a person
        gave with the yes; else the level that applies when the trial starts. accept: the Accept
        high risk row a high risk lesson with no yes goes on trial under; its marked yes is
        written only if the trial starts now, and a lesson that waits its turn keeps the row's id
        so start_turns reads the switch again."""
        if given is not None:
            share, days, level = given[0], given[1], GIVEN
        else:
            share, days, level = self._level_now(c, lesson_id)
        accept_id = None if accept is None else accept["id"]
        if self._ahead(c, stages, now, lesson_id):  # only given numbers are kept; a level is read at the start
            c.execute("INSERT INTO trials (lesson_id, agent, share, days, queued_at, level, accept_high_id) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (lesson_id) DO UPDATE SET share = excluded.share, "
                      "days = excluded.days, level = excluded.level, accept_high_id = excluded.accept_high_id",
                      (lesson_id, self.agent, share, days, now, GIVEN if given is not None else None, accept_id))
            return False
        if accept is not None:
            self._accept_yes(c, lesson_id, accept, now)
        c.execute("UPDATE lessons SET state = 'trying', share = ?, ends_at = ? WHERE id = ?",
                  (share, now + days * DAY, lesson_id))
        c.execute("INSERT INTO trials (lesson_id, agent, share, days, started_at, level, accept_high_id, worst_cost, "
                  "good, bad, harm, serious, windows) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                  "ON CONFLICT (lesson_id) DO UPDATE SET share = excluded.share, days = excluded.days, "
                  "started_at = excluded.started_at, level = excluded.level, accept_high_id = excluded.accept_high_id, "
                  "worst_cost = excluded.worst_cost, good = excluded.good, bad = excluded.bad, harm = excluded.harm, "
                  "serious = excluded.serious, windows = excluded.windows",
                  (lesson_id, self.agent, share, days, now, level, accept_id, *self._judged_by()))
        return True

    def level_now(self, lesson_id):
        """(share, days, level) a trial of this lesson would start with now: the lesson's own
        level when a person picked one, else the level switch. For a card that waits for a yes."""
        with self.db.tx() as c:
            return self._level_now(c, lesson_id)

    def _level_now(self, c, lesson_id):
        """(share, days, level) for a trial starting now: the lesson's own level when a person
        picked one, else the level switch."""
        row = switches_mod.latest(c, self.agent, switches_mod.LESSON, lesson_id)
        if row is None:
            row = switches_mod.latest(c, self.agent, switches_mod.LEVEL)
        name = switches_mod.CAREFUL if row is None else row["value"]
        lv = self.plug.level(name)
        return lv.share, float(lv.days), name

    def _judged_by(self):
        """What a trial is judged by, copied from the plug when it starts: (worst likely cost, good
        result, bad results, harm results, serious results, the days each deciding result takes
        to show as JSON {result: [least, most]})."""
        p = self.plug
        windows = {r: list(p.results[r].shows_in_days) for r in (p.decides.good, *p.decides.bad)}
        return (p.trial_worst_cost, p.decides.good, tag_text(p.decides.bad), tag_text(p.harm.results),
                tag_text(p.harm.serious), json.dumps(windows))

    def _ahead(self, c, stages, now, skip, before=None):
        """The ids ahead of a lesson on these stages: trials live at `now`, then lessons waiting
        their turn (only those that began waiting before `before`, a (time, id) pair, when
        given). skip: the lesson asking, or None for a new one."""
        skip = -1 if skip is None else skip
        out = [r["id"] for r in c.execute(_LIVE, (self.agent, now, now, skip)) if meet(stages, _tags(r["stages"]))]
        for t in c.execute("SELECT t.lesson_id, t.queued_at, l.stages FROM trials t JOIN lessons l "
                           "ON l.id = t.lesson_id WHERE t.agent = ? AND t.started_at IS NULL AND l.state = 'waiting' "
                           "AND t.lesson_id != ? AND t.queued_at <= ? ORDER BY t.queued_at, t.lesson_id",
                           (self.agent, skip, now)):
            if (before is None or (t["queued_at"], t["lesson_id"]) < before) and meet(stages, _tags(t["stages"])):
                out.append(t["lesson_id"])
        return out

    def set_score(self, lesson_id, score):
        """The score is the one number that moves, as results come in."""
        return self._update("score = ?", (float(score),), lesson_id, "1")

    def get(self, lesson_id):
        """This agent's lesson, or None (another agent's lesson is None too)."""
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM lessons WHERE id = ? AND agent = ?", (lesson_id, self.agent)).fetchone()
        return _row(row) if row else None

    def mine(self, state=None):
        """Every lesson of this agent, oldest first; only one state when named."""
        sql, args = "SELECT * FROM lessons WHERE agent = ?", [self.agent]
        if state is not None:
            sql += " AND state = ?"
            args.append(state)
        with self.db.tx() as c:
            return [_row(r) for r in c.execute(sql + " ORDER BY id", args).fetchall()]

    def live(self, stage=None, now=None):
        """The lessons given now: kept, or on trial before their end date; only those fitting the
        stage when one is named."""
        sql = ("SELECT * FROM lessons WHERE agent = ? AND (state = 'kept' OR (state = 'trying' AND ends_at > ?))")
        args = [self.agent, _now(now)]
        if stage:
            sql += " AND (instr(stages, ?) > 0 OR instr(stages, ?) > 0)"
            args += [f",{stage},", f",{ALL},"]
        with self.db.tx() as c:
            return [_row(r) for r in c.execute(sql + " ORDER BY id", args).fetchall()]

    def pick(self, stage, text, limit=MAX_PICK, *, case=None, now=None, every_share=False):
        """At most 8 live lessons that fit the stage and, for a lesson on trial, this case's share;
        the ones sharing words with the text first, then the higher score, then the older. With
        no case, only lessons given in every case. every_share: skip the share check (the exam
        hands a kept lesson even when a holdback keeps some cases on the old way)."""
        words = {w.lower() for w in _WORD.findall(text or "") if len(w) > 2}
        found = []
        for les in self.live(stage, now):
            if not every_share and not in_share(case, les["id"], les["share"]):
                continue
            overlap = len(words & {w.lower() for w in _WORD.findall(les["text"])})
            found.append((overlap, les["score"], -les["id"], les))
        found.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
        return [t[3] for t in found[:min(limit, MAX_PICK)]]

    def hand(self, case, action, stage, text, given, *, limit=MAX_PICK, now=None):
        """The lessons for one action in one case. Their ids join `given`, the set the action is
        saved with in the log. The stage is one of the plug's stages."""
        self.plug.action(action)
        if stage not in self.plug.stages:
            raise ValueError(f"{stage!r} is not a stage of {self.agent}")
        picked = self.pick(stage, text, limit, case=case, now=now)
        given.update(p["id"] for p in picked)
        return picked

    def _new(self, text, stages, *, source, sources=(), score=0.0, yes_by=None, source_lesson_id=None, trial=True,
             origin=AGENT, kind=PATTERN, exam_given=None, skip_exam=False, now=None):
        text = (text or "").strip()
        if not text or "\n" in text or "\r" in text:
            raise ValueError("a lesson is one line of text")
        if len(text) > MAX_LEN:
            raise ValueError(f"a lesson is {MAX_LEN} characters at most")
        tags = self.plug.stage_tags(stages)
        level, why = risk_mod.classify(text, self.plug.risk, self.judge, sources=sources)
        now = _now(now)
        wants = (self.examiner is not None or exam_given is not None) and trial and takes_exam(origin) and not skip_exam
        exam = exam_given if exam_given is not None or not wants else self._exam(text, tags, level, why, yes_by, origin, now)
        with self.db.tx() as c:  # the switch is read in the same transaction the lesson is written in
            accept = None
            if yes_by is None and trial and level == risk_mod.HIGH and not copied(why):  # a copy always waits for a yes
                row = switches_mod.latest(c, self.agent, switches_mod.ACCEPT)
                if switches_mod.accept_on(row, now):
                    accept = row  # its marked yes is written only as its trial starts (_try, start_turns)
            # a person's own line needs no yes; the agent's starts when low risk, or high under Accept high risk
            start = origin == PERSON or trial and (accept is not None or (yes_by is None and level == risk_mod.LOW))
            cur = c.execute(  # written as waiting, then its trial starts or it waits its turn
                "INSERT INTO lessons (agent, text, stages, fields, risk, risk_why, state, share, ends_at, score, source, "
                "source_lesson_id, origin, kind, yes_by, yes_at, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'waiting', 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent, text, tag_text(tags), tag_text(self.plug.fields), level, "; ".join(why), float(score),
                 source, source_lesson_id, origin, kind, yes_by, now if yes_by is not None else None, now))
            if start and wants and (exam is None or not exam.passed):
                start = False  # held by the exam (or the switch turned on after the exam was skipped): waits for a yes
            if exam is not None:
                exam_mod.save(c, self.agent, cur.lastrowid, exam, now)
            if start:
                self._try(c, cur.lastrowid, tags, now, accept=accept)
            return cur.lastrowid

    def _exam(self, text, tags, level, why, yes_by, origin, now):
        """Run the exam on a new lesson that would start its trial now (see takes_exam): a person's
        line when the rule says so, or the agent's lesson with no yes, low risk or high under Accept
        high risk (read now, and again in _new's transaction). Outside the transaction: model calls
        never hold the write lock. An examiner that raises fails the lesson. None when no exam ran."""
        if origin != PERSON:
            if yes_by is not None:
                return None
            if level != risk_mod.LOW:
                if copied(why):
                    return None
                with self.db.tx() as c:
                    if not switches_mod.accept_on(switches_mod.latest(c, self.agent, switches_mod.ACCEPT), now):
                        return None
        try:
            return self.examiner(text, tags)
        except Exception as e:
            return exam_mod.could_not_run(e)

    def _update(self, sets, args, lesson_id, when, c=None):
        with self._in(c) as c:
            cur = c.execute(f"UPDATE lessons SET {sets} WHERE id = ? AND agent = ? AND {when}",
                            (*args, lesson_id, self.agent))
            return cur.rowcount == 1


def slot(plug, picked):
    """The lessons' place in the agent's prompt: the plug's slot line, then one line each; "" when none."""
    if not picked:
        return ""
    return plug.slot + "\n" + "\n".join(f"- {p['text']}" for p in picked)


def in_share(case, lesson_id, share):
    """Is this case in the lesson's share? The same case always gets the same answer."""
    if share >= 1:
        return True
    if case is None:
        return False
    digest = hashlib.sha256(f"{lesson_id}|{case}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64 < share


def copied(why):
    """Is a lesson high because it copies a run of words from a case it came from (the copy
    check, risk.py)? why: its risk reasons, as saved in risk_why (never rewritten), split on
    "; ". Such a lesson always waits for a person's yes, even while Accept high risk is on."""
    return any(w.startswith(risk_mod.COPIED) for w in why)


def copied_saved(risk_why):
    """copied() on a lesson's risk_why as saved: its reasons joined by "; "."""
    return copied((risk_why or "").split("; "))


def tag_text(tags):
    return "," + ",".join(tags) + ","


def meet(a, b):
    """Do two lessons' stage tags meet? "all" meets every stage."""
    return ALL in a or ALL in b or bool(set(a) & set(b))


def returns_in(c, agent):
    """{lesson id: the pulled lesson it was brought back from} for the agent, read in c; {} in a
    database from before Bring back."""
    if c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lesson_returns'").fetchone() is None:
        return {}
    return {r["lesson_id"]: r["from_id"] for r in c.execute("SELECT lesson_id, from_id FROM lesson_returns "
                                                            "WHERE agent = ?", (agent,))}


def back_family(links, lesson_id):
    """Every lesson linked to this one by Bring back, either way, at any distance, itself
    included. links: as returns_in gives them."""
    near = {}
    for new, old in links.items():
        near.setdefault(new, set()).add(old)
        near.setdefault(old, set()).add(new)
    seen, todo = {lesson_id}, [lesson_id]
    while todo:
        for n in near.get(todo.pop(), ()):
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return seen


def back_copy(links, states, lesson_id):
    """The lesson of this one's bring back family, other than itself, that is not pulled (live,
    on trial or waiting its turn), or None: while there is one, the line is back already.
    states: {lesson id: state}."""
    live = sorted(i for i in back_family(links, lesson_id) - {lesson_id} if states.get(i, PULLED) != PULLED)
    return live[0] if live else None


_STATE_WORDS = {WAITING: "waiting its turn", TRYING: "on trial", KEPT: "kept"}


def _tags(text):
    return [s for s in text.split(",") if s]


# the trials live at a time: on trial, not ended, started by then; the last value skips one lesson
_LIVE = ("SELECT l.* FROM lessons l LEFT JOIN trials t ON t.lesson_id = l.id WHERE l.agent = ? "
         "AND l.state = 'trying' AND l.ends_at > ? AND COALESCE(t.started_at, l.yes_at, l.added_at) <= ? "
         "AND l.id != ? ORDER BY l.id")


def _fill_origin(c):
    """The origin of each lesson written before it was saved, read from what the lesson holds. A
    yes marked "(Accept high risk)" is the switch's, never a person's line."""
    mark = f" ({switches_mod.MARK})"
    for r in c.execute("SELECT id, source, source_lesson_id, yes_by, yes_at FROM lessons "
                       "WHERE origin IS NULL").fetchall():
        person = (r["yes_at"] is not None and r["source_lesson_id"] is None
                  and not (r["source"] or "").startswith(FROM_STUDY) and not (r["yes_by"] or "").endswith(mark))
        c.execute("UPDATE lessons SET origin = ? WHERE id = ?", (PERSON if person else AGENT, r["id"]))


def _fill_kind(c):
    """The kind of each lesson written before it was saved: a person's own line is an idea, the
    rest came from the study's counts or another agent, so a pattern."""
    c.execute("UPDATE lessons SET kind = CASE WHEN origin = 'person' THEN 'idea' ELSE 'pattern' END "
              "WHERE kind IS NULL")


def whose(les):
    """Whose idea a lesson is, as a possessive for a sentence: "the agent's", or the person's
    (person_whose)."""
    return person_whose(les.get("yes_by")) if les.get("origin") == PERSON else "the agent's"


def person_whose(who):
    """A person's name as the owner of a line: "mona's", "the team's" for a line signed "team",
    "a person's" with no name."""
    return "the team's" if who == "team" else f"{who}'s" if who else "a person's"


def _kind(kind):
    if kind not in KINDS:
        raise ValueError(f"kind: one of {', '.join(KINDS)}")
    return kind


def _row(r):
    d = dict(r)
    d["stages"] = [s for s in d["stages"].split(",") if s]
    d["fields"] = [s for s in d["fields"].split(",") if s]
    return d


def _now(now):
    return time.time() if now is None else float(now)


def _line(v, what):
    if not isinstance(v, str) or not v.strip() or "\n" in v:
        raise ValueError(f"{what}: one line of text")
    return v.strip()
