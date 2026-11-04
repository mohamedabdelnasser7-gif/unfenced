"""Run reflection on an agent's page (DECISIONS 92 and 93; reflection/reflect_now.py, Morning.run_reflection,
pages.py REFLECT_PATH), and the night lock the Arena and a night run by hand now read (review reflectbtn r1).
Fake models only: no model call, no network."""
import contextlib
import http.client
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from arena import learn_built, retry as retry_mod, run as run_mod, scope
from engine import exam as engine_exam, plug as plug_mod
from engine.lessons import Lessons as EngineLessons
from kit import turn
from kit.db import Db
from reflection import PLUG as SALES
from reflection import exam as exam_mod, judge as judge_mod, shared as shared_mod, study as parts
from reflection import morning as mo, night, pages, reflect_now, scheduler
from reflection.lessons import Lessons as SalesLessons
from tests.fake_model import Buyer, Seller, clean_env, say
from tests.kept import kept_lesson
from tests.test_night import Setup as NightSetup
import tests.test_arena_gate as tag
import tests.test_arena_practice as tap
import tests.test_quickstart as tq
import tests.test_turn_exam as tte

ARENA_TAB = {"tab": ["arena"]}
TURNS = [{"n": 1, "customer": "Is the blue mug in stock?", "replies": ["Let me check."], "outcome": "replied",
          "tools": ["store"], "actions": [], "failed": []},
         {"n": 2, "customer": "So?", "replies": ["It may come back soon."], "outcome": "replied", "tools": [],
          "actions": [], "failed": []}]


class Quiet:
    """A fake model: every call counted, every answer an empty list, so each part finds nothing."""

    route = types.SimpleNamespace(name="fake")
    model_id = "fake"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        return {"role": "assistant", "content": "[]"}


def match(mid, won):
    return {"id": mid, "card": "made-up-01", "worry": "a late answer", "made_up": True, "turns": TURNS,
            "agent": "stock_watch", "won": won, "why": "a clear answer" if won else "no stock answer",
            "quote": {"turn": 2, "who": "agent", "text": "x"}}


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.folder = self.dir / "agents" / "stock_watch"
        shutil.copytree(tap.FIXTURE, self.folder)
        plug = json.loads((self.folder / "plug.json").read_text())  # a bad result, as Build always names one
        plug["results"]["chat_closed"] = {"speed": "fast", "about": "The chat closed with no stock answer."}
        plug["decides"]["bad"] = ["chat_closed"]
        (self.folder / "plug.json").write_text(json.dumps(plug))
        self.db = Db(str(self.dir / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "sales" / "plug.json")], reports=self.dir,
                            db_path=self.dir / "ascent.db")
        self.assertEqual(self.m.add_built(), ["stock_watch"])
        self.model = Quiet()
        self.m.reflection_models = lambda: {"study": self.model, "open": self.model, "exam": self.model}
        self.starts = []
        self.m.reflect_start = lambda work, name: self.starts.append((work, name))
        self.p = pages.Pages(self.m)

    def lose(self, n=2):
        """n lost practice matches of stock_watch as cases (as Run the Arena's learner writes them), and
        the won and lost ones in its folder (as the night's from_folder reads them)."""
        plug = turn.load(self.folder).plug
        matches = []
        for i in range(n):
            lost = match(f"r1-t{2 * i}", False)
            learn_built.to_case(self.db, plug, lost, {"won": False, "why": lost["why"], "quote": lost["quote"]},
                                lost["id"])
            matches += [lost, match(f"r1-t{2 * i + 1}", True)]
        (self.folder / "arena-matches.jsonl").write_text("".join(json.dumps(x) + "\n" for x in matches))

    def page(self, agent="stock_watch", query=None, token="t"):
        return self.p.get(f"/agents/{agent}", query or {}, token).split("</style>")[1].split("<script>")[0]

    def held_by(self):
        self.db.script(scheduler.SCHEMA)
        with self.db.tx() as c:
            row = c.execute("SELECT holder FROM night_lock WHERE id = 1").fetchone()
        return None if row is None else row["holder"]


class TheButton(Base):
    def test_on_the_overview_with_the_owners_words_under_it_and_not_on_the_arena_tab(self):
        # DECISIONS 102 and 104: Run reflection stays for real customer chats, on the Overview; the Arena tab has
        # Run the Arena (Train only after a run that did not pass)
        self.lose()
        page = self.page()
        form = page.split(f'action="{pages.REFLECT_PATH}"')[1].split("</form>")[0]
        self.assertIn(f"{mo.REFLECT_BUTTON}</button>", form)
        self.assertIn('name="agent" value="stock_watch"', form)
        after = page.split(f'action="{pages.REFLECT_PATH}"')[1].split("</form>", 1)[1]
        self.assertTrue(after.startswith(f'<p class="quiet">{mo.REFLECT_SAID}</p>'))  # the line under it
        self.assertIn('data-live="reflect"', page)
        arena = self.page(query=ARENA_TAB)
        self.assertNotIn(f'action="{pages.REFLECT_PATH}"', arena)
        self.assertNotIn(mo.REFLECT_SAID, arena)
        self.assertIn(f'action="{pages.ARENA_PATH}"', arena)
        self.assertNotIn(f'action="{mo.TRAIN_PATH}"', arena)
        self.assertEqual(mo.REFLECT_BUTTON, "Run reflection")
        self.assertEqual(mo.REFLECT_SAID, "This is the learning step. The agent reads the chats it lost, writes every "
                         "lesson it finds in them, and tests each one on a full exam before it can reach a real "
                         "customer. It is slow on purpose: it takes as long as it needs to get it right. Uses your "
                         "model key.")

    def test_the_sales_agent_has_it_too_from_its_own_plug(self):
        page = self.page("sales")
        self.assertIn(f"{mo.REFLECT_BUTTON}", page)
        self.assertIn(mo.NO_LOST, page)  # its database has no lost chat
        self.assertEqual(self.p.csp_for("/agents/sales"), pages.AGENT_CSP)

    def test_the_route_takes_the_post_with_the_token(self):
        self.lose()
        server = mo.make_server(self.m, port=0, pages=self.p)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(5)))
        here = f"127.0.0.1:{server.server_address[1]}"

        def post(token):
            form = urllib.parse.urlencode({"token": token, "agent": "stock_watch", "back": "/agents/stock_watch?tab=arena"})
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            try:
                conn.request("POST", pages.REFLECT_PATH, form, {"Host": here, "Origin": f"http://{here}",
                                                               "Content-Type": "application/x-www-form-urlencoded"})
                r = conn.getresponse()
                r.read()
                return r.status, r.getheader("Location")
            finally:
                conn.close()
        self.assertEqual(post("guess")[0], 403)
        self.assertEqual(self.starts, [])
        self.assertEqual(post(server.token), (303, "/agents/stock_watch?tab=arena"))
        self.assertEqual([n for _, n in self.starts], ["reflect-stock_watch"])
        self.assertEqual(self.m.reflecting("stock_watch"), reflect_now.READ)
        self.starts[0][0]()


class Wording(Base):
    def test_no_lost_chats(self):
        page = self.page()
        self.assertEqual(mo.NO_LOST, "No lost chats to learn from yet. In the Arena, Train learns from the matches a "
                                    "run loses.")
        self.assertIn(f'<p class="no-yet" role="status">{mo.NO_LOST}</p>', page)
        self.assertNotIn(f'action="{pages.REFLECT_PATH}"', page)
        self.assertIn(f'disabled>{pages.icon("loop")}{mo.REFLECT_BUTTON}</button>', page)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("stock_watch")
        self.assertEqual(str(e.exception), mo.NO_LOST)
        self.assertEqual(self.starts, [])

    def test_no_key_points_to_the_recorded_replay(self):
        self.lose()
        self.m.reflection_models = None
        with mock.patch.object(night, "missing_keys", return_value=[night.MODEL_KEYS]):
            page = self.page()
            with self.assertRaises(mo.Refused) as e:
                self.m.run_reflection("stock_watch")
        self.assertEqual(mo.NO_KEY, "Reflection needs a model key. Watch a recorded reflection run instead.")
        self.assertIn(f'{mo.NO_KEY} <code>python3 -I recorded/play.py</code>', page)
        self.assertNotIn(f'action="{pages.REFLECT_PATH}"', page)
        self.assertIn(mo.NO_KEY, str(e.exception))
        self.assertIn("python3 -I recorded/play.py", str(e.exception))
        self.assertIn("python3 -I recorded/play.py", (Path(tq.ROOT) / "docs" / "judges.md").read_text())
        self.assertEqual(self.starts, [])

    def test_the_running_line_marks_the_current_step(self):
        self.lose()
        self.assertEqual(self.m.run_reflection("stock_watch"), mo.REFLECT_STARTED)
        self.assertEqual(mo.REFLECT_RUNNING, "Reflecting: reading lost chats, then writing a lesson, then the exam")
        page = self.page()
        self.assertIn('data-live="reflect" data-running', page)
        self.assertIn('Reflecting: <b aria-current="step">reading lost chats</b>, then writing a lesson, then the exam',
                      page)
        self.assertNotIn(f'action="{pages.REFLECT_PATH}"', page)
        steps = self.m._reflecting["stock_watch"]
        steps.mark(reflect_now.LESSON)
        self.assertIn('reading lost chats, then <b aria-current="step">writing a lesson</b>, then the exam',
                      self.page())
        steps.mark(reflect_now.EXAM)
        steps.mark(reflect_now.READ)  # never back
        self.assertIn('then writing a lesson, then <b aria-current="step">the exam</b>', self.page())
        self.starts[0][0]()
        self.assertIsNone(self.m.reflecting("stock_watch"))
        self.assertNotIn("data-running", self.page())

    def test_the_steps_follow_the_proposer_and_the_exam(self):
        steps = reflect_now.Steps()
        model = Quiet()
        steps.marking(model, reflect_now.LESSON).chat([])
        self.assertEqual((steps.at, model.calls), (reflect_now.LESSON, 1))
        self.assertEqual(steps.marking(model, reflect_now.LESSON).route.name, "fake")  # a part's label still reads
        examiner = steps.exam(lambda lessons: lambda text, stages: ("ran", text))(None)
        self.assertEqual(examiner("a line", ("all",)), ("ran", "a line"))
        self.assertEqual(steps.at, reflect_now.EXAM)


class Refusals(Base):
    def test_while_building_or_while_its_first_practice_runs(self):
        self.lose()
        go = self.p.actions[pages.REFLECT_PATH]
        self.p.run = pages.BuildRun(self.m)
        with self.assertRaises(mo.Refused) as e:
            go(self.m, {"agent": ["stock_watch"]})
        self.assertIn("It is building", str(e.exception))
        self.p.run.agent = "other_agent"
        self.p.quick._running.add("stock_watch")
        with self.assertRaises(mo.Refused) as e:
            go(self.m, {"agent": ["stock_watch"]})
        self.assertIn("Its first Arena run is still running.", str(e.exception))
        self.p.quick._running.discard("stock_watch")
        self.assertEqual(self.starts, [])
        self.assertEqual(go(self.m, {"agent": ["stock_watch"]}), mo.REFLECT_STARTED)
        self.starts[0][0]()

    def test_one_run_of_either_kind_per_agent(self):
        self.lose()
        self.m._arenas.add("stock_watch")  # a Run the Arena going
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("stock_watch")
        self.assertEqual(str(e.exception), mo.REFLECT_ARENA)
        self.assertIn(mo.REFLECT_ARENA, self.page())
        self.m._arenas.discard("stock_watch")
        self.assertIsNone(self.held_by())  # a refusal holds no lock
        self.m.run_reflection("stock_watch")
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("stock_watch")
        self.assertEqual(str(e.exception), mo.REFLECT_TWICE)
        self.m.arena_models = lambda: (tap.raises, tap.raises, tap.raises)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_arena("stock_watch")
        self.assertEqual(str(e.exception), mo.ARENA_REFLECTING)
        self.assertEqual(len(self.starts), 1)
        self.starts[0][0]()
        self.assertIsNone(self.held_by())

    def test_an_agent_not_here_and_a_page_with_no_database_folder(self):
        for agent in ("nobody", "../agents", None):
            with self.subTest(agent=agent), self.assertRaises(mo.Refused) as e:
                self.m.run_reflection(agent)
            self.assertEqual(str(e.exception), mo.REFLECT_NOT_HERE)
        self.m.db_path = None
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("sales")
        self.assertEqual(str(e.exception), mo.REFLECT_NO_DB)
        self.assertNotIn(mo.REFLECT_BUTTON, self.page("sales"))  # the sample days carry no button
        self.assertEqual(self.starts, [])


class Lock(Base):
    def test_it_waits_for_the_scheduled_night(self):
        self.lose()
        other = scheduler.Scheduler(self.db, str(self.dir / "ascent.db"), when=None, holder="whatsapp:1")
        self.assertTrue(other._lock(1e10))
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("stock_watch")
        self.assertEqual(str(e.exception), mo.REFLECT_LOCKED)
        self.assertEqual((self.starts, self.held_by()), ([], "whatsapp:1"))
        other._unlock()
        self.assertEqual(self.m.run_reflection("stock_watch"), mo.REFLECT_STARTED)

    def test_the_scheduled_night_waits_for_it_and_runs_after(self):
        from zoneinfo import ZoneInfo
        self.lose()
        self.m.run_reflection("stock_watch")
        self.assertTrue(self.held_by().startswith("page:stock_watch:"))
        ran = []
        sched = scheduler.Scheduler(self.db, str(self.dir / "ascent.db"), when=(3, ZoneInfo("Africa/Cairo")),
                                    run=lambda *a, **k: ran.append(a) or 0, find=lambda: [("sales", "x")])
        got = sched.once()
        self.assertTrue(got["locked"])
        self.assertEqual(ran, [])
        self.starts[0][0]()  # the reflection ends and lets the lock go
        self.assertIsNone(self.held_by())
        self.assertEqual(sched.once()["ran"], {"sales": scheduler.DONE})
        self.assertEqual(len(ran), 1)

    def test_a_second_agent_waits_too(self):
        self.lose()
        self.m.run_reflection("stock_watch")
        self.m.reflection_models = lambda: {"study": self.model, "open": self.model, "exam": self.model}
        with mock.patch.object(reflect_now, "lost_chats", return_value=1), self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("sales")
        self.assertEqual(str(e.exception), mo.REFLECT_LOCKED)
        self.starts[0][0]()


class Cap(Base):
    def calls_file(self):
        return run_mod.state_dir(self.dir / "ascent.db") / run_mod.CALLS_FILE

    def test_no_room_starts_nothing(self):
        self.lose()
        self.calls_file().write_text(json.dumps({"day": run_mod.today(), "calls": run_mod.DEFAULT_CAP}))
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection("stock_watch")
        self.assertEqual(str(e.exception), mo.REFLECT_CAP)
        with mock.patch.object(retry_mod, "has_room", return_value=False), self.assertRaises(mo.Refused):
            self.m.run_reflection("stock_watch")
        self.assertEqual((self.starts, self.held_by()), ([], None))

    def test_every_model_call_counts_on_the_days_cap(self):
        self.lose()
        self.calls_file().write_text(json.dumps({"day": run_mod.today(), "calls": 7}))
        self.m.run_reflection("stock_watch")
        self.starts[0][0]()
        self.assertIsNone(self.m.reflect_note("stock_watch"))
        self.assertGreater(self.model.calls, 0)
        saved = json.loads(self.calls_file().read_text())
        self.assertEqual(saved["calls"], 7 + self.model.calls)
        done = self.m.reflected("stock_watch")
        self.assertEqual(done["calls"], self.model.calls)

    def test_the_cap_reached_mid_run_stops_its_calls(self):
        self.lose()
        self.calls_file().write_text(json.dumps({"day": run_mod.today(), "calls": run_mod.DEFAULT_CAP - 1}))
        self.m.run_reflection("stock_watch")
        self.starts[0][0]()
        self.assertLessEqual(self.model.calls, 1)
        self.assertEqual(json.loads(self.calls_file().read_text())["calls"], run_mod.DEFAULT_CAP)


class Afterwards(Base):
    def test_the_page_says_what_it_did_from_the_saved_report(self):
        self.lose()
        self.m.run_reflection("stock_watch")
        self.starts[0][0]()
        done = self.m.reflected("stock_watch")
        self.assertTrue((self.dir / done["file"]).is_file())
        rep = json.loads((self.dir / done["file"]).read_text())
        self.assertEqual((rep["agent"], rep["by"]), ("stock_watch", "Run reflection"))
        self.assertEqual(done["lost"], 2)
        page = self.page()
        self.assertIn("Last reflection, ", page)
        self.assertIn("Reflection read 2 lost chats.", page)
        self.assertIn("No lesson this time.", page)
        self.assertIn(f'action="{pages.REFLECT_PATH}"', page)  # it can run again

    def test_a_lesson_it_wrote_shows_its_chip_and_its_exam(self):
        a = {"live": [{"id": 4, "text": "Say the stock first.", "state": mo.TRYING, "ends_at": 1.9e9,
                       "exam_result": "passed", "exam": "", "added_at": 1.8e9, "source": ""}],
             "waiting": [{"id": 5, "text": "Offer a swap.", "state": mo.WAITING, "card": True, "exam_result": "failed",
                          "exam": "failed the exam: situation 2, check no_promise", "added_at": 1.8e9, "source": ""}],
             "pulled": [], "night": None}
        html = pages.reflect_result(a, {"at": 1.8e9, "lost": 3, "candidates": 2, "cards": [4, 5], "notes": []})
        self.assertIn("Say the stock first.</b><span class=\"vchip trial\">On trial</span>", html)
        self.assertIn("It passed the full exam.", html)
        self.assertIn('Offer a swap.</b><span class="vchip ">Waiting</span><small>Waits for your yes on Today</small>',
                      html)
        self.assertIn("It did not pass the exam, so it waits for your yes. Failed the exam: situation 2, check "
                      "no_promise.", html)
        none = pages.reflect_result(a, {"at": 1.8e9, "lost": 3, "candidates": 0, "cards": [], "notes": []})
        self.assertIn("No lesson this time. It found no lesson in 3 lost chats.", none)

    def test_a_run_that_fails_says_why_and_lets_the_lock_go(self):
        self.lose()
        self.m.reflection_models = lambda: (_ for _ in ()).throw(RuntimeError("the study route is down"))
        self.m.run_reflection("stock_watch")
        self.starts[0][0]()
        self.assertIn("The last reflection could not finish (the study route is down).", self.page())
        self.assertIsNone(self.held_by())
        self.assertIsNone(self.m.reflecting("stock_watch"))


def dead_pid():
    """The pid of a process that ran and ended (reaped), so os.kill(pid, 0) raises ProcessLookupError."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def page_holder(agent, pid, host=None):
    return f"{reflect_now.PAGE_HOLDER}:{agent}:{host or socket.gethostname()}:{pid}:abcd1234"


class Started(Base):
    def test_a_start_that_raises_lets_the_lock_go(self):
        self.lose()

        def refuse(work, name):
            raise RuntimeError("no thread")
        self.m.reflect_start = refuse
        with self.assertRaises(RuntimeError):
            self.m.run_reflection("stock_watch")
        self.assertIsNone(self.held_by())
        self.assertIsNone(self.m.reflecting("stock_watch"))
        self.m.reflect_start = lambda work, name: self.starts.append((work, name))
        self.assertEqual(self.m.run_reflection("stock_watch"), mo.REFLECT_STARTED)  # nothing was left behind
        self.starts[0][0]()


class TakeOver(Base):
    """Review reflectbtn r1, item 3: a page stopped mid run (Ctrl+C) leaves its holder; the next press takes
    the lock over once that holder's process is gone, never while it runs or when it is not the page's."""

    def hold(self, holder):
        self.assertTrue(scheduler.Scheduler(self.db, str(self.dir / "ascent.db"), when=None, holder=holder)
                        ._lock(__import__("time").time()))

    def test_the_holder_names_this_machine_and_this_process(self):
        self.lose()
        self.m.run_reflection("stock_watch")
        kind, agent, host, pid, token = self.held_by().split(":")
        self.assertEqual((kind, agent, host, pid), ("page", "stock_watch", socket.gethostname(), str(os.getpid())))
        self.assertEqual(len(token), 8)
        self.starts[0][0]()

    def test_a_holder_whose_process_is_gone_is_taken_over(self):
        self.lose()
        self.hold(page_holder("sales", dead_pid()))
        self.assertEqual(self.m.run_reflection("stock_watch"), mo.REFLECT_STARTED)
        self.assertTrue(self.held_by().startswith(f"page:stock_watch:{socket.gethostname()}:{os.getpid()}:"))
        self.starts[0][0]()
        self.assertIsNone(self.held_by())

    def test_a_live_or_other_holder_still_waits(self):
        self.lose()
        gone = dead_pid()
        for held in (page_holder("sales", os.getpid()), page_holder("sales", os.getppid()),
                     page_holder("sales", gone, host="another-machine"), f"page:sales:{gone}",
                     f"{socket.gethostname()}:{gone}:abcd1234", "whatsapp:1", page_holder("sales", 0)):
            with self.subTest(held=held):
                self.hold(held)
                with self.assertRaises(mo.Refused) as e:
                    self.m.run_reflection("stock_watch")
                self.assertEqual(str(e.exception), mo.REFLECT_LOCKED)
                self.assertEqual((self.starts, self.held_by()), ([], held))
                with self.db.tx() as c:
                    c.execute("DELETE FROM night_lock")

    def test_gone_and_ours(self):
        gone = dead_pid()
        self.assertTrue(reflect_now.gone(page_holder("a", gone)))
        self.assertTrue(reflect_now.gone(reflect_now.holder("a").replace(f":{os.getpid()}:", f":{gone}:")))
        for held in (page_holder("a", os.getpid()), page_holder("a", gone, "elsewhere"), page_holder("a", "x1"),
                     page_holder("a", "١٢"), page_holder("a", 10 ** 30), None, "", "page:a:b"):
            with self.subTest(held=held):
                self.assertFalse(reflect_now.gone(held))
        self.assertTrue(reflect_now.ours(reflect_now.holder("a")))
        self.assertFalse(reflect_now.ours(page_holder("a", gone)))
        self.assertFalse(reflect_now.ours(f"{socket.gethostname()}:{os.getpid()}:abcd1234"))  # a night's, not a page's


class ArenaWaits(Base):
    """Review reflectbtn r1, item 4: Run the Arena does not start while a night holds the night lock."""

    def setUp(self):
        super().setUp()
        self.m.arena_models = lambda: (tap.raises, tap.raises, tap.raises)
        self.arena_starts = []
        self.m.arena_start = lambda work, name: self.arena_starts.append(name)

    def hold(self, holder, at=None):
        import time
        self.assertTrue(scheduler.Scheduler(self.db, str(self.dir / "ascent.db"), when=None, holder=holder)
                        ._lock(time.time() if at is None else at))

    def test_a_night_holding_the_lock_stops_it(self):
        for held in ("whatsapp:1", f"{socket.gethostname()}:{os.getpid() + 1}:abcd1234",
                     page_holder("sales", os.getppid())):
            with self.subTest(held=held):
                self.hold(held)
                with self.assertRaises(mo.Refused) as e:
                    self.m.run_arena("stock_watch")
                self.assertEqual(str(e.exception), mo.ARENA_LOCKED)
                self.assertEqual(self.arena_starts, [])
                self.assertNotIn("stock_watch", self.m._arenas)
                with self.db.tx() as c:
                    c.execute("DELETE FROM night_lock")
        self.assertEqual(self.m.run_arena("stock_watch"), mo.ARENA_STARTED)  # free: it starts

    def test_this_pages_own_reflection_a_gone_page_or_a_stale_lock_does_not(self):
        import time
        for held, at in ((page_holder("sales", os.getpid()), None), (page_holder("sales", dead_pid()), None),
                         ("whatsapp:1", time.time() - scheduler.STALE - 1)):
            with self.subTest(held=held):
                self.hold(held, at)
                self.assertEqual(self.m.run_arena("stock_watch"), mo.ARENA_STARTED)
                self.m._arenas.discard("stock_watch")
                with self.db.tx() as c:
                    c.execute("DELETE FROM night_lock")
        self.assertEqual(len(self.arena_starts), 3)

    def test_with_no_lock_table_yet_it_starts(self):
        self.assertEqual(self.m.run_arena("stock_watch"), mo.ARENA_STARTED)
        self.assertEqual(self.arena_starts, ["arena-stock_watch"])


class HandNight(NightSetup):
    """Review reflectbtn r1, item 4: python3 -m reflection.night run by hand takes the night lock, so it never
    runs beside the scheduled night or a Run reflection, and lets it go when it ends, however it ends. A night
    the scheduler started runs under its parent's lock."""

    def setUp(self):
        super().setUp()
        self.env()

    def holder(self):
        db = Db(str(self.db_path))
        try:
            return scheduler.live_holder(db, __import__("time").time())
        finally:
            db.close()

    def hold(self, holder):
        db = Db(str(self.db_path))
        try:
            self.assertTrue(scheduler.Scheduler(db, str(self.db_path), when=None, holder=holder)
                            ._lock(__import__("time").time()))
        finally:
            db.close()

    def watching(self, seen):
        real = night.night

        def study(*a, **k):
            seen.append(self.holder())
            return real(*a, **k)
        return mock.patch.object(night, "night", study)

    def test_it_holds_the_lock_while_it_runs_and_lets_it_go(self):
        seen = []
        with self.watching(seen):
            code, out, err = self.run_main()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith(f"{socket.gethostname()}:{os.getpid()}:"), seen)
        self.assertIsNone(self.holder())

    def test_a_held_lock_stops_it_before_the_study(self):
        for held in ("whatsapp:1", page_holder("stock_watch", os.getpid())):
            with self.subTest(held=held):
                self.hold(held)
                seen = []
                with self.watching(seen):
                    code, out, err = self.run_main()
                self.assertEqual(code, 2)
                self.assertIn(f"Not run: {night.NIGHT_LOCKED}.", err)
                self.assertEqual((seen, out, self.net.seen), ([], "", []))
                self.assertEqual(list(self.dir.glob("night-*.json")), [])
                self.assertEqual(self.holder(), held)
                db = Db(str(self.db_path))
                with db.tx() as c:
                    c.execute("DELETE FROM night_lock")
                db.close()

    def test_a_night_the_scheduler_started_runs_under_its_lock(self):
        parent = f"{socket.gethostname()}:{os.getppid()}:abcd1234"
        self.hold(parent)
        seen = []
        with self.watching(seen):
            code, out, err = self.run_main()
        self.assertEqual(code, 0, err)
        self.assertEqual((seen, self.holder()), ([parent], parent))  # the scheduler's to let go

    def test_a_night_that_raises_lets_the_lock_go(self):
        with mock.patch.object(night, "night", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_main()
        self.assertIsNone(self.holder())


IDEA_LINE = "Say whether the item is in stock in the first reply."
POOL_LINE = "When a customer asks about stock, say whether the item is there first."
KEPT_LINE = "Name the item back to the customer before the stock answer."


def _head(prompt):
    return prompt.split("{")[0]


class Teacher(tap.World):
    """tap.World for the exam, its judge and the rerun's customer and agent, and for the study: the idea part
    writes one lesson, the risk judge says low, the shared pool writer gives a pattern line and the other study
    parts find nothing. calls: the World's sides; study: the study parts'."""

    def __init__(self):
        super().__init__()
        self.study = {"idea": 0, "risk": 0, "writer": 0, "other": 0}

    @property
    def total(self):
        return sum(self.calls.values()) + sum(self.study.values())

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        if system.startswith(_head(parts.IDEA)):
            self.study["idea"] += 1
            return say(json.dumps([{"lesson": IDEA_LINE, "situation": "Any stock question.", "stages": ["all"]}]))
        if system.startswith(_head(judge_mod.SYSTEM)):
            self.study["risk"] += 1
            return say("low")
        if system.startswith(_head(shared_mod.PROMPT)):
            self.study["writer"] += 1
            return say(json.dumps({"pattern": POOL_LINE}))
        if system.startswith(tuple(_head(p) for p in (parts.PROPOSE, parts.TAG, parts.FIT, parts.ADAPT, parts.SPOT,
                                                       parts.NOTE))):
            self.study["other"] += 1
            return say("[]")
        return super().chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)


class OneCount(Base):
    """Review reflectbtn r1, items 5 and 6: a run that writes a lesson takes the full exam, and every call of
    it lands once in the day's count: the exam's, its judge's, the Arena rerun's, the risk judge's and the
    shared pool writer's."""

    def setUp(self):
        super().setUp()
        tte.with_exam(self.folder)
        raw = json.loads((self.folder / "plug.json").read_text())
        raw["owner"] = "mona"  # the owner's folder above the agent names it, so the agent gives to the pool
        (self.folder / "plug.json").write_text(json.dumps(raw))
        (self.dir / "agents" / "owner.json").write_text(json.dumps({"owner": "mona"}))
        self.m.plugs["stock_watch"] = turn.load(self.folder).plug
        self.teacher = Teacher()
        self.m.reflection_models = lambda: {"study": self.teacher, "open": self.teacher, "exam": self.teacher}

    def calls_file(self):
        return run_mod.state_dir(self.dir / "ascent.db") / run_mod.CALLS_FILE

    def lose(self, n=2):
        """As Base.lose, the won matches with the practice prompt's fingerprint and a persona card, as practice
        saves them, so the gate reruns them."""
        from arena import practice
        super().lose(n)
        path = self.folder / "arena-matches.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        path.write_text("".join(json.dumps(dict(r, prompt_sha=practice.PROMPT_SHA, persona=tap.PEOPLE[0]) if r["won"] else r) + "\n"
                                for r in rows))

    def test_a_written_lesson_takes_the_full_exam_and_every_call_counts_once(self):
        self.lose()
        kept_lesson(EngineLessons(self.db, self.m.plugs["stock_watch"]), KEPT_LINE, ["all"], yes_by="test",
                    skip_exam=True)
        self.calls_file().write_text(json.dumps({"day": run_mod.today(), "calls": 7}))
        self.m.run_reflection("stock_watch")
        self.starts[0][0]()
        self.assertIsNone(self.m.reflect_note("stock_watch"))
        done = self.m.reflected("stock_watch")
        rep = json.loads((self.dir / done["file"]).read_text())
        self.assertEqual(len(done["cards"]), 1, rep["notes"])
        self.assertEqual(rep["cards"][0]["change"], IDEA_LINE)
        self.assertGreaterEqual(rep["exam"]["runs"], 1)
        t = self.teacher
        self.assertEqual(t.study["idea"], 1)
        self.assertGreaterEqual(t.study["risk"], 1)    # the risk judge
        self.assertGreaterEqual(t.study["writer"], 1)  # the shared pool writer, on the kept lesson
        self.assertGreater(t.calls["agent"], 0)        # the exam's
        self.assertGreater(t.calls["judge"], 0)        # the exam's judge and the rerun's
        exam = EngineLessons(self.db, self.m.plugs["stock_watch"]).exam_of(done["cards"][0])
        self.assertEqual(json.loads(exam["parts"]).get("arena"), [2, 2])  # the rerun of its two past wins
        self.assertEqual(json.loads(self.calls_file().read_text())["calls"], 7 + t.total)
        self.assertEqual(done["calls"], t.total)

    def test_the_built_agents_rerun_counts_once_on_the_runs_calls(self):
        self.lose()
        calls = run_mod.Calls(self.calls_file(), run_mod.DEFAULT_CAP)
        make = night.agent_exam(self.m.plugs["stock_watch"], str(self.dir / "ascent.db"), folder=self.folder,
                                model=self.teacher, calls=calls)
        result = make(EngineLessons(self.db, self.m.plugs["stock_watch"]))(IDEA_LINE, ("all",))
        self.assertTrue(result.passed, result.rows)
        self.assertEqual(result.parts().get("arena"), [2, 2])  # the rerun played its two past wins
        self.assertEqual(calls.taken, self.teacher.total)
        self.assertEqual(json.loads(self.calls_file().read_text())["calls"], self.teacher.total)


class Shopper:
    """The Sales side of one fake: the reveal judge answers no, the rerun's customer is a Buyer, every other
    call is the Seller (the exam's agent and the rerun's)."""

    def __init__(self):
        self.seller, self.buyer, self.reveal = Seller(), Buyer(), 0

    @property
    def total(self):
        return len(self.seller.calls) + len(self.buyer.calls) + self.reveal

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        if system == scope.REVEAL_JUDGE:
            self.reveal += 1
            return say(json.dumps({"gives": False, "why": "a decline"}))
        side = self.buyer if system.startswith("You are a customer") else self.seller
        return side.chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)


class SalesCount(Base):
    """Review reflectbtn r1, items 5 and 6, for the Sales agent: its full exam's reveal judge and its Arena
    rerun take each call from the run's count."""

    def test_the_full_exam_and_its_reveal_judge_count(self):
        calls = run_mod.Calls(run_mod.state_dir(self.dir / "ascent.db") / run_mod.CALLS_FILE, run_mod.DEFAULT_CAP)
        fake = Shopper()
        make = night.agent_exam(SALES, str(self.dir / "ascent.db"), model=fake, calls=calls)
        result = make(SalesLessons(self.db))(tag.LESSON, ("all",))
        self.assertGreater(result.calls, 0)
        self.assertGreater(fake.reveal, 0)
        self.assertEqual(calls.taken, fake.total)
        self.assertEqual(json.loads(calls.path.read_text())["calls"], fake.total)

    def test_the_rerun_lands_in_the_runs_count(self):
        (run_mod.state_dir(self.dir / "ascent.db") / run_mod.MATCHES_FILE).write_text(json.dumps(tag.past()) + "\n")
        calls = run_mod.Calls(run_mod.state_dir(self.dir / "ascent.db") / run_mod.CALLS_FILE, run_mod.DEFAULT_CAP)
        fake = Shopper()
        made = []

        def passes(plug, *, kept=None, model=None, count=False, judge_model=None):
            made.append((model, judge_model))
            return lambda text, tags: engine_exam.Result(passed=True, rows=[engine_exam.Row(1, "s1", "guard", True, "")],
                                                         calls=0)
        with mock.patch.object(exam_mod, "Examiner", passes):
            result = night.agent_exam(SALES, str(self.dir / "ascent.db"), model=fake, calls=calls)(None)(
                tag.LESSON, ("all",))
        self.assertEqual([r.part for r in result.rows], ["guard", "arena"])  # the exam passed, so the rerun ran
        self.assertGreater(len(fake.buyer.calls), 0)  # on the run's model
        self.assertEqual(calls.taken, fake.total)
        model, judge = made[0]
        for m in (model, judge):
            before = calls.taken
            m.chat([{"role": "system", "content": "x"}, {"role": "user", "content": "y"}])
            self.assertEqual(calls.taken, before + 1)  # the exam's and the reveal judge's model, counted


class Script(unittest.TestCase):
    def test_the_one_poll_follows_both_runs(self):
        self.assertIn("[data-live][data-running]", pages.ARENA_SCRIPT)
        self.assertIn("k==='reflect'", pages.ARENA_SCRIPT)  # a reflection that ends loads the page again
        self.assertIn(f"script-src 'sha256-{pages._sha(pages.ARENA_SCRIPT)}'", pages.AGENT_CSP)


if __name__ == "__main__":
    unittest.main()
