"""The exam keeps what the agent said (2026-11-04): each situation's reply with the new lesson and without it,
cut to engine/exam.py MAX_SAID, saved on the lesson's exam row, so a refused lesson can be explained.
Fake answers only, no model."""
import unittest

from engine import exam
from kit.db import Db

SITS = [{"id": 1, "name": "price", "part": "a", "expect": {}}, {"id": 2, "name": "angry", "part": "a", "expect": {}}]


def answer(s, lesson):
    side = "with" if lesson else "without"
    if s["id"] == 2 and lesson:
        return {"said": "x" * 900, "calls": 1}
    return {"said": f"{side} {s['name']}", "calls": 1}


def check(s, did):
    return "too long" if len(did["said"]) > 100 else ""


class ExamKeepsAnswers(unittest.TestCase):
    def result(self):
        before = exam.sit(SITS, answer, {"short": check}, ("short",))
        after = exam.sit(SITS, answer, {"short": check}, ("short",), lesson="Be brief.")
        return exam.judge(after.rows, before.rows, len(SITS), None)

    def test_both_sides_are_kept_capped(self):
        got = exam.answers(self.result())
        self.assertEqual([a["situation"] for a in got], [1, 2])
        self.assertEqual((got[0]["with_lesson"], got[0]["without_lesson"]), ("with price", "without price"))
        self.assertEqual((got[1]["with_lesson"], got[1]["without_lesson"]), ("x" * exam.MAX_SAID, "without angry"))

    def test_the_refused_lessons_row_keeps_them(self):
        res = self.result()
        self.assertFalse(res.passed)
        db = Db(":memory:")
        self.addCleanup(db.close)
        db.script("CREATE TABLE lessons (id INTEGER PRIMARY KEY);")
        exam.ensure(db)
        with db.tx() as c:
            c.execute("INSERT INTO lessons (id) VALUES (7)")
            exam.save(c, "sales", 7, res, now=1.0)
        with db.tx() as c:
            row = exam.of(c, "sales", 7)
        kept = exam.answers_of(row)
        self.assertEqual(kept, exam.answers(res))
        self.assertEqual(kept[1]["with_lesson"], "x" * 600)
        self.assertEqual(exam.answers_of({"answers": None}), [])

    def test_a_row_rebuilt_by_the_vote_keeps_its_reply(self):
        rows = exam.sit(SITS[:1], answer, {"short": check}, ("short",)).rows
        self.assertEqual(exam.vote(rows + rows).said, "without price")


class BothAgentsHandTheirWords(unittest.TestCase):
    """The two exam answers, the built-in agent's and a built agent's, give the engine their words."""

    def setUp(self):
        from tests.fake_model import clean_env
        clean_env(self)

    def test_the_built_in_exam(self):
        from reflection import PLUG, exam as rexam
        from tests.fake_model import FakeModel, say
        did = rexam.answer(rexam.situations(PLUG)[0], None, model=FakeModel(say("We will ask the team.")))
        self.assertEqual(did[exam.SAID], "We will ask the team.")

    def test_a_built_agents_exam(self):
        import shutil
        import tempfile
        from pathlib import Path
        from kit import turn
        from reflection import turn_exam
        from tests.fake_model import FakeModel, say
        from tests.test_arena_practice import FIXTURE
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        folder = Path(d.name) / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, folder)
        did = turn_exam.answer({"id": 1, "turns": [{"customer": "Do you have it?"}]}, None,
                               agent=turn.load(folder), model=FakeModel(say("Yes, it is in stock.")))
        self.assertEqual(did[exam.SAID], "Yes, it is in stock.")


if __name__ == "__main__":
    unittest.main()
