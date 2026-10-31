"""The Arena defaults to the cleaned real cards, and no test reads them (new, 2026-10-31; DECISIONS
items 23 and 40; tests/real_guard.py). Only the names under arena/real/ are listed here."""
import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import run
from tests import real_guard
from tests.fake_model import clean_env

REAL = run.ROOT / "arena" / "real"


class NoRealReads(unittest.TestCase):
    def test_the_shipped_default_is_the_real_cards_and_the_suite_plays_the_made_up_set(self):
        self.assertEqual(real_guard.REAL_DEFAULT, REAL / "cards")
        self.assertEqual(run.DEMO_CARDS, run.ROOT / "demo" / "personas" / "cards")
        self.assertEqual(run.DEFAULT_CARDS, run.DEMO_CARDS)

    def test_opening_a_file_under_arena_real_fails_the_test(self):
        names = sorted(os.listdir(REAL / "cards"))  # names only: listing is allowed
        self.assertTrue(names)
        before = len(real_guard.refused)
        for opener in (lambda p: open(p, "rb"), lambda p: Path(p).read_text(encoding="utf-8"),
                       lambda p: os.open(p, os.O_RDONLY), lambda p: sqlite3.connect(str(p))):
            for p in (REAL / "cards" / names[0], REAL / "replay.jsonl", REAL / "summary.json",
                      REAL / "x" / ".." / "cards" / names[0]):
                with self.subTest(path=p.name), self.assertRaises(real_guard.RealRead):
                    opener(p)
        self.assertEqual(len(real_guard.refused) - before, 16)
        with self.assertRaises(real_guard.RealRead):
            run.load_cards(real_guard.REAL_DEFAULT)

    def test_paths_beside_arena_real_are_not_refused(self):
        for p in (run.DEMO_CARDS, run.ROOT / "arena" / "realx", run.ROOT / "arena" / "run.py", ":memory:", 3, None):
            with self.subTest(path=p):
                self.assertFalse(real_guard.under_real(p))
        self.assertTrue(real_guard.under_real(REAL))
        self.assertTrue(real_guard.under_real(os.fsencode(REAL / "cards")))

    def test_another_name_for_arena_real_is_refused_too(self):
        """Review round 1, finding 3 (red team 3): the folder is matched by device and inode, not text."""
        with tempfile.TemporaryDirectory() as d:
            to_real, to_arena = Path(d) / "to-real", Path(d) / "to-arena"
            to_real.symlink_to(REAL, target_is_directory=True)
            to_arena.symlink_to(REAL.parent, target_is_directory=True)
            to_cards = Path(d) / "to-cards"
            to_cards.symlink_to(REAL / "cards", target_is_directory=True)
            names = [to_real / "replay.jsonl", to_arena / "real" / "cards", to_arena / "real",
                     str(to_cards) + "/../replay.jsonl",  # review round 2, finding 3
                     os.path.relpath(REAL / "replay.jsonl"), str(REAL).replace(os.sep + "real", os.sep + os.sep + "real"),
                     "file:" + str(REAL / "replay.jsonl") + "?mode=ro", "file://" + str(REAL / "replay.jsonl"),
                     "file:" + str(to_real / "x.db").replace(" ", "%20")]
            swapped = Path(str(REAL).swapcase())
            if swapped.exists():  # a case blind disk
                names.append(swapped / "replay.jsonl")
            firm = Path("/System/Volumes/Data" + str(REAL))
            if firm.is_dir():
                names.append(firm / "replay.jsonl")
            for p in names:
                with self.subTest(path=str(p)):
                    self.assertTrue(real_guard.under_real(p))
            for p in (to_arena / "realx", to_arena / "run.py", "file:" + str(run.DEMO_CARDS), "file::memory:"):
                with self.subTest(path=str(p)):
                    self.assertFalse(real_guard.under_real(p))
            before = len(real_guard.refused)
            with self.assertRaises(real_guard.RealRead):
                open(to_real / "replay.jsonl", "rb")
            with self.assertRaises(real_guard.RealRead):
                sqlite3.connect(f"file:{to_real / 'x.db'}?mode=ro", uri=True)
            self.assertEqual(len(real_guard.refused) - before, 2)
            self.assertFalse((REAL / "x.db").exists())

    def test_a_run_with_no_cards_flag_loads_the_made_up_set(self):
        clean_env(self)
        seen = []

        def load(folder):
            seen.append(Path(folder))
            raise run.Refused("stopped here: only the folder is checked")

        with tempfile.TemporaryDirectory() as d, mock.patch.object(run, "load_cards", load), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = run.main(["--matches", "1", "--rounds", "1", "--state", d], agent_model=object(),
                            customer_model=object())
        self.assertEqual((code, seen), (2, [run.DEMO_CARDS]))
        self.assertEqual(len(run.load_cards(run.DEMO_CARDS)), len(list(run.DEMO_CARDS.glob("persona-*.json"))))


if __name__ == "__main__":
    unittest.main()
