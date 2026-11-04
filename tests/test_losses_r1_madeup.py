"""Coordinator item 9 (losses round 1): arena/madeup.py batch calls on a model that spends its budget
on reasoning. On the Meta key the top-up call came back with empty content and no error, twice, and
the run stopped at setup. Now: a 16000 token budget, one more ask on an empty or unreadable answer
(counted on the cap), and a run that goes on with the customers written when they are enough. Fake
models only."""
import contextlib
import io
import json
import unittest

from arena import madeup, run
from tests.fake_model import say
from tests.test_any_agent_r2 import THREE
from tests.test_customers_shape import Base, Writer

NAME = "coffee_caption_writer"


class Flaky:
    """A Writer whose calls numbered in empty answer with empty content (no error), and in odd with
    text that is not JSON."""

    def __init__(self, inner, empty=(), odd=()):
        self.inner, self.empty, self.odd, self.n, self.tokens = inner, set(empty), set(odd), 0, []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.n += 1
        self.tokens.append(max_tokens)
        if self.n in self.empty:
            return say("")
        if self.n in self.odd:
            return say("Here are your customers, one moment")
        return self.inner.chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)


class Retry(Base):
    def calls(self, cap=50):
        return run.Calls(self.root / run.CALLS_FILE, cap)

    def write_quiet(self, model, count):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = self.write(NAME, model, count)
        return got, err.getvalue()

    def test_the_budget_is_16000(self):
        model = Flaky(Writer())
        self.write_quiet(model, 6)
        self.assertEqual(madeup.MAX_TOKENS, 16000)
        self.assertEqual(model.tokens, [16000])

    def test_empty_then_good_writes_them_all_and_counts_both_calls(self):
        calls, model = self.calls(), Flaky(Writer(), empty={1})
        (cards, written), err = self.write_quiet(calls.model(model), 6)
        self.assertEqual((written, len(cards), model.n, calls.taken), (True, 6, 2, 2))
        self.assertEqual(json.loads((self.root / run.CALLS_FILE).read_text())["calls"], 2)
        self.assertEqual(err, "")

    def test_unreadable_then_good_is_asked_once_more(self):
        model = Flaky(Writer(), odd={1})
        (cards, _), _ = self.write_quiet(model, 6)
        self.assertEqual((len(cards), model.n), (6, 2))

    def test_the_top_up_empty_twice_goes_on_with_the_first_batch(self):
        # the case seen live: batch 1 has a repeat, its top-up call (told the people written) is empty twice
        calls = self.calls()
        model = Flaky(Writer(same=lambda c, i: 1 if (c, i) == (1, 1) else None), empty={2, 3})
        (cards, written), err = self.write_quiet(calls.model(model), 10)
        self.assertEqual((written, len(cards), model.n, calls.taken), (True, 9, 3, 3))
        self.assertIn("Note: 9 of 10 practice customers were written", err)
        self.assertIn("1 more could not be read, asked twice", err)
        self.assertIn("next run writes the rest", err)
        self.assertEqual(len(self.files(NAME)), 9)
        again = Writer()
        again.n = 100
        (cards, written), err = self.write_quiet(again, 10)
        self.assertEqual((written, len(cards), len(again.asks), err), (True, 10, 1, ""))

    def test_a_second_batch_empty_twice_goes_on_with_the_first(self):
        model = Flaky(Writer(), empty={2, 3})
        (cards, _), err = self.write_quiet(model, 20)
        self.assertEqual((len(cards), model.n), (10, 3))
        self.assertIn("Note: 10 of 20 practice customers were written", err)
        self.assertIn("10 more could not be read", err)

    def test_empty_twice_with_too_few_still_stops_with_the_same_line(self):
        calls, model = self.calls(), Flaky(Writer(), empty={1, 2})
        with self.assertRaises(madeup.Unreadable) as got:
            self.write_quiet(calls.model(model), 6)
        self.assertEqual(str(got.exception), "the practice customers the model wrote could not be read")
        self.assertEqual((model.n, calls.taken), (2, 2))
        self.assertFalse((self.folders[NAME] / madeup.FOLDER).exists())

    def test_one_customer_written_is_too_few(self):
        # batch 1 keeps one card, batch 2 is empty twice: one card is not enough for a run
        model, unread = Flaky(Writer(), empty={2, 3}), []
        keep_one = lambda i, kind, one: (madeup.card_of(i, kind, one, NAME, "src", 11)  # noqa: E731
                                         if one.get("want") == ["want number 1"] else None)
        with self.assertRaises(madeup.Unreadable) as got:
            madeup.write_many(THREE[NAME]["card"], model, ["easy"] * 11, [], [], system=madeup.SYSTEM,
                              ask_of=lambda b: {"kinds": list(b)}, build=keep_one, unread=unread)
        self.assertEqual((str(got.exception), model.n, len(unread)), (madeup.UNREAD, 3, 1))

    def test_the_cap_on_the_second_ask_still_saves_and_says_so(self):
        calls = self.calls(2)
        model = Flaky(Writer(), empty={2})
        with self.assertRaises(run.CapReached) as got:
            self.write_quiet(calls.model(model), 20)
        self.assertIn("10 of 20 practice customers were written and saved", str(got.exception))


if __name__ == "__main__":
    unittest.main()
