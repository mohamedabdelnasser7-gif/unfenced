"""Pre-order for an out of stock size (decision 108) on the real paths: the store data's rule (demo/offers.json)
is read by kit/offers.py, the store tool gives it on every answer, draft_order accepts an out of stock size as
a pre-order (down payment 20% of the total after any offer, the rest on delivery, 7 days) in a quote and a
summary, the order keeps the mark, the send check refuses a pre-order no tool gave, the Arena fact check
reads "available for pre-order" as no stock claim, a card that wants an out of stock size can buy, and a
Build card keeps the rule. Front door tests go through sales/loop.turn with a fake model. No network."""
import json
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from arena import factcheck, offers as arena_offers
from channels.base import Message
from kit import offers, orders, send_check, tools, turn
from kit.chats import Chats
from kit.db import Db
from kit.tools import cod_risk, delivery, draft_order, find_order, store
from reflection import quickstart
from reflection.lessons import Lessons
from reflection.results import Results
from sales import loop, stages
from tests.fake_model import FakeModel, Outbox, call, clean_env, say, tool_call

ME = "201011112222"
PHANTOM = "Nike Phantom 6"                 # Academy 43 is out in the sample stock, 7500; Academy 42 is in
OUT = [{"product": PHANTOM, "tier": "Academy", "size": "43", "quantity": 1}]
IN = [{"product": PHANTOM, "tier": "Academy", "size": "42", "quantity": 1}]


def no_rule():
    """The store data's offers with no pre-order rule."""
    return {k: v for k, v in offers.demo().items() if k != offers.PREORDER}


def tool_results(model, name=None):
    out = []
    for m in model.calls[-1]["messages"]:
        if m["role"] == "tool" and (name is None or m.get("name") in (None, name)):
            out.append(json.loads(m["content"]))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.addCleanup(store._cache.update, at=0.0, items=None)

    def without_rule(self):
        token = offers.OFFERS.set(no_rule())
        self.addCleanup(offers.OFFERS.reset, token)


class Data(Base):
    def test_the_store_data_has_the_rule_and_it_is_no_offer(self):
        rule = offers.preorder(offers.demo())
        self.assertEqual((rule["down_payment_percent"], rule["days"]), (20, 7))
        self.assertNotIn(offers.PREORDER, [o["kind"] for o in offers.demo()["offers"]])
        self.assertEqual(offers.down_payment("7125", offers.demo()), (Decimal(1425), Decimal(5700)))
        self.assertIsNone(offers.down_payment("7500", no_rule()))

    def test_any_store_sets_its_own_share_and_days_or_none(self):
        got = offers.clean({"preorder": {"down_payment_percent": 30, "days": 10}})
        self.assertEqual((got["preorder"]["down_payment_percent"], got["preorder"]["days"]), (30, 10))
        self.assertNotIn("preorder", offers.clean({"preorder": {"down_payment_percent": 0}}))
        self.assertNotIn("preorder", offers.clean({"preorder": {"days": 7}}))
        lifted = offers.clean([{"kind": "preorder", "down_payment_percent": 15}, {"kind": "choice", "what": "A cap"}])
        self.assertEqual((lifted["preorder"]["down_payment_percent"], len(lifted["offers"])), (15, 1))


class StoreTool(Base):
    def test_every_store_answer_carries_the_rule(self):
        for args in ({}, {"query": "phantom"}, {"query": "zzzz"}):
            got = store.run(args, None)
            self.assertEqual((got["preorder"]["down_payment_percent"], got["preorder"]["days"]), (20, 7))
            self.assertFalse({"names", "covers"} & set(got["preorder"]))

    def test_no_rule_no_line(self):
        self.without_rule()
        self.assertNotIn("preorder", store.run({}, None))


class Draft(Base):
    def test_a_quote_for_an_out_of_stock_size_is_a_pre_order(self):
        got = draft_order.quote({"items": OUT, "governorate": "Giza"})
        self.assertTrue(got["ok"], got)
        self.assertEqual((got["preorder"], got["total"], got["down_payment"], got["rest_on_delivery"]),
                         (True, 7500, 1500, 6000))
        self.assertEqual((got["days_min"], got["days_max"]), (7, 7))          # not Giza's 1 to 2
        self.assertTrue(got["items"][0]["preorder"])

    def test_the_down_payment_is_on_the_total_after_the_one_offer(self):
        got = draft_order.quote({"items": OUT, "payment": "card"})
        self.assertEqual([d["offer"] for d in got["discounts"]], ["card_5"])  # the order keeps its one offer
        self.assertEqual((got["total"], got["down_payment"], got["rest_on_delivery"]), (7125, 1425, 5700))

    def test_an_in_stock_size_is_no_pre_order(self):
        got = draft_order.quote({"items": IN, "governorate": "Giza"})
        self.assertNotIn("preorder", got)
        self.assertEqual((got["days_min"], got["days_max"]), (1, 2))

    def test_no_rule_keeps_out_of_stock_refused(self):
        self.without_rule()
        got = draft_order.quote({"items": OUT})
        self.assertFalse(got["ok"])
        self.assertIn("out of stock", got["feedback"])

    def test_the_order_keeps_the_mark(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        cid = Chats(db).open("whatsapp", ME)
        ctx = SimpleNamespace(chats=Chats(db), chat_id=cid)
        draft, problem = draft_order.build({"items": OUT, "name": "Demo Buyer", "governorate": "Giza",
                                            "address": "12 Tahrir St, Dokki"}, ctx)
        self.assertIsNone(problem)
        self.assertEqual((draft["preorder"], draft["down_payment"], draft["rest_on_delivery"], draft["days_max"]),
                         (True, "1500", "6000", 7))
        shown = draft_order.shown(draft)
        self.assertEqual((shown["down_payment"], shown["rest_on_delivery"]), (1500, 6000))
        book = orders.Book(db)
        row = book.demo_order(book.create(draft, cid, {"level": "low", "reasons": []})["order"])
        tags = json.loads(row["tags"])
        self.assertTrue({"preorder", "down-payment-1500", "rest-on-delivery-6000"} <= set(tags))
        self.assertEqual(row["down_payment"], "1500")
        plain, _ = draft_order.build({"items": IN, "name": "Demo Buyer", "governorate": "Giza",
                                      "address": "12 Tahrir St, Dokki"}, ctx)
        row = book.demo_order(book.create(plain, cid, {"level": "low", "reasons": []})["order"])
        self.assertNotIn("preorder", json.loads(row["tags"]))
        self.assertEqual(row["down_payment"], "")


class SendCheck(Base):
    def problems(self, reply, given=()):
        return send_check.offer_problems(reply, offers.for_check(offers.demo(), given))

    def test_a_pre_order_no_tool_gave_is_refused(self):
        for reply in ("Size 43 is out of stock, you can pre-order it.", "You can reserve it with a down payment.",
                      "مقاس 43 خلص، ممكن تحجزه بمقدم."):
            self.assertIn(send_check.NO_PREORDER, self.problems(reply), reply)

    def test_the_tool_s_pre_order_passes(self):
        reply = "Size 43 is out of stock, you can pre-order it with 20% down, delivered within 7 days."
        self.assertEqual(self.problems(reply, ["preorder"]), [])
        self.assertIn("20%", " ".join(self.problems(reply)))               # the share only once given

    def test_a_made_up_share_or_time_is_refused(self):
        self.assertIn("30%", " ".join(self.problems("You can pre-order it with 30% down.", ["preorder"])))
        bad = self.problems("You can pre-order it, it arrives in 3 to 5 days.", ["preorder"])
        self.assertIn(send_check.PREORDER_RULE, bad)

    def test_a_store_with_no_rule_is_not_held(self):
        self.assertEqual(send_check.preorder_problems("You can pre-order it.", None), [])
        self.assertNotIn("preorder", offers.for_check(no_rule(), ["preorder"]))

    def test_the_down_payment_is_an_allowed_amount(self):
        got = draft_order.quote({"items": OUT})
        self.assertTrue({1500, 6000} <= send_check.amounts_in(got))


class FactCheck(Base):
    def names(self, reply, customer="Phantom 6 Academy size 43 to Cairo?"):
        return [f["check"] for f in factcheck.check(reply, customer)]

    def test_out_of_stock_with_a_pre_order_passes(self):
        for reply in ("Size 43 is out of stock, you can pre-order it with 20% down.",
                      "Size 43 is available for pre-order with 20% down.",
                      "مقاس 43 متاح للحجز بمقدم 20%.",
                      "Size 43 is out of stock. Delivery to Cairo for a pre-order is within 7 days."):
            self.assertEqual(self.names(reply), [], reply)

    def test_a_false_in_stock_still_fails(self):
        self.assertIn("stock", self.names("The Phantom 6 Academy in size 43 is in stock."))
        self.assertIn("stock", self.names("Size 43 is in stock, or you can pre-order it with 20% down."))
        self.assertIn("delivery", self.names("Delivery to Cairo takes 7 days."))   # no pre-order, the zone's days


class Arena(Base):
    def test_a_card_that_wants_an_out_of_stock_size_can_buy(self):
        card = {"want": ["Phantom 6 Academy size 43"], "buy_trigger": ["a clear answer"]}
        got = arena_offers.cover(card, offers.demo())
        self.assertEqual(got, {"covered_by": ["Pre-order a size that is out of stock"], "close": False})
        self.assertTrue(arena_offers.cover(card, no_rule())["close"])
        self.assertFalse(arena_offers.cover({"want": ["Phantom 6 Academy size 42"]}, offers.demo())["covered_by"])
        self.assertTrue(arena_offers.cover({"want": ["boots"], "buy_trigger": ["sold out"]}, offers.demo())["covered_by"])


class Build(Base):
    def test_a_build_card_keeps_the_rule_and_the_agent_reads_it(self):
        got = quickstart.card_offers([{"what": "Free delivery", "kind": "delivery", "terms": "any order"},
                                      {"kind": "preorder", "what": "Pre-order", "down_payment_percent": 25, "days": 10}])
        self.assertEqual(got[-1], {"kind": "preorder", "what": "Pre-order", "down_payment_percent": 25, "days": 10})
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        offers.write(folder, got)
        data = offers.read(folder)
        self.assertEqual((data["preorder"]["down_payment_percent"], len(data["offers"])), (25, 1))
        agent = SimpleNamespace(instructions="Sell boots.", full_check=True, stock=True, offers=data, plug=None)
        self.assertIn(offers.PREORDER_LINE, turn.system_prompt(agent)["content"])
        agent.offers = offers.clean(got[:1])
        self.assertNotIn(offers.PREORDER_LINE, turn.system_prompt(agent)["content"])


class SalesFrontDoor(Base):
    def setUp(self):
        super().setUp()
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.results, self.out = Chats(self.db), Results(self.db), Outbox()
        p = mock.patch.dict(tools.TOOLS, {m.NAME: m for m in (delivery, draft_order, cod_risk, find_order)})
        p.start()
        self.addCleanup(p.stop)
        self.cid = self.chats.open("whatsapp", ME)

    def turn(self, model, text):
        msg = Message(channel="whatsapp", customer_id=ME, text=text)
        return loop.turn(msg, chats=self.chats, model=model, lessons=Lessons(self.db), results=self.results,
                         send=self.out)

    def test_a_pre_order_before_the_store_tool_is_refused_then_sent(self):
        good = "The Phantom 6 Academy in size 43 is out of stock, but you can pre-order it with 20% down."
        model = FakeModel(say(good), call("store", query="phantom"), say(good))
        r = self.turn(model, "Do you have the Phantom 6 Academy in 43?")
        self.assertEqual((r.outcome, r.reply), ("replied", good))
        self.assertEqual([t for _, t in self.out.sent], [good])
        rows = self.results.for_chat(self.cid)
        self.assertEqual([x["outcome"] for x in rows], ["check_failed", "replied"])
        self.assertIn(send_check.NO_PREORDER, rows[0]["detail"]["feedback"])
        self.assertIn(offers.PREORDER_LINE, model.calls[0]["messages"][0]["content"])
        self.assertIn("preorder", tool_results(model)[0])
        self.assertIn("preorder", loop.store_offers(self.chats, self.cid))

    def test_a_pre_order_quote_s_amounts_and_days_may_be_quoted(self):
        self.chats.set_stage(self.cid, "ordering")
        args = {"items": OUT, "quote": True, "governorate": "Giza"}
        good = ("The Phantom 6 Academy in 43 is a pre-order: 7,500 EGP in all, 1,500 EGP down payment now and "
                "6,000 EGP on delivery, delivered within 7 days.")
        model = FakeModel(tool_call("draft_order", args),
                          say("It is a pre-order: 2,000 EGP down payment now, delivered within 7 days."), say(good))
        r = self.turn(model, "I want the Phantom 6 Academy in 43 to Giza. How much?")
        self.assertEqual((r.outcome, r.reply), ("replied", good))
        got = tool_results(model)[0]
        self.assertEqual((got["preorder"], got["down_payment"], got["days_max"]), (True, 1500, 7))
        self.assertIn("2000", self.results.for_chat(self.cid)[0]["detail"]["feedback"])

    def test_without_the_rule_the_store_gives_none_and_a_pre_order_is_not_held(self):
        self.without_rule()
        model = FakeModel(call("store", query="phantom"), say("The Phantom 6 Academy in size 43 is out of stock."))
        r = self.turn(model, "Do you have the Phantom 6 Academy in 43?")
        self.assertEqual(r.outcome, "replied")
        self.assertNotIn("preorder", tool_results(model)[0])
        self.assertNotIn(offers.PREORDER_LINE, model.calls[0]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
