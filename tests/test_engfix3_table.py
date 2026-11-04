"""Arena run 20261104T143545, cause 4: a tool called without the key it looks up by returns every option
it holds (kit/tools run, NEEDS and table) instead of refusing, so delivery with no governorate gives every
zone's fee and days. Made-up data only, no network."""
import types
import unittest
from unittest import mock

from kit import offers, send_check, tools
from kit.tools import delivery

ZONES = {"zones": [{"area": "Zone A", "fee": 61, "days_min": 1, "days_max": 2},
                   {"area": "Zone B", "fee": 83, "days_min": 3, "days_max": 5}]}
GOVS = {"governorates": [{"name": "Alpha", "name_ar": "ألفا", "zone": "Zone A", "spellings": []},
                         {"name": "Beta", "name_ar": "بيتا", "zone": "Zone B", "spellings": []}]}


def ctx(*names):
    return types.SimpleNamespace(stage=types.SimpleNamespace(tools=names, moves_to=()))


class FakeLookup:
    NAME = "lookup"
    NEEDS = ("code",)
    DEFINITION = {}

    @staticmethod
    def check(args, ctx):
        return False, "Give the code."

    @staticmethod
    def run(args, ctx):
        return {"ok": True}

    @staticmethod
    def table(ctx):
        return {"ok": True, "rows": [{"code": "a", "price": 5}]}


class Table(unittest.TestCase):
    def setUp(self):
        p1 = mock.patch.object(delivery.store, "delivery", return_value=ZONES)
        p2 = mock.patch.object(delivery, "_data", return_value=GOVS)
        p1.start(), p2.start()
        self.addCleanup(mock.patch.stopall)
        token = offers.OFFERS.set(offers.EMPTY)  # no offers: the zones' own fees
        self.addCleanup(offers.OFFERS.reset, token)

    def test_delivery_with_no_governorate_gives_every_zone(self):
        for args in ({}, {"governorate": ""}, {"governorate": "  "}, {"governorate": None}):
            with self.subTest(args=args):
                out = tools.run("delivery", args, ctx("delivery"))
                self.assertTrue(out["ok"], out)
                self.assertEqual([(z["area"], z["fee"], z["days_min"], z["days_max"], z["governorates"])
                                  for z in out["zones"]],
                                 [("Zone A", 61, 1, 2, ["Alpha"]), ("Zone B", 83, 3, 5, ["Beta"])])
                self.assertEqual(send_check.amounts_in(out), {61, 83})  # the fees reach the send check

    def test_a_delivery_offer_sets_every_zones_fee_and_keeps_the_days(self):
        token = offers.OFFERS.set(offers.clean([{"id": "free_ship", "kind": "delivery", "what": "Free delivery",
                                                  "fee": 0}]))
        self.addCleanup(offers.OFFERS.reset, token)
        out = tools.run("delivery", {}, ctx("delivery"))
        self.assertEqual([(z["area"], z["fee"], z["days_min"], z["days_max"]) for z in out["zones"]],
                         [("Zone A", 0, 1, 2), ("Zone B", 0, 3, 5)])
        self.assertEqual(out["offer"], "Free delivery")
        with mock.patch.object(delivery, "find", return_value=[GOVS["governorates"][1]]):
            one = tools.run("delivery", {"governorate": "Beta"}, ctx("delivery"))
        self.assertEqual((one["fee"], one["days_min"], one["days_max"], one["offer"]), (0, 3, 5, "Free delivery"))

    def test_with_no_offers_there_is_no_offer_field(self):
        out = tools.run("delivery", {}, ctx("delivery"))
        self.assertNotIn("offer", out)
        with mock.patch.object(delivery, "find", return_value=[GOVS["governorates"][1]]):
            one = tools.run("delivery", {"governorate": "Beta"}, ctx("delivery"))
        self.assertEqual(one["fee"], 83)
        self.assertNotIn("offer", one)

    def test_a_bad_governorate_still_refuses(self):
        self.assertFalse(tools.run("delivery", {"governorate": 5}, ctx("delivery"))["ok"])
        self.assertFalse(tools.run("delivery", {"governorate": "Nowhere"}, ctx("delivery"))["ok"])
        self.assertNotIn("zones", tools.run("delivery", {}, ctx("store")))  # not offered: no table

    def test_the_definition_lets_it_be_left_out(self):
        self.assertNotIn("required", delivery.DEFINITION["function"]["parameters"])

    def test_any_tool_with_needs_and_table(self):
        with mock.patch.dict(tools.TOOLS, {"lookup": FakeLookup}):
            self.assertEqual(tools.run("lookup", {}, ctx("lookup"))["rows"][0]["price"], 5)
            self.assertEqual(tools.run("lookup", {"code": "x"}, ctx("lookup")),
                             {"ok": False, "feedback": "Give the code."})


if __name__ == "__main__":
    unittest.main()
