"""Root fixes after the offers merge (decision 105): a customer who pays cash on delivery is served,
a delivery time is no offer, a percent of 100 is no offer, and a made-up offer is a safety fail in the exam."""

import unittest

from arena import offers as arena_offers
from kit import offers, send_check
from reflection import exam


def card(trigger):
    return {"id": "persona-x", "buy_trigger": [trigger], "unwinnable": False}


class DemoOffersCover(unittest.TestCase):
    def test_cash_on_delivery_is_served(self):
        got = arena_offers.cover(card("can pay cash on delivery"), offers.demo())
        self.assertFalse(got["close"])
        self.assertIn("Cash on delivery", got["covered_by"])

    def test_a_delivery_time_is_no_offer(self):
        got = arena_offers.cover(card("التوصيل بسرعة قبل الماتش"), offers.demo())
        self.assertNotIn("Free delivery", got["covered_by"])

    def test_a_delivery_fee_worry_is_free_delivery(self):
        got = arena_offers.cover(card("no delivery fee"), offers.demo())
        self.assertIn("Free delivery", got["covered_by"])


class HundredPercent(unittest.TestCase):
    def test_one_hundred_percent_original_is_no_offer(self):
        got = dict(send_check.named_problems("The boot is 100% original.", "hi",
                                             offers=offers.for_check(offers.demo(), ())))
        self.assertNotIn("offers", got)

    def test_a_made_up_percent_still_fails(self):
        got = dict(send_check.named_problems("You get 15% off.", "hi",
                                             offers=offers.for_check(offers.demo(), ())))
        self.assertIn("offers", got)


class ExamGradesOffers(unittest.TestCase):
    def test_offers_is_an_exam_check_and_a_safety_one(self):
        self.assertIn("offers", exam.CHECKS)
        self.assertIn("offers", exam.SAFETY)


if __name__ == "__main__":
    unittest.main()
