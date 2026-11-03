"""Any agent, round 2 (2026-11-04): what three agents built on the real model showed (a support desk, a
gym lead follower, a coffee caption writer). tests/three_agents.json holds their cards, plugs, first
instructions and night lessons as the real model wrote them; nothing here calls the network."""
import json
import unittest
from pathlib import Path

from engine import plug as plug_mod
from engine import risk as risk_mod
from reflection import quickstart as qs

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


if __name__ == "__main__":
    unittest.main()
