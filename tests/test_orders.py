"""The order tools: delivery, draft_order, cod_risk and find_order. Offline; Shopify is always stubbed."""
import json
import time
import unittest
from unittest import mock

from channels.base import Message
from sales import loop, stages
from kit import limits as limits_mod
from kit import net, orders, send_check, tools
from kit.chats import Chats
from kit.db import Db
from kit.limits import Limits
from kit.tools import cod_risk, delivery, draft_order, find_order, store, voice_note
from reflection.lessons import Lessons
from reflection.results import Results
from tests.fake_model import FakeModel, Outbox, call, clean_env, say

ME = "201011112222"       # the customer in these tests: a new number with no history
A = "200000000101"        # demo/orders.json: three delivered, one shipped, Cairo
B = "200000000102"        # two refused, one delivered, Giza
C = "200000000103"        # one refused, Alexandria
WHITE, BLACK, RED = ("Beyond the Limits Football Boots, White", "Beyond the Limits Football Boots, Black",
                     "Beyond the Limits Football Boots, Red")
JUNIOR = "Beyond the Limits Junior Football Boots"
PRINT = "Beyond the Limits Name Printing"     # type Printing: one variant, no size
DEMO = json.loads(orders.DEMO_ORDERS.read_text(encoding="utf-8"))["orders"]


def tool_call(name, args):
    """A model step that calls one tool (fake_model.call takes name as its own argument)."""
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call_{name}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


def use(mod, args, ctx):
    """A tool call as the registry runs it: check first, then run."""
    passed, feedback = mod.check(args, ctx)
    return mod.run(args, ctx) if passed else {"ok": False, "feedback": feedback}


def order_args(**kw):
    args = {"items": [{"product": WHITE, "size": "43", "quantity": 1}], "name": "Demo Buyer",
            "governorate": "الجيزة", "address": "شارع التحرير، الدقي، عمارة ١٢"}
    args.update(kw)
    return args


def variant(items, title, size=""):
    """The variant with this title and size in a copy of the catalogue, to change in a test."""
    return next(v for i in items if i["title"] == title for v in i["variants"] if v.get("size", "") == size)


class OrderBase(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)
        self.book = orders.Book(self.db)

    def ctx(self, number=ME, stage="ordering", channel="whatsapp"):
        cid = self.chats.open(channel, number)
        self.chats.add_step(cid, "user", content="عايز اطلب")
        return tools.Context(cid, stages.STAGES[stage], self.chats, None, None, Outbox(), stages=stages.STAGES)

    def shown(self, ctx):
        """The model's summary reply, showing the pending draft's total (red team t261028j F1)."""
        pending = self.book.pending(ctx.chat_id)
        total = orders.amount(pending["draft"]["total"]) if pending else ""
        return f"ده ملخص الاوردر، الاجمالي {total} جنيه. أأكد؟"

    def reply_and_answer(self, ctx, answer="تمام، أكد"):
        """The summary reply goes out and the customer answers it."""
        self.chats.add_step(ctx.chat_id, "assistant", content=self.shown(ctx))
        self.chats.add_step(ctx.chat_id, "user", content=answer)

    def summary(self, ctx, **kw):
        out = use(draft_order, order_args(**kw), ctx)
        self.assertTrue(out["ok"], out)
        return out

    def confirm(self, ctx, code, **kw):
        return use(draft_order, order_args(confirm=code, **kw), ctx)


class DeliveryTest(unittest.TestCase):
    def test_every_governorate_has_a_zone_with_a_fee(self):
        govs = delivery._data()["governorates"]
        self.assertEqual(len(govs), 27)
        self.assertEqual(len({g["name"] for g in govs}), 27)
        areas = {z["area"] for z in store.delivery()["zones"]}
        for g in govs:
            self.assertIn(g["zone"], areas)
            self.assertTrue(delivery.quote(g["name"])["ok"], g["name"])
            self.assertTrue(delivery.quote(g["name_ar"])["ok"], g["name_ar"])
            for s in g["spellings"]:
                self.assertEqual(delivery.find(s), [g], s)

    def test_arabic_spellings(self):
        for place, gov in (("الجيزة", "Giza"), ("الجيزه", "Giza"), ("بالجيزة", "Giza"), ("إسكندرية", "Alexandria"),
                           ("الاسكندريه", "Alexandria"), ("بنى سويف", "Beni Suef"), ("بور سعيد", "Port Said"),
                           ("الأقصر", "Luxor"), ("محافظة القاهرة", "Cairo"), ("القاهرة الجديدة", "Cairo"),
                           ("12 شارع التحرير، الدقي، الجيزة", "Giza")):
            self.assertEqual(delivery.quote(place)["governorate"], gov, place)

    def test_franco_and_english_spellings(self):
        for place, gov in (("el giza", "Giza"), ("fel 2ahera", "Cairo"), ("eskendereya", "Alexandria"),
                           ("Alex", "Alexandria"), ("kafr el sheikh", "Kafr El Sheikh"), ("bor sa3id", "Port Said"),
                           ("el menofeya", "Monufia"), ("be7eira", "Beheira"), ("Assiut", "Asyut"),
                           ("Fayyum", "Faiyum"), ("el o2sor", "Luxor"), ("Marsa Matrouh", "Matrouh")):
            self.assertEqual(delivery.quote(place)["governorate"], gov, place)

    def test_fee_and_days_come_from_the_data(self):
        self.assertEqual(delivery.quote("Giza"), {"ok": True, "governorate": "Giza", "governorate_ar": "الجيزة",
                                                  "area": "Cairo and Giza", "fee": 60, "days_min": 1, "days_max": 2})
        self.assertEqual(delivery.quote("Aswan")["fee"], 85)
        data = {"zones": [{"area": "Cairo and Giza", "fee": 45, "days_min": 1, "days_max": 1},
                          {"area": "Other governorates", "fee": 70, "days_min": 3, "days_max": 5}]}
        with mock.patch.object(store, "delivery", return_value=data):
            self.assertEqual((delivery.quote("Cairo")["fee"], delivery.quote("Sohag")["days_max"]), (45, 5))
        with mock.patch.object(store, "delivery", return_value={"zones": []}):
            self.assertFalse(delivery.quote("Cairo")["ok"])

    def test_unknown_or_two_places_ask_which_governorate(self):
        for place in ("Narnia", "6 October", "sinai", "مصر"):
            out = delivery.quote(place)
            self.assertFalse(out["ok"], place)
            self.assertIn("which governorate", out["note"])
            self.assertNotIn("fee", out)
        two = delivery.quote("Cairo or Giza")
        self.assertFalse(two["ok"])
        self.assertIn("Cairo, Giza", two["note"])

    def test_check(self):
        self.assertTrue(delivery.check({"governorate": "Giza"}, None)[0])
        for bad in ({}, {"governorate": ""}, {"governorate": 5}, {"governorate": "x" * 121},
                    {"governorate": "Giza", "fee": 1}):
            self.assertFalse(delivery.check(bad, None)[0], bad)


class DraftOrderTest(OrderBase):
    def test_totals_are_computed_in_code_from_the_data(self):
        out = self.summary(self.ctx(), items=[{"product": PRINT, "quantity": 1},
                                              {"product": JUNIOR, "size": "34", "quantity": 1},
                                              {"product": WHITE, "size": "43", "quantity": 2}])
        self.assertEqual((out["subtotal"], out["fee"], out["total"]),
                         (2 * 1450 + 700 + 150, 60, 2 * 1450 + 700 + 150 + 60))
        self.assertEqual([(i["product"], i["price"]) for i in out["items"]], [(WHITE, 1450), (JUNIOR, 700), (PRINT, 150)])
        self.assertEqual(send_check.amounts_in(out), {1450, 700, 150, 60, 3750, 3810})
        self.assertEqual(len(out["code"]), orders.CODE_LENGTH)
        self.assertTrue(set(out["code"]) <= set(orders.CODE_LETTERS))

    def test_totals_follow_the_data_not_the_model(self):
        ctx = self.ctx()
        items = store.catalogue()
        cheap = json.loads(json.dumps(items))
        variant(cheap, WHITE, "43")["price"] = "500"
        with mock.patch.object(store, "catalogue", return_value=cheap):
            out = self.summary(ctx, governorate="Aswan", items=[{"product": WHITE, "size": "43", "quantity": 2}])
        self.assertEqual((out["subtotal"], out["fee"], out["total"]), (1000, 85, 1085))
        # the model cannot pass a price: any extra key is refused before anything runs
        bad = order_args(items=[{"product": WHITE, "size": "43", "quantity": 1, "price": 1}])
        self.assertFalse(draft_order.check(bad, ctx)[0])
        self.assertFalse(draft_order.check(order_args(total=1), ctx)[0])

    def test_same_item_twice_is_one_line(self):
        out = self.summary(self.ctx(), items=[{"product": WHITE, "size": "43", "quantity": 1},
                                              {"product": WHITE.lower(), "size": " 43 ", "quantity": 2}])
        self.assertEqual([(i["size"], i["quantity"]) for i in out["items"]], [("43", 3)])
        self.assertEqual(out["subtotal"], 3 * 1450)
        # two lines of the same item cannot pass the cap together
        over = use(draft_order, order_args(items=[{"product": WHITE, "size": "43", "quantity": 15},
                                                  {"product": WHITE, "size": " 43", "quantity": 6}]), self.ctx())
        self.assertFalse(over["ok"])
        self.assertIn("At most 20", over["feedback"])

    def test_phone_defaults_to_the_chat_number(self):
        ctx = self.ctx()
        self.assertEqual(self.summary(ctx)["phone"], "01011112222")
        self.assertEqual(self.summary(ctx, phone="+20 12 3333 4444")["phone"], "01233334444")
        self.assertEqual(self.book.pending(ctx.chat_id)["draft"]["whatsapp"], ME)

    def test_items_must_exist_in_the_store(self):
        ctx = self.ctx()
        cases = (
            ([{"product": "Beyond the Limits Hoodie", "quantity": 1}], "No product has that title"),
            ([{"product": WHITE, "quantity": 1}], "comes in"),                    # needs a size
            ([{"product": WHITE, "size": "46", "quantity": 1}], "comes in"),
            ([{"product": BLACK, "size": "45", "quantity": 1}], "out of stock"),  # stock 0 in the demo data
            ([{"product": PRINT, "size": "43", "quantity": 1}], "has no sizes"),  # the printing has one variant, no size
        )
        for items, feedback in cases:
            out = use(draft_order, order_args(items=items), ctx)
            self.assertFalse(out["ok"], items)
            self.assertIn(feedback, out["feedback"])
        self.assertIsNone(self.book.pending(ctx.chat_id))
        one = self.summary(ctx, items=[{"product": PRINT, "quantity": 1}])  # one variant needs no size
        self.assertEqual((one["items"][0]["product"], one["items"][0]["price"]), (PRINT, 150))
        self.assertNotIn("size", one["items"][0])

    def test_a_size_that_starts_two_sizes_is_asked_about(self):
        """Review t261028j finding 10 (o10): "43" starts two sizes here, so the customer is asked which;
        a size that starts only one is that one."""
        boots = {"title": "Test Boots", "variants": [
            {"size": "43 (EU)", "price": "1450", "sku": "TEST-43-EU", "stock": "in stock"},
            {"size": "43 (US)", "price": "1500", "sku": "TEST-43-US", "stock": "in stock"},
            {"size": "44 (EU)", "price": "1450", "sku": "TEST-44-EU", "stock": "in stock"}]}
        ctx = self.ctx()
        with mock.patch.object(store, "catalogue", return_value=[boots]):
            out = use(draft_order, order_args(items=[{"product": "Test Boots", "size": "43", "quantity": 1}]), ctx)
            self.assertFalse(out["ok"])
            self.assertIn("comes in: 43 (EU), 43 (US), 44 (EU)", out["feedback"])
            self.assertIsNone(self.book.pending(ctx.chat_id))
            exact = self.summary(ctx, items=[{"product": "Test Boots", "size": "43 (US)", "quantity": 1}])
            start = self.summary(ctx, items=[{"product": "Test Boots", "size": "44", "quantity": 1}])
        self.assertEqual((exact["items"][0]["size"], exact["items"][0]["price"]), ("43 (US)", 1500))
        self.assertEqual(start["items"][0]["size"], "44 (EU)")

    def test_items_in_two_currencies_make_no_summary(self):
        """Review t261028j finding 10 (o8): one order never mixes currencies; the model hands off."""
        items = json.loads(json.dumps(store.catalogue()))
        for i in items:
            for v in i["variants"]:
                v["currency"] = "USD" if i["title"] == RED else "EGP"
        both = [{"product": WHITE, "size": "43", "quantity": 1}, {"product": RED, "size": "42", "quantity": 1}]
        ctx = self.ctx()
        with mock.patch.object(store, "catalogue", return_value=items):
            out = use(draft_order, order_args(items=both), ctx)
            self.assertFalse(out["ok"])
            self.assertIn("different currencies", out["feedback"])
            self.assertIsNone(self.book.pending(ctx.chat_id))
            for v in (v for i in items for v in i["variants"]):
                v["currency"] = "EGP"
            self.assertTrue(use(draft_order, order_args(items=both), ctx)["ok"])  # one currency is fine

    def test_check_refuses_bad_arguments(self):
        ctx = self.ctx()
        for bad in (
            {k: v for k, v in order_args().items() if k != "address"},
            order_args(items=[]),
            order_args(items=[{"product": WHITE, "size": "43", "quantity": 0}]),
            order_args(items=[{"product": WHITE, "size": "43", "quantity": "2"}]),
            order_args(items=[{"product": WHITE, "size": "43", "quantity": True}]),
            order_args(items=[{"product": WHITE, "size": "43", "quantity": draft_order.MAX_QUANTITY + 1}]),
            order_args(items=[{"product": WHITE, "size": "43", "quantity": 1}] * (draft_order.MAX_LINES + 1)),
            order_args(items=[{"product": WHITE, "size": "43", "quantity": 21}]),       # the caps as numbers:
            order_args(items=[{"product": WHITE, "size": "43", "quantity": 1}] * 11),   # 20 a line, 10 lines
            order_args(items=[{"product": PRINT, "quantity": 1, "print_name": "Y"}]),   # the name to print:
            order_args(items=[{"product": PRINT, "quantity": 1, "print_name": " Y  "}]),  # 2 to 30 characters
            order_args(items=[{"product": PRINT, "quantity": 1, "print_name": "Y" * 31}]),  # after spaces fold
            order_args(items=[{"product": PRINT, "quantity": 1, "print_name": 7}]),
            order_args(name="x"),
            order_args(address="x" * 301),
            order_args(phone="call me"),
            order_args(confirm=""),
        ):
            self.assertFalse(draft_order.check(bad, ctx)[0], bad)
        self.assertTrue(draft_order.check(order_args(), ctx)[0])
        for name in ("Yo", "Y" * 30, "  Youssef   Ali  " + " " * 20):
            self.assertTrue(draft_order.check(order_args(items=[{"product": PRINT, "quantity": 1,
                                                                 "print_name": name}]), ctx)[0], name)

    def test_unknown_governorate_makes_no_draft(self):
        ctx = self.ctx()
        out = use(draft_order, order_args(governorate="Narnia"), ctx)
        self.assertFalse(out["ok"])
        self.assertIn("which governorate", out["feedback"])
        self.assertIsNone(self.book.pending(ctx.chat_id))

    def test_confirm_in_the_same_turn_is_refused(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        out = self.confirm(ctx, code)
        self.assertFalse(out["ok"])
        self.assertIn("not answered", out["feedback"])
        self.assertIsNotNone(self.book.pending(ctx.chat_id))

    def test_confirm_needs_the_summary_reply_then_a_customer_message(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.chats.add_step(ctx.chat_id, "user", content="?")        # wrote, but no summary reply went out
        self.assertFalse(self.confirm(ctx, code)["ok"])
        self.chats.add_step(ctx.chat_id, "assistant", content=self.shown(ctx))  # the reply, but nothing after it
        self.assertFalse(self.confirm(ctx, code)["ok"])
        self.chats.add_step(ctx.chat_id, "user", content="تمام")
        self.assertTrue(self.confirm(ctx, code)["ok"])

    def test_a_reply_from_before_the_summary_does_not_count(self):
        ctx = self.ctx()
        self.reply_and_answer(ctx, "عايز جزمة كورة بيضا")   # an earlier exchange, before any summary
        code = self.summary(ctx)["code"]
        out = self.confirm(ctx, code)                  # the same turn: the customer has not seen the summary
        self.assertFalse(out["ok"])
        self.assertIn("not answered", out["feedback"])

    def test_text_beside_a_tool_call_is_not_a_reply(self):
        """The loop never sends the text of a step that calls a tool, so it cannot be the summary reply."""
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.chats.add_step(ctx.chat_id, "assistant", content="ده الملخص", tool_calls=[{
            "id": "call_1", "type": "function", "function": {"name": "cod_risk", "arguments": "{}"}}])
        self.chats.add_step(ctx.chat_id, "user", content="تمام")
        out = self.confirm(ctx, code)
        self.assertFalse(out["ok"])
        self.assertIn("not answered", out["feedback"])

    def test_plain_yes(self):
        for text in ("تمام، أكد", "تمام اكد", "ok", "yes please", "aywa", "تماااام", "\U0001F44D", "tamam w akked",
                     "Yesss", "حاضر يا باشا", "أيوة واكد", "ماشي كده"):
            with self.subTest(text=text):
                self.assertTrue(draft_order.plain_yes(text))
        for text in ("yes, but change the size", "ايوه بس غير المقاس 44", "aywa bs 3ayez 44", "تمام؟", "ok?", "لا",
                     "no", "2", "ايوه 2", "yes in 44", "تمام \U0001F44E", "", "...", "شكرا", "eh"):
            with self.subTest(text=text):
                self.assertFalse(draft_order.plain_yes(text))

    def test_a_yes_with_a_change_or_a_question_makes_no_order(self):
        for i, answer in enumerate(("yes, but change the size", "ايوه بس غير المقاس 44", "aywa bs 3ayez 44", "تمام؟",
                                    "لا", "2")):
            with self.subTest(answer=answer):
                ctx = self.ctx(number=f"2010111133{i:02d}")
                code = self.summary(ctx)["code"]
                self.reply_and_answer(ctx, answer)
                self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_A_YES})
        self.assertIsNone(self.book.demo_order("#1001"))

    def test_after_a_change_only_a_new_summary_can_be_confirmed(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx, "ايوه بس غير المقاس 44")
        self.reply_and_answer(ctx, "yes")      # the model answered without a new summary: still refused
        self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_A_YES})
        new = self.summary(ctx, items=[{"product": WHITE, "size": "44", "quantity": 1}])["code"]
        self.reply_and_answer(ctx, "yes")
        out = self.confirm(ctx, new, items=[{"product": WHITE, "size": "44", "quantity": 1}])
        self.assertTrue(out["ok"], out)

    def voice_ctx(self, heard=None, audio=b"ogg"):
        """A chat whose summary was answered by a voice note in this turn."""
        ctx = self.ctx()
        msg = Message(channel="whatsapp", customer_id=ME, text="", audio=audio, audio_mime="audio/ogg")
        ctx = tools.Context(ctx.chat_id, ctx.stage, self.chats, None, msg, Outbox(), stages=stages.STAGES)
        code = self.summary(ctx)["code"]
        self.chats.add_step(ctx.chat_id, "assistant", content=self.shown(ctx))
        self.chats.add_step(ctx.chat_id, "user", media=[{"kind": "audio"}])
        if heard is not None:
            ctx.cache["voice_note"] = heard
        return ctx, code

    def test_a_voice_note_yes_uses_this_turns_transcript(self):
        ctx, code = self.voice_ctx()
        self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.HEAR_FIRST})
        for heard in ({"ok": True, "text": "ايوه بس خليها 44"}, dict(voice_note.NOT_HEARD)):
            with self.subTest(heard=heard):
                ctx, code = self.voice_ctx(heard)
                self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_A_YES})
        ctx, code = self.voice_ctx({"ok": True, "text": "ايوه اكد"}, audio=None)   # not this turn's message
        self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_A_YES})
        ctx, code = self.voice_ctx({"ok": True, "text": "ايوه اكد"})
        self.assertTrue(self.confirm(ctx, code)["ok"])

    def test_an_earlier_voice_note_or_a_photo_is_not_a_plain_yes(self):
        ctx, code = self.voice_ctx({"ok": True, "text": "ايوه اكد"})
        self.chats.add_step(ctx.chat_id, "user", content="تمام")        # the voice note is no longer the latest
        self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_A_YES})
        ctx = self.ctx(number=A)
        code = self.summary(ctx)["code"]
        self.chats.add_step(ctx.chat_id, "assistant", content=self.shown(ctx))
        self.chats.add_step(ctx.chat_id, "user", content="تمام", media=[{"kind": "image"}])
        self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_A_YES})

    def test_confirm_creates_the_order_with_the_chat_id(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        out = self.confirm(ctx, code.lower())
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["step"], out["order"], out["total"]), ("created", "#1001", 1510))
        row = self.book.demo_order("#1001")
        self.assertEqual((row["chat_id"], row["whatsapp"], row["phone"]), (ctx.chat_id, ME, ME))
        self.assertEqual((row["total"], row["status"], row["governorate"]), ("1510", "received", "Giza"))
        self.assertIn(f"wa-{ME}", json.loads(row["tags"]))
        self.assertIsNone(self.book.pending(ctx.chat_id))
        again = self.confirm(ctx, code)
        self.assertFalse(again["ok"])                                  # a summary is used once
        self.assertIn("No order summary", again["feedback"])

    def test_confirm_with_changed_details_is_refused(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        for change in ({"address": "شارع الهرم، عمارة ٥"}, {"governorate": "Cairo"}, {"name": "Someone Else"},
                       {"phone": "01233334444"},
                       {"items": [{"product": WHITE, "size": "43", "quantity": 3}]},
                       {"items": [{"product": WHITE, "size": "44", "quantity": 1}]}):
            out = self.confirm(ctx, code, **change)
            self.assertFalse(out["ok"], change)
            self.assertIn("not the order in the summary", out["feedback"])
        self.assertIsNone(self.book.demo_order("#1001"))
        self.assertTrue(self.confirm(ctx, code)["ok"])

    def test_a_price_change_after_the_summary_is_refused(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        dearer = json.loads(json.dumps(store.catalogue()))
        variant(dearer, WHITE, "43")["price"] = "1500"
        with mock.patch.object(store, "catalogue", return_value=dearer):
            out = self.confirm(ctx, code)
        self.assertFalse(out["ok"])
        self.assertIn("not the order in the summary", out["feedback"])
        gone = json.loads(json.dumps(store.catalogue()))
        variant(gone, WHITE, "43")["stock"] = "out"
        with mock.patch.object(store, "catalogue", return_value=gone):
            out = self.confirm(ctx, code)
        self.assertFalse(out["ok"])
        self.assertIn("out of stock", out["feedback"])
        self.assertIsNone(self.book.demo_order("#1001"))

    def test_a_newer_summary_replaces_the_code(self):
        ctx = self.ctx()
        old = self.summary(ctx)["code"]
        new = self.summary(ctx, address="شارع الهرم، عمارة ٥")["code"]
        self.reply_and_answer(ctx)
        out = self.confirm(ctx, old)
        self.assertFalse(out["ok"])
        self.assertIn("latest summary", out["feedback"])
        self.assertTrue(self.confirm(ctx, new, address="شارع الهرم، عمارة ٥")["ok"])

    def test_no_summary_or_an_old_one_is_refused(self):
        ctx = self.ctx()
        self.reply_and_answer(ctx)
        self.assertIn("No order summary", self.confirm(ctx, "BCDFG")["feedback"])
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        with mock.patch.object(draft_order.time, "time", return_value=time.time() + orders.DRAFT_SECONDS + 1):
            out = self.confirm(ctx, code)
        self.assertFalse(out["ok"])
        self.assertIn("more than a day old", out["feedback"])
        self.assertIsNone(self.book.pending(ctx.chat_id))

    def test_a_summary_lasts_one_day(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        with mock.patch.object(draft_order.time, "time", return_value=time.time() + 25 * 3600):
            out = self.confirm(ctx, code)
        self.assertFalse(out["ok"])
        self.assertIn("more than a day old", out["feedback"])
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        with mock.patch.object(draft_order.time, "time", return_value=time.time() + 23 * 3600):
            self.assertTrue(self.confirm(ctx, code)["ok"])

    def test_the_summary_belongs_to_its_chat(self):
        mine, other = self.ctx(), self.ctx(number="201055556666")
        code = self.summary(mine)["code"]
        self.reply_and_answer(other)
        self.assertFalse(self.confirm(other, code)["ok"])

    def test_two_confirms_at_once_make_one_order(self):
        """Both confirms read the pending draft before either takes it: only the first one places an order."""
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        both_read = self.book.pending(ctx.chat_id)
        with mock.patch.object(orders.Book, "pending", return_value=both_read):
            first, second = self.confirm(ctx, code), self.confirm(ctx, code)
        self.assertTrue(first["ok"], first)
        self.assertEqual(second, {"ok": False, "feedback": draft_order.NO_PENDING})
        self.assertIsNone(self.book.demo_order("#1002"))

    def test_take_removes_only_the_draft_with_that_code(self):
        mine, other = self.ctx().chat_id, self.ctx(number="201055556666").chat_id
        self.book.save_draft(mine, "BCDFG", {"x": 1}, 1)
        self.book.save_draft(other, "HJKLM", {"x": 2}, 1)
        self.assertFalse(self.book.take(mine, "HJKLM"))      # a code from another summary takes nothing
        self.assertEqual((self.book.pending(mine) or {}).get("code"), "BCDFG")
        self.assertTrue(self.book.take(mine, "BCDFG"))
        self.assertFalse(self.book.take(mine, "BCDFG"))      # once only
        self.assertEqual((self.book.pending(other) or {}).get("code"), "HJKLM")

    def test_the_order_goes_to_the_result_log_with_its_risk(self):
        ctx = self.ctx(number=B)
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        self.assertTrue(self.confirm(ctx, code)["ok"])
        rows = Results(self.db).for_chat(ctx.chat_id)
        self.assertEqual([r["outcome"] for r in rows], ["order_drafted", "order_created"])
        self.assertEqual(rows[0]["detail"], {"total": 1510})
        self.assertEqual(rows[1]["detail"]["cod_risk"], "high")
        self.assertEqual(rows[1]["detail"]["order"], "#1001")
        self.assertEqual(rows[1]["detail"]["total"], 1510)
        self.assertEqual(rows[1]["detail"]["area"], "Cairo and Giza")  # the zone, for the delivery days fact
        self.assertIn("cod-risk-high", json.loads(self.book.demo_order("#1001")["tags"]))
        with self.assertRaises(ValueError):        # the old outcome name is gone
            Results(self.db).record(ctx.chat_id, "ordered")

    def test_a_result_log_failure_never_stops_the_order(self):
        ctx = self.ctx()
        with mock.patch.object(Results, "record", side_effect=RuntimeError("disk full")), \
                self.assertLogs("kit.tools.draft_order", "ERROR") as logs:
            code = self.summary(ctx)["code"]
            self.reply_and_answer(ctx)
            self.assertTrue(self.confirm(ctx, code)["ok"])
        self.assertEqual(len(logs.records), 2)
        self.assertIsNotNone(self.book.demo_order("#1001"))

    def test_a_store_failure_keeps_the_summary(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        with mock.patch.object(orders.Book, "create", side_effect=orders.StoreError("down")), \
                self.assertLogs("kit.tools.draft_order", "ERROR"):
            out = self.confirm(ctx, code)
        self.assertEqual(out, {"ok": False, "feedback": draft_order.NOT_SAVED})
        self.assertEqual(self.book.pending(ctx.chat_id)["code"], code)
        self.assertEqual([r["outcome"] for r in Results(self.db).for_chat(ctx.chat_id)], ["order_drafted"])
        self.assertTrue(self.confirm(ctx, code)["ok"])

    def test_another_channel_needs_a_phone(self):
        ctx = self.ctx(number="ig-123", channel="instagram")
        out = use(draft_order, order_args(), ctx)
        self.assertFalse(out["ok"])
        self.assertIn("phone number", out["feedback"])
        self.assertTrue(use(draft_order, order_args(phone="01011112222"), ctx)["ok"])

    def test_another_channels_id_is_never_a_whatsapp_number(self):
        ctx = self.ctx(number="ig-200000000102", channel="instagram")   # digits shaped like B's number
        self.summary(ctx, phone="01011112222")
        draft = self.book.pending(ctx.chat_id)["draft"]
        self.assertEqual((draft["whatsapp"], draft["phone"]), ("", ME))

    def test_the_risk_never_reaches_what_the_customer_sees(self):
        ctx = self.ctx(number=B)   # a high risk number
        summary = self.summary(ctx)
        self.reply_and_answer(ctx)
        created = self.confirm(ctx, summary["code"])
        self.assertTrue(created["ok"], created)
        for out in (summary, created):
            text = json.dumps(out, ensure_ascii=False).lower()
            for word in ("risk", "high", "refus"):
                self.assertNotIn(word, text, out["step"])


BOOTS_AND_PRINT = [{"product": WHITE, "size": "43", "quantity": 1}, {"product": PRINT, "quantity": 1}]


def printed(name, quantity=1):
    return {"product": PRINT, "quantity": quantity, "print_name": name}


class PrintNameTest(OrderBase):
    """DECISIONS item 28: the printing line carries a name to print, the customer's own name unless they give another."""

    def line(self, out, product=PRINT):
        return next(i for i in out["items"] if i["product"] == product)

    def test_the_name_to_print_defaults_to_the_order_name(self):
        out = self.summary(self.ctx(), items=BOOTS_AND_PRINT, name="  Demo   Buyer ")
        self.assertEqual(self.line(out)["print_name"], "Demo Buyer")
        self.assertEqual(out["name"], "Demo Buyer")
        self.assertNotIn("print_name", self.line(out, WHITE))      # only the printing line has one
        self.assertEqual(out["subtotal"], 1450 + 150)

    def test_a_given_name_is_printed(self):
        ctx = self.ctx()
        out = self.summary(ctx, items=[BOOTS_AND_PRINT[0], printed("  يوسف   علي ")])
        self.assertEqual(self.line(out)["print_name"], "يوسف علي")
        self.assertEqual(out["name"], "Demo Buyer")                # the delivery name stays the order's
        lines = self.book.pending(ctx.chat_id)["draft"]["items"]
        self.assertEqual([i.get("print_name") for i in lines], [None, "يوسف علي"])

    def test_a_name_on_a_boots_line_is_refused(self):
        ctx = self.ctx()
        out = use(draft_order, order_args(items=[{"product": WHITE, "size": "43", "quantity": 1,
                                                  "print_name": "Youssef"}]), ctx)
        self.assertFalse(out["ok"])
        self.assertIn("print_name goes only on a printing line", out["feedback"])
        self.assertIsNone(self.book.pending(ctx.chat_id))

    def test_the_printing_service_is_told_by_its_type(self):
        """A product whose type folds to "printing" takes a name, whatever its title."""
        items = json.loads(json.dumps(store.catalogue()))
        for i in items:
            if i["title"] == PRINT:
                i["title"], i["type"] = "Custom Lettering", "  PRINTING "
        ctx = self.ctx()
        with mock.patch.object(store, "catalogue", return_value=items):
            out = self.summary(ctx, items=[{"product": "Custom Lettering", "quantity": 1}])
            self.assertEqual(self.line(out, "Custom Lettering")["print_name"], "Demo Buyer")
            for i in items:
                i.pop("type", None)                                 # no type: not a printing line
            out = use(draft_order, order_args(items=[{"product": "Custom Lettering", "quantity": 1,
                                                      "print_name": "Youssef"}]), ctx)
        self.assertFalse(out["ok"])
        self.assertIn("print_name goes only on a printing line", out["feedback"])

    def test_a_name_too_long_to_print_is_asked_for(self):
        ctx = self.ctx()
        long_name = "Demo Buyer With A Very Long Full Name"               # fine for delivery, over 30 to print
        out = use(draft_order, order_args(items=BOOTS_AND_PRINT, name=long_name), ctx)
        self.assertFalse(out["ok"])
        self.assertIn("pass it as print_name", out["feedback"])
        self.assertIsNone(self.book.pending(ctx.chat_id))
        out = self.summary(ctx, items=[BOOTS_AND_PRINT[0], printed("Demo")], name=long_name)
        self.assertEqual(self.line(out)["print_name"], "Demo")
        self.assertTrue(self.summary(ctx, name=long_name)["ok"])  # no printing line, no name to print

    def test_shown_in_the_summary(self):
        out = self.summary(self.ctx(), items=[BOOTS_AND_PRINT[0], printed("Youssef")])
        self.assertEqual(out["items"], [
            {"product": WHITE, "size": "43", "quantity": 1, "price": 1450},
            {"product": PRINT, "print_name": "Youssef", "quantity": 1, "price": 150}])
        self.assertIn("name to print", out["next"])
        item = draft_order.DEFINITION["function"]["parameters"]["properties"]["items"]["items"]
        self.assertIn("print_name", item["properties"])
        self.assertNotIn("print_name", item["required"])

    def test_two_names_are_two_lines(self):
        out = self.summary(self.ctx(), items=[BOOTS_AND_PRINT[0], printed("Youssef"), printed("Omar"),
                                              printed(" Youssef ", 2), {"product": PRINT, "quantity": 1}])
        lines = [(i["print_name"], i["quantity"]) for i in out["items"] if i["product"] == PRINT]
        self.assertEqual(lines, [("Demo Buyer", 1), ("Omar", 1), ("Youssef", 3)])
        self.assertEqual(out["subtotal"], 1450 + 5 * 150)
        # each name has its own cap of 20
        over = use(draft_order, order_args(items=[printed("Youssef", 15), printed("Youssef", 6)]), self.ctx())
        self.assertIn("At most 20", over["feedback"])
        self.assertTrue(use(draft_order, order_args(items=[printed("Youssef", 15), printed("Omar", 6)]),
                            self.ctx(number="201055556666"))["ok"])

    def test_the_order_of_lines_does_not_change_the_draft(self):
        ctx = self.ctx()
        a = [BOOTS_AND_PRINT[0], printed("Youssef"), printed("Omar")]
        code = self.summary(ctx, items=a)["code"]
        self.reply_and_answer(ctx)
        self.assertTrue(self.confirm(ctx, code, items=list(reversed(a)))["ok"])

    def test_a_changed_name_is_refused_at_confirm(self):
        ctx = self.ctx()
        items = [BOOTS_AND_PRINT[0], printed("Youssef")]
        code = self.summary(ctx, items=items)["code"]
        self.reply_and_answer(ctx)
        for change in ([BOOTS_AND_PRINT[0], printed("Omar")],      # another name
                       BOOTS_AND_PRINT):                           # left out: the order's name, not the one shown
            out = self.confirm(ctx, code, items=change)
            self.assertFalse(out["ok"], change)
            self.assertIn("not the order in the summary", out["feedback"])
        self.assertIsNone(self.book.demo_order("#1001"))
        self.assertTrue(self.confirm(ctx, code, items=items)["ok"])

    def test_the_default_name_given_at_confirm_is_the_same_draft(self):
        ctx = self.ctx()
        code = self.summary(ctx, items=BOOTS_AND_PRINT)["code"]
        self.reply_and_answer(ctx)
        self.assertTrue(self.confirm(ctx, code, items=[BOOTS_AND_PRINT[0], printed("Demo Buyer")])["ok"])

    def test_saved_on_the_demo_order(self):
        ctx = self.ctx()
        items = [BOOTS_AND_PRINT[0], printed("Youssef")]
        code = self.summary(ctx, items=items)["code"]
        self.reply_and_answer(ctx)
        self.assertEqual(self.confirm(ctx, code, items=items)["total"], 1450 + 150 + 60)
        saved = json.loads(self.book.demo_order("#1001")["items"])
        self.assertEqual([(i["product"], i.get("print_name")) for i in saved], [(WHITE, None), (PRINT, "Youssef")])
        self.assertEqual(saved[1]["sku"], "BTL-PRINT-NAME")


class CodRiskTest(OrderBase):
    def risk(self, number=ME, **kw):
        """The assessment the team gets, with the next step the model reads. The model reads only
        ok and next (red team t261028j F4)."""
        ctx = self.ctx(number=number)
        self.summary(ctx, **kw)
        out = use(cod_risk, {}, ctx)
        self.assertEqual(set(out), {"ok", "next"})
        return {**cod_risk.assess(self.book, self.book.pending(ctx.chat_id)["draft"]), "next": out["next"]}

    def test_two_refusals_are_high(self):
        out = self.risk(B)
        self.assertEqual(out["level"], "high")
        self.assertEqual(out["reasons"], ["Refused 2 earlier cash on delivery orders."])
        self.assertIn("address", out["next"])
        self.assertIn("Never mention", out["next"])

    def test_one_refusal_is_medium(self):
        out = self.risk(C)
        self.assertEqual((out["level"], out["reasons"]), ("medium", ["Refused 1 earlier cash on delivery order."]))

    def test_a_first_order_with_a_high_total(self):
        out = self.risk(items=[{"product": WHITE, "size": "43", "quantity": 2}])   # 2960, at or over 2500
        self.assertEqual((out["level"], out["reasons"]), ("medium", ["First order from this number, and the total is high."]))
        small = self.risk(number="201055556666")
        self.assertEqual((small["level"], small["reasons"]), ("low", ["No warning signs in past orders."]))
        for o in (out, small):
            self.assertIn("Never mention", o["next"])

    def test_the_area_refusal_rate(self):
        out = self.risk(number="201055556666", governorate="Aswan")
        self.assertEqual(out["level"], "medium")
        self.assertEqual(out["reasons"], ["Many cash on delivery orders to Aswan were refused (3 of 6 finished orders)."])
        both = self.risk(number="201077778888", governorate="أسوان",
                         items=[{"product": WHITE, "size": "43", "quantity": 2}])
        self.assertEqual(both["level"], "high")
        self.assertEqual(len(both["reasons"]), 2)
        # Giza has refusals too, but too few finished orders to count
        self.assertEqual(self.book.area_counts("Giza"), (2, 3))

    def test_a_good_history_is_low(self):
        out = self.risk(A, items=[{"product": WHITE, "size": "43", "quantity": 2}])   # a high total, not a first order
        self.assertEqual((out["level"], out["reasons"]), ("low", ["3 earlier orders delivered, none refused."]))

    def test_the_delivery_phone_counts_too(self):
        out = self.risk(phone="+" + B)  # a clean WhatsApp number giving a refused delivery phone
        self.assertEqual(out["level"], "high")

    def test_needs_a_summary_and_no_arguments(self):
        ctx = self.ctx()
        self.assertFalse(use(cod_risk, {}, ctx)["ok"])
        self.assertFalse(cod_risk.check({"phone": B}, ctx)[0])
        self.summary(self.ctx(number=B))                 # another chat's summary is never read here
        self.assertFalse(use(cod_risk, {}, ctx)["ok"])

    def test_adds_no_amount_to_the_send_check(self):
        ctx = self.ctx(number=B)
        self.summary(ctx)
        self.assertEqual(send_check.amounts_in(use(cod_risk, {}, ctx)), set())


class FindOrderTest(OrderBase):
    def test_finds_only_this_numbers_orders(self):
        out = use(find_order, {}, self.ctx(number=A, stage="my_order"))
        self.assertEqual([o["order"] for o in out["orders"]], ["#7015", "#7009", "#7004", "#7001"])
        self.assertEqual(out["orders"][0]["status"], "shipped")
        self.assertEqual((out["orders"][0]["days_min"], out["orders"][0]["days_max"]), (1, 2))
        self.assertNotIn("days_min", out["orders"][1])
        mine = {o["name"] for o in DEMO if o["phone"] == A}
        self.assertEqual({o["order"] for o in out["orders"]}, mine)

    def test_an_order_number_never_reaches_another_customer(self):
        out = use(find_order, {"order": "#7002"}, self.ctx(number=A, stage="my_order"))  # B's order
        self.assertNotIn("#7002", json.dumps(out))
        self.assertIn("None of the orders", out["note"])
        stranger = use(find_order, {"order": "7002"}, self.ctx(number="201099990000", stage="my_order"))
        self.assertEqual(stranger["orders"], [])
        self.assertIn("No orders under this WhatsApp number", stranger["note"])

    def test_the_same_last_digits_are_not_the_same_number(self):
        near = "210000000101"   # A's last nine digits under another country code
        self.assertEqual(use(find_order, {}, self.ctx(number=near, stage="my_order"))["orders"], [])
        self.assertEqual(self.book.for_phones({near}), [])

    def test_an_order_number_picks_among_their_own(self):
        out = use(find_order, {"order": "7009"}, self.ctx(number=A, stage="my_order"))
        self.assertEqual([o["order"] for o in out["orders"]], ["#7009"])
        self.assertEqual(out["orders"][0]["total"], 1510)

    def test_new_orders_are_found_by_the_number_that_placed_them(self):
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        self.confirm(ctx, code)
        out = use(find_order, {}, self.ctx(stage="my_order"))
        self.assertEqual([(o["order"], o["status"], o["total"]) for o in out["orders"]], [("#1001", "received", 1510)])
        self.assertEqual(use(find_order, {}, self.ctx(number=B, stage="my_order"))["orders"][0]["order"], "#7010")

    def test_the_number_comes_from_the_chat_only(self):
        ctx = self.ctx(number=A, stage="my_order")
        for bad in ({"phone": B}, {"customer": B}, {"order": "x" * 21}):
            self.assertFalse(find_order.check(bad, ctx)[0], bad)
        other = self.ctx(number="ig-200000000102", stage="my_order", channel="instagram")
        self.assertFalse(use(find_order, {}, other)["ok"])


class PhoneTest(unittest.TestCase):
    def test_one_number_many_ways(self):
        for raw in ("01012345678", "+20 10 1234 5678", "00201012345678", "201012345678", "1012345678",
                    "٠١٠١٢٣٤٥٦٧٨", "010-1234-5678"):
            self.assertEqual(orders.phone_key(raw), "201012345678", raw)
        for raw in ("", "12345", "call me", None, "1" * 16):
            self.assertEqual(orders.phone_key(raw), "", raw)
        self.assertEqual(orders.local_phone("201012345678"), "01012345678")
        self.assertEqual(orders.local_phone("447700900123"), "+447700900123")
        self.assertEqual(orders.local_phone("200000000101"), "+200000000101")    # no Egyptian number has 0 after 20
        self.assertEqual(orders.local_phone("2010123456789"), "+2010123456789")  # 13 digits is not an Egyptian mobile
        self.assertEqual(orders.local_phone(""), "")

    def test_demo_history_is_fake_and_adds_up(self):
        price = {(i["title"], v.get("size", "")): int(v["price"]) for i in store.catalogue() for v in i["variants"]}
        kind = {i["title"]: i.get("type", "") for i in store.catalogue()}
        for o in DEMO:
            self.assertTrue(o["phone"].startswith("200"), o["name"])  # no Egyptian number has a 0 after 20
            self.assertTrue(o["customer"].startswith("Demo Customer"))
            sub = sum(price[(i["product"], i.get("size", ""))] * i["quantity"] for i in o["items"])
            self.assertEqual((o["subtotal"], o["fee"], o["total"]),
                             (sub, delivery.quote(o["governorate"])["fee"], sub + o["fee"]), o["name"])
            for i in o["items"]:   # a name to print only on a printing line
                self.assertEqual("print_name" in i, kind[i["product"]] == "Printing", o["name"])


class FakeShopify:
    """Stands in for urlopen: answers each GraphQL call from a script and keeps every request."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode())
        self.requests.append((req.full_url, body))
        for marker, data in self.answers:
            if marker in body["query"]:
                return _Resp(json.dumps({"data": data(body) if callable(data) else data}).encode())
        raise AssertionError("unexpected Shopify call")


class _Resp:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


SHOP = {"SHOPIFY_STORE": "demo-shop.myshopify.com", "SHOPIFY_TOKEN": "test-token-not-real"}


class ShopifyTest(OrderBase):
    def setUp(self):
        super().setUp()
        clean_env(self, **SHOP)
        items = json.loads(json.dumps(store._from_demo(store.DEMO_CATALOGUE)))
        for i in items:
            for v in i["variants"]:
                v["currency"] = "EGP"
        p = mock.patch.object(store, "catalogue", return_value=items)
        p.start()
        self.addCleanup(p.stop)

    def shop(self, *answers):
        fake = FakeShopify(list(answers))
        p = mock.patch.object(net, "open_once", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def test_draft_order_create_shape(self):
        fake = self.shop(
            ("productVariants", lambda b: {"productVariants": {"nodes": [
                {"id": "gid://shopify/ProductVariant/1", "sku": b["variables"]["q"][4:]}]}}),
            ("draftOrderCreate", {"draftOrderCreate": {"draftOrder": {
                "id": "gid://shopify/DraftOrder/9", "name": "#D9",
                "totalPriceSet": {"shopMoney": {"amount": "1510.0", "currencyCode": "EGP"}}}, "userErrors": []}}),
            ("FindByPhone", {"orders": {"nodes": []}, "draftOrders": {"nodes": []}, "customers": {"nodes": []}}),
        )
        ctx = self.ctx(number=B)
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        out = self.confirm(ctx, code)
        self.assertEqual((out["ok"], out["order"]), (True, "#D9"))
        url, body = next(r for r in fake.requests if "draftOrderCreate" in r[1]["query"])
        self.assertEqual(url, "https://demo-shop.myshopify.com/admin/api/2026-10/graphql.json")
        inp = body["variables"]["input"]
        self.assertEqual(inp["customAttributes"], [{"key": "chat_id", "value": ctx.chat_id}])
        self.assertEqual(inp["lineItems"], [{"variantId": "gid://shopify/ProductVariant/1", "quantity": 1}])
        self.assertEqual(inp["shippingLine"]["priceWithCurrency"], {"amount": "60", "currencyCode": "EGP"})
        self.assertEqual(inp["shippingAddress"]["countryCode"], "EG")
        self.assertEqual((inp["phone"], inp["shippingAddress"]["phone"]), ("+" + B, "+" + B))
        self.assertEqual(inp["tags"], ["whatsapp", "sales-agent", "cod-risk-low", f"wa-{B}"])
        self.assertNotIn("risk", inp["note"].lower())
        self.assertIsNone(self.book.demo_order("#1001"))  # nothing in the demo table on Shopify

    def test_the_name_to_print_goes_on_its_shopify_line(self):
        fake = self.shop(
            ("productVariants", lambda b: {"productVariants": {"nodes": [
                {"id": "gid://shopify/ProductVariant/" + b["variables"]["q"][4:], "sku": b["variables"]["q"][4:]}]}}),
            ("draftOrderCreate", {"draftOrderCreate": {"draftOrder": {
                "id": "gid://shopify/DraftOrder/9", "name": "#D9",
                "totalPriceSet": {"shopMoney": {"amount": "1810.0", "currencyCode": "EGP"}}}, "userErrors": []}}),
            ("FindByPhone", {"orders": {"nodes": []}, "draftOrders": {"nodes": []}, "customers": {"nodes": []}}),
        )
        items = [{"product": WHITE, "size": "43", "quantity": 1}, printed("Youssef"), printed("Omar")]
        ctx = self.ctx()
        code = self.summary(ctx, items=items)["code"]
        self.reply_and_answer(ctx)
        out = self.confirm(ctx, code, items=items)
        self.assertEqual((out["ok"], out["order"], out["total"]), (True, "#D9", 1450 + 2 * 150 + 60))
        _, body = next(r for r in fake.requests if "draftOrderCreate" in r[1]["query"])
        variant_id = "gid://shopify/ProductVariant/"
        self.assertEqual(body["variables"]["input"]["lineItems"], [
            {"variantId": variant_id + "BTL-FB-WHT-43", "quantity": 1},
            {"variantId": variant_id + "BTL-PRINT-NAME", "quantity": 1,
             "customAttributes": [{"key": "Name to print", "value": "Omar"}]},
            {"variantId": variant_id + "BTL-PRINT-NAME", "quantity": 1,
             "customAttributes": [{"key": "Name to print", "value": "Youssef"}]}])
        looked_up = [b["variables"]["q"] for _, b in fake.requests if "productVariants" in b["query"]]
        self.assertEqual(looked_up, ["sku:BTL-FB-WHT-43", "sku:BTL-PRINT-NAME"])   # one lookup a sku

    def test_user_errors_keep_the_summary(self):
        self.shop(
            ("productVariants", {"productVariants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "sku": "BTL-FB-WHT-43"}]}}),
            ("draftOrderCreate", {"draftOrderCreate": {"draftOrder": None, "userErrors": [{"field": ["x"], "message": "no"}]}}),
            ("FindByPhone", {"orders": {"nodes": []}, "draftOrders": {"nodes": []}, "customers": {"nodes": []}}),
        )
        ctx = self.ctx()
        code = self.summary(ctx)["code"]
        self.reply_and_answer(ctx)
        with self.assertLogs("kit.tools.draft_order", "ERROR"):
            self.assertEqual(self.confirm(ctx, code), {"ok": False, "feedback": draft_order.NOT_SAVED})
        self.assertIsNotNone(self.book.pending(ctx.chat_id))

    def test_find_keeps_only_exact_matches(self):
        def order(name, phone=None, tags=(), ship=None, cust=None, status="UNFULFILLED"):
            return {"name": name, "createdAt": "2026-10-20T10:00:00Z", "cancelledAt": None,
                    "displayFulfillmentStatus": status, "phone": phone, "tags": list(tags),
                    "shippingAddress": {"phone": ship, "city": "Giza"},
                    "customer": {"defaultPhoneNumber": {"phoneNumber": cust}} if cust else None,
                    "totalPriceSet": {"shopMoney": {"amount": "1510.00"}},
                    "lineItems": {"nodes": [{"title": WHITE, "variantTitle": "43", "quantity": 1}]}}
        fake = self.shop(
            ("FindByPhone", {
                "orders": {"nodes": [order("#1", tags=[f"wa-{ME}"], status="FULFILLED"),
                                     order("#2", phone="+201099990000", tags=["wa-201099990000"])]},
                "draftOrders": {"nodes": [dict(order("#D3", ship="01011112222"), status="OPEN"),
                                          dict(order("#D4", phone="+201011112223"), status="OPEN"),
                                          dict(order("#D5", phone="+" + ME), status="COMPLETED")]},
                "customers": {"nodes": [{"id": "gid://shopify/Customer/77", "defaultPhoneNumber": {"phoneNumber": "+" + ME}},
                                        {"id": "gid://shopify/Customer/78", "defaultPhoneNumber": {"phoneNumber": "+201011112229"}}]}}),
            ("OrdersByCustomer", {"orders": {"nodes": [order("#6", cust="+" + ME), order("#7", cust="+201099990000")]}}),
        )
        out = use(find_order, {}, self.ctx(stage="my_order"))
        self.assertEqual(sorted(o["order"] for o in out["orders"]), ["#1", "#6", "#D3"])
        status = {o["order"]: o["status"] for o in out["orders"]}
        self.assertEqual(status, {"#1": "shipped", "#6": "confirmed", "#D3": "received"})
        queries = [b["variables"] for _, b in fake.requests]
        self.assertEqual(queries[0], {"tag": f"tag:wa-{ME}", "customer": f"phone:+{ME}"})
        self.assertEqual(queries[1:], [{"q": "customer_id:77"}])  # only the customer whose phone matches

    def test_another_countrys_number_with_the_same_last_digits_is_not_theirs(self):
        """Review t261028j finding 10 (o14): +966 011112222 ends like ME; only the exact number counts."""
        other = "+966011112222"
        self.assertEqual(orders.phone_key(other)[-9:], ME[-9:])

        def draft(name, phone):
            return {"name": name, "createdAt": "2026-10-20T10:00:00Z", "cancelledAt": None, "status": "OPEN",
                    "phone": phone, "tags": [], "shippingAddress": {"phone": phone, "city": "Giza"},
                    "customer": None, "totalPriceSet": {"shopMoney": {"amount": "1510.00"}},
                    "lineItems": {"nodes": [{"title": WHITE, "variantTitle": "43", "quantity": 1}]}}
        self.shop(("FindByPhone", {"orders": {"nodes": []},
                                   "draftOrders": {"nodes": [draft("#D8", other), draft("#D9", "+" + ME)]},
                                   "customers": {"nodes": []}}))
        out = use(find_order, {}, self.ctx(stage="my_order"))
        self.assertEqual([o["order"] for o in out["orders"]], ["#D9"])


class LoopTest(unittest.TestCase):
    """A full order through the Sales agent loop, with the order tools offered as the registry will offer them."""

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

    def turn(self, model, text):
        msg = Message(channel="whatsapp", customer_id=ME, text=text)
        return loop.turn(msg, chats=self.chats, model=model, lessons=Lessons(self.db), results=self.results,
                         send=self.out)

    def test_summary_then_yes_places_the_order(self):
        args = order_args(governorate="el giza")
        summary = "اجمالي الاوردر 1,510 جنيه: جزمة كورة بيضا مقاس 43 بـ 1,450 جنيه، والشحن 60 جنيه. هيوصل في يوم أو يومين. أأكد؟"
        r = self.turn(FakeModel(tool_call("draft_order", args), call("cod_risk"), say(summary)), "عايز الجزمة البيضا مقاس 43")
        self.assertEqual((r.outcome, r.reply), ("replied", summary))
        self.assertIsNone(orders.Book(self.db).demo_order("#1001"))

        def confirm(messages, tools_sent):
            code = next(json.loads(m["content"])["code"] for m in reversed(messages)
                        if m["role"] == "tool" and '"code"' in (m["content"] or ""))
            return tool_call("draft_order", {**args, "confirm": code})
        r = self.turn(FakeModel(confirm, say("تمام، اوردر #1001 اتسجل، الاجمالي 1510 جنيه.")), "تمام اكد")
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(orders.Book(self.db).demo_order("#1001")["chat_id"], self.cid)
        self.assertEqual([x["outcome"] for x in self.results.for_chat(self.cid)], ["order_drafted", "replied", "order_created", "replied"])

    def test_a_yes_with_a_change_does_not_place_the_order(self):
        args = order_args(governorate="el giza")
        summary = "Total 1510 EGP: white football boots, size 43, at 1450 EGP, delivery 60 EGP. It arrives in 1 to 2 days. Confirm?"
        self.turn(FakeModel(tool_call("draft_order", args), say(summary)), "I want the white boots in 43")
        seen = []

        def confirm(messages, tools_sent):
            code = next(json.loads(m["content"])["code"] for m in reversed(messages)
                        if m["role"] == "tool" and '"code"' in (m["content"] or ""))
            return tool_call("draft_order", {**args, "confirm": code})

        def after(messages, tools_sent):
            seen.append(json.loads(messages[-1]["content"]))
            return say("Sure, here is the new summary in 44.")
        r = self.turn(FakeModel(confirm, after), "yes but in 44")
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(seen, [{"ok": False, "feedback": draft_order.NOT_A_YES}])
        self.assertIsNone(orders.Book(self.db).demo_order("#1001"))

    def test_a_past_orders_total_from_find_order_passes(self):
        """find_order adds the totals of this customer's own orders: a past order's real total passes,
        and a total from another customer's order, or a made-up one, is still refused."""
        cid = self.chats.open("whatsapp", A)
        self.chats.set_stage(cid, "my_order")

        def turn(model):
            msg = Message(channel="whatsapp", customer_id=A, text="how much was my order 7004?")
            return loop.turn(msg, chats=self.chats, model=model, lessons=Lessons(self.db), results=self.results,
                             send=self.out)
        right = "Your order #7004 was delivered. Its total was 1,660 EGP."
        r = turn(FakeModel(tool_call("find_order", {"order": "7004"}), say(right)))
        self.assertEqual((r.outcome, r.reply), ("replied", right))
        for wrong in ("Your order #7004 was delivered. Its total was 4,435 EGP.",   # another customer's order (#7011)
                      "Your order #7004 was delivered. Its total was 1,800 EGP."):
            with self.subTest(wrong=wrong):
                r = turn(FakeModel(tool_call("find_order", {"order": "7004"}), say(wrong),
                                   say("I will check with the team.")))
                self.assertEqual(r.reply, "I will check with the team.")
        self.assertEqual([x["outcome"] for x in self.results.for_chat(cid)],
                         ["replied", "check_failed", "replied", "check_failed", "replied"])

    def test_a_summary_with_the_address_and_another_countrys_phone_passes(self):
        args = order_args(governorate="Giza", address="الدقي، عمارة 125، الدور 3، شقة 12", phone="+44 7700 900123")
        summary = ("جزمة كورة بيضا مقاس 43 بـ 1450 جنيه، والشحن 60 جنيه، الاجمالي 1510 جنيه. العنوان: الدقي، عمارة 125، "
                   "الدور 3، شقة 12. الموبايل: +447700900123. أأكد؟")
        r = self.turn(FakeModel(tool_call("draft_order", args), say(summary), say("مش هيعدي")), "عايز الجزمة البيضا مقاس 43")
        self.assertEqual((r.outcome, r.reply), ("replied", summary))
        self.assertEqual(orders.Book(self.db).pending(self.cid)["draft"]["phone"], "447700900123")

    def test_a_voice_note_passed_on_to_a_person_counts_its_transcript(self):
        """Review t261028j finding 10 (r12): with a person, hearing a voice note for the team member is
        a model call, so it counts against the customer's limits like the pass on itself."""
        clean_env(self, OPERATOR_WHATSAPP="201000000001")
        self.chats.set_stage(self.cid, "with_person")
        model = FakeModel(say("فين الاوردر بتاعي"))
        msg = Message(channel="whatsapp", customer_id=ME, audio=b"RIFF fake wav", audio_mime="audio/wav")
        r = loop.turn(msg, chats=self.chats, model=model, lessons=Lessons(self.db), results=self.results,
                      send=self.out, limits=Limits(self.db))
        self.assertEqual(r.outcome, "waiting")
        self.assertEqual(len(model.calls), 1)
        notes = [t for to, t in self.out.sent if to == "201000000001"]
        self.assertEqual(len(notes), 1)
        self.assertIn("فين الاوردر بتاعي", notes[0])
        with self.db.tx() as c:
            counted = c.execute("SELECT COUNT(*) FROM model_calls WHERE customer = ?",
                                (limits_mod.key("whatsapp", ME),)).fetchone()[0]
        self.assertEqual(counted, 2)  # the pass on, then the transcript

    def test_a_made_up_total_is_still_blocked(self):
        args = order_args(governorate="Giza")
        r = self.turn(FakeModel(tool_call("draft_order", args), say("الاجمالي 1900 جنيه."), say("الاجمالي 1510 جنيه.")),
                      "عايز الجزمة البيضا مقاس 43")
        self.assertEqual(r.reply, "الاجمالي 1510 جنيه.")
        self.assertEqual([x["outcome"] for x in self.results.for_chat(self.cid)],
                         ["order_drafted", "check_failed", "replied"])


if __name__ == "__main__":
    unittest.main()
