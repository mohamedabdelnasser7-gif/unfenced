"""Engine fix B (2026-11-03): one noisy answer never holds a lesson alone. A safety check that newly
fails with the line is voted over that situation answered twice more with it and twice more without
(engine/exam.py recheck, called by reflection/exam.py Examiner in the scoped and the full exam). At most
RECHECK_MAX situations a lesson, stopping at the first confirmed break, inside the exam's cap; a rerun
answer that raised, or that gave no words, counts against the lesson. The vote is for the lesson in hand
only: no voted row before is kept for the next lessons (red team engfix round 1, finding 5). Fake models
only, no network."""
import unittest
from unittest import mock

from engine import exam as engine_exam
from reflection import PLUG
from reflection import exam
from tests.fake_model import call, clean_env, say

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


class SitEmpty(unittest.TestCase):
    """engine/exam.py sit with empty_raises: an answer that gave no words is a row that raised."""

    SITS = [{"id": 1, "name": "s1", "part": "guard"}]
    CHECKS = {"amounts": lambda s, did: ""}  # passes on anything, so only the flag can fail the row

    def answer(self, s, lesson):
        return {"calls": 2, engine_exam.EMPTY: True, "reply": ""}

    def test_empty_raises_makes_it_an_answer_row(self):
        r = engine_exam.sit(self.SITS, self.answer, self.CHECKS, ["amounts"], empty_raises=True)
        self.assertEqual((r.rows[0].passed, r.rows[0].check, r.rows[0].why),
                         (False, engine_exam.ANSWER, "the answer gave no words"))
        self.assertEqual(r.calls, 2)
        self.assertFalse(r.passed)

    def test_without_the_flag_the_checks_run_as_before(self):
        r = engine_exam.sit(self.SITS, self.answer, self.CHECKS, ["amounts"])
        self.assertTrue(r.rows[0].passed)
        self.assertTrue(r.passed)
        failing = {"amounts": lambda s, did: "an amount"}
        r = engine_exam.sit(self.SITS, self.answer, failing, ["amounts"])
        self.assertEqual((r.rows[0].check, r.rows[0].why), ("amounts", "an amount"))

    def test_an_answer_with_words_is_checked_with_the_flag(self):
        r = engine_exam.sit(self.SITS, lambda s, les: {"calls": 1, engine_exam.EMPTY: False}, self.CHECKS,
                            ["amounts"], empty_raises=True)
        self.assertTrue(r.rows[0].passed)


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

    def test_another_safety_check_the_reruns_break_holds_it(self):
        """Review engfix round 1, finding 3 (p3a): the first answer fails amounts, both reruns with the line
        fail order, the ones without pass: held on order, with no more answers."""
        again = Script(w1=[row(1, "order"), row(1, "order")], o1=[row(1), row(1)])
        res, a, _, _ = vote([row(1, "amounts")], [row(1)], again)
        self.assertFalse(res.passed)
        self.assertEqual((res.blocked.situation, res.blocked.check), (1, "order"))
        self.assertEqual([c for c, _ in a[0].fails], ["order"])  # amounts came off as noise
        self.assertEqual(len(again.asked), 4)

    def test_another_check_counts_raised_reruns_against_the_lesson(self):
        # without the line, answers that raised count as passing there: held on order
        again = Script(w1=[row(1, "order"), row(1, "order")], o1=[raised(1), RuntimeError("down")])
        res = vote([row(1, "amounts")], [row(1)], again)[0]
        self.assertFalse(res.passed)
        self.assertEqual(res.blocked.check, "order")
        # with the line, an answer that raised counts as failing order too, so the row names it
        again = Script(w1=[row(1, "order"), raised(1)], o1=[row(1), row(1)])
        res, a, _, _ = vote([row(1, "amounts")], [row(1)], again)
        self.assertFalse(res.passed)
        self.assertEqual([c for c, _ in a[0].fails], ["amounts", "order"])

    def test_another_check_is_not_held_when_it_is_not_new(self):
        cases = {
            "fails without in the majority too": Script(w1=[row(1, "order"), row(1, "order")],
                                                        o1=[row(1, "order"), row(1, "order")]),
            "fails with in the minority": Script(w1=[row(1, "order"), row(1)], o1=[row(1), row(1)]),
            "a style check": Script(w1=[row(1, "tone"), row(1, "tone")], o1=[row(1), row(1)]),
        }
        for name, again in cases.items():
            with self.subTest(name):
                res, a, _, _ = vote([row(1, "amounts")], [row(1)], again)
                self.assertTrue(res.passed)
                self.assertEqual(len(again.asked), 4)
        # the row before fails order already: its verdict stands (not new), and it confirms no break, so the
        # next disputed situation is still rechecked (noise there too)
        again = Script(w1=[row(1, "order"), row(1, "order")], o1=[row(1), row(1)],
                       w2=[row(2), row(2)], o2=[row(2), row(2)])
        res, a, _, _ = vote([row(1, "amounts"), row(2, "amounts")], [row(1, "order"), row(2)], again)
        self.assertTrue(res.passed)
        self.assertEqual({sid for sid, _ in again.asked}, {1, 2})
        self.assertTrue(a[0].passed)

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

    def fake_run(self, plug, model, *, kept=None, lesson=None, stop_at_first=False, sits=None, safety=None,
                 empty_raises=False):
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
        self.assertEqual(self.runs[8:], [(False, 2), (False, 2), (True, 2), (True, 2)])  # the vote, then the recheck

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
        # 8, then the baseline vote (2 answers; room for 8 calls), then the recheck (2 with; room for 8 calls)
        for cap, rechecked in ((8 + 2 + 7, False), (8 + 2 + 8, True)):
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
        self.assertEqual(r.calls, m.n)  # every model call of the lesson, the reruns too
        # room for two situations (8 calls each); the baseline vote's two answers serve the recheck's side
        # without the line, so its worst case is the two answers with it, and that fits
        tm = Counter()
        tight = self.examiner(tm, scope=True, cap=16)
        self.with_answers.clear()
        self.assertTrue(tight("Greet them warmly.", ("asking",)).passed)
        self.assertLessEqual(tm.n, 16)

    def flaky_without(self, state):
        """Every lesson breaks "amounts" on situation 2; the single reruns without the line fail there too
        while state["flaky"] holds (a noisy run on the kept lessons)."""
        self.always = True
        real = self.fake_run

        def run(plug, model, *, kept=None, lesson=None, sits=None, **kw):
            got = real(plug, model, kept=kept, lesson=lesson, sits=sits)
            if state["flaky"] and lesson is None and len(sits) == 1 and sits[0]["id"] == 2:
                return Result(True, [row(2, "amounts")], calls=1)
            return got
        exam.run.side_effect = run

    def test_a_voted_row_before_is_not_kept_for_the_next_lesson_scoped(self):
        state = {"flaky": True}
        self.flaky_without(state)
        m = Counter()
        ex = self.examiner(m, scope=True, cap=60)
        self.assertTrue(ex("Greet them warmly.", ("asking",)).passed)  # it fails without the line too
        # the kept answers are answers, never a row a vote changed: the first as answered, then the vote's two
        self.assertEqual([[c for c, _ in r.fails] for r in ex._rows[()][2]], [[], ["amounts"], ["amounts"]])
        before = m.n
        self.assertTrue(ex("Greet them kindly.", ("asking",)).passed)
        self.assertEqual(m.n - before, 4)  # the kept answers reused, no vote or recheck to pay again

    def test_a_voted_row_before_is_not_kept_for_the_next_lesson_full(self):
        state = {"flaky": True}
        self.flaky_without(state)
        m = Counter()
        ex = self.examiner(m)
        self.assertTrue(ex("Greet them warmly.", ("all",)).passed)
        self.assertEqual([[c for c, _ in r.fails] for r in ex._rows[()][2]], [[], ["amounts"], ["amounts"]])
        before = m.n
        self.assertTrue(ex("Greet them kindly.", ("all",)).passed)
        self.assertEqual(m.n - before, 4)


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


class EmptyReruns(unittest.TestCase):
    """Review engfix round 1, p2: the Sales real answer path, one situation. With the line every answer
    calls the store tool, then invents an amount; the reruns without it give no words (a reply cut off,
    a turn spent on tools). They count like answers that raised, so they never excuse the lesson."""

    BAD = "الجزمة بـ 9,999 جنيه."
    SAFE = "أهلا بيك! تحب تسأل عن ايه؟"
    LINE = "Greet them warmly before anything else."

    def setUp(self):
        clean_env(self)
        one = exam.situations(PLUG)[:1]
        self.one_id = one[0]["id"]
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: one))

    def fake(self, mode):
        test, seen = self, {"without": 0}

        class Fake:
            def chat(self_, messages, tools=None, **kw):
                if any(test.LINE in str(m.get("content") or "") for m in messages):
                    if messages[-1].get("role") != "tool":
                        return call("store", query="boots")
                    return say(test.BAD)
                seen["without"] += 1
                if mode == "empty" and seen["without"] > 1:
                    return say("")
                if mode == "blank" and seen["without"] > 1:  # whitespace only: no words either
                    return say("  \n\t ")
                return say(test.SAFE)
        return Fake()

    def go(self, mode):
        ex = exam.Examiner(PLUG, model=self.fake(mode), count=True, cap=400)
        return ex, ex(self.LINE, ("all",))

    def test_reruns_with_no_words_do_not_pass_it(self):
        for mode in ("safe", "empty", "blank"):
            with self.subTest(mode=mode):
                _, r = self.go(mode)
                self.assertFalse(r.passed)
                self.assertEqual(r.blocked.check, "amounts")

    def test_a_whitespace_reply_from_the_loop_is_empty(self):
        # the model gave no words (every call a tool call), and the loop's own reply is only whitespace
        from types import SimpleNamespace

        class NoCall:
            def chat(self_, *a, **kw):
                raise AssertionError("not called")
        self.enterContext(mock.patch.object(exam.loop, "turn", lambda *a, **kw: SimpleNamespace(reply=" \n\t ")))
        did = exam.answer(exam.situations(PLUG)[0], None, model=NoCall())
        self.assertTrue(did[engine_exam.EMPTY])

    def test_the_next_lesson_is_held_too(self):
        ex, r = self.go("empty")
        self.assertFalse(r.passed)
        kept = ex._rows[()][self.one_id]
        self.assertEqual(len(kept), 1)  # the empty answers are not kept
        self.assertNotIn("amounts", [c for c, _ in kept[0].fails])  # as it was answered
        r2 = ex(self.LINE + " Always.", ("all",))
        self.assertFalse(r2.passed)
        self.assertEqual(r2.blocked.check, "amounts")



class EmptyFirstWithout(unittest.TestCase):
    """Review engfix round 2, finding 1 (probe p4): the first run on the kept lessons gives no words on
    a situation. It counts like an answer that raised, not as failing amounts there, so a lesson that
    invents an amount on that situation is still new and held; and in the full exam that run is not
    kept, so the next lesson asks again and is held too. Scoped and full."""

    BAD, SAFE, LINE = EmptyReruns.BAD, EmptyReruns.SAFE, EmptyReruns.LINE

    def setUp(self):
        clean_env(self)
        self.one = exam.situations(PLUG)[:1]
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: self.one))

    def fake(self, first, log):
        test, seen = self, {"without": 0}

        class Fake:
            def chat(self_, messages, tools=None, **kw):
                if any(test.LINE in str(m.get("content") or "") for m in messages):
                    if messages[-1].get("role") != "tool":
                        return call("store", query="boots")
                    log.append("with")
                    return say(test.BAD)
                seen["without"] += 1
                log.append("without")
                return say(first if seen["without"] == 1 else test.SAFE)
        return Fake()

    def test_both_lessons_held(self):
        sid = self.one[0]["id"]
        for scope in (False, True):
            for first in ("", "   "):
                with self.subTest(scope=scope, first=repr(first)):
                    log = []
                    ex = exam.Examiner(PLUG, model=self.fake(first, log), count=True, scope=scope, cap=400)
                    r1 = ex(self.LINE, ("all",))
                    self.assertFalse(r1.passed)
                    self.assertEqual(r1.blocked.check, "amounts")
                    self.assertNotIn(sid, ex._rows.get((), {}))  # the empty answer is not kept
                    r2 = ex(self.LINE + " Always.", ("all",))
                    self.assertFalse(r2.passed)
                    self.assertEqual(r2.blocked.check, "amounts")
                    before = ex._rows[()][sid][0]
                    self.assertNotEqual(before.check, engine_exam.ANSWER)
                    self.assertNotIn("amounts", [c for c, _ in before.fails])


if __name__ == "__main__":
    unittest.main()
