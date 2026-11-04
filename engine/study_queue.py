"""The study's queue (DECISIONS item 98): lessons a study found but did not examine before it
stopped, saved in the agent's own database so none is dropped. A study stops starting exams when
it is past its deadline (the scheduled night's is 09:00 in NIGHT_TZ, reflection/scheduler.py), when
a person pressed Stop, or when the day's model call cap is reached (engine/study.py Study.run).

The next study of the same agent, a night or a Run reflection, takes the waiting rows first, oldest
first, before any lesson it finds itself: each goes through the same write as when it was found, with
its sources and kind, so it takes the full exam, its risk check, its turn on a stage and a yes when
high, as any lesson does.

A row is written once and taken once: a later study sets when it took it, the lesson it became (or
none) and what happened, and the row stays as the record. Nothing else changes it, and the database
refuses any other change, as it does for lessons and exam rows (engine/lessons.py, engine/exam.py).
count(db, agent) is the number still waiting, for the page; it only reads.
"""
import json
import time

TABLE = """
CREATE TABLE IF NOT EXISTS study_queue (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('pattern', 'idea')),
  part TEXT NOT NULL,
  lesson TEXT NOT NULL,
  item TEXT NOT NULL,
  why TEXT NOT NULL,
  queued_at REAL NOT NULL,
  taken_at REAL,
  lesson_id INTEGER,
  outcome TEXT
);
CREATE INDEX IF NOT EXISTS study_queue_waiting ON study_queue (agent, taken_at, id);
CREATE TRIGGER IF NOT EXISTS study_queue_never_rewritten
BEFORE UPDATE OF id, agent, kind, part, lesson, item, why, queued_at ON study_queue
BEGIN SELECT RAISE(ABORT, 'a queued lesson is never rewritten'); END;
CREATE TRIGGER IF NOT EXISTS study_queue_taken_once
BEFORE UPDATE ON study_queue WHEN OLD.taken_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a queued lesson is taken once'); END;
CREATE TRIGGER IF NOT EXISTS study_queue_never_deleted
BEFORE DELETE ON study_queue
BEGIN SELECT RAISE(ABORT, 'a queued lesson is never deleted; a study takes it'); END;
"""
# study_queue: one row for each lesson a study found and did not examine before it stopped.
# kind: the lesson's kind (engine/lessons.py PATTERN or IDEA). part: where the study found it
# (PARTS). lesson: its line. item: what the write needs again, as JSON: the candidate {lesson,
# situation, stages, ...}, its source line, the texts of the cases it came from (the copy check),
# its counts (rec, or null), where it came from (origin, or null), the kept lesson it was adapted
# from (source_lesson_id, or null) and whether it goes on trial only through the eval gate (gated).
# why: what stopped the study. taken_at, lesson_id and outcome: set once, when a later study took it.
PARTS = ("pattern", "scope", "across", "pool", "idea")


def ensure(db):
    """The study_queue table. Safe to run again."""
    db.script(TABLE)


def add(db, agent, *, kind, part, lesson, item, why, now=None):
    """Queue one lesson; returns its row id."""
    if part not in PARTS:
        raise ValueError(f"{part!r} is not a part of the study")
    with db.tx() as c:
        return c.execute("INSERT INTO study_queue (agent, kind, part, lesson, item, why, queued_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (agent, kind, part, lesson, json.dumps(item, ensure_ascii=False), why,
                          time.time() if now is None else float(now))).lastrowid


def waiting(db, agent):
    """The agent's queued lessons not taken yet, oldest first: [{id, kind, part, lesson, item, why,
    queued_at}], item read back from its JSON."""
    if not _there(db):
        return []
    with db.tx() as c:
        rows = c.execute("SELECT id, kind, part, lesson, item, why, queued_at FROM study_queue "
                         "WHERE agent = ? AND taken_at IS NULL ORDER BY id", (agent,)).fetchall()
    return [dict(dict(r), item=json.loads(r["item"])) for r in rows]


def take(db, agent, queue_id, *, lesson_id=None, outcome, now=None):
    """Mark one queued lesson taken by a study: the lesson it became (None when it was not written)
    and what happened. True when it was waiting and is now taken."""
    with db.tx() as c:
        return c.execute("UPDATE study_queue SET taken_at = ?, lesson_id = ?, outcome = ? "
                         "WHERE id = ? AND agent = ? AND taken_at IS NULL",
                         (time.time() if now is None else float(now), lesson_id, outcome, queue_id, agent)
                         ).rowcount == 1


def count(db, agent):
    """How many lessons wait in the agent's queue for its next study (0 when none was ever queued).
    It only reads: a database with no queue yet is not changed."""
    if not _there(db):
        return 0
    with db.tx() as c:
        return c.execute("SELECT COUNT(*) FROM study_queue WHERE agent = ? AND taken_at IS NULL",
                         (agent,)).fetchone()[0]


def _there(db):
    with db.tx() as c:
        return c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'study_queue'"
                         ).fetchone() is not None
