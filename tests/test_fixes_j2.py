"""Fixes from review t261028j round 2 (29 Oct), one class per finding, then the tests that
kill the round 2 mutant sweep's survivors.

Each fix test failed before its fix. The attacks come from the reviewer's probes, run offline
on the fake model, in memory SQLite, with no network.
"""
import json
import unittest

from kit import orders
from kit.chats import FIXED
from kit.tools import draft_order, handoff
from tests.fake_model import FakeModel, clean_env, say
from tests.test_fixes_j import (OPERATOR, IdOutbox, MaskTest, RefusingOutbox, SendCheckBase, TurnBase,
                                confirm_from_history, summary_reply)
from tests.test_orders import ME, tool_call

LINE = "اوردرك اتسجل برقم #1001، والإجمالي 2,960 جنيه."


class ReDraftTest(TurnBase):
    """New 1: a turn that created an order makes no new summary, so the customer's thanks
    after a re-draft never places a second order."""

    def tool_results(self):
        return [json.loads(s["content"]) for s in self.chats.steps(self.cid) if s["role"] == "tool"]

    def test_a_re_draft_right_after_the_order_places_nothing_more(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين ابيض مقاس 43")
        self.turn(FakeModel(confirm_from_history(self.args), tool_call("draft_order", self.args),
                            say("اوردرك اتسجل، والاجمالي 2960 جنيه.")), "تمام")
        refused = self.tool_results()[-1]
        self.assertEqual((refused["ok"], refused.get("step")), (False, None))
        self.assertIn("#1001", refused["feedback"])
        self.assertIsNone(orders.Book(self.db).pending(self.cid))
        self.turn(FakeModel(confirm_from_history(self.args), say("تمام")), "تمام شكرا")
        book = orders.Book(self.db)
        self.assertIsNotNone(book.demo_order("#1001"))
        self.assertIsNone(book.demo_order("#1002"))

    def test_a_new_message_asking_for_another_order_gets_a_summary(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين ابيض مقاس 43")
        self.turn(self.done(), "تمام")
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز نفس الاوردر تاني")
        self.assertEqual(self.tool_results()[-1]["step"], "summary")
        self.assertIsNotNone(orders.Book(self.db).pending(self.cid))

    def test_created_reads_only_this_turn(self):
        made = {"ok": True, "step": "created", "order": "#1001", "total": 2960}

        def steps(*rows):
            return [{"n": n, "role": role, "content": text, "tool_calls": None, "name": name}
                    for n, (role, text, name) in enumerate(rows, 1)]
        body = json.dumps(made)
        self.assertEqual(draft_order.created(steps(("user", "تمام", None), ("tool", body, "draft_order"))), made)
        self.assertIsNone(draft_order.created(steps(("tool", body, "draft_order"), ("user", "تمام", None))))
        self.assertIsNone(draft_order.created(steps(("user", "تمام", None), ("tool", "not json", "draft_order"))))


class ModelHandoffOrderTest(TurnBase):
    """New 2: an order, then the model's own handoff call: the customer hears ORDER_PLACED
    first, once, and the team's note names the order."""

    def setUp(self):
        super().setUp()
        clean_env(self, OPERATOR_WHATSAPP=OPERATOR)
        self.out = IdOutbox()
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين ابيض مقاس 43")
        self.start = self.chats.steps(self.cid)[-1]["n"]

    def to_customer(self):
        return [t for to, t in self.out.sent if to == ME]

    def note(self):
        return "\n".join(t for to, t in self.out.sent if to == OPERATOR)

    def handoff(self, reason="the customer wants a person"):
        return tool_call("handoff", {"reason": reason})

    def test_the_order_line_goes_before_the_handoff_line(self):
        r = self.turn(FakeModel(confirm_from_history(self.args), self.handoff(), say("العميل عايز حد")), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual(r.outcome, "handed_off")
        self.assertEqual(self.to_customer()[-2:], [LINE, handoff.TAKING_OVER["arabic"]])
        self.assertEqual(self.to_customer().count(LINE), 1)
        self.assertIn(handoff.ORDER_MADE.format(order="#1001", total=2960), self.note())
        self.assertEqual(self.results.for_chat(self.cid)[-1]["detail"]["order"], "#1001")
        turn = [(s["role"], bool(s["tool_calls"]), s["name"]) for s in self.chats.steps(self.cid)
                if s["n"] > self.start and s["role"] != "event"]          # the stage change is an event row
        self.assertEqual(turn, [("user", False, None), ("assistant", True, None), ("tool", False, "draft_order"),
                                ("assistant", True, None), ("tool", False, "handoff"),
                                ("assistant", False, FIXED), ("assistant", False, FIXED)])

    def test_the_confirm_and_the_handoff_in_one_step(self):
        def both(messages, tools_sent):
            out = confirm_from_history(self.args)(messages, tools_sent)
            out["tool_calls"] = out["tool_calls"] + self.handoff()["tool_calls"]
            return out
        r = self.turn(FakeModel(both, say("العميل عايز حد")), "تمام")
        self.assertEqual(r.outcome, "handed_off")
        self.assertEqual(self.to_customer()[-2:], [LINE, handoff.TAKING_OVER["arabic"]])
        self.assertIn("#1001", self.note())

    def test_two_handoff_calls_in_one_step_send_the_order_line_once(self):
        self.out = RefusingOutbox()

        def three(messages, tools_sent):
            out = confirm_from_history(self.args)(messages, tools_sent)
            out["tool_calls"] = out["tool_calls"] + self.handoff()["tool_calls"] + self.handoff("again")["tool_calls"]
            return out
        self.turn(FakeModel(three, say("العميل عايز حد")), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual(self.to_customer().count(LINE), 1)

    def test_a_note_that_reaches_no_one_still_comes_after_the_order_line(self):
        self.out = RefusingOutbox()
        r = self.turn(FakeModel(confirm_from_history(self.args), self.handoff(), say("العميل عايز حد")), "تمام")
        self.assertEqual(r.outcome, "handoff_failed")
        self.assertEqual(self.to_customer(), [LINE, handoff.TEAM_WILL_REPLY["arabic"]])

    def test_an_order_made_after_a_refused_note_is_still_told(self):
        self.out = RefusingOutbox()

        def both(messages, tools_sent):
            out = self.handoff()
            out["tool_calls"] = out["tool_calls"] + confirm_from_history(self.args)(messages, tools_sent)["tool_calls"]
            return out
        r = self.turn(FakeModel(both, say("العميل عايز حد")), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual(r.outcome, "handoff_failed")
        self.assertEqual(self.to_customer(), [handoff.TEAM_WILL_REPLY["arabic"], LINE])

    def test_a_handoff_call_that_does_not_run_sends_no_order_line(self):
        r = self.turn(FakeModel(confirm_from_history(self.args), self.handoff(reason=" "),
                                say("تمام، اوردرك اتسجل.")), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, self.to_customer()[-1]), ("replied", "تمام، اوردرك اتسجل."))
        self.assertNotIn(LINE, self.to_customer())

    def test_the_loops_own_handoff_note_names_the_order(self):
        self.turn(FakeModel(confirm_from_history(self.args), say("الاجمالي 1900 جنيه."), say("الاجمالي 1901 جنيه."),
                            say("الاجمالي 1902 جنيه."), say("ملخص")), "تمام")
        self.assertEqual(self.to_customer()[-2:], [LINE, handoff.TAKING_OVER["arabic"]])
        self.assertEqual(self.to_customer().count(LINE), 1)
        self.assertIn("#1001", self.note())

    def test_no_order_no_order_line_and_no_order_in_the_note(self):
        self.turn(FakeModel(self.handoff(), say("العميل عايز حد")), "عايز اكلم حد")
        self.assertEqual(self.to_customer()[-1], handoff.TAKING_OVER["arabic"])
        self.assertNotIn(LINE, self.to_customer())
        self.assertNotIn("اوردر برقم", self.note())


class NotPassedOnTest(TurnBase):
    """New 3: with a person, a customer message that reaches no one on the team goes to the
    result log as relay_failed, and the customer hears TEAM_WILL_REPLY once."""

    def setUp(self):
        super().setUp()
        clean_env(self, OPERATOR_WHATSAPP=OPERATOR)
        self.out = RefusingOutbox()
        self.chats.set_stage(self.cid, "with_person")

    def to_customer(self):
        return [t for to, t in self.out.sent if to == ME]

    def last_result(self):
        return self.results.for_chat(self.cid)[-1]

    def test_a_refused_message_is_logged_and_the_customer_told_once(self):
        r = self.turn(FakeModel(), "لسه مستني حد يرد")
        self.assertEqual((r.outcome, r.reply), ("relay_failed", handoff.TEAM_WILL_REPLY["arabic"]))
        self.assertEqual(self.to_customer(), [handoff.TEAM_WILL_REPLY["arabic"]])
        self.assertEqual((self.last_result()["outcome"], self.last_result()["detail"]),
                         ("relay_failed", {"why": "not_passed_on", "told": True}))
        self.assertEqual(self.chats.steps(self.cid)[-1]["name"], FIXED)
        r = self.turn(FakeModel(), "في حد؟")
        self.assertEqual((r.outcome, r.reply), ("relay_failed", None))
        self.assertEqual(self.to_customer(), [handoff.TEAM_WILL_REPLY["arabic"]])
        self.assertEqual(self.last_result()["detail"], {"why": "not_passed_on", "told": False})
        self.assertEqual(self.chats.stage(self.cid), "with_person")

    def test_told_again_after_a_person_replied(self):
        self.turn(FakeModel(), "لسه مستني حد يرد")
        self.chats.add_person_reply(self.cid, "معاك، ثواني")
        self.turn(FakeModel(), "hello, anyone there?")
        self.assertEqual(self.to_customer(), [handoff.TEAM_WILL_REPLY["arabic"], handoff.TEAM_WILL_REPLY["english"]])

    def test_an_error_whose_team_line_also_fails_is_logged_and_told(self):
        from unittest import mock
        with mock.patch.object(handoff, "pass_on", side_effect=RuntimeError("bug")):
            r = self.turn(FakeModel(), "لسه مستني")
        self.assertEqual(r.outcome, "relay_failed")
        self.assertEqual(self.to_customer(), [handoff.TEAM_WILL_REPLY["arabic"]])

    def test_a_message_that_reaches_the_team_tells_the_customer_nothing(self):
        self.out = IdOutbox()
        self.assertEqual(self.turn(FakeModel(), "لسه مستني").outcome, "waiting")
        self.assertEqual(self.to_customer(), [])
        self.assertNotIn("relay_failed", [x["outcome"] for x in self.results.for_chat(self.cid)])


class LineGoesOnTest(SendCheckBase):
    """New 4: a line that ends in ":" or a cue word reads with the next line, so a price word
    on it still counts for a # number on the next line."""

    BLOCK = ("Total:\n#1500", "الإجمالي:\n#1500", "The total is\n#1500.", "Total:\r\n#1500", "Total =\n#1500",
             "الإجمالي: \n# 1500 جنيه بس", "El total:\n#1500",
             "Delivery:\nTo your house 120.", "The boots #1500 are\n1450 EGP.", "Shipping:\nonly 43.", "الشحن:\nب 43 بس")
    PASS = ("رقم الاوردر:\n#1042", "Your order:\n#1042\nTotal: 1450 EGP.", "Your order number is\n#1042.",
            "الإجمالي: 1450 جنيه\n#1042 هيوصل بكرة", "العنوان:\nالدقي، عمارة 125", "Total: 1450 EGP\nSizes:\n42, 43")

    def test_must_block(self):
        for reply in self.BLOCK:
            with self.subTest(reply=reply):
                self.assertIn("not in the store or delivery data", self.check(reply, {1450, 60, 2960})[1])

    def test_still_passes(self):
        for reply in self.PASS + MaskTest.PASS:
            with self.subTest(reply=reply):
                self.assertEqual(self.number_problems(reply), [])


class SummaryReplyGapTest(unittest.TestCase):
    """Sweep survivors f1-tool-calls-ok and f1-role-user-too: words beside a tool call, or the
    customer's own message with the total, are never the summary the customer saw."""

    def answers(self, *rows):
        steps = [{"n": n, "role": role, "content": text, "tool_calls": calls, "name": None}
                 for n, (role, text, calls) in enumerate(rows, 1)]
        return draft_order.answers(steps, 0, "2960.00")

    def test_words_beside_a_tool_call_do_not_count(self):
        call = [{"id": "c1", "type": "function", "function": {"name": "cod_risk", "arguments": "{}"}}]
        self.assertEqual(self.answers(("assistant", "الاجمالي 2960 جنيه", call), ("user", "تمام", None)), [])

    def test_the_customers_own_total_does_not_count(self):
        self.assertEqual(self.answers(("user", "يعني الاجمالي 2960 جنيه", None), ("user", "تمام", None)), [])

    def test_control_the_models_reply_counts(self):
        got = self.answers(("assistant", "الاجمالي 2960 جنيه", None), ("user", "تمام", None))
        self.assertEqual([s["content"] for s in got], ["تمام"])


class SendCheckGapTest(SendCheckBase):
    """Sweep survivors f7-order-name-any-length, f7-money-mark-off, f7-price-sub-mask, f6-lead-digit-any
    (blocks) and f7-money-sentence-off, f7-phone-groups-34-off, f6-join-phones, f6-lookbehind-off
    (false blocks)."""

    BLOCK = ("Your parcel #150000 is on its way.", "The boots #1500, 1450 EGP.", "الجزمة #1500 وصلت، 1450 جنيه.",
             "Total 0 700 EGP")
    PASS = ("#1042 is on its way.", "Call us on +20 100 123 4567.", "Call us on 0101 234 5678.", "Size 37.5 700 EGP")

    def test_must_block(self):
        for reply in self.BLOCK:
            with self.subTest(reply=reply):
                self.assertIn("not in the store or delivery data", self.check(reply, {1450, 700, 60, 2960})[1])

    def test_still_passes(self):
        for reply in self.PASS:
            with self.subTest(reply=reply):
                self.assertEqual(self.number_problems(reply), [])


class NotePartsCapTest(TurnBase):
    """Sweep survivor f2-send-all-parts: one message too long to trim still sends 3 parts at most."""

    def test_one_huge_message_sends_three_parts(self):
        clean_env(self, OPERATOR_WHATSAPP=OPERATOR)
        self.out = IdOutbox()
        self.chats.set_stage(self.cid, "asking")
        text = "عايز اكلم حد " + "كلام كتير " * 3000
        self.assertGreater(len(handoff.split(text)), 3)          # the one message alone is 8 parts
        model = FakeModel(tool_call("handoff", {"reason": "asks for a person"}), say("العميل عايز حد من الفريق"))
        self.assertEqual(self.turn(model, text).outcome, "handed_off")
        self.assertEqual(len([t for to, t in self.out.sent if to == OPERATOR]), 3)


class DeadlineReaderTest(unittest.TestCase):
    """Sweep survivor h-deadline-timeout-not-restored: after a read, writes get the normal timeout back."""

    def test_a_read_puts_the_normal_timeout_back(self):
        import time
        from channels.whatsapp import DeadlineReader
        calls = []
        conn = type("Conn", (), {"settimeout": lambda self, t: calls.append(t), "recv_into": lambda self, buf: 0})()
        DeadlineReader(conn, time.monotonic() + 0.5, per_read=10).readinto(bytearray(1))
        self.assertEqual((calls[0] < 1, calls[-1]), (True, 10))


if __name__ == "__main__":
    unittest.main()
