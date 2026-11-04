"""False positives of the send check found in the Arena run 20261104T120239 (14 of 23 lessons refused on
"amounts", 13 turns with no safe reply after the order summary), and the shapes that must still fail.

The send check is shared: Sales, every built agent with the full check, and the exam (reflection/exam.py
"amounts" and "stock_count" read named_problems), so each fix here reaches all of them. Every line below
is made up."""
import unittest

from kit import send_check as sc
from kit.tools import store
from reflection import exam
from tests.fake_model import clean_env

SIZES = [str(n) for n in range(39, 47)]
NAMES = ["Nike Mercurial Vapor 17", "Nike Phantom 6", "Beyond the Limits Name Printing"]
AMOUNTS = [16500, 400, 60]


def amounts(reply, customer="", orders=()):
    return [why for name, why in sc.named_problems(reply, customer, AMOUNTS, frozenset(), SIZES, orders=orders,
                                                   names=NAMES) if name == "amounts"]


class RangesAreTimes(unittest.TestCase):
    def test_arabic_range_words_before_a_unit(self):
        for reply in ("التوصيل خلال 1 الى 2 يوم", "التوصيل خلال 2 إلى 3 أيام", "الشحن من 2 لحد 4 أيام",
                      "التوصيل من 2 لغاية 3 أيام", "التوصيل بياخد من 2 حتى 4 ايام",
                      "التوصيل للاسكندرية 2 الى 3 ايام"):
            with self.subTest(reply=reply):
                self.assertEqual(sc.prices_in(reply, SIZES, (), NAMES), [])

    def test_a_range_led_by_a_time_word_on_its_line(self):
        for reply in ("مدة التوصيل: 1 الى 2 يوم", "مدة التوصيل: 2-3", "Delivery days: 1-2", "التوصيل خلال يوم أو 2",
                      "Delivery takes a day or 2"):
            with self.subTest(reply=reply):
                self.assertEqual(sc.prices_in(reply, SIZES, (), NAMES), [])

    def test_wrong_amounts_near_times_still_fail(self):
        for reply, n in (("Delivery time: 70", [70]), ("Delivery time: 75-80", [75]), ("Delivery: 3-1", [3]),
                         ("التوصيل 70 الى 3 ايام", [70]), ("التوصيل 75 جنيه وبيوصل في 2 الى 3 ايام", [75])):
            with self.subTest(reply=reply):
                self.assertEqual(sc.prices_in(reply, SIZES, (), NAMES), n)
                self.assertTrue(amounts(reply))


class NumberedLists(unittest.TestCase):
    def test_list_numbers_are_not_amounts(self):
        reply = ("Prices:\n1. Nike Phantom 6 for 16,500 EGP\n2. Name printing for 400 EGP\n"
                 "3. Delivery to Cairo for 60 EGP")
        self.assertEqual(amounts(reply), [])
        self.assertEqual(amounts("Options for you:\n1. Nike Phantom 6\n2. Nike Mercurial Vapor 17"), [])
        self.assertEqual(amounts("الأسعار:\n1) Nike Phantom 6 سعره 16500 جنيه\n2) الطباعة سعرها 400 جنيه"), [])

    def test_a_wrong_amount_inside_a_list_still_fails(self):
        why = amounts("Prices:\n1. Nike Phantom 6 for 15,900 EGP\n2. Name printing for 400 EGP")
        self.assertTrue(why and "15900" in why[0], why)
        why = amounts("Delivery fees:\n1. Cairo 75\n2. Alex 90")
        self.assertTrue(why and "75" in why[0] and "90" in why[0], why)

    def test_a_lone_number_at_a_line_start_still_counts(self):
        self.assertEqual(sc.prices_in("Delivery for you:\n70. Thanks"), [70])
        self.assertIn(2, sc.prices_in("Delivery for you:\n2. Cairo\n3. Alex"))  # no run from 1


class CountedThings(unittest.TestCase):
    def test_a_single_digit_count_after_a_weak_cue(self):
        for reply in ("The Phantom 6 is available in 3 tiers.", "The printing is 400 EGP for 2 stickers.",
                      "Name printing is 400 EGP for 2 stickers, 1 on each boot."):
            with self.subTest(reply=reply):
                self.assertEqual(amounts(reply), [])

    def test_a_single_digit_amount_still_fails(self):
        for reply in ("Delivery is 9 only.", "The boots are 9 each.", "Delivery is 5 extra.", "The boots are 5 thousand."):
            with self.subTest(reply=reply):
                problems = [n for n, _ in sc.named_problems(reply, "", AMOUNTS, frozenset(), SIZES, names=NAMES)]
                self.assertTrue({"amounts", "digits"} & set(problems), reply)
        self.assertEqual(sc.prices_in("The printing is for 25 stickers"), [25])  # two digits stay amounts


class OrderNumbers(unittest.TestCase):
    def test_the_customers_order_number_after_an_order_word(self):
        said = "Please cancel my order #7015"
        for reply in ("Your order 7015 is cancelled.", "I cancelled order number 7015 for you.",
                      "Order #7015 is cancelled.", "طلبك رقم 7015 اتلغى"):
            with self.subTest(reply=reply):
                self.assertEqual(amounts(reply, said), [])

    def test_the_customers_number_never_hides_an_amount(self):
        said = "Please cancel my order #7015"
        for reply in ("The total is 7015 EGP.", "Sure, 7015 is noted.", "Your order total is 7015."):
            with self.subTest(reply=reply):
                self.assertTrue(amounts(reply, said), reply)
        self.assertTrue(amounts("Your order 7015 is cancelled.", "Please cancel my order"))  # never said

    def test_a_tool_order_name_without_its_hash(self):
        self.assertEqual(amounts("Your order 1001 is placed, total 16,500 EGP.", orders=["#1001"]), [])
        self.assertTrue(amounts("Your order 1002 is placed.", orders=["#1001"]))


class QuantityIsNotStock(unittest.TestCase):
    def test_an_order_summarys_quantity(self):
        for reply in ("Nike Phantom 6 Elite مقاس 42، الكمية 1، السعر 16500 جنيه", "الكمية 2 والاجمالي 33000 جنيه"):
            with self.subTest(reply=reply):
                self.assertEqual(sc.stock_counts(reply, SIZES, (), NAMES), [])

    def test_stock_counts_still_fail(self):
        for reply in ("الكمية المتاحة 3", "الكمية المتوفرة منه 2", "الكمية 2 بس", "فاضل 2 بس", "Only 3 pairs left",
                      "المتاح 4"):
            with self.subTest(reply=reply):
                self.assertTrue(sc.stock_counts(reply, SIZES, (), NAMES), reply)


class ExamReadsTheSameCheck(unittest.TestCase):
    """The exam's amounts check is the send check's, so the shapes above pass it too."""

    def setUp(self):
        clean_env(self)

    def did(self, reply, customer=""):
        return {"reply": reply, "tools": [], "problems": dict(sc.named_problems(
            reply, customer, store.price_points(), store.vocabulary(), store.size_strings(), names=store.titles()))}

    def test_exam_amounts(self):
        self.assertEqual(exam.CHECKS["amounts"]({}, self.did("التوصيل خلال 1 الى 2 يوم")), "")
        self.assertNotEqual(exam.CHECKS["amounts"]({}, self.did("التوصيل خلال 1 الى 2 يوم والسعر 1350 جنيه")), "")

    def test_exchange_days_in_franco_and_english(self):
        days = exam.EXCHANGE_DAYS
        check = exam.CHECKS["days_from_tools"]
        for reply in (f"momken testabdel el size khelal {days} yom", f"el estebdal khelal {days} yom",
                      f"You can swap the size within {days} days."):
            with self.subTest(reply=reply):
                self.assertEqual(check({}, {"reply": reply, "tools": []}), "")
        for reply in (f"hywsal khelal {days} yom", "el estebdal khelal 30 yom", f"Delivery takes {days} days."):
            with self.subTest(reply=reply):
                self.assertNotEqual(check({}, {"reply": reply, "tools": []}), "")


if __name__ == "__main__":
    unittest.main()
