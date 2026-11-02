"""The second signal, shown only (DECISIONS item 67): engine/study.py second_counts on a pattern's
good cases, the night report's line under each candidate (reflection/night.py candidate_lines),
the saved card's counts checked on the way in (reflection/morning.py second) and the line on both
pages' cards. Nothing here decides a case, a pattern or a gate."""
import unittest

from engine import study
from reflection import morning as mo
from reflection import night
from reflection import pages
from reflection import PLUG as SALES
from tests.test_morning import NOW, Base

GOOD_CASE = study.GOOD


class Case:
    def __init__(self, status, *results):
        self.status, self.rows = status, [{"result": r} for r in results]


class Counts(unittest.TestCase):
    def test_good_cases_only_and_the_last_second_result_counts(self):
        cases = [Case(GOOD_CASE, "order_created", "delivered"), Case(GOOD_CASE, "order_created", "refused"),
                 Case(GOOD_CASE, "order_created", "delivered", "refused"), Case(GOOD_CASE, "order_created"),
                 Case(study.BAD, "chat_closed", "refused")]
        self.assertEqual(study.second_counts(SALES, cases), {"delivered": 1, "refused": 2, "none": 1})

    def test_no_second_signal_no_counts(self):
        from tests import plugs
        self.assertIsNone(study.second_counts(plugs.load(plugs.WATERER, self), [Case(GOOD_CASE, "x")]))

    def test_the_night_line_under_a_candidate(self):
        c = {"pattern": "asks the size", "verdict": "lesson", "chance": 0.9,
             "with": {"cases": 9, "good": 7, "sources": 3}, "without": {"cases": 9, "good": 3, "sources": 3},
             "second": {"delivered": 5, "refused": 1, "none": 1}}
        lines = night.candidate_lines(c, "order_created")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1].strip(), "How its good cases did later, shown only: 5 delivered, 1 refused, "
                                           "1 with no result yet.")
        del c["second"]
        self.assertEqual(len(night.candidate_lines(c, "order_created")), 1)


class Checked(unittest.TestCase):
    def test_only_small_whole_counts_pass(self):
        self.assertEqual(mo.second({"second": {"none": 2, "delivered": 3}}), {"delivered": 3, "none": 2})
        for bad in (None, [], {}, {"x": -1}, {"x": True}, {"x": 1.5}, {"": 1}, {"x" * 41: 1},
                    {f"k{n}": 1 for n in range(13)}, {"delivered": 0, "none": 0}):
            with self.subTest(bad=bad):
                self.assertIsNone(mo.second({"second": bad}))
        self.assertIsNone(mo.second("not a card"))


class OnTheCards(Base):
    def test_both_pages_show_the_line_escaped(self):
        lid = self.high("Water 3 times a day.")
        self.report("waterer", NOW, cards=[{"lesson_id": lid, "sure": 0.9,
                                            "cases": {"with": 9, "without": 9, "good_with": 7, "good_without": 3},
                                            "second": {"<b>held</b>": 4, "none": 1}}])
        a3 = self.page()
        two = pages.Pages(self.morning).get("/", {}, "t0ken")
        for page in (a3, two):
            self.assertIn("How its good cases did later, shown only: 4 &lt;b&gt;held&lt;/b&gt;, 1 with no result yet.",
                          page)
            self.assertNotIn("<b>held", page)

    def test_no_counts_no_line(self):
        lid = self.high("Water 3 times a day.")
        self.report("waterer", NOW, cards=[{"lesson_id": lid, "sure": 0.9,
                                            "cases": {"with": 9, "without": 9, "good_with": 7, "good_without": 3}}])
        self.assertNotIn("How its good cases did later", self.page())


if __name__ == "__main__":
    unittest.main()
