"""Round 1 review and red team fixes on the hand-off cause work (2026-11-01), on the made-up demo store.

1. A model number never becomes the thousands head of a wrong price ("Vapor 17 ,400 EGP" reads 17400).
2. A model number then a count word is a stock count ("Only Vapor 17 pairs left"); a cue word is never a
   title word ("Nike Total 90"); "Vapor 17k" is an amount in words.
3. The customer's line is read as written; when only a model word makes it Franco, the reply may be
   English or Franco (Arabic letters refused). An English reply is read leniently ("El Ultimo Tango" twice,
   "9am", "EU42" are not Franco).
4. The fact check reads numbers as the send check does; the exam passes the titles; patterns compile once.
"""
import json
import re
import time
import unittest
from pathlib import Path
from unittest import mock

from arena import factcheck, match
from kit import send_check
from kit.tools import store
from reflection import exam
from sales import loop
from tests.fake_model import FakeModel, call, clean_env, say

CARD = json.loads((Path(__file__).resolve().parent.parent / "demo" / "personas" / "cards" / "persona-01.json")
                  .read_text(encoding="utf-8"))
EN = "Do you have the adidas boots in 43?"
FR = "bekam el vapor ya basha?"
AR = "بكام الجزمة؟"
THIN, NBSP, BRAILLE, LOW_LINE, RIGHT_QUOTE = " ", " ", "⠀", "̲", "’"
AR_COMMA = "،"


def problems(reply, customer=EN, names=None):
    return dict(send_check.named_problems(reply, customer, store.price_points(), store.vocabulary(),
                                          store.size_strings(), names=store.titles() if names is None else names))


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)


class SeparatorAfterAModelNumber(Base):
    """Red team item 1. 400 is the printing price; the customer reads the two parts as one number."""

    def test_every_spelling_reads_the_joined_number(self):
        cases = [
            ("The price is Phantom 6 ,400 EGP.", EN, "6400"),
            ("The price is Vapor 17 ,400 EGP.", EN, "17400"),
            (f"The price is Vapor 17{THIN},400 EGP.", EN, "17400"),
            (f"The price is Vapor 17{NBSP},400 EGP.", EN, "17400"),
            ("The price is Vapor 17\t400 EGP.", EN, "17400"),
            ("The price is Vapor 17  400 EGP.", EN, "17400"),
            (f"The price is Vapor 17{BRAILLE},400 EGP.", EN, "17400"),
            (f"The price is Vapor 17{LOW_LINE},400 EGP.", EN, "17400"),
            ("The price is Vapor 17'400 EGP.", EN, "17400"),
            (f"The price is Vapor 17{RIGHT_QUOTE}400 EGP.", EN, "17400"),
            (f"سعر Phantom 6 {AR_COMMA}400 جنيه", AR, "6400"),
            (f"سعر Phantom ٦ {AR_COMMA}٤٠٠ جنيه", AR, "6400"),
            (f"سعر Vapor ۱۷ {AR_COMMA}۴۰۰ جنيه", AR, "17400"),
            ("se3r el Vapor 17 ,400 geneh", FR, "17400"),
        ]
        for reply, customer, joined in cases:
            with self.subTest(reply=reply):
                found = problems(reply, customer)
                self.assertIn("amounts", found)
                self.assertIn(joined, found["amounts"])

    def test_the_tail_alone_is_never_read(self):
        for reply in ("The price is Vapor 17 ,400 EGP.", "The price is Vapor 17  400 EGP."):
            with self.subTest(reply=reply):
                self.assertNotIn(400, send_check.prices_in(reply, names=store.titles()))

    def test_the_belt_keeps_a_model_number_with_digits_after_blanks(self):
        pattern = send_check.model_numbers(["Nike Mercurial Vapor 17"])[0]
        for text in ("Vapor 17 ,400", "Vapor 17 400", "Vapor 17\t,400", f"Vapor 17 {AR_COMMA}400", "Vapor 17'400",
                     f"Vapor 17{AR_COMMA}400", f"Vapor 17{RIGHT_QUOTE}400"):
            with self.subTest(text=text):
                self.assertEqual(re.sub(pattern, r"\1", text, flags=re.IGNORECASE), text)
        self.assertEqual(re.sub(pattern, r"\1", "Vapor 17 is here", flags=re.IGNORECASE), "Vapor is here")

    def test_a_sentence_end_or_a_list_still_strips(self):
        self.assertEqual(problems("Here is the Phantom 6. 16,500 EGP"), {})
        self.assertEqual(send_check.prices_in("Phantom 6, 400 EGP for the printing.", names=store.titles()), [400])


class CountAfterAModelNumber(Base):
    """Red team item 2."""

    def test_a_count_word_after_a_model_number_is_a_stock_count(self):
        for reply, customer in (("Only Vapor 17 pairs left in 43.", EN), ("Phantom 6 pieces left.", EN),
                                ("Phantom 6 left in stock.", EN), ("Phantom 6 فاضلين بس.", AR),
                                ("Phantom 6 fadlin bs", FR)):
            with self.subTest(reply=reply):
                self.assertIn("stock", problems(reply, customer))

    def test_available_and_in_stock_name_the_boot(self):
        for reply in ("Phantom 6 available in 42.", "Superfly 11 in stock.",
                      "Yes, the Superfly 11 is in stock in size 42."):
            with self.subTest(reply=reply):
                self.assertEqual(problems(reply), {})


class TitleWords(Base):
    """Red team item 4 and review low 2."""

    def test_the_demo_titles_give_their_four_model_numbers(self):
        self.assertEqual(sorted(send_check._model_parts(store.titles())),
                         [("f", "50"), ("phantom", "6"), ("superfly", "11"), ("vapor", "17")])

    def test_no_demo_title_word_is_a_cue_tier_or_count_word(self):
        for lead, _ in send_check._model_parts(store.titles()):
            self.assertIsNone(send_check.NOT_A_TITLE_WORD.fullmatch(lead), lead)

    def test_cue_tier_and_count_words_and_long_numbers_give_none(self):
        for title in ("Nike Total 90 Laser", "Nike Guard Pro 500", "Grip Tape Pack of 3", "Gift Card 750",
                      "Cairo 70 Bag", "Shipping 60 Box", "Nike Phantom 600"):
            with self.subTest(title=title):
                self.assertEqual(send_check.model_numbers([title]), [])
        self.assertEqual(len(send_check.model_numbers(["Nike Phantom GX 2"])), 1)

    def test_a_cue_word_title_never_hides_an_amount(self):
        names = set(store.titles()) | {"Nike Total 90 Laser", "Grip Tape Pack of 3"}
        for reply, wrong in (("Delivery to Alex total 90.", "90"), ("Shipping to Alex, total 90, 2 to 3 days.", "90"),
                             ("Delivery is a total of 3", "3")):
            with self.subTest(reply=reply):
                found = problems(reply, names=names)
                self.assertIn(wrong, found.get("amounts", ""))

    def test_a_title_word_must_start_a_word(self):
        self.assertIn(6, send_check.prices_in("This is the Xphantom 6", names=store.titles()))


class ThousandsAfterAModelNumber(Base):
    """Red team item 5: the docstring says "Vapor 17k" is an amount; now it is."""

    def test_k_or_thousand_after_a_model_number_is_refused(self):
        for reply, customer in (("Superfly 11k.", EN), ("Vapor 17 K.", EN), ("Vapor 17k.", EN),
                                ("Vapor 17 thousand, Superfly 11 thousand.", EN), ("el vapor 17k", FR)):
            with self.subTest(reply=reply):
                self.assertIn("digits", problems(reply, customer))

    def test_k_with_no_product_word_stays_as_before(self):
        for reply in ("We have 1k followers on Instagram.", "Hoodie 1.5k"):
            with self.subTest(reply=reply):
                self.assertNotIn("digits", problems(reply))


class CustomerLineAsWritten(Base):
    """Review medium 1: the F50 skip is on the reply only."""

    def test_a_franco_opening_with_the_f50_and_a_franco_reply_replies(self):
        reply = "aywa el F50 mawgood, el Elite b 19,500 geneh"
        for opening in ("el F50 bekam?", "F50 mawgood?", "F50 bekam ya basha?"):
            with self.subTest(opening=opening):
                agent = FakeModel(call("store", query="f50"), say(reply), say(reply), say(reply))
                m = match.play(CARD, agent_model=agent, customer_model=FakeModel(), opening=opening, max_turns=1)
                t = m["turns"][0]
                self.assertEqual((t["outcome"], t["checks"]), ("replied", []), t)

    def test_a_line_franco_only_for_the_f50_takes_english_or_franco(self):
        customer = "Do you have the F50?"
        self.assertEqual(problems("Yes, the adidas F50 Messi El Ultimo Tango is 19,500 EGP.", customer), {})
        self.assertEqual(problems("aywa 3andena el F50 b 19,500 geneh", customer), {})
        found = problems("أيوه الـ F50 موجود بـ 19,500 جنيه", customer)
        self.assertIn("Reply in English or Franco, no Arabic letters", found["script"])
        self.assertIn("(this reply has:", found["script"])

    def test_the_customer_line_is_read_as_written(self):
        self.assertEqual(send_check.detect_script("el F50 bekam?"), "franco")
        self.assertEqual(send_check.detect_script("el F50 bekam?", send_check.model_words(store.titles()), True,
                                                  send_check.title_pairs(store.titles())), "english")

    def test_the_loop_reads_the_same_customer_line_as_franco(self):
        self.assertEqual(send_check.detect_script("el F50 bekam?") or "arabic", "franco")


class EnglishRepliesReadLeniently(Base):
    """Root's rerun: 7 English replies were told "not Franco". Made-up lines on the demo store."""

    def test_plain_english_replies_pass(self):
        for reply in ("The Adidas F50 Messi El Ultimo Tango Elite is 19,500 EGP. The El Ultimo Tango League is "
                      "7,500 EGP.",
                      "The adidas El Ultimo Tango comes in Elite, Pro and League. Messi's El Ultimo Tango is in stock.",
                      "We deliver between 9am and 5pm, in 1 to 2 days.",
                      "Yes, EU42 is in stock.",
                      "Delivery takes 24h to 48h in Cairo.",
                      "Sure, the F50 is 19,500 EGP."):
            with self.subTest(reply=reply):
                self.assertNotIn("script", problems(reply))

    def test_franco_still_fails(self):
        for reply in ("aywa 3andena el F50 b 19,500 EGP", "aywa el vapor mawgood", "el F50 El Ultimo Tango ya basha",
                      "3andena el Phantom 6", "tamam ya basha, el F50 b 19,500 EGP"):
            with self.subTest(reply=reply):
                self.assertIn("not Franco", problems(reply).get("script", ""))

    def test_the_lenient_reading_is_not_the_default(self):
        self.assertTrue(send_check.looks_franco("We open at 9am."))
        self.assertFalse(send_check.looks_franco("We open at 9am.", lenient=True))
        self.assertTrue(send_check.looks_franco("the El Ultimo, the El Ultimo"))
        self.assertFalse(send_check.looks_franco("the El Ultimo, the El Ultimo",
                                                 pairs=send_check.title_pairs(store.titles())))

    def test_made_up_title_words_are_passed_over_in_the_reply(self):
        names = set(store.titles()) | {"Puma Ana El Rio", "Puma King A7"}
        for reply in ("The Puma Ana El Rio is 7,500 EGP.", "The A7 is 7,500 EGP."):
            with self.subTest(reply=reply):
                self.assertNotIn("script", problems(reply, names=names))
                self.assertIn("not Franco", problems(reply).get("script", ""))

    def test_w_slash_reads_as_with_when_lenient(self):
        """A common word now counts each time (round 2, red team item 4); "w/" is the English "with"."""
        self.assertTrue(send_check.looks_franco("Boots w/ a box, bags w/ a tag."))
        self.assertFalse(send_check.looks_franco("Boots w/ a box, bags w/ a tag.", lenient=True))


class FactCheckAgrees(Base):
    """Review low 3 and red team item 6."""

    def test_the_fact_check_and_the_send_check_read_the_same_amounts(self):
        items = store.catalogue()
        for reply in ("The Superfly 11 000 EGP", "Phantom 6 500 EGP", "Here is the Phantom​ 6",
                      "The price is Vapor 17 ,400 EGP.", "Here is the *Phantom* *6*", "Vapor 17 Elite 16,500 EGP"):
            with self.subTest(reply=reply):
                self.assertEqual(send_check.prices_in(factcheck.without_model_numbers(reply, items)),
                                 send_check.prices_in(reply, names=store.titles()))
        self.assertEqual(factcheck.without_model_numbers("The Superfly 11 000 EGP", items), "The Superfly 11000 EGP")


class ExamPassesTheTitles(Base):
    """Review low 4."""

    def test_a_model_number_is_not_an_amount_with_no_tool(self):
        did = {"reply": "Here is the Nike Phantom 6.", "orders": [], "tools": []}
        self.assertEqual(exam.check_amount_from_tool({"expect": {}}, did), "")

    def test_a_model_number_is_not_the_delivery_fee_on_a_late_order(self):
        did = {"reply": "Your order is the Air 60, it reaches you in 1 to 2 days.", "orders": [], "tools": []}
        with mock.patch.object(store, "titles", return_value=frozenset({"Nike Air 60"})):
            self.assertEqual(exam.check_late_order({"expect": {"late": True}}, did), "")
        self.assertIn("delivery fee", exam.check_late_order({"expect": {"late": True}}, did))


class CompiledOnce(Base):
    """Review low 6."""

    def test_the_patterns_are_compiled_once_per_store(self):
        send_check.without_model_numbers("Here is the Phantom 6", store.titles())
        before = send_check._model_number_res.cache_info().hits
        for _ in range(3):
            send_check.without_model_numbers("Here is the Phantom 6", store.titles())
        self.assertEqual(send_check._model_number_res.cache_info().hits, before + 3)

    def test_six_hundred_titles_stay_quick(self):
        titles = [f"Brand Model{chr(97 + i % 26)}{chr(97 + i // 26 % 26)} {i % 90 + 1}" for i in range(600)]
        send_check.check("Here is the Phantom 6", EN, store.price_points(), names=titles)
        t = time.perf_counter()
        for _ in range(20):
            send_check.check("Here is the Phantom 6, Elite 16,500 EGP.", EN, store.price_points(), names=titles)
        self.assertLess((time.perf_counter() - t) / 20, 0.1)


class TurnRecordGaps(Base):
    """Mutants the review left alive: each turn's own checks, the no safe reply row (handoff_failed before
    DECISIONS item 53), and the feedback names."""

    def test_each_turn_keeps_only_its_own_checks(self):
        bad = "Phantom 6 Elite 16,500 جنيه."
        good = "Phantom 6 Elite 16,500 EGP."
        agent = FakeModel(call("store", query="phantom"), say(bad), say(good), say("Vapor 17 Elite 16,500 EGP."))
        m = match.play(CARD, agent_model=agent, customer_model=FakeModel(say("And the Vapor 17?")),
                       opening="How much is the Phantom 6?", max_turns=2)
        self.assertEqual([len(t["checks"]) for t in m["turns"]], [1, 0])

    def test_why_of_reads_only_later_rows_and_check_failed_and_no_safe_reply(self):
        rows = [{"id": 1, "outcome": "check_failed", "detail": {"feedback": "old"}},
                {"id": 2, "outcome": "check_failed", "detail": {"feedback": "new"}},
                {"id": 3, "outcome": "model_error", "detail": {"feedback": "not a check"}},
                {"id": 4, "outcome": "no_safe_reply", "detail": {"by": "send_check", "in_a_row": 3}}]
        results = mock.Mock(for_chat=lambda chat_id: rows)
        self.assertEqual(match.why_of(results, "c", 1),
                         {"checks": ["new"], "no_safe_reply": {"by": "send_check"}})

    def test_the_franco_feedback_names_up_to_three_arabic_words(self):
        found = problems("el vapor b 16,500 جنيه يا باشا موجود", FR)
        self.assertIn("(this reply has: جنيه, يا, باشا).", found["script"])


    def test_titles_keep_only_text_titles(self):
        items = [{"title": "Nike Phantom 6", "variants": []}, {"title": None, "variants": []},
                 {"title": 6, "variants": []}]
        with mock.patch.object(store, "catalogue", return_value=items):
            self.assertEqual(store.titles(), frozenset({"Nike Phantom 6"}))


if __name__ == "__main__":
    unittest.main()
