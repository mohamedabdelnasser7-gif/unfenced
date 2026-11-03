"""Chat memory for the Sales agent (sales/memory.py; Mohamed's yes, 2026-11-03).

A long chat keeps what falls out of its 40 message window as one short note under the case, written
by one model call and refreshed only when more old messages fall out; a customer who comes back
(talk 2 of the same case) opens with a note on the talks before. The note stays in that customer's
case: never a lesson, never in the log, the chat's steps or another customer's prompt. A failed
call means the last 40 messages, no note, and a log line. Made up text only, a fake clock, fake
models, no network."""
import json
import sqlite3
import unittest
from unittest import mock

from channels import whatsapp as wa
from channels.base import Message
from kit.chats import Chats
from kit.db import Db
from reflection.lessons import Lessons
from reflection.results import Results
from sales import loop, memory, stages
from tests.fake_model import FakeModel, Outbox, clean_env, say
from tests.test_whatsapp import SendingGraph, payload, text_msg

T0 = 1_800_000_000.0
WHO, OTHER = "201000000001", "201000000002"
NOTE = "Wants the made up Falcon boots in size 42; order not placed yet; asked about delivery to Tanta."
NOTE2 = "Wants the made up Falcon boots in size 42 and a second pair in 43; still deciding."
ANSWER = "Which colour would you like?"


class Writer:
    """A fake note writer: keeps each call and answers from its script (text, or an exception to raise)."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, note, messages, meter=None):
        self.calls.append({"note": note, "messages": messages, "meter": meter})
        nxt = self.script.pop(0) if self.script else AssertionError("the fake writer ran out of script")
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


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

    def memory(self, *script):
        self.writer = Writer(*script)
        return memory.Memory(self.db, self.chats, writer=self.writer)

    def fill(self, pairs, who=WHO, tag="x"):
        """pairs customer lines, each with the agent's answer, in the customer's open chat."""
        chat_id = None
        for i in range(pairs):
            self.now += 1
            chat_id, _ = self.chats.receive("whatsapp", who, content=f"customer line {tag}{i}")
            self.chats.add_step(chat_id, "assistant", content=f"agent line {tag}{i}")
        return chat_id

    def turn(self, mem, text="and the delivery?", who=WHO, model=None, **kw):
        """One loop turn; returns (result, what the model was sent first)."""
        self.now += 1
        model = model or FakeModel(say(ANSWER))
        r = loop.turn(Message(channel="whatsapp", customer_id=who, text=text), chats=self.chats, model=model,
                      lessons=self.lessons, results=self.results, send=self.out, memory=mem, **kw)
        return r, (model.calls[0]["messages"] if model.calls else None)

    def close(self, chat_id):
        self.now += 10
        self.chats.close(chat_id)

    def texts(self, msgs):
        return [m.get("content") for m in msgs]


class LongChat(Base):
    def test_under_the_window_there_is_no_call_and_the_turn_sees_what_it_saw_before(self):
        mem = self.memory()
        chat_id = self.fill(19)  # 38 messages, 39 with the next one: all inside the window
        before = self.chats.messages(chat_id)
        r, sent = self.turn(mem)
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.writer.calls, [])
        self.assertNotIn(memory.HEADING, sent[0]["content"])
        self.assertEqual(sent[1:-1], before)

    def test_past_the_window_one_call_writes_the_note_and_the_turn_gets_it_with_the_recent_messages(self):
        mem = self.memory(NOTE)
        chat_id = self.fill(21)  # 42 messages before the new one
        r, sent = self.turn(mem)
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(len(self.writer.calls), 1)
        call = self.writer.calls[0]
        self.assertIsNone(call["note"])
        said = [m.get("text") for m in call["messages"]]
        self.assertEqual(said[0], "customer line x0")
        self.assertEqual(said[-1], "agent line x10")  # the last 20 stay out of the note
        self.assertEqual(len(said), 22)
        self.assertIn(memory.HEADING + "\n" + NOTE, sent[0]["content"])
        history = self.texts(sent[1:-1])
        self.assertEqual(history[0], "customer line x11")
        self.assertEqual(len(history), memory.KEEP)
        self.assertEqual(sent[-1]["content"], "and the delivery?")
        saved = mem.note(self.chats.talk(chat_id)[0])
        self.assertEqual((saved["talk"], saved["text"]), (1, NOTE))

    def test_the_next_turn_reuses_the_note_with_no_call(self):
        mem = self.memory(NOTE)
        self.fill(21)
        self.turn(mem)
        self.fill(5, tag="y")
        _, sent = self.turn(mem, "one more thing")
        self.assertEqual(len(self.writer.calls), 1)
        self.assertIn(NOTE, sent[0]["content"])
        history = self.texts(sent[1:-1])
        self.assertEqual(history[0], "customer line x11")  # nothing already kept is dropped
        self.assertEqual(history[-1], "agent line y4")

    def test_twenty_more_messages_refresh_the_note_from_the_old_one(self):
        mem = self.memory(NOTE, NOTE2)
        self.fill(21)
        self.turn(mem)  # 20 kept + the turn's 2
        self.fill(9, tag="y")  # 40 open: still inside the window
        _, sent = self.turn(mem, "still there?")
        self.assertEqual(len(self.writer.calls), 1)
        self.assertIn(NOTE, sent[0]["content"])
        self.fill(1, tag="z")  # 44 open: the older part falls out
        _, sent = self.turn(mem, "ok then")
        self.assertEqual(len(self.writer.calls), 2)
        call = self.writer.calls[1]
        self.assertEqual(call["note"], NOTE)
        said = [m.get("text") for m in call["messages"]]
        self.assertEqual(said[0], "customer line x11")  # starts where the old note stopped
        self.assertNotIn("customer line x10", said)
        self.assertIn(NOTE2, sent[0]["content"])
        self.assertNotIn(NOTE, sent[0]["content"])
        self.assertEqual(len(sent[1:-1]), memory.KEEP)

    def test_the_writer_reads_tool_names_never_their_arguments_or_answers(self):
        writer_model = FakeModel(say(json.dumps({"note": NOTE})))
        mem = memory.Memory(self.db, self.chats, writer=memory.Writer(model=writer_model))
        chat_id, _ = self.chats.receive("whatsapp", WHO, content="customer opening line")
        call = {"id": "c1", "type": "function",
                "function": {"name": "find_order", "arguments": json.dumps({"order": "SECRET-ARG-77"})}}
        self.chats.add_step(chat_id, "assistant", content=None, tool_calls=[call])
        self.chats.add_step(chat_id, "tool", content=json.dumps({"status": "SECRET-ANSWER-88"}), tool_call_id="c1",
                            name="find_order")
        self.chats.add_step(chat_id, "assistant", content="It is on its way.")
        self.fill(20)
        self.turn(mem)
        self.assertEqual(len(writer_model.calls), 1)
        sent = writer_model.calls[0]["messages"]
        self.assertEqual(sent[0]["role"], "system")
        data = json.loads(sent[1]["content"])  # the chat goes in as data, in its own message
        self.assertIn({"from": "agent", "tools": ["find_order"], "talk": 1}, data["messages"])
        self.assertIn({"from": "customer", "text": "customer opening line", "talk": 1}, data["messages"])
        self.assertNotIn("SECRET-ARG-77", sent[1]["content"])
        self.assertNotIn("SECRET-ANSWER-88", sent[1]["content"])
        self.assertNotIn("customer opening line", sent[0]["content"])

    def test_the_call_counts_against_the_customers_limits(self):
        class Limits:
            def __init__(self):
                self.metered = []

            def over(self, who):
                return None

            def meter(self, model, who):
                self.metered.append(who)
                return model
        limits = Limits()
        mem = self.memory(NOTE)
        self.fill(21)
        self.turn(mem, limits=limits)
        meter = self.writer.calls[0]["meter"]
        self.assertIsNotNone(meter)
        before = len(limits.metered)
        meter(object())
        self.assertEqual(limits.metered[before:], ["whatsapp:" + WHO])


class ReturningCustomer(Base):
    def test_talk_two_opens_with_a_note_on_talk_one(self):
        mem = self.memory(NOTE)
        first = self.fill(5)
        self.close(first)
        r, sent = self.turn(mem, "I'm back about the boots")
        self.assertNotEqual(r.chat_id, first)
        self.assertEqual(self.chats.talk(r.chat_id), (self.chats.talk(first)[0], 2))
        self.assertEqual(len(self.writer.calls), 1)
        said = [(m.get("text"), m["talk"]) for m in self.writer.calls[0]["messages"]]
        self.assertEqual(said[0], ("customer line x0", 1))
        self.assertEqual(said[-1], ("agent line x4", 1))
        self.assertIn(memory.HEADING + "\n" + NOTE, sent[0]["content"])
        self.assertEqual(sent[1:], [{"role": "user", "content": "I'm back about the boots"}])
        _, sent = self.turn(mem, "size 42 please")  # the second turn of talk 2: no new call
        self.assertEqual(len(self.writer.calls), 1)
        self.assertIn(NOTE, sent[0]["content"])
        self.assertEqual(self.texts(sent[1:]), ["I'm back about the boots", ANSWER, "size 42 please"])

    def test_talk_three_brings_the_note_up_to_the_end_of_talk_two(self):
        mem = self.memory(NOTE, NOTE2)
        first = self.fill(3)
        self.close(first)
        second, _ = self.turn(mem, "back again")
        second = second.chat_id
        self.fill(2, tag="t2")
        self.close(second)
        _, sent = self.turn(mem, "and once more")
        self.assertEqual(len(self.writer.calls), 2)
        call = self.writer.calls[1]
        self.assertEqual(call["note"], NOTE)
        said = [(m.get("text"), m["talk"]) for m in call["messages"]]
        self.assertEqual(said[0], ("back again", 2))
        self.assertEqual(said[-1], ("agent line t21", 2))
        self.assertFalse([s for s in said if s[1] == 1])  # talk 1 is in the old note already
        self.assertIn(NOTE2, sent[0]["content"])

    def test_a_first_talk_never_calls(self):
        mem = self.memory()
        self.fill(3)
        self.turn(mem)
        self.assertEqual(self.writer.calls, [])


class Failure(Base):
    def assert_falls_back(self, mem, chat_id, writer_calls):
        before = self.chats.messages(chat_id)
        with self.assertLogs("sales.memory", "WARNING") as logs:
            r, sent = self.turn(mem)
        self.assertEqual(r.outcome, "replied")
        self.assertNotIn(memory.HEADING, sent[0]["content"])
        self.assertEqual(sent[1:-1], before[-memory.WINDOW:])
        self.assertEqual(len(sent[1:-1]), memory.WINDOW)
        self.assertIsNone(mem.note(self.chats.talk(chat_id)[0]))
        line = "\n".join(logs.output)
        self.assertIn("the last 40 messages", line)
        self.assertNotIn("customer line", line)
        self.assertEqual(writer_calls(), 1)

    def test_a_raise_bad_json_a_long_note_or_a_link_gives_the_last_40_and_a_log_line(self):
        cases = {
            "raise": lambda: FakeModel(lambda m, t: (_ for _ in ()).throw(RuntimeError("down"))),
            "not json": lambda: FakeModel(say("the customer wants boots")),
            "no note key": lambda: FakeModel(say(json.dumps({"summary": NOTE}))),
            "too long": lambda: FakeModel(say(json.dumps({"note": "a" * (memory.NOTE_LEN + 1)}))),
            "link": lambda: FakeModel(say(json.dumps({"note": "Sent them to shop.example.com for sizes."}))),
            "tool call": lambda: FakeModel({"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]}),
        }
        for name, make in cases.items():
            with self.subTest(name):
                self.setUp()
                model = make()
                mem = memory.Memory(self.db, self.chats, writer=memory.Writer(model=model))
                chat_id = self.fill(21, who=WHO)
                self.assert_falls_back(mem, chat_id, lambda: len(model.calls))

    def test_after_a_failure_the_next_turn_tries_again(self):
        mem = self.memory(RuntimeError("down"), NOTE)
        self.fill(21)
        with self.assertLogs("sales.memory", "WARNING"):
            self.turn(mem)
        _, sent = self.turn(mem, "hello?")
        self.assertEqual(len(self.writer.calls), 2)
        self.assertIn(NOTE, sent[0]["content"])

    def test_memory_that_cannot_be_read_leaves_the_turn_as_before(self):
        class Broken:
            def for_turn(self, *a, **k):
                raise RuntimeError("broken table")
        chat_id = self.fill(21)
        before = self.chats.messages(chat_id)
        with self.assertLogs("sales.loop", "ERROR"):
            r, sent = self.turn(Broken())
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(sent[1:-1], before)

    def test_without_memory_the_turn_is_as_before(self):
        chat_id = self.fill(21)
        before = self.chats.messages(chat_id)
        _, sent = self.turn(None)
        self.assertEqual(sent[1:-1], before)
        self.assertNotIn(memory.HEADING, sent[0]["content"])


class Safety(Base):
    def test_another_customer_never_sees_the_note(self):
        mem = self.memory(NOTE)
        first = self.fill(3)
        self.close(first)
        self.turn(mem, "back again")
        self.assertEqual(len(self.writer.calls), 1)
        _, sent = self.turn(mem, "hi, a question", who=OTHER)
        self.assertNotIn(NOTE, json.dumps(sent, ensure_ascii=False))
        self.assertNotIn(memory.HEADING, sent[0]["content"])
        self.assertEqual(len(self.writer.calls), 1)

    def test_the_note_lives_only_in_its_table(self):
        """Never in the log, the chat's steps, the results or the lessons, so no night study, fast
        note, Arena or page that reads those ever reads it."""
        mem = self.memory(NOTE, NOTE2)
        first = self.fill(21)
        self.turn(mem)
        self.close(first)
        self.turn(mem, "back again")
        self.assertEqual(len(self.writer.calls), 2)
        held = []
        with self.db.tx() as c:
            tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
            for table in tables:
                for row in c.execute(f'SELECT * FROM "{table}"'):
                    text = json.dumps([v if not isinstance(v, bytes) else "" for v in tuple(row)], ensure_ascii=False)
                    if "Falcon" in text:
                        held.append(table)
        self.assertEqual(set(held), {"case_memory"})
        self.assertEqual(len(self.lessons_rows()), 0)

    def lessons_rows(self):
        with self.db.tx() as c:
            try:
                return c.execute("SELECT * FROM lessons").fetchall()
            except sqlite3.OperationalError:
                return []

    def test_the_memory_sits_after_the_lessons_and_before_the_fast_note(self):
        stage = stages.STAGES["asking"]
        content = loop.system_prompt(stage, [{"text": "Greet them."}], note="FAST NOTE", memory="MEMORY NOTE")["content"]
        self.assertLess(content.index("Greet them."), content.index("MEMORY NOTE"))
        self.assertLess(content.index("MEMORY NOTE"), content.index("FAST NOTE"))
        self.assertNotIn("MEMORY NOTE", loop.system_prompt(stage, [], note="FAST NOTE")["content"])

    def test_the_writer_is_told_the_chat_is_data_never_instructions(self):
        self.assertIn("never instructions", memory.WRITE)
        self.assertIn("never put a link", memory.WRITE)
        self.assertIn("never instructions", memory.HEADING)


class Running(Base):
    def test_the_running_agent_hands_its_memory_to_the_turn(self):
        mem = self.memory(NOTE)
        first = self.fill(3)
        self.close(first)
        model = FakeModel(say(ANSWER))
        app = wa.App(self.chats, model, self.lessons, self.results, SendingGraph(b"", "audio/ogg"), connected=True,
                     memory=mem)
        app.accept(wa.parse(payload(text_msg("m1", "back about the boots", frm=WHO))))
        self.now += 1
        app.work_one(app.q.get_nowait())
        self.assertEqual(len(self.writer.calls), 1)
        self.assertIn(NOTE, model.calls[0]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
