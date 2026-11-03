"""Any agent, round 2 (2026-11-04): what three agents built on the real model showed (a support desk, a
gym lead follower, a coffee caption writer). tests/three_agents.json holds their cards, plugs, first
instructions and night lessons as the real model wrote them; nothing here calls the network."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import plug as plug_mod
from engine import risk as risk_mod
from kit import send_check, turn
from kit.chats import Chats
from kit.db import Db
from reflection import quickstart as qs
from tests.fake_model import FakeModel, clean_env, say

THREE = json.loads((Path(__file__).resolve().parent / "three_agents.json").read_text(encoding="utf-8"))


def cleaned(name):
    """The agent's plug as Build writes it now: the model's plug through clean_plug with its card."""
    a = THREE[name]
    raw = {k: v for k, v in a["plug"].items() if k != "exam"}
    return plug_mod.from_dict(qs.clean_plug(raw, name, a["card"]["tools"], a["card"]))


def low(text, high_about, low_about):
    return risk_mod.LOW  # the judge's clear low, so only the code check can make a lesson high


class OwnWorkIsNotHighRisk(unittest.TestCase):
    """Every night lesson of a built agent waited for a yes (9 of 9): any digit was high, and the model put
    the agent's own work (reply, caption, trial, book, next step, time) in its high words."""

    def test_the_nine_night_lessons_are_low_except_the_one_on_fees_and_refunds(self):
        got = {}
        for name, a in THREE.items():
            plug = cleaned(name)
            for n, text in enumerate(a["lessons"], 1):
                got[(name, n)] = risk_mod.classify(text, plug.risk, low)
        highs = {k: why for k, (level, why) in got.items() if level == risk_mod.HIGH}
        self.assertEqual(sorted(highs), [("support_calm_helper", 2)], highs)
        why = highs[("support_calm_helper", 2)]
        self.assertIn("money: fee", why)
        self.assertIn("money: refund", why)
        self.assertEqual(len(got), 9)

    def test_the_old_plugs_marked_all_nine(self):
        """The plugs as the model wrote them: every lesson high from the code check alone."""
        for name, a in THREE.items():
            plug = plug_mod.from_dict({k: v for k, v in a["plug"].items() if k != "exam"})
            for text in a["lessons"]:
                self.assertTrue(risk_mod.code_check(text, plug.risk), (name, text))

    def test_money_refunds_personal_data_and_outside_promises_stay_high_for_every_agent(self):
        risky = ["Offer a 20% discount to a lead who hesitates.", "Say the price is 450 when asked.",
                 "Mention the 1,200 pound package.", "Tell them the refund goes out today.",
                 "Offer a replacement for any broken item.", "Ask for their home address before booking.",
                 "Send the customer's address with the reply.", "Share the lead's phone number with the coach.",
                 "Promise the order will arrive tomorrow.", "Guarantee delivery by Sunday.",
                 "Add a payment link to the caption.", "Waive the fee for late orders.",
                 "Tell the customer the courier will deliver it today.", "قول للعميل ان الخصم ٢٠٪."]
        for name in THREE:
            plug = cleaned(name)
            for text in risky:
                level, why = risk_mod.classify(text, plug.risk, low)
                self.assertEqual(level, risk_mod.HIGH, (name, text))

    def test_counts_times_and_the_verb_address_are_not_money(self):
        plug = cleaned("support_calm_helper")
        for text in ["Keep the reply to 3 short lines.", "Answer within 2 minutes of the ticket.",
                     "Address their worry first, then give the next step.", "Ask for one photo of the item.",
                     "Reply to the ticket and tag it as late."]:
            self.assertEqual(risk_mod.code_check(text, plug.risk), [], text)

    def test_the_cleaner_drops_own_work_vague_words_tool_names_and_every_number_patterns(self):
        card = {"does": "Writes a short reply to each ticket and tags it.",
                "case": {"input": "a ticket", "starts": "person", "output": "a reply and a tag",
                         "ends": "when the reply is sent"}}
        risk = {"high": {"about": "Anything that goes out.", "words": {
                    "goes_out": ["reply", "send", "replies", "forward", "orders"], "promise": ["next step", "time", "refund"],
                    "personal_data": ["name", "address", "phone"]},
                    "patterns": {"number": ["[0-9]", "\\d+"], "personal_data": ["@"]}, "tools": ["x"]},
                "low": {"about": "Tone."}}
        out = qs.clean_risk(risk, card, ["orders"])
        words = out["high"]["words"]
        self.assertEqual(words["goes_out"], ["forward"])
        self.assertEqual(words["promise"][0], "refund")
        self.assertNotIn("next step", words["promise"])
        self.assertEqual(words["personal_data"][0], "phone")
        self.assertNotIn("address", words["personal_data"])  # the pattern reads it, never the verb
        self.assertNotIn("number", out["high"]["patterns"])
        self.assertEqual(out["high"]["patterns"]["personal_data"][0], "@")
        self.assertEqual(out["high"]["tools"], ["orders"])
        self.assertEqual(out["high"]["about"], qs.HIGH_ABOUT)
        self.assertIn("a reply and a tag", out["low"]["about"])
        self.assertTrue(out["low"]["about"].endswith("Tone."))
        for group, items in qs.CORE_WORDS.items():
            self.assertTrue(set(items) <= set(words[group]))

    def test_the_build_prompt_asks_the_same(self):
        self.assertIn("Its normal work is never high", qs.BUILD_PROMPT)
        self.assertNotIn("anything that goes out in the user's name", qs.BUILD_PROMPT)


def agent_folder(root, name, instructions=None):
    """One of the three agents as Build writes its folder now, under root/agents/<name>."""
    a = THREE[name]
    folder = Path(root) / "agents" / name
    folder.mkdir(parents=True)
    raw = {k: v for k, v in a["plug"].items() if k != "exam"}
    (folder / "plug.json").write_text(json.dumps(qs.clean_plug(raw, name, a["card"]["tools"], a["card"])),
                                      encoding="utf-8")
    (folder / "card.json").write_text(json.dumps(a["card"]), encoding="utf-8")
    (folder / "instructions.md").write_text(instructions or a["instructions"], encoding="utf-8")
    return folder


class TheirOwnNumbers(unittest.TestCase):
    """A support agent's reply that named the customer's postal code 6000 failed "amounts not in the store
    data": the Sales agent's whole amounts rule judged an agent that quotes no prices."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    NOT_PRICES = ["Your order ORD-1004 to 45 Rue Habib Bourguiba, Gabes 6000 is on its way.",
                  "Ticket 48213 is tagged as late.", "Your order 6000 left the warehouse.",
                  "We open at 10:30 on 12 Nov, see you then.", "You have 150 points so far.",
                  "Your trial is on Tuesday at 6pm, for 1500 seconds of fun."]
    PRICES = ["The delivery fee is 85 EGP.", "It costs 450.", "The price is 300 for the month.",
              "Shipping comes to 120.", "That is 999 جنيه."]

    def test_only_prices_and_fees_are_held_to_the_data_for_any_agent_but_sales(self):
        for text in self.NOT_PRICES:
            self.assertEqual(send_check.check(text, text, priced_only=True, stock=False), (True, ""), text)
        for text in self.PRICES:
            passed, why = send_check.check(text, text, priced_only=True)
            self.assertFalse(passed, text)
            self.assertIn("amounts are not in the store", why)
        self.assertTrue(send_check.check("The delivery fee is 85 EGP.", "", amounts=[85], priced_only=True)[0])

    def test_the_sales_check_is_whole(self):
        for text in self.NOT_PRICES[:3]:
            passed, why = send_check.check(text, text)
            self.assertFalse(passed, text)
            self.assertIn("amounts are not in the store", why)
        self.assertFalse(send_check.check("Only 3 left in your size.", "")[0])
        self.assertTrue(send_check.check("Only 3 left in your size.", "", priced_only=True, stock=False)[0])

    def test_a_built_agent_reads_prices_only_and_the_stock_rule_only_with_the_store(self):
        agent = turn.load(agent_folder(self.root, "support_calm_helper"))
        self.assertEqual((agent.full_check, agent.priced_only, agent.stock), (True, True, False))
        leads = turn.load(agent_folder(self.root, "lead_trial_booker"))
        self.assertEqual((leads.full_check, leads.priced_only, leads.stock), (True, True, False))

    def turn(self, agent, reply):
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "c1")
        sent = []
        out = turn.turn(agent, "Where is my order?", chats=chats, chat_id=cid, model=FakeModel(*[say(reply)] * 4),
                        send=lambda to, text: sent.append(text), customer_id="c1")
        return out, sent

    def test_the_support_agent_names_the_postal_code_and_a_made_up_fee_is_still_refused(self):
        agent = turn.load(agent_folder(self.root, "support_calm_helper"))
        out, sent = self.turn(agent, self.NOT_PRICES[0])
        self.assertEqual((out.outcome, sent), ("replied", [self.NOT_PRICES[0]]))
        out, sent = self.turn(agent, "The delivery fee is 999 EGP.")
        self.assertEqual((out.outcome, sent), ("no_safe_reply", []))
        out, sent = self.turn(agent, "Your order is on its way \u2014 sorry for the wait.")
        self.assertEqual((out.outcome, sent), ("no_safe_reply", []))  # house style holds for every agent


class HouseStyleInTheInstructions(unittest.TestCase):
    """The three agents' instructions never said the house style, so first replies failed on dashes and **."""

    def test_none_of_the_three_said_it_and_build_adds_it(self):
        for name, a in THREE.items():
            self.assertNotIn("dash", a["instructions"].lower(), name)
            plug = {k: v for k, v in a["plug"].items() if k != "exam"}
            got, words, why = qs.QuickStart._plug_from(
                json.dumps({"plug": plug, "instructions": a["instructions"]}), name, a["card"]["tools"], a["card"])
            self.assertIsNone(why, name)
            self.assertTrue(words.startswith(a["instructions"].strip()))
            self.assertTrue(words.endswith(qs.HOUSE_STYLE))
            self.assertEqual(words.count(qs.HOUSE_STYLE), 1)
        for rule in ("markdown", "**", "em or en dashes", "emoji"):
            self.assertIn(rule, qs.HOUSE_STYLE)
        self.assertEqual(send_check.style_problems(qs.HOUSE_STYLE.replace("**", "")), [])


if __name__ == "__main__":
    unittest.main()
