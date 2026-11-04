"""The price fact check (arena/factcheck.py), tightened 2026-10-31, each rule from both sides:

1. An extra's own price (the name printing, 400) counts only in a clause that names the extra, by
   words from its own title, type and description (with their Arabic and Franco spellings), or as a
   price plus the extra, with or without one fee. "The Mercurial Vapor 17 Elite is 400 EGP" fails.
2. A number in a product's model name (the 17 in Vapor 17, the 50 in F50), taken from the store's
   titles, is never read as a price.
"""
import unittest
from unittest import mock

from arena import factcheck
from kit.tools import store
from tests.fake_model import clean_env


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class ExtraPriceClause(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_the_extra_price_beside_the_extra_passes(self):
        for reply, customer in (("printing is 400 EGP for two stickers", ""),
                                ("الطباعة 400 جنيه", ""),
                                ("16,500 plus 400 printing is 16,900", ""),
                                ("16,960 with delivery", ""),
                                ("16,960 with delivery", "Mercurial Vapor 17 Elite with my name printed"),
                                ("400 جنيه لاتنين استيكر واحد على كل فردة", ""),
                                ("اسمك هيتطبع بـ 400 جنيه", "عايز Vapor 17 Elite"),
                                ("Printing is available, it costs 400 EGP.", "Mercurial Vapor 17 Elite"),
                                ("The Phantom 6 Elite is 16,500 EGP, and the name printing is 400 EGP.", ""),
                                ("Printing and delivery to Cairo come to 460 EGP.", ""),
                                ("16,500 plus 60 delivery plus 400 printing is 16,960", ""),
                                ("It is 400 EGP.", "How much is the name printing?")):
            self.assertEqual(checks(reply, customer), [], reply)

    def test_the_extra_price_away_from_the_extra_fails(self):
        for reply, customer in (("The Mercurial Vapor 17 Elite is 400 EGP.", ""),
                                ("Vapor Elite is 400 EGP", ""),
                                ("الـ Mercurial Vapor 17 Elite بـ 400 جنيه", ""),
                                ("It is 400 EGP.", ""),
                                ("It is 400 EGP.", "How much is the Phantom 6 Elite?"),
                                # the printing is named, but in another clause, and this one names a tier
                                ("The Elite is 400 EGP, and we do printing.", "Mercurial Vapor 17")):
            self.assertEqual(checks(reply, customer), ["price"], reply)
        failed = factcheck.check("The Mercurial Vapor 17 Elite is 400 EGP.")
        self.assertIn("400 is the price of Beyond the Limits Name Printing", failed[0]["why"])

    def test_a_clause_that_names_only_the_extra_holds_its_amounts(self):
        # naming the printing names no boot, so a boot price passes only beside the printing's price or a sum
        self.assertEqual(checks("Printing is 16,500 EGP."), ["price"])
        self.assertEqual(checks("الطباعة 16500 جنيه", "عايز Vapor 17 Elite"), ["price"])
        self.assertEqual(checks("الطباعة 500 جنيه", "ممكن تطبعلي اسمي على ال Mercurial Vapor Elite؟"), ["price"])
        self.assertEqual(checks("The name printing is 16,500 EGP."), ["price"])
        # asking for the customer's name is no talk of the printing: the order total stands beside it
        for reply in ("Please confirm your name and address: the total is 16,560 EGP.",
                      "اكتبلي اسمك والعنوان والاجمالي 16560 جنيه"):
            self.assertEqual(checks(reply, "Mercurial Vapor 17 Elite"), [], reply)

    def test_extra_words_come_from_the_extra_data(self):
        items = store.catalogue()
        self.assertEqual(factcheck.extra_words(store.extras()[0], items), ["name", "print", "sticker"])
        box = {"title": "Beyond the Limits Gift Box", "type": "Packaging",
               "description": "A premium wrapping with a ribbon.", "variants": [{"price": "300"}]}
        boot = {"title": "Nike Phantom 6", "description": "The strike boot.",
                "variants": [{"tier": "Elite", "size": "43", "price": "16500"}]}
        with mock.patch.object(store, "catalogue", return_value=[boot, box]):
            self.assertEqual(factcheck.extra_words(box, [boot, box]), ["box", "gift", "packag", "premium",
                                                                      "ribbon", "wrapp"])
            self.assertEqual(checks("The gift box is 300 EGP."), [])
            self.assertEqual(checks("The Phantom 6 Elite is 300 EGP."), ["price"])
            self.assertEqual(checks("Printing is 300 EGP."), ["price"])    # print is no word of this extra


class ModelNumbers(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_a_model_number_is_no_price(self):
        for reply in ("Is the Vapor 17 in stock?", "is the Vapor 17", "Do you want the Superfly 11 Elite?",
                      "سعر الـ Vapor 17 كام؟", "The price of the Phantom 6 is 16,500 EGP.",
                      "The F50 is 19,500 EGP.", "Vapor-17 Elite: 16,500 EGP", "الـ Vapor ١٧ Elite بـ 16500 جنيه"):
            self.assertEqual(checks(reply), [], reply)
        self.assertEqual(factcheck.without_model_numbers("is the Vapor 17", store.catalogue()), "is the Vapor")

    def test_a_real_wrong_price_next_to_a_model_still_fails(self):
        for reply in ("The Vapor 17 is 17 EGP.", "The Vapor 17 Elite is 1,700 EGP.", "The Vapor 17,500 EGP.",
                      "The Vapor is 17 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_model_numbers_come_from_the_titles(self):
        future = {"title": "Puma Future 8", "variants": [{"tier": "Elite", "size": "43", "price": "9000"}]}
        with mock.patch.object(store, "catalogue", return_value=[future]):
            self.assertEqual(checks("The price of the Future 8 is 9,000 EGP."), [])
            self.assertEqual(checks("is the Vapor 17"), ["price"])   # no Vapor in this store: 17 is an amount


def setUpModule():
    # These pin a store with no offers, where the zone fees (60, 85) are facts; under free delivery they are
    # not (tests/test_offers_paths.py FactCheck).
    global _NO_OFFERS
    from kit import offers
    _NO_OFFERS = offers.OFFERS.set(offers.EMPTY)


def tearDownModule():
    from kit import offers
    offers.OFFERS.reset(_NO_OFFERS)
