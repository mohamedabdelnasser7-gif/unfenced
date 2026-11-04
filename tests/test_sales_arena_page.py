"""Train and Take the gate on the page for the Sales agent, and the stuck card's next step (DECISIONS 96 and
102; reflection/morning.py run_arena, run_train, trained, next_step; reflection/reflect_now.py run_arena;
pages.py run_arena). The Sales agent practises on its copy <db>.arena; Train studies the chats it lost there at
once, and only a lesson that passed the gate and the full exam reaches the live database. Run reflection reads
real customer chats only. Fake models only: no model call, no network; the cards are made here, never read from
arena/real/."""
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


class SalesTrain(Base):
    def test_train_plays_a_short_round_then_studies_its_losses_at_once_and_only_a_passed_lesson_goes_live(self):
        self.assertEqual(self.m.run_train("sales"), mo.TRAIN_STARTED)
        self.assertIsNone(self.m.arena_note("sales"))
        saved = self.m.read_arena()[0]["sales"]
        self.assertIs(saved["quick"], True)  # the short run's item, saved although it did not pass
        self.assertEqual(saved["gate_played"], 1)
        losses = self.m.arena_losses("sales")
        self.assertEqual(len(losses), mo.SHORT_MATCHES)  # each lost practice match, a case in the copy
        self.assertTrue(reflect_now.arena_path(self.path).is_file())
        self.assertEqual(self.live_arena_cases(), [])  # never in the live log
        done = self.m.trained("sales")
        self.assertEqual(done["lost"], mo.SHORT_MATCHES)
        live = self.live_lessons()
        self.assertIn(GOOD, live)  # passed the gate and the full exam: in the live database
        self.assertEqual(done["cards"], [live[GOOD]["id"]])
        self.assertEqual((done["written"], done["passed"]), (1, 1))
        self.assertEqual(self.exams.seen, [GOOD])
        self.assertEqual(self.full.seen, [GOOD])  # the full exam before live
        self.assertEqual([(x["text"], x["exam"]) for x in done["seen"]], [(GOOD, reflect_now.PASSED)])
        self.assertIsNone(self.m.training("sales"))
        page = self.page()
        self.assertIn(GOOD, page)  # the lesson it showed, with its exam word
        self.assertIn(mo.LIVE_EXAM[reflect_now.PASSED], page)
        self.assertIn(f"{mo.SHORT_MATCHES} lost matches studied, 1 lesson written, 1 passed the exam.", page)

    def test_run_reflection_never_reads_the_arena_losses(self):
        # DECISIONS 102: the Sales agent's Arena losses are Train's to study; Run reflection reads real chats only
        self.play(ideas=())
        self.m.run_train("sales")
        self.assertEqual(len(self.m.arena_losses("sales")), mo.SHORT_MATCHES)
        self.assertEqual(self.m.lost_count("sales"), 0)
        self.assertEqual(self.m.reflect_ready("sales"), mo.NO_LOST)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("sales")
        self.assertEqual(str(e.exception), mo.NO_LOST)
        self.assertIsNone(self.m.reflected("sales"))

    def refused(self, refuse=(), full_refuse=()):
        self.play(refuse=refuse, full_refuse=full_refuse)
        self.m.run_train("sales")
        self.assertNotIn(GOOD, self.live_lessons())
        done = self.m.trained("sales")
        self.assertEqual((done["cards"], done["written"], done["passed"]), ([], 1, 0))
        self.assertEqual([(x["text"], x["exam"]) for x in done["seen"]], [(GOOD, reflect_now.FAILED)])
        page = self.page()
        self.assertIn(f"{mo.SHORT_MATCHES} lost matches studied, 1 lesson written, 0 passed the exam.", page)
        self.assertIn(mo.LIVE_EXAM[reflect_now.FAILED], page)

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

    def test_the_sales_page_has_train_and_take_the_gate_and_the_line_that_training_never_unlocks_connect(self):
        page = self.page()
        train = page.split(f'action="{mo.TRAIN_PATH}"')
        self.assertEqual(len(train), 2)
        self.assertNotIn('name="full"', train[1].split("</form>")[0])
        self.assertIn(f"{mo.TRAIN_BUTTON}</button>", train[1].split("</form>")[0])
        forms = page.split(f'action="{pages.ARENA_PATH}"')
        self.assertEqual(len(forms), 2)  # Take the gate only: the short run has no button of its own now
        self.assertIn('name="full" value="yes"', forms[1].split("</form>")[0])
        self.assertIn(f"{mo.GATE_BUTTON}</button>", forms[1])
        self.assertIn(mo.TRAIN_SAID, page)
        self.assertIn("Training never unlocks Connect.", page)
        self.assertIn(mo.GATE_SAID, page)
        self.assertLess(page.index(mo.TRAIN_SAID), page.index(mo.GATE_SAID))  # Train, then Take the gate
        self.assertEqual((mo.TRAIN_BUTTON, mo.GATE_BUTTON), ("Train", "Take the gate"))

    def test_the_sales_agent_needs_the_database_folder(self):
        self.m.db_path = None
        for go in (self.m.run_arena, self.m.run_train):
            with self.subTest(go=go.__name__), self.assertRaises(mo.Refused) as e:
                go("sales")
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
    """next_step reads the newest gate run (a full run, quick=False) and the page's last Train (DECISIONS 102)."""

    def gate_run(self, run, at, won, played, stopped="rounds"):
        item(self.dir, "sales", run, at, won, played, stopped=stopped, quick=False)

    def trained(self, at, cards):
        self.m._trained["sales"] = {"at": at, "cards": cards, "lost": 2, "written": len(cards), "passed": len(cards),
                                    "notes": [], "queued": 0, "seen": []}

    def test_after_a_gate_run_that_did_not_pass_it_names_train(self):
        self.gate_run("r1", 1000.0, 0, 1)
        self.assertEqual(self.m.next_step("sales"), {"kind": "train", "n": 0, "lower": False})
        self.assertIn(mo.NEXT_TRAIN, self.page())
        self.assertIn(mo.NEXT_TRAIN, mo.render(self.m.view()))
        self.assertEqual(mo.NEXT_TRAIN, "Train to learn from what it lost, then take the gate again.")

    def test_a_short_run_is_never_a_gate_run(self):
        item(self.dir, "sales", "r1", 1000.0, 0, 1)  # quick: a Train's round, not the gate
        self.assertIsNone(self.m.next_step("sales"))
        self.gate_run("r0", 500.0, 0, 1)
        item(self.dir, "sales", "r2", 2000.0, 1, 1, stopped="passed")  # a quick pass newer than it changes nothing
        self.assertEqual(self.m.next_step("sales")["kind"], "train")

    def test_after_a_train_that_wrote_a_lesson_it_says_take_the_gate_again(self):
        self.gate_run("r1", 1000.0, 0, 1)
        self.trained(2000.0, [7])
        self.assertEqual(self.m.next_step("sales")["kind"], "again")
        page = self.page()
        self.assertIn(mo.NEXT_AGAIN, page)
        self.assertNotIn(mo.NEXT_TRAIN, page)
        self.assertEqual(mo.NEXT_AGAIN, "Take the gate again to see if it helped.")

    def test_a_train_before_the_newest_gate_run_does_not_count(self):
        self.gate_run("r1", 3000.0, 0, 1)
        self.trained(2000.0, [7])
        self.assertEqual(self.m.next_step("sales")["kind"], "train")

    def test_after_two_gate_runs_with_no_gain_it_links_the_correction_and_for_the_sales_agent_no_risk_level(self):
        self.gate_run("r1", 1000.0, 1, 2)
        self.gate_run("r2", 2000.0, 1, 2)
        self.assertEqual(self.m.next_step("sales"), {"kind": "no_gain", "n": 0, "lower": False})
        page = self.page()
        self.assertIn('Two runs without a gain. <a href="/agents/sales#say">Send a correction on this page</a>.', page)
        self.assertNotIn("lower the risk level", page)
        self.assertIn('id="say"', self.page(query={}))  # the correction box it links to, on the Overview

    def test_a_gain_or_a_passed_run_before_is_no_two_runs_without_a_gain(self):
        self.gate_run("r1", 1000.0, 0, 2)
        self.gate_run("r2", 2000.0, 1, 2)
        self.assertEqual(self.m.next_step("sales")["kind"], "train")
        self.gate_run("r0", 500.0, 1, 1)  # older than both: not the run before the newest
        self.assertEqual(self.m.next_step("sales")["kind"], "train")
        self.gate_run("r3", 3000.0, 1, 2)  # 1 of 2 again after 1 of 2: no gain
        self.assertEqual(self.m.next_step("sales")["kind"], "no_gain")
        self.gate_run("r4", 4000.0, 2, 2, stopped="passed")  # the newest passed: no step
        self.assertIsNone(self.m.next_step("sales"))

    def test_a_train_that_found_no_lesson_points_to_the_correction(self):
        self.gate_run("r1", 1000.0, 0, 1)
        self.trained(2000.0, [])
        self.assertEqual(self.m.next_step("sales")["kind"], "no_lesson")
        self.assertIn('Training found no lesson in what it lost. <a href="/agents/sales#say">Send a correction on '
                      'this page</a>.', self.page())

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
        item(base.dir, "stock_watch", "r1", time.time() - 60, 0, 1, quick=False)
        step = base.m.next_step("stock_watch")
        self.assertEqual((step["kind"], step["lower"]), ("train", True))
        self.assertIn(mo.NEXT_TRAIN, base.page(query=ARENA_TAB))


class Cap(Base):
    def test_train_counts_every_call_of_its_round_and_its_reflection_on_the_days_count(self):
        self.m.run_train("sales")
        self.assertGreater(self.night.calls + self.exam_model.calls, 0)  # it reflected
        self.assertEqual(self.count(), self.fakes())  # every Arena, study and exam call, on the one count file

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
