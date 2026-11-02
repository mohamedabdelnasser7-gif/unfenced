"""Results that come later (DECISIONS item 66): reflection/results.py late() adds one to a case,
once a case for its group, and the delivery webhook (channels/bosta.py) sends delivered or refused
to the agent that owns the order's case: for Sales its second signal, for an agent whose plug
decides on delivered (the made-up shipper) the result that settles its case. Fake data only."""
import threading
import unittest

from channels import bosta
from engine.log import Log
from engine.study import BAD, GOOD, PENDING, settle
from kit.db import Db
from reflection import PLUG as SALES
from reflection.results import Results, late
from tests import plugs

T0 = 1_800_000_000.0


def body(state=45, ref="2001", delivery="d-1", **more):
    out = {"_id": delivery, "trackingNumber": 111, "state": state, "type": "SEND", "timeStamp": 1761700000000,
           "numberOfAttempts": 1, "businessReference": ref}
    out.update(more)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.results = Results(self.db)
        self.shipper = plugs.load(plugs.SHIPPER, self)
        self.ship = Log(self.db, self.shipper)
        self.told = []
        self.app = bosta.Deliveries(self.results, tell_team=self.told.append, plugs=[self.shipper])

    def parcel(self, case, order, at=T0):
        self.ship.act(case, "ship", result="shipped", stage="sending", detail={"order": order}, at=at)

    def sale(self, chat, order):
        self.results.record(chat, "order_created", stage="ordering",
                            detail={"order": order, "store": "shopify", "total": 100, "cod_risk": "low", "reasons": []})


class Late(Base):
    def test_once_a_case_for_each_group(self):
        self.parcel("p1", "#2001")
        self.assertIsNotNone(late(self.db, self.shipper, "p1", "delivered", by="mona", now=T0 + 5))
        self.assertIsNone(late(self.db, self.shipper, "p1", "refused", by="api", now=T0 + 6))
        rows = self.ship.case("p1")
        self.assertEqual([r["result"] for r in rows], ["shipped", "delivered"])
        self.assertEqual((rows[-1]["detail"]["by"], rows[-1]["at"], rows[-1]["source"]), ("mona", T0 + 5, "p1"))
        self.assertEqual(settle(self.shipper, rows, T0 + 10)[0], GOOD)

    def test_a_second_signal_and_the_deciding_result_are_two_groups(self):
        self.sale("chat-1", "#1001")
        self.assertIsNotNone(late(self.db, SALES, "chat-1", "delivered", now=T0))
        self.assertIsNone(late(self.db, SALES, "chat-1", "refused", now=T0 + 1))
        with self.assertRaises(ValueError):  # order_created is fast: it is never a late result
            late(self.db, SALES, "chat-1", "order_created")
        with self.assertRaises(ValueError):
            late(self.db, SALES, "chat-1", "chat_closed")

    def test_no_case_and_a_history_case_are_refused(self):
        with self.assertRaises(ValueError):
            late(self.db, self.shipper, "nobody", "delivered")
        self.ship.act("old", "ship", result="shipped", detail={"history": True, "order": "#9"}, at=T0)
        with self.assertRaises(ValueError):
            late(self.db, self.shipper, "old", "delivered")

    def test_two_writers_at_once_save_one(self):
        self.parcel("p1", "#2001")
        got, start = [], threading.Barrier(8)

        def mark(outcome):
            start.wait()
            got.append(late(self.db, self.shipper, "p1", outcome, now=T0 + 1))
        threads = [threading.Thread(target=mark, args=("delivered" if n % 2 else "refused",)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self.assertEqual(sum(g is not None for g in got), 1)
        self.assertEqual(len([r for r in self.ship.case("p1") if r["action"] is None]), 1)


class Webhook(Base):
    def test_delivered_settles_the_shippers_case_good(self):
        self.parcel("p1", "#2001")
        self.assertEqual(settle(self.shipper, self.ship.case("p1"), T0 + 99 * 86400)[0], PENDING)
        self.assertEqual(self.app.accept(body(45, ref="2001")), (200, "recorded"))
        self.assertEqual(settle(self.shipper, self.ship.case("p1"), T0)[0], GOOD)

    def test_refused_settles_it_bad_and_a_return_after_adds_nothing(self):
        self.parcel("p2", "2002")
        self.assertEqual(self.app.accept(body(47, ref="#2002", delivery="d-2", exceptionCode=8)), (200, "recorded"))
        self.assertEqual(settle(self.shipper, self.ship.case("p2"), T0)[0], BAD)
        self.assertEqual(self.app.accept(body(46, ref="2002", delivery="d-3", type="RTO")),
                         (200, "already recorded"))

    def test_a_person_first_then_the_webhook_saves_nothing_twice(self):
        self.parcel("p1", "#2001")
        late(self.db, self.shipper, "p1", "refused", by="mona")
        self.assertEqual(self.app.accept(body(45, ref="2001")), (200, "already recorded"))
        self.assertEqual([r["result"] for r in self.ship.case("p1")], ["shipped", "refused"])

    def test_sales_still_gets_its_second_signal(self):
        self.sale("chat-1", "#1001")
        self.assertEqual(self.app.accept(body(45, ref="1001", delivery="d-9")), (200, "recorded"))
        rows = self.results.for_chat("chat-1")
        self.assertEqual([r["outcome"] for r in rows], ["order_created", "delivered"])
        self.assertEqual(settle(SALES, self.results.case("chat-1"), T0)[0], GOOD)  # the order decided it

    def test_one_order_in_two_agents_is_unknown(self):
        self.parcel("p1", "#1001")
        self.sale("chat-1", "#1001")
        self.assertEqual(self.app.accept(body(45, ref="1001")), (404, "unknown order"))
        self.assertEqual([r["result"] for r in self.ship.case("p1")], ["shipped"])

    def test_an_agent_that_takes_no_delivery_result_is_never_searched(self):
        waterer = plugs.load(plugs.WATERER, self)
        app = bosta.Deliveries(self.results, plugs=[waterer])
        self.assertEqual(app.plugs, [])
        Log(self.db, waterer).act("bed", "water", result="soaked", detail={"order": "#3001"}, at=T0)
        self.assertEqual(app.accept(body(45, ref="3001")), (404, "unknown order"))

    def test_a_failed_attempt_on_the_shippers_order_is_a_note(self):
        self.parcel("p1", "#2001")
        self.assertEqual(self.app.accept(body(47, ref="2001", exceptionCode=3)), (200, "noted"))
        self.assertEqual(len(self.told), 1)
        self.assertEqual([r["result"] for r in self.ship.case("p1")], ["shipped"])


if __name__ == "__main__":
    unittest.main()
