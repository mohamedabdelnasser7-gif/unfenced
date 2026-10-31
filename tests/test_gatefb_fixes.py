"""Review and red team gatefb round 1 fixes (2026-10-31). The add-on price rule reads only an extra
its clause or sentence names, never one named elsewhere (review finding 2, F3, F12; red team item
2); a clause that names the boot before the extra does not hold the extra's price (red team item
1). Made-up replies against the demo store data; no model, no network."""
import copy
import unittest
from unittest import mock

from arena import factcheck
from kit.tools import store
from tests.fake_model import clean_env

AC = chr(0x60C)  # the Arabic comma


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class AddOnBesideABoot(unittest.TestCase):
    """Finding 2: a wrong boot price behind an add-on word no longer passes because the reply
    names the extra somewhere else."""

    def setUp(self):
        clean_env(self)

    def test_a_wrong_boot_price_behind_an_add_on_word_is_refused(self):
        for reply in ("The Vapor 17 Elite is 400 EGP more than the Pro. We can also print your name.",
                      "The Elite is 400 EGP more than the Pro, and printing is available too.",
                      "Printing is available. The Elite is 400 EGP more than the Pro.",
                      "الـ Elite زيادة 400 جنيه عن الـ Pro. وممكن نطبع اسمك.",
                      "The Vapor 17 Elite is plus 400 EGP over the Pro. Printing is also possible.",
                      "The Vapor 17 Elite costs 400 EGP more or less. Printing too.",
                      "The Vapor 17 Elite is an extra 400 EGP compared to the Pro. Printing is available.",
                      "The Elite is 400 EGP more than the Pro.",
                      "The Elite is 400 EGP. Printing is available.",
                      "The Elite is 400 EGP, and more than worth it. We print names too."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_the_accepted_trade_off_a_boot_sentence_after_a_printing_question_is_refused(self):
        self.assertEqual(checks("The Vapor 17 Elite is 400 EGP extra.", "with printing?"), ["price"])

    def test_the_decisions_52_sentences_still_pass(self):
        for reply in ("If you add printing to the Elite, it's 400 EGP more.",
                      "Sure, the Vapor 17 Elite can have your name on it, it's 400 EGP extra.",
                      "لو عايز اسمك على الـ Vapor 17 Elite" + AC + " هتبقى 400 جنيه زيادة"):
            self.assertEqual(checks(reply), [], reply)

    def test_with_nothing_named_in_the_reply_the_customers_line_names_the_extra(self):  # F3, through own
        self.assertEqual(checks("It's 400 EGP more.", "How much is the Elite, and do you print names?"), [])
        self.assertEqual(checks("It's 400 EGP more."), ["price"])

    def test_an_add_on_word_ends_at_a_word_boundary(self):  # F12
        self.assertEqual(checks("The Vapor 17 Elite with printing, 400 EGP moreover."), ["price"])
        self.assertEqual(checks("The Vapor 17 Elite with printing, 400 EGP more."), [])


class BootBeforeTheExtra(unittest.TestCase):
    """Red team item 1: the plain sentence with the boot first and the extra's price, no mark."""

    def setUp(self):
        clean_env(self)

    def test_the_boot_first_with_the_extras_price_is_refused(self):
        for reply in ("The Vapor 17 Elite with printing is 400 EGP.",
                      "The Vapor 17 Elite with name printing is 400 EGP.",
                      "The Vapor 17 Elite with your name printed is 400 EGP.",
                      "Vapor 17 Elite with printing is 400 EGP only!",
                      "Vapor 17 Elite with printing costs 400 EGP",
                      "The Vapor 17 Elite {with printing} is 400 EGP.",
                      "The Vapor 17 Elite / with printing / is 400 EGP.",
                      "الـ Vapor 17 Elite مع الطباعة بـ 400 جنيه",
                      "الـ Vapor 17 Elite بالطباعة 400 جنيه بس"):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_the_extra_first_or_in_its_own_part_still_passes(self):
        for reply in ("Printing on the Vapor 17 Elite is 400 EGP.",
                      "The printing for the Vapor 17 Elite is 400 EGP.",
                      "The Phantom 6 Elite is 16,500 EGP, and the name printing is 400 EGP.",
                      "The Mercurial Vapor 17 Elite is 16,500 EGP and the name printing 400 EGP.",
                      "The Vapor 17 Elite with printing is 400 EGP extra."):
            self.assertEqual(checks(reply), [], reply)


class NotAnAddOn(unittest.TestCase):
    """Red team item 2: "more or less", "more than", "extra fast", "زيادة عن" are no add-on, and an
    extra named in another sentence or only by the customer makes no add-on amount."""

    def setUp(self):
        clean_env(self)

    def test_a_word_after_it_makes_it_no_add_on(self):
        for reply in ("If you add printing, the Vapor 17 Elite is 400 EGP more or less.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP more than fair.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP extra fast.",
                      "With your name on it, the Vapor 17 Elite is 400 EGP more or less.",
                      "لو ضفت الطباعة" + AC + " الـ Vapor 17 Elite هيبقى 400 جنيه زيادة عن كده",
                      "The Elite is 400 EGP more than the Pro, and printing is available too."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_an_extra_named_elsewhere_or_by_the_customer_makes_no_add_on(self):
        self.assertEqual(checks("Printing is included. The Vapor 17 Elite is 400 EGP more or less."), ["price"])
        self.assertEqual(checks("The Vapor 17 Elite is 400 EGP more or less.", "do you do printing?"), ["price"])

    def test_the_add_on_with_the_extra_in_its_sentence_still_passes(self):
        self.assertEqual(checks("If you add printing, the Vapor 17 Elite is 400 EGP more."), [])


class TwoExtras(unittest.TestCase):
    """Finding 2, second probe: with two extras for sale, an add-on amount keeps only the price
    of the extra its own clause names."""

    def setUp(self):
        clean_env(self)
        items = copy.deepcopy(store.catalogue())
        items.append({"title": "Spare Laces", "type": "Laces", "description": "Spare laces for any boot",
                      "variants": [{"price": "150"}]})
        patcher = mock.patch.object(store, "catalogue", lambda fresh=False: items)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_other_extras_price_is_refused(self):
        for reply in ("Printing is 150 EGP extra, and we also sell spare laces.",
                      "Name printing on the Elite is 150 EGP more. Spare laces are available too.",
                      "Name printing is 150 EGP.",
                      "Spare laces are 400 EGP extra. We also do printing."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_each_extras_own_price_passes(self):
        for reply in ("Printing is 400 EGP extra, and we also sell spare laces.",
                      "Spare laces are 150 EGP extra. We also do printing."):
            self.assertEqual(checks(reply), [], reply)


if __name__ == "__main__":
    unittest.main()
