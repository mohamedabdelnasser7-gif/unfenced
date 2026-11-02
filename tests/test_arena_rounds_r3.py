"""Review simplify round 3, finding 2: tests for the round 2 fixes the mutation sweep showed had none
(arena/rounds.py Between._gate, LiveKept and _Budget). A lesson the full exam holds is never handed on,
so it never plays the next round; the full exam sees the corrections that run live on the user's page,
in live() and in pick(); and each lesson's full exam starts with the whole FULL_CAP. Fake models only,
no network; the cards are made here, never read from arena/real/."""
import unittest
from unittest import mock

from arena import rounds
from engine import exam as engine_exam
from tests import test_arena_rounds as tar
from tests.test_arena_hotfix import FIX, correct
from tests.test_arena_rounds import BAD, GOOD, WHOLESALE


class HeldIsNotHanded(tar.Base):
    """R2-1a: the full exam runs before hand_on, so a lesson it holds never plays the next round."""

    run_real = tar.RealFullExam.run_real  # the real full exam, its tests not run twice

    def test_a_lesson_the_full_exam_holds_never_plays_the_next_round(self):
        db, got, _ = self.run_real([WHOLESALE], [WHOLESALE])
        self.assertTrue(got["lessons"][0]["full_exam"].startswith("held"), got["lessons"][0])
        _, after = self.round_two()
        self.assertTrue(after)
        self.assertFalse(any(WHOLESALE in s for s in after), after[0])

    def test_a_lesson_the_full_exam_passes_plays_the_next_round(self):
        db, got, _ = self.run_real([WHOLESALE], [])
        self.assertEqual(got["lessons"][0]["full_exam"], "passed")
        _, after = self.round_two()
        self.assertTrue(after and all(WHOLESALE in s for s in after), after[:1])


class TheFullExamSeesTheLiveCorrections(tar.Base):
    """R2-1f and R2-1g: a correction that passed its exam and runs live on the user's page is on the kept
    side of the full exam, in live() and in pick(), as the live agent holds it."""

    def test_a_live_correction_is_on_the_kept_side_of_the_full_exam(self):
        db = self.db()
        correct(db, FIX)
        seen = []

        def full(plug, kept, model):
            def examine(text, tags):
                seen.append((text, [p["text"] for p in kept.live()], [p["text"] for p in kept.pick("greeting", "hi")]))
                return engine_exam.Result(passed=True, rows=[engine_exam.Row(1, "s1", "guard", True)], calls=0)
            return examine
        self.cli(db, [GOOD, BAD], refuse=[BAD], full=full)
        self.assertEqual([s[0] for s in seen], [GOOD])
        _, live, picked = seen[0]
        self.assertIn(FIX, live)
        self.assertIn(FIX, picked)
        self.assertNotIn(GOOD, live + picked)  # the lesson under exam is never on its own kept side


class EachLessonHasTheWholeCap(tar.Base):
    """R2-6c: the budget starts again at every lesson, so two lessons whose full exams together take
    more than FULL_CAP calls both pass when each takes less."""

    def test_two_lessons_each_under_the_cap_both_pass(self):
        calls = []

        def full(plug, kept, model):
            def examine(text, tags):
                for _ in range(2):
                    model.chat([{"role": "system", "content": "exam"}, {"role": "user", "content": text}])
                calls.append(text)
                return engine_exam.Result(passed=True, rows=[engine_exam.Row(1, "s1", "guard", True)], calls=2)
            return examine
        with mock.patch.object(rounds, "FULL_CAP", 3):
            code, rep = self.cli(self.db(), [GOOD, WHOLESALE], full=full)
        got = rep["rounds"][0]["reflection"]["lessons"]
        self.assertEqual(sorted(calls), sorted([GOOD, WHOLESALE]))
        for one in got:
            with self.subTest(lesson=one["text"]):
                self.assertEqual(one["full_exam"], "passed", one)
                self.assertTrue(one["handed"])


if __name__ == "__main__":
    unittest.main()
