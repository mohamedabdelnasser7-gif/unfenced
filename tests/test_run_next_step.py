"""A run that stops at the cap says its next step (decision 75): the quick limit, or the day's reset and --cap."""
import unittest

from arena import run


class NextStep(unittest.TestCase):
    def rep(self, **calls):
        return {"stopped": run.CAP, "calls": calls}

    def test_day_cap_names_the_reset_and_the_flag(self):
        step = run.next_step(self.rep(day="2026-11-02", used=1000, cap=1000))
        self.assertIn("2026-11-03", step)
        self.assertIn("--cap", step)

    def test_quick_limit_says_run_without_quick(self):
        step = run.next_step(self.rep(day="2026-11-02", cap=1000, run_limit=80, run_used=80))
        self.assertIn("without --quick", step)

    def test_no_line_when_not_capped_or_count_broken(self):
        self.assertEqual(run.next_step({"stopped": run.ROUNDS, "calls": {}}), "")
        self.assertEqual(run.next_step(self.rep(problem="count file unreadable", cap=1000)), "")



if __name__ == "__main__":
    unittest.main()
