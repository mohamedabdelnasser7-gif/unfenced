"""python3 -m unfenced (unfenced/__main__.py): the page with every option passed through, and the arena and
night subcommands handing off to their mains. Nothing is served and no model is called."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import run as run_mod
from reflection import morning as mo, night


class EntryPoint(unittest.TestCase):
    def test_the_page_with_every_option_passed_through(self):
        import unfenced.__main__ as entry
        argv = ["--db", "x.db", "--assistant-state", "y", "--demo-days", "z"]
        with mock.patch.object(mo, "main", return_value=0) as page:
            self.assertEqual(entry.main(list(argv)), 0)
        page.assert_called_once_with(argv)

    def test_arena_and_night_hand_off_to_their_mains(self):
        import unfenced.__main__ as entry
        with mock.patch.object(run_mod, "main", return_value=1) as arena:
            self.assertEqual(entry.main(["arena", "--quick", "--db", "d.db"]), 1)
        arena.assert_called_once_with(["--quick", "--db", "d.db"])
        with mock.patch.object(night, "main", return_value=2) as nightly:
            self.assertEqual(entry.main(["night", "--plug", "p.json"]), 2)
        nightly.assert_called_once_with(["--plug", "p.json"])

    def test_with_no_database_it_makes_the_empty_one_the_page_opens(self):
        import unfenced.__main__ as entry
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "data" / "ascent.db"
            with mock.patch.object(entry, "DEFAULT_PATH", db), mock.patch.object(mo, "main", return_value=0) as page, \
                    mock.patch("builtins.print"):
                self.assertEqual(entry.main([]), 0)
                self.assertTrue(db.is_file())
                page.assert_called_once_with([])
                db.unlink()
                entry.main(["--db", "other.db"])  # a named database is the page's to refuse
                self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
