"""Decision 56: a correction a person sends from the agent page is a hotfix. It takes the exam first, then
starts at once on a 50/50 split whatever the level switch says, and never waits behind a lesson already on
trial on its stage; a high risk one still waits for a yes. Scripted parts only: no model, no network."""
import tempfile
import unittest
from pathlib import Path

from engine import exam as exam_mod
from engine.lessons import HOTFIX_SHARE, TRYING, WAITING, Lessons
from kit.db import Db
from reflection import morning as morning_mod
from tests import plugs
from tests.test_ideas import BLEACH, ROOTS, SHADE, SOIL, always_low

NOW = 1_780_000_000.0


def passed(text, tags):
    """An exam the correction passes."""
    return exam_mod.Result(True, [exam_mod.Row(1, "s1", "guard", True)], calls=1)


class ACorrection(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low, exam=passed)

    def test_it_starts_at_once_on_half_the_cases(self):
        fixed = self.lessons.correct(SOIL["lesson"], ["grown"], yes_by="mona", now=NOW)
        les, trial = self.lessons.get(fixed), self.lessons.trial(fixed)
        self.assertEqual((les["state"], les["share"], trial["share"]), (TRYING, HOTFIX_SHARE, HOTFIX_SHARE))
        self.assertEqual(trial["days"], float(self.plug.level("fast").days))

    def test_it_never_waits_behind_a_lesson_on_trial_on_its_stage(self):
        first = self.lessons.add(SHADE["lesson"], ["all"], "typed", yes_by="mona", now=NOW)
        typed = self.lessons.add(ROOTS["lesson"], ["seedling"], "typed", yes_by="mona", now=NOW)
        fixed = self.lessons.correct(SOIL["lesson"], ["grown"], yes_by="mona", now=NOW)
        self.assertEqual(self.lessons.get(first)["state"], TRYING)
        self.assertEqual(self.lessons.get(typed)["state"], WAITING)  # a plain line still waits its turn
        self.assertEqual(self.lessons.get(fixed)["state"], TRYING)

    def test_a_high_risk_correction_waits_for_a_yes_then_starts_on_half(self):
        fixed = self.lessons.correct(BLEACH["lesson"], ["grown"], yes_by="mona", now=NOW)
        self.assertEqual((self.lessons.get(fixed)["risk"], self.lessons.get(fixed)["state"]), ("high", WAITING))
        self.assertTrue(self.lessons.approve(fixed, "mohamed", now=NOW + 60))
        self.assertEqual((self.lessons.get(fixed)["state"], self.lessons.get(fixed)["share"]), (TRYING, HOTFIX_SHARE))
        self.assertEqual(self.lessons.trial(fixed)["days"], float(self.plug.level("fast").days))

    def test_no_exam_no_correction(self):
        """Fail closed: with no examiner and no exam result nothing is saved (red team handoff2 round 1, item 2)."""
        bare = Lessons(self.db, self.plug, judge=always_low)
        with self.assertRaisesRegex(ValueError, "exam"):
            bare.correct(SOIL["lesson"], ["grown"], yes_by="mona", now=NOW)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0], 0)
        given = bare.correct(SOIL["lesson"], ["grown"], yes_by="mona", exam=passed(SOIL["lesson"], ()), now=NOW)
        self.assertEqual(self.lessons.get(given)["state"], TRYING)
        self.assertTrue(self.lessons.exam_of(given)["passed"])

    def test_the_exam_comes_first(self):
        failed = exam_mod.could_not_run(RuntimeError("no examiner"))
        fixed = Lessons(self.db, self.plug, judge=always_low, exam=lambda text, tags: failed).correct(
            SOIL["lesson"], ["grown"], yes_by="mona", now=NOW)
        self.assertEqual(self.lessons.get(fixed)["state"], WAITING)
        self.assertTrue(self.lessons.approve(fixed, "mohamed", now=NOW + 60))
        self.assertEqual(self.lessons.get(fixed)["share"], HOTFIX_SHARE)
        self.assertEqual(self.lessons.trial(fixed)["days"], float(self.plug.level("fast").days))


class OnToday(unittest.TestCase):
    """Review handoff2 round 1, finding 4: a high risk correction has its writer's yes, yet it waits for a yes,
    so Today shows its Yes card, and that Yes starts it on half the cases."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.plug = plugs.load(plugs.WATERER, self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low, exam=passed)
        self.morning = morning_mod.Morning(self.db, [self.plug], reports=Path(folder.name))

    def test_a_high_risk_correction_is_a_yes_card_on_today(self):
        fixed = self.lessons.correct(BLEACH["lesson"], ["grown"], yes_by="mona", now=NOW)
        self.assertIsNotNone(self.lessons.get(fixed)["yes_at"])
        self.assertTrue(self.lessons.wants_yes(fixed))
        view = self.morning.view(NOW + 1)
        self.assertIn(fixed, [c["id"] for c in view["cards"]])
        page = morning_mod.render(view, token="t")
        self.assertEqual(page.count('action="/yes"'), 1)
        self.morning.yes(fixed, now=NOW + 2)
        self.assertEqual((self.lessons.get(fixed)["state"], self.lessons.get(fixed)["share"]), (TRYING, HOTFIX_SHARE))
        self.assertFalse(self.lessons.wants_yes(fixed))
        self.assertNotIn(fixed, [c["id"] for c in self.morning.view(NOW + 3)["cards"]])


if __name__ == "__main__":
    unittest.main()
