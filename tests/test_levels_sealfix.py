"""The levels seal check's findings (review levels seal check items 1 to 5): a folder whose three record
files were all deleted, or left with none by a crash inside Start a new test set, counts every saved
practice customer as trained, so none of them joins the next test set; a correction's practice round
never plays a saved test customer; the refusal when too few customers are left names lowering the
level, and Start a new test set warns when the 99 customer cap leaves too few at the agent's level;
the seal check on a test line with no roster, the record check on a quick run and keep_trained's
refusal when the roster is gone are pinned; the command line starts a new test set with --new-test-set,
and its refusal on a torn record names it. Fake models only."""
import contextlib
import io
import json
import os
import shutil
from unittest import mock

from arena import gate, levels, madeup, practice, run
from kit import seal, turn
from reflection import morning as mo
from tests import test_levels_tab
from tests import test_levels_testset as testset  # the module, so its tests are not run twice
from tests.test_customers_shape import Base, Writer

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


class CorrectionRoundCards(Base):
    """Item 2: the test customers only ever play in the gate's own test matches."""
    practise = testset.Kept.practise

    def round_of(self, folder, writer=None):
        cr = gate.CorrectionRound.__new__(gate.CorrectionRound)
        cr.folder, cr.agent, cr.customer_model = folder, turn.load(folder), writer or Writer()
        cr.matches = gate.ROUND_MATCHES
        return cr

    def test_a_correction_round_never_plays_a_saved_test_customer(self):
        for name in self.folders:
            for shape in ((20, 10), (30, 20)):
                with self.subTest(name=name, shape=shape):
                    folder = self.folders[name]
                    rep = self.practise(name, *shape)
                    saved = {i for i, _ in practice.read_test(folder)}
                    self.assertTrue(set(rep["held_out_cards"]) <= saved)
                    got = [c["id"] for c in self.round_of(folder).cards()]
                    self.assertEqual(len(got), gate.ROUND_MATCHES)
                    self.assertFalse(set(got) & saved)

    def test_a_torn_test_set_stops_the_round_before_the_writer(self):
        folder = self.folders[NAME]
        self.practise(NAME, 20, 10)
        (folder / practice.TEST_FILE).write_text('{"test": [', encoding="utf-8")
        shutil.rmtree(folder / madeup.FOLDER)  # so a round past the check would ask the writer first
        writer = Writer()
        with self.assertRaises(run.Refused):
            self.round_of(folder, writer).cards()
        self.assertEqual(writer.asks, [])



def all_trained(folder, upto=madeup.MAX_CUSTOMERS):
    """persona-01 to persona-<upto> each have a training match on record (the roster a run would keep)."""
    practice.keep_trained(folder, [(f"persona-{n:02d}", practice._ANY) for n in range(1, upto + 1)])


class Cap(Base):
    """Item 3: an agent has at most 99 customers, so repeated resets can leave too few for a test set."""
    practise = testset.Kept.practise

    def test_the_too_few_refusal_names_lowering_the_level(self):
        folder = self.folders[NAME]
        all_trained(folder)
        with self.assertRaises(run.Refused) as got:
            self.practise(NAME, 30, 20)
        self.assertIn("too few are left. One step: lower the agent's risk level to medium or low, whose test "
                      "set holds 10", str(got.exception))
        with self.assertRaises(run.Refused) as got:
            self.practise(NAME, 20, 10)
        self.assertIn("too few are left. No lower risk level holds a smaller test set", str(got.exception))
        self.assertNotIn("One step", str(got.exception))

    def test_room_warning_at_the_agents_level(self):
        folder = self.folders[NAME]
        self.assertIsNone(practice.room_warning(folder, levels.HIGH))  # a fresh agent
        all_trained(folder, 60)
        self.assertIsNone(practice.room_warning(folder, levels.HIGH))  # 39 left: enough for 20
        all_trained(folder, 85)
        warn = practice.room_warning(folder, levels.HIGH)  # 14 left: too few for 8, 8 and 4
        self.assertIn("85 of the 99 customers", warn)
        self.assertIn("test set of 20 at its high level", warn)
        self.assertIn("lower the agent's risk level to medium or low", warn)
        self.assertIsNone(practice.room_warning(folder, levels.MEDIUM))  # enough for 4, 4 and 2
        all_trained(folder, 97)
        self.assertIn("No lower risk level", practice.room_warning(folder, levels.MEDIUM))
        levels.write(folder, levels.HIGH)
        self.assertIn("at its high level", practice.room_warning(folder))  # the agent's own level.json


class CapPage(test_levels_tab.Tab):
    """Item 3 on the Arena tab: Start a new test set says when the cap leaves too few."""

    def reset(self, level, saved):
        levels.write(self.folder, level)
        cards = self.folder / madeup.FOLDER
        cards.mkdir(exist_ok=True)
        for n in range(1, saved + 1):
            (cards / f"persona-{n:02d}.json").write_text(json.dumps({"id": f"persona-{n:02d}"}), encoding="utf-8")
        (self.folder / run.MATCHES_FILE).write_text("torn\n", encoding="utf-8")
        return self.m.new_test_set("stock_watch")

    def test_the_reset_warns_at_high_with_85_customers_trained(self):
        got = self.reset(levels.HIGH, 85)
        self.assertTrue(got.startswith(mo.NEW_TEST_SET + " 85 of the 99 customers"), got)
        self.assertIn("lower the agent's risk level to medium or low", got)

    def test_the_reset_says_nothing_more_while_there_is_room(self):
        self.assertEqual(self.reset(levels.MEDIUM, 85), mo.NEW_TEST_SET)



class Gaps(Base):
    """Item 4: the cases the seal check found untested."""
    practise = testset.Kept.practise

    def test_an_unsealed_test_line_in_a_folder_with_no_roster_counts_as_training(self):
        folder = self.folders[NAME]
        seal.sign({}, practice.reports_of(folder))  # the key is there, so only the line's own seal decides
        line = {"id": "old-r1-g01", "card": "persona-05", practice.TEST_KEY: True,
                "persona": {"id": "persona-05", "from_card": "F"}}
        (folder / run.MATCHES_FILE).write_text(json.dumps(line) + "\n", encoding="utf-8")
        self.assertFalse((folder / practice.ROSTER_FILE).exists())
        self.assertIn(("persona-05", "F"), practice.trained(folder))
        self.assertIn(("persona-05", "F"), practice.keep_trained(folder))  # and on the roster built from it

    def test_a_quick_run_on_a_torn_roster_stops_before_the_writer(self):
        folder = self.folders[NAME]
        self.practise(NAME, quick=True)
        (folder / practice.ROSTER_FILE).write_text('{"trained": [', encoding="utf-8")
        shutil.rmtree(folder / madeup.FOLDER)  # so a run past the check would ask the writer first
        writer, played = Writer(), []
        with mock.patch.object(practice.Practice, "play", testset.recorded_play(played)), \
                self.assertRaises(practice.Unrecorded) as got:
            practice.practise(folder, agent_model=None, customer_model=writer, judge_model=None, quick=True)
        self.assertEqual(got.exception.file, practice.ROSTER_FILE)
        self.assertEqual((writer.asks, played), ([], []))

    def test_keep_trained_refuses_when_the_roster_is_gone_beside_sealed_lines(self):
        folder = self.folders[NAME]
        self.practise(NAME, quick=True)  # sealed training lines and no test-set.json
        self.assertFalse((folder / practice.TEST_FILE).exists())
        (folder / practice.ROSTER_FILE).unlink()
        with self.assertRaises(practice.Unrecorded) as got:
            practice.keep_trained(folder, [("persona-01", "F")])
        self.assertEqual(got.exception.file, practice.ROSTER_FILE)
        self.assertFalse((folder / practice.ROSTER_FILE).exists())  # left as it is, never rebuilt



class CommandLine(Base):
    """Item 5: arena/practice.py --new-test-set, the way on from the command line."""
    practise = testset.Kept.practise

    def main(self, *argv, models=False):
        out, err = io.StringIO(), io.StringIO()
        given = dict(agent_model=Writer(), customer_model=Writer(), judge_model=Writer()) if models else {}
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = practice.main(["--agent", str(self.folders[NAME]), *argv], **given)
        return code, out.getvalue(), err.getvalue()

    def test_a_torn_record_names_the_flag_and_the_flag_gets_past_it(self):
        folder = self.folders[NAME]
        self.practise(NAME, 20, 10)
        before = {c for c, _ in practice.trained(folder)}
        (folder / practice.ROSTER_FILE).write_text('{"trained": [', encoding="utf-8")
        with mock.patch.object(practice.Practice, "play", testset.recorded_play([])):
            code, _, err = self.main("--quick", models=True)
        self.assertEqual(code, 2)
        self.assertIn(practice.ROSTER_FILE, err)
        self.assertIn("arena/practice.py --agent", err)
        self.assertIn("--new-test-set", err)
        code, out, err = self.main("--new-test-set")  # no model and no key needed
        self.assertEqual((code, err), (0, ""))
        self.assertIn("A new test set is ready", out)
        self.assertIn("trained-before-", out)
        self.assertIsNone(practice.broken_record(folder))
        self.assertLessEqual(before, {c for c, _ in practice.trained(folder)})
        again = self.practise(NAME, 20, 10)
        self.assertFalse(set(again["held_out_cards"]) & before)

    def test_the_flag_refuses_a_whole_record_and_a_folder_that_is_not_an_agents(self):
        self.practise(NAME, 20, 10)
        code, out, err = self.main("--new-test-set")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("read whole", err)
        self.assertEqual(list(self.folders[NAME].glob("*-before-*")), [])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = practice.main(["--agent", str(self.root), "--new-test-set"])
        self.assertEqual(code, 2)
        self.assertIn("not an agent's folder", err.getvalue())

    def test_the_flag_says_when_the_cap_leaves_too_few(self):
        folder = self.folders[NAME]
        levels.write(folder, levels.HIGH)
        (folder / run.MATCHES_FILE).write_text("torn\n", encoding="utf-8")  # 85 saved customers, a torn record
        cards = folder / madeup.FOLDER
        cards.mkdir()
        for n in range(1, 86):
            (cards / f"persona-{n:02d}.json").write_text("{}", encoding="utf-8")
        code, out, _ = self.main("--new-test-set")
        self.assertEqual(code, 0)
        self.assertIn("85 of the 99 customers", out)


if __name__ == "__main__":
    import unittest
    unittest.main()
