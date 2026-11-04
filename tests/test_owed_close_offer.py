"""Two leftovers of store offers (decision 105), 2026-11-04: the Sales agent's Try again judges a card no
offer covers with the close judge, as the Arena does (arena/retry.py), and a draft order keeps the delivery
offer that set its fee (kit/tools/draft_order.py build, kit/orders.py tags). Fakes only, no network."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import retry
from kit import orders
from kit.chats import Chats
from kit.db import Db
from kit.tools import draft_order
from tests.fake_model import clean_env

ME = "201011112222"
CARD = "persona-09"
PAST = {"card": CARD, "id": "r-t01", "persona": {"id": CARD, "close": True}}
LOST = {"won": False, "why": "no sale", "quote": {"turn": 1}, "needs_close": True}
CLOSED = {"won": True, "why": "correct close", "quote": None, "close": True}


class TryAgainClose(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.items = []
        for target, value in (("saved_lost", lambda state, run, cards: {CARD: PAST}),
                              ("_write", lambda *a: self.items.append(a[3]) or a[3])):
            p = mock.patch.object(retry, target, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in (("arena.retry.gate_mod._prompt_of", lambda past: "prompt"),
                              ("arena.retry.match_mod.play", lambda *a, **k: {"ended": "turns", "turns": []}),
                              ("arena.retry.verdict.judge", lambda m, facts=True: dict(LOST))):
            p = mock.patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def go(self, judge_model):
        pool = mock.Mock()
        return retry.retry(agent="sales", run="r", cards=[CARD], state=self.state, reports=self.state, pool=pool,
                           agent_model=object(), customer_model=object(), judge_model=judge_model)

    def test_a_close_card_is_judged_by_the_close_judge(self):
        with mock.patch("arena.close.judge", return_value=dict(CLOSED)) as judge:
            results = self.go(judge_model=object())
        judge.assert_called_once()
        self.assertEqual(results, [{"card": CARD, "result": retry.WON_AGAIN, "why": "correct close"}])

    def test_with_no_judge_model_it_stays_lost_as_before(self):
        with mock.patch("arena.close.judge") as judge:
            results = self.go(judge_model=None)
        judge.assert_not_called()
        self.assertEqual(results[0]["result"], retry.STILL_LOST)

    def test_an_unreadable_judge_twice_is_not_played_never_a_loss(self):
        from arena import close as close_mod
        with mock.patch("arena.close.judge", side_effect=close_mod.Unreadable("x")) as judge:
            results = self.go(judge_model=object())
        self.assertEqual(judge.call_count, 2)
        self.assertEqual(results[0]["result"], retry.NOT_PLAYED)


class DraftKeepsTheDeliveryOffer(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)
        self.cid = self.chats.open("whatsapp", ME)

    def test_the_free_delivery_offer_rides_on_the_draft_and_the_order(self):
        ctx = mock.Mock(chats=self.chats, chat_id=self.cid)
        args = {"name": "Demo Buyer", "address": "12 Tahrir St", "governorate": "Giza",
                "items": [{"product": "Nike Phantom 6", "tier": "Elite", "size": "42", "quantity": 1}]}
        draft, problem = draft_order.build(args, ctx)
        self.assertIsNone(problem)
        self.assertEqual((draft["offer_id"], draft["fee"]), ("free_delivery", "0"))
        made = orders.Book(self.db).create(draft, self.cid, {"level": "low", "reasons": []})
        tags = json.loads(orders.Book(self.db).demo_order(made["order"])["tags"])
        self.assertIn("offer-free_delivery", tags)


class StockLineUnderItsProduct(unittest.TestCase):
    """A size line under a product's heading is about that product (Arena run 20261104T170549): "Size 42
    is out of stock" under the Vapor 17 Elite heading was checked against the Superfly 11 too."""

    def test_a_size_line_follows_the_product_named_just_before_it(self):
        from arena import factcheck
        from kit.tools import store
        items = [{"title": "Nike Mercurial Vapor 17", "type": "Football Boots", "variants": [
                     {"tier": "Elite", "size": "42", "price": "16500", "stock": "out"},
                     {"tier": "Elite", "size": "46", "price": "16500", "stock": "in stock"}]},
                 {"title": "Nike Mercurial Superfly 11", "type": "Football Boots", "variants": [
                     {"tier": "Elite", "size": "42", "price": "20000", "stock": "in stock"},
                     {"tier": "Elite", "size": "46", "price": "20000", "stock": "in stock"}]}]
        good = ("Nike Mercurial Vapor 17 Elite, 16,500 EGP:\nSize 42 is out of stock. Size 46 is in stock.\n\n"
                "Nike Mercurial Superfly 11 Elite, 20,000 EGP:\nSize 42 is in stock. Size 46 is in stock.")
        bad = ("Nike Mercurial Vapor 17 Elite, 16,500 EGP:\nSize 46 is in stock.\n\n"
               "Nike Mercurial Superfly 11 Elite, 20,000 EGP:\nSize 42 is out of stock.")
        with mock.patch.object(store, "catalogue", return_value=items):
            self.assertEqual([f for f in factcheck.check(good) if f["check"] == "stock"], [])
            self.assertEqual([f["why"] for f in factcheck.check(bad) if f["check"] == "stock"],
                             ["Nike Mercurial Superfly 11 Elite 42 is in stock, the reply says out"])
