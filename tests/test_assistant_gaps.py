"""The assistant's three closed gaps (new, 2026-10-31; DECISIONS items 30, 32, 36, 38): lessons
only from the user's corrections, the user's finished days reaching the Arena at night, and
meeting prep notes that never go anywhere."""
import time
import unittest

from assistant import PLUG, arena, simday
from engine import study
from engine.log import Log
from kit.db import Db
from tests.assistant_fakes import Helper

LATER = time.time() + 365 * 86400  # long past every deciding window


def closed(model, seed):
    """A simulated day played and closed into a fresh log: (log, case id, desk)."""
    db = Db(":memory:")
    log = Log(db, PLUG)
    day = simday.build_day(seed)
    desk, _, judged = arena.play_day(day, model=model, log=log)
    arena.close_day(log, arena.case_of(day), desk, judged)
    return db, log, arena.case_of(day), desk, judged


class LessonsOnlyFromCorrections(unittest.TestCase):
    def test_only_a_correction_settles_a_day_as_bad(self):
        self.assertEqual(PLUG.decides.bad, ("corrected",))
        self.assertTrue({"urgent_missed", "clash", "corrected"} <= set(PLUG.harm.results))

    def test_a_miss_only_the_code_found_is_left_out_never_bad(self):
        db, log, case, desk, judged = closed(Helper(miss_urgent=True), 3)
        self.addCleanup(db.close)
        self.assertFalse(judged["won"])
        self.assertFalse(any(a["kind"] == "corrected" for a in desk.answers))
        rows = log.case(case)
        status, deciding, causes, _ = study.settle(PLUG, rows, LATER)
        self.assertEqual((status, deciding, causes), (study.LEFT_OUT, None, ["only_code"]))
        # the code-found results stay harm for a trial: they carry no cause
        self.assertTrue([r for r in rows if r["result"] == "urgent_missed"])
        self.assertTrue(all(r["cause"] is None for r in rows if r["result"] in ("urgent_missed", "clash")))

    def test_a_day_the_user_corrected_is_bad_and_a_clean_day_is_good(self):
        db, log, case, desk, _ = closed(Helper(long_drafts=True), 3)
        self.addCleanup(db.close)
        self.assertTrue(any(a["kind"] == "corrected" for a in desk.answers))
        self.assertEqual(study.settle(PLUG, log.case(case), LATER)[:2], (study.BAD, "corrected"))
        db2, log2, case2, _, judged2 = closed(Helper(), 5)
        self.addCleanup(db2.close)
        self.assertTrue(judged2["won"])
        self.assertEqual(study.settle(PLUG, log2.case(case2), LATER)[:2], (study.GOOD, "day_clean"))


if __name__ == "__main__":
    unittest.main()
