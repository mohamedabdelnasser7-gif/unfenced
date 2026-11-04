"""The risk level on the agent's page (decision 84, reflection/morning.py): set_risk_level and its POST
/arena/level keep, lower or raise it, refuse anything else and never start a run; Connect unlocks on the
agent's own level (a run at least the level's gate size, stuck runs count, no failed safety check at high); Run the
Arena studies between rounds when it has the study models. A fake model only."""
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from arena import levels
from engine import plug as plug_mod
from engine.lessons import Lessons as EngineLessons
from kit import seal, turn
from kit.db import Db
from reflection import morning as mo
import tests.test_quickstart as tq
from tests.fake_model import clean_env
from tests.test_arena_practice import FIXTURE, World
from tests.test_arena_rounds import Exams
from tests.test_levels_study import FIRST, Climb

NOW = time.time()


class Page(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.folder = self.dir / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        self.db = Db(str(self.dir / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "sales" / "plug.json")], reports=self.dir,
                            db_path=self.dir / "ascent.db")
        self.assertEqual(self.m.add_built(), ["stock_watch"])
        self.starts = []
        self.m.arena_start = lambda work, name: self.starts.append((work, name))

    def item(self, kind="arena_rounds", run="r1", signed=True, **kw):
        body = {"agent": "stock_watch", "kind": kind, "at": NOW, "run": run, "lost": [], "line": "x",
                "practice": True, "quick": False, **kw}
        body = seal.sign(body, self.dir) if signed else body
        (self.dir / f"arena-stock_watch-{run}.json").write_text(json.dumps(body), encoding="utf-8")


class SetRiskLevel(Page):
    def test_lower_and_raise_write_level_json_and_start_nothing(self):
        said = self.m.set_risk_level("stock_watch", "low")
        self.assertIn("risk level is low now", said)
        self.assertIn("nothing was started", said)
        self.assertEqual(levels.read(self.folder), "low")
        self.m.set_risk_level("stock_watch", "high")
        self.assertEqual(levels.read(self.folder), "high")
        self.assertEqual(self.starts, [])
        self.assertFalse(self.m.arena_running("stock_watch"))

    def test_keep_changes_nothing(self):
        levels.write(self.folder, "medium")
        before = (self.folder / levels.FILE).stat().st_mtime_ns
        self.assertIn("stays at medium", self.m.set_risk_level("stock_watch", "medium"))
        self.assertEqual((self.folder / levels.FILE).stat().st_mtime_ns, before)

    def test_bad_values_and_other_agents_are_refused_with_nothing_written(self):
        for level in ("extreme", "", "HIGH", None, ["high"], {"level": "low"}, "low ", "../high"):
            with self.subTest(level=level), self.assertRaises(mo.Refused) as e:
                self.m.set_risk_level("stock_watch", level)
            self.assertEqual(str(e.exception), mo.LEVEL_BAD)
        for agent in ("sales", "nobody", "../agents", None, ["stock_watch"]):
            with self.subTest(agent=agent), self.assertRaises(mo.Refused) as e:
                self.m.set_risk_level(agent, "low")
            self.assertEqual(str(e.exception), mo.LEVEL_NOT_HERE)
        self.assertFalse((self.folder / levels.FILE).exists())
        self.assertEqual(self.starts, [])

    def test_the_post_path_sets_it_and_is_not_the_trial_level_path(self):
        go = mo.TWO_TAB_ACTIONS[mo.LEVEL_PATH]
        self.assertEqual(mo.LEVEL_PATH, "/arena/level")
        self.assertIn("risk level is low now", go(self.m, {"agent": ["stock_watch"], "level": ["low"]}))
        self.assertEqual(levels.read(self.folder), "low")
        with self.assertRaises(mo.Refused):
            go(self.m, {"agent": ["stock_watch"], "level": ["top"]})
        self.assertNotIn(mo.LEVEL_PATH, mo.ACTIONS)  # the A3 page never sends it
        self.assertEqual(self.starts, [])


class ConnectOnTheAgentsLevel(Page):
    def passed(self):
        return self.m.gate("stock_watch")["passed"]

    def test_six_of_ten_unlocks_at_low_not_at_medium(self):
        self.item(gate_won=6, gate_played=10, gate_size=10, needs=7, level="medium", failed_checks=0)
        self.assertFalse(self.passed())
        self.assertIn("medium level", self.m.gate("stock_watch")["said"])
        self.m.set_risk_level("stock_watch", "low")
        self.assertTrue(self.passed())
        self.assertIn("passed the gate for its low level", self.m.gate("stock_watch")["said"])

    def test_a_stuck_run_counts_when_it_meets_the_level(self):
        self.item(kind="arena_stuck", gate_won=5, gate_played=10, gate_size=10, needs=7, failed_checks=0)
        self.assertFalse(self.passed())
        self.m.set_risk_level("stock_watch", "low")
        self.assertTrue(self.passed())

    def test_high_needs_no_failed_safety_check(self):
        levels.write(self.folder, "high")
        self.item(gate_won=18, gate_played=20, gate_size=20, needs=16, failed_checks=1)
        self.assertFalse(self.passed())
        self.assertIn("failed a safety check", self.m.gate("stock_watch")["said"])
        self.item(run="r2", gate_won=18, gate_played=20, gate_size=20, needs=16)  # no count reads as a fail
        self.assertFalse(self.passed())
        self.item(run="r3", gate_won=16, gate_played=20, gate_size=20, needs=16, failed_checks=0)
        self.assertTrue(self.passed())
        self.item(run="r4", gate_won=15, gate_played=20, gate_size=20, needs=16, failed_checks=0)
        self.assertFalse(self.passed())

    def test_a_raised_level_asks_for_a_run_at_its_own_size(self):
        levels.write(self.folder, "high")  # a medium run of 10, raised to high: 8 of 10 with no failed check
        self.item(gate_won=8, gate_played=10, gate_size=10, needs=7, failed_checks=0, level="medium")
        self.assertFalse(self.passed())
        self.assertIn("its high level asks for a run of 20, so run the Arena again", self.m.gate("stock_watch")["said"])
        self.item(run="r2", gate_won=10, gate_played=10, gate_size=10, needs=7, failed_checks=0, level="medium")
        self.assertFalse(self.passed())

    def test_lowering_from_a_bigger_run_still_passes(self):
        levels.write(self.folder, "medium")  # a high run of 20 lowered to medium: 14 of 20 is 7 of 10
        self.item(gate_won=14, gate_played=20, gate_size=20, needs=16, failed_checks=2, level="high")
        self.assertTrue(self.passed())
        self.item(run="r2", gate_won=13, gate_played=20, gate_size=20, needs=16, failed_checks=0, level="high")
        self.assertFalse(self.passed())
        self.item(run="r3", gate_won=15, gate_played=15, gate_size=20, needs=16, failed_checks=0, level="high")
        self.assertFalse(self.passed())  # cut short at 15 of its 20: the gate must be whole

    def test_a_trust_file_of_one_match_never_unlocks(self):
        for level in levels.ORDER:  # a sealed full run whose trust file asked for one match, won
            with self.subTest(level=level):
                levels.write(self.folder, level)
                self.item(run=f"t-{level}", gate_won=1, gate_played=1, gate_size=1, needs=1, failed_checks=0,
                          level=None)
                self.assertFalse(self.passed())

    def test_a_short_gate_a_quick_run_and_an_unsealed_one_never_count(self):
        levels.write(self.folder, "low")
        self.item(gate_won=6, gate_played=6, gate_size=10, needs=5, failed_checks=0)
        self.assertFalse(self.passed())
        self.item(run="r2", gate_won=1, gate_played=1, gate_size=1, needs=1, quick=True, failed_checks=0)
        self.assertFalse(self.passed())
        self.item(run="r3", gate_won=10, gate_played=10, gate_size=10, needs=5, failed_checks=0, signed=False)
        self.assertFalse(self.passed())

    def test_a_sealed_run_that_does_not_say_it_was_full_never_counts(self):
        levels.write(self.folder, "low")
        self.item(gate_won=10, gate_played=10, gate_size=10, needs=5, failed_checks=0, quick=None)
        self.assertFalse(self.passed())
        self.assertIn("does not say it was a full run", self.m.gate("stock_watch")["said"])

    def test_the_tab_fields_are_read_and_checked(self):
        self.item(kind="arena_stuck", gate_won=3, gate_played=10, gate_size=10, needs=7, level="medium",
                  failed_checks=0, scores=[1, 3, "x", -2], studied=True, stopped="stuck",
                  blocks=[{"kind": "exam", "line": "2 lessons failed the exam,\n so not handed on."}, {"kind": 3}])
        got = self.m.read_arena()[0]["stock_watch"]
        self.assertEqual({k: got[k] for k in ("level", "gate_size", "failed_checks", "scores", "studied", "stopped")},
                         {"level": "medium", "gate_size": 10, "failed_checks": 0, "scores": [1, 3], "studied": True,
                          "stopped": "stuck"})
        self.assertEqual(got["blocks"], [{"kind": "exam", "line": "2 lessons failed the exam, so not handed on."}])


class RunTheArenaStudies(Page):
    def test_with_the_study_models_it_plays_the_levels_rounds_and_studies_in_the_agents_db(self):
        world = Climb((self.folder / "instructions.md").read_text(encoding="utf-8"), [[FIRST]])
        self.m.arena_models = lambda: (world, world, world)
        self.m.arena_reflection = lambda: {"study": world, "open": world, "exam": world, "examiner": Exams()}
        self.m.run_arena("stock_watch")
        self.starts[0][0]()
        got = self.m.read_arena()[0]["stock_watch"]
        self.assertEqual((got["studied"], got["scores"]), (True, [0, 5]))
        texts = [les["text"] for les in EngineLessons(self.db, turn.load(self.folder).plug).mine()]
        self.assertIn(FIRST, texts)

    def test_test_fakes_with_no_study_play_one_round(self):
        self.m.arena_models = lambda: (World(), World(), World())
        self.m.run_arena("stock_watch")
        self.starts[0][0]()
        got = self.m.read_arena()[0]["stock_watch"]
        self.assertEqual((got["studied"], len(got["scores"])), (False, 1))


if __name__ == "__main__":
    unittest.main()
