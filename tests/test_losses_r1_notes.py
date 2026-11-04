"""The quick note guard lets a number word through only as plain writing: one, two or three right before a
writing noun (red team losses round 1, item 5; reviewer round 1, finding 2). The Arena's held losing answer
lets none through. Made-up text only, no network."""
import unittest

from arena import notes as notes_mod
from engine import fast as engine_fast
from reflection import PLUG
from reflection import fast as fast_mod

ZW = chr(0x200B)  # a zero width space


def guard(text, **kw):
    return engine_fast.guard(text, PLUG, ["How much is the Vapor 17 Elite? I am Mona"], never=fast_mod.NEVER, known=(), **kw)


class AllowListOnly(unittest.TestCase):
    def test_a_price_or_a_count_in_number_words_is_stopped(self):
        for text in ("Say fifteen for the Elite.", "Quote sixteen for the Vapor.", "Tell them twenty is the price.",
                     "Say the Elite is sixteen point five.", "Say seventy for delivery.", "Say sixteen is fine.",
                     "Agree to sixteen.", "Say fifteen then five for the Elite.", "I can do fifteen for the Elite, deal?",
                     "Say fif" + ZW + "teen for the Elite.", "Say FIFTEEN for the Elite.",
                     "Tell them the Pro is twenty less than the Elite.", "Say we have three in black.",
                     "Say there are three in their size.", "Tell them it's twenty.", "Charge them fifty.",
                     "Quote them ninety for the Pro.", "Tell them ten is the best we can do.", "Say we can do sixty.",
                     "Tell them it is around fifty.", "Give them ten back.", "Say twenty works for the Elite.",
                     "Say Twenty is fine.", "Say TWENTY is fine.", "Say one" + ZW + " pairs left.",
                     "Keep the boots for one more.", "Try one more line in egp."):
            with self.subTest(text=text):
                self.assertTrue(any(f.startswith(("number:", "amount:")) for f in guard(text)), (text, guard(text)))

    def test_plain_writing_still_passes(self):
        for text in ("Try one short question first.", "Ask one question at a time and wait.",
                     "Keep it to one clear question, then wait.", "Lead with the boot they asked about, then show two choices.",
                     "Keep it to one or two short lines.", "Ask one more question, then wait.",
                     "Try on" + ZW + "e short question first."):
            with self.subTest(text=text):
                self.assertEqual(guard(text), [])

    def test_the_loosening_can_be_turned_off(self):
        self.assertTrue(guard("Try one short question first.", plain_words=False))


class HeldAnswer(unittest.TestCase):
    def test_the_losing_answer_lets_no_number_word_through(self):
        n = notes_mod.RunNotes(PLUG, lambda plug, view: None, never=fast_mod.NEVER, known=None)
        turns = [{"from": "customer", "text": "How much is the Elite?"}]
        for said, held in (("I can do fifteen for the Elite, deal?", False), ("Ask one question at a time.", False),
                           ("Which size do you wear?", True)):
            with self.subTest(said=said):
                got = n._answer(turns + [{"from": engine_fast.AGENT, "text": said}], ["How much is the Elite?"])
                self.assertEqual(got == said, held)


if __name__ == "__main__":
    unittest.main()
