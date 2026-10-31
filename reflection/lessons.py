"""The Sales agent's lessons: the engine's lessons (engine/lessons.py) under the Sales agent
plug, with the names the Sales agent code already uses.

A lesson is one line, never rewritten. The database refuses any change to a lesson's text
or tags, and a retired lesson stays retired. To change what a lesson says, retire it
and add a new one. The store starts empty; the morning review and the night study fill
it.

add() is the team's own line: it needs no yes, the team wrote it, so it goes on trial in
some chats like any other lesson, or waits its turn when its stage has a trial; its origin
is "person". A lesson the study proposes goes through propose(): low risk lessons are
tried in some chats for a week, high risk ones wait for a yes. Risk comes from the Sales
agent plug's risk list, then the judge it is given. retire() is the engine's pull(), active() its live().

Before the engine the lessons table had no agent, risk or state. The first Lessons(db) on
such a database moves every lesson across with the same id, in one transaction: an active
lesson is kept with the team's yes, a retired one is pulled, and its risk is checked.
"""
from engine import lessons as engine_lessons
from engine import risk
from kit.db import Db
from reflection import PLUG

MAX_PICK = engine_lessons.MAX_PICK
MAX_LEN = engine_lessons.MAX_LEN
ALL = "all"  # tag for a lesson that fits every stage
TEAM = "team"


class Lessons(engine_lessons.Lessons):
    def __init__(self, db=None, judge=risk.no_judge, exam=None):
        """judge: the engine's stub unless given; the running Sales agent passes the Meta judge
        (reflection/judge.py), which counts as high whenever it cannot answer."""
        db = db if db is not None else Db()
        _move_old_lessons(db)
        super().__init__(db, PLUG, judge=judge, exam=exam)

    def add(self, text, stages, source="", score=0.0):
        """Add one line the team wrote: on trial, or waiting its turn (engine Lessons.add).
        Returns its id."""
        return super().add(text, stages, source, score, yes_by=TEAM)

    def retire(self, lesson_id, why=""):
        return self.pull(lesson_id, why)

    def active(self, stage=None):
        return self.live(stage)


def _move_old_lessons(db):
    """Move the lessons of the old table (no agent column) into the engine's table, same ids."""
    with db.tx() as c:
        columns = {r["name"] for r in c.execute("PRAGMA table_info(lessons)")}
        if not columns or "agent" in columns:
            return
        if not c.in_transaction:
            c.execute("BEGIN")  # the renames and the copy are one step: all or nothing
        c.execute("DROP TRIGGER IF EXISTS lessons_never_rewritten")
        c.execute("DROP TRIGGER IF EXISTS lessons_stay_retired")
        c.execute("ALTER TABLE lessons RENAME TO lessons_before_engine")
        c.execute(engine_lessons.TABLE)
        fields = engine_lessons.tag_text(PLUG.fields)
        for r in c.execute("SELECT * FROM lessons_before_engine ORDER BY id").fetchall():
            level, why = risk.classify(r["text"], PLUG.risk)
            c.execute(
                "INSERT INTO lessons (id, agent, text, stages, fields, risk, risk_why, state, share, score, source, "
                "yes_by, yes_at, added_at, pulled_at, pulled_why) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
                (r["id"], PLUG.agent, r["text"], r["stages"], fields, level, "; ".join(why),
                 engine_lessons.KEPT if r["status"] == "active" else engine_lessons.PULLED, r["score"], r["source"],
                 TEAM, r["added_at"], r["added_at"], r["retired_at"], r["retired_why"]))
        c.execute("DROP TABLE lessons_before_engine")
