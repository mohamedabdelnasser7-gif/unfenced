"""Fixes from red team and review t261028j round 1 (28 Oct), one class per finding.

Each test here failed before its fix. The attacks come from the red team's proof scripts and
the reviewer's probes, run offline on the fake model, in memory SQLite, with no network.
"""
import json
import time
import unittest

from channels.base import Message
from sales import loop
from kit import orders
from kit.chats import FIXED, PERSON, Chats
from kit.db import Db
from kit.limits import Limits
from kit.model import ModelError
from kit.tools import draft_order
from reflection.lessons import Lessons
from reflection.results import Results
from tests.fake_model import FakeModel, Outbox, clean_env, say
from tests.test_orders import ME, order_args, tool_call
from kit import offers

BOOTS = "Nike Mercurial Vapor 17"


def boots_args(**kw):
    """Two pairs of the Vapor 17 Elite in size 43 to Giza: 2 x 16500 and 60 delivery is 33060."""
    return order_args(**{"items": [{"product": BOOTS, "tier": "Elite", "size": "43", "quantity": 2}], "governorate": "الجيزة", **kw})


def down(messages, tools_sent):
    raise ModelError("Baseten answered 502 Bad Gateway")


def summary_reply(messages, tools_sent):
    """The model's own summary reply, with the total from the draft_order result."""
    out = next(json.loads(m["content"]) for m in reversed(messages)
               if m["role"] == "tool" and '"step": "summary"' in (m["content"] or ""))
    return say(f"الاجمالي {out['total']} جنيه، والتوصيل خلال {out['days_max']} أيام. أأكد؟")


def confirm_from_history(args):
    """The model reads the code from the summary in its history and confirms."""
    def confirm(messages, tools_sent):
        code = next(json.loads(m["content"])["code"] for m in reversed(messages)
                    if m["role"] == "tool" and '"code"' in (m["content"] or ""))
        return tool_call("draft_order", {**args, "confirm": code})
    return confirm


class TurnBase(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.results, self.out = Chats(self.db), Results(self.db), Outbox()
        self.cid = self.chats.open("whatsapp", ME)
        self.chats.set_stage(self.cid, "ordering")
        self.args = boots_args()

    def turn(self, model, text, limits=None, **kw):
        msg = Message(channel="whatsapp", customer_id=ME, text=text, **kw)
        return loop.turn(msg, chats=self.chats, model=model, lessons=Lessons(self.db), results=self.results,
                         send=self.out, limits=limits)

    def placed(self):
        return orders.Book(self.db).demo_order("#1001") is not None

    def done(self):
        return FakeModel(confirm_from_history(self.args), say("تمام، الاوردر اتسجل."))


class SummaryReplyTest(TurnBase):
    """F1: only the model's own reply that shows the draft's total is the summary the customer saw."""

    def test_control_the_summary_reply_then_a_yes_places_the_order(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")
        self.turn(self.done(), "تمام")
        self.assertTrue(self.placed())

    def test_pa1_the_model_down_line_is_not_the_summary(self):
        r1 = self.turn(FakeModel(tool_call("draft_order", self.args), down), "عايز اتنين الإيليت مقاس 43")
        self.assertEqual(r1.outcome, "model_error")
        self.assertIsNone(orders.Book(self.db).pending(self.cid))      # the line drops the summary
        self.turn(self.done(), "تمام")
        self.assertFalse(self.placed())

    def test_pa2_the_limit_line_is_not_the_summary(self):
        now = [1_000_000.0]
        lim = Limits(self.db, per_customer=1, window=600, daily=1000, customer_daily=150, clock=lambda: now[0])
        r1 = self.turn(FakeModel(tool_call("draft_order", self.args), say("never reached")), "عايز اتنين الإيليت مقاس 43",
                       limits=lim)
        self.assertEqual(r1.outcome, "limited")
        self.assertIsNone(orders.Book(self.db).pending(self.cid))
        now[0] += 700
        self.turn(self.done(), "اوك", limits=lim)
        self.assertFalse(self.placed())

    def test_fixed_lines_are_saved_with_their_name(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), down), "عايز اتنين الإيليت مقاس 43")
        lines = [s for s in self.chats.steps(self.cid) if s["role"] == "assistant" and not s["tool_calls"]]
        self.assertEqual([s["name"] for s in lines], [FIXED])

    def test_only_the_models_reply_with_the_total_counts(self):
        def steps(*rows):
            return [{"n": n, "role": role, "content": text, "tool_calls": None, "name": name}
                    for n, (role, text, name) in enumerate(rows, 1)]
        total = "33060.00"
        for rows in (
            (("assistant", "مش قادر أرد دلوقتي.", FIXED), ("user", "تمام", None)),
            (("assistant", "الاجمالي 33060 جنيه، أأكد؟", FIXED), ("user", "تمام", None)),
            (("assistant", "الاجمالي 33060 جنيه، أأكد؟", PERSON), ("user", "تمام", None)),
            (("assistant", "ده ملخص الاوردر، أأكد؟", None), ("user", "تمام", None)),
            (("assistant", "الاجمالي 33061 جنيه، أأكد؟", None), ("user", "تمام", None)),
        ):
            self.assertEqual(draft_order.answers(steps(*rows), 0, total), [], rows)
        for text in ("الاجمالي 33060 جنيه، أأكد؟", "Total 33,060 EGP. Confirm?", "الاجمالي ٣٣٠٦٠ جنيه"):
            got = draft_order.answers(steps(("assistant", text, None), ("user", "تمام", None)), 0, total)
            self.assertEqual([s["content"] for s in got], ["تمام"], text)


class IdOutbox(Outbox):
    """An outbox that answers like WhatsApp, with a message id for each send."""

    def __call__(self, to, text):
        super().__call__(to, text)
        return {"messages": [{"id": f"wamid.{len(self.sent)}"}]}


class SendCheckBase(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        from kit.tools import store
        self.amounts, self.vocab, self.sizes = set(store.price_points()), store.vocabulary(), store.size_strings()

    def check(self, reply, amounts=None):
        from kit import send_check
        customer = send_check.detect_script(reply) or "english"
        customer = {"arabic": "ازيك", "franco": "ezayak ya basha", "english": "hi there"}[customer]
        return send_check.check(reply, customer, self.amounts if amounts is None else amounts, self.vocab, self.sizes)

    def number_problems(self, reply):
        """The check's feedback about numbers only (the script rule is not under test here)."""
        fb = self.check(reply)[1]
        return [p for p in ("not in the store or delivery data", "Write every amount in digits") if p in fb]


class MaskTest(SendCheckBase):
    """F7 and review 4: masks only hide numbers shaped like what they stand for."""

    BLOCK = ("Delivery is flat 500.", "Flat 1500 for the pair.", "طلبك 1500 وهيوصلك خلال يومين",
             "Your order 1500, arrives in 2 days.", "Total: #1500", "الإجمالي # 1500", "رقم 1500",
             "Total +20 1500 0000 00", "call 010 500 12345",
             "سعر التوصيل للبيت 120", "التوصيل لحد البيت 95.", "الشحن لحد باب العمارة 85",
             "Delivery to your house 120.", "Shipping to the building 150.",
             "The total with delivery to your flat 2100.")
    PASS = ("Your order #D12 is received. The total is 16500 EGP.", "#D12 is on its way, 16500 EGP.",
            "Your total for order #1042 is 16500 EGP.", "Your order #10234 is with the courier.",
            "الأوردر #1042 اتشحن وهيوصل بكرة", "Our WhatsApp is +20 10 1234 5678.", "kalemna 3la 010 1234 5678",
            "Call us on 02 2345 6789.", "Our Alex office is on 03 4567890.", "+44 7700 900123",
            "Write to 00201012345678 or +201012345678.", "28.10", "10.30", "Hoodie 1.5k",
            "العنوان: الدقي، عمارة 125، الدور 3، شقة 12. سعر الجزمة 16500 جنيه.", "Building 125, Flat 12")

    def test_must_block(self):
        for reply in self.BLOCK:
            with self.subTest(reply=reply):
                self.assertIn("not in the store or delivery data", self.check(reply, {16500, 60, 33060})[1])

    def test_still_passes(self):
        for reply in self.PASS:
            with self.subTest(reply=reply):
                self.assertEqual(self.number_problems(reply), [])


class SpacedThousandsTest(SendCheckBase):
    """F6: a space as a thousands separator is read as one number."""

    def test_spaced_groups_read_as_one_number(self):
        from kit.send_check import prices_in
        for reply, n in (("الطباعة 1 400 جنيه", 1400), ("Total: 10 150 EGP.", 10150), ("الشحن 1 060 جنيه", 1060),
                         ("الإجمالي ١ ٤٠٠ جنيه", 1400), ("The printing is 2\u00a0400 EGP.", 2400)):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [n])
                self.assertIn("not in the store or delivery data", self.check(reply, {16500, 400, 60, 33060})[1])

    def test_every_unicode_space_joins_the_groups(self):
        import unicodedata
        from kit.send_check import prices_in
        spaces = [c for c in map(chr, range(0x3001)) if unicodedata.category(c) == "Zs"]
        self.assertEqual(len(spaces), 17)
        for sp in spaces:
            for reply in ("الطباعة 1" + sp + "400 جنيه", "الإجمالي ١" + sp + "٤٠٠ جنيه"):
                with self.subTest(space=hex(ord(sp)), reply=reply):
                    self.assertEqual(prices_in(reply), [1400])
                    self.assertIn("not in the store or delivery data", self.check(reply, {400})[1])

    def test_phone_numbers_and_small_numbers_stay_apart(self):
        for reply in ("+1 202 555 0143", "Our WhatsApp is +20 10 1234 5678.", "Call us on 02 2345 6789.",
                      "Sizes 42 43 44 are in stock.", "1 pair for 16500 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(self.number_problems(reply), [])


class CodRiskResultTest(unittest.TestCase):
    """F4: a typed courier phone never brings another number's history into what the model reads."""

    def test_the_model_reads_only_ok_and_next(self):
        from kit import tools
        from sales import stages
        from tests.test_orders import B, use
        from kit.tools import cod_risk
        clean_env(self)
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "201222222222")          # a fresh number with no history
        chats.add_step(cid, "user", content="x")
        ctx = tools.Context(cid, stages.STAGES["ordering"], chats, None, None, Outbox(), stages=stages.STAGES)
        self.assertTrue(use(draft_order, boots_args(phone="+" + B), ctx)["ok"])   # B: two refusals
        out = use(cod_risk, {}, ctx)
        self.assertEqual(set(out), {"ok", "next"})
        self.assertNotIn("Refused", json.dumps(out))


class OrderLineTest(TurnBase):
    """Review 2: an order created in a turn that then hits the limit, a model error or a crash
    is still told to the customer, with its number and total, instead of the usual line."""

    LINE = "اوردرك اتسجل برقم #1001، والإجمالي 33,060 جنيه."

    def summary(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")

    def to_customer(self):
        return [t for to, t in self.out.sent if to == ME]

    def test_a_model_error_after_the_order_was_created(self):
        self.summary()
        r = self.turn(FakeModel(confirm_from_history(self.args), down), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, r.reply), ("model_error", self.LINE))
        self.assertEqual(self.to_customer()[-1], self.LINE)
        self.assertNotIn(loop.MODEL_DOWN["arabic"], self.to_customer())
        self.assertEqual(self.chats.steps(self.cid)[-1]["name"], FIXED)
        self.assertEqual(self.results.for_chat(self.cid)[-1]["detail"]["order"], "#1001")

    def test_the_limit_after_the_order_was_created(self):
        now = [1_000_000.0]
        lim = Limits(self.db, per_customer=2, window=600, daily=1000, customer_daily=150, clock=lambda: now[0])
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43", limits=lim)
        now[0] += 700
        r = self.turn(FakeModel(confirm_from_history(self.args), say("never reached")), "تمام", limits=lim)
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, r.reply), ("limited", self.LINE))
        self.assertNotIn(loop.LIMIT_LINE["arabic"], self.to_customer())
        self.assertTrue(lim.notice_due("whatsapp:" + ME, "customer"))     # the limit line is still due

    def test_a_crash_after_the_order_was_created(self):
        self.summary()

        def crash(messages, tools_sent):
            raise RuntimeError("a bug in code")
        msg = Message(channel="whatsapp", customer_id=ME, text="yes", message_id="wamid.c2")
        self.chats.first_seen("wamid.c2")                                  # as the webhook does
        with self.assertRaises(RuntimeError):
            loop.turn(msg, chats=self.chats, model=FakeModel(confirm_from_history(self.args), crash),
                      lessons=Lessons(self.db), results=self.results, send=self.out)
        r = loop.failed_turn(msg, chats=self.chats, model=None, results=self.results, send=self.out)
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, r.reply), ("turn_failed", "Your order #1001 is placed. The total is 33,060 EGP."))

    def test_the_second_model_error_is_no_safe_reply_and_only_the_order_line_goes(self):
        self.summary()
        self.chats.add_model_error(self.cid, "down")
        before = len(self.to_customer())
        r = self.turn(FakeModel(confirm_from_history(self.args), down), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, r.reply), ("no_safe_reply", self.LINE))
        self.assertEqual(self.to_customer()[before:], [self.LINE])

    def test_three_failed_checks_are_no_safe_reply_and_only_the_order_line_goes(self):
        self.summary()
        before = len(self.to_customer())
        r = self.turn(FakeModel(confirm_from_history(self.args), say("الاجمالي 1900 جنيه."),
                                say("الاجمالي 1901 جنيه."), say("الاجمالي 1902 جنيه.")), "تمام")
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, r.reply), ("no_safe_reply", self.LINE))
        self.assertEqual(self.to_customer()[before:], [self.LINE])

    def test_franco_and_no_order_keep_the_usual_lines(self):
        self.summary()
        r = self.turn(FakeModel(confirm_from_history(self.args), down), "tamam 2aked")
        self.assertEqual(r.reply, "el order bta3ak etsagel b ra2am #1001, w el egmaly 33,060 geneh.")
        self.chats.reset_model_errors(self.cid)
        r = self.turn(FakeModel(down), "fen el order")
        self.assertEqual(r.reply, loop.MODEL_DOWN["franco"])               # a later turn: no order made in it



class NoGraph:
    """Over a limit nothing is downloaded: download fails the test."""

    def __init__(self):
        self.send = IdOutbox()

    def download(self, media_id, max_bytes):
        raise AssertionError("over a limit nothing is downloaded")


class MediaMarkTest(TurnBase):
    """Review 3: a photo or voice note that was not opened leaves a mark, so its caption is never a yes."""

    def summary(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")

    def media(self):
        return [s["media"] for s in self.chats.steps(self.cid) if s["role"] == "user"][-1]

    def test_pb_a_photo_that_was_not_opened_with_a_yes_caption_places_nothing(self):
        self.summary()
        self.turn(FakeModel(confirm_from_history(self.args), say("الصورة مفتحتش، ابعتها تاني.")), "تمام",
                  rejected_images=1)
        self.assertEqual(self.media(), [{"kind": "image", "opened": False}])
        self.assertFalse(self.placed())
        self.turn(self.done(), "تمام")                     # the earlier photo still stands between summary and yes
        self.assertFalse(self.placed())

    def test_a_voice_note_that_was_not_fetched_leaves_a_mark(self):
        self.turn(FakeModel(say("never reached")), "", audio_failed=True)
        self.assertEqual(self.media(), [{"kind": "audio", "opened": False}])

    def test_over_a_limit_a_photo_with_a_yes_caption_is_marked(self):
        from channels.whatsapp import App, Incoming
        self.summary()
        app = App(self.chats, None, Lessons(self.db), self.results, NoGraph(), limits=Limits(self.db), connected=True)
        self.chats.first_seen("wamid.p1")
        r = app.work_one(("customer", Incoming("wamid.p1", ME, 1, "image", text="تمام", media_id="111",
                                               media_mime="image/jpeg")))
        self.assertEqual(r.outcome, "limited")
        self.assertEqual(self.media(), [{"kind": "image", "opened": False}])
        self.chats.first_seen("wamid.v1")
        app.work_one(("customer", Incoming("wamid.v1", ME, 2, "audio", media_id="112", media_mime="audio/ogg")))
        self.assertEqual(self.media(), [{"kind": "audio", "opened": False}])

class RiskBeforeTakeTest(TurnBase):
    """Review 6: a cod_risk lookup that fails never loses the draft; the order goes in tagged unknown."""

    def test_a_failed_risk_lookup_still_places_the_order(self):
        from unittest import mock
        from kit.tools import cod_risk
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")
        with mock.patch.object(cod_risk, "assess", side_effect=orders.StoreError("Shopify did not answer")):
            self.turn(self.done(), "تمام")
        made = orders.Book(self.db).demo_order("#1001")
        self.assertIsNotNone(made)
        self.assertEqual(made["cod_risk"], "unknown")
        self.assertIn("cod-risk-unknown", made["tags"])
        created = [r for r in self.results.for_chat(self.cid) if r["outcome"] == "order_created"]
        self.assertEqual(created[-1]["detail"]["cod_risk"], "unknown")



class NoRedirectTest(unittest.TestCase):
    """Review 8: Shopify calls carry the token, so they go through the opener that refuses redirects.
    urllib's default opener follows a 302 on a POST as a GET and keeps the token header."""

    def setUp(self):
        clean_env(self, SHOPIFY_STORE="demo-shop.myshopify.com", SHOPIFY_TOKEN="test-token-not-real")

    def opened_by(self, call, data):
        import urllib.request
        from unittest import mock
        from tests.test_orders import _Resp
        seen = []

        def fake_open(director, req, data_=None, timeout=None):
            seen.append(director)
            return _Resp(json.dumps({"data": data}).encode())
        with mock.patch.object(urllib.request.OpenerDirector, "open", fake_open):
            call()
        self.assertTrue(seen)
        for director in seen:
            kinds = [type(h) for h in director.handlers]
            self.assertFalse(any(k is urllib.request.HTTPRedirectHandler for k in kinds), kinds)
            self.assertTrue(any(issubclass(k, urllib.request.HTTPRedirectHandler) for k in kinds))

    def test_orders_graphql(self):
        self.opened_by(lambda: orders._graphql("query { shop { name } }", {}), {"shop": {"name": "x"}})

    def test_store_catalogue(self):
        from kit.tools import store
        page = {"shop": {"currencyCode": "EGP"},
                "products": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
        self.opened_by(store._from_shopify, page)

    def test_the_opener_stops_at_a_redirect_on_a_post(self):
        import threading
        import urllib.error
        import urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from kit import net
        hits = []

        class Redirecting(BaseHTTPRequestHandler):
            def _answer(self):
                hits.append((self.command, self.path, self.headers.get("X-Shopify-Access-Token")))
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                self.send_response(302 if self.path == "/a" else 200)
                if self.path == "/a":
                    self.send_header("Location", "/b")
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_POST = _answer

            def log_message(self, *args):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Redirecting)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/a", data=b"{}", method="POST",
                                     headers={"X-Shopify-Access-Token": "test-token-not-real"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            net.open_once(req, timeout=5)
        cm.exception.close()
        self.assertEqual((cm.exception.code, hits), (302, [("POST", "/a", "test-token-not-real")]))


def setUpModule():
    """These tests read the zone fees (60, 85) as they were before decision 105: the store with no offers.
    The offers' own paths are in tests/test_offers.py and tests/test_offers_paths.py."""
    global _OFFERS_TOKEN
    _OFFERS_TOKEN = offers.OFFERS.set(offers.EMPTY)


def tearDownModule():
    offers.OFFERS.reset(_OFFERS_TOKEN)


if __name__ == "__main__":
    unittest.main()
