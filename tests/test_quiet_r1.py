"""Review and red team handoff2 round 1 on the quiet close (DECISIONS item 54; sales/quiet.py, kit/chats.py).

Finding 1 and red team item 1: the tick works from one view of the open chats and a notice send can take
seconds, so a chat whose customer wrote meanwhile is never closed; the customer's step and the chat it goes
in are found in one transaction, so a close never lands between them; no chat ends with chat_closed beside
replied or order_created. Finding 2: a message accepted from the webhook and still queued keeps its chat
as it is. Finding 3: no notice goes out that was due before a restart or an upgrade; a database made before the
quiet columns has its old chats closed silently. The clock is a fake one the test moves; no model call,
no network."""
import json
import threading
import unittest

from channels import whatsapp as wa
from kit import chats as chats_mod
from kit.chats import Chats
from kit.db import Db
from sales import quiet
from tests.test_quiet import ANSWER, OTHER, T0, WHO, Base
from tests.fake_model import FakeModel, say
from tests.test_whatsapp import TypingGraph, payload, text_msg

# The chats table and the webhook ids as they were before the quiet columns (abc8a36 and earlier).
OLD_SCHEMA = """
CREATE TABLE chats (id TEXT PRIMARY KEY, channel TEXT NOT NULL, customer_id TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'asking', failed_checks INTEGER NOT NULL DEFAULT 0, parent_id TEXT,
  branched_at INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  model_errors INTEGER NOT NULL DEFAULT 0);
CREATE TABLE steps (chat_id TEXT NOT NULL REFERENCES chats (id), n INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'event')), content TEXT, tool_calls TEXT,
  tool_call_id TEXT, name TEXT, media TEXT, at REAL NOT NULL, PRIMARY KEY (chat_id, n));
CREATE TABLE seen_messages (message_id TEXT PRIMARY KEY, at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  payload TEXT, attempts INTEGER NOT NULL DEFAULT 0);
"""


class Races(Base):
    """Finding 1 and red team item 1."""

    def no_lost_beside_a_reply(self):
        """No chat is both lost and won, and nothing is said or answered in a chat after it closed."""
        for (cid,) in self.db.conn.execute("SELECT id FROM chats").fetchall():
            closed_at = self.chats.get(cid)["closed_at"]
            if closed_at is None:
                continue
            self.assertFalse(self.rows(cid, quiet.CLOSED) and self.rows(cid, "order_created"), cid)
            self.assertEqual([r for r in self.rows(cid, "replied") if r["at"] >= closed_at], [], cid)
            steps = self.chats.steps(cid)
            close_n = max(s["n"] for s in steps if s["role"] == "event" and '"closed"' in (s["content"] or ""))
            self.assertEqual([s["n"] for s in steps if s["n"] > close_n], [], cid)

    def two_due(self):
        """a (the older chat) due its notice, on time; b due to close, both at the next tick."""
        a = self.turn(who=WHO).chat_id
        self.later(1)
        b = self.turn(who=OTHER).chat_id
        self.later(quiet.NOTICE_AFTER)
        self.chats.mark_notice(b, self.now)
        self.assertEqual(self.turn("طيب", who=WHO).chat_id, a)
        self.later(quiet.CLOSE_AFTER)
        return a, b

    def test_a_message_during_another_chats_notice_send_keeps_that_chat_open(self):
        a, b = self.two_due()  # a: its notice is due; b: due to close
        seen = []

        def slow_send(to, text):  # while a's notice goes out, b's customer writes and gets an answer
            if to == WHO:
                self.later(3)
                seen.append(self.turn("لسه معاك، عايز اطلب", who=OTHER).chat_id)

        self.assertEqual(self.tick(send=slow_send), [(a, "notice")])
        self.assertEqual(seen, [b])
        self.assertIsNone(self.chats.get(b)["closed_at"])
        self.assertEqual(self.rows(b, quiet.CLOSED), [])
        self.assertEqual(self.turn("1", who=OTHER).chat_id, b)  # the customer's next message stays in b
        self.no_lost_beside_a_reply()

    def test_a_message_during_another_chats_notice_send_gets_no_notice(self):
        a = self.turn(who=WHO).chat_id
        self.later(1)
        b = self.turn(who=OTHER).chat_id
        self.later(quiet.NOTICE_AFTER)  # both due their notice; a goes first

        def slow_send(to, text):
            if to == WHO:
                self.later(3)
                self.turn("ومقاس 44؟", who=OTHER)

        self.assertEqual(self.tick(send=slow_send), [(a, "notice")])
        self.assertIsNone(self.chats.get(b)["notice_at"])
        self.assertNotIn(quiet.NOTICE["arabic"], [s["content"] for s in self.chats.steps(b)])

    def test_a_tick_inside_a_turn_never_closes_the_chat_the_turn_answers_in(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)  # due to close as the customer writes
        real = self.chats.messages
        did = []

        def messages(cid, *a, **k):  # the sweep thread ticks while the worker reads the chat
            did.extend(self.tick())
            return real(cid, *a, **k)

        self.chats.messages = messages
        try:
            r = self.turn("تمام ابعتلي العنوان")
        finally:
            self.chats.messages = real
        self.assertEqual((did, r.chat_id, r.outcome), ([], chat_id, "replied"))
        self.assertIsNone(self.chats.get(chat_id)["closed_at"])
        self.assertEqual(self.chats.steps(chat_id)[-2]["content"], "تمام ابعتلي العنوان")
        self.no_lost_beside_a_reply()

    def test_a_close_just_before_the_step_moves_the_message_to_a_new_chat(self):
        first = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)
        real = self.chats.receive

        def receive(*a, **k):  # the tick wins the lock first
            self.assertEqual(self.tick(), [(first, "closed")])
            return real(*a, **k)

        self.chats.receive = receive
        try:
            r = self.turn("انا رجعت")
        finally:
            self.chats.receive = real
        self.assertNotEqual(r.chat_id, first)
        self.assertEqual(r.outcome, "replied")
        self.assertNotIn("انا رجعت", [s["content"] for s in self.chats.steps(first)])
        self.no_lost_beside_a_reply()

    def test_receive_saves_in_the_open_chat_or_a_new_one_in_one_step(self):
        cid, n = self.chats.receive("whatsapp", WHO, content="hi", message_id="wamid.1")
        self.chats.first_seen("wamid.2", {"customer_id": WHO})
        self.assertEqual((n, self.chats.saved("wamid.1")), (1, False))  # never seen, so nothing to mark
        self.assertEqual(self.chats.receive("whatsapp", WHO, content="again", message_id="wamid.2"), (cid, 2))
        self.assertTrue(self.chats.saved("wamid.2"))
        self.chats.close(cid)
        new, n = self.chats.receive("whatsapp", WHO, content="back")
        self.assertNotEqual(new, cid)
        self.assertEqual((n, self.chats.steps(new)[0]["content"]), (1, "back"))

    def test_close_and_mark_notice_hold_to_the_ticks_view(self):
        cid, n = self.chats.receive("whatsapp", WHO, content="hi")
        self.chats.add_step(cid, "assistant", content="hello")
        self.assertFalse(self.chats.mark_notice(cid, last_n=n))  # the agent spoke after step 1
        self.assertFalse(self.chats.close(cid, last_n=n))
        self.chats.add_step(cid, "event", content=json.dumps({"stage": "x"}))  # an event is no message
        self.assertTrue(self.chats.mark_notice(cid, last_n=n + 1))
        self.assertTrue(self.chats.close(cid, last_n=n + 1))

    def test_an_order_saved_after_the_ticks_view_gets_no_lost_row(self):
        a, b = self.two_due()

        def slow_send(to, text):
            if to == WHO:
                self.results.record(b, "order_created", detail={"order": "#1001", "store": "demo", "total": 1450})

        self.assertEqual(self.tick(send=slow_send), [(a, "notice"), (b, "closed")])
        self.assertEqual(self.rows(b, quiet.CLOSED), [])

    def test_the_close_its_order_check_and_its_result_are_one_step_under_the_lock(self):
        a, b = self.two_due()
        real = self.results.query
        during = []

        def query(**k):  # another thread saves an order while the tick checks b for one
            if k.get("case") == b:
                t = threading.Thread(target=self.results.record, args=(b, "order_created"),
                                     kwargs={"detail": {"order": "#1001", "store": "demo", "total": 1450}})
                t.start()
                t.join(0.3)
                during.append(t.is_alive())  # still waiting for the lock
                self.addCleanup(t.join)
            return real(**k)

        self.results.query = query
        self.assertEqual(self.tick(), [(a, "notice"), (b, "closed")])
        self.assertEqual(during, [True])


class Queued(Base):
    """Finding 2: accept, tick, work_one."""

    def app(self):
        graph = TypingGraph(b"", "audio/ogg")
        return wa.App(self.chats, FakeModel(say(ANSWER), say(ANSWER)), self.lessons, self.results, graph), graph

    def test_a_queued_yes_before_the_close_keeps_the_chat_and_lands_in_it(self):
        app, graph = self.app()
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        first = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(app.quiet_once(), [(first, "notice")])
        self.later(quiet.CLOSE_AFTER - 5)
        app.accept(wa.parse(payload(text_msg("wamid.m2", "تمام هاخده", frm=WHO))))  # the worker is busy elsewhere
        self.later(5)
        self.assertEqual(app.quiet_once(), [])
        self.assertIsNone(self.chats.get(first)["closed_at"])
        self.assertEqual(app.work_one(app.q.get_nowait()).chat_id, first)
        self.assertGreater(len(app.model.calls[-1]["messages"]), 2)  # it reads the chat so far
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(app.quiet_once(), [])  # it came back after the notice: an hour of quiet now
        self.assertEqual(self.rows(first, quiet.CLOSED), [])

    def test_a_queued_question_before_30_minutes_gets_no_notice(self):
        app, graph = self.app()
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        first = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER - 5)
        app.accept(wa.parse(payload(text_msg("wamid.m2", "ومقاس 44 موجود؟", frm=WHO))))
        self.later(5)
        sent = len(graph.sent)
        self.assertEqual(app.quiet_once(), [])
        self.assertEqual(len(graph.sent), sent)
        self.assertEqual(app.work_one(app.q.get_nowait()).chat_id, first)
        self.assertIsNone(self.chats.get(first)["notice_at"])

    def test_another_customers_queued_message_changes_nothing(self):
        app, graph = self.app()
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        first = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER)
        app.accept(wa.parse(payload(text_msg("wamid.o1", "hi", frm=OTHER))))
        self.assertEqual(app.quiet_once(), [(first, "notice")])

    def test_a_message_given_up_on_holds_nothing(self):
        app, graph = self.app()
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        first = app.work_one(app.q.get_nowait()).chat_id
        self.chats.first_seen("wamid.dead", {"customer_id": WHO, "text": "x"})
        self.db.conn.execute("UPDATE seen_messages SET attempts = ? WHERE message_id = 'wamid.dead'",
                             (chats_mod.MAX_ATTEMPTS,))
        self.later(quiet.NOTICE_AFTER)
        self.assertEqual(app.quiet_once(), [(first, "notice")])


class NeverLate(Base):
    """Finding 3, as review round 2 finding 1 left it: only a notice already due when the process started
    is never sent."""

    def test_a_chat_found_long_quiet_after_a_restart_closes_silently(self):
        for gap in (quiet.NOTICE_AFTER + quiet.START_GRACE + 1, quiet.NOTICE_AFTER + quiet.CLOSE_AFTER, 3 * 3600, 3 * 86400):
            with self.subTest(gap=gap):
                who = f"2010{gap:08d}"
                chat_id = self.turn(who=who).chat_id
                sent = len(self.out.sent)
                self.later(gap)  # the process was down; it starts now
                self.assertEqual(self.tick(started=self.now), [(chat_id, "closed")])
                self.assertEqual(len(self.out.sent), sent)
                self.assertIsNone(self.chats.get(chat_id)["notice_at"])
                self.assertEqual(len(self.rows(chat_id, quiet.CLOSED)), 1)

    def test_the_migration_bound_is_the_quiet_hour(self):
        self.assertEqual(chats_mod.OLD_AFTER, quiet.NOTICE_AFTER + quiet.CLOSE_AFTER)


class OldDatabase(unittest.TestCase):
    """Finding 3 on a database made before the quiet columns: nothing goes out on the first tick."""

    def setUp(self):
        self.now = T0
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.db.script(OLD_SCHEMA)
        self.ages = {"3 days": 3 * 86400, "5 hours": 5 * 3600, "90 minutes": 90 * 60, "an hour": 3600,
                     "40 minutes": 40 * 60, "31 minutes": 31 * 60, "10 minutes": 10 * 60}
        with self.db.tx() as c:
            for i, age in enumerate(self.ages.values()):
                c.execute("INSERT INTO chats (id, channel, customer_id, stage, created_at, updated_at) "
                          "VALUES (?, 'whatsapp', ?, 'asking', ?, ?)", (f"c{i}", f"20100000000{i}", T0 - age - 60, T0 - age))
                c.execute("INSERT INTO steps VALUES (?, 1, 'user', 'x', NULL, NULL, NULL, NULL, ?)", (f"c{i}", T0 - age - 60))
                c.execute("INSERT INTO steps VALUES (?, 2, 'assistant', 'y', NULL, NULL, NULL, NULL, ?)", (f"c{i}", T0 - age))

    def test_the_first_tick_after_the_upgrade_sends_nothing_late(self):
        from reflection.results import Results
        chats = Chats(self.db, clock=lambda: self.now)
        results = Results(self.db)
        names = dict(zip((f"c{i}" for i in range(len(self.ages))), self.ages))
        closed = {names[r["id"]] for r in self.db.conn.execute("SELECT id FROM chats WHERE closed_at IS NOT NULL")}
        self.assertEqual(closed, {"3 days", "5 hours", "90 minutes", "an hour"})  # by the migration, no result
        self.assertEqual(results.query(result=quiet.CLOSED), [])
        sent = []
        did = quiet.tick(chats=chats, results=results, send=lambda to, text: sent.append((to, text)),
                         channel="whatsapp", started=T0)
        # 40 minutes: due 10 minutes before the start, past the grace, closed silently with its result;
        # 31 minutes: due a minute before the start, inside the grace, so its notice still goes
        self.assertEqual(sorted((names[c], w) for c, w in did), [("31 minutes", "notice"), ("40 minutes", "closed")])
        self.assertEqual(len(sent), 1)
        Chats(self.db, clock=lambda: self.now)  # a restart: the columns are there, nothing more closes
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM chats WHERE closed_at IS NULL").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
