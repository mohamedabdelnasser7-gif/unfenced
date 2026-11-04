"""Arena run 20261104T143545, cause 2: fixed against broke counts safety checks only, and the run on the
kept lessons is voted per situation (engine/exam.py vote, reflection/exam.py Examiner), so one noisy
answer reused for a whole round neither excuses a break nor makes a fix. Fake models only, no network."""
import unittest
from unittest import mock

from engine import exam as engine_exam
from reflection import PLUG
from reflection import exam
from tests.fake_model import say

Row, Result = engine_exam.Row, engine_exam.Result
SAFETY = ("amounts", "order")


def row(n, *fails):
    if not fails:
        return Row(n, f"s{n}", "guard", True)
    pairs = tuple((c, f"{c} failed") for c in fails)
    return Row(n, f"s{n}", "guard", False, pairs[0][0], pairs[0][1], pairs)


class Vote(unittest.TestCase):
    def test_majority_of_the_answers_that_did_not_raise(self):
        raised = Row(1, "s1", "guard", False, engine_exam.ANSWER, "down")
        v = engine_exam.vote([row(1, "amounts"), row(1), row(1)])
        self.assertTrue(v.passed)
        v = engine_exam.vote([row(1, "amounts", "script"), row(1, "amounts"), row(1)])
        self.assertEqual([c for c, _ in v.fails], ["amounts"])
        self.assertEqual(engine_exam.vote([raised, row(1, "amounts")]).check, "amounts")  # one usable answer
        self.assertIs(engine_exam.vote([raised]), raised)
        self.assertIsNone(engine_exam.vote([]))


class Counted(unittest.TestCase):
    def test_style_breaks_never_hold_safety_counts_do(self):
        after = [row(1, "script"), row(2, "script"), row(3)]
        before = [row(1), row(2), row(3, "script")]
        r = engine_exam.judge(after, before, 3, SAFETY)
        self.assertTrue(r.passed)
        eff = engine_exam.effect(r.pairs)  # reported over every check
        self.assertEqual((eff["fixed"], eff["broke"]), (1, 2))
        safe = engine_exam.effect(engine_exam.pair_rows(before, after, SAFETY))
        self.assertEqual((safe["fixed"], safe["broke"], safe["both_right"]), (0, 0, 3))


class Counter:
    def __init__(self):
        self.n = 0

    def chat(self, *a, **kw):
        self.n += 1
        return say("ok")


class Kept:
    def live(self):
        return []


class BaselineVote(unittest.TestCase):
    """Situation 2: its first answer on the kept lessons fails amounts by chance and every later one passes
    (or, with mostly_fails, the other way round)."""

    def setUp(self):
        self.without = {}
        self.runs = []
        sits = [{"id": n, "name": f"s{n}", "part": "guard", "stage": "asking"} for n in (1, 2)]
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: sits))
        self.enterContext(mock.patch.object(exam, "run", side_effect=self.fake_run))
        self.lesson_breaks, self.mostly_fails = True, False

    def fake_run(self, plug, model, *, kept=None, lesson=None, sits=None, **kw):
        rows = []
        for s in sits:
            model.chat([])
            n = s["id"]
            self.runs.append((lesson is not None, n))
            if lesson is None:
                self.without[n] = self.without.get(n, 0) + 1
                first = self.without[n] == 1
                rows.append(row(n, "amounts") if n == 2 and first != self.mostly_fails else row(n))
            else:
                rows.append(row(n, "amounts") if n == 2 and self.lesson_breaks else row(n))
        return Result(True, rows, calls=len(sits))

    def test_a_fail_the_vote_shows_before_is_no_break(self):
        self.mostly_fails = True  # situation 2's first answer passes by chance, every later one fails amounts
        m = Counter()
        r = exam.Examiner(PLUG, kept=Kept(), model=m, count=True, cap=400)("Say the pair is 9999.", ("all",))
        self.assertTrue(r.passed)
        # before 2, with 2, then the vote's 2 answers without on 2; no recheck: the fail was there before
        self.assertEqual(self.runs[4:], [(False, 2), (False, 2)])
        self.assertEqual((m.n, r.calls), (6, 6))

    def test_a_noisy_fail_before_makes_no_fix(self):
        self.lesson_breaks = False
        r = exam.Examiner(PLUG, kept=Kept(), model=Counter(), count=True)("Greet them.", ("all",))
        self.assertTrue(r.passed)
        self.assertEqual(engine_exam.effect(r.pairs)["fixed"], 0)

    def test_the_vote_is_paid_once_per_kept_set_and_inside_the_cap(self):
        self.lesson_breaks = False
        m = Counter()
        ex = exam.Examiner(PLUG, kept=Kept(), model=m, count=True, scope=True, cap=60)
        ex("Greet them.", ("asking",))
        self.assertEqual(len(ex._rows[()][2]), engine_exam.BASE_VOTES)
        before = m.n
        ex("Greet them again.", ("asking",))
        self.assertEqual(m.n - before, 2)  # the lesson's own answers only
        tight = exam.Examiner(PLUG, kept=Kept(), model=Counter(), count=True, cap=4 + 7)
        self.without.clear()
        tight("Greet them.", ("all",))
        self.assertEqual(len(tight._rows[()][2]), 1)  # two more answers of 4 calls each do not fit in 7


if __name__ == "__main__":
    unittest.main()
