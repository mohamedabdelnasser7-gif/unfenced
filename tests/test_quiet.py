"""A chat ends after quiet, and the pause switch (DECISIONS item 54; sales/quiet.py, kit/switch.py).

30 quiet minutes and the customer gets one notice in their own script, once per chat; 30 more and
the chat closes. A closed chat with no order gets chat_closed at once, so the fast note is written
in the same pass and goes into the customer's next chat, a new chat on the same customer_id. A
paused agent saves what comes in and sends nothing: no reply, no notice, and no chat closes. The
clock is a fake one the test moves; no model call, no network."""
import json
import threading
import unittest
from unittest import mock

from channels import whatsapp as wa
from channels.base import Message
from kit import switch
from kit.chats import FIXED, Chats
from kit.db import Db
from kit.limits import Limits
from reflection import fast as sales_fast
from reflection.lessons import Lessons
from reflection.results import Results
from sales import loop, quiet
from tests.fake_model import FakeModel, Outbox, clean_env, say
from tests.test_whatsapp import SendingGraph, TypingGraph, payload, text_msg

T0 = 1_800_000_000.0
NOTE = "Ask what they need it for before naming any item."
ANSWER = "التوصيل حسب المحافظة، قولّي إنت منين؟"
WHO, OTHER = "201111111111", "201222222222"


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.now = T0
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db, clock=lambda: self.now)
        self.results, self.lessons = Results(self.db), Lessons(self.db)
        self.out = Outbox()

    def later(self, seconds):
        self.now += seconds

    def turn(self, text="التوصيل بكام؟", who=WHO, model=None):
        model = model if model is not None else FakeModel(say(ANSWER))
        msg = Message(channel="whatsapp", customer_id=who, text=text)
        return loop.turn(msg, chats=self.chats, model=model, lessons=self.lessons, results=self.results,
                         send=self.out)

    def tick(self, limits=None, send=None, started=None):
        return quiet.tick(chats=self.chats, results=self.results, send=send or self.out, channel="whatsapp",
                          limits=limits, started=started)

    def rows(self, chat_id, result):
        return self.results.query(case=chat_id, result=result)


class TheNotice(Base):
    def test_one_notice_after_30_quiet_minutes_and_never_a_second(self):
        chat_id = self.turn().chat_id
        self.later(30 * 60 - 1)
        self.assertEqual(self.tick(), [])
        self.later(1)
        self.assertEqual(self.tick(), [(chat_id, "notice")])
        self.assertEqual(self.out.sent[-1], (WHO, quiet.NOTICE["arabic"]))
        last = self.chats.steps(chat_id)[-1]
        self.assertEqual((last["role"], last["content"], last["name"]), ("assistant", quiet.NOTICE["arabic"], FIXED))
        self.assertEqual(self.chats.get(chat_id)["notice_at"], self.now)
        sent = len(self.out.sent)
        for wait in (60, quiet.CLOSE_AFTER - 61):
            self.later(wait)
            self.assertEqual(self.tick(), [])
        self.assertEqual(len(self.out.sent), sent)

    def test_the_notice_is_in_the_customers_script(self):
        for text, answer, script in (("how much is delivery?", "Where are you?", "english"),
                                     ("el tawseel b kam? 3ayez a3raf", "enta mn ay ma7afza?", "franco"), ("التوصيل بكام؟", ANSWER, "arabic")):
            with self.subTest(script=script):
                who = f"2010{len(self.out.sent):08d}"
                self.assertEqual(self.turn(text, who=who, model=FakeModel(say(answer))).outcome, "replied")
                self.later(quiet.NOTICE_AFTER)
                self.tick()
                self.assertEqual(self.out.sent[-1], (who, quiet.NOTICE[script]))

    def test_the_lines_say_the_same_in_each_script(self):
        self.assertEqual(quiet.NOTICE["english"], "This chat closes in 30 minutes. Write anytime to keep going.")
        for line in quiet.NOTICE.values():
            self.assertIn("30", line)
            self.assertNotIn("\u2014", line)
            self.assertNotIn("\u2013", line)

    def test_a_customer_over_a_limit_gets_no_notice_and_the_chat_still_closes(self):
        limits = Limits(self.db, customer_daily=1, clock=lambda: self.now)
        chat_id = self.turn().chat_id
        limits.take(f"whatsapp:{WHO}")
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(self.tick(limits=limits), [(chat_id, "notice")])
        self.assertEqual([t for _, t in self.out.sent if t == quiet.NOTICE["arabic"]], [])
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(self.tick(limits=limits), [(chat_id, "closed")])

    def test_a_notice_that_could_not_be_sent_is_not_tried_again(self):
        calls = []

        def refused(to, text):
            calls.append(text)
            raise wa.SendRefused(400, 131047)
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        with self.assertLogs("sales.quiet", "ERROR"):
            self.tick(send=refused)
        self.later(60)
        self.tick(send=refused)
        self.assertEqual(calls, [quiet.NOTICE["arabic"]])
        self.assertNotEqual(self.chats.steps(chat_id)[-1]["content"], quiet.NOTICE["arabic"])
        self.later(quiet.CLOSE_AFTER - 60)
        self.assertEqual(self.tick(send=refused), [(chat_id, "closed")])

    def test_only_the_channels_open_chats_are_read(self):
        chat_id = self.turn().chat_id
        imported = self.chats.open("history:whatsapp", WHO)
        self.chats.add_step(imported, "user", content="old")
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(self.tick(), [(chat_id, "notice")])
        self.assertIsNone(self.chats.get(imported)["notice_at"])


class TheClose(Base):
    def test_the_chat_closes_after_60_quiet_minutes_and_goes_to_the_hotfix_lost(self):
        chat_id = self.turn().chat_id
        self.later(30 * 60)  # minutes as the decision says them, not the constants
        self.assertEqual(self.tick(), [(chat_id, "notice")])
        self.later(30 * 60 - 1)
        self.assertEqual(self.tick(), [])
        self.assertIsNone(self.chats.get(chat_id)["closed_at"])
        self.later(1)
        self.assertEqual(self.tick(), [(chat_id, "closed")])
        self.assertEqual(self.chats.get(chat_id)["closed_at"], T0 + 60 * 60)
        row, = self.rows(chat_id, "chat_closed")
        self.assertEqual((row["action"], row["at"]), (None, self.now))
        self.assertEqual(self.tick(), [])  # closed once
        self.assertEqual(len(self.rows(chat_id, "chat_closed")), 1)

    def test_a_chat_with_an_order_closes_with_no_row(self):
        chat_id = self.turn().chat_id
        self.results.record(chat_id, "order_created", detail={"order": "#1001", "store": "demo", "total": 1450})
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(self.tick(), [(chat_id, "closed")])
        self.assertEqual(self.rows(chat_id, "chat_closed"), [])

    def test_a_message_in_the_window_keeps_the_chat_open_then_an_hour_of_quiet_closes_it(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER - 60)
        self.assertEqual(self.turn("لسه معاك").chat_id, chat_id)
        sent = len(self.out.sent)
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(self.tick(), [])  # kept open, and no second notice
        self.later(quiet.NOTICE_AFTER - 1)
        self.assertEqual(self.tick(), [])
        self.later(1)
        self.assertEqual(self.tick(), [(chat_id, "closed")])
        self.assertEqual(len(self.out.sent), sent)

    def test_a_later_message_starts_a_new_chat_on_the_same_customer(self):
        first = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)
        self.tick()
        self.later(3600)
        second = self.turn("رجعت تاني").chat_id
        self.assertNotEqual(second, first)
        self.assertEqual({self.chats.get(c)["customer_id"] for c in (first, second)}, {WHO})
        self.assertEqual((self.chats.first_chat(second), self.chats.customer_chats(second)), (first, [first, second]))
        self.assertEqual(self.turn("طيب").chat_id, second)  # the new chat is open
        self.assertNotIn(self.chats.open("whatsapp", OTHER), (first, second))

    def test_a_branch_is_never_ticked(self):
        chat_id = self.turn().chat_id
        branch = self.chats.branch(chat_id, 1)
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(self.tick(), [(chat_id, "notice")])
        self.assertIsNone(self.chats.get(branch)["notice_at"])


class TheNoteFollowsTheCustomer(Base):
    def setUp(self):
        super().setUp()
        self.writer = FakeModel(say(json.dumps({"note": NOTE})))
        self.fast = sales_fast.FastNotes(self.db, self.chats, writer=sales_fast.Writer(model=self.writer))
        clock = mock.patch("time.time", new=lambda: self.now)  # the log's rows and the notes on the same clock
        clock.start()
        self.addCleanup(clock.stop)

    def close(self):
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)
        self.tick()

    def prompt(self, text, who=WHO):
        model = FakeModel(say(ANSWER))
        r = loop.turn(Message(channel="whatsapp", customer_id=who, text=text), chats=self.chats, model=model,
                      lessons=self.lessons, results=self.results, send=self.out, fast=self.fast)
        return r.chat_id, model.calls[0]["messages"][0]["content"]

    def test_the_note_from_a_closed_chat_reaches_the_customers_new_chat_only(self):
        first = self.turn().chat_id
        self.close()
        wrote, = self.fast.sweep()
        self.assertEqual((wrote["case"], wrote["text"]), (first, NOTE))
        _, other = self.prompt("مساء الخير", who=OTHER)
        self.assertNotIn(NOTE, other)
        second, prompt = self.prompt("رجعت تاني")
        self.assertNotEqual(second, first)
        self.assertTrue(prompt.endswith(sales_fast.HEADING + "\n- " + NOTE), prompt[-300:])
        self.later(60)
        _, prompt = self.prompt("طيب والمقاس 44؟")
        self.assertIn(NOTE, prompt)  # the whole new chat

    def test_a_note_written_after_the_new_chat_began_is_missed_never_joined_half_way(self):
        self.turn()
        self.close()
        self.later(5)
        self.prompt("رجعت تاني")  # the new chat began before the sweep wrote the note
        note_id = self.fast.sweep()[0]["id"]
        self.later(60)
        _, prompt = self.prompt("طيب")
        self.assertNotIn(NOTE, prompt)
        self.assertEqual(self.fast.state(note_id), "missed")

    def test_the_next_closed_chat_ends_the_note(self):
        self.turn()
        self.close()
        note_id = self.fast.sweep()[0]["id"]
        self.prompt("رجعت تاني")
        self.close()
        self.later(60)
        _, prompt = self.prompt("انا تاني")
        self.assertNotIn(NOTE, prompt)
        self.assertEqual(self.fast.state(note_id), "done")


class ThePauseSwitch(Base):
    def test_the_three_functions(self):
        self.assertFalse(switch.is_paused("sales", db=self.db))
        switch.pause("sales", db=self.db, now=T0)
        self.assertTrue(switch.is_paused("sales", db=self.db))
        self.assertFalse(switch.is_paused("marketing", db=self.db))
        self.assertIsNone(switch.resumed_at("sales", db=self.db))
        switch.resume("sales", db=self.db, now=T0 + 5)
        self.assertFalse(switch.is_paused("sales", db=self.db))
        self.assertEqual(switch.resumed_at("sales", db=self.db), T0 + 5)
        with self.assertRaises(ValueError):
            switch.pause("", db=self.db)

    def test_it_is_kept_in_the_database(self):
        switch.pause(db=self.db)
        with self.db.tx() as c:
            self.assertEqual(dict(c.execute("SELECT agent, paused FROM agent_switch").fetchone()),
                             {"agent": "sales", "paused": 1})

    def test_a_paused_agent_saves_the_message_and_sends_nothing(self):
        switch.pause(db=self.db)
        model = FakeModel(say(ANSWER))
        r = self.turn("التوصيل بكام؟", model=model)
        self.assertEqual((r.outcome, r.reply), ("paused", None))
        self.assertEqual((self.out.sent, model.calls), ([], []))
        self.assertEqual([(s["role"], s["content"]) for s in self.chats.steps(r.chat_id)], [("user", "التوصيل بكام؟")])
        self.assertEqual(self.results.for_chat(r.chat_id), [])

    def test_a_paused_agent_sends_no_notice_and_closes_no_chat(self):
        chat_id = self.turn().chat_id
        switch.pause(db=self.db, now=self.now)
        self.later(quiet.NOTICE_AFTER + quiet.CLOSE_AFTER + 60)
        self.assertEqual(self.tick(), [])
        self.assertEqual([t for _, t in self.out.sent], [ANSWER])
        self.assertEqual((self.chats.get(chat_id)["notice_at"], self.chats.get(chat_id)["closed_at"]), (None, None))

    def test_after_a_resume_the_agent_answers_and_quiet_counts_from_the_resume(self):
        chat_id = self.turn().chat_id
        switch.pause(db=self.db, now=self.now)
        self.later(3 * 3600)
        switch.resume(db=self.db, now=self.now)
        self.assertEqual(self.tick(), [])  # not closed for the hours it was paused
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(self.tick(), [(chat_id, "notice")])
        r = self.turn("لسه معاك")
        self.assertEqual((r.chat_id, r.outcome), (chat_id, "replied"))

    def test_a_crashed_turn_of_a_paused_agent_sends_nothing(self):
        switch.pause(db=self.db)
        msg = Message(channel="whatsapp", customer_id=WHO, text="hi", message_id="m1")
        self.chats.first_seen("m1")
        self.assertIsNone(loop.failed_turn(msg, chats=self.chats, model=None, results=self.results, send=self.out))
        self.assertEqual(self.out.sent, [])


class TheRunningAgent(Base):
    def test_the_sweep_thread_ticks_first_then_sweeps(self):
        order = []
        app = wa.App(self.chats, None, None, self.results, SendingGraph(b"", "audio/ogg"), connected=True)
        app.quiet_once = lambda: order.append("tick")
        app.sweep_once = lambda: order.append("sweep")
        stop = threading.Event()
        real_wait = stop.wait
        calls = []

        def wait(every):
            calls.append(every)
            if len(calls) > 1:
                stop.set()
            return real_wait(0)
        stop.wait = wait
        app.sweep_fast(stop=stop, every=wa.FAST_EVERY)
        self.assertEqual(order, ["tick", "sweep"])

    def test_the_app_ticks_on_its_clock_and_sends_through_graph(self):
        graph = TypingGraph(b"", "audio/ogg")
        app = wa.App(self.chats, FakeModel(say(ANSWER)), self.lessons, self.results, graph, connected=True)
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        chat_id = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(app.quiet_once(), [(chat_id, "notice")])
        self.assertEqual(graph.sent[-1], (WHO, quiet.NOTICE["arabic"]))
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(app.quiet_once(), [(chat_id, "closed")])
        # the turn's reply had the dots; the tick's notice and close get none
        self.assertEqual([e[0] for e in graph.events], ["typing", "send", "send"])

    def test_a_tick_that_fails_never_stops_the_running_agent(self):
        class Broken:
            clock = staticmethod(lambda: T0)

            def open_chats(self, channel):
                raise RuntimeError("down")
        broken = Broken()
        broken.db = self.db
        with self.assertLogs("channels.whatsapp", "ERROR"):
            self.assertEqual(wa.App(broken, None, None, self.results, SendingGraph(b"", "audio/ogg"), connected=True).quiet_once(), [])


if __name__ == "__main__":
    unittest.main()
