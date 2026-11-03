"""Engine fix B (2026-11-03): one noisy answer never holds a lesson alone. A safety check that newly
fails with the line is voted over that situation answered twice more with it and twice more without
(engine/exam.py recheck, called by reflection/exam.py Examiner in the scoped and the full exam). At most
RECHECK_MAX situations a lesson, stopping at the first confirmed break, inside the exam's cap; a rerun
answer that raised counts against the lesson. Fake models only, no network."""
import unittest
from unittest import mock

from engine import exam as engine_exam
from reflection import PLUG
from reflection import exam
from tests.fake_model import clean_env, say

Row, Result = engine_exam.Row, engine_exam.Result
SAFETY = ("amounts", "order")
OK, BAD = "ok", "bad"


def row(n, *fails):
    if not fails:
        return Row(n, f"s{n}", "guard", True)
    pairs = tuple((c, f"{c} failed") for c in fails)
    return Row(n, f"s{n}", "guard", False, pairs[0][0], pairs[0][1], pairs)


def raised(n):
    return Row(n, f"s{n}", "guard", False, engine_exam.ANSWER, "the answer raised: down")


class Script:
    """again(situation, with_line): the next scripted row for that side of that situation."""

    def __init__(self, **sides):  # w1=[rows], o1=[rows]: with and without the line, situation 1
        self.sides = {k: list(v) for k, v in sides.items()}
        self.asked = []

    def __call__(self, sid, with_line):
        self.asked.append((sid, with_line))
        got = self.sides[f"{'w' if with_line else 'o'}{sid}"].pop(0)
        if isinstance(got, Exception):
            raise got
        return got


def vote(after, before, again, left=None):
    a, b, changed = engine_exam.recheck(after, before, SAFETY, again, left=left, per=4)
    return engine_exam.judge(a, b, len(after), SAFETY), a, b, changed


class Recheck(unittest.TestCase):
    def test_a_check_broken_once_by_noise_passes(self):
        again = Script(w1=[row(1), row(1)], o1=[row(1), row(1)])
        res, a, b, changed = vote([row(1, "amounts"), row(2)], [row(1), row(2)], again)
        self.assertTrue(res.passed)
        self.assertEqual((a[0].passed, changed), (True, {}))
        self.assertEqual(len(again.asked), 4)

    def test_a_check_broken_in_the_majority_fails(self):
        again = Script(w1=[row(1, "amounts"), row(1)], o1=[row(1), row(1)])
        res, a, _, _ = vote([row(1, "amounts"), row(2)], [row(1), row(2)], again)
        self.assertFalse(res.passed)
        self.assertEqual((res.blocked.situation, res.blocked.check), (1, "amounts"))
        self.assertEqual(a[0].check, "amounts")

    def test_a_check_that_fails_without_the_line_too_is_not_new(self):
        again = Script(w1=[row(1, "amounts"), row(1, "amounts")], o1=[row(1, "amounts"), row(1, "amounts")])
        res, _, b, changed = vote([row(1, "amounts")], [row(1)], again)
        self.assertTrue(res.passed)
        self.assertEqual(list(changed), [1])
        self.assertEqual((b[0].passed, b[0].check), (False, "amounts"))

    def test_a_rerun_that_raised_counts_against_the_lesson(self):
        # with: the first answer failed, one rerun raised: two of three against it
        again = Script(w1=[raised(1), row(1)], o1=[row(1), row(1)])
        self.assertFalse(vote([row(1, "amounts")], [row(1)], again)[0].passed)
        # an again that raised itself counts the same way
        again = Script(w1=[RuntimeError("down"), row(1)], o1=[row(1), row(1)])
        self.assertFalse(vote([row(1, "amounts")], [row(1)], again)[0].passed)
        # without: answers that raised count as passing there, so they never excuse the lesson
        again = Script(w1=[row(1, "amounts"), row(1)], o1=[raised(1), RuntimeError("down")])
        self.assertFalse(vote([row(1, "amounts")], [row(1)], again)[0].passed)

    def test_no_room_for_the_worst_case_leaves_it_broken(self):
        again = Script(w1=[row(1), row(1)], o1=[row(1), row(1)])
        res = vote([row(1, "amounts")], [row(1)], again, left=lambda: 15)[0]  # 4 answers x 4 calls = 16
        self.assertFalse(res.passed)
        self.assertEqual(again.asked, [])
        res = vote([row(1, "amounts")], [row(1)], again, left=lambda: 16)[0]
        self.assertTrue(res.passed)

    def test_at_most_three_situations_a_lesson(self):
        sides = {}
        for n in range(1, 6):
            sides[f"w{n}"], sides[f"o{n}"] = [row(n), row(n)], [row(n), row(n)]
        again = Script(**sides)
        after = [row(n, "amounts") for n in range(1, 6)]
        res, a, _, _ = vote(after, [row(n) for n in range(1, 6)], again)
        self.assertEqual(sorted({sid for sid, _ in again.asked}), [1, 2, 3])
        self.assertEqual(len(again.asked), 12)
        self.assertEqual([r.passed for r in a], [True, True, True, False, False])
        self.assertFalse(res.passed)
        self.assertEqual(res.blocked.situation, 4)

    def test_it_stops_at_the_first_confirmed_break(self):
        again = Script(w1=[row(1, "amounts"), row(1, "amounts")], o1=[row(1), row(1)],
                       w2=[row(2), row(2)], o2=[row(2), row(2)])
        res = vote([row(1, "amounts"), row(2, "order")], [row(1), row(2)], again)[0]
        self.assertFalse(res.passed)
        self.assertEqual({sid for sid, _ in again.asked}, {1})

    def test_only_a_newly_broken_safety_check_is_rechecked(self):
        again = Script()
        cases = (
            ([row(1, "tone")], [row(1)]),                       # a style check: it never blocks
            ([row(1, "amounts")], [row(1, "amounts")]),         # broken before too: not new
            ([raised(1)], [row(1)]),                            # the answer raised: always blocks
            ([row(1, "amounts")], [raised(1)]),                 # no answer before to compare
            ([row(1, "amounts")], []),                          # no run before
            ([Row(1, "s1", "guard", False, "amounts", "x", (("amounts", "x"), ("nope", engine_exam.NO_CHECK)))],
             [row(1)]),                                         # a check name with no check also holds it
        )
        for after, before in cases:
            with self.subTest(after=after, before=before):
                self.assertEqual(engine_exam.disputed(after, before, SAFETY), [])
        self.assertEqual(again.asked, [])


def sits():
    return [{"id": n, "name": f"s{n}", "part": "guard", "stage": "asking"} for n in range(1, 5)]


class Kept:
    def live(self):
        return []


class Counter:
    """A model that only counts: the patched run calls it once an answer, as the real one does."""

    def __init__(self):
        self.n = 0

    def chat(self, *a, **kw):
        self.n += 1
        return say(OK)


class ExaminerWiring(unittest.TestCase):
    """reflection/exam.py Examiner, with run patched: situation 2 fails "amounts" with the line once
    (noise) or always (a real break)."""

    def setUp(self):
        self.runs, self.always = [], False
        self.with_answers = {}  # situation id: answers given with the line so far
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: sits()))
        self.enterContext(mock.patch.object(exam, "run", side_effect=self.fake_run))

    def fake_run(self, plug, model, *, kept=None, lesson=None, stop_at_first=False, sits=None, safety=None):
        rows = []
        for s in sits:
            model.chat([])
            n = s["id"]
            self.runs.append((lesson is not None, n))
            if lesson is not None:
                self.with_answers[n] = self.with_answers.get(n, 0) + 1
                broke = n == 2 and (self.always or self.with_answers[n] == 1)
                rows.append(row(n, "amounts") if broke else row(n))
            else:
                rows.append(row(n))
        return Result(True, rows, calls=len(sits))

    def examiner(self, model, **kw):
        return exam.Examiner(PLUG, kept=Kept(), model=model, count=True, **kw)

    def test_full_exam_noise_passes_with_four_more_calls(self):
        m = Counter()
        r = self.examiner(m)("Greet them warmly.", ("all",))
        self.assertTrue(r.passed)
        self.assertEqual((m.n, r.calls), (4 + 4 + 4, 12))  # before, with, then 2 with and 2 without on situation 2
        self.assertEqual(self.runs[8:], [(True, 2), (True, 2), (False, 2), (False, 2)])

    def test_full_exam_real_break_fails(self):
        self.always = True
        m = Counter()
        r = self.examiner(m, cap=400)("Greet them warmly.", ("all",))
        self.assertFalse(r.passed)
        self.assertEqual((r.blocked.situation, r.blocked.check), (2, "amounts"))

    def test_no_dispute_costs_nothing(self):
        self.with_answers[2] = 5  # past the noisy first answer
        m = Counter()
        self.assertTrue(self.examiner(m)("Greet them warmly.", ("all",)).passed)
        self.assertEqual(m.n, 8)

    def test_the_cap_is_respected(self):
        for cap, rechecked in ((8 + 15, False), (8 + 16, True)):
            with self.subTest(cap=cap):
                self.with_answers.clear()
                m = Counter()
                r = self.examiner(m, cap=cap)("Greet them warmly.", ("all",))
                self.assertLessEqual(m.n, cap)
                self.assertEqual(r.passed, rechecked)

    def test_scoped_exam_rechecks_inside_its_cap_and_keeps_the_voted_row(self):
        m = Counter()
        ex = self.examiner(m, scope=True, cap=60)
        r = ex("Greet them warmly.", ("asking",))
        self.assertTrue(r.passed)
        self.assertLessEqual(m.n, 60)
        self.assertEqual(m.n, 4 + 4 + 4)
        tight = self.examiner(Counter(), scope=True, cap=16)  # room for two situations (8 calls each), none for reruns
        self.with_answers.clear()
        self.assertFalse(tight("Greet them warmly.", ("asking",)).passed)

    def test_a_voted_row_before_is_kept_for_the_next_lesson(self):
        self.always = True
        real = self.fake_run

        def without_fails_too(plug, model, *, kept=None, lesson=None, sits=None, **kw):
            got = real(plug, model, kept=kept, lesson=lesson, sits=sits)
            if lesson is None and any(s["id"] == 2 for s in sits) and len(sits) == 1:
                return Result(True, [row(2, "amounts")], calls=1)
            return got
        exam.run.side_effect = without_fails_too
        m = Counter()
        ex = self.examiner(m, scope=True, cap=60)
        self.assertTrue(ex("Greet them warmly.", ("asking",)).passed)  # it fails without the line too
        self.assertEqual(ex._rows[()][2].check, "amounts")
        before = m.n
        self.assertTrue(ex("Greet them kindly.", ("asking",)).passed)
        self.assertEqual(m.n - before, 4)  # the kept run reused, situation 2 no longer new: no reruns


class ArenaFullExam(unittest.TestCase):
    def test_the_full_exam_reruns_inside_the_full_cap(self):
        from arena import rounds
        ex = rounds.full_examiner(PLUG, None, Counter())
        self.assertEqual((ex.cap, ex.scope, ex.count), (rounds.FULL_CAP, False, True))


class RealPathMeasure(unittest.TestCase):
    """The Sales exam's real answer path on five real situations with a fake model: an invented amount
    once with the line is noise; the extra calls are measured."""

    BAD = "الجزمة بـ 9,999 جنيه."
    SAFE = "أهلا بيك! تحب تسأل عن ايه؟"
    LINE = "Greet them warmly before anything else."

    def model(self, bad_on):
        line, seen = self.LINE, {"with": 0}

        class Fake:
            calls = 0

            def chat(self_, messages, tools=None, **kw):
                Fake.calls += 1
                if any(line in str(m.get("content") or "") for m in messages):
                    seen["with"] += 1
                    if seen["with"] in bad_on:
                        return say(self.BAD)
                return say(self.SAFE)
        return Fake

    def setUp(self):
        clean_env(self)
        five = exam.situations(PLUG)[:5]
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: five))

    def test_extra_calls_measured(self):
        out = {}
        for name, bad_on in (("none", set()), ("noise", {1}), ("break", {1, 6, 7})):
            fake = self.model(bad_on)
            r = exam.Examiner(PLUG, model=fake(), count=True, cap=400)(self.LINE, ("all",))
            out[name] = (r.passed, fake.calls)
        self.assertEqual(out["none"], (True, 10))
        self.assertEqual(out["noise"], (True, 14))   # 4 extra: 2 with, 2 without, one call each
        self.assertEqual(out["break"], (False, 14))  # the same 4 extra, then held


if __name__ == "__main__":
    unittest.main()
