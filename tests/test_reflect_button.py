"""Run reflection on an agent's page (DECISIONS 92 and 93; reflection/reflect_now.py, Morning.run_reflection,
pages.py REFLECT_PATH). Fake models only: no model call, no network."""
import http.client
import json
import shutil
import tempfile
import threading
import types
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from arena import learn_built, retry as retry_mod, run as run_mod
from engine import plug as plug_mod
from kit import turn
from kit.db import Db
from reflection import morning as mo, night, pages, reflect_now, scheduler
from tests.fake_model import clean_env
import tests.test_arena_practice as tap
import tests.test_quickstart as tq

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
    def test_beside_run_the_arena_with_the_owners_words_under_it(self):
        self.lose()
        for query in (ARENA_TAB, {}):
            with self.subTest(query=query):
                page = self.page(query=query)
                form = page.split(f'action="{pages.REFLECT_PATH}"')[1].split("</form>")[0]
                self.assertIn(f"{mo.REFLECT_BUTTON}</button>", form)
                self.assertIn('name="agent" value="stock_watch"', form)
                after = page.split(f'action="{pages.REFLECT_PATH}"')[1].split("</form>", 1)[1]
                self.assertTrue(after.startswith(f'<p class="quiet">{mo.REFLECT_SAID}</p>'))  # the line under it
                self.assertIn('data-live="reflect"', page)
        arena = self.page(query=ARENA_TAB)
        self.assertLess(arena.index(f'action="{pages.ARENA_PATH}"'), arena.index(f'action="{pages.REFLECT_PATH}"'))
        self.assertEqual(mo.REFLECT_BUTTON, "Run reflection")
        self.assertEqual(mo.REFLECT_SAID, "This is the learning step. The agent reads the chats it lost, writes one "
                         "lesson from them, and tests that lesson on a full exam before it can reach a real customer. "
                         "Uses your model key.")

    def test_the_sales_agent_has_it_too_from_its_own_plug(self):
        page = self.page("sales", ARENA_TAB)
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
        page = self.page(query=ARENA_TAB)
        self.assertEqual(mo.NO_LOST, "No lost chats yet. Run the Arena first so the agent has something to learn from.")
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
            page = self.page(query=ARENA_TAB)
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
        page = self.page(query=ARENA_TAB)
        self.assertIn('data-live="reflect" data-running', page)
        self.assertIn('Reflecting: <b aria-current="step">reading lost chats</b>, then writing a lesson, then the exam',
                      page)
        self.assertNotIn(f'action="{pages.REFLECT_PATH}"', page)
        steps = self.m._reflecting["stock_watch"]
        steps.mark(reflect_now.LESSON)
        self.assertIn('reading lost chats, then <b aria-current="step">writing a lesson</b>, then the exam',
                      self.page(query=ARENA_TAB))
        steps.mark(reflect_now.EXAM)
        steps.mark(reflect_now.READ)  # never back
        self.assertIn('then writing a lesson, then <b aria-current="step">the exam</b>', self.page())
        self.starts[0][0]()
        self.assertIsNone(self.m.reflecting("stock_watch"))
        self.assertNotIn("data-running", self.page(query=ARENA_TAB))

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
        self.assertIn("first short practice", str(e.exception))
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
        self.assertIn(mo.REFLECT_ARENA, self.page(query=ARENA_TAB))
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
                                    run=lambda *a: ran.append(a) or 0, find=lambda: [("sales", "x")])
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
        page = self.page(query=ARENA_TAB)
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
        self.assertIn("The last reflection could not finish (the study route is down).", self.page(query=ARENA_TAB))
        self.assertIsNone(self.held_by())
        self.assertIsNone(self.m.reflecting("stock_watch"))


class Script(unittest.TestCase):
    def test_the_one_poll_follows_both_runs(self):
        self.assertIn("[data-live][data-running]", pages.ARENA_SCRIPT)
        self.assertIn("k==='reflect'", pages.ARENA_SCRIPT)  # a reflection that ends loads the page again
        self.assertIn(f"script-src 'sha256-{pages._sha(pages.ARENA_SCRIPT)}'", pages.AGENT_CSP)


if __name__ == "__main__":
    unittest.main()
