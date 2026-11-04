"""Run the Arena on the page for the Sales agent, the short run and Full run, and the stuck card's next step
(DECISIONS 96; reflection/morning.py run_arena, lost_count, next_step; reflection/reflect_now.py run_arena;
pages.py run_arena). The Sales agent practises on its copy <db>.arena; its Run reflection studies the chats
it lost there, and only a lesson that passed the gate and the full exam reaches the live database. Fake
models only: no model call, no network; the cards are made here, never read from arena/real/."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from arena import learn, practice, run as run_mod
from engine import exam as engine_exam
from engine import plug as plug_mod
from kit.db import Db
from reflection import morning as mo, pages, reflect_now
from reflection.lessons import Lessons as SalesLessons
from tests.fake_model import clean_env
import tests.test_arena_practice as tap
import tests.test_arena_rounds as tar
import tests.test_quickstart as tq

GOOD, BAD = tar.GOOD, tar.BAD
ARENA_TAB = {"tab": ["arena"]}


def item(reports, agent, run, at, won, played, stopped="rounds", quick=True):
    """An Arena item as the page reads it (read_arena), written by hand: never sealed, so never a gate pass."""
    doc = {"agent": agent, "kind": "arena_rounds", "at": at, "run": run, "line": "The Arena ran 1 round.",
           "gate_won": won, "gate_played": played, "needs": 1, "stopped": stopped, "quick": quick, "lost": []}
    (Path(reports) / f"arena-{agent}-{run}.json").write_text(json.dumps(doc), encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.cards = self.dir / "cards"
        self.cards.mkdir()
        for c in (tar.card(1, "price"), tar.card(2, "fit"), tar.card(3, "size")):
            (self.cards / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "sales" / "plug.json")], reports=self.dir,
                            db_path=self.path)
        self.m.arena_cards = self.cards
        self.m.arena_start = lambda work, name: work()  # the thread's work, at once
        self.m.reflect_start = lambda work, name: work()
        self.calls_file = self.dir / run_mod.CALLS_FILE
        self.play(buyers=())
        self.p = pages.Pages(self.m)

    def play(self, buyers=(), ideas=(GOOD,), refuse=(), full_refuse=()):
        """Fake models for the Arena and Run reflection: a customer that buys only on the worries in buyers,
        the night's model writing ideas, the exam and the full exam refusing the lines named."""
        self.agent, self.customer = tar.Agent(), tar.Customer(buyers)
        self.night, self.exam_model = tar.Night(ideas, self.agent, self.calls_file), tar.ExamModel()
        self.exams, self.full = tar.Exams(refuse), tar.Exams(full_refuse)
        self.m.arena_models = lambda: (self.agent, self.customer, None)
        between = lambda: {"study": self.night, "open": self.night, "exam": self.exam_model,  # noqa: E731
                           "examiner": self.exams, "full": self.full}
        self.m.arena_reflection = between
        self.m.reflection_models = between

    def count(self):
        try:
            return json.loads(self.calls_file.read_text(encoding="utf-8"))["calls"]
        except FileNotFoundError:
            return 0

    def fakes(self):
        return len(self.agent.systems) + self.customer.calls + self.night.calls + self.exam_model.calls

    def live_lessons(self):
        d = Db(str(self.path))
        self.addCleanup(d.close)
        return {les["text"]: les for les in SalesLessons(d).mine()}

    def live_arena_cases(self):
        with self.db.tx() as c:
            return [r[0] for r in c.execute("SELECT case_id FROM trace WHERE json_extract(detail, '$.arena') = 1")]

    def page(self, agent="sales", query=ARENA_TAB, token="t"):
        return self.p.get(f"/agents/{agent}", query, token).split("</style>")[1].split("<script>")[0]


class SalesShortRun(Base):
    def test_its_losses_land_where_its_run_reflection_reads_them_and_only_a_passed_lesson_goes_live(self):
        self.assertEqual(self.m.run_arena("sales"), mo.ARENA_STARTED)
        self.assertIsNone(self.m.arena_note("sales"))
        saved = self.m.read_arena()[0]["sales"]
        self.assertIs(saved["quick"], True)  # the short run's item, saved although it did not pass
        self.assertEqual(saved["gate_played"], 1)
        losses = self.m.arena_losses("sales")
        self.assertEqual(len(losses), mo.SHORT_MATCHES)  # each lost practice match, a case in the copy
        self.assertTrue(reflect_now.arena_path(self.path).is_file())
        self.assertEqual(self.live_arena_cases(), [])  # never in the live log
        self.assertEqual(self.m.lost_count("sales"), mo.SHORT_MATCHES)
        self.assertIsNone(self.m.reflect_ready("sales"))  # Run reflection can start: it has lost chats now
        self.assertEqual(self.m.run_reflection("sales"), mo.REFLECT_STARTED)
        self.assertIsNone(self.m.reflect_note("sales"))
        done = self.m.reflected("sales")
        self.assertEqual(done["lost"], mo.SHORT_MATCHES)
        live = self.live_lessons()
        self.assertIn(GOOD, live)  # passed the gate and the full exam: in the live database
        self.assertEqual(done["cards"], [live[GOOD]["id"]])
        self.assertEqual(self.exams.seen, [GOOD])
        self.assertEqual(self.full.seen, [GOOD])  # the full exam before live
        self.assertIn(GOOD, self.page())  # its lesson row on the page

    def test_it_still_reads_them_days_after_the_run(self):
        self.m.run_arena("sales")
        self.m.run_reflection("sales", now=time.time() + 5 * 86400)
        self.assertEqual(self.m.reflected("sales")["lost"], mo.SHORT_MATCHES)
        self.assertIn(GOOD, self.live_lessons())

    def refused(self, refuse=(), full_refuse=()):
        self.play(refuse=refuse, full_refuse=full_refuse)
        self.m.run_arena("sales")
        self.m.run_reflection("sales")
        self.assertNotIn(GOOD, self.live_lessons())
        done = self.m.reflected("sales")
        self.assertEqual((done["cards"], done["written"]), ([], 1))
        self.assertIn("It wrote 1 lesson from them; none passed the exam, so none reaches a real customer.",
                      self.page())

    def test_a_lesson_the_exam_refuses_never_reaches_the_live_database(self):
        self.refused(refuse=(GOOD,))
        self.assertEqual(self.full.seen, [])  # refused first: no full exam

    def test_a_lesson_the_full_exam_refuses_never_reaches_the_live_database(self):
        self.refused(full_refuse=(GOOD,))
        self.assertEqual(self.full.seen, [GOOD])

    def test_with_no_arena_loss_its_run_reflection_reads_the_live_database_as_before(self):
        self.assertEqual(self.m.arena_losses("sales"), [])
        self.assertEqual(self.m.reflect_ready("sales"), mo.NO_LOST)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("sales")
        self.assertEqual(str(e.exception), mo.NO_LOST)

    def test_the_sales_page_has_both_buttons_and_the_line_that_the_short_run_never_unlocks_connect(self):
        page = self.page()
        forms = page.split(f'action="{pages.ARENA_PATH}"')
        self.assertEqual(len(forms), 3)  # Run the Arena and Full run
        self.assertNotIn('name="full"', forms[1].split("</form>")[0])
        self.assertIn('name="full" value="yes"', forms[2].split("</form>")[0])
        self.assertIn(f"{mo.ARENA_FULL_BUTTON}</button>", forms[2])
        self.assertIn(mo.ARENA_SHORT_SAID, page)
        self.assertIn("A short run never unlocks Connect.", page)
        self.assertIn(mo.ARENA_FULL_SAID, page)

    def test_the_sales_agent_needs_the_database_folder(self):
        self.m.db_path = None
        with self.assertRaises(mo.Refused) as e:
            self.m.run_arena("sales")
        self.assertEqual(str(e.exception), mo.ARENA_NO_DB)


class FullAndShort(Base):
    def test_a_short_run_that_wins_never_unlocks_connect_and_a_full_run_that_wins_does(self):
        self.play(buyers=("price", "fit", "size"))
        self.m.run_arena("sales")
        self.assertIsNone(self.m.arena_note("sales"))
        saved = self.m.read_arena()[0]["sales"]
        self.assertEqual((saved["quick"], saved["stopped"], saved["gate_won"]), (True, "passed", 1))
        gate = self.m.gate("sales")
        self.assertFalse(gate["passed"])
        self.assertIn("was the quick one", gate["said"])
        self.m.run_arena("sales", full=True)
        self.assertIsNone(self.m.arena_note("sales"))
        saved = self.m.read_arena()[0]["sales"]
        self.assertEqual((saved["quick"], saved["stopped"], saved["sealed"]), (False, "passed", True))
        self.assertEqual(saved["gate_played"], run_mod.PUBLIC_TRUST["matches"])
        self.assertTrue(self.m.gate("sales")["passed"])

    def test_the_page_post_runs_a_full_run_only_with_full_yes(self):
        got = []
        self.m.run_arena = lambda agent, now=None, full=False: got.append((agent, full)) or mo.ARENA_STARTED
        go = self.p.actions[pages.ARENA_PATH]
        go(self.m, {"agent": ["sales"]})
        go(self.m, {"agent": ["sales"], "full": ["yes"]})
        self.assertEqual(got, [("sales", False), ("sales", True)])

    def test_a_built_agents_short_run_is_one_round_marked_quick_and_full_is_its_level_shape(self):
        import tests.test_reflect_button as trb
        base = trb.Base(methodName="setUp")
        base.setUp()
        self.addCleanup(base.doCleanups)
        m = base.m
        m.arena_models = lambda: (object(), object(), object())
        m.arena_start = lambda work, name: work()
        seen = []
        with mock.patch.object(practice, "practise", lambda folder, **kw: seen.append(kw)):
            m.run_arena("stock_watch")
            m.run_arena("stock_watch", full=True)
        short, full = seen
        self.assertEqual((short["quick"], short["matches"], short["limit"]), (True, mo.SHORT_MATCHES, mo.SHORT_CALLS))
        self.assertIsNone(short["study"])  # no study between rounds in a short run
        self.assertNotIn("quick", full)
        self.assertNotIn("limit", full)


class StuckCard(Base):
    def lost_in_copy(self, n):
        """n lost Arena chats in the Sales agent's copy, as its Arena's learner writes them."""
        copy = Db(str(reflect_now.arena_path(self.path)))
        try:
            for i in range(n):
                learn.to_case(copy, {"id": f"r1-t{i:02d}", "card": "persona-01", "turns": [
                    {"customer": "How much?", "replies": ["Let me check."], "outcome": "replied"}]},
                    {"won": False, "why": "no price", "quote": {"turn": 1, "who": "agent", "text": "Let me check."}},
                    f"r1-t{i:02d}")
        finally:
            copy.close()

    def test_after_a_run_with_losses_it_names_run_reflection_on_them(self):
        item(self.dir, "sales", "r1", 1000.0, 0, 1)
        self.lost_in_copy(2)
        self.assertEqual(self.m.next_step("sales"), {"kind": "reflect", "n": 2, "lower": False})
        self.assertIn("Run reflection to learn from these 2 lost chats.", self.page())
        self.assertIn("Run reflection to learn from these 2 lost chats.", mo.render(self.m.view()))

    def test_one_lost_chat_reads_as_one(self):
        item(self.dir, "sales", "r1", 1000.0, 0, 1)
        self.lost_in_copy(1)
        self.assertIn(mo.NEXT_REFLECT_ONE, self.page())

    def test_after_a_reflection_that_wrote_a_lesson_it_says_run_the_arena_again(self):
        item(self.dir, "sales", "r1", 1000.0, 0, 1)
        self.lost_in_copy(2)
        self.m._reflected["sales"] = {"at": 2000.0, "cards": [7], "lost": 2, "read": 2, "candidates": 1, "notes": []}
        self.assertEqual(self.m.next_step("sales")["kind"], "again")
        self.assertIn(mo.NEXT_AGAIN, self.page())
        self.assertNotIn("Run reflection to learn from", self.page())

    def test_a_reflection_before_the_newest_run_does_not_count(self):
        item(self.dir, "sales", "r1", 3000.0, 0, 1)
        self.lost_in_copy(2)
        self.m._reflected["sales"] = {"at": 2000.0, "cards": [7], "lost": 2, "read": 2, "candidates": 1, "notes": []}
        self.assertEqual(self.m.next_step("sales")["kind"], "reflect")

    def test_after_two_runs_with_no_gain_it_links_the_correction_and_for_the_sales_agent_no_risk_level(self):
        item(self.dir, "sales", "r1", 1000.0, 1, 2)
        item(self.dir, "sales", "r2", 2000.0, 1, 2)
        self.lost_in_copy(2)
        self.assertEqual(self.m.next_step("sales"), {"kind": "no_gain", "n": 0, "lower": False})
        page = self.page()
        self.assertIn('Two runs without a gain. <a href="/agents/sales#say">Send a correction on this page</a>.', page)
        self.assertNotIn("lower the risk level", page)
        self.assertIn('id="say"', self.page(query={}))  # the correction box it links to, on the Overview

    def test_a_gain_or_a_passed_run_before_is_no_two_runs_without_a_gain(self):
        item(self.dir, "sales", "r1", 1000.0, 0, 2)
        item(self.dir, "sales", "r2", 2000.0, 1, 2)
        self.lost_in_copy(2)
        self.assertEqual(self.m.next_step("sales")["kind"], "reflect")
        item(self.dir, "sales", "r0", 500.0, 1, 1)  # older than both: not the run before the newest
        self.assertEqual(self.m.next_step("sales")["kind"], "reflect")
        item(self.dir, "sales", "r3", 3000.0, 1, 2)  # 1 of 2 again after 1 of 2: no gain
        self.assertEqual(self.m.next_step("sales")["kind"], "no_gain")
        item(self.dir, "sales", "r4", 4000.0, 2, 2, stopped="passed")  # the newest passed: no step
        self.assertIsNone(self.m.next_step("sales"))

    def test_a_reflection_that_found_no_lesson_points_to_the_correction(self):
        item(self.dir, "sales", "r1", 1000.0, 0, 1)
        self.lost_in_copy(2)
        self.m._reflected["sales"] = {"at": 2000.0, "cards": [], "lost": 2, "read": 2, "candidates": 0, "notes": []}
        self.assertEqual(self.m.next_step("sales")["kind"], "no_lesson")
        self.assertIn("Reflection found no lesson in these chats.", self.page())

    def test_a_built_agent_gets_the_risk_level_link_too(self):
        step = {"kind": "no_gain", "n": 0, "lower": True}
        html = mo.next_step_html(step, "stock_watch")
        self.assertIn('<a href="/agents/stock_watch#say">Send a correction on this page</a>', html)
        self.assertIn(', or <a href="/agents/stock_watch?tab=arena#lv-h">lower the risk level</a>.', html)
        self.assertEqual(mo.next_step_html(None, "x"), "")

    def test_any_agent_on_the_page(self):
        import tests.test_reflect_button as trb
        base = trb.Base(methodName="setUp")
        base.setUp()
        self.addCleanup(base.doCleanups)
        base.lose(2)
        item(base.dir, "stock_watch", "r1", time.time() - 60, 0, 1)
        step = base.m.next_step("stock_watch")
        self.assertEqual((step["kind"], step["lower"]), ("reflect", True))
        self.assertGreater(step["n"], 0)
        self.assertIn("Run reflection to learn from", base.page(query=ARENA_TAB))


class Cap(Base):
    def test_the_short_run_and_the_reflection_count_every_call_on_the_days_count(self):
        self.m.run_arena("sales")
        self.assertEqual(self.count(), self.fakes())  # every Arena call, on the one count file
        before_count, before_fakes = self.count(), self.fakes()
        self.m.run_reflection("sales")
        self.assertGreater(self.night.calls + self.exam_model.calls, 0)
        self.assertEqual(self.count() - before_count, self.fakes() - before_fakes)  # the study's and exams' too

    def test_the_short_run_stops_at_its_own_limit(self):
        with mock.patch.object(mo, "SHORT_CALLS", 5):
            self.m.run_arena("sales")
        self.assertEqual(self.count(), 5)
        self.assertEqual(self.m.read_arena()[0]["sales"]["stopped"], run_mod.CAP)

    def test_no_room_on_the_days_cap_starts_nothing_for_the_sales_agent(self):
        self.calls_file.write_text(json.dumps({"day": run_mod.today(), "calls": run_mod.DEFAULT_CAP,
                                               "cap": run_mod.DEFAULT_CAP}), encoding="utf-8")
        with self.assertRaises(mo.Refused) as e:
            self.m.run_arena("sales")
        self.assertIn("model call cap", str(e.exception))
        self.assertEqual(self.fakes(), 0)
        self.assertFalse(reflect_now.arena_path(self.path).exists())


if __name__ == "__main__":
    unittest.main()
