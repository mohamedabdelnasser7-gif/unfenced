"""Review late r1 finding 4: an idea from a plug that names no days still draws on the A3 page."""
import unittest

from reflection import morning


def card(shows):
    return {"whose": "user", "moves": {"result": "order_created", "shows_in_days": shows},
            "level": {"name": "careful", "share": 0.1, "days": 7},
            "must_not_worsen": {"results": [], "about": ""}, "know_in_days": 7.0, "sure": "low"}


class IdeaLines(unittest.TestCase):
    def test_no_days_drops_the_days_clause(self):
        out = morning._idea_lines(card(None))
        self.assertIn("It must move order_created; we know", out)
        self.assertNotIn("days after a case", out)

    def test_days_still_show(self):
        self.assertIn("days after a case", morning._idea_lines(card([1, 3])))


if __name__ == "__main__":
    unittest.main()
