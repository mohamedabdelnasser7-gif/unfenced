"""Step 1: each agent declares its work in one plug file; the engine keeps no list of its own."""
import copy
import re
import unittest
from pathlib import Path

from engine import plug
from sales import stages
from kit.db import Db
from kit.tools import TOOLS
from reflection import PLUG
from reflection.results import Results
from tests import plugs

ROOT = Path(__file__).resolve().parent.parent
TODAYS_11 = {"replied", "check_failed", "no_safe_reply", "limited", "model_error", "turn_failed",
             "person_replied", "order_drafted", "order_created", "delivered", "refused"}
GONE = ("handed_off", "handoff_failed", "handed_back", "relay_failed")  # the hand-off left (DECISIONS item 53)
BUSINESS = re.compile(r"chat|customer|order|sales|store|whatsapp|price|waterer|ledger", re.IGNORECASE)


def engine_source():
    """Every engine file's text, with SQL's ORDER BY taken out (a keyword, not a business word)."""
    return {p.name: p.read_text(encoding="utf-8").replace("ORDER BY", "") for p in sorted((ROOT / "engine").glob("*.py"))}


class EngineHasNoBusinessWords(unittest.TestCase):
    def test_no_business_word_and_no_agent_name_in_engine_code(self):
        found = {name: BUSINESS.findall(text) for name, text in engine_source().items()}
        self.assertEqual({k: v for k, v in found.items() if v}, {})
        self.assertIn("plug.py", found)

    def test_the_scan_catches_a_business_word(self):
        self.assertTrue(BUSINESS.search("def for_chat(self, chat_id):"))
        self.assertTrue(BUSINESS.search("Customer"))
        self.assertFalse(BUSINESS.search("SELECT * FROM trace  id"))


class SalesPlug(unittest.TestCase):
    def test_declares_todays_11_results(self):
        self.assertEqual(set(PLUG.results), TODAYS_11)
        self.assertEqual(PLUG.agent, "sales")

    def test_fast_and_slow(self):
        slow = {n for n, r in PLUG.results.items() if r.speed == plug.SLOW}
        self.assertEqual(slow, {"delivered", "refused"})
        self.assertEqual(PLUG.results["delivered"].shows_in_days, (2.0, 7.0))
        for name, r in PLUG.results.items():
            if r.speed == plug.FAST:
                self.assertLessEqual(r.shows_in_days[1], 1, name)

    def test_results_of_the_agent_turn_end_an_action(self):
        after = {n: r.after for n, r in PLUG.results.items()}
        self.assertEqual(after["replied"], "reply")
        self.assertEqual(after["check_failed"], "reply")
        self.assertEqual(after["no_safe_reply"], "reply")
        self.assertEqual(after["order_created"], "order")
        self.assertEqual(set(PLUG.actions), {"reply", "order"})
        for later in ("delivered", "refused", "person_replied"):
            self.assertIsNone(after[later], later)

    def test_causes_not_its_fault(self):
        self.assertEqual(set(PLUG.causes), {"out_of_stock", "price", "area"})

    def test_stages_match_the_sales_stages(self):
        self.assertEqual(set(PLUG.stages), set(stages.STAGES))

    def test_risk_tools_are_real_tools(self):
        self.assertTrue(PLUG.risk.tools)
        for t in PLUG.risk.tools:
            self.assertIn(t, TOOLS)

    def test_risk_list_has_the_four_approved_groups(self):
        groups = {g for g, _ in PLUG.risk.words}
        self.assertEqual(groups, {"number", "promise", "policy", "personal_data"})
        self.assertIn("tone", PLUG.risk.low_about)

    def test_the_log_refuses_an_outcome_the_plug_did_not_declare(self):
        r = Results(Db(":memory:"))
        self.addCleanup(r.db.close)
        for outcome in TODAYS_11:
            r.record("c1", outcome)
        for bad in ("made_up", "grew", "soaked", "") + GONE:
            with self.assertRaises(ValueError):
                r.record("c1", bad)


class MadeUpAgent(unittest.TestCase):
    """A small agent that is not the Sales agent, declared in one file, with no engine change."""

    def test_its_plug_loads_from_one_file(self):
        p = plugs.load(plugs.WATERER, self)
        self.assertEqual(p.agent, "waterer")
        self.assertEqual(set(p.actions), {"water", "skip"})
        self.assertEqual(p.result("grew").speed, plug.SLOW)
        self.assertEqual(p.result("wilted").shows_in_days, (1.5, 5.0))
        self.assertEqual(p.result("soaked").after, "water")
        self.assertEqual(p.cause("frost"), "A night frost.")
        self.assertEqual(p.risk.tools, ("sprayer",))
        self.assertEqual(p.stage_tags(["grown", "all", "grown"]), ["all", "grown"])

    def test_it_refuses_what_it_did_not_declare(self):
        p = plugs.load(plugs.WATERER, self)
        for name in ("replied", "delivered", "order_created"):  # the Sales agent's results are not its own
            with self.assertRaises(ValueError):
                p.result(name)
        with self.assertRaises(ValueError):
            p.action("reply")
        with self.assertRaises(ValueError):
            p.cause("out_of_stock")
        with self.assertRaises(ValueError):
            p.stage_tags(["asking"])
        with self.assertRaises(ValueError):
            p.stage_tags([])

    def test_the_two_plugs_share_nothing(self):
        p = plugs.load(plugs.WATERER, self)
        self.assertFalse(set(p.results) & set(PLUG.results))
        self.assertFalse(set(p.actions) & set(PLUG.actions))

    def test_a_plug_cannot_be_changed_after_loading(self):
        p = plugs.load(plugs.WATERER, self)
        with self.assertRaises(TypeError):
            p.results["delivered"] = p.results["grew"]
        with self.assertRaises(AttributeError):
            p.agent = "sales"


class PlugFileChecks(unittest.TestCase):
    def bad(self, data, words):
        with self.assertRaises(ValueError) as cm:
            plug.from_dict(data)
        self.assertIn(words, str(cm.exception))

    def test_refuses_a_broken_plug(self):
        w = plugs.WATERER
        self.bad(plugs.changed(w, extra=1), "unknown key 'extra'")
        no_risk = copy.deepcopy(w)
        del no_risk["risk"]
        self.bad(no_risk, "missing 'risk'")
        self.bad(plugs.changed(w, agent="Water Bot"), "lowercase")
        self.bad(plugs.changed(w, stages=["all"]), "every stage")
        self.bad(plugs.changed(w, actions={}), "at least one entry")
        self.bad(plugs.changed(w, results={"grew": {"speed": "slow", "shows_in_days": [3, 10], "after": "water"}}),
                 "attaches by case")
        self.bad(plugs.changed(w, results={"soaked": {"speed": "fast", "shows_in_days": [0, 2]}}), "within a day")
        self.bad(plugs.changed(w, results={"grew": {"speed": "slow", "shows_in_days": [0, 1]}}), "more than a day")
        self.bad(plugs.changed(w, results={"grew": {"speed": "slow", "shows_in_days": [9, 3]}}), "least <= most")
        self.bad(plugs.changed(w, results={"grew": {"speed": "soon", "shows_in_days": [3, 9]}}), "fast or slow")
        self.bad(plugs.changed(w, results={"soaked": {"speed": "fast", "shows_in_days": [0, 0], "after": "dig"}}),
                 "no declared action")
        self.bad(plugs.changed(w, results={"soaked": {"speed": "fast", "shows_in_days": [0, 0], "colour": "x"}}),
                 "unknown key 'colour'")
        self.bad(plugs.changed(w, trial=dict(w["trial"], fast={"share": 0, "days": 7})), "trial fast share")
        self.bad(plugs.changed(w, trial=dict(w["trial"], fast={"share": float("nan"), "days": 7})), "a number")
        self.bad(plugs.changed(w, slot="two\nlines"), "one line")
        risk = copy.deepcopy(w["risk"])
        risk["high"]["patterns"] = {"amount": ["[0-9"]}
        self.bad(plugs.changed(w, risk=risk), "risk pattern")
        risk = copy.deepcopy(w["risk"])
        del risk["low"]
        self.bad(plugs.changed(w, risk=risk), "missing 'low'")

    def test_refuses_a_file_that_is_not_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plug.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                plug.load(path)


if __name__ == "__main__":
    unittest.main()
