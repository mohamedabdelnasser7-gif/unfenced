"""Why passed lessons were not handed in the Arena run 20261104T120239 (part B): the full exam held them, and
the report cut that line, as it prints only a round's first three notes; and an empty live database read as
"live busy (no such table: lessons)". Every line below is made up."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from arena import rounds, run
from reflection import PLUG


def report(lessons):
    reflection = {"after_round": 1, "cases": 1, "proposed": len(lessons), "passed": 1, "refused": 0,
                  "waits_for_yes": 0, "handed": 0, "fixed": 0, "broke": 0, "calls": 9, "lessons": lessons,
                  "notes": ["one", "two", "three", "four"]}
    return {"run": "r", "agent": "sales", "stopped": "stuck", "trust": {"wins": 7, "matches": 10},
            "fact_checks": True, "training_cards": ["a"], "held_out_cards": ["b"],
            "rounds": [{"round": 1, "training": {"won": 0, "played": 1, "cases": [1]},
                        "gate": {"won": 0, "played": 1, "lost": []}, "reflection": reflection}],
            "calls": {"day": "2026-11-04", "used": 9, "cap": 100}}


class TheReport(unittest.TestCase):
    def test_a_passed_lesson_says_why_it_was_not_handed(self):
        held = f"{rounds.FULL_HELD} (failed the exam: situation 2, check amounts)"
        lines = run.text(report([{"lesson_id": 1, "risk": "low", "passed": True, "handed": False,
                                  "waits_for_yes": False, "why": "", "gate": {"fixed": 0, "broke": 0},
                                  "live": held}]))
        self.assertIn(f"lesson 1 (low risk): passed, not handed (0 fixed, 0 broke); {held}", lines)
        self.assertIn("not handed to the next round nor live", lines)

    def test_a_handed_lesson_reads_as_before(self):
        lines = run.text(report([{"lesson_id": 2, "risk": "low", "passed": True, "handed": True,
                                  "waits_for_yes": False, "why": "", "gate": {"fixed": 1, "broke": 0}}]))
        self.assertIn("lesson 2 (low risk): handed on (1 fixed, 0 broke)\n", lines + "\n")


class AnEmptyLiveDatabase(unittest.TestCase):
    def test_no_lessons_table_holds_no_correction(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ascent.db"
            sqlite3.connect(str(path)).close()  # a new, empty database file
            self.assertEqual(rounds.live_hotfixes(path, PLUG.agent), [])
            pool = rounds.Pool(_NoLessons(), hotfixes=lambda: rounds.live_hotfixes(path, PLUG.agent))
            pool.refresh()
            self.assertIsNone(pool.busy)  # not "live busy"

    def test_a_missing_file_is_still_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(sqlite3.Error):
                rounds.live_hotfixes(Path(d) / "none.db", PLUG.agent)
            self.assertFalse((Path(d) / "none.db").exists())


class _NoLessons:
    def live(self, stage=None, now=None):
        return []

    def get(self, lesson_id):
        return None


if __name__ == "__main__":
    unittest.main()
