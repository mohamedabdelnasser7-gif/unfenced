"""Task t261029s step E: the rows draft_order writes itself (order_drafted, order_created) keep
the ids of the lessons their turn was given, like the replied rows do, so the night study can
tie an order to the lessons behind it. Offline; Shopify is never called (demo orders)."""
import json
import unittest
from unittest import mock

from channels.base import Message
from sales import loop, stages
from kit import tools
from kit.chats import Chats
from kit.db import Db
from kit.tools import cod_risk, delivery, draft_order, find_order
from reflection.lessons import Lessons
from reflection.results import Results
from tests.fake_model import FakeModel, Outbox, call, clean_env, say
from tests.test_orders import ME, order_args, tool_call
from tests.kept import kept_lesson
from kit import offers

TONE = "Greet them warmly before anything else."


class OrdersKeepTheirLessons(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.results, self.out = Chats(self.db), Results(self.db), Outbox()
        added = {m.NAME: m for m in (delivery, draft_order, cod_risk, find_order)}
        p = mock.patch.dict(tools.TOOLS, added)
        p.start()
        self.addCleanup(p.stop)
        self.cid = self.chats.open("whatsapp", ME)
        self.chats.set_stage(self.cid, "ordering")
        self.lessons = Lessons(self.db)
        self.kept = kept_lesson(self.lessons, TONE, ["all"])

    def turn(self, model, text):
        msg = Message(channel="whatsapp", customer_id=ME, text=text)
        return loop.turn(msg, chats=self.chats, model=model, lessons=self.lessons, results=self.results,
                         send=self.out)

    def test_the_draft_and_the_order_rows_name_the_turns_lessons(self):
        args = order_args(governorate="el giza")
        summary = "اجمالي الاوردر 16,560 جنيه: الـ Mercurial Vapor 17 Elite مقاس 43 بـ 16,500 جنيه، والشحن 60 جنيه. هيوصل في يوم أو يومين. أأكد؟"
        first = FakeModel(tool_call("draft_order", args), call("cod_risk"), say(summary))
        self.assertEqual(self.turn(first, "عايز الـ Vapor 17 Elite مقاس 43").outcome, "replied")
        self.assertIn(TONE, first.calls[0]["messages"][0]["content"])  # the model was given the lesson

        def confirm(messages, tools_sent):
            code = next(json.loads(m["content"])["code"] for m in reversed(messages)
                        if m["role"] == "tool" and '"code"' in (m["content"] or ""))
            return tool_call("draft_order", {**args, "confirm": code})
        r = self.turn(FakeModel(confirm, say("تمام، اوردر #1001 اتسجل، الاجمالي 16560 جنيه.")), "تمام اكد")
        self.assertEqual(r.outcome, "replied")
        rows = self.results.for_chat(self.cid)
        self.assertEqual([(x["outcome"], x["lessons"]) for x in rows],
                         [("order_drafted", [self.kept]), ("replied", [self.kept]),
                          ("order_created", [self.kept]), ("replied", [self.kept])])

    def test_a_tool_used_outside_a_turn_writes_no_lessons(self):
        ctx = tools.Context(self.cid, stages.STAGES["ordering"], self.chats, None, None, Outbox())
        self.chats.add_step(self.cid, "user", content="عايز اطلب")
        passed, feedback = draft_order.check(order_args(), ctx)
        self.assertTrue(passed, feedback)
        self.assertTrue(draft_order.run(order_args(), ctx)["ok"])
        self.assertEqual([(x["outcome"], x["lessons"]) for x in self.results.for_chat(self.cid)],
                         [("order_drafted", [])])


def setUpModule():
    """These tests read the zone fees (60, 85) as they were before decision 105: the store with no offers.
    The offers' own paths are in tests/test_offers.py and tests/test_offers_paths.py."""
    global _OFFERS_TOKEN
    _OFFERS_TOKEN = offers.OFFERS.set(offers.EMPTY)


def tearDownModule():
    offers.OFFERS.reset(_OFFERS_TOKEN)


if __name__ == "__main__":
    unittest.main()
