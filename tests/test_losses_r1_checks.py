"""Holes the losses fixes of the send check opened, found by the red team (losses round 1, items 1 to 4 and 6)
and the reviewer (losses round 1, findings 1, 4 and 5), and the false positives those fixes closed, which
stay closed (tests/test_losses_checks.py). Every line below is made up."""
import unittest

from kit import send_check as sc

SIZES = [str(n) for n in range(39, 47)]
NAMES = ["Nike Mercurial Vapor 17", "Nike Phantom 6", "Beyond the Limits Name Printing"]
AMOUNTS = [16500, 400, 60, 85]


def kinds(reply, customer="", orders=()):
    return [n for n, _ in sc.named_problems(reply, customer, AMOUNTS, frozenset({"elite", "pro", "nike"}), SIZES,
                                            orders=orders, names=NAMES)]


class SaidOrderNumbers(unittest.TestCase):
    """Item 1, finding 4: a number the customer wrote with a # never hides a price."""

    def test_a_price_word_before_it_keeps_it_an_amount(self):
        for customer, reply in (("Please confirm the total of my order #14000", "The total of your order 14000 is confirmed."),
                                ("Please confirm my order #15000", "The price for your order 15000."),
                                ("طلبي رقم #14000 اتأكد لو سمحت", "اجمالي الطلب 14000"),
                                ("#١٤٠٠٠ ده رقم طلبي", "سعر الطلب 14000"),
                                ("my order #2500 is late", "Your order total: 2500"),
                                ("طلبي #2500 اتأخر", "اجمالي طلبك 2500"),
                                ("order #15000 please", "Se3r el order 15000.")):
            with self.subTest(reply=reply):
                self.assertIn("amounts", kinds(reply, customer))

    def test_a_bare_order_label_or_a_short_number_is_never_hidden(self):
        self.assertIn("amounts", kinds("Your order: 15000", "my order #15000 please"))
        self.assertIn("amounts", kinds("Delivery for your order 90.", "order #90 please"))
        self.assertIn("amounts", kinds("Your order is 90.", "cancel order #90"))

    def test_the_order_number_still_passes(self):
        said = "Please cancel my order #7015"
        for reply in ("Your order 7015 is cancelled.", "Your order number: 7015 is cancelled.", "طلبك رقم 7015 اتلغى"):
            with self.subTest(reply=reply):
                self.assertNotIn("amounts", kinds(reply, said))


class ListLeads(unittest.TestCase):
    """Item 2: a list item that opens with a fee under a priced heading is read."""

    def test_a_fee_opening_a_list_item(self):
        for reply, n in (("Delivery fees:\n1. 70 for Cairo\n2. 90 for Alex", [70, 90]),
                         ("Delivery:\n1. 70 Cairo and Giza\n2. 95 other governorates", [70, 95]),
                         ("التوصيل:\n1. 70 للقاهرة\n2. 95 للمحافظات", [70, 95]),
                         ("Delivery fees:\n1. 60 for Cairo\n\n2. 90 for Alex", [60, 90])):
            with self.subTest(reply=reply):
                self.assertEqual(sorted(sc.prices_in(reply, SIZES, (), NAMES)), n)

    def test_what_is_not_a_fee_stays_out(self):
        self.assertEqual(sc.prices_in("Options:\n1. 70 Cairo\n2. 90 Alex", SIZES, (), NAMES), [])  # no price word
        self.assertEqual(sc.prices_in("Delivery fees:\n1. 3 days to Cairo\n2. 5 days to Aswan", SIZES, (), NAMES), [])
        self.assertEqual(sc.prices_in("Prices:\n1. 2 stickers for 400 EGP\n2. 1 boot", SIZES, (), NAMES), [400])
        self.assertEqual(sc.prices_in("Total:\n1. Nike Phantom 6\n2. Nike Mercurial Vapor 17", SIZES, (), NAMES), [])

    def test_a_lone_list_opener_stays_readable(self):
        self.assertEqual(sc.prices_in("Delivery:\n1. Cairo"), [1])


class Ranges(unittest.TestCase):
    """Item 3, finding 1: a time word marks a range as days only in its clause, with no price between."""

    def test_a_range_in_another_clause_or_after_a_price_word_is_an_amount(self):
        for reply in ("Delivery time is 2-3 days, and your discount is 10-20.",
                      "Delivery time: 2-3 days. The printing fee is 20-25.",
                      "Delivery takes 1-2 days and costs 10-15", "الشحن 2-3 أيام بـ 25-30",
                      "مدة التوصيل 2-3 أيام والشحن 20-30", "مدة التوصيل ٢-٣ أيام والشحن ٢٠-٣٠",
                      "el tawsil 2-3 ayam w el sha7n 20-30", "التوصيل خلال يومين الى 3 أيام والشحن من 15 الى 25",
                      "التوصيل من يوم لـ 3 ايام والشحن من 20 لـ 30"):
            with self.subTest(reply=reply):
                self.assertIn("amounts", kinds(reply))

    def test_a_day_or_a_big_number_is_an_amount(self):
        for reply in ("Delivery is a day or 90.", "التوصيل يوم أو 90", "El tawseel youm aw 90.",
                      "Delivery is a day or 90 to Alex, and 2 to 4 days for other cities.",
                      "Delivery is a day or 50 for express.", "Delivery is a day or 5 for express."):
            with self.subTest(reply=reply):
                self.assertIn("amounts", kinds(reply))
        self.assertEqual(sc.prices_in("Delivery a day or 150", priced_only=True), [150])

    def test_a_range_that_runs_down_or_a_time_word_on_an_earlier_line(self):
        self.assertEqual(sc.prices_in("Delivery days: 5-2"), [5])
        self.assertEqual(sc.prices_in("Delivery days\nfee 10-20"), [10])

    def test_times_still_pass(self):
        for reply in ("مدة التوصيل: 2-3", "Delivery days: 1-2", "Delivery is a day or 2.", "Delivery takes a day or 2",
                      "التوصيل خلال يوم أو 2", "Delivery time is 2-3"):
            with self.subTest(reply=reply):
                self.assertEqual(sc.prices_in(reply, SIZES, (), NAMES), [])


class QuantityStock(unittest.TestCase):
    """Item 4, finding 5: الكمية then a number is a stock count unless the sentence is an order summary."""

    def test_stock_counts_with_the_quantity_word(self):
        for reply in ("الكمية عندنا 2", "الكمية المتاحة حاليا 2", "الكمية بالمخزن 2", "الكمية المتبقية 2", "الكمية 2 لسه",
                      "الكمية دلوقتي 2 في مقاس 43", "فاضل كام؟ الكمية 2", "الكمية المتاحة من مقاس 43 هي 2",
                      "الكمية 3 متاحة من مقاس 42", "الكمية ٣ متاحة", "الكمية 3 موجودة", "الكمية اللي عندنا 3",
                      "الكمية عندنا 3 بس", "el kemya 3 mawgoda"):
            with self.subTest(reply=reply):
                self.assertTrue(sc.stock_counts(reply, SIZES, (), NAMES), reply)

    def test_an_order_summarys_quantity_still_passes(self):
        for reply in ("Nike Phantom 6 Elite مقاس 42، الكمية 1، السعر 16500 جنيه", "الكمية 2 والاجمالي 33000 جنيه",
                      "طلبك: الكمية 1"):
            with self.subTest(reply=reply):
                self.assertEqual(sc.stock_counts(reply, SIZES, (), NAMES), [])


class CountNouns(unittest.TestCase):
    """Item 6, finding 1: only a short list of count nouns makes a single digit a count."""

    def test_a_single_digit_amount_fails(self):
        for reply in ("The discount is 5 percent.", "Your discount is for 5 percent off the Elite.", "The boots are 9 grand.",
                      "Printing is 4 mia.", "The Elite is 9 grand.", "Elite for 9 bucks", "We can do it at 5 percent off.",
                      "الـ Elite بـ 7 ونص", "الـ Elite بـ ٧ ونص", "الـ Pro بـ 9 وخمسمية", "el Elite b 7 w nos",
                      "el Elite b 9 alaaf", "We have it in 3 colours for 9 quid.", "الخصم بـ 5 بالمية",
                      "Printing is 0 stickers."):
            with self.subTest(reply=reply):
                self.assertTrue({"amounts", "digits"} & set(kinds(reply)), reply)

    def test_counts_still_pass(self):
        for reply in ("The Phantom 6 is available in 3 tiers.", "The printing is 400 EGP for 2 stickers.",
                      "The Phantom 6 comes in 4 colours."):
            with self.subTest(reply=reply):
                self.assertNotIn("amounts", kinds(reply))


if __name__ == "__main__":
    unittest.main()
