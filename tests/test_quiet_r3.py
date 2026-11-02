"""Review and red team handoff2 round 3 on the quiet close (DECISIONS item 54; sales/quiet.py, kit/chats.py,
kit/db.py).

Review finding 1: a message a restart requeues holds its chat for PENDING_HOLD from the requeue, so the
first tick never closes the chat before the worker reaches it. Red team finding 1: a notice that fell due
just before a quick restart still goes out (START_GRACE). The test gaps: an inner tx error is raised, not
swallowed. The clock is a fake one the test moves; no model call, no network."""
import logging

from channels import whatsapp as wa
from sales import quiet
from tests.fake_model import FakeModel, say
from tests.test_quiet import ANSWER, OTHER, WHO, Base
from tests.test_whatsapp import TypingGraph, payload, text_msg


class Requeue(Base):
    def setUp(self):
        super().setUp()
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def graph(self):
        return TypingGraph(b"", "audio/ogg")

    def test_a_requeued_yes_after_a_long_stop_lands_in_its_chat(self):
        a = self.turn(who=WHO).chat_id
        b = self.turn(who=OTHER).chat_id
        self.later(60)
        old = wa.App(self.chats, FakeModel(), self.lessons, self.results, self.graph(), connected=True)
        old.accept(wa.parse(payload(text_msg("wamid.a2", "طيب مقاس 43", frm=WHO))))
        old.accept(wa.parse(payload(text_msg("wamid.b2", "تمام هاخده", frm=OTHER))))
        self.later(2 * 3600)  # the process was down two hours

        def slow(m, t):
            self.later(31)  # the first turn outlasts the first tick's 30 seconds
            return say(ANSWER)

        app = wa.App(self.chats, FakeModel(slow, say(ANSWER)), self.lessons, self.results, self.graph(), connected=True)
        self.assertEqual(app.requeue_pending(), 2)
        self.assertEqual(app.work_one(app.q.get_nowait()).chat_id, a)
        self.assertNotIn(b, [c for c, _ in app.quiet_once()])
        self.assertEqual(app.work_one(app.q.get_nowait()).chat_id, b)
        self.assertEqual(self.rows(b, quiet.CLOSED), [])


class Grace(Base):
    def test_a_notice_due_just_before_a_quick_restart_still_goes(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER + 1)
        self.assertEqual(self.tick(started=self.now), [(chat_id, "notice")])

    def test_a_notice_due_past_the_grace_is_skipped(self):
        chat_id = self.turn().chat_id
        self.later(quiet.NOTICE_AFTER + quiet.START_GRACE + 2)
        self.assertEqual(self.tick(started=self.now), [(chat_id, "closed")])
        self.assertIsNone(self.chats.get(chat_id)["notice_at"])


class InnerError(Base):
    def test_an_inner_tx_error_is_raised_and_the_outer_one_rolls_back(self):
        db = self.db
        db.script("CREATE TABLE t (x INTEGER)")
        with self.assertRaises(KeyError):
            with db.tx() as c:
                c.execute("INSERT INTO t VALUES (1)")
                with db.tx() as c2:
                    c2.execute("INSERT INTO t VALUES (2)")
                    raise KeyError
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 0)
        self.assertFalse(db.conn.in_transaction)
