"""Decision 56: a correction a person sends from the agent page is a hotfix. It takes the exam first, then
starts at once on a 50/50 split whatever the level switch says, and never waits behind a lesson already on
trial on its stage; a high risk one still waits for a yes. Scripted parts only: no model, no network."""
import unittest

from engine import exam as exam_mod
from engine.lessons import HOTFIX_SHARE, TRYING, WAITING, Lessons
from kit.db import Db
from tests import plugs
from tests.test_ideas import BLEACH, ROOTS, SHADE, SOIL, always_low

NOW = 1_780_000_000.0


class ACorrection(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)

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

    def test_the_exam_comes_first(self):
        failed = exam_mod.could_not_run(RuntimeError("no examiner"))
        fixed = Lessons(self.db, self.plug, judge=always_low, exam=lambda text, tags: failed).correct(
            SOIL["lesson"], ["grown"], yes_by="mona", now=NOW)
        self.assertEqual(self.lessons.get(fixed)["state"], WAITING)
        self.assertTrue(self.lessons.approve(fixed, "mohamed", now=NOW + 60))
        self.assertEqual(self.lessons.get(fixed)["share"], HOTFIX_SHARE)
        self.assertEqual(self.lessons.trial(fixed)["days"], float(self.plug.level("fast").days))


if __name__ == "__main__":
    unittest.main()
