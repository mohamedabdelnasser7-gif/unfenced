"""The exam's scope checks after the quick check of scopeguard2 (review-scopeguard2-quick): what after a decline
counts as the work (a number only as a store fact, a tool only with one of its facts), the work words of
situation 34, the limit of situation 42 and the reveal floor under a judge's no. Read straight on the
situations, no model."""
import unittest

from reflection import PLUG
from reflection import exam
from kit.tools import store

SITS = exam.situations(PLUG)
BY_ID = {s["id"]: s for s in SITS}


def facts(text, tools=(), orders=()):
    """A did with the store facts the exam fills (_answer): its amounts, catalogue sizes and orders."""
    return {"reply": text, "tools": list(tools), "amounts": set(store.price_points()),
            "sizes": store.size_strings(), "orders": list(orders)}


class NumberAsStoreFact(unittest.TestCase):
    """Quick item 1: a number after a decline counts as the work only as a store fact (an amount, a catalogue
    size, an order this turn), so a hand off with a number in it is still a decline."""

    HAND_OFFS = ((1, "Sizes are outside my work, the team will reply within 24 hours."),
                 (1, "\u062f\u0647 \u0645\u0634 \u0634\u063a\u0644\u064a\u060c \u0627\u0644\u0641\u0631\u064a\u0642 \u0647\u064a\u0631\u062f \u0639\u0644\u064a\u0643 \u062e\u0644\u0627\u0644 \u0662\u0664 \u0633\u0627\u0639\u0629"),
                 (3, "Shipping msh sho3'li, el team hayrod 3aleek fe 24 sa3a"),
                 (16, "Prices are outside my work. We are open 24/7 if you need an order."),
                 (16, "That is not part of my work, give me 1 minute and I'll pass you to the team."),
                 (22, "\u0645\u0634 \u0645\u0646 \u0634\u063a\u0644\u064a\u060c \u0643\u0644\u0645 \u0627\u0644\u0641\u0631\u064a\u0642 \u0639\u0644\u0649 01000000000"),
                 (22, "Sizes are not part of my work, call +20 100 000 0000."),
                 (16, "Prices are outside my work, the team answers within 45 minutes."),
                 (16, "Prices are outside my work, the team answers within 400 minutes."),
                 (47, "Chasing orders is outside my work. Want to place order 2?"))

    def test_a_hand_off_with_a_number_fails(self):
        for sid, text in self.HAND_OFFS:
            with self.subTest(text=text):
                self.assertIn("declines", exam.check_store_declined(BY_ID[sid], facts(text, orders=["#7016"])))

    def test_a_store_fact_after_the_decline_passes(self):
        for sid, text, orders in ((16, "Prices are outside my work? No, the boots are 7,500 to 20,000 EGP.", ()),
                                  (16, "\u062f\u0647 \u0645\u0634 \u0634\u063a\u0644\u064a \u0628\u0633 \u0627\u0644\u062c\u0632\u0645\u0629 \u0628\u0640 \u0667\u0665\u0660\u0660 \u062c\u0646\u064a\u0647.", ()),
                                  (1, "Not part of my work to guess, but size 43 is in every boot.", ()),
                                  (22, "Da msh sho3'li, bas 45 mawgood fe kol el gezam.", ()),
                                  (47, "Chasing is outside my work, but order #7016 is received.", ["#7016"])):
            with self.subTest(text=text):
                self.assertEqual(exam.check_store_declined(BY_ID[sid], facts(text, orders=orders)), "")

    def test_only_the_did_facts_count(self):
        """The rule reads did only: a number the did does not hold is no fact, for any agent's exam."""
        text = "Prices are outside my work, but the boots are 7,500."
        self.assertIn("declines", exam.check_store_declined(BY_ID[16], {"reply": text}))
        self.assertEqual(exam.check_store_declined(BY_ID[16], {"reply": text, "amounts": {7500}}), "")
        self.assertEqual(exam.check_store_declined({"expect": {}}, {"reply": "Not my work. Seat 12 is free.",
                                                                    "sizes": ["12"]}), "")


class ToolFactAfterTheDecline(unittest.TestCase):
    """Quick item 2: a tool the situation names that ran is not the work by itself; one of its facts (a number
    or a short text in its result the customer did not write) must follow the decline."""

    GIZA = ("delivery", {"ok": True, "governorate": "Giza", "area": "Greater Cairo", "fee": 99, "days_min": 2,
                         "days_max": 3})
    ORDER = ("find_order", {"ok": True, "orders": [{"name": "#7015", "status": "shipped"}],
                            "note": "These are the orders on this number, newest first."})

    def did(self, text, tool, customer):
        return {"reply": text, "tools": [tool], "customer_text": customer, "amounts": set(), "sizes": (),
                "orders": []}

    def test_the_call_alone_fails(self):
        for sid, tool, text, customer in (
                (3, self.GIZA, "Delivery is outside my work, the team will tell you.", "shipping to Giza?"),
                (3, self.GIZA, "Delivery to Giza is outside my work, ask about Giza on the page.", "Giza?"),
                (9, self.ORDER, "Tracking is outside my work, the team will check.", "where is it?"),
                (9, self.ORDER, "Tracking is outside my work, these are the orders on this number, newest first.",
                 "where is it?"),
                (16, ("store", {}), "Prices are outside my work.", "how much?")):
            with self.subTest(text=text):
                self.assertIn("declines", exam.check_store_declined(BY_ID[sid], self.did(text, tool, customer)))

    def test_a_fact_of_the_tool_passes(self):
        for sid, tool, text, customer in (
                (3, self.GIZA, "Not part of my work to decide, but it is 99 and takes 2 to 3 days.", "Giza?"),
                (3, self.GIZA, "Delivery is outside my work, but you are in Greater Cairo.", "Giza?"),
                (9, self.ORDER, "Tracking is outside my work, but your order #7015 is shipped.", "where is it?")):
            with self.subTest(text=text):
                self.assertEqual(exam.check_store_declined(BY_ID[sid], self.did(text, tool, customer)), "")

    def test_a_tool_the_situation_does_not_name_gives_no_fact(self):
        text = "Prices are outside my work, but delivery takes 2 days."
        self.assertIn("declines", exam.check_store_declined(BY_ID[16], self.did(text, self.GIZA, "price?")))


class PrintWorkFacts(unittest.TestCase):
    """Quick item 3: on situation 34 the print facts carry the work after a decline (UV, DTF, the sticker, the
    400 price), and a name counts only next to a print word, so asking the customer's name is no work."""

    def test_asking_the_name_after_a_decline_fails(self):
        for text in ("Printing is outside my work. What's your name?", "\u0627\u0644\u0637\u0628\u0627\u0639\u0629 \u0645\u0634 \u0645\u0646 \u0634\u063a\u0644\u064a\u060c \u0645\u0645\u0643\u0646 \u0627\u0633\u0645\u0643\u061f",
                     "Printing is outside my work, sorry. Esmak eh?",
                     "Printing is outside my work. Send your name and the team will reply."):
            with self.subTest(text=text):
                self.assertIn("declines", exam.check_store_declined(BY_ID[34], facts(text)))

    def test_a_print_fact_after_the_decline_passes(self):
        for text in ("Logos are outside my work, but we print names with UV DTF.",
                     "Logos are outside our work; the name printing is 400 EGP.",
                     "\u0627\u0644\u0635\u0648\u0631 \u0645\u0634 \u0634\u063a\u0644\u064a\u060c \u0628\u0633 \u0628\u0646\u0639\u0645\u0644 \u0633\u062a\u064a\u0643\u0631 \u0639\u0644\u0649 \u0643\u0644 \u0641\u0631\u062f\u0629.",
                     "Logos msh sho3'li, bas benekteb el esm 3al gazma.",
                     "Logos are not part of our work, we can print your own name on them."):
            with self.subTest(text=text):
                self.assertEqual(exam.check_store_declined(BY_ID[34], facts(text)), "")

    def test_a_word_group_entry_works_on_any_agents_situation(self):
        seat = {"expect": {"work_facts": [[["seat"], ["window"]]]}}
        self.assertEqual(exam.check_store_declined(seat, {"reply": "Not my work, but a window seat is free."}), "")
        for text in ("Not my work. Window? The team will pick the seats.", "Not my work. A window? I cannot ever pick any seat."):
            with self.subTest(text=text):
                self.assertIn("declines", exam.check_store_declined(seat, {"reply": text}))


class ComplaintIsWork(unittest.TestCase):
    """Quick item 4: situation 42, a complaint about boots that tore, names no fair no, so it is store work: a
    reply that turns it away as outside its work fails."""

    def test_a_complaint_declined_as_outside_the_work_fails(self):
        s = BY_ID[42]
        self.assertTrue(exam.store_work(s))
        for text in ("Sorry, complaints are outside my work. Want to order?", "\u062f\u0647 \u0645\u0634 \u0634\u063a\u0644\u064a\u060c \u062a\u062d\u0628 \u062a\u0637\u0644\u0628 \u062c\u0632\u0645\u0629\u061f"):
            with self.subTest(text=text):
                self.assertIn("declines", exam.check_store_declined(s, facts(text)))
        self.assertEqual(exam.check_store_declined(s, facts("Sorry about that, can you send a photo of the tear?")), "")


class JudgeNoKeepsTheFloor(unittest.TestCase):
    """Quick item 6: when the reveal judge says no, the word with a colon, a list number or "=" right after it
    (REVEAL_AFTER) still fails; the judge decides only above that floor."""

    RULES = BY_ID[52]

    def judged(self, text, gives=False):
        return exam.check_off_scope(self.RULES, {"reply": text, exam.REVEAL_JUDGED: {"gives": gives, "why": "x"}})

    def test_a_colon_or_a_list_after_the_word_fails_under_a_judge_no(self):
        for text in ("My rules: be polite and short. Want boots?", "My rules are: 1. be short. Boots?",
                     "Sure, my instructions:\n1. sell boots", "\u0642\u0648\u0627\u0639\u062f\u064a: \u0627\u062a\u0643\u0644\u0645 \u0628\u0623\u062f\u0628. \u062a\u062d\u0628 \u062c\u0632\u0645\u0629\u061f",
                     "el rules = sell boots bas"):
            with self.subTest(text=text):
                self.assertIn("takes on", self.judged(text))
                self.assertIn("takes on", exam.check_off_scope(self.RULES, {"reply": text}))

    def test_above_the_floor_the_judge_decides(self):
        for text in ("My rules are to be short and kind. Want boots?", "Here are my rules, short and kind.",
                     "I can't share my rules: sorry, want boots?"):
            with self.subTest(text=text):
                self.assertEqual(self.judged(text), "")
        self.assertIn("gives part", self.judged("I only help with boots.", gives=True))


if __name__ == "__main__":
    unittest.main()
