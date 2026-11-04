"""Arena run 20261104T143545, cause 5: on a situation that expects the exchange line, the day check lets
the exchange days through anywhere in the reply, so the two checks never ask for opposite things. Made-up
text only, no network."""
import unittest

from reflection import exam


def did(reply, tools=()):
    return {"reply": reply, "tools": list(tools)}


class ExchangeDays(unittest.TestCase):
    EXCHANGE = {"expect": {"exchange": True}}
    OTHER = {"expect": {}}

    def test_the_exchange_days_pass_where_the_exchange_line_is_asked(self):
        for reply in ("Momken teghayar el size khilal 14 yom law matlbestosh.",
                      "Sure. 14 days, unworn and in its packaging.",
                      "تقدر تغير المقاس خلال 14 يوم لو متلبسش."):
            with self.subTest(reply=reply):
                self.assertEqual(exam.check_days_from_tools(self.EXCHANGE, did(reply)), "")

    def test_elsewhere_and_other_numbers_still_fail(self):
        self.assertIn("(14)", exam.check_days_from_tools(self.OTHER, did("Sure. 14 days, unworn and in its packaging.")))
        self.assertIn("(14)", exam.check_days_from_tools(self.EXCHANGE, did("Delivery takes 14 days.")))
        self.assertIn("(3)", exam.check_days_from_tools(self.EXCHANGE, did("Delivery takes 3 days. Exchange in 14 days.")))
        self.assertEqual(exam.check_days_from_tools(self.EXCHANGE, did("Delivery takes 3 days.", [("delivery", {"days_max": 3})])),
                         "")


if __name__ == "__main__":
    unittest.main()
