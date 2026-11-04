"""Fixes from review and red team t261028j round 3 (29 Oct), one class per finding.

Each fix test failed before its fix. The replies come from the reviewer's probes and the red
team's proof scripts, run offline on the fake model, in memory SQLite, with no network.
"""
import json
import unittest

from sales import loop
from kit.chats import FIXED
from tests.fake_model import FakeModel, clean_env, say
from tests.test_fixes_j import SendCheckBase, TurnBase, confirm_from_history, summary_reply
from tests.test_orders import ME, tool_call
from kit import offers

REVIEW_AMOUNTS = {16500, 60, 70, 33060, 1850, 1920}
LINE = "اوردرك اتسجل برقم #1001، والإجمالي 33,060 جنيه."


class NumberCheck(SendCheckBase):
    def blocked(self, reply, amounts=frozenset({16500, 400, 60, 33060, 33000})):
        return "not in the store or delivery data" in self.check(reply, set(amounts))[1]

    def passes(self, reply):
        fb = self.check(reply, self.amounts | REVIEW_AMOUNTS)[1]
        return [p for p in ("not in the store or delivery data", "Write every amount in digits") if p in fb]


class AddressLineTest(NumberCheck):
    """Review 1: a line that ends in a price word reads into the next line only when that line
    starts with a number or #, and an address label is not a price word, so an address number
    in a summary is not read as an amount."""

    PASS = ("Payment: cash on delivery\nAddress: Madinaty, Building 15, Apartment 302",
            "الدفع كاش عند التوصيل\nالعنوان: مدينتي، عمارة 15، شقة 302",
            "الإجمالي 1,920 جنيه شامل التوصيل\nهيوصلك على مدينتي، عمارة 15، شقة 302 خلال 3 أيام",
            "عنوان التوصيل:\nشقة 302، عمارة 15", "Delivery address:\nApartment 302",
            "عنوان التوصيل: شقة 302، عمارة 15، مدينتي", "Delivery address: Apartment 302, Building 15, Madinaty",
            "عنوان الشحن:\nعمارة 125، شارع 9، المعادي", "Shipping address: Apartment 302",
            "3enwan el tawsil:\n3emara 125, share3 9", "Free delivery\nElite is available in 43 and 44",
            "Name: Mohamed\nPhone: 01012345678\nPayment: cash on delivery\n"
            "Address: Madinaty, Building 15, Apartment 302\nTotal: 1,920 EGP",
            "ملخص طلبك:\nهودي أسود مقاس L، العدد 1: 1,850 جنيه\nالتوصيل للقاهرة: 70 جنيه\nالإجمالي: 1,920 جنيه\n"
            "الاسم: محمد\nالعنوان: مدينتي، عمارة 15، شقة 302\nالموبايل: 01012345678\nهيوصلك خلال 3 أيام\nأأكد الطلب؟",
            "Your order:\nBlack Hoodie L x1: 1,850 EGP\nDelivery: 70 EGP\nTotal: 1,920 EGP\nName: Mohamed\n"
            "Address: Madinaty, Building 15, Apartment 302\nPhone: 01012345678\nShall I confirm?",
            "الإجمالي: 33,060 جنيه\n#1001 هيوصل بكرة")
    BLOCK = ("Total\n#1500", "Total\nis #1500", "Total\n(#1500)", "The total is\n#1500.",
             "Delivery to your house 120.", "Delivery address fee 120", "عنوان التوصيل وسعر الشحن 120")

    def test_address_numbers_pass(self):
        for reply in self.PASS:
            with self.subTest(reply=reply):
                self.assertEqual(self.passes(reply), [])

    def test_a_number_after_a_price_word_line_still_counts(self):
        for reply in self.BLOCK:
            with self.subTest(reply=reply):
                self.assertTrue(self.blocked(reply))


def u(*points):
    """Characters from code points, so the test source holds no invisible or look-alike character."""
    return "".join(chr(p) for p in points)


class LineGapTest(NumberCheck):
    """Red team 4: blank lines, look-alike colons, invisible blanks and price words that are not the
    line's last word no longer hide a # amount on the next line."""

    BLANK_LINES = ("Total:\n\n#1500", "Total:\n \n#1500", "Total:\n\t\n#1500", "Total:\r\n\r\n#1500",
                   "الإجمالي:\n\n#1500", "The total is\n\n#1500.", "Delivery:\n\nTo your house 120.", "Shipping:\n\nonly 43.",
                   "Total\n\n\n#1500", "Total:\n" + u(0x2800) + "\n#1500", "Total\n:\n#1500")
    SIGNS = tuple(f"Total{u(c)}\n#1500" for c in (0xFF1A, 0xFE55, 0xFE13, 0xA789, 0x2236, 0x02D0, 0x02F8)) + tuple(
        f"Total {u(c)}\n#1500" for c in (0xFF1D, 0xFE66, 0x207C, 0x208C)) + ("الإجمالي" + u(0xFF1A) + "\n#1500",)
    BLANKS = tuple(f"Total:{u(c)}\n#1500" for c in (0x034F, 0x3164, 0x2800, 0x115F, 0x1160, 0xFFA0, 0xFE0F, 0xE0100)) + (
        "Total" + u(0x3164) + "is" + u(0x3164) + "#1500", "Price: 1" + u(0x2800) + "400 EGP")
    WORDS = ("Total comes to\n#1500", "Total amount\n#1500", "الإجمالي هيبقى\n#1500", "الاجمالي بتاعك\n#1500",
             "El egmaly\n#1500", "egmali\n#1500", "المبلغ المطلوب\n#1500", "مبلغ\n#1500", "El egmaly #1500", "المبلغ #1500",
             "Total for size 43\n#1500", "Total for 2 pairs comes to\n#1500")
    PASS = ("Delivery address:\n\nApartment 302", "Payment: cash on delivery\n\nAddress: Madinaty, Building 15, Apartment 302",
            "الإجمالي: 33,060 جنيه\n\n#1001 هيوصل بكرة", "Total: 16500 EGP\n\n#1042 is on its way.",
            "Delivery takes 2 to 3 days\nwith the courier.", "The price is 16" + u(0x034F) + "500 EGP.",
            "التوصيل:\n\nخلال 3 أيام", "المبلغ: 33,060 جنيه")

    def test_must_block(self):
        for reply in self.BLANK_LINES + self.SIGNS + self.BLANKS + self.WORDS:
            with self.subTest(reply=reply.encode("unicode_escape").decode()):
                self.assertTrue(self.blocked(reply))

    def test_still_passes(self):
        for reply in self.PASS:
            with self.subTest(reply=reply.encode("unicode_escape").decode()):
                self.assertEqual(self.passes(reply), [])


PLACED = "اوردرك اتسجل برقم #1001، والإجمالي 33060 جنيه."


class GivenOrderTest(NumberCheck):
    """Review note 1: the order name a draft_order or find_order result gave this turn reads as an
    order number wherever it stands whole; any other #number still counts as an amount."""

    def problems(self, reply, orders, amounts=frozenset({16500, 400, 60, 33060, 33000})):
        from kit import send_check
        fb = send_check.check(reply, "ازيك", set(amounts), self.vocab, self.sizes, orders=orders)[1]
        return [p for p in ("not in the store or delivery data", "Write every amount in digits") if p in fb]

    def test_the_given_order_name_passes(self):
        for reply, orders in ((PLACED, {"#1001"}), (PLACED, ("1001",)), (PLACED, {"#1001", "#1002"}),
                              (PLACED.replace("1001", "١٠٠١"), {"#1001"}), (LINE, ["#1001"]),
                              ("طلبك برقم #1001 اتشحن، والإجمالي 33060 جنيه.", {"#1001"})):
            with self.subTest(reply=reply, orders=orders):
                self.assertEqual(self.problems(reply, orders), [])

    def test_any_other_number_still_counts(self):
        for reply, orders in ((PLACED, ()), (PLACED, {"#1002"}), (PLACED.replace("1001", "1002"), {"#1001"}),
                              (PLACED.replace("1001", "10011"), {"#1001"}), ("الإجمالي 1001 جنيه", {"#1001"}),
                              ("الإجمالي #1001 جنيه", {"#1001"}), (PLACED, {"#100"}), (PLACED, {"#1001x"})):
            with self.subTest(reply=reply, orders=orders):
                self.assertIn("not in the store or delivery data", self.problems(reply, orders))


class GivenOrderTurnTest(TurnBase):
    """Review note 1 through the loop: the model's own line with the order it just placed, or the
    order find_order just found, goes out; the names come only from this turn's tool results."""

    def order(self):
        self.turn(FakeModel(tool_call("draft_order", self.args), summary_reply), "عايز اتنين الإيليت مقاس 43")
        return self.turn(FakeModel(confirm_from_history(self.args), say(PLACED), say(PLACED), say(PLACED)), "تمام")

    def test_the_order_just_placed_passes(self):
        r = self.order()
        self.assertTrue(self.placed())
        self.assertEqual((r.outcome, r.reply), ("replied", PLACED))
        self.assertEqual(loop.order_names(self.chats, self.cid), {"#1001"})

    def test_the_order_find_order_found_passes(self):
        self.order()
        self.chats.set_stage(self.cid, "my_order")
        reply = "طلبك برقم #1001 اتسجل، والإجمالي 33060 جنيه."
        r = self.turn(FakeModel(tool_call("find_order", {}), say(reply), say(reply), say(reply)), "الاوردر فين؟")
        self.assertEqual((r.outcome, r.reply), ("replied", reply))
        self.assertEqual(loop.order_names(self.chats, self.cid), {"#1001"})

    def test_a_name_from_an_earlier_turn_is_not_given(self):
        self.order()
        self.chats.set_stage(self.cid, "my_order")
        r = self.turn(FakeModel(say(PLACED), say(PLACED), say(PLACED)), "تمام شكرا")
        self.assertEqual(loop.order_names(self.chats, self.cid), set())
        self.assertNotEqual(r.outcome, "replied")

    def test_order_names_never_raises(self):
        class Broken:
            def steps(self, chat_id):
                raise RuntimeError("db down")
        with self.assertLogs("sales.loop"):
            self.assertEqual(loop.order_names(Broken(), self.cid), set())


def setUpModule():
    """These tests read the zone fees (60, 85) as they were before decision 105: the store with no offers.
    The offers' own paths are in tests/test_offers.py and tests/test_offers_paths.py."""
    global _OFFERS_TOKEN
    _OFFERS_TOKEN = offers.OFFERS.set(offers.EMPTY)


def tearDownModule():
    offers.OFFERS.reset(_OFFERS_TOKEN)


if __name__ == "__main__":
    unittest.main()
