"""Review and red team handoff2 round 2 on the quiet close (DECISIONS item 54; sales/quiet.py, kit/chats.py,
kit/db.py).

Finding 1: a notice that falls due while the process runs always goes out, however late the tick comes
(a slow fast reflection sweep shares its thread); only a chat whose notice was due before the process
started closes silently. Finding 2: a message stuck pending holds its chat for CLOSE_AFTER at most.
Finding 3: the pending check reads a partial index. Minor 4: a silent close records its real quiet
minutes. Red team 3: a close and its result land together or not at all (tx() nests). Red team 2b: the
upgrade's close leaves a chat whose customer has a message pending. The test gaps: each guard on its own.
The clock is a fake one the test moves; no model call, no network."""
import json
import logging
import unittest

from channels import whatsapp as wa
from channels.base import Message
from kit import chats as chats_mod
from kit.chats import Chats
from kit.db import Db
from reflection.results import Results
from sales import loop, quiet
from tests.fake_model import FakeModel, say
from tests.test_quiet import ANSWER, OTHER, T0, WHO, Base
from tests.test_quiet_r1 import OLD_SCHEMA
from tests.test_whatsapp import TypingGraph, payload, text_msg


class SlowSweep:
    """Fast reflection's sweep taking 6 minutes (20 notes at about 18 seconds each) on the fake clock."""

    def __init__(self, test):
        self.test = test

    def sweep(self):
        self.test.later(6 * 60)
        return []


class Due(Base):
    """Finding 1 and minor 4."""

    def app(self, **k):
        return wa.App(self.chats, FakeModel(*[say(ANSWER)] * 4), self.lessons, self.results,
                      TypingGraph(b"", "audio/ogg"), **k)

    def test_a_notice_due_during_a_slow_sweep_still_goes_and_the_close_waits_30_minutes_after_it(self):
        app = self.app(fast=SlowSweep(self))
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        chat_id = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER - 20)
        self.assertEqual(app.quiet_once(), [])
        app.sweep_once()  # 6 minutes
        self.later(30)
        self.assertEqual(app.quiet_once(), [(chat_id, "notice")])  # 36 minutes quiet: late, still sent
        self.assertEqual(app.graph.sent[-1], (WHO, quiet.NOTICE["arabic"]))
        self.later(quiet.CLOSE_AFTER - 1)
        self.assertEqual(app.quiet_once(), [])
        self.later(1)
        self.assertEqual(app.quiet_once(), [(chat_id, "closed")])

    def test_a_yes_after_a_late_notice_stays_in_the_chat(self):
        app = self.app(fast=SlowSweep(self))
        app.accept(wa.parse(payload(text_msg("wamid.m1", "التوصيل بكام؟", frm=WHO))))
        chat_id = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER - 20)
        app.quiet_once()
        app.sweep_once()
        self.later(30)
        app.quiet_once()
        self.later(4 * 60)  # minute 40
        app.accept(wa.parse(payload(text_msg("wamid.m2", "تمام هاخده", frm=WHO))))
        self.assertEqual(app.work_one(app.q.get_nowait()).chat_id, chat_id)

    def test_a_notice_hours_late_goes_when_it_fell_due_while_running(self):
        started = self.now
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER + 3 * 3600)  # the sweep thread was stuck, the process ran on
        self.assertEqual(self.tick(started=started), [(chat_id, "notice")])

    def test_only_a_notice_due_before_the_start_is_skipped(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER + 60)
        start = self.now - 60  # the notice fell due at the very moment the process started
        self.assertEqual(self.tick(started=start), [(chat_id, "notice")])
        other = self.turn(who=OTHER).chat_id
        self.later(quiet.NOTICE_AFTER + 60)  # the first chat is due to close now too
        self.assertEqual(self.tick(started=self.now - 59), [(chat_id, "closed"), (other, "closed")])
        self.assertIsNone(self.chats.get(other)["notice_at"])  # its notice was due a second before the start

    def test_the_app_skips_only_notices_due_before_it_started(self):
        old = self.turn(who=OTHER).chat_id
        self.later(2 * 3600)  # the process was down two hours
        app = self.app()
        self.assertEqual(app.started, self.now)
        self.assertEqual(app.quiet_once(), [(old, "closed")])
        self.assertEqual(app.graph.sent, [])
        self.assertEqual(self.rows(old, quiet.CLOSED)[0]["detail"]["quiet_minutes"], 120)

    def test_a_silent_close_records_its_real_quiet_minutes(self):
        for gap, minutes in ((quiet.NOTICE_AFTER + 1, 30), (3 * 3600 + 59, 180), (3 * 86400, 3 * 1440)):
            with self.subTest(gap=gap):
                chat_id = self.turn(who=f"2010{gap:08d}").chat_id
                self.later(gap)
                self.assertEqual(self.tick(started=self.now), [(chat_id, "closed")])
                self.assertEqual(self.rows(chat_id, quiet.CLOSED)[0]["detail"]["quiet_minutes"], minutes)

    def test_an_on_time_close_records_the_quiet_hour(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick(started=T0)
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(self.tick(started=T0), [(chat_id, "closed")])
        self.assertEqual(self.rows(chat_id, quiet.CLOSED)[0]["detail"]["quiet_minutes"], 60)


class StuckPending(Base):
    """Finding 2: a message whose turn and failed turn both crashed before its step was saved."""

    def setUp(self):
        super().setUp()
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_a_stuck_message_holds_its_chat_for_close_after_at_most(self):
        self.assertEqual(chats_mod.PENDING_HOLD, quiet.CLOSE_AFTER)
        app = wa.App(self.chats, FakeModel(*[say(ANSWER)] * 4), self.lessons, self.results, TypingGraph(b"", "audio/ogg"))
        app.accept(wa.parse(payload(text_msg("wamid.m1", "hi", frm=WHO))))
        first = app.work_one(app.q.get_nowait()).chat_id
        self.later(quiet.NOTICE_AFTER - 60)
        app.accept(wa.parse(payload(text_msg("wamid.m2", "x", frm=WHO))))
        real = self.chats.receive

        def boom(*a, **k):
            raise RuntimeError("database is locked")

        self.chats.receive = boom
        item = app.q.get_nowait()
        try:
            app.work_one(item)
        except RuntimeError:
            app.turn_failed(item)
        finally:
            self.chats.receive = real
        self.assertFalse(self.chats.saved("wamid.m2"))
        self.later(60)
        self.assertEqual(app.quiet_once(), [])  # notice due, but a message is still on its way in
        self.later(chats_mod.PENDING_HOLD - 61)
        self.assertEqual(app.quiet_once(), [])  # still younger than the hold
        self.later(1)
        self.assertEqual(app.quiet_once(), [(first, "notice")])
        self.later(quiet.CLOSE_AFTER)
        self.assertEqual(app.quiet_once(), [(first, "closed")])


class PendingIndex(unittest.TestCase):
    """Finding 3."""

    class Spy:
        """The connection, keeping every SQL it runs."""

        def __init__(self, conn):
            self.conn, self.sql = conn, []

        def execute(self, sql, args=()):
            self.sql.append((sql, args))
            return self.conn.execute(sql, args)

        def __getattr__(self, name):
            return getattr(self.conn, name)

    def plan(self, db, sql, args):
        return " | ".join(r[3] for r in db.conn.execute("EXPLAIN QUERY PLAN " + sql, args))

    def test_the_index_is_made_on_a_new_and_an_old_database_and_twice_is_fine(self):
        for schema in (None, OLD_SCHEMA):
            with self.subTest(old=schema is not None):
                db = Db(":memory:")
                self.addCleanup(db.close)
                if schema:
                    db.script(schema)
                Chats(db)
                Chats(db)  # a restart: the index is there already
                row = db.conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'seen_pending'").fetchone()
                self.assertIsNotNone(row)
                self.assertIn("WHERE status = 'pending'", row[0])

    def test_the_tick_reads_the_pending_rows_through_the_index(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db, clock=lambda: T0)
        cid, n = chats.receive("whatsapp", WHO, content="hi")
        with db.tx() as c:
            c.executemany("INSERT INTO seen_messages (message_id, at, status) VALUES (?, ?, 'done')",
                          ((f"wamid.{i}", T0 - i) for i in range(2000)))
            c.execute("ANALYZE")
        spy = self.Spy(db.conn)
        db.conn = spy
        try:
            chats.open_chats("whatsapp")
            chats.mark_notice(cid, T0, last_n=n)
            chats.close(cid, T0, last_n=n)
        finally:
            db.conn = spy.conn
        reads = [(s, a) for s, a in spy.sql if "seen_messages m" in s]
        self.assertEqual(len(reads), 3)
        for sql, args in reads:
            with self.subTest(sql=sql[:40]):
                plan = self.plan(db, sql, args)
                self.assertIn("seen_pending", plan)
                self.assertNotRegex(plan, r"SCAN m(?! USING)")


class OneStep(Base):
    """Red team item 3: the close and its result land together or not at all."""

    def test_a_failing_result_write_undoes_the_close(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)
        steps = len(self.chats.steps(chat_id))

        def broken(*a, **k):
            raise RuntimeError("disk I/O error")

        self.results.result = broken
        with self.assertRaises(RuntimeError):
            self.tick()
        del self.results.result
        self.assertIsNone(self.chats.get(chat_id)["closed_at"])
        self.assertEqual(len(self.chats.steps(chat_id)), steps)  # no close event either
        self.assertEqual(self.tick(), [(chat_id, "closed")])  # the next tick closes it, with its row
        self.assertEqual(len(self.rows(chat_id, quiet.CLOSED)), 1)

    def test_a_tx_inside_a_tx_commits_with_the_outer_one(self):
        db = self.db
        db.script("CREATE TABLE t (x INTEGER)")
        with self.assertRaises(ValueError), db.tx() as c:
            c.execute("INSERT INTO t VALUES (1)")
            with db.tx() as c2:
                c2.execute("INSERT INTO t VALUES (2)")
            raise ValueError
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 0)
        with db.tx() as c:  # the inner one opens the transaction itself
            with db.tx() as c2:
                c2.execute("INSERT INTO t VALUES (3)")
            self.assertTrue(db.conn.in_transaction)
        with db.tx() as c:  # an inner error caught inside undoes only the inner writes
            c.execute("INSERT INTO t VALUES (4)")
            try:
                with db.tx() as c2:
                    c2.execute("INSERT INTO t VALUES (5)")
                    raise KeyError
            except KeyError:
                pass
        self.assertEqual([r[0] for r in db.conn.execute("SELECT x FROM t ORDER BY x")], [3, 4])
        self.assertFalse(db.conn.in_transaction)


class SqlGuards(Base):
    """Test gap: the pending check inside mark_notice and close holds on its own, for a message accepted
    while the tick runs (after its view of the open chats)."""

    def setUp(self):
        super().setUp()
        self.app = wa.App(self.chats, FakeModel(say(ANSWER)), self.lessons, self.results, TypingGraph(b"", "audio/ogg"))

    def accept_during(self, who, text):
        def slow_send(to, line):
            if to == WHO:
                self.later(3)
                self.app.accept(wa.parse(payload(text_msg(f"wamid.{who}", text, frm=who))))
        return slow_send

    def test_a_message_accepted_during_the_tick_holds_off_the_close(self):
        a = self.turn(who=WHO).chat_id
        self.later(1)
        b = self.turn(who=OTHER).chat_id
        self.later(quiet.NOTICE_AFTER)
        self.chats.mark_notice(b, self.now)
        self.assertEqual(self.turn("طيب", who=WHO).chat_id, a)
        self.later(quiet.CLOSE_AFTER)  # a due its notice, b due to close
        self.assertEqual(self.tick(send=self.accept_during(OTHER, "لسه معاك")), [(a, "notice")])
        self.assertIsNone(self.chats.get(b)["closed_at"])
        self.assertEqual(self.app.work_one(self.app.q.get_nowait()).chat_id, b)

    def test_a_message_accepted_during_the_tick_holds_off_the_notice(self):
        a = self.turn(who=WHO).chat_id
        self.later(1)
        b = self.turn(who=OTHER).chat_id
        self.later(quiet.NOTICE_AFTER)  # both due their notice; a goes first
        self.assertEqual(self.tick(send=self.accept_during(OTHER, "ومقاس 44؟")), [(a, "notice")])
        self.assertIsNone(self.chats.get(b)["notice_at"])


class TestGaps(Base):
    """The customer's message reaches the model once; failed_turn finds the chat and saves the step in one
    transaction."""

    def test_the_customers_message_reaches_the_model_once(self):
        model = FakeModel(say(ANSWER))
        self.turn("عايز اعرف التوصيل لمدينة نصر بكام", model=model)
        sent = json.dumps(model.calls[0]["messages"], ensure_ascii=False)
        self.assertEqual(sent.count("عايز اعرف التوصيل لمدينة نصر بكام"), 1)
        model = FakeModel(say(ANSWER))
        self.turn("وللتجمع الخامس؟", model=model)  # a second turn in the same chat
        sent = json.dumps(model.calls[0]["messages"], ensure_ascii=False)
        self.assertEqual(sent.count("وللتجمع الخامس؟"), 1)
        self.assertEqual(sent.count("عايز اعرف التوصيل لمدينة نصر بكام"), 1)

    def test_a_failed_turn_never_saves_into_a_chat_closed_meanwhile(self):
        first = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER)
        self.tick()
        self.later(quiet.CLOSE_AFTER)  # due to close as the crashed message is saved
        self.chats.first_seen("wamid.crash", {"customer_id": WHO, "text": "انا رجعت"})
        self.db.conn.execute("UPDATE seen_messages SET at = ? WHERE message_id = 'wamid.crash'",
                             (self.now - chats_mod.PENDING_HOLD,))  # re-queued after a restart: too old to hold
        real_receive, real_add = self.chats.receive, self.chats.add_step
        closed = []

        def receive(*a, **k):  # the tick wins the lock first
            closed.extend(self.tick())
            return real_receive(*a, **k)

        def add_step(chat_id, role, *a, **k):  # the same tick, if the chat is found and saved in two steps
            if role == "user":
                closed.extend(self.tick())
            return real_add(chat_id, role, *a, **k)

        self.chats.receive, self.chats.add_step = receive, add_step
        try:
            msg = Message(channel="whatsapp", customer_id=WHO, text="انا رجعت", message_id="wamid.crash")
            loop.failed_turn(msg, chats=self.chats, model=FakeModel(say(ANSWER)), results=self.results, send=self.out)
        finally:
            self.chats.receive, self.chats.add_step = real_receive, real_add
        self.assertEqual(closed, [(first, "closed")])
        self.assertNotIn("انا رجعت", [s["content"] for s in self.chats.steps(first)])
        self.assertTrue(self.chats.saved("wamid.crash"))


class OldDatabaseShapes(unittest.TestCase):
    """Test gap and red team 2b: the upgrade's close reads the last customer or agent step (not an event,
    not when the chat was made) and leaves a chat whose customer has a message pending."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.db.script(OLD_SCHEMA)

    def chat(self, cid, who, created, steps):
        with self.db.tx() as c:
            c.execute("INSERT INTO chats (id, channel, customer_id, stage, created_at, updated_at) "
                      "VALUES (?, 'whatsapp', ?, 'asking', ?, ?)", (cid, who, created, created))
            for n, (role, at) in enumerate(steps, 1):
                c.execute("INSERT INTO steps VALUES (?, ?, ?, 'x', NULL, NULL, NULL, NULL, ?)", (cid, n, role, at))

    def closed(self):
        Chats(self.db, clock=lambda: T0)
        return {r[0] for r in self.db.conn.execute("SELECT id FROM chats WHERE closed_at IS NOT NULL")}

    def test_an_old_chat_with_a_recent_message_stays_open(self):
        self.chat("old_but_talking", "201000000001", T0 - 3 * 86400, [("user", T0 - 3 * 86400), ("assistant", T0 - 600)])
        self.chat("quiet_with_an_event", "201000000002", T0 - 3 * 3600,
                  [("user", T0 - 2 * 3600), ("assistant", T0 - 2 * 3600), ("event", T0 - 300)])
        self.chat("no_steps", "201000000003", T0 - 2 * 3600, [])
        self.assertEqual(self.closed(), {"quiet_with_an_event", "no_steps"})

    def test_a_chat_whose_customer_has_a_message_pending_stays_open(self):
        self.chat("waiting", "201000000001", T0 - 5 * 3600, [("user", T0 - 5 * 3600)])
        self.chat("gone", "201000000002", T0 - 5 * 3600, [("user", T0 - 5 * 3600)])
        with self.db.tx() as c:  # accepted four hours ago, before the stop, never saved
            c.execute("INSERT INTO seen_messages (message_id, at, status, payload) VALUES ('wamid.w', ?, 'pending', ?)",
                      (T0 - 4 * 3600, json.dumps({"customer_id": "201000000001", "text": "تمام"})))
        self.assertEqual(self.closed(), {"gone"})


if __name__ == "__main__":
    unittest.main()
