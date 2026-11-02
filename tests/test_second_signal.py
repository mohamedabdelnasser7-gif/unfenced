"""The second signal (DECISIONS items 67 and 73): a result such as delivered stays on its own case
and decides nothing. A second signal row saved tonight never pulls an old case into the study
window (engine/log.py window), and no page counts it per pattern: a night reads 2 days and these
results land 2 to 7 days later, so a saved card that still carries the old counts shows none."""
import unittest

from engine import study
from reflection import pages
from reflection import PLUG as SALES
from tests.test_morning import NOW, Base

DAY = 86400.0


class Window(unittest.TestCase):
    """Review late r1 finding 2: a second signal row saved tonight on an old good Sales case (a page
    mark, a sheet, the courier) must not pull that case into tonight's study window; a slow deciding
    result still pulls its case in (engine/log.py window)."""

    def setUp(self):
        from kit.db import Db
        from engine.log import Log
        from tests import plugs
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.sales = Log(self.db, SALES)
        self.shipper = plugs.load(plugs.SHIPPER, self)
        self.ship = Log(self.db, self.shipper)
        self.since, self.until = NOW - 30 * DAY, NOW + 60

    def order(self, case, at):
        self.sales.act(case, SALES.result("order_created").after, result="order_created", stage="ordering",
                       detail={"order": "#1001", "store": "shopify"}, at=at)

    def test_a_second_signal_tonight_leaves_an_old_good_case_out(self):
        self.order("old", NOW - 40 * DAY)
        self.order("new", NOW - DAY)
        before = study._counts(SALES, study._read(SALES, self.sales.window(self.since, self.until), self.until))
        self.sales.result("old", "delivered", at=NOW)
        self.sales.result("new", "refused", at=NOW)
        win = self.sales.window(self.since, self.until)
        self.assertEqual(list(win), ["new"])
        self.assertEqual([r["result"] for r in win["new"]], ["order_created", "refused"])  # still read in full
        after = study._counts(SALES, study._read(SALES, win, self.until))
        self.assertEqual((after["read"]["cases"], after["decided"]), (before["read"]["cases"], before["decided"]))

    def test_another_agents_plug_is_named_for_its_second_signal(self):
        self.order("old", NOW - 40 * DAY)
        self.sales.result("old", "delivered", at=NOW)
        self.assertEqual(self.ship.window(self.since, self.until, agent=SALES.agent, plug=SALES), {})

    def test_a_slow_deciding_result_still_pulls_its_case_in(self):
        self.ship.act("p1", "ship", result="shipped", stage="sending", at=NOW - 40 * DAY)
        self.ship.result("p1", "delivered", at=NOW)
        win = self.ship.window(self.since, self.until)
        self.assertEqual([r["result"] for r in win["p1"]], ["shipped", "delivered"])


class NotPerPattern(Base):
    def test_an_old_card_with_counts_shows_no_line_on_either_page(self):
        lid = self.high("Water 3 times a day.")
        self.report("waterer", NOW, cards=[{"lesson_id": lid, "sure": 0.9,
                                            "cases": {"with": 9, "without": 9, "good_with": 7, "good_without": 3},
                                            "second": {"delivered": 4, "none": 1}}])
        a3 = self.page()
        two = pages.Pages(self.morning).get("/", {}, "t0ken")
        for page in (a3, two):
            self.assertIn("Water 3 times a day.", page)
            self.assertNotIn("How its good cases did later", page)
            self.assertNotIn("4 delivered", page)


if __name__ == "__main__":
    unittest.main()
