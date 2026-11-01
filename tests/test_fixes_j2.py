"""Fixes from review t261028j round 2 (29 Oct), one class per finding, then the tests that
kill the round 2 mutant sweep's survivors.

Each fix test failed before its fix. The attacks come from the reviewer's probes, run offline
on the fake model, in memory SQLite, with no network.
"""
import json
import unittest

from kit import orders
from kit.chats import FIXED
from kit.tools import draft_order
from tests.fake_model import FakeModel, clean_env, say
from tests.test_fixes_j import MaskTest, SendCheckBase, TurnBase, confirm_from_history, summary_reply
from tests.test_orders import ME, tool_call

LINE = "اوردرك اتسجل برقم #1001، والإجمالي 33,060 جنيه."


class ReDraftTest(TurnBase):
    """New 1: a turn that created an order makes no new summary, so the customer's thanks
    after a re-draft never places a second order."""

    def tool_results(self):
        return [json.loads(s["content"]) for s in self.chats.steps(self.cid) if s["role"] == "tool"]

    def test_a_re_draft_right_after_the_order_places_nothing_more(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")
        self.turn(FakeModel(confirm_from_history(self.args), tool_call("draft_order", self.args),
                            say("اوردرك اتسجل، والاجمالي 33060 جنيه.")), "تمام")
        refused = self.tool_results()[-1]
        self.assertEqual((refused["ok"], refused.get("step")), (False, None))
        self.assertIn("#1001", refused["feedback"])
        self.assertIsNone(orders.Book(self.db).pending(self.cid))
        self.turn(FakeModel(confirm_from_history(self.args), say("تمام")), "تمام شكرا")
        book = orders.Book(self.db)
        self.assertIsNotNone(book.demo_order("#1001"))
        self.assertIsNone(book.demo_order("#1002"))

    def test_a_new_message_asking_for_another_order_gets_a_summary(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")
        self.turn(self.done(), "تمام")
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز نفس الاوردر تاني")
        self.assertEqual(self.tool_results()[-1]["step"], "summary")
        self.assertIsNotNone(orders.Book(self.db).pending(self.cid))

    def test_created_reads_only_this_turn(self):
        made = {"ok": True, "step": "created", "order": "#1001", "total": 33060}

        def steps(*rows):
            return [{"n": n, "role": role, "content": text, "tool_calls": None, "name": name}
                    for n, (role, text, name) in enumerate(rows, 1)]
        body = json.dumps(made)
        self.assertEqual(draft_order.created(steps(("user", "تمام", None), ("tool", body, "draft_order"))), made)
        self.assertIsNone(draft_order.created(steps(("tool", body, "draft_order"), ("user", "تمام", None))))
        self.assertIsNone(draft_order.created(steps(("user", "تمام", None), ("tool", "not json", "draft_order"))))


class LineGoesOnTest(SendCheckBase):
    """New 4: a line that ends in ":" or a cue word reads with the next line, so a price word
    on it still counts for a # number on the next line."""

    BLOCK = ("Total:\n#1500", "الإجمالي:\n#1500", "The total is\n#1500.", "Total:\r\n#1500", "Total =\n#1500",
             "الإجمالي: \n# 1500 جنيه بس", "El total:\n#1500",
             "Delivery:\nTo your house 120.", "The boots #1500 are\n16500 EGP.", "Shipping:\nonly 43.", "الشحن:\nب 43 بس")
    PASS = ("رقم الاوردر:\n#1042", "Your order:\n#1042\nTotal: 16500 EGP.", "Your order number is\n#1042.",
            "الإجمالي: 16500 جنيه\n#1042 هيوصل بكرة", "العنوان:\nالدقي، عمارة 125", "Total: 16500 EGP\nSizes:\n42, 43")

    def test_must_block(self):
        for reply in self.BLOCK:
            with self.subTest(reply=reply):
                self.assertIn("not in the store or delivery data", self.check(reply, {16500, 60, 33060})[1])

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
        return draft_order.answers(steps, 0, "33060.00")

    def test_words_beside_a_tool_call_do_not_count(self):
        call = [{"id": "c1", "type": "function", "function": {"name": "cod_risk", "arguments": "{}"}}]
        self.assertEqual(self.answers(("assistant", "الاجمالي 33060 جنيه", call), ("user", "تمام", None)), [])

    def test_the_customers_own_total_does_not_count(self):
        self.assertEqual(self.answers(("user", "يعني الاجمالي 33060 جنيه", None), ("user", "تمام", None)), [])

    def test_control_the_models_reply_counts(self):
        got = self.answers(("assistant", "الاجمالي 33060 جنيه", None), ("user", "تمام", None))
        self.assertEqual([s["content"] for s in got], ["تمام"])


class SendCheckGapTest(SendCheckBase):
    """Sweep survivors f7-order-name-any-length, f7-money-mark-off, f7-price-sub-mask, f6-lead-digit-any
    (blocks) and f7-money-sentence-off, f7-phone-groups-34-off, f6-join-phones, f6-lookbehind-off
    (false blocks)."""

    BLOCK = ("Your parcel #150000 is on its way.", "The boots #1500, 16500 EGP.", "الجزمة #1500 وصلت، 16500 جنيه.",
             "Total 0 400 EGP")
    PASS = ("#1042 is on its way.", "Call us on +20 100 123 4567.", "Call us on 0101 234 5678.", "Size 37.5 400 EGP")

    def test_must_block(self):
        for reply in self.BLOCK:
            with self.subTest(reply=reply):
                self.assertIn("not in the store or delivery data", self.check(reply, {16500, 400, 60, 33060})[1])

    def test_still_passes(self):
        for reply in self.PASS:
            with self.subTest(reply=reply):
                self.assertEqual(self.number_problems(reply), [])


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
