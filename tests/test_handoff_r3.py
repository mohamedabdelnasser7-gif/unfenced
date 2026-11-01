"""Round 3 review and red team fixes on the send check (2026-11-01), on the made-up demo store.

Red team items 1 to 4 and review findings 1 to 3 and the NARROW_BLANKS part of minor 4:
1. k after a model number or a sign after a store word is an amount ("Phantom 6: 8.5k", "Elite (17.5k)").
2. Control characters, every narrow blank and letters that draw as a dot or an apostrophe never split a model
   number from the rest of a price.
3. alaf, elf, الآف and ألآف are thousands words.
4. Count shapes: remain by grammar, currently, bas, pieces and units after we have, 3andena, متوفر.
5. Ordinary sales lines pass again: mawgod singular, order summaries, "UK 8 is in stock", clock ranges,
   "mesh" twice, "w/o", b or ب glued to a price, an ellipsis, ؛ or a spaced ? after a model number.
"""
import unittest

from kit import send_check
from kit.tools import store
from tests.fake_model import clean_env

EN = "Do you have the adidas boots in 43?"
FR = "bekam el vapor ya basha?"
AR = "بكام الجزمة؟"
ELLIPSIS, AR_SEMICOLON = "…", "؛"


def problems(reply, customer=EN, names=None):
    return dict(send_check.named_problems(reply, customer, store.price_points(), store.vocabulary(),
                                          store.size_strings(), names=store.titles() if names is None else names))


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def assert_refused(self, lines, kind):
        for reply, customer in lines:
            with self.subTest(reply=reply):
                self.assertIn(kind, problems(reply, customer))

    def assert_sent(self, lines, names=None):
        for reply, customer in lines:
            with self.subTest(reply=reply):
                self.assertEqual(problems(reply, customer, names), {})


class KAfterAModelNumber(Base):
    """Red team item 1 (high)."""

    def test_k_after_a_model_number_or_a_sign_is_refused(self):
        self.assert_refused(
            [("Phantom 6: 8.5k.", EN), ("Phantom 6, 8.5k.", EN), ("Phantom 6 8.5k.", EN), ("Phantom 6 - 8.5k.", EN),
             ("Phantom 6: 8,5k", EN), ("Phantom 6: 8.5 thousand.", EN), ("Superfly 11: 11k.", EN),
             ("Vapor 17: 17.5k.", EN), ("F50: 15k.", EN), ("el phantom 6: 8.5k", FR), ("Elite (17.5k).", EN),
             ("Elite = 17.5k.", EN), ("Elite 17,5k.", EN), ("Elite: 17,5k.", EN), ("Vapor 17 Elite (17.5k)", EN),
             ("Vapor 17 Elite (17.5k), Academy (7.5k).", EN)], "digits")

    def test_the_k_rule_stays_as_it_was_elsewhere(self):
        self.assert_sent([("Hoodie 1.5k", EN), ("We have 1k followers on Instagram.", EN),
                          ("We have 10k followers on Instagram.", EN), ("Phantom 6: 16,500 EGP.", EN)])


class HiddenSeparators(Base):
    """Red team item 2 and review minor 4 (NARROW_BLANKS)."""

    def test_a_control_character_after_a_separator_joins_the_number(self):
        lines = [(f"The price is Vapor 17,{c}400 EGP.", EN) for c in ("\x85", "\x1c", "\x0b", "\x0c")]
        lines += [("se3r el Vapor 17,\x1d400 geneh", FR), ("سعر Vapor ١٧،\x85٤٠٠ جنيه", AR)]
        self.assert_refused(lines, "amounts")

    def test_every_narrow_blank_after_a_separator_joins_the_number(self):
        lines = []
        for c in (" ", " ", " ", " ", " ", " ", " ", " "):
            lines += [(f"Vapor 17,{c}400 EGP", EN), (f"The price is Vapor 17,{c}400 EGP.", EN),
                      (f"سعر Vapor ١٧،{c}٤٠٠ جنيه", AR), (f"se3r el Vapor 17,{c}400 geneh", FR)]
        self.assert_refused(lines, "amounts")

    def test_a_letter_that_draws_as_a_dot_or_an_apostrophe_joins_the_number(self):
        lines = []
        for cp in (0xA78F, 0x1427, 0x18DF, 0x0887, 0x0971, 0xA78B, 0xA78C, 0x144A, 0xA4F9):
            c = chr(cp)
            lines += [(f"The price is Vapor 17{c}400 EGP.", EN), (f"Vapor 17{c}400 EGP.", EN),
                      (f"سعر Vapor ١٧{c}٤٠٠ جنيه", AR), (f"se3r el Vapor 17{c}400 geneh", FR)]
        for reply, customer in lines:
            with self.subTest(reply=reply):
                self.assertTrue(problems(reply, customer))
        for cp in (0xA78F, 0x1427, 0x18DF, 0x0887, 0x0971, 0xA78B, 0xA78C):
            for reply, customer in ((f"The price is Vapor 17 {chr(cp)}400 EGP.", EN),
                                    (f"se3r el Vapor 17 {chr(cp)}400 geneh", FR)):
                with self.subTest(reply=reply):
                    self.assertIn(17400, send_check.prices_in(reply, store.size_strings(), (), store.titles()))
                    self.assertIn("amounts", problems(reply, customer))

    def test_an_emphasis_mark_after_a_separator_joins_the_number(self):
        """Found by the sweep of a separator then a character: WhatsApp shows "17,_400_" as 17,400."""
        self.assert_refused([("The price is Vapor 17,_400_ EGP.", EN), ("سعر Vapor 17،*400* جنيه", AR),
                             ("se3r el Vapor 17,~400~ geneh", FR)], "amounts")

    def test_a_line_break_still_ends_the_line(self):
        """A carriage return shows as a line break, so "17," then a carriage return then "400" is a list like
        "17," then a line feed (the red team's fix maps it to a line feed though its item 2 list named it)."""
        for reply in ("The price is Vapor 17,\r400 EGP.", "The price is Vapor 17,\r\n400 EGP.",
                      "The price is Vapor 17, 400 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(send_check._plain(reply).count("\n"), 1)
        self.assert_sent([("The Phantom 6 is 7,500 EGP.\r\nDelivery is 85 EGP.", EN)])


class MoreThousandsWords(Base):
    """Red team item 3."""

    def test_the_four_spellings_are_refused(self):
        self.assert_refused([("se3r el Vapor 17 alaf geneh", FR), ("Vapor 17 alaf.", FR), ("el phantom 6 alaf", FR),
                             ("se3r el Vapor 17 elf geneh", FR), ("سعر Vapor 17 الآف", AR),
                             ("سعر Vapor 17 ألآف جنيه", AR)], "digits")


class CountShapes(Base):
    """Red team item 4 and review minor 4."""

    def test_the_count_shapes_are_refused(self):
        self.assert_refused(
            [("Only Vapor 17 remain right now.", EN), ("3 remain so hurry.", EN), ("Only 3 pairs currently available.", EN),
             ("We have 3 pieces in 43.", EN), ("We have 3 pcs in 43.", EN), ("We have Vapor 17 units in 43.", EN),
             ("3 goz bas", FR), ("3andena 3 pairs bs", FR), ("متوفر 3 بس", AR), ("المتوفر 3", AR),
             ("Only Vapor 17 remain available in 43.", EN),
             # is or are after the count word (review handoff2 round 1, finding 5)
             ("Only 3 pairs are in stock.", EN), ("Only 3 pairs are still in stock.", EN),
             ("Only 2 pieces are available.", EN), ("Hurry, 2 pairs are in stock.", EN),
             ("Only 2 pairs are now available.", EN),
             # is after a count word (review handoff2 round 2, test gap)
             ("1 pair is in stock.", EN), ("Only 1 piece is left in 43.", EN)], "stock")

    def test_remains_as_a_verb_is_not_a_count(self):
        self.assert_sent([("The Superfly 11 remains in our range.", EN), ("The Superfly 11 remains at the same price.", EN),
                          ("The Superfly 11 remains only in 43.", EN), ("The Vapor 17 remains our best seller.", EN),
                          ("Both the Phantom 6 and Vapor 17 remain popular.", EN)])


class OrdinaryLines(Base):
    """Review findings 1 to 3: lines that passed before round 2 and were refused after it."""

    def test_mawgod_singular_is_available_not_a_count(self):
        self.assert_sent([("el F50 mawgod fel 43 ya basha", FR), ("el Vapor 17 mwgod b 16,500 geneh", FR),
                          ("el Phantom 6 mawgoda fel 42", FR)])
        self.assert_refused([("Phantom 6 mawgodeen bs", FR)], "stock")

    def test_order_summaries_are_not_counts(self):
        self.assert_sent([("Your order has 2 pairs in size 43, Phantom 6 and Vapor 17.", EN),
                          ("There are 2 pairs in your cart, size 42 and 43.", EN),
                          ("tamam, el order 2 goz bs, size 43", FR), ("تمام، الأوردر 2 جوز بس، مقاس 43", AR)])

    def test_a_size_or_an_option_in_stock_is_not_a_count(self):
        self.assert_sent([("Yes, UK 8 is in stock, that is EU 42.", EN), ("Option 2 is available in 43.", EN),
                          ("UK 8 is in stock.", EN), ("Option 2 is available.", EN), ("Your order has 2 pairs.", EN)])
        self.assert_sent([("The Air Max 90 is available in 43.", EN)], names=store.titles() | {"Nike Air Max 90"})

    def test_english_with_clock_ranges_mesh_and_w_o_stays_english(self):
        self.assert_sent([("We're open daily 9am-9pm.", EN), ("Our working hours are 9am-5pm, Sunday to Thursday.", EN),
                          ("Delivery comes 2pm-5pm.", EN), ("Mesh upper, mesh tongue, firm ground studs.", EN),
                          ("The Phantom 6 has a mesh upper, the Vapor 17 has a mesh collar.", EN),
                          ("Boots w/o box, bags w/o tag.", EN)])

    def test_mesh_still_counts_with_another_franco_word(self):
        self.assertTrue(send_check.looks_franco("mesh mawgood ya basha", lenient=True))

    def test_the_model_number_ends_before_a_glued_b_an_ellipsis_a_semicolon_or_a_spaced_question_mark(self):
        self.assert_sent([("se3r el Phantom 6 b7,500 geneh", FR), ("سعر الـ Phantom 6 ب7,500 جنيه", AR),
                          (f"The price of the Phantom 6{ELLIPSIS} 7,500 EGP.", EN),
                          (f"سعر الـ Phantom 6{AR_SEMICOLON} 7,500 جنيه", AR), ("Is it the Vapor 17 ?", EN)])


if __name__ == "__main__":
    unittest.main()
