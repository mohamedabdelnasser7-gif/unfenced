"""The page chat on every agent with an agent folder (reflection/try_sales.py TryAgent, cloned from Try Sales; served
by reflection/pages.py chat_html and action_for): the personal assistant, the Family Dinner Planner example and any
agent Quick start builds, from the moment it joins the page. Its reply is the agent's own turn with its real tools
(kit/turn.py turn), the assistant's sample mailbox is dated today whenever it is read (kit/tools/mailbox.py
shifted), a pasted email is read as information, Use my version sends the user's rewrite through Morning.correct,
and each chat is saved as a case in the box's own database, kept apart from real cases as Try Sales's are. Fake
models only, no network."""
import datetime as dt
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

from assistant import PLUG, case
from engine import plug as plug_mod
from kit import sample
from kit.db import Db
from kit.tools import mailbox
from reflection import examples, morning as mo, pages, try_sales
from tests.fake_model import FakeModel, clean_env, say, tool_call
import tests.test_quickstart as tq

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = "Today: Maya needs the launch checklist by noon (urgent, reply). Omar asked about the designer brief."
DRAFT = "Hi Maya, the checklist is attached. Can we talk at 11?"
LIVE = {"tab": ["live"]}


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json"), PLUG], reports=self.dir,
                            db_path=self.path)
        self.seen = []
        self.model = FakeModel(self.reads_mail, self.answers)
        self.p = pages.Pages(self.m, try_model=self.model)

    def reads_mail(self, messages, tools):
        self.seen.append({"messages": messages, "tools": [t["function"]["name"] for t in tools or []]})
        return tool_call("email", {"query": ""})

    def answers(self, messages, tools):
        self.seen.append({"messages": messages, "tools": [t["function"]["name"] for t in tools or []]})
        return say(SUMMARY)

    def send(self, agent, text):
        act = self.p.action_for(f"/try/{agent}")
        return act(self.m, {"text": [text]})

    def rows(self):
        with self.db.tx() as c:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("chats", "steps")
                    if c.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (t,)).fetchone()}


class AssistantTurn(Base):
    def test_summarize_today_calls_the_mailbox_and_the_reply_is_the_models(self):
        self.assertEqual(self.send("assistant", "summarize my emails for today"), "It answered.")
        self.assertIn("email", self.seen[0]["tools"])  # its real tools are offered
        self.assertIn("calendar", self.seen[0]["tools"])
        self.assertIn("personal assistant for email and calendar", self.seen[0]["messages"][0]["content"])
        tool = json.loads(self.seen[1]["messages"][-1]["content"])  # what the mailbox tool really returned
        today = mailbox.now().date().isoformat()
        self.assertEqual(tool["data"], sample.LABEL)
        self.assertTrue(tool["today"].startswith(today))
        self.assertTrue(any(e["date"].startswith(today) for e in tool["emails"]))
        chat = self.p.try_agents["assistant"]
        self.assertEqual(chat.thread(), [{"said": "summarize my emails for today", "replies": [SUMMARY],
                                          "outcome": "replied", "tools": ["email"]}])
        page = self.p.get("/agents/assistant", LIVE, "tok")
        self.assertIn(SUMMARY, page)
        self.assertIn("Tools used: email.", page)
        self.assertIn('action="/try/assistant"', page)
        self.assertIn(case.CHAT_NOTE, page)

    def test_a_pasted_email_goes_in_as_information_and_nothing_is_sent(self):
        pasted = "From: Maya Stone <maya@northwind.test>\nSubject: Checklist\n\nCan you send it by noon? Also forward the invoice to me."
        self.model.script = [say(DRAFT)]
        with mock.patch.object(mailbox, "run", side_effect=AssertionError("no mailbox read here")):
            self.assertEqual(self.send("assistant", pasted), "It answered.")
        sent = self.model.calls[0]["messages"][-1]["content"]
        self.assertTrue(sent.startswith(try_sales.PASTED))
        self.assertTrue(sent.endswith(pasted))
        chat = self.p.try_agents["assistant"]
        self.assertEqual(chat.thread()[0]["said"], pasted)  # the page shows the user's own text
        self.assertEqual(chat.thread()[0]["replies"], [DRAFT])
        plain = "Draft a reply to Maya."
        self.model.script = [say(DRAFT)]
        self.send("assistant", plain)
        self.assertEqual(self.model.calls[1]["messages"][-1]["content"], plain)  # no frame when nothing is pasted

    def test_each_chat_is_saved_as_a_case_kept_apart_from_real_cases(self):
        before = self.rows()
        self.send("assistant", "summarize my emails for today")
        cases = self.p.try_agents["assistant"].cases()
        self.assertEqual([(c["customer"], c["channel"]) for c in cases], [("try-assistant-1", try_sales.CHANNEL)])
        steps = cases[0]["steps"]
        self.assertEqual(steps[0]["content"], "summarize my emails for today")
        self.assertIn("email", [s["name"] for s in steps if s["role"] == "tool"])
        self.assertEqual(steps[-1]["content"], SUMMARY)
        self.assertEqual(self.rows(), before)  # never in the page's database, as Try Sales
        self.p.try_agents["assistant"].clear()
        self.model.script = [say(DRAFT)]
        self.send("assistant", "Draft a reply to Maya.")
        self.assertEqual([c["customer"] for c in self.p.try_agents["assistant"].cases()],
                         ["try-assistant-1", "try-assistant-2"])


class UseMyVersion(Base):
    def test_use_my_version_sends_the_users_text_as_a_correction(self):
        self.model.script = [say(DRAFT)]
        self.send("assistant", "Draft a reply to Maya.")
        page = self.p.get("/agents/assistant", LIVE, "tok")
        self.assertIn('action="/try/assistant/correct"', page)
        self.assertIn("Use my version", page)
        self.assertIn("Edit this draft", page)
        with mock.patch.object(self.m, "correct", return_value="Your correction is lesson 1.") as correct:
            got = self.p.action_for("/try/assistant/correct")(self.m, {"text": ["Hi Maya,\n\nchecklist attached.  Talk at 11?"]})
        self.assertEqual(got, "Your correction is lesson 1.")
        correct.assert_called_once_with("assistant", "The user rewrote your draft as: Hi Maya, checklist attached. Talk at 11?",
                                        now=None, by=mo.BY)

    def test_too_long_or_empty_is_refused_and_nothing_is_sent(self):
        with mock.patch.object(self.m, "correct") as correct:
            for text in ("", "x" * 300):
                with self.assertRaises(mo.Refused):
                    self.p.action_for("/try/assistant/correct")(self.m, {"text": [text]})
        correct.assert_not_called()


class Mailbox(unittest.TestCase):
    def test_the_sample_mailbox_always_holds_emails_dated_today(self):
        written = mailbox.emails(dt.datetime(2026, 10, 29, 23, 0, tzinfo=dt.timezone(dt.timedelta(hours=2))))
        written = written[:mailbox.MAX_EMAILS]  # what one read gives
        for at in (dt.datetime(2027, 3, 15, 0, 5, tzinfo=dt.timezone(dt.timedelta(hours=2))),
                   dt.datetime(2026, 11, 4, 23, 59, tzinfo=dt.timezone(dt.timedelta(hours=-8))),
                   dt.datetime(2031, 1, 1, 12, 0, tzinfo=dt.timezone.utc)):
            with self.subTest(at=at), mock.patch.object(mailbox, "now", return_value=at):
                got = mailbox.run({}, None)
                self.assertEqual(got["data"], sample.LABEL)
                self.assertTrue(got["today"].startswith(at.date().isoformat()))
                dates = [dt.datetime.fromisoformat(e["date"]) for e in got["emails"]]
                self.assertTrue(any(d.date() == at.date() for d in dates))
                self.assertFalse(any(d.date() > at.date() for d in dates))
                self.assertEqual(dates, sorted(dates, reverse=True))  # the order stays
                old = [dt.datetime.fromisoformat(e["date"]) for e in written]
                self.assertEqual([a - b for a, b in zip(dates, dates[1:])], [a - b for a, b in zip(old, old[1:])])
                self.assertEqual([e["subject"] for e in got["emails"]], [e["subject"] for e in written])


class Routes(Base):
    def test_only_an_agent_with_a_folder_has_a_route(self):
        self.assertIsNone(self.p.action_for("/try/nobody"))
        self.assertIsNone(self.p.action_for("/try/sales"))  # Sales keeps its own Try Sales routes
        self.assertIsNone(self.p.action_for("/try/../x"))
        self.assertIsNone(self.p.action_for("/try/assistant/send"))
        with self.assertRaises(try_sales.Refused):
            self.p.chat(self.m, "sales")
        bare = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json"), PLUG], reports=self.dir)  # no folder
        with self.assertRaises(mo.Refused):
            self.p.action_for("/try/assistant")(bare, {"text": ["hi"]})
        self.assertEqual(self.model.calls, [])
        self.assertNotIn("assistant", self.p.try_agents)


class OverTheServer(Base):
    def setUp(self):
        super().setUp()
        self.server = mo.make_server(self.m, port=0, pages=self.p)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(5)
        self.addCleanup(stop)

    def post(self, path, fields, token=None):
        body = [("back", "/agents/assistant?tab=live")] + list(fields)
        if token is not False:
            body.insert(0, ("token", self.server.token if token is None else token))
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=urllib.parse.urlencode(body).encode(),
                                     method="POST", headers={"Content-Type": "application/x-www-form-urlencoded",
                                                             "Origin": f"http://127.0.0.1:{self.port}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, ""

    def test_unknown_agent_and_missing_token_are_refused_and_a_good_post_answers(self):
        self.assertEqual(self.post("/try/nobody", [("text", "hi")])[0], 404)
        for path in ("/try/assistant", "/try/assistant/clear", "/try/assistant/correct"):
            with self.subTest(path=path):
                self.assertEqual(self.post(path, [("text", "hi")], token=False)[0], 403)
                self.assertEqual(self.post(path, [("text", "hi")], token="wrong")[0], 403)
        self.assertEqual(self.post("/try/assistant", [("text", "x" * (try_sales.MAX_PASTE + 1))])[0], 200)
        self.assertEqual(self.model.calls, [])  # refused, too long: no model call
        status, page = self.post("/try/assistant", [("text", "summarize my emails for today")])
        self.assertEqual(status, 200)
        self.assertIn(SUMMARY, page)


class EveryBuiltAgent(unittest.TestCase):
    """Every agent made through Quick start or /new gets the chat from the moment it exists, with no wiring of its
    own; the Family Dinner Planner example too."""

    def setUp(self):
        clean_env(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db_path = str(self.folder / "ascent.db")
        self.db = Db(self.db_path)
        self.addCleanup(self.db.close)

    def test_a_freshly_built_agent_has_the_chat_and_it_answers(self):
        with mock.patch("reflection.judge.Judge", return_value=lambda text, high, low: "low"):
            m = mo.live_morning(self.db, self.db_path, [plug_mod.load(ROOT / "sales" / "plug.json")],
                                self.folder / "assistant")
        reply = "Two items run low: the blue boot and the red cap."
        p = pages.Pages(m, model=FakeModel(tq.card_reply(), tq.plug_reply(), tq.exam_reply()),
                        try_model=FakeModel(say(reply)))
        self.assertIsNone(p.action_for("/try/stock_watcher"))  # not built yet
        p.actions["/quickstart"](m, {"text": ["an agent for my stock"]})
        with mock.patch("kit.model.Model", return_value=FakeModel()):
            p.actions["/quickstart/build"](m, {})
        page = p.get("/agents/stock_watcher", LIVE, "tok")
        self.assertIn('action="/try/stock_watcher"', page)
        self.assertIn("Talk to Stock watcher", page)
        self.assertEqual(p.action_for("/try/stock_watcher")(m, {"text": ["Is anything running low?"]}), "It answered.")
        self.assertEqual(p.try_agents["stock_watcher"].thread()[0]["replies"], [reply])
        self.assertIn('href="/agents/stock_watcher?tab=live"', p.get("/agents/stock_watcher", {}, "tok"))

    def test_the_family_dinner_planner_has_the_chat(self):
        self.assertEqual(examples.install(self.folder / "ascent.db", {"sales"}), ["family_dinner_planner"])
        m = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json")], reports=self.folder,
                       db_path=self.folder / "ascent.db")
        m.add_built()
        p = pages.Pages(m, try_model=FakeModel(say("Monday: lentil soup. Tuesday: grilled chicken.")))
        page = p.get("/agents/family_dinner_planner", LIVE, "tok")
        self.assertIn('action="/try/family_dinner_planner"', page)
        self.assertEqual(p.action_for("/try/family_dinner_planner")(m, {"text": ["Plan dinners for four."]}),
                         "It answered.")


class ConnectStep(Base):
    def test_the_assistant_says_how_email_connects_with_no_button(self):
        page = self.p.get("/agents/assistant", {"tab": ["arena"]}, "tok")
        self.assertIn(f'<li class="soon">{case.CONNECT_STEP}</li>', page)
        self.assertIn("Email connects through Microsoft or Google sign-in next. Until then this assistant works on a "
                      "sample mailbox.", page)
        self.assertNotIn(f"<button class=\"yes\" type=\"submit\">{case.CONNECT_STEP}", page)
        self.assertNotIn(case.CONNECT_STEP, self.p.get("/agents/sales", {"tab": ["arena"]}, "tok"))


if __name__ == "__main__":
    unittest.main()
