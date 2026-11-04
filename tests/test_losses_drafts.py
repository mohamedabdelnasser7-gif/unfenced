"""Each draft the send check refused is kept in the match's turn record, {"draft", "check"}, for the Sales
agent (arena/match.py) and any built agent (arena/practice.py through kit/turn.py): the agent's own words and
the check's line only, never the customer's text (part C; the Arena run 20261104T120239 lost 13 matches on no
safe reply with no draft kept). Every line below is made up."""
import json
import os
import unittest
from pathlib import Path

from arena import match
from kit import send_check, turn
from tests import test_arena_practice as tp
from tests.fake_model import FakeModel, clean_env, say

CARD = json.loads((Path(__file__).resolve().parent.parent / "demo" / "personas" / "cards" / "persona-01.json")
                  .read_text(encoding="utf-8"))
ASK = "How much is the Mercurial Vapor 17 Elite?"
WRONG = "It is 99,999 EGP."
RIGHT = "The Mercurial Vapor 17 Elite is 16,500 EGP."


class SalesMatch(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_no_safe_reply_keeps_each_refused_draft(self):
        m = match.play(CARD, agent_model=FakeModel(*[say(WRONG)] * 3), customer_model=FakeModel(say(ASK)))
        t = m["turns"][0]
        self.assertEqual((m["ended"], t["outcome"]), ("no_safe_reply", "no_safe_reply"))
        self.assertEqual([r["draft"] for r in t["refused"]], [WRONG] * 3)
        self.assertTrue(all("99999" in r["check"] for r in t["refused"]))
        self.assertEqual([r["check"] for r in t["refused"]], t["checks"])
        self.assertFalse(any(ASK in json.dumps(r) for r in t["refused"]))  # the customer's text is never there
        self.assertEqual(set(t["refused"][0]), {"draft", "check"})

    def test_a_turn_that_replied_after_a_refusal_keeps_that_draft(self):
        m = match.play(CARD, agent_model=FakeModel(say(WRONG), say(RIGHT)), customer_model=FakeModel(say(ASK)),
                       max_turns=1)
        t = m["turns"][0]
        self.assertEqual((t["outcome"], t["replies"]), ("replied", [RIGHT]))
        self.assertEqual([r["draft"] for r in t["refused"]], [WRONG])

    def test_a_clean_turn_keeps_none(self):
        m = match.play(CARD, agent_model=FakeModel(say(RIGHT)), customer_model=FakeModel(say(ASK)), max_turns=1)
        self.assertEqual(m["turns"][0]["refused"], [])


class BuiltAgentMatch(tp.Base):
    def test_a_built_agents_refused_drafts_are_kept(self):
        world = tp.World(agent=lambda messages, tools: say(WRONG))
        self.main("--quick", "--json", world=world)
        m = self.matches()[0]
        t = m["turns"][0]
        self.assertEqual(t["outcome"], "no_safe_reply")
        self.assertEqual([r["draft"] for r in t["refused"]], [WRONG] * turn.MAX_FAILED_CHECKS)
        self.assertTrue(all(r["check"] for r in t["refused"]))
        self.assertFalse(any(tp.OPENING in json.dumps(r) for r in t["refused"]))

    def test_the_turn_result_carries_them(self):
        self.assertIn("refused", {f.name for f in turn.TurnResult.__dataclass_fields__.values()})


class OrderTurnShapes(unittest.TestCase):
    """Shapes an order turn writes (every no safe reply in that run came right after draft_order): an order
    quantity, delivery days and sizes pass; a stock count and a wrong amount still fail."""

    def setUp(self):
        clean_env(self)
        from kit.tools import store
        self.args = (store.price_points(), store.vocabulary(), store.size_strings())
        self.names = store.titles()

    def problems(self, reply, customer=ASK):
        a, v, sizes = self.args
        return [n for n, _ in send_check.named_problems(reply, customer, a, v, sizes, names=self.names)]

    def test_pass(self):
        for reply in ("I can place 2 pairs for your order, size 43 and size 44.", "Delivery takes 2 to 3 days.",
                      "Your order: Mercurial Vapor 17 Elite, size 43, quantity 1, 16,500 EGP.",
                      "Delivery days: 1-2. Quantity: 2.", "Sizes 42 and 43 are both in stock."):
            with self.subTest(reply=reply):
                self.assertEqual(self.problems(reply), [])

    def test_still_fail(self):
        for reply, name in (("Only 2 pairs left in size 43.", "stock"), ("We have 3 pairs in size 43.", "stock"),
                            ("Your total is 16,999 EGP.", "amounts"), ("Delivery to Cairo is 75 EGP, 2 to 3 days.",
                                                                      "amounts")):
            with self.subTest(reply=reply):
                self.assertIn(name, self.problems(reply))


if __name__ == "__main__":
    unittest.main()
