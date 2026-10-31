"""Why the Sales agent handed most Arena chats on at turn 1 (2026-11-01), on the fake model and the demo store.

Reproduced on the made-up cards with the real model: an English reply with a store price written
"16,500 جنيه" (as the price line in sales/instructions.md shows it) failed the script check, and
"Here is the Nike Phantom 6" read 6 as an amount after "is". Three failed drafts in the turn, then
the loop's own handoff, with no handoff tool step. The turn record now keeps the send check
feedback and the hand-off reason, so the next run shows it.
"""
import json
import unittest
from pathlib import Path

from arena import factcheck, match
from kit import send_check
from kit.tools import store
from sales import loop
from tests.fake_model import FakeModel, call, clean_env, say

CARD = json.loads((Path(__file__).resolve().parent.parent / "demo" / "personas" / "cards" / "persona-01.json")
                  .read_text(encoding="utf-8"))
PHOTO_ASK = "Can you send me a photo of the Phantom 6?"
LINK = "https://images.beyond-the-limits.example/phantom-6.jpg"
ARABIC_POUND = "جنيه"   # جنيه


def checked(reply, customer_text, links=(LINK,)):
    """The send check as the loop runs it on the demo store, with the store's titles."""
    return send_check.check(reply, customer_text, store.price_points(), store.vocabulary(), store.size_strings(),
                            links=links, names=store.titles())


class TurnRecordKeepsTheReason(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_three_failed_checks_show_their_feedback_and_the_handoff_reason(self):
        bad = f"Here is the Nike Phantom 6: Elite 16,500 {ARABIC_POUND}."
        agent = FakeModel(call("store", query="phantom"), say(bad), say(bad), say(bad))
        m = match.play(CARD, agent_model=agent, customer_model=FakeModel(), opening=PHOTO_ASK, max_turns=1)
        t = m["turns"][0]
        self.assertEqual((t["outcome"], t["tools"], m["ended"]), ("handed_off", ["store"], "handed_off"))
        self.assertEqual(len(t["checks"]), 3)
        self.assertTrue(all(ARABIC_POUND in c and "EGP" in c for c in t["checks"]), t["checks"])
        self.assertEqual(t["handoff"], {"by": "send_check", "reason": "3 replies failed the send check"})
        self.assertNotIn("Elite 16,500", json.dumps(t, ensure_ascii=False))  # the failed drafts stay out

    def test_a_reply_that_passes_keeps_no_checks_and_no_handoff(self):
        good = f"Here is the Nike Phantom 6:\n{LINK}\n\nElite 16,500 EGP, Pro 11,000 EGP, Academy 7,500 EGP."
        agent = FakeModel(call("store", query="phantom"), say(good))
        m = match.play(CARD, agent_model=agent, customer_model=FakeModel(), opening=PHOTO_ASK, max_turns=1)
        t = m["turns"][0]
        self.assertEqual((t["outcome"], t["replies"], t["checks"]), ("replied", [good], []))
        self.assertNotIn("handoff", t)

    def test_one_failed_draft_then_a_pass_keeps_the_one_feedback(self):
        agent = FakeModel(call("store", query="phantom"), say(f"Phantom 6 Elite 16,500 {ARABIC_POUND}."),
                          say("Phantom 6 Elite 16,500 EGP."))
        m = match.play(CARD, agent_model=agent, customer_model=FakeModel(), opening=PHOTO_ASK, max_turns=1)
        t = m["turns"][0]
        self.assertEqual((t["outcome"], len(t["checks"])), ("replied", 1))

    def test_the_models_own_handoff_shows_by_model_and_no_model_words(self):
        agent = FakeModel(call("handoff", reason="customer wants a manager, secret words"))
        m = match.play(CARD, agent_model=agent, customer_model=FakeModel(), opening="I want a manager now", max_turns=1)
        t = m["turns"][0]
        self.assertEqual(t["handoff"], {"by": "model"})
        self.assertNotIn("secret words", json.dumps(t["handoff"]))


class ModelNumbersAreNotAmounts(unittest.TestCase):
    def test_here_is_the_phantom_6_with_its_link_passes(self):
        reply = f"Here is the Nike Phantom 6:\n{LINK}\n\nIt comes in Elite 16,500 EGP, Pro 11,000 EGP, Academy 7,500 EGP."
        self.assertEqual(checked(reply, PHOTO_ASK), (True, ""))

    def test_each_demo_model_number_after_a_cue_passes(self):
        for reply in ("The price is for the Mercurial Vapor 17 Elite, 16,500 EGP.",
                      "Yes, the Superfly 11 is in stock in size 42.",
                      "The Nike Phantom 6 is available in size 42.",
                      "This is the adidas F50 El Ultimo Tango."):
            with self.subTest(reply=reply):
                self.assertEqual(checked(reply, "Do you have it?"), (True, ""))

    def test_a_model_number_with_a_currency_or_a_wrong_price_still_fails(self):
        for reply, wrong in (("The Phantom 6 is 6 EGP.", "6"), ("Vapor 17 EGP", "17"), ("Vapor 17k EGP", None),
                             ("The Phantom 6 is 999.", "999"), ("Phantom 6 for 16,600 EGP", "16600"),
                             ("Phantom 16,600", "16600")):
            with self.subTest(reply=reply):
                passed, fb = checked(reply, "price?")
                self.assertFalse(passed, reply)
                if wrong:
                    self.assertIn(wrong, fb)

    def test_a_model_number_is_not_a_stock_count(self):
        self.assertEqual(send_check.stock_counts("Phantom 6 available in 42", store.size_strings(), (),
                                                 store.titles()), [])
        self.assertTrue(send_check.stock_counts("Phantom 6, 3 available", store.size_strings(), (), store.titles()))

    def test_with_no_titles_the_old_reading_holds(self):
        self.assertIn(6, send_check.prices_in("Here is the Nike Phantom 6"))
        self.assertNotIn(6, send_check.prices_in("Here is the Nike Phantom 6", names=store.titles()))

    def test_the_fact_check_reads_model_numbers_from_the_same_home(self):
        items = store.catalogue()
        self.assertEqual(factcheck.model_numbers(items), send_check.model_numbers(i["title"] for i in items))
        self.assertEqual(factcheck.without_model_numbers("is the Vapor 17", items), "is the Vapor")
        self.assertEqual(factcheck.MODEL_NUMBER_END, send_check.MODEL_NUMBER_END)


class ModelWordsAreNotFranco(unittest.TestCase):
    def test_an_english_reply_naming_the_f50_passes(self):
        self.assertEqual(checked("Yes, the adidas F50 El Ultimo Tango is 16,500 EGP.", "Do you have the F50?"),
                         (True, ""))

    def test_a_franco_reply_to_an_english_customer_still_fails(self):
        passed, fb = checked("aywa 3andena el F50 b 16,500 EGP", "Do you have the F50?")
        self.assertFalse(passed)
        self.assertIn("not Franco", fb)

    def test_the_skip_holds_only_title_words_with_a_digit(self):
        self.assertEqual(send_check.model_words(store.titles()), frozenset({"f50"}))
        self.assertTrue(send_check.looks_franco("the F50"))
        self.assertFalse(send_check.looks_franco("the F50", send_check.model_words(store.titles())))


class CurrencyFollowsTheScript(unittest.TestCase):
    def test_arabic_pound_in_an_english_reply_names_the_word_and_egp(self):
        passed, fb = checked(f"The Vapor 17 Elite is 16,500 {ARABIC_POUND}.", "How much is the Vapor 17?")
        self.assertFalse(passed)
        self.assertIn(f"(this reply has: {ARABIC_POUND})", fb)
        self.assertIn("16,500 EGP", fb)

    def test_arabic_pound_in_a_franco_reply_names_geneh(self):
        passed, fb = checked(f"el vapor 17 elite b 16,500 {ARABIC_POUND}", "bekam el vapor 17 ya basha?")
        self.assertFalse(passed)
        self.assertIn("geneh", fb)

    def test_egp_in_english_geneh_in_franco_and_pound_in_arabic_pass(self):
        for reply, customer in (("The Vapor 17 Elite is 16,500 EGP.", "How much is the Vapor 17?"),
                                ("el vapor 17 elite b 16,500 geneh", "bekam el vapor 17 ya basha?"),
                                (f"الـ Vapor 17 Elite بـ 16,500 {ARABIC_POUND}",
                                 "بكام الفيبور؟")):
            with self.subTest(reply=reply):
                self.assertEqual(checked(reply, customer), (True, ""))

    def test_the_digits_feedback_names_each_scripts_currency(self):
        passed, fb = checked("The Vapor 17 is two thousand EGP.", "How much is the Vapor 17?")
        self.assertFalse(passed)
        self.assertIn("EGP in English", fb)

    def test_the_instructions_keep_the_price_line_and_say_egp_and_geneh(self):
        self.assertIn('Say the price plainly, the number then جنيه, for example "16,500 جنيه".', loop.INSTRUCTIONS)
        self.assertIn('In English write the currency as EGP, for example "16,500 EGP"; in Franco as geneh',
                      loop.INSTRUCTIONS)


class MaskedProductWords(unittest.TestCase):
    """Cleaned real cards can say "nike [name] boots". The store does not fail on it; a lone "[name]"
    matches the name printing (its title holds "Name"), so that query returns the printing only."""

    def test_store_answers_a_query_with_a_masked_word(self):
        out = store.run({"query": "nike [name] boots"}, None)
        self.assertTrue(out["ok"])
        self.assertTrue(any(i["title"].startswith("Nike") for i in out["items"]))

    def test_a_lone_masked_word_reads_as_the_name_printing(self):
        out = store.run({"query": "[name]"}, None)
        self.assertEqual([i["title"] for i in out["items"]], ["Beyond the Limits Name Printing"])


if __name__ == "__main__":
    unittest.main()
