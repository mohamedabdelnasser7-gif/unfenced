"""Store offers on the real paths (decision 105): the store and data tools list them, the delivery fee and
the amounts a reply may quote follow the delivery offer, draft_order works the totals out through
kit/offers.py (quote mode and the saved order), the Sales prompt and instructions carry them, and a built
agent sees only its own offers. Front door tests T1, T3 and T4 of the offers plan go through sales/loop.turn
and kit/turn.turn with a fake model. The send check's offers rule comes later (plan step A7). No network."""
import json
import os
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from channels.base import Message
from kit import offers, orders, tools, turn
from kit.chats import Chats
from kit.db import Db
from kit.tools import cod_risk, data as data_tool, delivery, draft_order, find_order, store
from reflection.lessons import Lessons
from reflection.results import Results
from sales import loop, stages
from tests.fake_model import FakeModel, Outbox, call, clean_env, say, tool_call

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "agents" / "stock_watch"
ME = "201011112222"
PHANTOM, PRINT = "Nike Phantom 6", "Beyond the Limits Name Printing"   # Elite 16500, Pro 11000; printing 400
ITEMS = [{"product": PHANTOM, "tier": "Elite", "size": "42", "quantity": 1},
         {"product": PHANTOM, "tier": "Pro", "size": "42", "quantity": 1},
         {"product": PRINT, "quantity": 1}]
OWN = {"offers": [{"id": "cap_deal", "kind": "choice", "what": "A matching cap at its own price",
                   "when": "the customer asks what goes with it", "names": ["cap deal"]}]}


def tool_results(model, name=None):
    """Every tool result the model was shown, parsed, in order (the last call holds them all)."""
    out = []
    for m in model.calls[-1]["messages"]:
        if m["role"] == "tool" and (name is None or m.get("name") in (None, name)):
            out.append(json.loads(m["content"]))
    return out


class Tools(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        store._cache.update(at=0.0, items=None)
        self.addCleanup(store._cache.update, at=0.0, items=None)

    def test_the_store_lists_the_offers_on_every_answer(self):
        for args in ({}, {"query": "phantom"}, {"query": "zzzz"}):
            got = store.run(args, None)
            self.assertEqual([o["id"] for o in got["offers"]],
                             ["valu_3m", "card_5", "free_delivery", "elite_print", "second_pair", "lower_tier"])
            self.assertEqual(got["payment_methods"], ["cash", "card", "valu"])
            self.assertIn("One offer an order", got["offer_limit"])
            self.assertFalse(any("names" in o or "covers" in o for o in got["offers"]))
        self.assertIn("offers", store.DEFINITION["function"]["description"])

    def test_free_delivery_sets_the_fee_and_keeps_the_days(self):
        got = delivery.quote("Giza")
        self.assertEqual((got["fee"], got["days_min"], got["days_max"], got["offer"]), (0, 1, 2, "Free delivery"))
        self.assertEqual((delivery.quote("Aswan")["fee"], delivery.quote("Aswan")["days_max"]), (0, 4))
        token = offers.OFFERS.set(offers.EMPTY)
        try:
            got = delivery.quote("Giza")
            self.assertEqual(got["fee"], 60)
            self.assertNotIn("offer", got)
        finally:
            offers.OFFERS.reset(token)

    def test_draft_order_checks_payment_and_quote(self):
        ok = {"items": ITEMS, "quote": True, "payment": "card"}
        self.assertEqual(draft_order.check(ok, None), (True, ""))
        self.assertTrue(draft_order.check(dict(ok, payment="Card"), None)[0])
        bad, why = draft_order.check(dict(ok, payment="bitcoin"), None)
        self.assertFalse(bad)
        self.assertIn("cash, card, valu", why)
        self.assertFalse(draft_order.check(dict(ok, quote=False), None)[0])
        self.assertFalse(draft_order.check(dict(ok, name="Demo Buyer"), None)[0])
        self.assertFalse(draft_order.check({"items": ITEMS}, None)[0])          # an order still needs its details
        self.assertEqual(draft_order.DEFINITION["function"]["parameters"]["required"], ["items"])

    def test_a_quote_is_offers_apply_and_saves_nothing(self):
        got = draft_order.quote({"items": ITEMS, "payment": "card", "governorate": "Giza"})
        lines = [{"price": "16500", "quantity": 1, "tier": "Elite", "size": "42"},
                 {"price": "11000", "quantity": 1, "tier": "Pro", "size": "42"},
                 {"price": "400", "quantity": 1, "type": "Printing", "size": ""}]
        want = offers.apply(lines, "card", offers.demo(), fee=60)
        self.assertEqual((got["subtotal"], got["fee"], got["total"]), (27900, 0, int(want["total"])))
        self.assertEqual(got["discounts"], [{"offer": "card_5", "what": "5% off when paid by debit or credit card",
                                             "discount": 1395}])
        self.assertEqual((got["step"], got["payment"], got["governorate"]), ("quote", "card", "Giza"))
        got = draft_order.quote({"items": ITEMS})
        self.assertEqual([d["offer"] for d in got["discounts"]], ["second_pair"])
        self.assertNotIn("fee", got)
        self.assertEqual(got["total"], 26800)

    def test_the_order_keeps_payment_and_discount(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        Chats(db).open("whatsapp", ME)
        book = orders.Book(db)
        draft = {"items": [{"product": PHANTOM, "tier": "Elite", "size": "42", "sku": "x", "price": "16500",
                            "quantity": 1}], "name": "Demo Buyer", "address": "12 Tahrir St", "phone": ME,
                 "whatsapp": ME, "governorate": "Giza", "area": "Cairo and Giza", "days_min": 1, "days_max": 2,
                 "subtotal": "16500", "fee": "0", "total": "15675", "currency": "EGP", "payment": "card",
                 "discounts": [{"offer": "card_5", "what": "5% off when paid by debit or credit card",
                                "discount": "825"}]}
        cid = Chats(db).open("whatsapp", ME)
        made = book.create(draft, cid, {"level": "low", "reasons": []})
        row = book.demo_order(made["order"])
        self.assertEqual((row["payment"], row["discount"], row["total"]), ("card", "825", "15675"))
        self.assertIn("payment-card", json.loads(row["tags"]))
        got = orders.draft_order_input(draft, cid, [], {"x": "gid://shopify/ProductVariant/1"})
        self.assertEqual(got["appliedDiscount"]["amountWithCurrency"], {"amount": "825", "currencyCode": "EGP"})
        self.assertNotIn("appliedDiscount", orders.draft_order_input(dict(draft, discounts=[]), cid, [],
                                                                     {"x": "gid://shopify/ProductVariant/1"}))

    def test_an_old_orders_table_gets_the_new_columns(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        old = orders.SCHEMA
        for name, decl in orders.ORDER_COLUMNS:
            self.assertNotIn(f"  {name} ", old)
        db.script(old)
        orders.Book(db)
        with db.tx() as c:
            have = {r[1] for r in c.execute("PRAGMA table_info(demo_orders)")}
        self.assertTrue({"payment", "discount", "discounts"} <= have)

    def test_sales_instructions_and_data_carry_the_offers(self):
        self.assertIn("valU", loop.INSTRUCTIONS)
        self.assertIn("lower tier", loop.INSTRUCTIONS)
        self.assertIn("never a made-up discount", loop.INSTRUCTIONS)
        self.assertNotIn("cash on delivery", loop.INSTRUCTIONS)
        self.assertNotIn("cash_on_delivery", (ROOT / "demo" / "delivery.json").read_text(encoding="utf-8"))
        self.assertIn(offers.PROMPT_LINE, loop.system_prompt(stages.get("asking"), [])["content"])


class SalesFrontDoor(unittest.TestCase):
    """T1 and T3: the Sales agent through sales/loop.turn."""

    def setUp(self):
        clean_env(self)
        store._cache.update(at=0.0, items=None)
        self.addCleanup(store._cache.update, at=0.0, items=None)
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

    def test_t1_the_store_step_shows_the_offers(self):
        reply = "The Phantom 6 Elite is 16,500 EGP, and you can pay in installments through valU."
        model = FakeModel(call("store", query="phantom"), say(reply))
        r = self.turn(model, "How much is the Phantom 6 Elite? It is a bit much for me")
        self.assertEqual((r.outcome, r.reply), ("replied", reply))
        shown = tool_results(model)[0]
        self.assertIn("valu_3m", [o["id"] for o in shown["offers"]])
        self.assertEqual(shown["payment_methods"], ["cash", "card", "valu"])
        self.assertIn(offers.PROMPT_LINE, model.calls[0]["messages"][0]["content"])
        self.assertIn("valU", model.calls[0]["messages"][0]["content"])
        self.assertTrue({"valu_3m", "card_5", "free_delivery", "second_pair"} <= loop.store_offers(self.chats, self.cid))

    def test_t3_a_card_quote_takes_the_one_biggest_offer(self):
        self.chats.set_stage(self.cid, "ordering")
        args = {"items": ITEMS, "quote": True, "payment": "card", "governorate": "Giza"}
        good = "With the card, the total is 26,505 EGP, and delivery is free."
        model = FakeModel(tool_call("draft_order", args), say("With the card, the total is 26,000 EGP."),
                          say("The total is 26,505 EGP plus delivery 60 EGP."), say(good))
        r = self.turn(model, "Phantom 6 Elite and Pro in 42 with a name printing, paying by card. How much?")
        self.assertEqual((r.outcome, r.reply), ("replied", good))
        self.assertEqual(len(model.calls), 4)       # the free-hand total and the old delivery fee were refused
        self.assertEqual([t for _, t in self.out.sent], [good])
        got = tool_results(model)[0]
        lines = draft_order._offer_lines(draft_order._lines(ITEMS, None)[0], {PRINT: "Printing"})
        want = offers.apply(lines, "card", offers.current(), fee=60)
        self.assertEqual([d["offer"] for d in got["discounts"]], ["card_5"])   # one offer an order: the biggest
        self.assertEqual((got["fee"], got["total"]), (0, int(want["total"])))
        self.assertEqual(want["total"], Decimal(26505))
        self.assertIsNone(orders.Book(self.db).pending(self.cid))              # a quote saves nothing
        self.assertIn("card_5", loop.store_offers(self.chats, self.cid))

    def test_a_card_order_summary_keeps_payment_and_the_discount(self):
        self.chats.set_stage(self.cid, "ordering")
        args = {"items": ITEMS[:1], "payment": "card", "name": "Demo Buyer", "governorate": "Giza",
                "address": "12 Tahrir St, Dokki"}
        model = FakeModel(tool_call("draft_order", args), say("Total 15,675 EGP for the Phantom 6 Elite in 42, delivery free. Confirm?"))
        r = self.turn(model, "I want the Phantom 6 Elite in 42, paying by card")
        self.assertEqual(r.outcome, "replied", r)
        shown = tool_results(model)[0]
        self.assertEqual((shown["payment"], shown["fee"], shown["total"]), ("card", 0, 15675))
        self.assertEqual(shown["discounts"][0]["discount"], 825)
        draft = orders.Book(self.db).pending(self.cid)["draft"]
        self.assertEqual((draft["payment"], draft["discounts"][0]["offer"]), ("card", "card_5"))


class BuiltAgentFrontDoor(unittest.TestCase):
    """T4: a built agent through kit/turn.turn sees its own offers, never the store data's."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.folder = Path(d.name).resolve() / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith("SHOPIFY")},
                              clear=True)
        env.start()
        self.addCleanup(env.stop)
        store._cache.update(at=0.0, items=None)
        self.addCleanup(store._cache.update, at=0.0, items=None)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)

    def run_turn(self, agent, *script):
        model = FakeModel(*script)
        cid = self.chats.open("whatsapp", "c1")
        got = turn.turn(agent, "Is the Phantom 6 in stock?", chats=self.chats, chat_id=cid, model=model,
                        send=lambda *a: None, customer_id="c1")
        return got, model

    def test_t4_the_store_result_carries_its_offers_and_the_prompt_the_line(self):
        offers.write(self.folder, OWN)
        agent = turn.load(self.folder)
        self.assertEqual([o["id"] for o in agent.offers["offers"]], ["cap_deal"])
        got, model = self.run_turn(agent, tool_call("store", {"query": "phantom"}), say("The Phantom 6 is in stock."))
        self.assertEqual(got.outcome, "replied", got)
        shown = tool_results(model)[0]
        self.assertEqual(shown["offers"], [{"id": "cap_deal", "kind": "choice", "what": "A matching cap at its own price",
                                            "when": "the customer asks what goes with it"}])
        self.assertNotIn("payment_methods", shown)           # none of the store data's offers or methods
        self.assertIn(offers.PROMPT_LINE, model.calls[0]["messages"][0]["content"])
        self.assertIsNone(offers.own())                      # set for the turn only

    def test_an_agent_with_no_offers_gets_none_of_the_store_datas(self):
        agent = turn.load(self.folder)
        self.assertIsNone(agent.offers)
        got, model = self.run_turn(agent, tool_call("store", {"query": "phantom"}), say("The Phantom 6 is in stock."))
        shown = tool_results(model)[0]
        self.assertNotIn("offers", shown)
        self.assertNotIn(offers.PROMPT_LINE, model.calls[0]["messages"][0]["content"])

    def test_with_no_store_tool_the_data_tool_lists_the_offers(self):
        plug = json.loads((self.folder / "plug.json").read_text(encoding="utf-8"))
        plug["risk"]["high"]["tools"] = ["switch_stage"]
        (self.folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
        offers.write(self.folder, OWN)
        agent = turn.load(self.folder)
        self.assertNotIn(store.NAME, agent.tools)
        self.assertIn(turn.DATA_TOOL, agent.tools)
        got, model = self.run_turn(agent, tool_call("data", {}), say("Ask me about a cap."))
        shown = tool_results(model)[0]
        self.assertEqual((shown["ok"], shown["rows"], shown["offers"][0]["id"]), (True, [], "cap_deal"))
        self.assertFalse(data_tool.run({}, mock.Mock(data=None))["ok"])   # outside a turn with offers: as before


if __name__ == "__main__":
    unittest.main()
