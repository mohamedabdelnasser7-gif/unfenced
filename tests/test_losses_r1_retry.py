"""Coordinator item 9, the general part (losses round 1): kit/model.py asks an empty answer (or, with
whole, a cut one) once more with a larger budget, and every wrapper that counts model calls toward a
cap counts that second ask, or refuses it past the cap. A fake transport only, no network."""
import json
import secrets
import tempfile
import unittest
from pathlib import Path

from arena import recipe as recipe_mod
from arena import rounds, run
from arena import tag as tag_mod
from kit import model as kit_model
from kit.limits import Metered as LimitsMetered
from reflection import exam as exam_mod
from reflection import fast as fast_mod
from reflection import turn_exam
from tests.test_judge_keys import BASETEN_URL, HI, Transport, env_with, ok

TOOL = json.dumps({"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
    {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
    "finish_reason": "tool_calls"}]}).encode()


def budgets(t):
    return [json.loads(r.data)["max_tokens"] for r in t.seen]


class Base(unittest.TestCase):
    def setUp(self):
        env_with(self, BASETEN_API_KEY=secrets.token_urlsafe(24))

    def model(self, *steps):
        t = Transport(baseten=list(steps))
        return kit_model.Model(opener=t), t


class Retry(Base):
    def test_empty_then_good_returns_the_second_with_a_larger_budget(self):
        m, t = self.model(ok(""), ok("hello"))
        with self.assertLogs("kit.model", level="WARNING") as logs:
            got = m.chat(HI, max_tokens=1500)
        self.assertEqual(got["content"], "hello")
        self.assertEqual((t.hosts(), budgets(t)), ([BASETEN_URL] * 2, [1500, 4000]))
        self.assertIn("an empty answer at 1500 tokens; asked once more at 4000", logs.output[0])
        self.assertEqual(m.last_route, "Baseten")

    def test_null_and_spaces_are_empty_too(self):
        null = json.dumps({"choices": [{"message": {"role": "assistant", "content": None}}]}).encode()
        for first in (null, ok("  \n ")):
            with self.subTest(first=first):
                m, t = self.model(first, ok("hello"))
                with self.assertLogs("kit.model", level="WARNING"):
                    self.assertEqual(m.chat(HI)["content"], "hello")
                self.assertEqual(len(t.seen), 2)

    def test_empty_twice_is_asked_only_twice_and_returned_as_it_was(self):
        m, t = self.model(ok(""), ok(""), ok("never asked"))
        with self.assertLogs("kit.model", level="WARNING"):
            got = m.chat(HI, max_tokens=800)
        self.assertEqual((got["content"], budgets(t)), ("", [800, 4000]))

    def test_a_tool_call_with_no_words_and_a_plain_answer_are_not_asked_again(self):
        for first in (TOOL, ok("hello")):
            with self.subTest(first=first):
                m, t = self.model(first, ok("second"))
                m.chat(HI)
                self.assertEqual(len(t.seen), 1)

    def test_whole_cut_then_good_and_cut_twice_named_at_the_second_budget(self):
        m, t = self.model(ok("half", reason="length"), ok("whole"))
        with self.assertLogs("kit.model", level="WARNING") as logs:
            self.assertEqual(m.chat(HI, max_tokens=3000, whole=True)["content"], "whole")
        self.assertEqual(budgets(t), [3000, 6000])
        self.assertIn("a cut off answer at 3000", logs.output[0])
        m, t = self.model(ok("half", reason="length"), ok("half", reason="length"))
        with self.assertRaises(kit_model.ModelError) as e, self.assertLogs("kit.model", level="WARNING"):
            m.chat(HI, max_tokens=3000, whole=True)
        self.assertEqual(str(e.exception), "Baseten answer was cut off at 6000 tokens")

    def test_a_cut_answer_without_whole_is_still_an_answer(self):
        m, t = self.model(ok("half", reason="length"), ok("second"))
        self.assertEqual(m.chat(HI)["content"], "half")
        self.assertEqual(len(t.seen), 1)

    def test_the_budgets(self):
        self.assertEqual([kit_model.retry_tokens(n) for n in (800, 1500, 2000, 3000, 4000, 8000, 12000, 16000, 20000)],
                         [4000, 4000, 4000, 6000, 8000, 16000, 16000, None, None])
        m, t = self.model(ok(""), ok("never asked"))
        self.assertEqual(m.chat(HI, max_tokens=16000)["content"], "")  # arena/madeup.py asks again itself
        self.assertEqual(len(t.seen), 1)

    def test_other_failures_are_not_asked_again(self):
        m, t = self.model(b"<html>", ok("never asked"))
        with self.assertRaises(kit_model.ModelError):
            m.chat(HI, whole=True)
        self.assertEqual(len(t.seen), 1)


class Counted(Base):
    """Every wrapper that counts model calls counts the second ask, and refuses it past its cap."""

    def setUp(self):
        super().setUp()
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    def test_the_run_cap_counts_both_and_stops_the_second_at_the_cap(self):
        calls = run.Calls(self.root / run.CALLS_FILE, 5)
        m, t = self.model(ok(""), ok("hello"))
        with self.assertLogs("kit.model", level="WARNING"):
            self.assertEqual(calls.model(m).chat(HI)["content"], "hello")
        self.assertEqual((calls.taken, json.loads((self.root / run.CALLS_FILE).read_text())["calls"]), (2, 2))
        calls = run.Calls(self.root / "other.json", 1)
        m, t = self.model(ok(""), ok("hello"))
        with self.assertRaises(run.CapReached):
            calls.model(m).chat(HI)
        self.assertEqual((len(t.seen), calls.taken, calls.reached), (1, 1, True))

    def test_the_full_exam_budget(self):
        m, t = self.model(ok(""), ok("hello"))
        b = rounds._Budget(m, 2)
        with self.assertLogs("kit.model", level="WARNING"):
            b.chat(HI)
        self.assertEqual((b.left, b.over), (0, False))
        m, t = self.model(ok(""), ok("hello"))
        b = rounds._Budget(m, 1)
        with self.assertRaises(rounds.FullCapReached):
            b.chat(HI)
        self.assertEqual((b.over, len(t.seen)), (True, 1))

    def test_the_exam_situation_cap(self):
        m, t = self.model(ok(""), ok("hello"))
        e = exam_mod.ExamModel(m)
        with self.assertLogs("kit.model", level="WARNING"):
            e.chat(HI)
        self.assertEqual((e.calls, e.first, e.error), (2, "hello", None))
        m, t = self.model(ok(""), ok("hello"))
        e = exam_mod.ExamModel(m, cap=1)
        with self.assertRaises(kit_model.ModelError):
            e.chat(HI)
        self.assertIsInstance(e.error, kit_model.ModelError)
        self.assertEqual((e.calls, len(t.seen)), (1, 1))

    def test_the_exam_counter_and_its_parent(self):
        m, t = self.model(ok(""), ok("hello"))
        parent = exam_mod._Counted(None)
        c = exam_mod._Counted(m, parent=parent)
        with self.assertLogs("kit.model", level="WARNING"):
            c.chat(HI)
        self.assertEqual((c.calls, parent.calls), (2, 2))

    def test_the_turn_exam_cap(self):
        m, t = self.model(ok(""), ok("hello"))
        c = turn_exam.Capped(m)
        with self.assertLogs("kit.model", level="WARNING"):
            c.chat(HI)
        self.assertEqual(c.calls, 2)
        m, t = self.model(ok(""), ok("hello"))
        c = turn_exam.Capped(m, cap=1)
        with self.assertRaises(kit_model.ModelError):
            c.chat(HI)
        self.assertEqual(len(t.seen), 1)

    def test_the_customer_limits_and_the_fast_notes_limit(self):
        class Limits:
            def __init__(self, room):
                self.taken, self.room = [], room

            def take(self, who):
                if len(self.taken) >= self.room:
                    raise fast_mod.limits_mod.OverLimit("day")
                self.taken.append(who)

        m, t = self.model(ok(""), ok("hello"))
        lim = Limits(5)
        with self.assertLogs("kit.model", level="WARNING"):
            LimitsMetered(m, lim, "c1").chat(HI)
        self.assertEqual(lim.taken, ["c1", "c1"])
        m, t = self.model(ok(""), ok("hello"))
        lim = Limits(1)
        with self.assertRaises(fast_mod.limits_mod.OverLimit):
            LimitsMetered(m, lim, "c1").chat(HI)
        self.assertEqual(len(t.seen), 1)
        m, t = self.model(ok(""), ok('{"note": null}'))
        lim = Limits(5)
        with self.assertLogs("kit.model", level="WARNING"):
            fast_mod.Metered(lambda plug, view: m.chat(HI), lim)(None, None)
        self.assertEqual(lim.taken, [fast_mod.LIMIT_KEY] * 2)
        m, t = self.model(ok(""), ok('{"note": null}'))
        with self.assertRaises(fast_mod.PartError):
            fast_mod.Metered(lambda plug, view: m.chat(HI), Limits(1))(None, None)
        self.assertEqual(len(t.seen), 1)

    def test_the_tagger_cap(self):
        m, t = self.model(ok(""), ok("[]"))
        tg = tag_mod.Tagger(model=m, cap=5, recipe=recipe_mod.load(recipe_mod.EXAMPLE))
        with self.assertLogs("kit.model", level="WARNING"):
            tg([{"from": "customer", "text": "hi"}], "left")
        self.assertEqual((tg.calls, len(t.seen)), (2, 2))
        m, t = self.model(ok(""), ok("[]"))
        tg = tag_mod.Tagger(model=m, cap=1, recipe=recipe_mod.load(recipe_mod.EXAMPLE))
        self.assertIsNone(tg([{"from": "customer", "text": "hi"}], "left"))
        self.assertEqual((tg.calls, tg.failed, len(t.seen)), (1, 1, 1))

    def test_nested_counters_each_count_once(self):
        calls = run.Calls(self.root / run.CALLS_FILE, 5)
        m, t = self.model(ok(""), ok("hello"))
        b = rounds._Budget(m, 3)
        with self.assertLogs("kit.model", level="WARNING"):
            calls.model(b).chat(HI)
        self.assertEqual((calls.taken, b.left, len(t.seen)), (2, 1, 2))

    def test_no_counter_left_behind(self):
        calls = run.Calls(self.root / run.CALLS_FILE, 5)
        m, _ = self.model(ok("hello"))
        calls.model(m).chat(HI)
        self.assertEqual(kit_model._COUNTERS.get(), ())
        m, _ = self.model(ok(""), ok("hello"))
        with self.assertLogs("kit.model", level="WARNING"):
            m.chat(HI)  # no wrapper: asked again, nothing to count
        self.assertEqual(calls.taken, 1)


if __name__ == "__main__":
    unittest.main()
