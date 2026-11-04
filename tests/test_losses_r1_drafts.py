"""A refused draft that quotes the customer (3 or more of their words in a row) is stored as "(held back: it
quotes the customer)" in the Arena's turn record, for the Sales agent and any built agent, whether the turn
replied or not; a draft that only names the store's product is kept as written (red team losses round 1,
item 8). Every line below is made up."""
import json
import unittest
from pathlib import Path

from arena import match
from kit import turn as engine_fast  # held_draft and HELD_DRAFT live in kit/turn.py
from tests import test_arena_practice as tp
from tests.fake_model import FakeModel, clean_env, say

CARD = json.loads((Path(__file__).resolve().parent.parent / "demo" / "personas" / "cards" / "persona-01.json")
                  .read_text(encoding="utf-8"))
ASK = "How much is the Mercurial Vapor 17 Elite? My name is Mona Adel, 0101 234 5678"
QUOTE = f'You wrote: "{ASK}". It is 99,999 EGP.'
NAMED = "The Mercurial Vapor 17 Elite is 99,999 EGP."
RIGHT = "The Mercurial Vapor 17 Elite is 16,500 EGP."


class HeldDraft(unittest.TestCase):
    def test_a_quote_is_held_and_store_words_are_not(self):
        self.assertEqual(engine_fast.held_draft("Sure, Mona Adel from Giza, noted.", ["I am Mona Adel from Giza"]), engine_fast.HELD_DRAFT)
        self.assertEqual(engine_fast.held_draft("It is the mercurial vapor 17.", ["Is the Mercurial Vapor 17 here?"],
                                                ("Nike Mercurial Vapor 17",)), "It is the mercurial vapor 17.")
        self.assertEqual(engine_fast.held_draft("It is the mercurial vapor 17.", ["Is the Mercurial Vapor 17 here?"]),
                         engine_fast.HELD_DRAFT)  # with no own words the run counts
        self.assertEqual(engine_fast.held_draft("Two words only", ["two words"]), "Two words only")
        self.assertEqual(engine_fast.held_draft(None, ["x y z"]), "")


class SalesMatch(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_a_quoting_draft_is_held_back(self):
        m = match.play(CARD, agent_model=FakeModel(*[say(QUOTE)] * 3), customer_model=FakeModel(say(ASK)))
        t = m["turns"][0]
        self.assertEqual(m["ended"], "no_safe_reply")
        self.assertEqual([r["draft"] for r in t["refused"]], [engine_fast.HELD_DRAFT] * 3)
        self.assertFalse(any("Mona" in r["draft"] for r in t["refused"]))

    def test_a_draft_that_names_the_product_is_kept_on_a_replied_turn(self):
        m = match.play(CARD, agent_model=FakeModel(say(NAMED), say(RIGHT)), customer_model=FakeModel(say(ASK)),
                       max_turns=1)
        t = m["turns"][0]
        self.assertEqual((t["outcome"], t["replies"]), ("replied", [RIGHT]))
        self.assertEqual([r["draft"] for r in t["refused"]], [NAMED])

    def test_a_quote_on_a_replied_turn_is_held_back(self):
        m = match.play(CARD, agent_model=FakeModel(say(QUOTE), say(RIGHT)), customer_model=FakeModel(say(ASK)),
                       max_turns=1)
        self.assertEqual([r["draft"] for r in m["turns"][0]["refused"]], [engine_fast.HELD_DRAFT])


class BuiltAgentMatch(tp.Base):
    def test_a_built_agents_quoting_draft_is_held_back(self):
        quote = f'You asked "{tp.OPENING}" and we have 999,999 EGP boots.'
        world = tp.World(agent=lambda messages, tools: say(quote))
        self.main("--quick", "--json", world=world)
        t = self.matches()[0]["turns"][0]
        self.assertEqual(t["outcome"], "no_safe_reply")
        self.assertTrue(t["refused"])
        self.assertEqual({r["draft"] for r in t["refused"]}, {engine_fast.HELD_DRAFT})


if __name__ == "__main__":
    unittest.main()
