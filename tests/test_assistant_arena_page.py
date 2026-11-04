"""Run the Arena on the personal assistant's page (reflection/morning.py run_arena, assistant/arena.py page_run):
its own Arena of simulated days on this page's database, through the same entry, thread and sealed item the
Sales agent and an agent made here use. Its refusals, the Arena tab showing the run, no Connect implied (it has no
live channel) and no Train yet. Fake models only: no model call, no network."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from arena import retry as retry_mod, run as run_mod
from assistant import PLUG, arena as assistant_arena
from engine import plug as plug_mod
from engine.log import Log
from kit.db import Db
from reflection import morning as mo, pages, scheduler
from tests.assistant_fakes import Helper
from tests.fake_model import clean_env
import tests.test_quickstart as tq

ARENA_TAB = {"tab": ["arena"]}


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "sales" / "plug.json"), PLUG], reports=self.dir,
                            db_path=self.path)
        self.helper = Helper()
        self.m.arena_models = lambda: (self.helper, None, None)
        self.m.arena_start = lambda work, name: work()  # the thread's work, at once
        self.p = pages.Pages(self.m)

    def page(self, query=ARENA_TAB, token="t"):
        return self.p.get("/agents/assistant", query, token).split("</style>")[1].split("<script>")[0]


class Runs(Base):
    def test_run_the_arena_plays_its_days_and_writes_a_sealed_full_item(self):
        self.helper = Helper(miss_urgent=True)
        self.assertEqual(self.m.run_arena("assistant", full=True), mo.ARENA_STARTED)
        self.assertIsNone(self.m.arena_note("assistant"))
        self.assertFalse(self.m.arena_running("assistant"))
        item = self.m.read_arena()[0]["assistant"]
        trust = run_mod.PUBLIC_TRUST  # no trust file: the level assistant/arena.py load_trust gives it
        self.assertEqual((item["gate_played"], item["needs"], item["quick"]), (trust["matches"], trust["wins"], False))
        self.assertTrue(item["sealed"])
        self.assertEqual(item["gate_won"], 0)
        matches = self.dir / assistant_arena.PAGE_FOLDER / run_mod.MATCHES_FILE
        self.assertEqual(len(matches.read_text(encoding="utf-8").splitlines()), trust["matches"])
        last = self.m.last_run("assistant")
        self.assertEqual((last["won"], last["played"]), (0, trust["matches"]))
        self.assertFalse(self.m.gate("assistant")["passed"])
        # each lost day is a case in this database, as close_day writes it
        log = Log(self.db, PLUG)
        case = last["lost"][0]["card"]
        self.assertIn("urgent_missed", [r["result"] for r in log.case(case)])
        summary = self.m.arena_summary("assistant")
        self.assertEqual(summary["reasons"][0][0], "An urgent item was missed")

    def test_the_arena_tab_shows_the_run_without_connect_or_train(self):
        self.helper = Helper(miss_urgent=True)
        self.m.run_arena("assistant", full=True)
        page = self.page()
        self.assertIn(mo.SUMMARY_HEAD.format(won=0, played=run_mod.PUBLIC_TRUST["matches"]), page)
        self.assertIn("An urgent item was missed", page)
        self.assertIn(mo.ASSISTANT_GATE.format(won=0, need=run_mod.PUBLIC_TRUST["wins"]), page)
        self.assertIn(mo.TRAIN_NOT_YET, page)
        self.assertNotIn(f'action="{mo.TRAIN_PATH}"', page)
        self.assertNotIn("Ready to go live", page)
        self.assertIn("Passed the gate", page)
        self.assertNotIn(mo.ARENA_RUN_SAID, page)  # that line promises Connect
        self.assertIn(mo.ASSISTANT_RUN_SAID, page)
        self.assertNotIn(f"<li>{mo.CONNECT_WORD}", page)
        self.assertNotIn(mo.READY, page)
        self.assertIn(f'action="{pages.ARENA_PATH}"', page)  # it can run again
        self.assertIsNone(self.m.next_step("assistant"))

    def test_a_passing_run_says_there_is_nothing_to_connect(self):
        self.m.run_arena("assistant", full=True)
        self.assertTrue(self.m.gate("assistant")["passed"])
        status = self.m.arena_status("assistant")
        self.assertEqual((status["line"], status["ready"], status["next"]), (mo.ASSISTANT_PASSED, False, None))
        self.assertEqual(self.m.connection_view("assistant"), [])
        page = self.page()
        self.assertIn(mo.ASSISTANT_PASSED, page)
        self.assertNotIn(mo.READY, page)
        self.assertNotIn(f"<li>{mo.CONNECT_WORD}", page)
        with self.assertRaises(mo.Refused):
            self.m.connect("assistant", "whatsapp")

    def test_the_short_run_is_quick_and_never_a_pass(self):
        self.m.run_arena("assistant")
        item = self.m.read_arena()[0]["assistant"]
        self.assertEqual((item["gate_played"], item["quick"]), (1, True))
        self.assertFalse(self.m.gate("assistant")["passed"])

    def test_the_overview_offers_run_the_arena_before_any_run(self):
        page = self.page(query={})
        self.assertIn("No practice run saved yet.", page)
        self.assertIn(mo.ASSISTANT_SAID, page)
        self.assertIn(f'action="{pages.ARENA_PATH}"', page)
        self.assertIn(pages.STATUS_SAID["Training"], page)  # the status label reads as before

    def test_progress_counts_the_days_played(self):
        starts = []
        self.m.arena_start = lambda work, name: starts.append(work)
        self.m.run_arena("assistant", full=True)
        self.assertTrue(self.m.arena_running("assistant"))
        self.assertIn("Running the Arena: its first matches are starting.", self.page())
        starts[0]()
        self.assertFalse(self.m.arena_running("assistant"))
        self.assertIn("assistant", self.m.read_arena()[0])


class Refusals(Base):
    def setUp(self):
        super().setUp()
        self.starts = []
        self.m.arena_start = lambda work, name: self.starts.append(name)

    def test_refusals_start_nothing(self):
        m = mo.Morning(self.db, [PLUG], reports=self.dir)  # no database folder
        m.arena_start = self.m.arena_start
        with self.assertRaises(mo.Refused) as e:
            m.run_arena("assistant")
        self.assertEqual(str(e.exception), mo.ASSISTANT_NO_DB)
        with mock.patch.object(retry_mod, "has_room", return_value=False), self.assertRaises(mo.Refused) as e:
            self.m.run_arena("assistant")
        self.assertIn("model call cap", str(e.exception))
        self.m.arena_models = None
        with mock.patch("kit.model.has_key", return_value=False), self.assertRaises(mo.Refused) as e:
            self.m.run_arena("assistant")
        self.assertIn("No model key", str(e.exception))
        self.m.arena_models = lambda: (self.helper, None, None)
        self.assertTrue(scheduler.Scheduler(self.db, str(self.path), when=None, holder="whatsapp:1")._lock(time.time()))
        with self.assertRaises(mo.Refused) as e:
            self.m.run_arena("assistant")
        self.assertEqual(str(e.exception), mo.ARENA_LOCKED)
        with self.db.tx() as c:
            c.execute("DELETE FROM night_lock")
        self.assertEqual(self.starts, [])
        self.assertEqual(self.m.run_arena("assistant"), mo.ARENA_STARTED)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_arena("assistant")
        self.assertIn("running for this agent already", str(e.exception))
        self.assertEqual(self.starts, ["arena-assistant"])

    def test_train_is_not_available_yet(self):
        with self.assertRaises(mo.Refused) as e:
            self.m.run_train("assistant")
        self.assertEqual(str(e.exception), mo.TRAIN_NOT_HERE)
        self.assertEqual(self.starts, [])

    def test_other_agents_not_here_are_still_refused(self):
        m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "marketing" / "plug.json")], reports=self.dir,
                       db_path=self.path)
        for agent in ("marketing", "nobody"):
            with self.subTest(agent=agent), self.assertRaises(mo.Refused) as e:
                m.run_arena(agent)
            self.assertEqual(str(e.exception), mo.ARENA_NOT_HERE)


if __name__ == "__main__":
    unittest.main()
