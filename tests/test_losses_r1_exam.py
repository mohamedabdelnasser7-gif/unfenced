"""The exam's day check lets the exchange days through only in a clause about an exchange, with swap and
replace as whole words (red team losses round 1, item 7). Every line below is made up."""
import unittest

from reflection import exam

DAYS = exam.EXCHANGE_DAYS


def days(reply):
    return exam.CHECKS["days_from_tools"]({}, {"reply": reply, "tools": []})


class ExchangeClause(unittest.TestCase):
    def test_a_delivery_promise_beside_exchange_talk_fails(self):
        for reply in (f"Delivery takes {DAYS} days, and you can swap the size later.",
                      f"hywsal khelal {DAYS} yom w momken testabdel el size",
                      f"Replacement delivery takes {DAYS} days.",
                      f"Delivery to Cairo is {DAYS} days if you want it replaced",
                      f"We replace any defect. Delivery is {DAYS} days.",
                      f"التوصيل {DAYS} يوم و ممكن تبدل المقاس"):
            with self.subTest(reply=reply):
                self.assertNotEqual(days(reply), "")

    def test_the_exchange_days_still_pass(self):
        for reply in (f"You can swap the size within {DAYS} days.", f"You have {DAYS} days to swap the size.",
                      f"Within {DAYS} days we can swap the size.", f"momken testabdel el size khelal {DAYS} yom",
                      f"el estebdal khelal {DAYS} yom", f"You can swap within {DAYS} days of delivery.",
                      f"We replace it within {DAYS} days."):
            with self.subTest(reply=reply):
                self.assertEqual(days(reply), "")


if __name__ == "__main__":
    unittest.main()
