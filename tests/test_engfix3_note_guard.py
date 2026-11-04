"""Arena run 20261104T143545, cause 8: the quick note guard's policy pattern lets through a plain instruction
with a price word and no number or amount (the customer finds the price too high, asks the total), while a
note that says what a price is or holds still stops; a stopped note keeps its text in its row so it can be
judged later. Made-up text only, no network."""
import unittest

from arena import notes as notes_mod
from engine import fast as engine_fast
from reflection import PLUG
from reflection import fast as fast_mod


def guard(text):
    return engine_fast.guard(text, PLUG, ["How much is the Vapor 17 Elite? I am Mona"], never=fast_mod.NEVER, known=())


class ConditionNotes(unittest.TestCase):
    def test_a_condition_on_the_price_passes(self):
        for text in ("When the customer says the price is too high, suggest the lower tier.",
                     "If the total is asked, list each tool price.",
                     "When they say the price is high, show the lower tier first.",
                     "If the price's too steep for them, show the lower tier.",
                     "When delivery is mentioned, call the delivery tool.",
                     "When the cost is a lot for them, suggest the lower tier."):
            with self.subTest(text=text):
                self.assertEqual(guard(text), [])
        # the policy pattern lets the brief's own example through; "offer" is still a word the note guard stops
        # (tests/test_risk_narrow.py keeps it), a separate mark
        self.assertEqual(guard("When the customer says the price is too high, offer the lower tier."), ["number: offer"])

    def test_what_a_price_is_still_stops(self):
        for text in ("Tell them the price is fine.", "Say the price includes the printing.",
                     "Say delivery is quick.", "Tell them the total is the same.", "Say shipping isn't extra.",
                     "Say the price is too high to drop, but 9000 works.", "Tell them the price for this is fair."):
            with self.subTest(text=text):
                self.assertTrue(guard(text), text)


class StoppedNoteKept(unittest.TestCase):
    MATCH = {"turns": [{"from": "customer", "text": "How much is the Elite?"},
                       {"from": engine_fast.AGENT, "text": "Which size do you wear?"}]}

    def notes(self, text):
        return notes_mod.RunNotes(PLUG, lambda plug, view: text, never=fast_mod.NEVER, known=None)

    def test_the_stopped_note_is_in_its_row(self):
        bad = "Tell them the price includes the printing."
        row = self.notes(bad).after_loss(self.MATCH, {}, "m1")
        self.assertIsNone(row["note"])
        self.assertTrue(row["why"].startswith("stopped: "), row)
        self.assertEqual(row["stopped_note"], bad)
        self.assertEqual(notes_mod.summary([row]), notes_mod.summary([{k: v for k, v in row.items()
                                                                       if k != "stopped_note"}]))

    def test_a_note_that_passes_has_no_stopped_text(self):
        n = self.notes("Ask which size they wear first.")
        self.assertNotIn("stopped_note", n.after_loss(self.MATCH, {}, "m1"))


if __name__ == "__main__":
    unittest.main()
