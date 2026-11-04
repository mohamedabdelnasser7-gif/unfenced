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
from engine import exam as engine_exam
from engine import plug as plug_mod
from engine import risk
from engine.lessons import Lessons
from kit import sample
from kit.db import Db
from kit.tools import calendar_tool, mailbox
from reflection import examples, morning as mo, pages, try_sales
from tests.fake_model import FakeModel, clean_env, say, tool_call
import tests.test_quickstart as tq

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = "Today: Maya needs the launch checklist by noon (urgent, reply). Omar asked about the designer brief."
DRAFT = "Hi Maya, the checklist is attached. Can we talk at 11?"
LIVE = {"tab": ["live"]}
WAITING = {"Revised quote", "Intro call", "Budget numbers", "This week in design"}  # the newest day's mail with no reply
AT = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))  # the clock the chat tests read the mail at
TRICK = "</textarea><script>alert(1)</script>"


def waiting_today(got, day):
    """The subjects of the inbox emails in a mailbox answer dated day that no sent email answers (its Re: subject)."""
    replies = {e["subject"] for e in got["emails"] if e["box"] == "sent"}
    today = [e for e in got["emails"] if e["box"] == "inbox" and e["date"].startswith(day)]
    return {e["subject"] for e in today if "Re: " + e["subject"] not in replies}, today


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
        clock = mock.patch.object(mailbox, "now", return_value=AT)  # a fixed clock: early in the day, today has no mail
        clock.start()
        self.addCleanup(clock.stop)

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

    def test_summarize_today_gets_the_mail_still_waiting_for_a_reply_and_the_prompt_offers_drafts(self):
        self.send("assistant", "summarize my emails for today")
        tool = json.loads(self.seen[1]["messages"][-1]["content"])  # what the mailbox tool really returned
        waiting, today = waiting_today(tool, mailbox.now().date().isoformat())
        self.assertGreaterEqual(len(waiting), 3)
        self.assertEqual(waiting, WAITING)
        self.assertGreater(len(today), len(waiting))  # some of today's mail is answered already
        prompt = self.seen[0]["messages"][0]["content"]  # the installed instructions: point out and offer, as an intent
        self.assertIn("still wait for a reply", prompt)
        self.assertIn("offer to draft", prompt)
        cli = (ROOT / "assistant" / "instructions.md").read_text(encoding="utf-8")  # the command line assistant's too
        self.assertIn("still wait for a reply", cli)
        self.assertIn("offer to draft", cli)

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

    def test_the_cap_is_exactly_what_a_correction_holds(self):
        """Review r1 finding 7 (M6): the boundary, the most a correction holds passes and one more is refused."""
        self.assertEqual(pages.MINE_ROOM, mo.MAX_LEN - len(pages.MINE.format(text="")))
        act = self.p.action_for("/try/assistant/correct")
        with mock.patch.object(self.m, "correct", return_value="ok") as correct:
            self.assertEqual(act(self.m, {"text": ["x" * pages.MINE_ROOM]}), "ok")
            with self.assertRaises(mo.Refused) as e:
                act(self.m, {"text": ["x" * (pages.MINE_ROOM + 1)]})
        self.assertIn(f"at most {pages.MINE_ROOM}", str(e.exception))
        correct.assert_called_once()
        self.assertEqual(len(correct.call_args.args[1]), mo.MAX_LEN)

    def test_an_agent_with_no_folder_on_this_page_is_refused(self):
        """Review r1 finding 7 (M7): Use my version on a page whose assistant has no agent folder is refused."""
        bare = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json"), PLUG], reports=self.dir)  # no folder
        with mock.patch.object(bare, "correct") as correct, mock.patch.object(self.m, "correct") as other:
            with self.assertRaises(mo.Refused):
                self.p.action_for("/try/assistant/correct")(bare, {"text": ["Hi Maya, attached."]})
        correct.assert_not_called()
        other.assert_not_called()

    def test_the_agents_own_draft_unchanged_is_refused(self):
        """Review r1 finding 3: the model's draft sent back unchanged is not the user's version, so a pasted email
        cannot turn the model's own words into a lesson with one press."""
        self.model.script = [say(DRAFT)]
        self.send("assistant", "Draft a reply to Maya.")
        act = self.p.action_for("/try/assistant/correct")
        with mock.patch.object(self.m, "correct", return_value="ok") as correct:
            for same in (DRAFT, f"  {DRAFT}\n", DRAFT.replace(" ", "\n  ", 2)):
                with self.subTest(same=same), self.assertRaises(mo.Refused) as e:
                    act(self.m, {"text": [same]})
                self.assertEqual(str(e.exception), pages.MINE_SAME)
            correct.assert_not_called()
            self.assertEqual(act(self.m, {"text": [DRAFT.replace("11", "12")]}), "ok")
        correct.assert_called_once()

    def test_edit_this_draft_shows_the_limit_and_prefills_only_what_fits(self):
        """Review r1 finding 2: the box holds at most what a correction holds, says so, and a longer draft leaves it
        empty with a hint instead of a text the server would refuse."""
        long = "Hi Leo, " + "thanks for the note on the revised quote, I will send it by noon tomorrow. " * 5
        self.assertGreater(len(long), pages.MINE_ROOM)
        self.model.script = [say(DRAFT), say(long)]
        self.send("assistant", "Draft a reply to Maya.")
        self.send("assistant", "Draft a reply to Leo.")
        page = self.p.get("/agents/assistant", LIVE, "tok")
        self.assertIn(f"at most {pages.MINE_ROOM} characters", page)
        self.assertEqual(page.count(f'maxlength="{pages.MINE_ROOM}"'), 2)
        self.assertIn(f'required>{mo.h(DRAFT)}</textarea>', page)  # a short draft is there to edit
        self.assertIn(f'required placeholder="{mo.h(pages.MINE_HINT)}"></textarea>', page)  # a long one: empty, a hint
        self.assertNotIn(f">{mo.h(' '.join(long.split()))}</textarea>", page)

    def test_a_reply_is_escaped_in_the_thread_and_in_the_box(self):
        """Review r1 finding 7 (M10 and M12): a reply holding markup shows as text, in the thread and in the draft box."""
        self.model.script = [say(TRICK)]
        self.send("assistant", "Draft a reply to Maya.")
        page = self.p.get("/agents/assistant", LIVE, "tok")
        self.assertNotIn("<script>alert", page)
        self.assertNotIn(TRICK, page)
        self.assertIn(f'<p class="said ag" dir="auto">{mo.h(TRICK)}</p>', page)
        self.assertIn(f'required>{mo.h(TRICK)}</textarea>', page)


def low(text, high_about, low_about):
    return risk.LOW


class Handed(Base):
    def test_a_passed_correction_reaches_the_chats_next_turn(self):
        """Review r1 finding 7 (M19): a correction that passed its exam and runs on the live database is handed to
        the chat's next turn, as the Arena hands it."""
        fix = "Always offer two times for a call."
        d = Db(str(self.path))
        try:
            Lessons(d, PLUG, judge=low).correct(fix, ["all"], yes_by=mo.BY,
                                                exam=engine_exam.Result(True, [engine_exam.Row(1, "s1", "guard", True)],
                                                                        calls=1))
        finally:
            d.close()
        self.model.script = [say(DRAFT)]
        self.send("assistant", "Draft a reply to Hana.")
        self.assertIn(fix, json.dumps(self.model.calls[0]["messages"]))


class Mailbox(unittest.TestCase):
    def test_the_sample_mailbox_always_holds_emails_dated_today(self):
        written = mailbox.emails(dt.datetime(2026, 10, 29, 23, 0, tzinfo=dt.timezone(dt.timedelta(hours=2))))
        written = written[:mailbox.MAX_EMAILS]  # what one read gives
        for at in (dt.datetime(2027, 3, 15, 8, 35, tzinfo=dt.timezone(dt.timedelta(hours=2))),
                   dt.datetime(2026, 11, 4, 23, 59, tzinfo=dt.timezone(dt.timedelta(hours=-8))),
                   dt.datetime(2031, 1, 1, 12, 0, tzinfo=dt.timezone.utc)):
            with self.subTest(at=at), mock.patch.object(mailbox, "now", return_value=at):
                got = mailbox.run({}, None)
                self.assertEqual(got["data"], sample.LABEL)
                self.assertTrue(got["today"].startswith(at.date().isoformat()))
                dates = [dt.datetime.fromisoformat(e["date"]) for e in got["emails"]]
                self.assertTrue(any(d.date() == at.date() for d in dates))
                self.assertFalse(any(d > at for d in dates))  # never after now
                self.assertEqual(dates, sorted(dates, reverse=True))  # the order stays
                old = [dt.datetime.fromisoformat(e["date"]) for e in written]
                self.assertEqual([a - b for a, b in zip(dates, dates[1:])], [a - b for a, b in zip(old, old[1:])])
                self.assertEqual([e["subject"] for e in got["emails"]], [e["subject"] for e in written])


    def test_the_newest_day_holds_mail_with_no_reply_yet(self):
        for at in (dt.datetime(2026, 11, 4, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=2))),
                   dt.datetime(2026, 11, 4, 23, 59, tzinfo=dt.timezone(dt.timedelta(hours=-8))),
                   dt.datetime(2031, 1, 1, 12, 0, tzinfo=dt.timezone.utc)):
            with self.subTest(at=at), mock.patch.object(mailbox, "now", return_value=at):
                waiting, today = waiting_today(mailbox.run({}, None), at.date().isoformat())
                self.assertGreaterEqual(len(waiting), 3)
                self.assertEqual(waiting, WAITING)
                self.assertGreater(len(today), len(waiting))  # a mix: some answered, some not

    def test_the_newest_email_lands_just_before_now_never_after(self):
        """Review r1 finding 4: at 09:00 no email is dated later the same day; the newest lands GAP before now."""
        at = dt.datetime(2026, 11, 4, 9, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
        with mock.patch.object(mailbox, "now", return_value=at):
            dates = [dt.datetime.fromisoformat(e["date"]) for e in mailbox.run({}, None)["emails"]]
        self.assertEqual(max(dates), dt.datetime(2026, 11, 4, 8, 50, tzinfo=at.tzinfo))
        self.assertTrue(all(d < at for d in dates))
        self.assertEqual(mailbox.GAP, dt.timedelta(minutes=10))

    def test_a_zone_past_midnight_reads_in_its_own_time(self):
        """Review r1 finding 7 (M13): at +14:00 the sample's own times (+02:00) fall on the next day; every date is
        written in the user's zone, the newest just before now and today's waiting mail on the user's today."""
        for hours in (14, 10, -12):
            at = dt.datetime(2026, 11, 4, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=hours)))
            with self.subTest(hours=hours), mock.patch.object(mailbox, "now", return_value=at):
                got = mailbox.run({}, None)
                zone = at.strftime("%z")
                self.assertTrue(all(e["date"].endswith(f"{zone[:3]}:{zone[3:]}") for e in got["emails"]))
                self.assertEqual(got["emails"][0]["date"], "2026-11-04T19:50:00" + f"{zone[:3]}:{zone[3:]}")
                self.assertEqual(waiting_today(got, "2026-11-04")[0], WAITING)

    def test_an_empty_mailbox_or_one_with_no_dates_stays_as_it_is(self):
        """Review r1 finding 7 (M14): nothing to move is no crash and no change."""
        self.assertEqual(mailbox.shifted([]), [])
        self.assertEqual(mailbox.shifted([None]), [None])
        self.assertEqual(mailbox.shifted([None, None], AT), [None, None])


class Calendar(unittest.TestCase):
    def test_the_calendar_day_is_the_mailboxs_today(self):
        """Review r1 finding 1: the calendar moves onto the same today as the mailbox, so today's meetings and a
        booking for tomorrow read the day the mail is on."""
        for at in (AT, dt.datetime(2026, 11, 4, 23, 59, tzinfo=dt.timezone(dt.timedelta(hours=-8))),
                   dt.datetime(2027, 3, 15, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=14))),
                   dt.datetime(2031, 1, 1, 12, 0, tzinfo=dt.timezone.utc)):
            with self.subTest(at=at), mock.patch.object(mailbox, "now", return_value=at):
                mail, cal = mailbox.run({}, None), calendar_tool.run({}, None)
                today = at.date().isoformat()
                self.assertEqual(cal["date"], today)
                self.assertEqual(mail["today"], cal["today"])
                self.assertTrue(mail["today"].startswith(cal["date"]))
                self.assertEqual([m["title"] for m in cal["meetings"]], ["Team sync", "Focus time", "Client call"])
                self.assertTrue(all(m["date"] == today for m in cal["meetings"]))
                tomorrow = (at.date() + dt.timedelta(days=1)).isoformat()
                self.assertEqual(calendar_tool.run({"date": tomorrow}, None)["meetings"], [])
                clash = calendar_tool.run({"title": "Hana", "start": "16:30", "end": "17:00"}, None)
                self.assertIn("clashes with Client call", clash["feedback"])
                self.assertEqual(clash["date"], today)
        written = json.loads(calendar_tool.DEMO.read_text(encoding="utf-8"))["events"]
        self.assertEqual({e["date"] for e in written}, {"2026-11-02"})  # the demo file is never written


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
        status, page = self.post("/try/assistant", [("text", chr(0x201C) * (try_sales.MAX_PASTE + 1))])
        self.assertEqual(status, 200)  # review r1 finding 6: 3 byte characters get the chat's refusal, not a bare 413
        self.assertIn(f"A message is at most {try_sales.MAX_PASTE} characters.", page)
        self.assertEqual(self.model.calls, [])
        self.assertEqual(self.post("/try/assistant", [("text", "x" * pages.MAX_TRY_BODY)])[0], 413)  # still capped
        self.assertEqual(self.post("/try/sales", [("text", "x" * mo.MAX_BODY)])[0], 413)  # Try Sales keeps its cap
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
