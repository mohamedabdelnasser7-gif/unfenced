"""The page polish batch (2026-11-05): the status word In practice, the Arena tab's matches as they land, the
track as steps, the running pill, the console while a run goes, writes.json folded, and Quick start's first
run counted as the agent's run going (Morning.arena_hold). Each test fails with its change taken back. Fake
models only, no network; every text here is made up."""
import json
import threading
import unittest
from unittest import mock

from arena import practice
from reflection import console, morning as mo, page_css, pages, quickstart as qs
from tests.fake_model import FakeModel
import tests.test_any_agent as taa  # the module, never its classes: their tests would run here twice

RUN = "20261105T120000"


def match(n, won, why="", **more):
    """One judged practice match line, as the matches file holds it."""
    return json.dumps({"id": f"{RUN}-r1-m{n}", "won": won, "why": why, **more}) + "\n"


class Base(unittest.TestCase):
    """RunTheArena's page and agent (stock_watch, built, with the fake models), without its tests."""

    def setUp(self):
        taa.RunTheArena.setUp(self)
        self.matches = self.folder / "arena-matches.jsonl"

    tab = taa.RunTheArena.tab

    def add(self, *lines):
        with open(self.matches, "a", encoding="utf-8") as f:
            f.write("".join(lines))


class StatusWord(Base):
    def test_an_agent_not_live_reads_in_practice_and_never_training(self):
        for page in (self.p.get("/agents", {}, "t"), self.p.get("/agents/stock_watch", {}, "t")):
            body = page.split("</style>")[1]
            self.assertIn(">In practice<", body)
            self.assertNotIn(">Training<", body)
        self.assertEqual(pages.status_of(self.m, "stock_watch"), "In practice")
        self.assertIn("In practice", pages.STATUS_SAID)
        self.assertIn("white-space:nowrap}\n.st.live", page_css.CSS)  # the chip never wraps


class SoFar(Base):
    def test_it_reads_only_the_lines_gained_since_the_run_started_newest_first(self):
        self.add(match(0, True, "an old run"))
        self.assertIsNone(self.m.arena_so_far("stock_watch"))  # no run goes
        self.m.run_arena("stock_watch", full=True)
        self.assertEqual(self.m.arena_so_far("stock_watch"), {"played": 0, "won": 0, "rows": []})
        self.add(match(1, False, "it guessed the stock"), '{"not judged": 1}\n', "not json\n",
                 match(2, True, "a clear answer"))
        got = self.m.arena_so_far("stock_watch")
        self.assertEqual(got["played"], 4)
        self.assertEqual(got["won"], 1)
        self.assertEqual([x["id"] for x in got["rows"]], [f"{RUN}-r1-m2", f"{RUN}-r1-m1"])

    def test_it_keeps_only_the_newest_bytes_and_rows(self):
        self.m.run_arena("stock_watch", full=True)
        self.add(*(match(n, n % 2 == 0, "x" * 40) for n in range(10)))
        with mock.patch.object(mo, "SO_FAR_TAIL", len(match(9, False, "x" * 40)) * 3), \
                mock.patch.object(mo, "SO_FAR_ROWS", 2):
            got = self.m.arena_so_far("stock_watch")
        self.assertEqual(got["played"], 10)  # the count is every line gained
        self.assertEqual([x["id"] for x in got["rows"]], [f"{RUN}-r1-m9", f"{RUN}-r1-m8"])

    def test_the_tab_shows_each_match_as_it_lands_and_the_saved_run_after(self):
        self.m.run_arena("stock_watch", full=True)
        self.add(match(1, False, "it guessed the stock"), match(2, True, "a clear answer"))
        page = self.tab()
        tiles = page.split('<div class="tiles">')[1].split("</div></section>")[0]
        self.assertIn(pages.SO_FAR_SUB, page)
        self.assertLess(tiles.index("A clear answer."), tiles.index("It guessed the stock."))  # newest first
        self.assertIn('<span class="res">Won</span>', tiles)
        self.assertIn('<span class="res">Lost</span>', tiles)
        self.assertIn('class="qs arq"', page)
        self.assertIn('data-live="tiles" data-running', page)  # inside the part the poll swaps
        self.starts[0][0]()  # the run ends
        page = self.tab()
        self.assertNotIn(pages.SO_FAR_SUB, page)
        self.assertNotIn("It guessed the stock.", page)


class TrackSteps(Base):
    def test_each_step_has_its_number_and_its_state_in_words_and_no_pill(self):
        track = self.tab().split('<ol class="trk"')[1].split("</ol>")[0]
        self.assertIn('<li class="next"><span class="n" aria-hidden="true">1</span>', track)
        self.assertIn('<small class="vh">, Next</small>', track)
        self.assertNotIn(f"<small>{mo.DONE_WORD}</small>", track)
        self.assertNotIn(".trk li.next{background", page_css.CSS)
        self.assertIn(".trk li + li::before", page_css.CSS)  # the line between steps
        done = pages.track_step(2, "Run the Arena", "done")
        self.assertIn(pages.icon("check"), done)
        self.assertIn(f'<small class="vh">, {mo.DONE_WORD}</small>', done)


class RunningPill(Base):
    def test_a_run_going_shows_a_pill_with_a_turning_ring_in_place_of_its_button(self):
        self.m.run_arena("stock_watch", full=True)
        page = self.tab()
        self.assertIn('<span class="runp"><span class="spin" aria-hidden="true"></span><span role="status">Running '
                      'the Arena: its first matches are starting.</span></span>', page)
        self.assertNotIn('class="no-yet" role="status">Running', page)
        self.assertIn("@keyframes spin", page_css.CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce){ .runp .spin{animation:none} }", page_css.CSS)


class ConsoleWhileRunning(Base):
    def test_the_bar_marks_the_arena_while_a_run_or_a_train_goes(self):
        self.assertIsNone(console.running(self.m, "stock_watch", [], 0))
        self.m.run_arena("stock_watch", full=True)
        self.assertEqual(console.running(self.m, "stock_watch", [], 0), "A")
        self.starts[0][0]()
        self.assertIsNone(console.running(self.m, "stock_watch", [], 0))
        with mock.patch.object(self.m, "training", return_value="lesson"):
            self.assertEqual(console.running(self.m, "stock_watch", [], 0), "A")

    def test_the_card_and_the_rows_show_the_matches_so_far(self):
        self.m.run_arena("stock_watch", full=True)
        self.add(match(1, False, "it guessed the stock"), match(2, True, "a clear answer"))
        data = console.collect(self.m, "stock_watch")
        self.assertEqual(data["so_far"], {"played": 2, "won": 1})
        self.assertIn("running: 2 played, 1 won so far", console.cards_html(data))
        st = console.state_of({"view": ["arena"]}, "stock_watch")
        rows = console.arena_html(data, st, None)
        self.assertIn("running: 2 played so far", rows)
        self.assertLess(rows.index(f"{RUN}-r1-m2"), rows.index(f"{RUN}-r1-m1"))
        self.assertIn("training, running", rows)
        self.assertIn(f"running: match {RUN}-r1-m1 lost: it guessed the stock", [r["text"] for r in data["records"]])
        self.assertEqual(console.find(data, f"m.{RUN}-r1-m1")[1]["why"], "it guessed the stock")


class RawRecordsFolded(Base):
    def test_writes_json_sits_inside_a_details_the_poll_keeps(self):
        page = self.p.get("/console", {"agent": ["stock_watch"]}, "t")
        raw = page.split('<details class="raw">')[1].split("</details>")[0]
        self.assertIn("Raw records (writes.json)", raw.split("</summary>")[0])
        self.assertIn('data-live="writes"', raw.split("</summary>")[1])
        self.assertIn("details.raw>summary", console.CSS)


class FirstRunCounts(Base):
    """Item 9: the first Arena run Build starts (QuickStart.start_practice) is the agent's run going."""

    def quick(self, practise):
        for p in (mock.patch.object(qs.model_mod, "has_key", return_value=True),
                  mock.patch.object(qs.model_mod, "Model", lambda *a, **k: FakeModel()),
                  mock.patch.object(practice, "practise", practise)):
            p.start()
            self.addCleanup(p.stop)
        return qs.QuickStart()

    @staticmethod
    def wait(agent):
        for t in threading.enumerate():
            if t.name == f"practice-{agent}":
                t.join(5)

    def test_while_it_plays_the_arena_tab_and_the_console_see_it_and_it_ends_with_it(self):
        self.add(match(0, True, "an old run"))
        go, seen = threading.Event(), []

        def practise(folder, **kw):
            self.add(match(1, False, "it guessed the stock"))
            seen.append((self.m.arena_running("stock_watch"), self.m.arena_played("stock_watch")))
            go.wait(5)
        quick = self.quick(practise)
        self.assertEqual(quick.start_practice(self.m, "stock_watch"), qs.PRACTISING)
        self.assertTrue(self.m.arena_running("stock_watch"))
        for _ in range(500):
            if seen:
                break
            threading.Event().wait(0.01)
        self.assertEqual(seen, [(True, 1)])  # its start is the file's length when it began, as Run the Arena's
        self.assertEqual(self.m.arena_run("stock_watch"), (self.folder, 1))
        self.assertEqual([x["id"] for x in self.m.arena_so_far("stock_watch")["rows"]], [f"{RUN}-r1-m1"])
        self.assertIn('class="runp"', self.tab())
        self.assertEqual(console.running(self.m, "stock_watch", [], 0), "A")
        with self.assertRaises(mo.Refused):
            self.m.run_arena("stock_watch", full=True)
        go.set()
        self.wait("stock_watch")
        self.assertFalse(self.m.arena_running("stock_watch"))
        self.assertIsNone(self.m.arena_run("stock_watch"))
        self.assertEqual(quick.practice_line("stock_watch"), qs.PRACTICE_DONE)

    def test_it_counts_in_its_own_folder_before_the_agent_joins_the_page(self):
        m = mo.Morning(self.db, [], reports=self.dir, db_path=self.dir / "ascent.db")  # Build done, not joined
        self.assertIsNone(m.agent_folder("stock_watch"))
        self.assertTrue(m.arena_hold("stock_watch", self.folder))
        self.add(match(1, True, "a clear answer"))
        self.assertEqual(m.arena_played("stock_watch"), 1)
        self.assertEqual(m.arena_so_far("stock_watch")["won"], 1)
        m.arena_release("stock_watch")
        self.assertFalse(m.arena_running("stock_watch"))
        self.assertEqual(m.arena_played("stock_watch"), 0)

    def test_a_run_going_already_is_never_held_twice_nor_released_by_it(self):
        self.m.run_arena("stock_watch", full=True)
        self.assertFalse(self.m.arena_hold("stock_watch", self.folder))
        quick = self.quick(lambda folder, **kw: None)
        quick.start_practice(self.m, "stock_watch")
        self.wait("stock_watch")
        self.assertTrue(self.m.arena_running("stock_watch"))  # the Run the Arena still goes

    def test_a_thread_that_cannot_start_holds_nothing(self):
        quick = self.quick(lambda folder, **kw: None)
        with mock.patch.object(qs.threading, "Thread", side_effect=RuntimeError("no threads")), \
                self.assertRaises(RuntimeError):
            quick.start_practice(self.m, "stock_watch")
        self.assertFalse(self.m.arena_running("stock_watch"))
        self.assertFalse(quick.practising("stock_watch"))


if __name__ == "__main__":
    unittest.main()
