"""Round 2 review and red team fixes on the send check (2026-11-01), on the made-up demo store.

1. A sign that shows as a comma, a dot or an apostrophe, a narrow blank next to a separator, a spacing mark
   or a modifier letter never splits a model number from the rest of a price: "Vapor 17‚400" reads 17400.
   A model number is dropped only where the reply plainly moves on (an allow list), checked by a sweep.
2. ألاف, تلاف and talaf are thousands words; a number with k right after a store word is an amount.
3. Count words are stems with up to two bridge words ("Only Vapor 17 are left", "Phantom 6 lesa fadlin");
   "N pairs" after have and "N جوز بس" are counts.
4. Lenient English: a common Franco word counts each time, a clock time is passed over only next to a time
   word, and Franco currency and mawgood words count.
5. No demo title lead is a cue, tier, count word or a preposition; the test gaps the review listed.
"""
import re
import unicodedata
import unittest

from kit import send_check
from kit.tools import store
from reflection import PLUG, exam
from tests.fake_model import FakeModel, clean_env, say

EN = "Do you have the adidas boots in 43?"
FR = "bekam el vapor ya basha?"
AR = "بكام الجزمة؟"
HAIR, THIN, SIX, NNBSP, NBSP = " ", " ", " ", " ", " "
AR_COMMA = "،"
COMMA_LIKE = (0x201A, 0xFF0C, 0xFE50, 0xFE51, 0x3001)
DOT_LIKE = (0x2024, 0xFF0E, 0xFE52, 0x00B7, 0x2027)
APOSTROPHE_LIKE = (0x2018, 0x201B, 0x2032, 0x2035, 0x02B9, 0x02BB, 0x02BC, 0x02BD, 0x00B4, 0xFF07, 0x275B, 0x275C)


def problems(reply, customer=EN, names=None):
    return dict(send_check.named_problems(reply, customer, store.price_points(), store.vocabulary(),
                                          store.size_strings(), names=store.titles() if names is None else names))


def read(reply):
    return send_check.prices_in(reply, store.size_strings(), (), store.titles())


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)


class SeparatorLookAlikes(Base):
    """Red team item 1 and review finding 1. 400 is the printing price; the customer reads one number."""

    def test_comma_and_apostrophe_look_alikes_read_the_joined_number(self):
        for cp in COMMA_LIKE + APOSTROPHE_LIKE:
            for reply, customer in ((f"The price is Vapor 17{chr(cp)}400 EGP.", EN),
                                    (f"The price is Vapor 17 {chr(cp)}400 EGP.", EN),
                                    (f"se3r el Vapor 17{chr(cp)}400 geneh", FR)):
                with self.subTest(cp=hex(cp), reply=reply):
                    self.assertIn(17400, read(reply))
                    self.assertIn("17400", problems(reply, customer)["amounts"])
        self.assertIn(17400, read("سعر Vapor ١٧‚٤٠٠ جنيه"))

    def test_dot_look_alikes_read_like_the_plain_dot(self):
        """Glued, a dot look-alike reads as the plain dot does (17.4); after a blank it joins (17400)."""
        for cp in DOT_LIKE:
            with self.subTest(cp=hex(cp)):
                self.assertEqual(read(f"The price is Vapor 17{chr(cp)}400 EGP."), read("The price is Vapor 17.400 EGP."))
                self.assertIn("amounts", problems(f"The price is Vapor 17{chr(cp)}400 EGP."))
                self.assertIn(17400, read(f"The price is Vapor 17 {chr(cp)}400 EGP."))

    def test_names_keep_their_own_look_alike_table(self):
        """arena/clean.py builds its name table from LOOKALIKES; the number signs stay out of it."""
        for cp in COMMA_LIKE + DOT_LIKE + APOSTROPHE_LIKE:
            self.assertNotIn(cp, send_check.LOOKALIKES)
            self.assertIn(cp, send_check.NUMBER_LOOKALIKES)

    def test_a_narrow_blank_next_to_a_separator_reads_the_joined_number(self):
        for reply in (f"The price is Vapor 17,{HAIR}400 EGP.", f"The price is Vapor 17,{THIN}400 EGP.",
                      f"The price is Vapor 17,{NNBSP}400 EGP.", f"The price is Vapor 17,{SIX}400 EGP.",
                      f"The price is Vapor 17{HAIR},{HAIR}400 EGP.", f"The price is Vapor 17{THIN},{THIN}400 EGP.",
                      f"سعر Vapor ١٧{AR_COMMA}{HAIR}٤٠٠ جنيه", f"سعر Phantom ٦{HAIR}{AR_COMMA}{HAIR}٤٠٠ جنيه"):
            with self.subTest(reply=reply):
                found = read(reply)
                self.assertTrue(17400 in found or 6400 in found, found)
                self.assertNotIn(400, found)

    def test_a_spacing_mark_or_a_modifier_letter_inside_the_number_joins_it(self):
        for reply in ("The price is Vapor 17ः,400 EGP.", "The price is Vapor 17ˈ400 EGP.",
                      "The price is Phantom 6ʿ400 EGP.", "سعر Phantom ٦ـ٤٠٠ جنيه"):
            with self.subTest(reply=reply):
                found = read(reply)
                self.assertTrue(17400 in found or 6400 in found, found)

    def test_blanks_around_a_separator_keep_the_model_number(self):
        for reply in ("The price is Vapor 17 , 400 EGP.", "The price is Vapor 17 . 400 EGP."):
            with self.subTest(reply=reply):
                self.assertIn("17", problems(reply)["amounts"])

    def test_a_list_and_a_sentence_end_still_strip(self):
        for reply in ("Here is the Phantom 6. 16,500 EGP", "Phantom 6 (16,500 EGP).", "Phantom 6: 16,500 EGP.",
                      "Cairo 60, Alex 85 EGP.", "Vapor 17, 400 EGP for printing.", f"Vapor 17,{NBSP}400 EGP for printing.",
                      "The Vapor 17's sole is firm ground.", "Phantom 6 - 7,500 EGP is the Academy.",
                      "Phantom 6\n7,500 EGP"):
            with self.subTest(reply=reply):
                self.assertNotIn("amounts", problems(reply))


class SeparatorSweep(Base):
    """Review finding 1 (c): every BMP punctuation, symbol, modifier letter, spacing mark, blank, control, line
    and paragraph separator and letter or other number sign (Nl, No) from U+0000 between "Phantom 6" and a store
    amount tail, glued, after a blank and after a separator, in English, Arabic and Franco (red team handoff
    round 3, item 2). The PR base 9c415df (no model numbers) let 235 glued characters through (237 in Arabic)
    and none after a blank; head fcfa213 let 3,990 through. Now glued only the percent signs pass ("6%400" is
    not one number); anywhere a line end passes (a line break is a list); after a separator a blank as wide as
    a plain space passes ("6, 400" is a list)."""

    CATEGORIES = ("Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po", "Sm", "Sc", "Sk", "So", "Lm", "Mc", "Zs", "Cc", "Zl",
                  "Zp", "Nl", "No")
    TEMPLATES = (("The price is Phantom 6{c}400 EGP.", EN), ("The price is Phantom 6 {c}400 EGP.", EN),
                 ("The price is Phantom 6,{c}400 EGP.", EN),
                 ("سعر Phantom 6{c}400 جنيه", AR), ("سعر Phantom 6 {c}400 جنيه", AR), ("سعر Phantom 6،{c}400 جنيه", AR),
                 ("el se3r Phantom 6{c}400 geneh", FR), ("el se3r Phantom 6 {c}400 geneh", FR),
                 ("el se3r Phantom 6,{c}400 geneh", FR))
    LINE_ENDS = {"0xa", "0xd", "0x2028", "0x2029"}
    WIDE_BLANKS = {"0x9", "0x20", "0xa0", "0x3000", "0x2800"}

    def test_no_separator_lets_the_tail_through(self):
        chars = [chr(cp) for cp in range(0x00, 0x10000) if unicodedata.category(chr(cp)) in self.CATEGORIES]
        args = (store.price_points(), store.vocabulary(), store.size_strings())
        names = store.titles()
        for template, customer in self.TEMPLATES:
            passed = {hex(ord(c)) for c in chars
                      if not send_check.named_problems(template.replace("{c}", c), customer, *args, names=names)}
            with self.subTest(template=template):
                allowed = set(self.LINE_ENDS)
                if "6{c}" in template:
                    allowed |= {"0x25", "0x66a"}
                if ",{c}" in template or "،{c}" in template:
                    allowed |= self.WIDE_BLANKS
                self.assertLessEqual(passed, allowed)


class ThousandsWords(Base):
    """Red team item 2."""

    def test_the_three_words_after_a_model_number_are_refused(self):
        for reply, customer in (("سعر Vapor 17 ألاف", AR), ("سعر Vapor ١٧ ألاف", AR), ("سعره Phantom 6 تلاف.", AR),
                                ("Phantom 6 تلاف بس", AR), ("se3ro Phantom 6 talaf", FR), ("el phantom 6 talaf", FR)):
            with self.subTest(reply=reply):
                self.assertIn("digits", problems(reply, customer))

    def test_the_words_spelled_with_a_currency_are_refused(self):
        for reply, customer in (("el se3r sab3a talaf geneh", FR), ("السعر سبعة ألاف جنيه", AR)):
            with self.subTest(reply=reply):
                self.assertTrue(send_check.amount_in_words(reply) or send_check.SPELLED_AMOUNT.search(reply))
                self.assertIn("digits", problems(reply, customer))


class KAfterAStoreWord(Base):
    """Review finding 2: lenient English stopped reading "17.5k" as Franco, the only refusal it had."""

    def test_k_right_after_a_store_word_is_refused(self):
        for reply in ("Elite 17.5k, Academy 7.5k.", "Vapor 17 Elite, 17.5k.", "Phantom 6 Academy 8.5k",
                      "The Tiempo Maestro: 13.5k."):
            with self.subTest(reply=reply):
                self.assertIn("digits", problems(reply))

    def test_the_k_rule_stays_as_it_was_elsewhere(self):
        """Locked: "1.5k" with no cue passes (tests/test_fixes_j.py). "The Elite runs 17k." and "It comes to
        17k." are named in docs/known-limits.md."""
        for reply in ("Hoodie 1.5k", "We have 1k followers on Instagram."):
            with self.subTest(reply=reply):
                self.assertNotIn("digits", problems(reply))
        self.assertFalse(send_check.store_word_thousands("We have 1k followers.", store.vocabulary()))


class CountWords(Base):
    """Red team item 3 and the adjacent count words."""

    def test_stems_and_bridge_words_keep_a_count(self):
        for reply, customer in (("Only Vapor 17 are left in 43.", EN), ("Only Vapor 17 still left.", EN),
                                ("Only Vapor 17 remain.", EN), ("Only Vapor 17 remains.", EN),
                                ("Only Vapor 17 pc left.", EN), ("Only Vapor 17 pcs left.", EN),
                                ("Only Vapor 17 pairs are left.", EN), ("Vapor 17 only left.", EN),
                                ("Phantom 6 باقيه بس", AR), ("Phantom 6 متبقية", AR), ("Phantom 6 لسه فاضلين", AR),
                                ("Phantom 6 بس لسه فاضلين", AR), ("Phantom 6 fadla bs", FR),
                                ("Phantom 6 ba2yeen bs", FR), ("Phantom 6 fadlen", FR), ("Phantom 6 lesa fadlin", FR),
                                ("Phantom 6 bs fadlin", FR), ("Phantom 6 mawgodeen bs", FR)):
            with self.subTest(reply=reply):
                self.assertIn("stock", problems(reply, customer))

    def test_pairs_and_goz_are_counts(self):
        for reply, customer in (("We have Vapor 17 pairs in 43.", EN), ("We have 3 pairs in 43.", EN),
                                ("Phantom 6 جوز بس", AR), ("Phantom 6 goz bs", FR), ("عندنا 3 جوز", AR)):
            with self.subTest(reply=reply):
                self.assertIn("stock", problems(reply, customer))

    def test_a_count_without_a_model_number_agrees(self):
        for reply in ("Only 3 pcs left.", "Only 3 are left.", "3 remain in 43.", "Phantom 6, 3 lesa fadlin"):
            with self.subTest(reply=reply):
                self.assertTrue(send_check.stock_counts(reply, store.size_strings(), (), store.titles()))

    def test_orders_offers_codes_and_the_verb_are_not_counts(self):
        for reply, customer in (("The Vapor 17 remains our best seller.", EN), ("Buy 2 pairs and get free delivery.", EN),
                                ("It comes with 2 pairs of laces.", EN), ("The box has 2 pairs of laces.", EN), ("The Phantom 6 pairs well with a firm pitch.", EN),
                                ("Yes, your order is 2 pairs in size 43.", EN), ("Code BO-2936845 is in stock.", EN),
                                ("Phantom 6 still available in 43.", EN), ("The Phantom 6 is still available.", EN),
                                ("The price of the Phantom 6 is more than the Superfly 11.", EN),
                                ("Phantom 6 mawgood bs", FR), ("Phantom 6 موجود بس", AR)):
            with self.subTest(reply=reply):
                self.assertNotIn("stock", problems(reply, customer))

    def test_more_stays_a_whole_word(self):
        titles = ["Nike Phantom 6"]
        self.assertEqual(send_check.without_model_numbers("Phantom 6 moreover", titles), "Phantom moreover")
        self.assertEqual(send_check.without_model_numbers("Phantom 6 more", titles), "Phantom 6 more")


class LenientEnglish(Base):
    """Red team item 4 and review minor 3."""

    def test_a_common_word_counts_each_time(self):
        self.assertIn("not Franco", problems("el vapor, el superfly, el tawsil 70 EGP.").get("script", ""))

    def test_a_clock_time_is_passed_over_only_next_to_a_time_word(self):
        for reply in ("ya 3am, the Vapor is in stock.", "3am, the vapor is 16,500 EGP."):
            with self.subTest(reply=reply):
                self.assertIn("not Franco", problems(reply).get("script", ""))
        for reply in ("Call us at 3pm or 9am.", "We open at 9am and close at 9pm, EU42 is in stock.",
                      "Open from 9am to 9pm.", "We open 9am, close 9pm.", "Deliveries start 9am daily.",
                      "The El Ultimo Tango is 16,500 EGP, the El Ultimo Tango in 43 too.",
                      "Boots w/ a box, bags w/ a tag."):
            with self.subTest(reply=reply):
                self.assertNotIn("script", problems(reply))

    def test_franco_currency_and_mawgood_words_count(self):
        for reply in ("El Vapor b 16,500 geneh, el Phantom b 7,500 geneh.", "el vapor mawgood, el phantom mawgood",
                      "3am, el F50 mawgood b 19,500 geneh.", "El Ultimo mawgood ya basha, b 19,500 geneh",
                      "Ma32ool, el vapor b 16,500 geneh"):
            with self.subTest(reply=reply):
                self.assertIn("not Franco", problems(reply).get("script", ""))

    def test_size_and_count_codes_are_not_franco(self):
        for reply in ("Yes, UK8 is in stock.", "Take x2 and the delivery is free."):
            with self.subTest(reply=reply):
                self.assertNotIn("script", problems(reply))

    def test_a_franco_word_after_a_title_word_is_passed_over(self):
        names = set(store.titles()) | {"Puma Fast Keda"}
        self.assertNotIn("script", problems("The Puma Fast Keda is 7,500 EGP, ya know.", names=names))

    def test_the_customer_line_takes_the_title_pairs(self):
        customer = "Is the El Ultimo Tango in stock, and the El Ultimo Tango League?"
        self.assertIn("English or Franco", problems("أيوه موجودين", customer)["script"])


class TitleLeads(Base):
    """Red team item 5 and review minor 4: no title lead hides a number, and each word list holds."""

    PREPOSITIONS = ("from", "under", "over", "around", "about", "approx", "starting", "now", "extra", "another",
                    "within")

    def test_no_demo_title_lead_is_a_cue_tier_count_word_or_a_preposition(self):
        leads = [lead for lead, _ in send_check._model_parts(store.titles())]
        self.assertTrue(leads)
        for lead in leads:
            with self.subTest(lead=lead):
                self.assertIsNone(send_check.NOT_A_TITLE_WORD.fullmatch(lead))
                self.assertNotIn(lead, self.PREPOSITIONS)
        for title in store.titles():
            for word in re.findall(r"[a-z]+", title.casefold()):
                self.assertNotIn(word, self.PREPOSITIONS, title)

    def test_each_word_list_gives_no_model_number(self):
        for title in ("Nike Just 9", "Nike Building 9", "Nike Size 9", "Nike EU 9", "Nike EGP 9", "Nike Five 9", "Nike K 9",
                      "Nike Model 9", "Nike Days 9", "Nike March 9", "Nike Elite 9", "Nike To 9"):
            with self.subTest(title=title):
                self.assertEqual(send_check.model_numbers([title]), [])


class Gaps(Base):
    """Review minor 4: the surviving mutants."""

    def test_the_exam_passes_the_titles(self):
        did = exam.answer(exam.situations(PLUG)[0], None,
                          model=FakeModel(say("The price of the Phantom 6 is 7,500 EGP.")))
        self.assertNotIn("amounts", did["problems"])

    def test_a_line_end_never_joins_digit_groups(self):
        self.assertEqual(send_check._plain("1\n400"), "1\n400")
        self.assertEqual(send_check._plain("1 400"), "1400")

    def test_an_enclosing_mark_on_no_letter_goes(self):
        self.assertIn(17400, read("The price is Vapor 17⃝,400 EGP."))


if __name__ == "__main__":
    unittest.main()
