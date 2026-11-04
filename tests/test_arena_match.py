"""Arena match, fact checks and verdict (new, 2026-10-30), on the fake model and the demo store."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from arena import factcheck, match, verdict
from tests.fake_model import BUY, PRICE, Buyer, FakeModel, Seller, clean_env, say

CARD = json.loads((Path(__file__).resolve().parent.parent / "demo" / "personas" / "cards" / "persona-01.json")
                  .read_text(encoding="utf-8"))


def store_items():
    from kit.tools import store
    return store.catalogue()


def checker(reply, customer_text, ran, orders):
    return factcheck.check(reply, customer_text, ran, orders)


class Match(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_won_only_when_the_agent_places_the_order_quoting_the_yes(self):
        """Strict win rule (2026-10-30): the customer's yes and details are not a win until draft_order places it."""
        customer, agent = Buyer(), Seller()
        m = match.play(CARD, agent_model=agent, customer_model=customer, checker=checker, stop=verdict.closed)
        self.assertEqual([t["customer"] for t in m["turns"]], ["How much is the Mercurial Vapor 17 Elite?", BUY, "yes"])
        self.assertEqual(m["turns"][0]["replies"], [PRICE])
        self.assertEqual([t["order"] for t in m["turns"]], [False, False, True])
        self.assertEqual((m["ended"], m["order"]), ("order", True))
        v = verdict.judge(m)
        self.assertEqual((v["won"], v["why"]), (True, verdict.WON_ORDER), v)
        self.assertEqual(v["quote"], {"turn": 3, "who": "customer", "text": "yes"})
        # the agent saw the customer's line; the customer saw the agent's reply as the other side
        self.assertEqual(agent.calls[0]["messages"][-1]["content"], "How much is the Mercurial Vapor 17 Elite?")
        roles = [(x["role"], x["content"]) for x in customer.calls[1]["messages"][2:]]
        self.assertEqual(roles, [("assistant", "How much is the Mercurial Vapor 17 Elite?"), ("user", PRICE)])

    def test_a_yes_after_the_price_with_no_order_placed_is_no_win(self):
        customer = FakeModel(say("How much is the Mercurial Vapor 17 Elite?"), say("ok I'll take it"))
        agent = FakeModel(say(PRICE), say("Great. Which governorate are you in?"))
        m = match.play(CARD, agent_model=agent, customer_model=customer, max_turns=2, checker=checker,
                       stop=verdict.closed)
        self.assertEqual(len(m["turns"]), 2)  # the yes did not end the match: no order was placed
        v = verdict.judge(m)
        self.assertEqual((v["won"], v["why"]), (False, verdict.OUT_OF_TURNS), v)
        self.assertFalse(verdict.closed(m["turns"]))

    def test_customer_leaves_lost_quotes_the_reply_it_left_after(self):
        customer = FakeModel(say("How much is the Mercurial Vapor 17 Elite?"), say("[LEAVE]"))
        agent = FakeModel(say("The Mercurial Vapor 17 Elite is 16,500 EGP."))
        m = match.play(CARD, agent_model=agent, customer_model=customer, checker=checker)
        self.assertEqual(m["ended"], "left")
        v = verdict.judge(m)
        self.assertFalse(v["won"])
        self.assertEqual(v["why"], verdict.LEFT)
        self.assertEqual(v["quote"]["text"], "The Mercurial Vapor 17 Elite is 16,500 EGP.")

    def test_a_store_price_on_the_wrong_product_passes_the_send_check_but_loses_the_match(self):
        customer = FakeModel(say("How much is the Mercurial Vapor 17 Elite?"), say("ok I'll take it"))
        agent = FakeModel(say("The Mercurial Vapor 17 Elite is 11,000 EGP."), say("Great. Which governorate are you in?"))
        m = match.play(CARD, agent_model=agent, customer_model=customer, max_turns=2, checker=checker)
        self.assertEqual(m["turns"][0]["failed"][0]["check"], "price")
        v = verdict.judge(m)
        self.assertFalse(v["won"])
        self.assertTrue(v["why"].startswith(verdict.FAILED), v)
        self.assertEqual(v["quote"], {"turn": 1, "who": "agent", "text": "The Mercurial Vapor 17 Elite is 11,000 EGP."})
        self.assertFalse(verdict.judge(m, facts=False)["won"])  # no order placed, so no win either way
        m = match.play(CARD, agent_model=Seller("The Mercurial Vapor 17 Elite is 11,000 EGP."), customer_model=Buyer(),
                       checker=checker, stop=verdict.closed)
        self.assertTrue(m["order"])
        self.assertTrue(verdict.judge(m)["why"].startswith(verdict.FAILED))
        self.assertTrue(verdict.judge(m, facts=False)["won"])  # the setting turns the fact rule off

    def test_opening_given_is_used_as_it_is(self):
        customer = FakeModel(say("[leave]"))
        agent = FakeModel(say("The Mercurial Vapor 17 Elite is 16,500 EGP."))
        m = match.play(CARD, agent_model=agent, customer_model=customer, opening="Price of the Mercurial Vapor 17 Elite?")
        self.assertEqual(match.first_line(m), "Price of the Mercurial Vapor 17 Elite?")
        self.assertEqual(len(customer.calls), 1)


def raises(why):
    """A fake model script item that raises the model's own error."""
    from kit.model import ModelError

    def item(messages, tools):
        raise ModelError(why)
    return item


class ModelFault(unittest.TestCase):
    """Review round 1, note 13: a model that does not answer voids the match, never a loss."""

    def setUp(self):
        clean_env(self)

    def test_the_agent_model_not_answering_voids_the_match(self):
        customer = FakeModel(say("How much is the Mercurial Vapor 17 Elite?"))
        m = match.play(CARD, agent_model=FakeModel(raises("the route is busy")), customer_model=customer,
                       checker=checker)
        self.assertEqual((m["ended"], m["error"], len(m["turns"])), (match.VOID, match.AGENT_SILENT, 1))
        self.assertEqual(m["turns"][0]["outcome"], "model_error")
        self.assertEqual(len(customer.calls), 1)  # the match stops there; the customer is not asked again

    def test_the_customer_model_not_answering_voids_the_match(self):
        first = match.play(CARD, agent_model=FakeModel(), customer_model=FakeModel(raises("the route is busy")))
        self.assertEqual((first["ended"], first["error"], first["turns"]), (match.VOID, "the route is busy", []))
        later = match.play(CARD, agent_model=FakeModel(say("The Mercurial Vapor 17 Elite is 16,500 EGP.")),
                           customer_model=FakeModel(say("How much is the Mercurial Vapor 17 Elite?"), raises("cut off")),
                           checker=checker)
        self.assertEqual((later["ended"], later["error"], len(later["turns"])), (match.VOID, "cut off", 1))
        self.assertNotIn("error", match.play(CARD, agent_model=FakeModel(say("The Mercurial Vapor 17 Elite is 16,500 EGP.")),
                                             customer_model=FakeModel(say("How much?"), say("[leave]"))))


class KeysOut(unittest.TestCase):
    """Review round 1, finding 10: a match runs with no Shopify keys and no operator number, even
    when they are set, so it never reads the real store or messages the team; they are back after."""

    def test_the_match_hides_the_store_keys_and_the_operator_number(self):
        given = {"SHOPIFY_STORE": "probe-not-a-store", "SHOPIFY_TOKEN": "probe-token",
                 "OPERATOR_WHATSAPP": "201000000098"}
        clean_env(self, **given)
        seen = []

        def look(messages, tools):
            seen.append({k: os.environ.get(k) for k in given})
            return say("The Mercurial Vapor 17 Elite is 16,500 EGP.")

        m = match.play(CARD, agent_model=FakeModel(look), customer_model=FakeModel(say("[leave]")),
                       opening="How much is the Mercurial Vapor 17 Elite?")
        self.assertEqual(m["ended"], "left")
        self.assertEqual(seen, [dict.fromkeys(given)])
        self.assertEqual({k: os.environ.get(k) for k in given}, given)


class Facts(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def names(self, reply, customer=""):
        return [f["check"] for f in factcheck.check(reply, customer)]

    def test_stock(self):
        # A store that tracks stock: Phantom 6 Elite 45 is out, Elite 43 and Pro 45 are in stock.
        from unittest import mock
        from kit.tools import store
        items = [{"title": "Nike Phantom 6", "type": "Football Boots", "variants": [
            {"tier": "Elite", "size": "45", "price": "16500", "stock": "out"},
            {"tier": "Elite", "size": "43", "price": "16500", "stock": "in stock"},
            {"tier": "Pro", "size": "45", "price": "11000", "stock": "in stock"}]}]
        with mock.patch.object(store, "catalogue", return_value=items):
            self.assertEqual(self.names("The Phantom 6 Elite in size 45 is available."), ["stock"])
            self.assertEqual(self.names("The Phantom 6 Elite in size 43 is available."), [])
            self.assertEqual(self.names("The Phantom 6 Pro in size 45 is sold out."), ["stock"])
            self.assertEqual(self.names("The Phantom 6 Elite in size 45 is sold out."), [])
        # A store with no stock level: saying it is in stock fails as no stock data (Arena run 20261104T143545,
        # cause 7), and saying it is out fails nothing. The demo store has one only from its sample layer.
        store._cache.update(at=0.0, items=None)
        self.addCleanup(store._cache.update, at=0.0, items=None)
        with mock.patch.object(store, "DEMO_SAMPLE_STOCK", Path("/nonexistent/sample-stock.json")):
            self.assertEqual(self.names("The Phantom 6 Elite in size 45 is available."), ["stock"])
            self.assertEqual(self.names("The Phantom 6 Elite in size 45 is sold out."), [])
        store._cache.update(at=0.0, items=None)
        level = [v["stock"] for i in store.catalogue() if i["title"] == "Nike Phantom 6" for v in i["variants"]
                 if (v["tier"], v["size"]) == ("Elite", "45")]
        self.assertEqual(self.names("The Phantom 6 Elite in size 45 is available."), ["stock"] if level == ["out"] else [])

    def test_size(self):
        self.assertEqual(self.names("The Phantom 6 Elite comes in size 43."), [])
        self.assertEqual(self.names("The Phantom 6 Elite comes in size 55."), ["size"])

    def test_a_product_is_named_with_or_without_the_maker(self):
        items = store_items()
        for text, titles in (("the Mercurial Vapor 17 Elite", ["Nike Mercurial Vapor 17"]),
                             ("Nike Mercurial Vapor 17", ["Nike Mercurial Vapor 17"]),
                             ("the Superfly 11", []),   # all but the maker is "Mercurial Superfly"
                             ("the Mercurial Superfly 11 Pro", ["Nike Mercurial Superfly 11"]),
                             ("الـ Phantom 6 Elite", ["Nike Phantom 6"]),
                             ("F50 Messi El Ultimo Tango League", ["Adidas F50 Messi El Ultimo Tango"])):
            with self.subTest(text=text):
                self.assertEqual([i["title"] for i in factcheck.products_named(text, items)], titles)

    def test_a_price_must_be_the_named_tiers(self):
        # The tier rule (DECISIONS 39): the Pro price given for an Elite boot is a wrong price.
        self.assertEqual(self.names("The Mercurial Vapor 17 Elite is 16,500 EGP."), [])
        self.assertEqual(self.names("The Mercurial Vapor 17 Elite is 11,000 EGP."), ["price"])
        self.assertEqual(self.names("The Mercurial Superfly 11 Elite is 16,500 EGP."), ["price"])  # 20,000
        # A list line, one tier a clause, passes.
        self.assertEqual(self.names("The Mercurial Vapor 17 is 16,500 EGP for the Elite, 11,000 for the Pro "
                                    "and 7,500 for the Academy."), [])
        self.assertEqual(self.names("الـ Phantom 6: الـ Elite بـ 16500 جنيه، والـ Pro بـ 11000، والـ Academy بـ 7500."), [])
        # Each amount sits in the reply's tiers, but in the wrong clause: the clause rule catches it.
        failed = factcheck.check("The Mercurial Vapor 17 Elite is 11,000 EGP, the Pro is 16,500 EGP.")
        self.assertEqual([f["check"] for f in failed], ["price", "price"])
        self.assertIn("not the Elite price of Nike Mercurial Vapor 17", failed[0]["why"])
        self.assertIn("not the Pro price of Nike Mercurial Vapor 17", failed[1]["why"])
        # A reply that names no tier reads the tier from the customer's line.
        ask = "How much is the Mercurial Vapor 17 Elite?"
        self.assertEqual(self.names("It is 16,500 EGP.", ask), [])
        self.assertEqual(self.names("It is 11,000 EGP.", ask), ["price"])
        self.assertEqual(self.names("It is 16,500 EGP plus 60 EGP delivery to Cairo.", ask), [])
        # The printing has no tier: its price stands next to a tier's.
        self.assertEqual(self.names("The Phantom 6 Elite is 16,500 EGP, and the name printing is 400 EGP."), [])

    def test_a_bare_catalogue_size_fits(self):
        """The catalogue holds bare sizes ("43"), not ranges: a size word and its number fit one,
        in Arabic or English, and a number no product comes in is still a bad size."""
        self.assertEqual(factcheck._eu("43"), (43, 43))
        self.assertEqual(factcheck._eu("EU 43"), (43, 43))
        self.assertEqual(factcheck._eu("M (EU 42-45)"), (42, 45))
        for size in ("M", "143", "", None):
            self.assertIsNone(factcheck._eu(size), size)
        self.assertEqual(self.names("مقاس 43 متاح"), [])
        self.assertEqual(self.names("size 43 is in stock"), [])
        self.assertEqual(self.names("The Phantom 6 Elite, size 43."), [])
        self.assertEqual(self.names("size 55 is in stock"), ["size"])
        self.assertEqual(self.names("مقاس 55 متاح"), ["size"])
        self.assertEqual(self.names("The Tiempo Maestro Academy comes in size 38."), ["size"])  # 39 to 46 only

    def test_delivery(self):
        self.assertEqual(self.names("Delivery to Cairo is 60 EGP and takes 1 to 2 days."), [])
        self.assertEqual(self.names("Delivery to Cairo is 85 EGP."), ["delivery"])
        self.assertEqual(self.names("Delivery to Alexandria takes 1 to 2 days."), ["delivery"])

    def test_tool_amount_counts(self):
        self.assertEqual(self.names("Your total is 16560 EGP."), [])  # one price plus one fee
        self.assertEqual(factcheck.check("Your total is 1898 EGP.", "", [("draft_order", {"total": "1898"})]), [])
        self.assertEqual([f["check"] for f in factcheck.check("Your total is 1898 EGP.")], ["price"])


class Prompt(unittest.TestCase):
    def test_generic_when_no_file(self):
        self.assertEqual(match.load_prompt(None), match.GENERIC_PROMPT)

    def test_file_inside_the_repo_is_refused(self):
        with self.assertRaises(match.PromptRefused):
            match.load_prompt(Path(match.__file__))

    def test_private_file_is_read_and_filled(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "customer.txt"
            p.write_text("Worry $worry, patience $patience, keep $other. $unwinnable", encoding="utf-8")
            text = match.load_prompt(p)
        filled, _ = match.fill(text, dict(CARD, unwinnable=True, why_unwinnable="just browsing"), match.random.Random(1))
        self.assertIn("Worry size, patience 0, keep $other.", filled)
        self.assertIn("will not buy", filled)
        plain, _ = match.fill(text, CARD, match.random.Random(1))
        self.assertNotIn("will not buy", plain)


class Verdict(unittest.TestCase):
    def test_order_placed_wins(self):
        m = {"turns": [{"n": 1, "customer": "yes", "replies": ["Order #1001 placed."], "failed": [], "order": True}],
             "ended": "order"}
        self.assertEqual(verdict.judge(m)["why"], verdict.WON_ORDER)

    def test_confirm_before_any_price_is_no_win(self):
        m = {"turns": [{"n": 1, "customer": "I'll take it", "replies": ["Which size?"], "failed": []}], "ended": "turns"}
        self.assertFalse(verdict.judge(m)["won"])


class AgentClaim(unittest.TestCase):
    """In a match the agent is the store: its own "order placed" words are never a win (review round 1,
    finding 2). Only the customer's address or yes after a price, or an order a tool made, wins."""

    def setUp(self):
        clean_env(self)

    def test_the_agent_saying_the_order_is_placed_loses_in_english_and_arabic(self):
        for first, price, think, claim in (
                ("How much is the Mercurial Vapor 17 Elite?", "The Mercurial Vapor 17 Elite is 16,500 EGP.", "hmm, let me think about it",
                 "Your order is confirmed."),
                ("بكام جزمة الميركوريال فيبور الإيليت؟", "الـ Mercurial Vapor 17 Elite بـ 16500 جنيه", "هفكر شوية", "تم تسجيل الطلب")):
            with self.subTest(claim=claim):
                m = match.play(CARD, agent_model=FakeModel(say(price), say(claim)), customer_model=FakeModel(say(think)),
                               opening=first, max_turns=2, checker=checker, stop=verdict.closed)
                self.assertEqual([t["replies"] for t in m["turns"]], [[price], [claim]])
                self.assertFalse(m["order"])
                self.assertEqual([f["check"] for f in m["turns"][1]["failed"]], ["order"])
                v = verdict.judge(m)
                self.assertFalse(v["won"], v)
                self.assertTrue(v["why"].startswith(f"{verdict.FAILED}: order"), v)
                self.assertEqual(v["quote"], {"turn": 2, "who": "agent", "text": claim})
                off = verdict.judge(m, facts=False)  # with the fact checks off the claim still wins nothing
                self.assertFalse(off["won"], off)
                self.assertEqual(off["why"], verdict.OUT_OF_TURNS)
                self.assertFalse(verdict.closed(m["turns"]))

    def test_the_order_check_passes_only_with_an_order_a_tool_made(self):
        made = ("draft_order", {"ok": True, "step": "created", "order": "#1001", "total": "16560"})
        summary = ("draft_order", {"ok": True, "step": "summary", "total": "16560", "code": "x1"})
        self.assertEqual(factcheck.check("Your order is confirmed.", "", [made]), [])
        for ran in ([], [summary], [("find_order", {"ok": True, "orders": [{"order": "#1001"}]})],
                    [("draft_order", {"ok": False, "step": "created", "order": "#1001"})]):
            self.assertEqual([f["check"] for f in factcheck.check("Your order is confirmed.", "", ran)], ["order"], ran)
        self.assertEqual(factcheck.check("Shall I confirm the order?", ""), [])  # a question claims nothing
        self.assertIn("order", factcheck.CHECKS)

    def test_every_form_of_an_order_claim_fails_and_a_condition_claims_nothing(self):
        """Review round 2, findings 1 and 2: the order check has its own claim words, wider than the labeller's."""
        for claim in ("Your order is confirmed.", "تم تسجيل الطلب", "تم تأكيد طلبك", "تم تسجيل طلبك",
                      "تم تأكيد طلبك يا فندم وهيوصلك خلال يومين", "طلبك اتسجل", "تمام، الاوردر اتأكد", "تم الطلب",
                      "Order placed!", "I've placed your order.", "Done, your order is booked.",
                      "We've confirmed your order.", "Your order's confirmed.", "Your order has been placed.",
                      "The price is 16500 EGP. Your order is confirmed."):
            self.assertEqual([f["check"] for f in factcheck.check(claim, "")], ["order"], claim)
        for line in ("If you reply yes, your order is confirmed.", "Reply yes and your order is confirmed.",
                     "Once you confirm, your order is placed.", "As soon as you say yes, your order is confirmed.",
                     "Just say yes and your order is placed with free delivery.", "لو موافق، تم تأكيد الطلب",
                     "Your order is confirmed once you reply yes.", "Your order is not confirmed yet.",
                     "طلبك لسه متأكدش", "Is your order confirmed?"):
            self.assertEqual(factcheck.check(line, ""), [], line)

    def test_words_outside_the_claims_clause_do_not_hide_it(self):
        """Review round 3 (reviewer and red team): a question, a negation or a condition in another clause
        no longer hides a true claim, and the closing forms they found are read as claims."""
        for claim in ("Your order is confirmed, anything else I can help with?",
                      "Your order is confirmed \U0001F389 can I help with anything else?",
                      "تم تأكيد طلبك، تحب حاجة تانية؟", "تمام يا فندم تم تسجيل طلبك وهيوصلك خلال يومين، محتاج حاجة تانية؟",
                      "Your order is confirmed, don't worry about a thing.",
                      "Your order is confirmed, you won't pay anything until delivery.",
                      "Your order is confirmed, if you need anything just ask.",
                      "Your order is confirmed and it arrives after the weekend.",
                      "Your order is confirmed, it ships when the courier comes by.",
                      "Your order is placed, no need to pay now, not until it arrives.",
                      "Your order is confirmed, we'll call you once it ships.", "تم تأكيد طلبك ومش هتدفع غير عند الاستلام",
                      "تم تسجيل طلبك، لو محتاج أي حاجة كلمني", "تم تأكيد طلبك وهيوصلك بعد ما المندوب يكلمك",
                      "Your order is all set.", "Your order is successfully placed.",
                      "Your order has been successfully confirmed.", "I've placed an order for you.",
                      "I have created an order for you.", "Your order #1043 is confirmed.", "Order: confirmed.",
                      "We've received your order and it's on its way.", "Your purchase is confirmed.",
                      "تم حجز طلبك", "تم تسجيل الطلبية", "الأوردر بتاعك اتأكد", "اتعمل الطلب", "سجلتلك الطلب يا فندم",
                      "خلاص أكدتلك الأوردر", "طلبك في الطريق", "تم تأكيد الحجز", "اتأكد الطلب",
                      "el order et2aked", "tmam, el order etsagel", "talabak etsagel", "tm ta2keed el order",
                      "3amaltlak el order", "order-ak et2aked ya fandem", "Total 2.450 EGP, your order is confirmed."):
            self.assertTrue(factcheck.claims_order(claim), claim)
            self.assertIn("order", [f["check"] for f in factcheck.check(claim, "")], claim)  # 2.450 also fails price

    def test_a_condition_scoped_to_the_claim_claims_nothing(self):
        """Review round 3: each line holds an order-made phrase; only the condition next to it vetoes it."""
        for line in ("If you pay 2.450 EGP, your order is confirmed.", "When you pay 1.5k your order is placed.",
                     "Should I go ahead? Then your order is confirmed.", "Say the word. Your order is confirmed right after.",
                     "Your order is confirmed only after you send the address.",
                     "Before your order is confirmed I need your address.", "To get your order confirmed, send your address.",
                     "Nothing is placed yet. Reply yes. Your order is confirmed then.", "Your order is confirmed after payment.",
                     "I can have your order placed today.", "Can I get your order confirmed?", "Is your order confirmed?",
                     "If you reply yes, your order is confirmed.", "لو موافق، تم تأكيد الطلب"):
            self.assertTrue(factcheck.ORDER_CLAIM.search(factcheck.clean.normalize(line)), line)
            self.assertFalse(factcheck.claims_order(line), line)

    def test_a_lie_after_the_customers_yes_loses_the_match(self):
        """Review round 3, probe p2: the agent says the order is made with no tool order, after the yes."""
        for first, price, yes, lie in (
                ("How much is the Mercurial Vapor 17 Elite?", PRICE, "ok I'll take it", "Your order is confirmed, anything else?"),
                ("How much is the Mercurial Vapor 17 Elite?", PRICE, "ok I'll take it", "Your order is all set."),
                ("بكام جزمة الميركوريال فيبور الإيليت؟", "الـ Mercurial Vapor 17 Elite بـ 16500 جنيه", "تمام أكده", "تم حجز طلبك")):
            with self.subTest(lie=lie):
                m = match.play(CARD, agent_model=FakeModel(say(price), say(lie), say("Thanks!")),
                               customer_model=FakeModel(say(yes), say("[leave]")), opening=first, max_turns=3,
                               checker=checker, stop=verdict.closed)
                v = verdict.judge(m)
                self.assertFalse(m["order"])
                self.assertEqual((v["won"], v["quote"]["text"]), (False, lie), v)
                self.assertTrue(v["why"].startswith(f"{verdict.FAILED}: order"), v)

    def test_a_tool_order_still_wins(self):
        m = {"turns": [{"n": 1, "customer": "How much is the Mercurial Vapor 17 Elite?", "replies": ["The Mercurial Vapor 17 Elite is 16,500 EGP."],
                        "failed": []},
                       {"n": 2, "customer": "yes", "replies": ["Your order is confirmed."], "failed": [], "order": True}],
             "ended": "order"}
        self.assertEqual(verdict.judge(m)["why"], verdict.WON_ORDER)


def setUpModule():
    # These pin a store with no offers, where the zone fees (60, 85) are facts; under free delivery they are
    # not (tests/test_offers_paths.py FactCheck).
    global _NO_OFFERS
    from kit import offers
    _NO_OFFERS = offers.OFFERS.set(offers.EMPTY)


def tearDownModule():
    from kit import offers
    offers.OFFERS.reset(_NO_OFFERS)


if __name__ == "__main__":
    unittest.main()
