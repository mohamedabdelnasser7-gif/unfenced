"""Round 3 fixes (2026-10-31; DECISIONS item 52, review round 3 findings 2, 3 and 4). The price check
keeps an add-on's price when an add-on word sits right beside the amount, and a bracket or a spaced
dash sets an aside apart like a comma. Made-up replies on the demo catalogue only."""
import unittest

from arena import factcheck
from tests.fake_model import clean_env

AC = chr(0x60C)  # the Arabic comma


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class AddOnWords(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_an_add_on_word_beside_the_amount_keeps_the_extras_price(self):
        for reply in ("If you add printing to the Elite, it's 400 EGP more.",
                      "Sure, the Vapor 17 Elite can have your name on it, it's 400 EGP extra.",
                      "لو عايز اسمك على الـ Vapor 17 Elite" + AC + " هتبقى 400 جنيه زيادة",
                      "Vapor Elite with printing, plus 400 EGP.",
                      "Vapor Elite 16,500, an extra 400 for your name.",
                      "The Vapor 17 Elite with printing, 400 EGP on top.",
                      "الـ Vapor 17 Elite مع اسمك زيادة 400 جنيه",
                      "Vapor 17 Elite with name printing: 16,900 EGP (16,500 + 400)."):
            self.assertEqual(checks(reply), [], reply)

    def test_the_word_must_sit_beside_the_amount_and_the_extra_be_named(self):
        for reply in ("The Vapor 17 Elite is 400 EGP more.",                # no extra named anywhere
                      "Vapor Elite 16,500 plus 400",
                      "Vapor Elite 16,500; the printing is on top: 400",   # a colon between
                      "Vapor Elite with printing, 1400 EGP extra.",        # not the extra's price
                      "Vapor Elite with printing, 4000 more."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_round_2_refusals_still_hold(self):
        for reply in ("The Vapor 17 Elite, with printing, is 400 EGP.", "The Vapor 17 Elite with printing: 400 EGP.",
                      "Vapor Elite, 400 EGP, with your name.", "The Vapor 17 Elite is 400 EGP",
                      "The Vapor 17 Elite, printing included, is 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)


class Asides(unittest.TestCase):
    """Review round 3, item 4: the guard lines no test caught on their own."""

    def setUp(self):
        clean_env(self)

    def test_a_bracket_or_a_spaced_dash_aside_is_cut_like_a_comma(self):
        for reply in ("The Vapor 17 Elite (with printing) is 400 EGP.",
                      "The Vapor 17 Elite [with printing] is 400 EGP.",
                      "The Vapor 17 Elite - with printing - is 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)
        for reply in ("Phantom 6 Elite (with your name printed): 16,900 EGP", "Superfly 11 Elite (20,000 EGP).",
                      "Printing (400 EGP) goes on any boot."):
            self.assertEqual(checks(reply), [], reply)

    def test_an_extra_price_before_the_boot_in_its_sentence_fails(self):
        """The sentence names a boot after the price: the backdrop does not hold it (sentence_boot)."""
        for reply in ("It's 400 EGP, the Vapor 17 Elite with printing.",
                      "400 EGP, with printing, for the Vapor 17 Elite."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_a_boot_named_with_no_tier_counts_as_a_boot(self):
        for reply in ("The Mercurial Vapor, with printing, is 400 EGP.", "The Phantom, with your name, is 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_a_boot_price_in_a_clause_after_the_extra_alone_fails(self):
        """The clause takes the extra from the clause before it (inheritance)."""
        for reply in ("Printing, 16,500 EGP.", "The name printing, 16,500 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)


if __name__ == "__main__":
    unittest.main()
