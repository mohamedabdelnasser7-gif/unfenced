"""One case id across a customer's talks (DECISIONS item 65; kit/chats.py, engine/log.py).

A customer who writes again after their chat closed continues the same case id: the new chat is
talk 2, talk 3 of that case, saved under the same case id, and each talk has its own result, its
own fast note and its own place in the night study's counts. A database made before talks keeps
every chat and every saved row as it was. Made up text only, a fake clock, fake models, no network."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import grow
from channels.base import Message
from engine import fast as engine_fast
from engine import study
from engine.log import Log, talk_key
from kit.chats import Chats
from kit.db import Db
from reflection import PLUG as SALES
from reflection import fast as sales_fast
from reflection import late as late_mod
from reflection.lessons import Lessons
from reflection.results import Results, late
from sales import loop, quiet
from tests import plugs
from tests.fake_model import FakeModel, Outbox, clean_env, say

T0 = 1_800_000_000.0
WHO, OTHER = "201000000001", "201000000002"
ASK = "how much is delivery?"
ANSWER = "Where are you based?"
TONE = "Ask where they live before talking about delivery."
SHOP = {"store": "shopify", "total": 900}


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.now = T0
        clock = mock.patch("time.time", new=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.lessons, self.results = Chats(self.db), Lessons(self.db), Results(self.db)
        self.out = Outbox()
        self.writer = FakeModel(say(json.dumps({"note": TONE})), say(json.dumps({"note": TONE})))
        self.fast = sales_fast.FastNotes(self.db, self.chats, writer=sales_fast.Writer(model=self.writer))

    def later(self, seconds):
        self.now += seconds

    def turn(self, text=ASK, who=WHO):
        model = FakeModel(say(ANSWER))
        msg = Message(channel="whatsapp", customer_id=who, text=text)
        r = loop.turn(msg, chats=self.chats, model=model, lessons=self.lessons, results=self.results,
                      send=self.out, fast=self.fast)
        return r.chat_id, model.calls[0]["messages"][0]["content"] if model.calls else None

    def close_quiet(self):
        for wait in (quiet.NOTICE_AFTER, quiet.CLOSE_AFTER):
            self.later(wait)
            quiet.tick(chats=self.chats, results=self.results, send=self.out, channel="whatsapp")

    def order(self, chat_id, name):
        self.results.record(chat_id, "order_created", stage="ordering", detail=dict(SHOP, order=name))


class TheCaseId(Base):
    def test_a_customer_who_writes_again_continues_the_same_case_as_the_next_talk(self):
        first, _ = self.turn()
        self.close_quiet()
        self.later(3600)
        second, _ = self.turn("back again")
        self.close_quiet()
        third, _ = self.turn("one more question")
        self.assertEqual(len({first, second, third}), 3)  # each talk is its own chat
        self.assertEqual([self.chats.talk(c) for c in (first, second, third)],
                         [(first, 1), (first, 2), (first, 3)])
        self.assertEqual(self.chats.chat_of(first, 2), second)
        other, _ = self.turn(who=OTHER)
        self.assertEqual(self.chats.talk(other), (other, 1))  # another customer: a case of their own
        branch = self.chats.branch(second, 1)
        self.assertEqual(self.chats.talk(branch), (branch, 1))  # a replay copy: its own case, as before

    def test_the_case_id_is_a_chat_id_never_the_customers_number(self):
        first, _ = self.turn()
        self.close_quiet()
        second, _ = self.turn("back again")
        rows = Log(self.db, SALES).case(first)
        self.assertEqual({r["case_id"] for r in rows}, {first})
        self.assertNotIn(WHO, json.dumps(rows))
        self.assertEqual({r["source"] for r in rows}, {first})  # the customer, across talks

    def test_each_talk_keeps_its_own_rows_under_the_one_case_id(self):
        first, _ = self.turn()
        self.close_quiet()
        second, _ = self.turn("back again")
        self.order(second, "#2002")
        talks = [(r["talk"], r["outcome"]) for r in self.results.for_chat(first)]
        self.assertEqual(talks, [(1, "replied"), (1, "chat_closed")])
        self.assertEqual([(r["talk"], r["outcome"], r["chat_id"]) for r in self.results.for_chat(second)],
                         [(2, "replied", second), (2, "order_created", second)])
        self.assertEqual([r["talk"] for r in Log(self.db, SALES).case(first)], [1, 1, 2, 2])


class TheClose(Base):
    def test_a_quiet_talk_gets_chat_closed_although_an_earlier_talk_ordered(self):
        first, _ = self.turn()
        self.order(first, "#1001")
        self.close_quiet()
        second, _ = self.turn("back again")
        self.close_quiet()
        self.assertEqual([r["outcome"] for r in self.results.for_chat(first)], ["replied", "order_created"])
        self.assertEqual([r["outcome"] for r in self.results.for_chat(second)], ["replied", "chat_closed"])


class TheNight(Base):
    def test_each_talk_is_its_own_unit_in_the_study_with_its_own_result(self):
        first, _ = self.turn()
        self.close_quiet()
        second, _ = self.turn("back again")
        self.order(second, "#2002")
        self.later(60)
        win = Log(self.db, SALES).window(T0 - 1, self.now)
        self.assertEqual(list(win), [first, talk_key(first, 2)])
        self.assertEqual(talk_key(first, 2), f"{first} talk 2")
        cases = study._read(SALES, win, self.now)
        self.assertEqual([(c.id, c.status) for c in cases], [(first, study.BAD), (f"{first} talk 2", study.GOOD)])
        counts = study._counts(SALES, cases)
        self.assertEqual((counts["read"]["cases"], counts["decided"]), (2, {"good": 1, "bad": 1}))

    def test_a_talk_still_going_is_pending_and_never_settled_by_the_talk_before(self):
        first, _ = self.turn()
        self.close_quiet()
        self.turn("back again")
        self.later(60)
        cases = study._read(SALES, Log(self.db, SALES).window(T0 - 1, self.now), self.now)
        self.assertEqual([c.status for c in cases], [study.BAD, study.PENDING])


class TheFastNote(Base):
    def test_each_talk_gets_its_own_note_and_none_while_the_next_talk_runs(self):
        first, _ = self.turn()
        self.close_quiet()
        note_id, = [w["id"] for w in self.fast.sweep() if w["case"] == first]
        second, prompt = self.turn("back again")
        self.assertIn(TONE, prompt)  # the note for talk 1 opens talk 2
        self.later(120)
        self.assertEqual(self.fast.sweep(), [])  # talk 2 is still going: nothing written mid talk
        self.close_quiet()
        self.assertEqual(self.fast.state(note_id), engine_fast.DONE)  # talk 2 ended: its note is gone
        wrote = self.fast.sweep()
        self.assertEqual([w["case"] for w in wrote], [f"{first} talk 2"])
        self.assertEqual(len(self.writer.calls), 2)
        turns = json.loads(self.writer.calls[1]["messages"][1]["content"])["turns"]
        self.assertEqual(turns[0], {"from": "other", "text": "back again"})  # talk 2's own words only


class LateResults(Base):
    def test_a_delivery_lands_on_the_talk_that_ordered_once_each(self):
        first, _ = self.turn()
        self.order(first, "#1001")
        self.close_quiet()
        second, _ = self.turn("back again")
        self.order(second, "#2002")
        self.assertEqual(self.results.chat_for_order("#1001"), first)
        key = self.results.chat_for_order("#2002")
        self.assertEqual(key, f"{first} talk 2")
        self.assertIsNotNone(late(self.db, SALES, key, "delivered", now=self.now))
        self.assertIsNotNone(late(self.db, SALES, first, "refused", now=self.now))  # talk 1 has none yet
        self.assertIsNone(late(self.db, SALES, key, "refused", now=self.now))  # once a talk
        self.assertEqual(self.results.for_chat(second)[-1]["outcome"], "delivered")
        self.assertEqual(self.results.for_chat(first)[-1]["outcome"], "refused")

    def test_a_talk_without_an_order_number_gets_its_own_made_reference(self):
        first, _ = self.turn()
        self.close_quiet()
        self.turn("back again")
        key = late_mod.ref_key(self.db, make=lambda: "ab" * 32)
        win = Log(self.db, SALES).window(T0 - 1, self.now + 1)
        refs = [late_mod.case_ref(SALES, k, rows, key) for k, rows in win.items()]
        self.assertEqual(len(set(refs)), 2)
        self.assertTrue(all(r.startswith("c-") and WHO not in r for r in refs))


class TheKey(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.log = Log(self.db, plugs.load(plugs.WATERER, self))

    def test_a_key_reads_back_to_its_case_and_talk(self):
        self.log.act("bed-1", "water", result="soaked", at=T0)
        self.assertEqual(self.log.unit("bed-1"), ("bed-1", 1))
        self.assertEqual(self.log.unit("bed-1 talk 2"), ("bed-1", 2))  # a talk not begun yet
        self.assertEqual(self.log.unit("bed-9 talk 2"), ("bed-9 talk 2", 1))  # no such case: a plain id
        self.assertEqual(self.log.unit("bed-1 talk 1"), ("bed-1 talk 1", 1))

    def test_a_key_that_reads_two_ways_is_refused(self):
        self.log.act("bed-1", "water", result="soaked", at=T0)
        self.log.act("bed-1 talk 2", "water", result="soaked", at=T0)
        with self.assertRaises(ValueError):
            self.log.unit("bed-1 talk 2")

    def test_a_talk_is_a_whole_number_from_one(self):
        for bad in (0, -1, True, "2", 1.5):
            with self.subTest(talk=bad), self.assertRaises(ValueError):
                self.log.act("bed-1", "water", result="soaked", at=T0, talk=bad)

    def test_an_agent_without_talks_reads_as_before(self):
        self.log.act("bed-1", "water", result="soaked", at=T0)
        self.log.result("bed-1", "wilted", at=T0 + 1)
        self.log.act("bed-1", "water", result="soaked", at=T0 + 2)
        self.assertEqual(list(self.log.window(T0, T0 + 3)), ["bed-1"])
        self.assertEqual(len(self.log.talk("bed-1")), 3)


class OldDatabases(unittest.TestCase):
    """A database made before talks: every chat stays its own case, talk 1, and no saved row moves."""

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "old.db"
        con = sqlite3.connect(self.path)
        con.executescript("""
            CREATE TABLE chats (id TEXT PRIMARY KEY, channel TEXT NOT NULL, customer_id TEXT NOT NULL,
              stage TEXT NOT NULL DEFAULT 'asking', failed_checks INTEGER NOT NULL DEFAULT 0, parent_id TEXT,
              branched_at INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL,
              model_errors INTEGER NOT NULL DEFAULT 0, notice_at REAL, closed_at REAL);
            CREATE TABLE trace (id INTEGER PRIMARY KEY, agent TEXT NOT NULL, case_id TEXT NOT NULL, action TEXT,
              result TEXT, cause TEXT, lessons TEXT NOT NULL DEFAULT '[]', stage TEXT, step INTEGER, detail TEXT,
              at REAL NOT NULL, source TEXT);
        """)
        for cid, at in (("old-a", 1.0), ("old-b", 2.0)):
            con.execute("INSERT INTO chats (id, channel, customer_id, created_at, updated_at, closed_at) "
                        "VALUES (?, 'whatsapp', ?, ?, ?, ?)", (cid, WHO, at, at, at))
            con.execute("INSERT INTO trace (agent, case_id, action, result, at, source) "
                        "VALUES ('sales', ?, 'reply', 'replied', ?, ?)", (cid, at, cid))
        con.commit()
        con.close()
        self.db = Db(self.path)
        self.addCleanup(self.db.close)

    def test_old_chats_stay_their_own_cases_and_the_next_chat_continues_the_last(self):
        chats, results = Chats(self.db, clock=lambda: 10.0), Results(self.db)
        self.assertEqual([chats.talk(c) for c in ("old-a", "old-b")], [("old-a", 1), ("old-b", 1)])
        with self.db.tx() as c:
            saved = [tuple(r) for r in c.execute("SELECT id, case_id, talk FROM chats ORDER BY created_at")]
        self.assertEqual(saved, [("old-a", "old-a", 1), ("old-b", "old-b", 1)])
        new, _ = chats.receive("whatsapp", WHO, "hello again")
        self.assertEqual(chats.talk(new), ("old-b", 2))
        rows = Log(self.db, SALES).query()
        self.assertEqual([(r["case_id"], r["talk"]) for r in rows], [("old-a", None), ("old-b", None)])
        self.assertEqual([r["outcome"] for r in results.for_chat("old-b")], ["replied"])
        results.record(new, "replied", step=1, stage="asking", at=11.0)
        self.assertEqual(list(Log(self.db, SALES).window(0, 20)), ["old-a", "old-b", "old-b talk 2"])

    def test_results_on_a_database_whose_chats_have_no_talks_name_the_chat_itself(self):
        self.assertEqual(Results(self.db).talk_of("old-a"), ("old-a", None))


class Practice(Base):
    def test_the_arena_reads_a_later_talk_as_the_agents_chat_and_by_its_own_result(self):
        first, _ = self.turn()
        self.order(first, "#1001")
        self.close_quiet()
        second, _ = self.turn("back again")
        self.close_quiet()
        self.assertEqual(grow.decided(self.db, SALES, first, self.now + 1), grow.label_mod.WON)
        self.assertEqual(grow.decided(self.db, SALES, second, self.now + 1), grow.label_mod.LOST)
        ids = [c[0] for c in grow.real_chats(self.db, T0 - 1, self.now + 1, agent=SALES.agent, own=False)]
        self.assertEqual(ids, [first, second])


if __name__ == "__main__":
    unittest.main()
