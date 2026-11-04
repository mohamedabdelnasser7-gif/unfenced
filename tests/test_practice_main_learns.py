"""The command line learns like the page (2026-11-04): arena/practice.py main hands practise() learn (each
lost match becomes a case, quick notes) and the study between rounds, through the same helper the page uses
(practice.learning); --quick keeps one round with no study. Fake models only, practise itself stubbed."""
import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import practice, run
from kit.db import Db
from tests.fake_model import FakeModel, clean_env
from tests.test_arena_practice import FIXTURE


class MainLearns(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()
        self.folder = self.root / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        Db(str(self.root / "ascent.db")).close()
        self.got = {}

    def main(self, *argv, **kw):
        def fake(folder, **kwargs):
            self.got = kwargs
            return {"stopped": run.PASSED}
        err = io.StringIO()
        with mock.patch.object(practice, "practise", fake), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            code = practice.main(["--agent", str(self.folder), "--json", *argv], agent_model=FakeModel(),
                                 customer_model=FakeModel(), judge_model=FakeModel(), **kw)
        self.err = err.getvalue()
        return code

    def test_main_hands_learn_and_study(self):
        study = {"study": FakeModel(), "open": FakeModel(), "exam": FakeModel()}
        self.assertEqual(self.main(study=study), 0)
        self.assertTrue(callable(self.got["learn"]))
        self.assertIs(self.got["study"], study)
        self.assertIsNotNone(self.got["db"])
        self.assertEqual(self.got["live_path"], str(self.root / "ascent.db"))

    def test_quick_keeps_one_round_with_no_study_but_still_learns(self):
        self.assertEqual(self.main("--quick", study={"study": FakeModel()}), 0)
        self.assertTrue(self.got["quick"])
        self.assertIsNone(self.got["study"])
        self.assertTrue(callable(self.got["learn"]))

    def test_with_real_models_the_nights_models_are_made(self):
        made = {"study": object()}
        with mock.patch.object(run, "reflection_models", return_value=made):
            db, learn, study, why = practice.learning(self.folder, self.root / "ascent.db", made=True)
        self.addCleanup(db.close)
        self.assertEqual((study, why), (made, None))
        with mock.patch.object(run, "reflection_models", side_effect=run.Refused("META_KEY is not set")):
            db2, _, study, why = practice.learning(self.folder, self.root / "ascent.db", made=True)
        self.addCleanup(db2.close)
        self.assertEqual((study, why), (None, "META_KEY is not set"))

    def test_no_database_says_so_and_runs_without(self):
        (self.root / "ascent.db").unlink()
        self.assertEqual(self.main(), 0)
        self.assertEqual((self.got["learn"], self.got["study"], self.got["db"]), (None, None, None))
        self.assertIn("No database beside the agent's folder", self.err)
        self.assertFalse((self.root / "ascent.db").exists())


if __name__ == "__main__":
    unittest.main()
