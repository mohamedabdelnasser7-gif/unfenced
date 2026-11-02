"""Three fixes from a measured Arena run (2026-10-31), each from both sides:

1. The exchange window ("ممكن تبدل المقاس خلال 14 يوم") is not a delivery time, while a wrong
   delivery time still fails the delivery fact check.
2. The name printing price (400, an extra on any boot) counts when the reply or the customer names
   a boot, while a price that is no store price still fails.
3. A photo or link request is answered: the store tool gives each product's image link, and the
   send check lets a reply carry only a link the store tool gave in this chat.
"""
import json
import unittest
from pathlib import Path
from unittest import mock

from arena import factcheck
from channels.base import Message
from kit import send_check
from kit.chats import Chats
from kit.db import Db
from kit.tools import store
from reflection.lessons import Lessons
from reflection.results import Results
from sales import loop
from tests.fake_model import FakeModel, Outbox, call, clean_env, say

ROOT = Path(__file__).resolve().parent.parent
VAPOR_LINK = "https://images.beyond-the-limits.example/mercurial-vapor-17.jpg"
REAL_REPLY = ("التوصيل لحد باب البيت والدفع كاش عند الاستلام وممكن تبدل المقاس خلال 14 يوم بس لازم يكون "
              "متلبسش و علبته موجوده")
PRINTING_REPLY = "الطباعة عندنا للاسم بس، 400 جنيه لاتنين ستيكر واحد على كل فردة"


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class ExchangeDays(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_the_exchange_window_is_not_a_delivery_time(self):
        for reply in (REAL_REPLY,
                      "Delivery takes 2 to 3 days, and you can exchange the size within 14 days.",
                      "Delivery takes 2 days and you can exchange within 14 days.",
                      "Within 14 days you can return it unworn, delivery is 2 days.",
                      "momken tbadel khelal 14 yom, w el tawseel 2 to 4 ayam",
                      "ممكن تبدل خلال 14 يوم من التوصيل",
                      "التوصيل يومين والاستبدال خلال 14 يوم",
                      "Shipping is 60 EGP and swaps are fine within 14 days."):
            self.assertEqual(checks(reply, "عايز Mercurial Vapor Elite مقاس 43"), [], reply)

    def test_a_wrong_delivery_time_still_fails(self):
        for reply in ("التوصيل خلال 14 يوم",
                      "Delivery takes 14 days.",
                      "You can exchange within 14 days, delivery takes 10 days.",
                      "Within 14 days delivery, exchange any time.",
                      "el tawseel 14 yom",
                      "التوصيل في يومين بدل 5 ايام"):   # a bare بدل (instead of) is no exchange word
            self.assertEqual(checks(reply), ["delivery"], reply)

    def test_exchange_days_reads_the_nearest_word(self):
        s = "Delivery is 2 days and exchange within 14 days"
        self.assertFalse(factcheck.exchange_days(s, s.index("2 days")))
        self.assertTrue(factcheck.exchange_days(s, s.index("14")))
        self.assertTrue(factcheck.exchange_days("14 days to exchange, delivery 2 days", 0))
        self.assertFalse(factcheck.exchange_days("14 days delivery, exchange later", 0))
        self.assertFalse(factcheck.exchange_days("14 days", 0))

    def test_the_store_policy_says_14_days(self):
        # The window the agent gave is the store's own exchange rule, not one it made up.
        text = (ROOT / "sales" / "instructions.md").read_text(encoding="utf-8")
        self.assertIn("exchanges within 14 days for a different size, unworn and in its packaging.", text)


class PrintingPrice(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_the_printing_price_counts_with_a_named_boot(self):
        self.assertEqual(checks(PRINTING_REPLY, "ممكن تطبعلي اسمي على ال Mercurial Vapor Elite؟"), [])
        self.assertEqual(checks("The Mercurial Vapor 17 Elite is 16,500 EGP and the name printing 400 EGP."), [])
        self.assertEqual(checks("The Mercurial Vapor 17 Elite with your name printed comes to 16,900 EGP."), [])
        self.assertEqual(checks("The Mercurial Vapor 17 Elite with printing and delivery to Cairo is 16,960 EGP."), [])

    def test_a_wrong_price_still_fails(self):
        self.assertEqual(checks("الطباعة 500 جنيه", "ممكن تطبعلي اسمي على ال Mercurial Vapor Elite؟"), ["price"])
        self.assertEqual(checks("The Mercurial Vapor 17 Elite with your name printed comes to 16,950 EGP."), ["price"])
        self.assertEqual(checks("The Mercurial Vapor 17 Elite is 450 EGP."), ["price"])
        self.assertEqual(checks("Two printings come to 800 EGP.", "Mercurial Vapor"), ["price"])

    def test_extras_are_the_products_with_no_tier_and_no_size(self):
        self.assertEqual([i["title"] for i in store.extras()], ["Beyond the Limits Name Printing"])
        items = [{"title": "A", "variants": [{"tier": "Elite", "price": "1"}]},
                 {"title": "B", "variants": [{"size": "43", "price": "1"}]},
                 {"title": "C", "variants": [{"price": "1"}]},
                 {"title": "D"}]
        with mock.patch.object(store, "catalogue", return_value=items):
            self.assertEqual([i["title"] for i in store.extras()], ["C"])


class ImageLinks(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_every_demo_product_has_a_stand_in_link(self):
        items = store.catalogue()
        self.assertEqual(len(items), 6)
        for item in items:
            self.assertTrue(item["image"].startswith("https://images.beyond-the-limits.example/"), item["title"])
        vapor = next(i for i in items if i["title"] == "Nike Mercurial Vapor 17")
        self.assertEqual(vapor["image"], VAPOR_LINK)
        # the stand-in links stay out of the seed mutation's variables
        data = json.loads((ROOT / "demo" / "catalogue.json").read_text(encoding="utf-8"))
        self.assertNotIn("image", json.dumps(data["variables"]))

    def test_only_a_plain_https_link_goes_out(self):
        self.assertEqual(store._image(VAPOR_LINK), VAPOR_LINK)
        for bad in ("http://images.example/a.jpg", "javascript:alert(1)", "https://a.example/a b.jpg",
                    'https://a.example/"x', "", None, 5, " " + VAPOR_LINK):
            self.assertIsNone(store._image(bad), bad)

    def test_shopify_featured_media_url(self):
        from tests.test_orders import _Resp
        page = {"shop": {"currencyCode": "EGP"}, "products": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"title": "Nike Phantom 6", "productType": "Football Boots", "description": "x",
                           "featuredMedia": {"preview": {"image": {"url": "https://cdn.shop.test/p6_1.jpg?v=12345"}}},
                           "variants": {"nodes": []}},
                          {"title": "No Image", "productType": "Football Boots", "description": "x",
                           "featuredMedia": None, "variants": {"nodes": []}}]}}
        clean_env(self, SHOPIFY_STORE="demo-shop.myshopify.com", SHOPIFY_TOKEN="test-token-not-real")
        sent = []

        def fake_open(director, req, data_=None, timeout=None):
            sent.append(json.loads(req.data)["query"])
            return _Resp(json.dumps({"data": page}).encode())
        import urllib.request
        with mock.patch.object(urllib.request.OpenerDirector, "open", fake_open):
            items = store._from_shopify()
        self.assertIn("featuredMedia { preview { image { url } } }", sent[0])
        self.assertEqual(items[0]["image"], "https://cdn.shop.test/p6_1.jpg?v=12345")
        self.assertNotIn("image", items[1])


class LinkCheck(unittest.TestCase):
    def names(self, reply, links=(), customer="ممكن صورة للجزمة دي لو سمحت؟ ال Vapor"):
        return [n for n, _ in send_check.named_problems(reply, customer, {16500}, store.vocabulary(), links=links)]

    def test_a_link_the_store_gave_passes(self):
        self.assertEqual(self.names(f"دي صورة الـ Mercurial Vapor 17: {VAPOR_LINK}", {VAPOR_LINK}), [])
        self.assertEqual(self.names(f"اتفضل الصورة {VAPOR_LINK}.", {VAPOR_LINK}), [])
        shop = "https://cdn.shop.test/files/vapor_17_elite_1234.jpg?v=987654"
        self.assertEqual(self.names(f"Here is a photo of the Vapor: {shop}", {shop}, "photo of the vapor?"), [])

    def test_any_other_link_is_refused(self):
        given = {VAPOR_LINK}
        for reply in ("دي الصورة https://evil.example/vapor.jpg",
                      f"دي الصورة {VAPOR_LINK}.evil.com",
                      f"دي الصورة {VAPOR_LINK}x",
                      "شوف www.evil.com",
                      "شوف evil.com",
                      "شوف shop.example/vapor",
                      "شوف bad.photos/vapor",   # a domain with a path, whatever its ending
                      "شوف evil" + chr(0x200B) + ".com",   # an invisible character does not hide it
                      "شوف http://images.beyond-the-limits.example/mercurial-vapor-17.jpg",
                      "دي الصورة https://images.beyond-the-limits.example/mercurial-vapor-17" + chr(0x200B) + ".jpg"):
            self.assertIn("links", self.names(reply, given), reply)
        self.assertIn("links", self.names(f"دي الصورة {VAPOR_LINK}"))   # not given in this chat
        self.assertIn("links", self.names("Here: https://evil.example/a", given, "photo please"))
        self.assertFalse(send_check.check(f"Here: {VAPOR_LINK}", "photo please")[0])

    def test_no_link_read_in_plain_text(self):
        for reply in ("الـ Vapor 17 Elite بـ 16,500 جنيه.", "The Elite is 16.500 EGP, e.g. size 43.",
                      "Sizes 39 to 46. Thanks!"):
            self.assertEqual(send_check.links_in(reply), [], reply)


class StoreLinks(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)

    def test_only_store_results_give_links(self):
        cid = self.chats.open("whatsapp", "201000000001")
        self.chats.add_step(cid, "user", content="https://user.example/a.jpg")
        self.chats.add_step(cid, "tool", name="store", tool_call_id="1",
                            content=json.dumps({"ok": True, "items": [{"title": "V", "image": VAPOR_LINK},
                                                                      {"title": "H", "image": "http://x.example/h.jpg"}]}))
        self.chats.add_step(cid, "tool", name="find_order", tool_call_id="2",
                            content=json.dumps({"ok": True, "items": [{"image": "https://order.example/o.jpg"}]}))
        self.chats.add_step(cid, "tool", name="store", tool_call_id="3",
                            content=json.dumps({"ok": False, "items": [{"image": "https://fail.example/f.jpg"}]}))
        self.assertEqual(loop.store_links(self.chats, cid), {VAPOR_LINK})


class PhotoTurn(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.lessons, self.results = Chats(self.db), Lessons(self.db), Results(self.db)
        self.out = Outbox()

    def turn(self, model, text):
        msg = Message(channel="whatsapp", customer_id="201000000002", text=text)
        return loop.turn(msg, chats=self.chats, model=model, lessons=self.lessons, results=self.results, send=self.out)

    def test_the_store_link_goes_out(self):
        reply = f"Here is a photo of the Mercurial Vapor: {VAPOR_LINK}"   # the customer line reads as English
        r = self.turn(FakeModel(call("store", query="vapor"), say(reply)), "ممكن صورة لل Nike Mercurial Vapor Elite ؟")
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.out.sent[-1][1], reply)

    def test_a_link_the_store_did_not_give_is_sent_back(self):
        model = FakeModel(call("store", query="vapor"), say("دي الصورة https://evil.example/vapor.jpg"),
                          say(f"دي الصورة {VAPOR_LINK}"))
        r = self.turn(model, "ممكن لينك للجزمة دي لو سمحت؟ ال Vapor")
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.out.sent[-1][1], f"دي الصورة {VAPOR_LINK}")
        self.assertIn("No other links", model.calls[-1]["messages"][-1]["content"])

    def test_instructions_answer_a_photo_or_link_request(self):
        self.assertIn("image link", store.DEFINITION["function"]["description"])


if __name__ == "__main__":
    unittest.main()
