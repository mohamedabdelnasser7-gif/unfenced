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


class EachSizeTakesItsOwnStockWord(unittest.TestCase):
    """One sentence that lists sizes in stock and out (live run 20261104T170549): each size takes the stock
    word beside it, never the out word of another size; a question claims nothing."""
    ITEMS = [{"title": "Nike Mercurial Vapor 17", "type": "Football Boots", "variants": [
        {"tier": "Elite", "size": s, "price": "16500", "stock": st} for s, st in
        (("39", "in stock"), ("40", "in stock"), ("42", "out"), ("43", "out"), ("44", "few left"))] + [
        {"tier": "Pro", "size": "42", "price": "11000", "stock": "in stock"}]}]

    def stock(self, reply):
        from arena import factcheck
        from kit.tools import store
        with mock.patch.object(store, "catalogue", return_value=self.ITEMS):
            return [f["why"] for f in factcheck.check(reply) if f["check"] == "stock"]

    def test_right_lists_pass(self):
        for reply in ("Nike Mercurial Vapor 17 Elite: sizes 39, 40 in stock, size 44 only a few are left, size 43 out of stock.",
                      "Nike Mercurial Vapor 17 Elite size 39 in stock, 40 in stock, 42 out of stock.",
                      "Nike Mercurial Vapor 17 فئة Elite مقاس 42 حاليا غير متوفر، والمتاح من Elite هو مقاسات 40 و41",
                      "Nike Mercurial Vapor 17 Elite size 42 is out. Do you want the Elite size 42 in stock elsewhere?"):
            with self.subTest(reply=reply):
                self.assertEqual(self.stock(reply), [])

    def test_wrong_sizes_in_a_list_still_fail(self):
        self.assertEqual(self.stock("Nike Mercurial Vapor 17 Elite: size 42 in stock, size 40 out of stock."),
                         ["Nike Mercurial Vapor 17 Elite 42 is out, the reply says available",
                          "Nike Mercurial Vapor 17 Elite 40 is in stock, the reply says out"])
        self.assertEqual(self.stock("Nike Mercurial Vapor 17 فئة Elite مقاس 40 غير متوفر، والمتاح مقاس 43"),
                         ["Nike Mercurial Vapor 17 Elite 40 is in stock, the reply says out",
                          "Nike Mercurial Vapor 17 Elite 43 is out, the reply says available"])


class LostAfterTheLargerAsk(unittest.TestCase):
    """Live run 20261104T172523: a cut answer was asked again larger, that ask got a network failure, and the
    match was dropped. Now that ask is asked once more too: at most three sends a call."""

    def test_cut_then_lost_then_good(self):
        import secrets
        import urllib.error
        from kit import model as kit_model
        from tests.test_judge_keys import HI, META_URL, Transport, env_with, ok
        env_with(self, META_API_KEY=secrets.token_urlsafe(16))
        t = Transport(meta=[ok("half", reason="length"), urllib.error.URLError("down"), ok("whole")])
        with self.assertLogs("kit.model", level="WARNING"):
            got = kit_model.Model(opener=t).chat(HI, max_tokens=1500, whole=True)
        self.assertEqual((got["content"], t.hosts()), ("whole", [META_URL] * 3))
        budgets = [json.loads(r.data)["max_completion_tokens"] for r in t.seen]
        self.assertEqual(budgets, [1500, 4000, 4000])


class JudgeSeesWhatTheToolsReturned(unittest.TestCase):
    """With no sample file, the judge's records are what the agent's tools returned in the case."""

    def test_the_tool_results_go_to_the_judge_as_data(self):
        from arena import good, practice
        seen = practice.seen_of([("store", {"items": [{"title": "Boot", "stock": "few left"}]}), ("take_action", {})])
        self.assertEqual(seen, [{"tool": "store", "result": {"items": [{"title": "Boot", "stock": "few left"}]}}])
        asked = []

        class Judge:
            def chat(self, messages, **k):
                asked.append(json.loads(messages[1]["content"]))
                return {"content": json.dumps({"reached": True, "broke_never": False, "turn": 1, "why": "ok"})}
        match = {"turns": [{"n": 1, "customer": "", "replies": ["Report: Boot is low."], "tools": ["store"],
                            "actions": [], "failed": [], "seen": seen}]}
        card = {"good": "a report", "never": []}
        got = good.judge(match, card, Judge(), plug=None, data=None)
        self.assertTrue(got["won"])
        self.assertEqual(asked[0]["data"], seen)
