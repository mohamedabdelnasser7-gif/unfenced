"""Store offers on the real paths (decision 105): the store and data tools list them, the delivery fee and
the amounts a reply may quote follow the delivery offer, draft_order works the totals out through
kit/offers.py (quote mode and the saved order), the Sales prompt and instructions carry them, and a built
agent sees only its own offers. Front door tests T1 to T4 of the offers plan go through sales/loop.turn
and kit/turn.turn with a fake model, the send check's offers rule (plan step A7) among them. No network."""
import json
import os
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from arena import factcheck
from channels.base import Message
from kit import offers, orders, send_check, tools, turn
from kit.chats import Chats
from kit.db import Db
from kit.tools import cod_risk, data as data_tool, delivery, draft_order, find_order, store
from reflection import exam
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
                             ["valu_3m", "card_5", "free_delivery", "elite_print", "second_pair", "lower_tier", "cash_on_delivery"])
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


class OffersRule(unittest.TestCase):
    """The send check's offers rule on its own (kit/send_check.py offer_problems, kit/offers.py for_check)."""

    def problems(self, reply, given=()):
        return dict(send_check.named_problems(reply, "hi", offers=offers.for_check(offers.demo(), given)))

    def test_nothing_given_refuses_names_talk_and_percents(self):
        self.assertIn("free_delivery", self.problems("Delivery is free delivery to Giza.").get("offers", ""))
        self.assertIn("valu_3m", self.problems("You can pay through valU.").get("offers", ""))
        self.assertIn(send_check.NO_OFFER_TALK, self.problems("We have a discount for you.").get("offers", ""))
        self.assertIn("10%", self.problems("You get 10% off today.").get("offers", ""))
        self.assertIn("10%", self.problems("خصم ١٠٪ النهارده").get("offers", ""))
        self.assertIn("free_delivery", self.problems("والتوصيل مجاني لحد البيت").get("offers", ""))
        self.assertIn(send_check.NO_OFFER_TALK, self.problems("في عرض والخصم كويس").get("offers", ""))
        self.assertNotIn("offers", self.problems("We have the Phantom 6 Elite in 42, two pairs left."))

    def test_given_offers_pass_and_other_percents_fail(self):
        every = [o["id"] for o in offers.demo()["offers"]]
        for ok in ("Pay by card and get 5% off.", "Every second pair is 10% off.", "Delivery is free delivery.",
                   "There is a discount when you pay by card.", "valU, 3 months, no interest."):
            self.assertNotIn("offers", self.problems(ok, every), ok)
        self.assertIn("15%", self.problems("Pay by card and get 15% off.", every)["offers"])
        self.assertIn("20%", self.problems("20 percent off the Elite.", every)["offers"])
        only_card = self.problems("Pay by card for 5% off, or valU.", ["card_5"])["offers"]
        self.assertIn("valu_3m", only_card)
        self.assertNotIn("card_5", only_card)
        self.assertIn("10%", self.problems("10% off a second pair.", ["card_5"]).get("offers", ""))

    def test_an_agent_with_no_offers_is_not_held(self):
        self.assertIsNone(offers.for_check(offers.EMPTY, ["x"]))
        self.assertNotIn("offers", dict(send_check.named_problems("You get 10% off today.", "hi")))
        self.assertEqual(send_check.offer_problems("10% off", None), [])
        passed, feedback = send_check.check("You get 10% off today.", "hi", offers=offers.for_check(offers.demo(), ()))
        self.assertFalse(passed)
        self.assertIn(send_check.OFFERS_RULE, feedback)

    def test_the_prompt_holds_the_rule_it_is_checked_on(self):
        self.assertNotIn(send_check.OFFERS_RULE, send_check.prompt_rules())
        self.assertIn(send_check.OFFERS_RULE, send_check.prompt_rules(offers=True))
        self.assertIn(send_check.OFFERS_RULE, loop.system_prompt(stages.get("asking"), [])["content"])
        token = offers.OFFERS.set(offers.EMPTY)
        try:
            self.assertNotIn(send_check.OFFERS_RULE, loop.system_prompt(stages.get("asking"), [])["content"])
        finally:
            offers.OFFERS.reset(token)

    def test_a_discount_a_tool_gave_is_an_amount(self):
        self.assertIn("discount", send_check.AMOUNT_KEYS)
        self.assertEqual(send_check.amounts_in({"discounts": [{"offer": "card_5", "discount": 1395}]}), {1395})


class FactCheck(unittest.TestCase):
    """arena/factcheck.py under the store's offers: free delivery makes the zone fees (60, 85) no facts."""

    def setUp(self):
        clean_env(self)

    def names(self, reply, customer=""):
        return [f["check"] for f in factcheck.check(reply, customer)]

    def test_a_zone_fee_under_free_delivery_fails(self):
        self.assertIn("delivery", self.names("Delivery to Cairo is 60 EGP and takes 1 to 2 days."))
        self.assertIn("delivery", self.names("Delivery to Aswan is 85 EGP."))
        self.assertIn("price", self.names("It is 16,500 EGP plus 60 EGP delivery to Cairo."))
        self.assertIn("price", self.names("Your total is 16560 EGP."))          # a price plus the old fee
        self.assertEqual(self.names("Delivery to Cairo is free and takes 1 to 2 days."), [])
        self.assertEqual(self.names("The Phantom 6 Elite is 16,500 EGP with free delivery."), [])

    def test_with_no_offers_the_zone_fees_stay_facts(self):
        token = offers.OFFERS.set(offers.EMPTY)
        self.addCleanup(offers.OFFERS.reset, token)
        self.assertEqual(self.names("Delivery to Cairo is 60 EGP and takes 1 to 2 days."), [])
        self.assertEqual(self.names("Delivery to Aswan is 85 EGP."), [])
        self.assertEqual(self.names("Your total is 16560 EGP."), [])
        self.assertIn("delivery", self.names("Delivery to Cairo is 85 EGP."))   # the other zone's fee


class ExamTotals(unittest.TestCase):
    """reflection/exam.py answer passes the chat's tool amounts to the send check (fix D): a total that adds
    up amounts a tool gave passes, a made-up one fails."""

    def setUp(self):
        clean_env(self)
        store._cache.update(at=0.0, items=None)
        self.addCleanup(store._cache.update, at=0.0, items=None)

    def did(self, reply):
        s = {"id": 1, "stage": "asking", "expect": {},
             "turns": [{"customer": "How much is the Phantom 6 Elite with a name printing?"}]}
        model = FakeModel(call("store", query="phantom"), call("store", query="printing"), say(reply))
        return exam.answer(s, None, model=model)

    def test_a_sum_of_tool_amounts_passes_and_a_made_up_total_fails(self):
        good = self.did("The Phantom 6 Elite is 16,500 EGP and the printing 400 EGP, 16,900 EGP in all.")
        self.assertEqual([n for n, _ in good["tools"]], ["store", "store"])
        self.assertNotIn(16900, good["amounts"])                 # no tool gave the total itself
        self.assertNotIn("amounts", good["problems"])
        bad = self.did("The Phantom 6 Elite is 16,500 EGP and the printing 400 EGP, 16,950 EGP in all.")
        self.assertIn("16950", bad["problems"]["amounts"])

    def test_an_offer_no_tool_gave_is_an_exam_problem(self):
        s = {"id": 1, "stage": "asking", "expect": {}, "turns": [{"customer": "Any discount?"}]}
        did = exam.answer(s, None, model=FakeModel(say("Yes, 10% off today.")))
        self.assertIn("10%", did["problems"]["offers"])


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

    def test_t2_a_made_up_discount_is_refused_and_a_given_offer_is_sent(self):
        bad, good = "You get 10% off today on the Phantom 6.", "You can pay through valU, 3 months, no interest."
        model = FakeModel(say(bad), call("store", query="phantom"), say(good))
        r = self.turn(model, "Is there any discount on the Phantom 6?")
        self.assertEqual((r.outcome, r.reply), ("replied", good))
        self.assertEqual([t for _, t in self.out.sent], [good])
        rows = self.results.for_chat(self.cid)
        self.assertEqual([x["outcome"] for x in rows], ["check_failed", "replied"])
        self.assertIn("10%", rows[0]["detail"]["feedback"])
        self.assertIn(send_check.OFFERS_RULE, rows[0]["detail"]["feedback"])

    def test_t2_an_offer_named_before_any_tool_gave_it_is_refused(self):
        model = FakeModel(*[say("Delivery is free delivery anywhere in Egypt.")] * loop.MAX_FAILED_CHECKS)
        r = self.turn(model, "How much is delivery?")
        self.assertNotEqual(r.outcome, "replied")
        self.assertEqual(self.out.sent, [])
        rows = [x for x in self.results.for_chat(self.cid) if x["outcome"] == "check_failed"]
        self.assertEqual(len(rows), loop.MAX_FAILED_CHECKS)
        self.assertIn("free_delivery", rows[0]["detail"]["feedback"])

    def test_t2_the_delivery_tool_gives_the_free_delivery_offer(self):
        good = "Delivery to Giza is free delivery, 1 to 2 days."
        model = FakeModel(call("delivery", governorate="Giza"), say(good))
        r = self.turn(model, "How much is delivery to Giza?")
        self.assertEqual((r.outcome, r.reply), ("replied", good))
        self.assertEqual(tool_results(model)[0]["offer_id"], "free_delivery")
        self.assertEqual(loop.store_offers(self.chats, self.cid), {"free_delivery"})

    def test_t3_the_quote_s_discount_and_percent_may_be_quoted(self):
        self.chats.set_stage(self.cid, "ordering")
        args = {"items": ITEMS, "quote": True, "payment": "card", "governorate": "Giza"}
        good = "With the card's 5% you save 1,395 EGP, so the total is 26,505 EGP with free delivery."
        model = FakeModel(tool_call("draft_order", args), say("With the card you get 10% off, 25,110 EGP."),
                          say(good))
        r = self.turn(model, "Phantom 6 Elite and Pro in 42 with a name printing, paying by card. How much?")
        self.assertEqual((r.outcome, r.reply), ("replied", good))
        feedback = self.results.for_chat(self.cid)[0]["detail"]["feedback"]
        self.assertIn("10%", feedback)

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

    def test_t4_a_made_up_offer_is_refused_and_its_own_offer_passes_after_the_tool(self):
        offers.write(self.folder, OWN)
        agent = turn.load(self.folder)
        good = "The Phantom 6 is in stock, and there is a cap deal with it."
        got, model = self.run_turn(agent, say("The Phantom 6 is 10% off today."), say("Ask about our cap deal."),
                                   tool_call("store", {"query": "phantom"}), say(good))
        self.assertEqual((got.outcome, got.reply), ("replied", good), got)
        retries = [m["content"] for m in model.calls[-1]["messages"] if m["role"] == "user"][1:]
        self.assertIn("10%", retries[0])
        self.assertIn("cap_deal", retries[1])
        self.assertIn(send_check.OFFERS_RULE, model.calls[0]["messages"][0]["content"])

    def test_an_agent_with_no_offers_gets_none_of_the_store_datas(self):
        agent = turn.load(self.folder)
        self.assertIsNone(agent.offers)
        got, model = self.run_turn(agent, tool_call("store", {"query": "phantom"}), say("The Phantom 6 is in stock."))
        shown = tool_results(model)[0]
        self.assertNotIn("offers", shown)
        self.assertNotIn(offers.PROMPT_LINE, model.calls[0]["messages"][0]["content"])
        self.assertNotIn(send_check.OFFERS_RULE, model.calls[0]["messages"][0]["content"])
        self.assertIsNone(turn._offers_for(agent, ["valu_3m"]))     # not held to the store data's offers

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
