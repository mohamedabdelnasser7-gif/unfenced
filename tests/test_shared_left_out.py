"""An owner id or shared folder that cannot be read leaves the shared pool out, never the night
(review crossowner round 2, item 1): the night study runs without the pool and its notes say why;
the grow night, an owner's Arena state and a built agent's practice read no shared card. Fake
model and fake files; no key, no network."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import grow, practice
from kit.db import Db
from reflection import night, shared
from tests.test_arena_practice import FIXTURE


class LeftOut(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.base = Path(d.name)
        self.folder = self.base / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        plug = json.loads((self.folder / "plug.json").read_text(encoding="utf-8"))
        plug["owner"] = "north"
        (self.folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
        (self.base / "agents" / "owner.json").write_text(json.dumps({"owner": "north"}), encoding="utf-8")
        self.plug = plug
        Db(str(self.base / "ascent.db")).close()

    def bad_id(self):
        (self.base / "agents" / shared.OWNER_ID_FILE).write_text("not an id", encoding="utf-8")

    def main(self):
        rep = {"agent": self.plug["agent"], "window": {"since": 0, "until": 1}, "snapshot": {}, "notes": []}
        with mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]), \
                mock.patch.object(night, "night", return_value=rep) as study, mock.patch("kit.model.Model"), \
                mock.patch("arena.grow.night", return_value={"kind": "sales"}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = night.main(["--plug", str(self.folder / "plug.json"), "--db", str(self.base / "ascent.db"),
                               "--json"])
        return code, study, rep

    def test_an_owner_id_out_of_shape_leaves_the_pool_out_of_the_night_study(self):
        self.bad_id()
        code, study, rep = self.main()
        self.assertEqual(code, 0)
        self.assertTrue(study.called)
        self.assertIsNone(study.call_args.kwargs["shared"])
        self.assertIn("the shared pool was left out tonight (the owner's id file is out of shape)", rep["notes"])

    def test_an_owner_folder_that_cannot_be_read_leaves_the_pool_out_too(self):
        with mock.patch.object(shared, "owner_id", side_effect=PermissionError("/a/path/never/said")):
            code, study, rep = self.main()
        self.assertEqual(code, 0)
        self.assertIsNone(study.call_args.kwargs["shared"])
        self.assertIn("the shared pool was left out tonight (PermissionError)", rep["notes"])
        self.assertNotIn("/a/path", json.dumps(rep))

    def test_with_a_readable_owner_id_the_study_gets_the_pool(self):
        code, study, rep = self.main()
        self.assertEqual(code, 0)
        self.assertIsNotNone(study.call_args.kwargs["shared"])
        self.assertEqual(rep["notes"], [])

    def test_the_grow_night_goes_on_without_the_pool(self):
        from arena import recipe as recipe_mod
        with mock.patch.object(shared, "owner_id", side_effect=PermissionError("x")):
            rep = grow.night(self.base / "ascent.db", night.plug_mod.load(self.folder / "plug.json"),
                             recipe_mod.EXAMPLE, 0, 1, folder=self.folder, shared_root=self.base / "shared")
        self.assertEqual(rep["shared_stopped"], "the shared pool was left out tonight (PermissionError)")

    def test_practice_reads_no_shared_card_on_an_os_error(self):
        with mock.patch.object(shared, "owner_id", side_effect=PermissionError("x")):
            self.assertEqual(grow.for_state(self.folder, shared_root=self.base / "shared").shared, [])
            self.assertEqual(practice.shared_cards(self.folder, night.plug_mod.load(self.folder / "plug.json")), [])
        with mock.patch.object(shared.Pool, "shared", side_effect=PermissionError("x")):
            self.assertEqual(shared.practice_cards("sales", self.base / "shared"), [])


if __name__ == "__main__":
    unittest.main()
