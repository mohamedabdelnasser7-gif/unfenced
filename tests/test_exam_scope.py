"""The Arena's scoped exam (DECISIONS item 75): a lesson takes only its stages' and source situations,
under an exam cap; the run on the kept lessons covers only those, once each; the night keeps the full exam."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import rounds, run
from engine import exam as engine_exam
from engine import plug as plug_mod
from reflection import PLUG
from reflection import exam, night

Row, Result = engine_exam.Row, engine_exam.Result


def sits():
    """Six situations: 1 to 4 asking, 5 and 6 ordering."""
    return [{"id": n, "name": f"s{n}", "part": "guard", "stage": "asking" if n <= 4 else "ordering"}
            for n in range(1, 7)]


class Kept:
    def live(self):
        return []


class Scoped(unittest.TestCase):
    def setUp(self):
        self.runs = []
        self.raise_without = set()
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: sits()))
        self.enterContext(mock.patch.object(exam, "run", side_effect=self.fake_run))

    def fake_run(self, plug, model, *, kept=None, lesson=None, stop_at_first=False, sits=None, safety=None,
                 empty_raises=False):
        ids = [s["id"] for s in sits]
        self.runs.append((lesson is None, ids))
        rows = []
        for n in ids:
            if lesson is None and n in self.raise_without:
                rows.append(Row(n, f"s{n}", "guard", False, engine_exam.ANSWER, "the answer raised"))
            else:
                rows.append(Row(n, f"s{n}", "guard", True))
        return Result(True, rows, calls=len(ids))

    def examiner(self, cap=None):
        return exam.Examiner(PLUG, kept=Kept(), model=object(), count=True, scope=True, cap=cap)

    def test_only_its_stages_and_the_kept_run_of_that_subset_once(self):
        ex = self.examiner()
        r1 = ex("Ask the size first.", ("ordering",))
        r2 = ex("Name the size again.", ("ordering",))
        r3 = ex("Greet in one line.", ("asking",))
        self.assertTrue(r1.passed and r2.passed and r3.passed)
        self.assertEqual(self.runs, [(True, [5, 6]), (False, [5, 6]), (False, [5, 6]), (True, [1, 2, 3, 4]),
                                     (False, [1, 2, 3, 4])])
        self.assertEqual((len(r1.pairs), r1.calls, r2.calls), (2, 4, 2))  # the kept run counted once

    def test_a_lesson_for_every_stage_takes_every_situation(self):
        self.examiner()("Be short.", (plug_mod.ALL,))
        self.assertEqual(self.runs[-1], (False, [1, 2, 3, 4, 5, 6]))

    def test_the_cap_and_the_source_situations(self):
        ex = self.examiner(cap=exam.CALL_CAP * 4)  # room for two new situations, or four with the kept run made
        ex.source = (5,)
        ex("Fix the summary.", ("asking",))
        self.assertEqual(self.runs[-1], (False, [5, 1]))  # the source first, then its stage
        ex.source = ()
        ex("Again.", ("asking",))
        self.assertEqual(self.runs[-1], (False, [1, 2]))  # 1 made already costs half, so 2 fits beside it

    def test_a_cap_with_room_for_none_holds_it(self):
        got = self.examiner(cap=exam.CALL_CAP)("Greet.", ("asking",))
        self.assertEqual((got.passed, got.first.check), (False, engine_exam.NOT_RUN))
        self.assertEqual(self.runs, [])

    def test_a_kept_run_that_raised_is_asked_again(self):
        ex = self.examiner()
        self.raise_without = {2}
        ex("One.", ("asking",))
        self.raise_without = set()
        ex("Two.", ("asking",))
        self.assertEqual(self.runs[2], (True, [2]))


class Wiring(unittest.TestCase):
    def test_the_arena_scopes_and_the_night_does_not(self):
        got = rounds.real_examiner(PLUG, None, object(), cap=12)
        self.assertEqual((got.scope, got.cap, got.count), (True, 12, True))
        self.assertEqual(rounds.real_examiner(PLUG, None, object()).cap, rounds.EXAM_CAP)
        self.assertFalse(night.sales_exam(PLUG)(None).scope)

    def test_exam_cap_flag_must_be_at_least_one(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = run.main(["--exam-cap", "0", "--state", d.name, "--cards", str(run.DEMO_CARDS)],
                            agent_model=object(), customer_model=object())
        self.assertEqual(code, 2)
        self.assertIn("--exam-cap must be at least 1", err.getvalue())

    def test_a_rewrite_points_the_exam_at_what_its_earlier_tries_failed(self):
        between = rounds.Between.__new__(rounds.Between)
        between.scoped = exam.Examiner(PLUG, count=True, scope=True)

        class Lessons:
            def exam_of(self, lid):
                fails = [{"situation": 7, "check": "amounts"}, {"situation": None, "check": engine_exam.NOT_RUN},
                         {"situation": 2, "check": engine_exam.RERUN}] if lid == 1 else [{"situation": 9, "check": "order"}]
                return {"passed": 0, "fails": json.dumps(fails), "situation": None, "check_name": ""}
        between._source(Lessons(), [1, 4])
        self.assertEqual(between.scoped.source, (7, 9))
        between._source(Lessons(), ())
        self.assertEqual(between.scoped.source, ())


if __name__ == "__main__":
    unittest.main()
