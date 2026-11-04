"""Store offers (kit/offers.py, decision 105): the store data's offers read and cleaned, untrusted fields
dropped or capped, the file written whole, the turn's own offers before the store data's, what a tool may
show, and the totals: one offer an order (the one that saves most, a tie to the first listed), delivery on
top, the card percent on the items' total, whole pounds rounded half up. No model, no network."""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from kit import offers

ROOT = Path(__file__).resolve().parent.parent

ELITE = {"product": "Nike Phantom 6", "tier": "Elite", "size": "42", "price": "16500", "quantity": 1}
PRO = {"product": "Nike Phantom 6", "tier": "Pro", "size": "42", "price": "11000", "quantity": 1}
PRINT = {"product": "Beyond the Limits Name Printing", "type": "Printing", "size": "", "price": "400", "quantity": 1}


class Data(unittest.TestCase):
    def test_demo_offers_are_the_owners(self):
        d = offers.read(ROOT / "demo" / "offers.json")
        self.assertEqual([o["id"] for o in d["offers"]],
                         ["valu_3m", "card_5", "free_delivery", "elite_print", "second_pair", "lower_tier"])
        self.assertEqual((d["max_stack"], d["pick"], d["stack_counts"], d["round_to"]),
                         (1, "most_saved", {"delivery": False}, 1))
        self.assertEqual(d["payment_methods"], ["cash", "card", "valu"])
        by = {o["id"]: o for o in d["offers"]}
        self.assertEqual((by["valu_3m"]["method"], by["valu_3m"]["months"]), ("valu", 3))
        self.assertNotIn("percent_off", by["valu_3m"])
        self.assertEqual((by["card_5"]["method"], by["card_5"]["percent_off"]), ("card", 5))
        self.assertEqual(by["free_delivery"]["fee"], 0)
        self.assertEqual((by["second_pair"]["which"], by["second_pair"]["every_nth"]), ("cheaper", True))
        self.assertTrue(by["elite_print"]["per_item"])
        self.assertEqual(offers.percents(d), {Decimal(5), Decimal(10)})

    def test_untrusted_fields_are_cleaned(self):
        raw = {"max_stack": 99, "pick": "random", "round_to": -1, "stack_counts": {"delivery": "no", "addon": False,
               "evil": False}, "apply": ["payment", "run", "payment"], "payment_methods": ["Cash!", 3, "card"],
               "offer_talk": ["<b>sale</b>", True],
               "offers": [{"kind": "payment", "what": "<script>x</script>  Half off", "percent_off": 500, "id": "a"},
                          {"kind": "steal", "what": "x"}, {"kind": "choice"},
                          {"kind": "nth_item", "what": "w", "nth": 1, "which": "all", "every_nth": "yes",
                           "applies_to": {"Has": "Size", "x": {"deep": 1}}, "id": "a"},
                          {"kind": "choice", "what": "w2", "names": ["a" * 500, "a" * 500, None], "extra": 1}]}
        d = offers.clean(raw)
        self.assertEqual((d["max_stack"], d["pick"], d["round_to"]), (1, "most_saved", 1))
        self.assertEqual(d["stack_counts"], {"addon": False})
        self.assertEqual(d["apply"], ["payment"])
        self.assertEqual(d["payment_methods"], ["cash", "card"])
        self.assertEqual(d["offer_talk"], ["bsale/b"])
        self.assertEqual([o["id"] for o in d["offers"]], ["a", "offer_5"])  # the second "a" is dropped
        self.assertEqual(d["offers"][0]["what"], "scriptx/script Half off")
        self.assertNotIn("percent_off", d["offers"][0])
        self.assertEqual(d["offers"][1]["names"], ["a" * offers.MAX_WORD])
        self.assertNotIn("extra", d["offers"][1])

    def test_a_list_of_lines_gets_the_defaults(self):
        d = offers.clean([{"kind": "choice", "what": "A cheaper plan", "when": "price is the worry"}])
        self.assertEqual(d["max_stack"], 1)
        self.assertEqual(d["offers"], [{"id": "offer_1", "kind": "choice", "what": "A cheaper plan",
                                        "when": "price is the worry"}])

    def test_write_then_read_and_refusals(self):
        with tempfile.TemporaryDirectory() as t:
            offers.write(t, {"offers": [{"kind": "choice", "what": "A cheaper plan"}]})
            self.assertEqual(offers.read(t)["offers"][0]["what"], "A cheaper plan")
            self.assertEqual([p.name for p in Path(t).iterdir()], [offers.FILE])
            big = {"offers": [{"kind": "choice", "what": "x" * 150, "names": ["y" * 50] * 30, "id": f"o{i}"}
                              for i in range(20)]}
            big["offers"] = [dict(o, names=[f"{o['id']}{'y' * 50}{j}" for j in range(30)]) for o in big["offers"]]
            with self.assertRaises(offers.Refused):
                offers.write(t, big)
            link = Path(t) / "link"
            link.symlink_to(t)
            with self.assertRaises(offers.Refused):
                offers.write(link, {"offers": []})
            (Path(t) / offers.FILE).write_text("[not json", encoding="utf-8")
            self.assertIsNone(offers.read(t))
        self.assertIsNone(offers.read("/no/such/folder"))

    def test_the_turns_offers_come_first(self):
        mine = offers.clean([{"kind": "choice", "what": "mine"}])
        self.assertEqual(offers.current()["offers"][0]["id"], "valu_3m")
        self.assertIsNone(offers.own())
        token = offers.OFFERS.set(mine)
        try:
            self.assertIs(offers.current(), mine)
            self.assertIs(offers.own(), mine)
        finally:
            offers.OFFERS.reset(token)
        token = offers.OFFERS.set(offers.EMPTY)
        try:
            self.assertEqual(offers.current()["offers"], [])
        finally:
            offers.OFFERS.reset(token)

    def test_what_a_tool_shows(self):
        d = offers.demo()
        shown = offers.for_tool(d)
        self.assertTrue(all("names" not in o and "covers" not in o for o in shown))
        self.assertEqual(shown[0]["what"], "Pay in installments through valU")
        self.assertEqual(offers.limit_line(d),
                         "One offer an order: the one that saves the customer most applies; always on top: free_delivery.")
        self.assertIn("فاليو", offers.mention_words(d)["valu_3m"])
        self.assertIn("valu 3m", offers.mention_words(d)["valu_3m"])
        self.assertIn("خصم", offers.talk_words(d))
        self.assertEqual(offers.payment_methods(d), ["cash", "card", "valu"])
        self.assertEqual(offers.delivery_fee(d, 60), 0)
        self.assertEqual(offers.delivery_fee(d, 85), 0)
        self.assertEqual(offers.delivery_fee(offers.EMPTY, 60), 60)
        self.assertEqual(offers.delivery_offer(d)["id"], "free_delivery")
        self.assertEqual(offers.limit_line(offers.EMPTY), "")
        self.assertIn("never make up a discount", offers.PROMPT_LINE)


class Totals(unittest.TestCase):
    def setUp(self):
        self.d = offers.demo()

    def ids(self, got):
        return [x["offer"] for x in got["discounts"]]

    def test_card_saves_most_and_is_the_one_offer(self):
        got = offers.apply([ELITE, PRO, PRINT], "card", self.d, fee=60)
        self.assertEqual(got["subtotal"], Decimal(27900))
        self.assertEqual(self.ids(got), ["card_5"])          # 1395 beats the second pair's 1100 and printing's 400
        self.assertEqual(got["discounts"][0]["discount"], Decimal(1395))
        self.assertEqual((got["fee"], got["total"]), (Decimal(0), Decimal(26505)))

    def test_cash_gets_the_second_pair(self):
        got = offers.apply([ELITE, PRO, PRINT], "cash", self.d, fee=85)
        self.assertEqual(self.ids(got), ["second_pair"])
        self.assertEqual(got["discounts"][0]["discount"], Decimal(1100))   # 10% of the cheaper pair
        self.assertEqual(got["total"], Decimal(26800))

    def test_valu_saves_nothing_so_the_line_offer_applies(self):
        got = offers.apply([ELITE, PRINT], "valu", self.d)
        self.assertEqual(self.ids(got), ["elite_print"])
        self.assertEqual(got["total"], Decimal(16500))
        self.assertNotIn("fee", got)

    def test_printing_is_one_per_elite_pair(self):
        two = dict(PRINT, quantity=2)
        got = offers.apply([ELITE, two], "cash", self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(400))
        got = offers.apply([dict(ELITE, quantity=2), dict(PRINT, quantity=3)], None, self.d)
        # 2 pairs: the second pair (1650) beats two free printings (800)
        self.assertEqual(self.ids(got), ["second_pair"])
        got = offers.apply([PRO, PRINT], None, self.d)
        self.assertEqual(got["discounts"], [])

    def test_every_second_pair_on_the_cheaper(self):
        lines = [dict(ELITE, quantity=2), dict(PRO, quantity=2)]
        got = offers.apply(lines, None, self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(2200))   # the two cheaper pairs
        got = offers.apply([dict(ELITE, quantity=3)], None, self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(1650))   # 3 pairs: one discounted

    def test_a_tie_goes_to_the_first_listed(self):
        d = offers.clean({"max_stack": 1, "pick": "most_saved", "offers": [
            {"id": "b", "kind": "payment", "method": "card", "percent_off": 10, "what": "b"},
            {"id": "a", "kind": "nth_item", "nth": 2, "percent_off": 20, "applies_to": {"has": "size"},
             "which": "cheaper", "every_nth": True, "what": "a"}]})
        lines = [dict(ELITE, price="1000"), dict(PRO, price="1000")]
        self.assertEqual(self.ids(offers.apply(lines, "card", d)), ["b"])     # 200 and 200: b is listed first
        d["offers"].reverse()
        self.assertEqual(self.ids(offers.apply(lines, "card", d)), ["a"])

    def test_whole_pounds_half_up(self):
        got = offers.apply([dict(ELITE, price="16510")], "card", self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(826))       # 825.5
        got = offers.apply([dict(ELITE, price="16490")], "card", self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(825))       # 824.5
        got = offers.apply([dict(ELITE, price="16489")], "card", self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(824))       # 824.45
        got = offers.apply([dict(ELITE, price="16509")], "card", self.d)
        self.assertEqual(got["discounts"][0]["discount"], Decimal(825))       # 825.45

    def test_a_limit_of_two_and_the_listed_pick(self):
        d = json.loads(json.dumps(self.d))
        d["max_stack"] = 2
        got = offers.apply([ELITE, PRO, PRINT], "card", d, fee=60)
        self.assertEqual(self.ids(got), ["second_pair", "card_5"])   # worked in the apply order
        # the card's 5% is on what the items cost after the second pair: 26800 * 5% = 1340
        self.assertEqual(got["discounts"][1]["discount"], Decimal(1340))
        self.assertEqual(got["total"], Decimal(27900 - 1100 - 1340))
        d["max_stack"], d["pick"] = 1, "listed"
        self.assertEqual(self.ids(offers.apply([ELITE, PRO, PRINT], "card", d)), ["card_5"])
        self.assertEqual(self.ids(offers.apply([ELITE, PRINT], "cash", d)), ["elite_print"])

    def test_no_offers_no_change(self):
        got = offers.apply([ELITE, PRINT], "card", offers.EMPTY, fee=60)
        self.assertEqual((got["discounts"], got["fee"], got["total"]), ([], Decimal(60), Decimal(16960)))

    def test_bad_amounts_raise(self):
        with self.assertRaises(ValueError):
            offers.apply([dict(ELITE, price="-5")], None, self.d)


if __name__ == "__main__":
    unittest.main()
