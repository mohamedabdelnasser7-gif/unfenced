"""The made-up customer's generic prompt (Arena run 20261104T143545, cause 1): the card's buy triggers
read as "any one of these is enough", a direct question (area, size) gets an answer, and a win played
with the generic prompt before this change is still rerun with the prompt it was played with."""
import random
import tempfile
import unittest
from pathlib import Path

from arena import gate, match, run
from tests.fake_model import Buyer, Seller, clean_env
from tests.test_arena_gate import LESSON, exam, past

# the generic prompt's fingerprint before this change, as saved with the matches played with it
OLD_SHA = "1f6fbfdf61bb29cc68aee491678737ccbcb814078aad40e7d0a520ab617ca7fb"
TRIGGERS = ["lower price or discount offer", "faster delivery", "a clear delivery time"]


def old():
    """The past generic prompt, found by its saved fingerprint."""
    text = match.KNOWN_PROMPTS[OLD_SHA]
    assert match.prompt_sha(text) == OLD_SHA
    return text


def filled(prompt, card, defaults=None):
    return match.fill(prompt, dict({"worry": "price"}, **card), random.Random(1), defaults)[0]


class Triggers(unittest.TestCase):
    def test_more_than_one_trigger_reads_as_any_one_is_enough(self):
        text = filled(match.GENERIC_PROMPT, {"buy_trigger": TRIGGERS})
        self.assertIn("You buy when you get one of these (any one of these is enough): lower price or discount "
                      "offer; faster delivery; a clear delivery time.", text)
        self.assertNotIn("You buy only when", text)
        self.assertNotIn("$buy_any", text)

    def test_one_trigger_reads_plain(self):
        self.assertIn("You buy when you get a clear answer. ", filled(match.GENERIC_PROMPT, {"buy_trigger": ["a clear answer"]}))

    def test_no_trigger_takes_the_default(self):
        self.assertIn("You buy when you get a size chart. ",
                      filled(match.GENERIC_PROMPT, {"buy_trigger": []}, {"buy_trigger": "a size chart"}))
        self.assertIn("You buy when you get a clear answer. ", filled(match.GENERIC_PROMPT, {"buy_trigger": ["", "  "]}))

    def test_a_direct_question_gets_an_answer_before_deciding(self):
        text = filled(match.GENERIC_PROMPT, {"buy_trigger": TRIGGERS})
        self.assertIn("When the shop asks you a direct question, such as your governorate or area or your size, "
                      "answer it in your next message with a made-up answer that fits you, even before you decide "
                      "to buy.", text)

    def test_the_past_prompt_and_a_private_file_fill_as_before(self):
        self.assertIn("You buy only when you get lower price or discount offer, faster delivery, a clear delivery "
                      "time. ", filled(old(), {"buy_trigger": TRIGGERS}))
        self.assertNotIn("any one of these", filled(old(), {"buy_trigger": TRIGGERS}))
        self.assertEqual(filled("Buy on $buy_trigger.", {"buy_trigger": TRIGGERS}),
                         "Buy on lower price or discount offer, faster delivery, a clear delivery time.")


class PastPrompt(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def test_the_fingerprint_changed_and_both_are_known(self):
        self.assertNotEqual(match.GENERIC_SHA, OLD_SHA)
        self.assertEqual(match.KNOWN_PROMPTS, {match.GENERIC_SHA: match.GENERIC_PROMPT, OLD_SHA: old()})
        self.assertEqual(gate._prompt_of({"prompt_sha": OLD_SHA, "prompt_file": None}), old())
        self.assertEqual(gate._prompt_of({"prompt_sha": match.GENERIC_SHA, "prompt_file": None}), match.GENERIC_PROMPT)
        self.assertIsNone(gate._prompt_of({"prompt_sha": OLD_SHA, "prompt_file": None}, prompts={}))

    def test_a_win_played_with_the_past_prompt_is_rerun_with_it(self):
        win = dict(past(), prompt_sha=OLD_SHA)
        reruns, skipped = gate.pick([win])
        self.assertEqual((reruns, skipped), ([(win, old())], []))
        customer = Buyer()
        r = gate.Gate(exam(True), wins=[win], agent_model=Seller(), customer_model=customer,
                      calls=run.Calls(self.dir / "calls.json", 300, day="2026-10-30"))(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual([row.part for row in r.rows[1:]], [gate.PART])
        system = customer.calls[0]["messages"][0]["content"]
        self.assertIn("You buy only when you get", system)
        self.assertNotIn("direct question", system)


if __name__ == "__main__":
    unittest.main()
