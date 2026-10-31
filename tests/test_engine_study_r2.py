"""Fixes from review t261029l round 2 (29 Oct): a pulled line never comes back on its own.

Lines are compared on their words alone, so punctuation, case and accents make no new line,
and a small rewording of a pulled line waits for a yes. Offline, on the plant waterer plug,
in memory SQLite.
"""
import unittest

from engine import risk
from engine.lessons import DAY, Lessons, TRYING, WAITING
from engine.log import Log
from engine.study import PULLED_BEFORE, Study
from kit.db import Db
from tests import plugs
from tests import study_fakes as fk


def always_low(text, hidden, letters):
    return risk.LOW


class PulledLineTest(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        fk.beds(Log(self.db, self.plug))
        self.les = Lessons(self.db, self.plug, judge=always_low)
        first = self.night(fk.EARLY)["cards"][0]["lesson_id"]
        self.les.pull(first, "faded")

    def night(self, *cands, now=fk.NOW):
        study = Study(self.db, self.plug, proposer=fk.Proposer(*cands), tagger=fk.Tagger(), lessons=self.les)
        return study.run(fk.SINCE, fk.UNTIL, now=now)

    def again(self, line):
        return self.night(fk.candidate(fk.EARLY, lesson=line), now=fk.NOW + 2 * DAY)

    def test_punctuation_and_case_make_no_new_line(self):
        for line in ("Water the beds early in the morning", "Water the beds early in the morning!",
                     "Water the beds early, in the morning.", "WATER the beds early in the morning..."):
            with self.subTest(line=line):
                rep = self.again(line)
                self.assertEqual([c["verdict"] for c in rep["candidates"]], [PULLED_BEFORE])
                self.assertEqual(rep["cards"], [])
                self.assertEqual(len(self.les.mine()), 1)

    def test_a_small_rewording_waits_for_a_yes(self):
        for line in ("Water the beds early in the mornings.", "Water the beds early each morning."):
            with self.subTest(line=line):
                rep = self.again(line)
                card = rep["cards"][0]
                self.assertEqual(card["state"], WAITING)
                self.assertEqual(card["close_to_pulled"], "Water the beds early in the morning.")
                self.assertIsNone(card["waits_for"])  # waiting for a yes on the pulled line, not its turn
                self.les.pull(card["lesson_id"], "test")

    def test_the_same_words_in_another_order_wait_for_a_yes(self):  # call 4A, 29 Oct
        for line in ("In the morning, water the beds early.", "Early in the morning water the beds."):
            with self.subTest(line=line):
                card = self.again(line)["cards"][0]
                self.assertEqual((card["state"], card["close_to_pulled"]),
                                 (WAITING, "Water the beds early in the morning."))
                self.les.pull(card["lesson_id"], "test")

    def test_the_same_words_with_some_said_twice_are_not_the_same_words(self):
        card = self.again("In the morning in the morning, water the beds the beds early early.")["cards"][0]
        self.assertEqual((card["state"], card["close_to_pulled"]), (TRYING, None))

    def test_a_different_line_still_tries(self):
        rep = self.again("Water the beds late in the evening.")
        card = rep["cards"][0]
        self.assertEqual(card["state"], TRYING)
        self.assertIsNone(card["close_to_pulled"])


class ArabicPulledLineTest(PulledLineTest):
    """The same rule on an Arabic line: short vowels and Arabic punctuation make no new line."""

    LINE = "اسقِ الأحواض بدري الصبح."

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        fk.beds(Log(self.db, self.plug))
        self.les = Lessons(self.db, self.plug, judge=always_low)
        first = self.night(fk.candidate(fk.EARLY, lesson=self.LINE))["cards"][0]["lesson_id"]
        self.les.pull(first, "faded")

    def test_punctuation_and_case_make_no_new_line(self):
        for line in ("اسق الأحواض بدري الصبح", "اسقِ الأحواض، بدري الصبح!"):
            with self.subTest(line=line):
                rep = self.again(line)
                self.assertEqual([c["verdict"] for c in rep["candidates"]], [PULLED_BEFORE])
                self.assertEqual(len(self.les.mine()), 1)

    def test_a_small_rewording_waits_for_a_yes(self):
        card = self.again("اسقِ الأحواض بدري كل صبح.")["cards"][0]
        self.assertEqual(card["state"], WAITING)
        self.assertEqual(card["close_to_pulled"], self.LINE)

    def test_the_same_words_in_another_order_wait_for_a_yes(self):
        card = self.again("الصبح بدري، اسقِ الأحواض.")["cards"][0]
        self.assertEqual((card["state"], card["close_to_pulled"]), (WAITING, self.LINE))

    def test_the_same_words_with_some_said_twice_are_not_the_same_words(self):
        card = self.again("الصبح الصبح بدري بدري اسق الأحواض الأحواض.")["cards"][0]
        self.assertEqual((card["state"], card["close_to_pulled"]), (TRYING, None))

    def test_a_different_line_still_tries(self):
        card = self.again("حط غطا على الحوض قبل الري.")["cards"][0]
        self.assertEqual(card["state"], TRYING)


if __name__ == "__main__":
    unittest.main()
