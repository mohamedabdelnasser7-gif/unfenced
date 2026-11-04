"""Study between rounds for a built agent (decisions 84 and 85, arena/rounds.py BuiltBetween, arena/practice.py
practise study= and db=): each lost practice match becomes a case in the agent's own database, the study
writes lessons there, a lesson that passes its exam is handed in the next round, and the run climbs to its
level, stops flat, or stops at its cap (1,500 for a high run, 1,000 for a normal one). A fake model only."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from arena import levels, practice, run
from engine.lessons import WAITING
from engine.lessons import Lessons as EngineLessons
from kit import turn
from kit.db import Db
from tests.fake_model import clean_env, say
from tests.test_any_agent_r2 import THREE, agent_folder
from tests.test_arena_practice import FIXTURE, World
from tests.test_arena_rounds import IDEA_HEAD, JUDGE_HEAD, Exams

FIRST = "Say the item name back before you answer."
SECOND = "Name the size you looked up in the same line."
PROMISE = "Promise a refund when the item is late."
BREAKS = "Answer with one word only."


class Climb(World):
    """The World with the night study's parts: the idea part answers the next list from ideas (one a
    study, then none), the risk judge says high for a line with a promise in it, other study parts get
    an empty list. The agent counts how many of the known lessons it was handed (its system prompt), and
    the judge reads that count: none handed, every match lost; one, every second match won; two, all won."""

    def __init__(self, instructions, ideas=()):
        super().__init__(agent=self.answer, judge=self.verdict)
        self.head = instructions.strip()[:60]
        self.ideas, self.handed, self.flip, self.studied, self.broken = list(ideas), 0, 0, 0, False
        self.handed_seen = []

    def answer(self, messages, tools):
        system = messages[0]["content"]
        self.handed = sum(t in system for t in (FIRST, SECOND))
        self.broken = BREAKS in system
        self.handed_seen.append((self.handed, PROMISE in system))
        return say("Thanks for writing. Here is what happens next.")

    def verdict(self, messages):
        self.flip += 1
        won = not self.broken and self.handed >= 2 or not self.broken and (self.handed == 1 and self.flip % 2 == 0)
        return say(json.dumps({"reached": won, "broke_never": False, "turn": 1, "why": "plain"}))

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        if system.startswith(IDEA_HEAD):
            self.studied += 1
            got = self.ideas.pop(0) if self.ideas else []
            return say(json.dumps([{"lesson": x, "situation": "Any chat.", "stages": ["all"]} for x in got]))
        if system.startswith(JUDGE_HEAD):
            return say("high" if "promise" in messages[1]["content"].lower() else "low")
        if system.startswith((self.head, "You are a person", "You are the person")) or system in self._known():
            return super().chat(messages, tools, effort, max_tokens, whole)
        return say("[]")

    @staticmethod
    def _known():
        from arena import good
        from tests.test_arena_practice import WRITER_SYSTEMS
        return (good.SYSTEM, *WRITER_SYSTEMS)


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def stock(self, level=None, root=None):
        folder = (root or self.root) / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, folder)
        if level:
            levels.write(folder, level)
        return folder

    def run_it(self, folder, ideas, *, refuse=(), root=None, **kw):
        root = root or self.root
        world = Climb((folder / "instructions.md").read_text(encoding="utf-8"), ideas)
        self.exams = Exams(refuse)
        db = Db(str(root / "ascent.db"))
        self.addCleanup(db.close)
        study = {"study": world, "open": world, "exam": world, "examiner": self.exams}
        rep = practice.practise(folder, agent_model=world, customer_model=world, judge_model=world, study=study, db=db,
                                **kw)
        self.world, self.db = world, db
        return rep

    def item(self, rep, root=None):
        item = rep.get("item") or rep.get("stuck")
        return json.loads(((root or self.root) / item["file"]).read_text(encoding="utf-8"))

    def lessons(self, folder):
        agent = turn.load(folder)
        return {les["text"]: les for les in EngineLessons(self.db, agent.plug).mine()}


class ItClimbs(Base):
    def test_a_high_run_climbs_across_three_rounds_to_twenty_of_twenty(self):
        folder = self.stock("high")
        rep = self.run_it(folder, [[FIRST], [SECOND]], live_path=self.root / "ascent.db")
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual([r["gate"]["won"] for r in rep["rounds"]], [0, 10, 20])
        self.assertEqual([r["reflection"]["handed"] for r in rep["rounds"][:2]], [1, 1])
        self.assertEqual(rep["calls"]["cap"], 1500)
        item = self.item(rep)
        self.assertEqual((item["kind"], item["scores"], item["studied"], item["needs"]), ("arena_rounds", [0, 10, 20],
                                                                                          True, 16))
        self.assertNotIn("blocks", item)
        mine = self.lessons(folder)  # the lessons are in the agent's own database, as its night writes them
        self.assertIn(FIRST, mine)
        self.assertIn(SECOND, mine)
        self.assertEqual(sorted(self.exams.seen), sorted([FIRST, SECOND]))

    def test_a_medium_run_stops_after_two_rounds_while_it_climbs_and_keeps_the_1000_cap(self):
        rep = self.run_it(self.stock(), [[FIRST], [SECOND]])
        self.assertEqual((rep["stopped"], [r["gate"]["won"] for r in rep["rounds"]]), (run.ROUNDS, [0, 5]))
        self.assertEqual(rep["calls"]["cap"], 1000)
        item = self.item(rep)
        self.assertEqual((item["scores"], item["gate_size"], item["studied"]), ([0, 5], 10, True))
        self.assertEqual(self.world.studied, 1)

    def test_low_also_plays_two_rounds_at_the_1000_cap(self):
        rep = self.run_it(self.stock("low"), [[FIRST]])
        self.assertEqual((rep["stopped"], len(rep["rounds"]), rep["calls"]["cap"]), (run.PASSED, 2, 1000))

    def test_a_lesson_that_waits_for_yes_is_never_handed(self):
        folder = self.stock("high")
        rep = self.run_it(folder, [[PROMISE]])
        self.assertNotEqual(rep["stopped"], run.PASSED)
        self.assertEqual(self.lessons(folder).get(PROMISE, {}).get("state", WAITING), WAITING)
        self.assertFalse(any(promise for _, promise in self.world.handed_seen))
        kinds = [b["kind"] for b in self.item(rep)["blocks"]]
        self.assertIn("waits", kinds)

    def test_every_kind_of_the_three_agents_studies_in_its_own_database(self):
        for name in THREE:
            with self.subTest(name):
                root = self.root / name
                folder = agent_folder(root, name)
                levels.write(folder, "medium")
                rep = self.run_it(folder, [[FIRST]], root=root)
                self.assertEqual(len(rep["rounds"]), 2)
                self.assertTrue(rep["rounds"][0]["reflection"]["cases"])
                self.assertTrue(self.item(rep, root)["studied"])

    def test_a_correction_on_trial_on_the_live_page_is_handed_from_the_first_match(self):
        import time
        from engine.lessons import HOTFIX_SOURCE
        path = self.root / "ascent.db"
        folder = self.stock()
        d = Db(str(path))
        EngineLessons(d, turn.load(folder).plug)  # its tables
        now = time.time()
        with d.tx() as c:
            lid = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, share, ends_at, source, "
                            "origin, kind, added_at) VALUES ('stock_watch', ?, 'all', '', 'low', 'trying', 1, ?, ?, "
                            "'person', 'pattern', ?)", (FIRST, now + 86400, HOTFIX_SOURCE, now)).lastrowid
            c.execute("INSERT INTO lesson_exams (lesson_id, agent, passed, at) VALUES (?, 'stock_watch', 1, ?)",
                      (lid, now))
        d.close()
        rep = self.run_it(folder, [], live_path=path)
        self.assertEqual(rep["rounds"][0]["gate"]["won"], 5)
        self.assertEqual(self.world.handed_seen[0], (1, False))

    def test_a_lesson_that_passes_its_exam_but_loses_a_past_win_is_not_handed(self):
        rep = self.run_it(self.stock("high"), [[FIRST], [BREAKS]])
        two = rep["rounds"][1]["reflection"]
        self.assertEqual((two["passed"], two["refused"], two["handed"]), (0, 1, 0))
        self.assertGreater(two["broke"], 0)
        self.assertEqual([r["gate"]["won"] for r in rep["rounds"]], [0, 10, 10])
        self.assertIn(BREAKS, self.exams.seen)  # it passed the exam itself; the rerun of the past wins held it


class ItStops(Base):
    def test_flat_when_no_lesson_passes_the_exam(self):
        rep = self.run_it(self.stock("high"), [[FIRST], [SECOND]], refuse=(FIRST, SECOND))
        self.assertEqual((rep["stopped"], [r["gate"]["won"] for r in rep["rounds"]]), (run.STUCK, [0, 0, 0]))
        item = self.item(rep)
        self.assertEqual((item["kind"], item["scores"]), ("arena_stuck", [0, 0, 0]))
        kinds = [b["kind"] for b in item["blocks"]]
        self.assertIn("exam", kinds)
        self.assertNotIn("cap", kinds)

    def test_flat_when_the_study_finds_no_lesson(self):
        rep = self.run_it(self.stock("high"), [])
        self.assertEqual(rep["stopped"], run.STUCK)
        self.assertIn("no_lesson", [b["kind"] for b in self.item(rep)["blocks"]])

    def test_the_cap_stops_it_during_the_study(self):
        one = self.run_it(self.stock("high", self.root / "one"), [], root=self.root / "one", rounds=1)
        used = one["calls"]["used"]
        rep = self.run_it(self.stock("high"), [[FIRST]], cap=used + 1)
        self.assertEqual((rep["stopped"], len(rep["rounds"])), (run.CAP, 1))
        item = self.item(rep)
        self.assertIn("cap", [b["kind"] for b in item["blocks"]])
        self.assertIn(f"cap of {used + 1}", item["line"])

    def test_quick_never_studies(self):
        rep = self.run_it(self.stock("high"), [[FIRST]], quick=True)
        self.assertEqual((len(rep["rounds"]), self.world.studied), (1, 0))


if __name__ == "__main__":
    unittest.main()
