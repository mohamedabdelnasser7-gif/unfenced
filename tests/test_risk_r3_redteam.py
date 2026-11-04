"""Red team engfix round 3 (reviews/2026-11-04/redteam-engfix-r3.md): a lesson is one line whatever
the line break; a cut off exam answer is an error, not a short reply; posting with no yes reads high
for the judge of any plug."""
import json
import unittest
from pathlib import Path

from engine.lessons import Lessons
from kit.db import Db
from reflection import exam, judge as judge_mod
from tests import plugs

ROOT = Path(__file__).resolve().parent.parent


def always_low(text, about):
    return "low"


class OneLineWhateverTheBreak(unittest.TestCase):
    def test_every_line_break_is_refused(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        lessons = Lessons(db, plugs.load(plugs.WATERER, self), judge=always_low)
        self.assertTrue(lessons.add("Water the beds then rake.", ["grown"], source="test", yes_by="Mohamed"))
        for brk in ("\n", "\r", "\v", "\f", "\x1c", "\x85", " ", " "):
            with self.subTest(brk=repr(brk)):
                with self.assertRaises(ValueError):
                    lessons.add(f"Water the beds{brk}then rake.", ["grown"], source="test", yes_by="Mohamed")


class CutAnswersAreErrors(unittest.TestCase):
    def test_the_exam_asks_for_a_whole_answer(self):
        got = []

        class Rec:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                got.append(whole)
                return {"content": "x"}
        exam.ExamModel(Rec()).chat([])
        self.assertEqual(got, [True])


class PostingWithNoYes(unittest.TestCase):
    def test_the_judge_reads_posting_with_no_yes_as_always_high(self):
        self.assertIn("published to a customer or the public with no yes", judge_mod.SYSTEM)

    def test_the_marketing_plug_names_posting_with_no_yes_as_high(self):
        data = json.loads((ROOT / "marketing" / "plug.json").read_text(encoding="utf-8"))
        self.assertIn("without the owner's yes", json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
