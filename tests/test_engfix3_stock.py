"""Arena run 20261104T143545, cause 7: the Arena fact check fails a reply that says a product is in stock
(Arabic, Franco or English) when the store gives no stock data for it; the honest "I cannot confirm stock"
passes, and nothing is filled in. Made-up store only, no network."""
import unittest
from unittest import mock

from arena import factcheck
from kit.tools import store

ITEMS = [
    {"title": "Zeta Runner 3", "type": "Boots", "variants": [  # untracked: no stock field
        {"tier": "Gold", "size": "42", "price": "9000"}, {"tier": "Gold", "size": "44", "price": "9000"}]},
    {"title": "Kappa Glide", "type": "Boots", "variants": [  # tracked
        {"tier": "Gold", "size": "42", "price": "8000", "stock": "in stock"},
        {"tier": "Gold", "size": "44", "price": "8000", "stock": "few left"}]},
    {"title": "Name Printing", "type": "Extra", "variants": [{"price": "300"}]},
]


def stock_fails(reply, customer=""):
    with mock.patch.object(store, "catalogue", return_value=ITEMS):
        return [f for f in factcheck.check(reply, customer) if f["check"] == "stock"]


class NoStockData(unittest.TestCase):
    def test_in_stock_with_no_stock_data_fails(self):
        for reply, customer in (
                ("The Zeta Runner is in stock.", ""),
                ("Zeta Runner size 42 is available.", ""),
                ("Yes, it is in stock in size 44.", "Is the Zeta Runner there?"),
                ("ايوه متوفر مقاس 42.", "عندك Zeta Runner؟"),
                ("Aywa mawgoud fel stock.", "fi Zeta Runner?"),
                ("Zeta Runner metwafra ma2as 42.", ""),
                ("الـ Zeta Runner موجود في المخزن.", "")):
            with self.subTest(reply=reply):
                fails = stock_fails(reply, customer)
                self.assertTrue(fails and "no stock data" in fails[0]["why"], fails)

    def test_honest_and_other_replies_pass(self):
        for reply, customer in (
                ("I cannot confirm stock for the Zeta Runner, it is listed in size 42.", ""),
                ("I can't confirm the Zeta Runner is in stock.", ""),
                ("مش متأكد إن الـ Zeta Runner متوفر، هو موجود في الكتالوج.", ""),
                ("mesh met2aked en el Zeta Runner mawgood.", ""),
                ("The Zeta Runner is 9000 EGP. Cash on delivery is available.", ""),
                ("Zeta Runner: delivery is available to every governorate.", ""),
                ("Name Printing is available for 300 EGP.", ""),
                ("Is the Zeta Runner in size 42 available for you?", ""),
                ("The Kappa Glide is in stock in size 42.", ""),
                ("The Zeta Runner is sold out.", "")):
            with self.subTest(reply=reply):
                self.assertEqual(stock_fails(reply, customer), [])

    def test_tracked_out_still_fails(self):
        items = [dict(ITEMS[1], variants=[{"tier": "Gold", "size": "42", "price": "8000", "stock": "out"}])]
        with mock.patch.object(store, "catalogue", return_value=items):
            self.assertEqual([f["check"] for f in factcheck.check("Kappa Glide size 42 is in stock.")], ["stock"])


if __name__ == "__main__":
    unittest.main()
