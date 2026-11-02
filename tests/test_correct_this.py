"""Correct this: a correction sent from beside the reply the agent lost a practice match on
(reflection/pages.py correct_this), the same hotfix as the box on the agent's page, and the page's
Sales exam scoped so it answers fast (reflection/night.py sales_exam scope). No model call."""
import unittest
from pathlib import Path

from engine import plug as plug_mod
from engine import risk
from kit.db import Db
from reflection import morning as mo
from reflection import night
from reflection import pages

ROOT = Path(__file__).resolve().parent.parent
REPLY = "This one is 900 pounds, want it?"


def run_with(lost):
    return {"sales": {"file": "arena-sales-1.json", "at": 1_793_000_000.0, "line": "", "lost": lost,
                      "rounds": [], "kind": "arena_rounds", "gate_won": None, "gate_played": None}}, []


class CorrectThis(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        self.m = mo.Morning(self.db, plugs, judge=lambda *a: risk.LOW)
        self.p = pages.Pages(self.m)

    def build(self, lost, token="t"):
        self.m.read_arena = lambda: run_with(lost)
        return self.p.get("/new/build", {"agent": ["sales"]}, token)

    def test_each_lost_reply_has_correct_this_back_to_the_agent_page(self):
        page = self.build([{"card": "c1", "why": "it named a price with no value", "turn": 1, "who": "agent",
                            "text": REPLY}])
        self.assertIn("Correct this", page)
        form = page.split('class="fix"')[1].split("</details>")[0]
        self.assertIn('action="/correct"', form)
        self.assertIn('name="agent" value="sales"', form)
        self.assertIn('name="back" value="/agents/sales"', form)
        self.assertIn('name="token" value="t"', form)
        self.assertEqual(form.count('name="back"'), 1)

    def test_no_correct_this_without_a_token_or_a_quoted_reply(self):
        lost = [{"card": "c1", "why": "it went quiet", "turn": None, "who": "", "text": ""}]
        self.assertNotIn("Correct this", self.build(lost))
        reply = [{"card": "c1", "why": "x", "turn": 1, "who": "agent", "text": REPLY}]
        self.assertNotIn("Correct this", self.build(reply, token=None))

    def test_the_answer_returns_to_the_agent_page(self):
        self.assertEqual(self.p.back("/agents/sales"), "/agents/sales")


class PageExamScoped(unittest.TestCase):
    def test_page_exam_is_scoped_and_the_night_full(self):
        plug = plug_mod.load(ROOT / "sales" / "plug.json")
        page = night.sales_exam(plug, scope=True)(None)
        self.assertTrue(page.scope)
        from arena import rounds
        self.assertEqual(page.cap, rounds.EXAM_CAP)
        nightly = night.sales_exam(plug)(None)
        self.assertFalse(nightly.scope)
        self.assertIsNone(nightly.cap)


if __name__ == "__main__":
    unittest.main()
