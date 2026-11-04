"""The levels seal check's findings (review levels seal check items 1 to 5): a folder whose three record
files were all deleted, or left with none by a crash inside Start a new test set, counts every saved
practice customer as trained, so none of them joins the next test set. Fake models only."""
import os
from unittest import mock

from arena import practice, run
from tests import test_levels_testset as testset  # the module, so its tests are not run twice
from tests.test_customers_shape import Base

NAME = "support_calm_helper"


class DeleteAll(Base):
    """Item 1: a fresh agent has no practice customer saved when its roster is first made, so a folder
    with customers and no roster has trained them."""
    practise = testset.Kept.practise

    def trained_ids(self, folder):
        return {c for c, _ in practice.trained(folder)}

    def test_deleting_all_three_record_files_never_tests_a_customer_that_trained(self):
        for name in self.folders:
            for how in ("deleted", "matches left empty", "quick first"):
                with self.subTest(name=name, how=how):
                    self.setUp()
                    folder = self.folders[name]
                    if how == "quick first":
                        self.practise(name, quick=True)
                    self.practise(name, 20, 10)
                    before = self.trained_ids(folder)
                    self.assertTrue(before)
                    for f in (practice.TEST_FILE, practice.ROSTER_FILE, run.MATCHES_FILE):
                        (folder / f).unlink()
                    if how == "matches left empty":
                        (folder / run.MATCHES_FILE).write_text("", encoding="utf-8")
                    rep = self.practise(name, 30, 20)
                    self.assertEqual(len(rep["held_out_cards"]), 20)
                    self.assertFalse(set(rep["held_out_cards"]) & before)
                    self.assertLessEqual(before, self.trained_ids(folder))  # on the new roster

    def test_a_crash_between_the_renames_of_a_new_test_set_never_tests_a_customer_that_trained(self):
        real = os.replace
        for tear in ("roster gone", "test set torn"):
            crashed = 0
            for n in range(1, 10):  # each rename in turn: the old files set aside, the new roster, the new matches
                with self.subTest(tear=tear, crash_at=n):
                    self.setUp()
                    folder = self.folders[NAME]
                    self.practise(NAME, 20, 10)
                    before = self.trained_ids(folder)
                    if tear == "roster gone":
                        (folder / practice.ROSTER_FILE).unlink()  # beside sealed lines
                    else:
                        (folder / practice.TEST_FILE).write_text('{"test": [', encoding="utf-8")
                    seen = []

                    def crash(a, b):
                        seen.append(a)
                        if len(seen) == n:
                            raise OSError("the machine stopped here")
                        return real(a, b)
                    try:
                        with mock.patch.object(practice.os, "replace", crash):
                            practice.new_test_set(folder)
                        break  # n is past the last rename: every crash point was tried
                    except OSError:
                        crashed += 1
                    try:
                        rep = self.practise(NAME, 30, 20)
                    except practice.Unrecorded:  # still torn: the way on is a new test set, run whole this time
                        practice.new_test_set(folder)
                        rep = self.practise(NAME, 30, 20)
                    self.assertFalse(set(rep["held_out_cards"]) & before)
            self.assertEqual(crashed, 4 if tear == "roster gone" else 5)

if __name__ == "__main__":
    import unittest
    unittest.main()
