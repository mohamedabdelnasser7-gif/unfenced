"""The Arena tab of an agent made here (decision 84, reflection/pages.py level_card): "N of 10, your level
needs M", Keep, Lower and Raise, each round's score, what holds it below its level, and Try again for a
built agent (Morning.try_again, arena/retry.py built). A fake model only."""
import json
import re

from arena import levels, retry, run
from reflection import morning as mo
from reflection import pages
from tests.test_any_agent import ARENA_TAB
from tests.test_arena_practice import World
from tests.test_levels_morning import Page

EXAM = "2 lessons failed the exam, so not handed on."


class Tab(Page):
    def setUp(self):
        super().setUp()
        self.p = pages.Pages(self.m)

    def tab(self, agent="stock_watch", token="t"):
        return self.p.get(f"/agents/{agent}", ARENA_TAB, token).split("</style>")[1].split("<script>")[0]

    def level_forms(self, page):
        return re.findall(r'<form method="post" action="/arena/level">.*?name="level" value="(\w+)".*?'
                          r'<button class="([\w ]+)" type="submit">([^<]+)</button>', page)


class LevelCard(Tab):
    def test_below_its_level_it_shows_the_score_the_rounds_what_blocks_it_and_the_three_ways(self):
        self.item(kind="arena_stuck", gate_won=6, gate_played=10, gate_size=10, needs=7, failed_checks=0,
                  scores=[4, 6], blocks=[{"kind": "exam", "line": EXAM}], level="medium",
                  lost=[{"card": "c1", "why": "it gave no answer", "quote": {"turn": 1, "who": "agent", "text": "Hi"}}])
        page = self.tab()
        self.assertIn("Risk level: Medium", page)
        self.assertIn("<b>6 of 10</b>, your level needs 7</p>", page)
        self.assertIn("<li><span>Round 1</span><b>4 of 10</b></li><li><span>Round 2</span><b>6 of 10</b></li>", page)
        self.assertIn("What holds it back", page)
        self.assertIn(EXAM, page)
        self.assertIn(pages.LEVEL_HELP, page)
        self.assertEqual(self.level_forms(page), [("medium", "lb on", "Keep medium"), ("low", "lb", "Lower to low"),
                                                  ("high", "lb", "Raise to high")])
        self.assertIn('action="/tryagain"', page)  # Try again for an agent made here
        self.assertNotIn("Not built for this agent yet", page)

    def test_at_its_level_no_blocks_and_high_has_no_raise(self):
        levels.write(self.folder, "high")
        self.item(gate_won=17, gate_played=20, gate_size=20, needs=16, failed_checks=0, scores=[9, 17], level="high")
        page = self.tab()
        self.assertIn("<b>17 of 20</b>, your level needs 16 with no failed safety check</p>", page)
        self.assertIn("passed the gate for its high level", page)
        self.assertNotIn("What holds it back", page)
        self.assertNotIn(pages.LEVEL_HELP, page)
        self.assertEqual([f[0] for f in self.level_forms(page)], ["high", "medium"])

    def test_lowering_on_the_tab_changes_the_score_line_at_once(self):
        self.item(gate_won=6, gate_played=10, gate_size=10, needs=7, failed_checks=0, scores=[6], level="medium")
        mo.TWO_TAB_ACTIONS[mo.LEVEL_PATH](self.m, {"agent": ["stock_watch"], "level": ["low"]})
        page = self.tab()
        self.assertIn("<b>6 of 10</b>, your level needs 5</p>", page)
        self.assertIn("passed the gate for its low level", page)
        self.assertEqual([f[0] for f in self.level_forms(page)], ["low", "medium"])

    def test_a_raised_level_shows_what_its_own_gate_needs(self):
        self.item(gate_won=8, gate_played=10, gate_size=10, needs=7, failed_checks=0, scores=[8], level="medium")
        levels.write(self.folder, "high")
        page = self.tab()
        self.assertIn("<b>8 of 10</b>, your level needs 16 of 20 with no failed safety check</p>", page)
        self.assertIn("asks for a run of 20, so run the Arena again", page)

    def test_a_round_cut_short_shows_what_was_played(self):
        self.item(gate_won=6, gate_played=7, gate_size=10, needs=7, failed_checks=0, scores=[5, 6], stopped="cap",
                  level="medium")
        page = self.tab()
        self.assertIn("<b>6 won of 7 played</b> (the run stopped before all 10), your level needs 7</p>", page)
        self.assertIn("<li><span>Round 1</span><b>5 of 10</b></li><li><span>Round 2</span><b>6 of 7</b></li>", page)
        self.assertNotIn("<b>6 of 10</b>", page)

    def test_no_run_yet_says_what_the_level_means(self):
        page = self.tab()
        self.assertIn("Risk level: Medium", page)
        self.assertIn(levels.WORDS["medium"] + " Its first Arena run shows the score against it.", page)
        self.assertEqual(len(self.level_forms(page)), 3)

    def test_no_token_no_buttons_and_sales_has_no_level_card(self):
        self.item(gate_won=6, gate_played=10, gate_size=10, needs=7, failed_checks=0)
        self.assertEqual(self.level_forms(self.tab(token=None)), [])
        self.assertNotIn("Risk level", self.tab("sales"))

    def test_the_text_has_no_dashes(self):
        self.item(kind="arena_stuck", gate_won=6, gate_played=10, gate_size=10, needs=7, failed_checks=0,
                  scores=[4, 6], blocks=[{"kind": "exam", "line": EXAM}])
        card = self.tab().split('class="grp sq lvc"')[1].split("</section>")[0]
        self.assertFalse(re.search("[–—]| - ", re.sub(r"<[^>]+>", " ", card)))


class TryAgainBuilt(Tab):
    def test_it_plays_the_lost_practice_matches_again_with_its_own_judge(self):
        lose = World(reached=False)
        self.m.arena_models = lambda: (lose, lose, lose)
        self.m.arena_shape = {"matches": 4, "rounds": 1}  # 4 of 10 practice customers, at most 3 never ones
        self.m.run_arena("stock_watch", full=True)
        self.starts.pop()[0]()
        item = self.m.read_arena()[0]["stock_watch"]
        self.assertTrue(item["lost"])
        win = World()
        before = json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]
        self.m.retry_models = lambda: (win, win, win)
        self.m.retry_start = lambda work, name: work()
        self.assertEqual(self.m.try_again("stock_watch"), retry.STARTED)
        self.assertIsNone(self.m.try_note("stock_watch"))
        got = self.m.read_arena()[0]["stock_watch"]["retry"]
        self.assertTrue(got["results"])
        self.assertEqual({r["result"] for r in got["results"]}, {"won"})
        self.assertGreater(win.calls["judge"], 0)
        calls = json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))
        self.assertGreater(calls["calls"], before)  # counted beside the database, as its practice runs are
        self.assertFalse(self.m.gate("stock_watch")["passed"])  # a try never unlocks Connect

    def test_it_plays_the_last_rounds_lost_practice_matches_never_a_test_customer(self):
        from arena import practice
        lose = World(reached=False)  # every match lost: practice and test alike
        self.m.arena_models = lambda: (lose, lose, lose)
        self.m.arena_shape = {"matches": 4, "rounds": 1}  # 4 of 10 practice customers, at most 3 never ones
        self.m.run_arena("stock_watch", full=True)
        self.starts.pop()[0]()
        test = {e["id"] for e in json.loads((self.folder / practice.TEST_FILE).read_text(encoding="utf-8"))["test"]}
        self.assertEqual(len(test), 10)
        item = self.m.read_arena()[0]["stock_watch"]
        self.assertTrue(item["lost"])
        self.assertFalse({x["card"] for x in item["lost"]} & test)
        self.m.retry_models = lambda: (lose, lose, lose)
        self.m.retry_start = lambda work, name: work()
        self.m.try_again("stock_watch")
        self.assertIsNone(self.m.try_note("stock_watch"))
        played = [r["card"] for r in self.m.read_arena()[0]["stock_watch"]["retry"]["results"] if r["result"] != "not_played"]
        self.assertTrue(played)
        self.assertFalse(set(played) & test)

    def test_the_try_is_judged_by_the_third_model(self):
        lose = World(reached=False)
        self.m.arena_models = lambda: (lose, lose, lose)
        self.m.arena_shape = {"matches": 4, "rounds": 1}  # 4 of 10 practice customers, at most 3 never ones
        self.m.run_arena("stock_watch", full=True)
        self.starts.pop()[0]()
        agent, customer, judge = World(), World(), World()
        self.m.retry_models = lambda: (agent, customer, judge)
        self.m.retry_start = lambda work, name: work()
        self.m.try_again("stock_watch")
        self.assertIsNone(self.m.try_note("stock_watch"))
        self.assertGreater(judge.calls["judge"], 0)
        self.assertEqual((agent.calls["judge"], customer.calls["judge"]), (0, 0))

    def test_a_folder_that_is_gone_is_refused(self):
        import shutil
        self.item(gate_won=0, gate_played=10, gate_size=10, needs=7,
                  lost=[{"card": "c1", "why": "x", "quote": {"turn": 1, "who": "agent", "text": "Hi"}}])
        shutil.rmtree(self.folder)
        with self.assertRaises(mo.Refused) as e:
            self.m.try_again("stock_watch")
        self.assertEqual(str(e.exception), mo.TRY_NOT_BUILT)


class TryAgainHandsTheCorrections(Tab):
    def test_a_correction_that_passed_since_the_run_is_handed_in_the_try(self):
        import time
        from engine.lessons import HOTFIX_SOURCE
        from engine.lessons import Lessons as EngineLessons
        from kit import turn
        from tests.test_levels_study import FIRST, Climb
        world = Climb((self.folder / "instructions.md").read_text(encoding="utf-8"))
        self.m.arena_models = lambda: (world, world, world)
        self.m.arena_shape = {"matches": 4, "rounds": 1}  # 4 of 10 practice customers, at most 3 never ones
        self.m.run_arena("stock_watch", full=True)
        self.starts.pop()[0]()
        self.assertEqual(world.handed_seen and max(n for n, _ in world.handed_seen), 0)
        EngineLessons(self.db, turn.load(self.folder).plug)
        now = time.time()
        with self.db.tx() as c:
            lid = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, share, ends_at, source, "
                            "origin, kind, added_at) VALUES ('stock_watch', ?, 'all', '', 'low', 'trying', 1, ?, ?, "
                            "'person', 'pattern', ?)", (FIRST, now + 86400, HOTFIX_SOURCE, now)).lastrowid
            c.execute("INSERT INTO lesson_exams (lesson_id, agent, passed, at) VALUES (?, 'stock_watch', 1, ?)",
                      (lid, now))
        self.m.retry_models = lambda: (world, world, world)
        self.m.retry_start = lambda work, name: work()
        world.handed_seen.clear()
        world.flip = 1  # one lesson handed wins every second match: the try's first match is a won one
        self.m.try_again("stock_watch")
        self.assertIsNone(self.m.try_note("stock_watch"))
        self.assertTrue(world.handed_seen)
        self.assertTrue(all(n == 1 for n, _ in world.handed_seen))
        got = self.m.read_arena()[0]["stock_watch"]["retry"]
        self.assertIn("won", {r["result"] for r in got["results"]})
