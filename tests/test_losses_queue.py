"""The Arena's fresh copy keeps the study queue's waiting rows of the last copy (losses part H): a Stop on the page
queues leftover lessons in <db>.arena, and the next run's copy must not drop them. The table here is a made-up
stand-in of engine/study_queue.py's shape (not on this branch), made by the test, never imported."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from arena import run

QUEUE = """
CREATE TABLE study_queue (id INTEGER PRIMARY KEY, agent TEXT NOT NULL, kind TEXT NOT NULL, part TEXT NOT NULL,
  lesson TEXT NOT NULL, item TEXT NOT NULL, why TEXT NOT NULL, queued_at REAL NOT NULL, taken_at REAL,
  lesson_id INTEGER, outcome TEXT);
CREATE INDEX study_queue_waiting ON study_queue (agent, taken_at, id);
CREATE TRIGGER study_queue_never_deleted BEFORE DELETE ON study_queue
BEGIN SELECT RAISE(ABORT, 'never deleted'); END;
"""
ROW = "INSERT INTO study_queue (agent, kind, part, lesson, item, why, queued_at, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"


def rows(path):
    c = sqlite3.connect(str(path))
    try:
        return c.execute("SELECT agent, lesson, why, queued_at, taken_at FROM study_queue ORDER BY id").fetchall()
    finally:
        c.close()


class Queue(unittest.TestCase):
    def test_the_fresh_copy_keeps_the_waiting_queue_rows_once(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        live = Path(d.name) / "agent.db"
        c = sqlite3.connect(str(live))
        c.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY)")  # the live database has no queue yet
        c.commit()
        c.close()
        old = run.arena_copy(live)
        c = sqlite3.connect(str(old))
        c.executescript(QUEUE)
        c.execute(ROW, ("sales", "pattern", "pattern", "Ask the size first.", "{}", "stopped", 100.0, None))
        c.execute(ROW, ("sales", "idea", "idea", "A line taken already.", "{}", "stopped", 90.0, 120.0))
        c.commit()
        c.close()
        new = run.arena_copy(live)
        self.assertEqual(rows(new), [("sales", "Ask the size first.", "stopped", 100.0, None)])  # taken: not carried
        c = sqlite3.connect(str(new))
        with self.assertRaises(sqlite3.DatabaseError):  # the table came with its own rules
            c.execute("DELETE FROM study_queue")
        c.close()
        again = run.arena_copy(live)  # the next run carries it on, still once
        self.assertEqual(rows(again), [("sales", "Ask the size first.", "stopped", 100.0, None)])
        c = sqlite3.connect(str(live))
        try:  # the live database is only read
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'study_queue'").fetchone())
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
