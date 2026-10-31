"""The handoff note and the team member's replies to it, on a fake Graph and a scripted model.

All numbers and texts are made up.
"""
import io
import json
import logging
import sqlite3
import unittest
import urllib.error
from unittest import mock

from channels import whatsapp as wa
from channels.base import Image, Message
from sales import loop
from kit import limits as limits_mod
from kit.chats import PERSON, Chats
from kit.db import Db
from kit.limits import Limits
from kit.model import ModelError
from kit.tools import handoff, voice_note
from reflection.lessons import Lessons
from reflection.results import Results
from tests.fake_model import FakeModel, call, clean_env, say

CUSTOMER = "201111111111"
OTHER_CUSTOMER = "201222222222"
OPERATOR = "201000000001"
STRANGER = "201333333333"
JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 4
SUMMARY = "العميل عايز يكلم حد من الفريق عن الأوردر"
SMILE, DASH, RLM = chr(0x1F60A), chr(0x2014), chr(0x200F)
BLOCKED = "349 جنيه بس " + SMILE + " " + DASH + " تمام"  # the send check would refuse this; a person's words go as typed


def down(messages, tools_sent):
    raise ModelError("Baseten call failed: URLError")


class Outbox:
    """Stands in for Graph.send: keeps every (to, text) and answers like WhatsApp, with a message id."""

    def __init__(self):
        self.sent, self.fail = [], {}

    def __call__(self, to, text):
        if to in self.fail:
            raise self.fail[to]
        self.sent.append((to, text))
        return {"messaging_product": "whatsapp", "contacts": [{"input": to, "wa_id": to}],
                "messages": [{"id": f"wamid.out.{len(self.sent)}"}]}

    def to(self, who):
        return [t for w, t in self.sent if w == who]

    def ids_to(self, who):
        return [f"wamid.out.{i}" for i, (w, _) in enumerate(self.sent, 1) if w == who]


class FakeGraph:
    """The Graph the App uses: sends through an Outbox, and never downloads in these tests unless told."""

    def __init__(self):
        self.out = Outbox()
        self.downloads = 0

    def send(self, to, text):
        return self.out(to, text)

    def download(self, media_id, max_bytes):
        self.downloads += 1
        raise AssertionError("nothing should be downloaded here")


def text_msg(mid, body, frm=CUSTOMER, quoted=None):
    m = {"from": frm, "id": mid, "timestamp": "1761600000", "type": "text", "text": {"body": body}}
    if quoted is not None:
        m["context"] = {"from": "201000000000", "id": quoted}
    return m


def image_msg(mid, frm=CUSTOMER, quoted=None):
    m = {"from": frm, "id": mid, "timestamp": "1761600000", "type": "image",
         "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "ده"}}
    if quoted is not None:
        m["context"] = {"from": "201000000000", "id": quoted}
    return m


def failed_status(sent_id, code=wa.WINDOW_CLOSED, status="failed"):
    st = {"id": sent_id, "status": status, "timestamp": "1761600100", "recipient_id": CUSTOMER}
    if status == "failed":
        st["errors"] = [{"code": code, "title": "Re-engagement message"}]
    return st


def payload(messages=(), statuses=(), pnid="111"):
    value = {"messaging_product": "whatsapp",
             "metadata": {"display_phone_number": "201000000000", "phone_number_id": pnid}}
    if messages:
        value["messages"] = list(messages)
    if statuses:
        value["statuses"] = list(statuses)
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "1", "changes": [{"field": "messages", "value": value}]}]}


class NoteFormat(unittest.TestCase):
    """The note the team member gets: the summary, then the waiting messages word for word."""

    def setUp(self):
        clean_env(self, OPERATOR_WHATSAPP=OPERATOR)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.lessons, self.results = Chats(self.db), Lessons(self.db), Results(self.db)
        self.out = Outbox()

    def turn(self, model, text="", **kw):
        msg = Message(channel="whatsapp", customer_id=CUSTOMER, text=text, **kw)
        return loop.turn(msg, chats=self.chats, model=model, lessons=self.lessons, results=self.results, send=self.out)

    def note(self):
        parts = self.out.to(OPERATOR)
        self.assertEqual(len(parts), 1)
        return parts[0]

    def test_summary_then_every_message_since_the_last_reply_word_for_word(self):
        cid = self.chats.open("whatsapp", CUSTOMER)
        self.chats.add_step(cid, "user", content="سؤال قديم اتجاوب")
        self.chats.add_step(cid, "assistant", content="رد قديم")
        self.chats.add_step(cid, "user", content="فين الأوردر بتاعي؟\nبقالي أسبوع")
        self.chats.add_step(cid, "user", content="*حد يرد* please")
        model = FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY))
        r = self.turn(model, "  عايز اكلم حد دلوقتي  ")
        self.assertEqual(r.outcome, "handed_off")
        note = self.note()
        self.assertEqual(note, "\n".join([
            handoff.NOTE_HEAD, f"العميل: {CUSTOMER}", handoff.SUMMARY_LABEL, SUMMARY, "",
            handoff.WAITING_LABEL,
            "فين الأوردر بتاعي؟\nبقالي أسبوع\n\n*حد يرد* please\n\n  عايز اكلم حد دلوقتي  ",
            "", handoff.HOW_TO_REPLY]))
        self.assertNotIn("سؤال قديم", note)
        self.assertLess(note.index(handoff.SUMMARY_LABEL), note.index(handoff.WAITING_LABEL))

    def test_a_person_reply_also_counts_as_the_last_reply(self):
        cid = self.chats.open("whatsapp", CUSTOMER)
        self.chats.add_step(cid, "user", content="اتجاوب من حد")
        self.chats.add_person_reply(cid, "رد من الفريق")
        self.turn(FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY)), "تاني لو سمحت")
        note = self.note()
        self.assertIn("تاني لو سمحت", note)
        self.assertNotIn("اتجاوب من حد", note)

    def test_tool_call_words_are_not_a_reply(self):
        cid = self.chats.open("whatsapp", CUSTOMER)
        self.chats.add_step(cid, "user", content="أول رسالة")
        self.chats.add_step(cid, "assistant", content="let me check", tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": "store", "arguments": "{}"}}])
        self.chats.add_step(cid, "tool", content='{"ok": true}', tool_call_id="c1", name="store")
        self.turn(FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY)), "تانية")
        self.assertIn("أول رسالة\n\nتانية", self.note())

    def test_voice_notes_show_as_their_transcript(self):
        cid = self.chats.open("whatsapp", CUSTOMER)
        # an earlier voice note the agent heard, then never answered (the model went down)
        self.chats.add_step(cid, "user", media=[{"kind": "audio", "sha256": "a" * 64, "mime": "audio/ogg"}])
        self.chats.add_step(cid, "assistant", tool_calls=[
            {"id": "v1", "type": "function", "function": {"name": "voice_note", "arguments": "{}"}}])
        self.chats.add_step(cid, "tool", content=json.dumps({"ok": True, "text": "عايز مقاس ٤٣"}, ensure_ascii=False),
                            tool_call_id="v1", name="voice_note")
        model = FakeModel(call("voice_note"), say("لو سمحت حد يكلمني"),
                          call("handoff", reason="customer wants a person"), say(SUMMARY))
        with mock.patch.object(voice_note, "to_wav", return_value=b"RIFF0000WAVE"):
            self.turn(model, "", audio=b"OggS fake", audio_mime="audio/ogg; codecs=opus")
        self.assertIn(f"{handoff.VOICE} عايز مقاس ٤٣\n\n{handoff.VOICE} لو سمحت حد يكلمني", self.note())

    def test_a_voice_note_not_heard_yet_is_heard_for_the_note(self):
        model = FakeModel(call("handoff", reason="customer wants a person"), say("عايز ارجع الأوردر"), say(SUMMARY))
        with mock.patch.object(voice_note, "to_wav", return_value=b"RIFF0000WAVE") as conv:
            self.turn(model, "", audio=b"OggS fake", audio_mime="audio/ogg; codecs=opus")
        conv.assert_called_once()
        self.assertIn(f"{handoff.VOICE} عايز ارجع الأوردر", self.note())

    def test_a_voice_note_that_cannot_be_heard_says_so(self):
        cid = self.chats.open("whatsapp", CUSTOMER)
        self.chats.add_step(cid, "user", media=[{"kind": "audio", "sha256": "b" * 64, "mime": "audio/ogg"}])
        model = FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY))
        self.turn(model, "hello?")
        self.assertIn(f"{handoff.VOICE_NOT_HEARD}\n\nhello?", self.note())

    def test_photos_show_as_a_marker(self):
        model = FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY))
        self.turn(model, "ده اللي وصلني", images=[Image(JPEG, "image/jpeg")])
        self.assertIn(f"{handoff.PHOTO} ده اللي وصلني", self.note())

    def test_a_photo_that_could_not_be_opened_still_shows(self):
        # the fixed "send it again" line goes out first in this turn; the message still counts
        model = FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY))
        self.turn(model, "المقاس غلط", rejected_images=1)
        self.assertIn(f"{handoff.WAITING_LABEL}\n{handoff.PHOTO} المقاس غلط", self.note())

    def test_note_part_ids_are_saved_with_the_chat(self):
        r = self.turn(FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY)), "عايز حد")
        (note_id,) = self.out.ids_to(OPERATOR)
        self.assertEqual(self.chats.note_chat(note_id, OPERATOR), r.chat_id)
        self.assertIsNone(self.chats.note_chat(note_id, STRANGER))
        self.assertIsNone(self.chats.note_chat(self.out.ids_to(CUSTOMER)[0], OPERATOR))  # not a note

    def test_a_note_with_no_id_cannot_be_answered_and_says_so_in_the_log(self):
        out = []
        r = None
        with self.assertLogs("kit.tools.handoff", "WARNING") as logs:
            msg = Message(channel="whatsapp", customer_id=CUSTOMER, text="عايز حد")
            r = loop.turn(msg, chats=self.chats, model=FakeModel(call("handoff", reason="x"), say(SUMMARY)),
                          lessons=self.lessons, results=self.results,
                          send=lambda to, text: out.append((to, text)) or {"ok": True})
        self.assertIn("no message id", "\n".join(logs.output))
        with self.db.tx() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM team_notes").fetchone()[0], 0)
        self.assertEqual(r.outcome, "handed_off")

    def test_a_long_note_is_split_and_every_part_can_be_answered(self):
        # Near WhatsApp's 4096 character cap for one text, so the note needs a second part (F2 caps it at 3).
        long_text = ("كلام كتير " * 380).strip() + "\n" + "سطر تاني " * 30
        r = self.turn(FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY)), long_text)
        parts = self.out.to(OPERATOR)
        self.assertGreater(len(parts), 1)
        for i, part in enumerate(parts, 1):
            self.assertLess(handoff.units(part), 4000)
            self.assertTrue(part.startswith(f"({i}/{len(parts)})\n"))
        joined = "".join(p.split("\n", 1)[1] for p in parts).replace("\n", "")
        self.assertIn(long_text.replace("\n", ""), joined)
        for note_id in self.out.ids_to(OPERATOR):
            self.assertEqual(self.chats.note_chat(note_id, OPERATOR), r.chat_id)


class Split(unittest.TestCase):
    def test_short_text_is_one_part_as_is(self):
        self.assertEqual(handoff.split("سطر\nسطر"), ["سطر\nسطر"])

    def test_one_long_line_and_emoji_count_in_utf16_units(self):
        text = chr(0x1F600) * 2500 + "\n" + "x" * 9000
        parts = handoff.split(text)
        self.assertTrue(all(handoff.units(p) < 4000 for p in parts))
        self.assertEqual("".join(p.split("\n", 1)[1] for p in parts).replace("\n", ""), text.replace("\n", ""))
        self.assertEqual(handoff.units(chr(0x1F600)), 2)

    def test_short_lines_pack_with_room_for_the_part_number(self):
        parts = handoff.split("\n".join(["y" * 99] * 60))
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(handoff.units(p) < 4000 for p in parts), [handoff.units(p) for p in parts])

    def test_under_the_limit_exactly(self):
        self.assertEqual(handoff.split("x" * 3999), ["x" * 3999])
        self.assertEqual(len(handoff.split("x" * 4000)), 2)


class Relay(unittest.TestCase):
    """A team member's reply to the note, through App.accept and work_one like the worker."""

    def setUp(self):
        clean_env(self, OPERATOR_WHATSAPP=OPERATOR)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.results = Chats(self.db), Results(self.db)
        self.graph = FakeGraph()
        self.out = self.graph.out

    def app(self, model=None, limits=None, **kw):
        return wa.App(self.chats, model or FakeModel(), Lessons(self.db), self.results, self.graph, limits=limits,
                      **kw)

    def run_one(self, payload_, model=None, limits=None, **kw):
        app = self.app(model, limits, **kw)
        app.accept(wa.parse(payload_, "111"))
        return app.work_one(app.q.get_nowait())

    def handed_off(self, customer=CUSTOMER, mid="c1"):
        """A customer asks for a person; the model hands off. Returns (chat_id, the note's message id)."""
        model = FakeModel(call("handoff", reason="customer wants a person"), say(SUMMARY))
        r = self.run_one(payload([text_msg(mid, "عايز اكلم حد", frm=customer)]), model)
        self.assertEqual((r.outcome, self.chats.stage(r.chat_id)), ("handed_off", "with_person"))
        return r.chat_id, self.out.ids_to(OPERATOR)[-1]

    def outcomes(self, chat_id):
        return [r["outcome"] for r in self.results.for_chat(chat_id)]

    def test_a_new_customer_message_goes_on_to_the_team_and_a_reply_to_it_reaches_the_customer(self):
        cid, _ = self.handed_off()
        model = mock.Mock(spec=["chat"])
        model.chat.side_effect = AssertionError("the model was called")
        r = self.run_one(payload([text_msg("c2", "لسه مستني، الأوردر هيوصل امتى؟")]), model)
        self.assertEqual((r.outcome, r.chat_id), ("waiting", cid))
        note = self.out.to(OPERATOR)[-1]
        self.assertTrue(note.startswith(handoff.NEW_MESSAGE_HEAD))
        self.assertIn("لسه مستني، الأوردر هيوصل امتى؟", note)
        self.assertIn(CUSTOMER, note)
        r = self.run_one(payload([text_msg("t1", "هيوصل بكرة", frm=OPERATOR, quoted=self.out.ids_to(OPERATOR)[-1])]))
        self.assertEqual((r.outcome, self.out.sent[-1]), ("person_replied", (CUSTOMER, "هيوصل بكرة")))

    def test_only_the_new_message_goes_on_after_a_person_replied(self):
        cid, note = self.handed_off()
        self.run_one(payload([text_msg("c2", "طيب والمقاس؟")]))
        self.run_one(payload([text_msg("t1", "هنشوف المقاس", frm=OPERATOR, quoted=note)]))
        self.run_one(payload([text_msg("c3", "تمام شكرا")]))
        last = self.out.to(OPERATOR)[-1]
        self.assertIn("تمام شكرا", last)
        self.assertNotIn("طيب والمقاس؟", last)

    def test_two_messages_in_a_row_each_go_on_once(self):
        self.handed_off()
        self.run_one(payload([text_msg("c2", "اول سؤال")]))
        self.run_one(payload([text_msg("c3", "تاني سؤال")]))
        first, second = self.out.to(OPERATOR)[-2:]
        self.assertIn("اول سؤال", first)
        self.assertIn("تاني سؤال", second)
        self.assertNotIn("اول سؤال", second)

    def test_a_customer_over_a_limit_does_not_reach_the_team_phone(self):
        cid, _ = self.handed_off()
        limits = Limits(self.db, per_customer=2, window=600, daily=100)
        for i in range(5):
            self.run_one(payload([text_msg(f"c{i + 2}", f"رسالة رقم {i}")]), limits=limits)
        passed = [n for n in self.out.to(OPERATOR) if n.startswith(handoff.NEW_MESSAGE_HEAD)]
        self.assertEqual(len(passed), 2)
        self.assertEqual(len([s for s in self.chats.steps(cid) if s["role"] == "user"]), 6)  # all still saved

    def test_without_an_operator_number_nothing_goes_on(self):
        cid, _ = self.handed_off()
        clean_env(self)
        before = len(self.out.sent)
        r = self.run_one(payload([text_msg("c2", "في حد؟")]))
        self.assertEqual((r.outcome, self.out.sent[before:]), ("waiting", []))

    def test_reply_goes_to_the_customer_exactly_as_typed(self):
        cid, note = self.handed_off()
        typed = "  أهلا يا فندم، *الأوردر* هيوصل بكرة " + SMILE + "\nلو في أي حاجة كلمنا  "
        before = len(self.out.sent)
        r = self.run_one(payload([text_msg("t1", typed, frm=OPERATOR, quoted=note)]))
        self.assertEqual(r.outcome, "person_replied")
        self.assertEqual(self.out.sent[before:], [(CUSTOMER, typed)])
        last = self.chats.steps(cid)[-1]
        self.assertEqual((last["role"], last["name"], last["content"]), ("assistant", PERSON, typed))
        row = self.results.for_chat(cid)[-1]
        self.assertEqual((row["outcome"], row["step"], row["stage"]), ("person_replied", last["n"], "with_person"))
        self.assertEqual(self.chats.pending(), [])
        self.assertEqual(self.chats.stage(cid), "with_person")  # the agent keeps waiting
        self.assertEqual(self.chats.reply_step(self.out.ids_to(CUSTOMER)[-1]), (cid, last["n"]))

    def test_no_model_call_no_send_check_no_limit_on_a_relay(self):
        cid, note = self.handed_off()
        limits = Limits(self.db, per_customer=1, window=600, daily=100)
        limits.take(limits_mod.key("whatsapp", OPERATOR))  # the operator is over a limit from testing
        with self.db.tx() as c:
            calls_before = c.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
        model = mock.Mock(spec=["chat"])
        model.chat.side_effect = AssertionError("the model was called")
        with mock.patch("kit.send_check.check", side_effect=AssertionError("send_check ran")) as checked, \
                mock.patch.object(loop, "turn", side_effect=AssertionError("a turn ran")) as turned:
            r = self.run_one(payload([text_msg("t1", BLOCKED, frm=OPERATOR, quoted=note)]),
                             model, limits)
        self.assertEqual((r.outcome, self.out.sent[-1]), ("person_replied", (CUSTOMER, BLOCKED)))
        model.chat.assert_not_called()
        checked.assert_not_called()
        turned.assert_not_called()
        with self.db.tx() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0], calls_before)
        self.assertEqual(self.out.to(OPERATOR)[1:], [])  # no limit line, nothing else to the operator

    def test_a_quote_of_any_other_message_is_a_customer_message(self):
        cid, note = self.handed_off()
        customer_line = self.out.ids_to(CUSTOMER)[-1]  # the "taking over" line, not a note
        before = len(self.out.sent)
        for i, quoted in enumerate(("wamid.unknown", customer_line, "")):
            with self.subTest(quoted=quoted):
                r = self.run_one(payload([text_msg(f"t{i}", "hello there, a question", frm=OPERATOR, quoted=quoted)]),
                                 FakeModel(say("Ask me anything.")))
                self.assertEqual(r.outcome, "replied")
                self.assertNotEqual(r.chat_id, cid)
        self.assertEqual(self.out.sent[before:], [(OPERATOR, "Ask me anything.")] * 3)
        self.assertEqual(self.outcomes(cid), ["handed_off"])

    def test_operator_without_a_quote_is_a_customer(self):
        cid, _ = self.handed_off()
        r = self.run_one(payload([text_msg("t1", "hello there, a question", frm=OPERATOR)]),
                         FakeModel(say("Ask me anything.")))
        self.assertEqual((r.outcome, self.out.sent[-1]), ("replied", (OPERATOR, "Ask me anything.")))
        self.assertEqual(self.chats.get(r.chat_id)["customer_id"], OPERATOR)
        self.assertNotIn(PERSON, [s["name"] for s in self.chats.steps(cid)])

    def test_another_number_quoting_a_note_is_not_a_team_reply(self):
        cid, note = self.handed_off()
        before = len(self.out.sent)
        r = self.run_one(payload([text_msg("t1", "hello there, a question", frm=STRANGER, quoted=note)]),
                         FakeModel(say("Ask me anything.")))
        self.assertEqual((r.outcome, self.out.sent[before:]), ("replied", [(STRANGER, "Ask me anything.")]))
        self.assertEqual(self.outcomes(cid), ["handed_off"])

    def test_a_note_only_answers_for_the_number_it_went_to(self):
        cid, note = self.handed_off()
        # the operator number changed since the note went out: the new number cannot use it
        r = self.run_one(payload([text_msg("t1", "hello there, a question", frm=STRANGER, quoted=note)]),
                         FakeModel(say("Ask me anything.")), operator=STRANGER)
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.outcomes(cid), ["handed_off"])

    def test_only_the_operator_number_can_use_a_note(self):
        cid, _ = self.handed_off()
        self.chats.save_note("wamid.old", cid, STRANGER)  # sent when STRANGER was the operator
        r = self.run_one(payload([text_msg("t1", "hello there, a question", frm=STRANGER, quoted="wamid.old")]),
                         FakeModel(say("Ask me anything.")))
        self.assertEqual((r.outcome, self.out.sent[-1]), ("replied", (STRANGER, "Ask me anything.")))
        self.assertEqual(self.outcomes(cid), ["handed_off"])

    def test_a_note_for_a_chat_on_another_channel_is_not_answered(self):
        cid = self.chats.open("instagram", CUSTOMER)
        self.chats.save_note("wamid.ig", cid, OPERATOR)
        with self.assertLogs("channels.whatsapp", "WARNING"):
            r = self.run_one(payload([text_msg("t1", "ردنا", frm=OPERATOR, quoted="wamid.ig")]))
        self.assertEqual((r.outcome, self.out.sent), ("ignored", []))
        self.assertEqual(self.chats.pending(), [])

    def test_a_reply_reaches_only_its_own_chat(self):
        first, note_a = self.handed_off(CUSTOMER, "c1")
        second, note_b = self.handed_off(OTHER_CUSTOMER, "c2")
        before = len(self.out.sent)
        self.run_one(payload([text_msg("t1", "ردك يا أستاذ", frm=OPERATOR, quoted=note_b)]))
        self.assertEqual(self.out.sent[before:], [(OTHER_CUSTOMER, "ردك يا أستاذ")])
        self.assertEqual(self.outcomes(first), ["handed_off"])
        self.assertEqual(self.outcomes(second), ["handed_off", "person_replied"])

    def test_hand_back_words(self):
        for word in ("رجّع", "رجع", " رجع ", "رجَّع", "rag3", "RAG3", "Back", " b a c k\n", RLM + "رجع"):
            with self.subTest(word=word):
                self.assertTrue(wa.is_hand_back(word))
        for other in ("رجع الفلوس", "back please", "رجعت", "", "bac", "backk", "رجع."):
            with self.subTest(other=other):
                self.assertFalse(wa.is_hand_back(other))

    def test_hand_back_resets_the_chat_and_tells_only_the_team(self):
        cid, note = self.handed_off()
        self.chats.add_failed_check(cid, "x")
        self.chats.add_model_error(cid, "y")
        before = len(self.out.sent)
        r = self.run_one(payload([text_msg("t1", " رجّع ", frm=OPERATOR, quoted=note)]))
        self.assertEqual(r.outcome, "handed_back")
        self.assertEqual((self.chats.stage(cid), self.chats.failed_checks(cid), self.chats.model_errors(cid)),
                         ("asking", 0, 0))
        self.assertEqual(self.out.sent[before:], [(OPERATOR, wa.TEAM_LINES["handed_back"])])
        row = self.results.for_chat(cid)[-1]
        self.assertEqual((row["outcome"], row["stage"]), ("handed_back", "with_person"))
        self.assertEqual(self.chats.pending(), [])
        branched = self.chats.branch(cid, len(self.chats.steps(cid)))
        self.assertEqual((self.chats.stage(branched), self.chats.failed_checks(branched),
                          self.chats.model_errors(branched)), ("asking", 0, 0))
        # the agent answers this customer again
        r = self.run_one(payload([text_msg("c9", "hello there, a question")]), FakeModel(say("Ask me anything.")))
        self.assertEqual((r.chat_id, r.outcome, self.out.sent[-1]), (cid, "replied", (CUSTOMER, "Ask me anything.")))

    def test_after_a_hand_back_one_model_error_sends_the_line_not_a_handoff(self):
        line = loop.MODEL_DOWN["arabic"]
        with self.assertLogs(level="WARNING"):  # the loop's warnings and the handoff's failed summary
            r = self.run_one(payload([text_msg("c1", "عندكم جزم؟")]), FakeModel(down))
            self.assertEqual(r.outcome, "model_error")
            r = self.run_one(payload([text_msg("c2", "عندكم جزم؟")]), FakeModel(down, down))
        cid = r.chat_id
        self.assertEqual((r.outcome, self.chats.stage(cid)), ("handed_off", "with_person"))
        note = self.out.ids_to(OPERATOR)[-1]
        r = self.run_one(payload([text_msg("t1", "رجّع", frm=OPERATOR, quoted=note)]))
        self.assertEqual((r.outcome, self.chats.stage(cid)), ("handed_back", "asking"))
        with self.assertLogs("sales.loop", "WARNING"):
            r = self.run_one(payload([text_msg("c3", "عندكم جزم؟")]), FakeModel(down))
        self.assertEqual((r.chat_id, r.outcome, r.reply), (cid, "model_error", line))
        self.assertEqual((self.chats.stage(cid), self.chats.model_errors(cid)), ("asking", 1))
        self.assertEqual(self.out.sent[-1], (CUSTOMER, line))
        self.assertEqual(self.outcomes(cid)[-2:], ["handed_back", "model_error"])

    def crash(self, payload_):
        """Run the payload through App.work with work_one raising, as a bug in the turn would."""
        app = self.app()
        app.accept(wa.parse(payload_, "111"))
        app.q.put(None)
        with mock.patch.object(app, "work_one", side_effect=RuntimeError("a bug in the relay")), \
                self.assertLogs("channels.whatsapp", "ERROR"):
            app.work()  # returns at the None: no crash escapes

    def test_a_crashed_team_reply_tells_the_team_member_once(self):
        cid, note = self.handed_off()
        before = len(self.out.sent)
        self.crash(payload([text_msg("t1", "هيوصل بكرة", frm=OPERATOR, quoted=note)]))
        self.assertEqual(self.out.sent[before:], [(OPERATOR, wa.TEAM_LINES["unsure"])])
        self.assertEqual((self.chats.stage(cid), self.chats.model_errors(cid)), ("with_person", 0))
        self.assertEqual(self.chats.pending(), [])  # not tried again after a restart

    def test_a_team_reply_whose_chat_lookup_crashes_still_tells_the_team_member(self):
        cid, note = self.handed_off()
        before = len(self.out.sent)
        app = self.app()
        app.accept(wa.parse(payload([text_msg("t1", "رجّع", frm=OPERATOR, quoted=note)]), "111"))
        app.q.put(None)
        with mock.patch.object(self.chats, "note_chat", side_effect=sqlite3.OperationalError("database is locked")), \
                self.assertLogs("channels.whatsapp", "ERROR"):
            app.work()  # the real work_one: its team chat lookup crashes, and so does the one after
        self.assertEqual(self.out.sent[before:], [(OPERATOR, wa.TEAM_LINES["unsure"])])
        self.assertEqual(self.chats.stage(cid), "with_person")

    def test_a_crash_on_a_failed_status_sends_nothing(self):
        cid, note = self.handed_off()
        self.run_one(payload([text_msg("t1", "ردنا", frm=OPERATOR, quoted=note)]))
        before, steps = len(self.out.sent), len(self.chats.steps(cid))
        self.crash(payload(statuses=[failed_status(self.out.ids_to(CUSTOMER)[-1])]))
        self.assertEqual(self.out.sent[before:], [])
        self.assertEqual(len(self.chats.steps(cid)), steps)  # a status is no customer message

    def test_a_closed_window_is_logged_and_the_team_told(self):
        cid, note = self.handed_off()
        self.out.fail[CUSTOMER] = wa.SendRefused(400, wa.WINDOW_CLOSED)
        steps = len(self.chats.steps(cid))
        with self.assertLogs("channels.whatsapp", "WARNING"):
            r = self.run_one(payload([text_msg("t1", "ردنا متأخر", frm=OPERATOR, quoted=note)]))
        self.assertEqual(r.outcome, "relay_failed")
        self.assertEqual(self.out.to(OPERATOR)[-1], wa.TEAM_LINES["window_closed"])
        row = self.results.for_chat(cid)[-1]
        self.assertEqual((row["outcome"], row["step"], row["detail"]["why"], row["detail"]["code"]),
                         ("relay_failed", None, "window_closed", wa.WINDOW_CLOSED))
        self.assertEqual(len(self.chats.steps(cid)), steps)  # nothing saved as sent
        self.assertEqual(self.chats.pending(), [])           # and it is not tried again after a restart

    def test_another_refusal_is_not_called_a_closed_window(self):
        cid, note = self.handed_off()
        self.out.fail[CUSTOMER] = wa.SendRefused(400, 131026)
        with self.assertLogs("channels.whatsapp", "WARNING"):
            r = self.run_one(payload([text_msg("t1", "ردنا", frm=OPERATOR, quoted=note)]))
        self.assertEqual((r.outcome, self.out.to(OPERATOR)[-1]), ("relay_failed", wa.TEAM_LINES["not_sent"]))
        self.assertEqual(self.results.for_chat(cid)[-1]["detail"]["why"], "not_sent")

    def test_other_send_failures_never_stop_the_worker(self):
        cid, note = self.handed_off()
        app = self.app()
        app.accept(wa.parse(payload([text_msg("t1", "رد", frm=OPERATOR, quoted=note),
                                     text_msg("t2", "رد تاني", frm=OPERATOR, quoted=note)]), "111"))
        self.out.fail[CUSTOMER] = OSError("network down")
        app.q.put(None)
        with self.assertLogs("channels.whatsapp", "ERROR"):
            app.work()  # returns at the None; neither failure escaped
        self.assertEqual(self.out.to(OPERATOR)[-2:], [wa.TEAM_LINES["not_sent"]] * 2)
        self.assertEqual([r["detail"]["why"] for r in self.results.for_chat(cid)[-2:]], ["not_sent"] * 2)

    def test_a_late_failed_status_for_a_team_reply(self):
        cid, note = self.handed_off()
        self.run_one(payload([text_msg("t1", "ردنا", frm=OPERATOR, quoted=note)]))
        sent = self.out.ids_to(CUSTOMER)[-1]
        step = self.chats.steps(cid)[-1]["n"]
        with self.assertLogs("channels.whatsapp", "WARNING"):
            r = self.run_one(payload(statuses=[failed_status(sent)]))
        self.assertEqual(r.outcome, "relay_failed")
        row = self.results.for_chat(cid)[-1]
        self.assertEqual((row["outcome"], row["step"], row["detail"]),
                         ("relay_failed", step, {"why": "window_closed", "code": wa.WINDOW_CLOSED, "late": True}))
        self.assertEqual(json.loads(self.chats.steps(cid)[-1]["content"]),
                         {"not_delivered": step, "code": wa.WINDOW_CLOSED})
        self.assertEqual(self.out.to(OPERATOR)[-1], wa.TEAM_LINES["window_closed"])
        self.assertEqual(self.chats.pending(), [])

    def test_other_statuses_are_not_queued(self):
        cid, note = self.handed_off()
        self.run_one(payload([text_msg("t1", "ردنا", frm=OPERATOR, quoted=note)]))
        sent = self.out.ids_to(CUSTOMER)[-1]
        app = self.app()
        app.accept(wa.parse(payload(statuses=[failed_status(sent, status="delivered"),
                                              failed_status(self.out.ids_to(CUSTOMER)[0]),  # the agent's line
                                              failed_status("wamid.unknown")]), "111"))
        self.assertEqual(app.q.qsize(), 0)

    def test_a_photo_or_voice_reply_is_not_sent_or_downloaded(self):
        cid, note = self.handed_off()
        before = len(self.out.sent)
        r = self.run_one(payload([image_msg("t1", frm=OPERATOR, quoted=note)]))
        self.assertEqual((r.outcome, self.graph.downloads), ("ignored", 0))
        self.assertEqual(self.out.sent[before:], [(OPERATOR, wa.TEAM_LINES["text_only"])])
        self.assertEqual(self.chats.pending(), [])

    def test_a_requeued_team_reply_is_still_a_team_reply(self):
        cid, note = self.handed_off()
        self.app().accept(wa.parse(payload([text_msg("t1", "ردنا", frm=OPERATOR, quoted=note)]), "111"))
        app = self.app()  # the process stopped before the reply was sent
        self.assertEqual(app.requeue_pending(), 1)
        r = app.work_one(app.q.get_nowait())
        self.assertEqual((r.outcome, self.out.sent[-1]), ("person_replied", (CUSTOMER, "ردنا")))

    def test_no_message_text_in_the_info_log(self):
        typed = "سر الأوردر 4471"
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        self.addCleanup(root.setLevel, old_level)
        self.addCleanup(root.removeHandler, handler)
        cid, note = self.handed_off()
        self.run_one(payload([text_msg("t1", typed, frm=OPERATOR, quoted=note)]))
        self.run_one(payload([text_msg("t2", "رجع", frm=OPERATOR, quoted=note)]))
        logged = stream.getvalue()
        self.assertIn("team reply sent", logged)
        for secret_text in (typed, "عايز اكلم حد", SUMMARY):
            self.assertNotIn(secret_text, logged)


class ParseAndSend(unittest.TestCase):
    def test_context_id_and_failed_statuses(self):
        fwd = text_msg("f1", "forwarded")
        fwd["context"] = {"forwarded": True}
        items = wa.parse(payload([text_msg("m1", "hi", quoted="wamid.note"), fwd, text_msg("m2", "plain")],
                                 [failed_status("wamid.sent"), failed_status("wamid.ok", status="delivered"),
                                  {"id": "wamid.x", "status": "failed", "errors": [{"code": "131047"}]}]), "111")
        self.assertEqual([(i.kind, i.message_id, i.context_id, i.error_code) for i in items], [
            ("text", "m1", "wamid.note", 0), ("text", "f1", "", 0), ("text", "m2", "", 0),
            ("failed", "failed:wamid.sent", "wamid.sent", wa.WINDOW_CLOSED), ("failed", "failed:wamid.x", "wamid.x", 0)])

    def test_send_refusal_carries_metas_error_code(self):
        def opener(body):
            def open_(req, timeout):
                raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(body))
            return open_

        window = json.dumps({"error": {"message": "(#131047) Re-engagement message", "code": 131047}}).encode()
        for body, code in ((window, 131047), (b"not json", 0), (b'{"error": "x"}', 0), (b'{"error": {"code": true}}', 0)):
            with self.subTest(body=body):
                with self.assertRaises(wa.SendRefused) as cm:
                    wa.Graph("t" * 20, "111", opener=opener(body)).send(CUSTOMER, "hi")
                self.assertEqual((cm.exception.status, cm.exception.code), (400, code))
                self.assertIsNone(cm.exception.__cause__)

    def test_sent_id(self):
        self.assertEqual(handoff.sent_id({"messages": [{"id": "wamid.1"}]}), "wamid.1")
        for bad in (None, {}, {"messages": []}, {"messages": [{}]}, {"messages": [{"id": 5}]}, {"messages": "x"}):
            self.assertEqual(handoff.sent_id(bad), "")


if __name__ == "__main__":
    unittest.main()
