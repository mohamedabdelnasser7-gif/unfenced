"""The night's API check (reflection/late.py) and Bosta's read-one-delivery answer
(channels/bosta.py api_outcome). A fake opener only: nothing reaches the network, and the key
is a made-up string read from no file."""
import io
import json
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from channels import bosta
from engine.log import Log
from engine.study import GOOD, settle
from kit.db import Db
from reflection import PLUG as SALES
from reflection import late as late_mod
from reflection.results import Results, late
from tests import plugs

T0 = 1_800_000_000.0
KEY = "made-up-key"


class Opener:
    """Answers each request with the next canned body, or raises it; keeps each request."""

    def __init__(self, *answers):
        self.answers, self.reqs = list(answers), []

    def __call__(self, req, timeout):
        self.reqs.append(req)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return io.BytesIO(json.dumps(a).encode() if not isinstance(a, bytes) else a)


def view(code, kind="SEND"):
    return {"success": True, "message": "", "data": {"state": {"code": code, "value": "x"},
                                                     "type": {"code": 10, "value": kind}}}


class ApiOutcome(unittest.TestCase):
    def test_delivered_and_returned_only(self):
        for answer, want in ((view(45), ("delivered", 45)), (view(46), ("refused", 46)),
                             (view(46, "RTO"), ("refused", 46)), (view(47), (None, 47)),
                             (view(45, "CUSTOMER_RETURN_PICKUP"), (None, 45)), ({"data": None}, (None, None))):
            with self.subTest(answer=answer):
                self.assertEqual(bosta.api_outcome("123", KEY, opener=Opener(answer)), want)

    def test_the_request_and_its_guards(self):
        op = Opener(view(45))
        bosta.api_outcome("4808 9608".replace(" ", ""), KEY, opener=op)
        req = op.reqs[0]
        self.assertEqual(req.full_url, "https://app.bosta.co/api/v2/deliveries/business/48089608")
        self.assertEqual(req.get_header("Authorization"), KEY)
        for bad in ("../x", "", "a" * 65, "1/2"):
            with self.assertRaises(ValueError):
                bosta.api_outcome(bad, KEY, opener=Opener(view(45)))
        with self.assertRaises(ValueError):
            bosta.api_outcome("123", "", opener=Opener(view(45)))
        with self.assertRaises(ValueError):
            bosta.api_outcome("123", KEY, opener=Opener(b"x" * (bosta.MAX_API_BODY + 1)))

    def test_an_answer_sent_a_byte_at_a_time_stops_at_the_deadline(self):
        """Red team late r1 finding 1: each read had its own timeout and the whole answer none, so a
        server dripping one byte at a time held the night. A local server this test starts and stops."""
        body = json.dumps(view(45)).encode()

        class Drip(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    for b in body:
                        self.wfile.write(bytes([b]))
                        self.wfile.flush()
                        time.sleep(0.02)
                except OSError:  # the client gave up, as it should
                    pass

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Drip)
        th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        th.start()
        self.addCleanup(th.join, 5)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}/x"

        def local(req, timeout):
            return urllib.request.build_opener().open(urllib.request.Request(url), timeout=timeout)

        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            bosta.api_outcome("123", KEY, opener=local, timeout=0.3)
        self.assertLess(time.monotonic() - started, 1.2)  # the body alone takes over 2 seconds
        self.assertEqual(bosta.api_outcome("123", KEY, opener=local, timeout=30), ("delivered", 45))


class NightCheck(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.results = Results(self.db)
        self.shipper = plugs.load(plugs.SHIPPER, self)
        self.ship = Log(self.db, self.shipper)

    def parcel(self, case, tracking=None, at=T0):
        detail = {"order": f"#{case}"}
        if tracking:
            detail["tracking"] = tracking
        self.ship.act(case, "ship", result="shipped", stage="sending", detail=detail, at=at)

    def test_it_settles_waiting_cases_and_skips_the_rest(self):
        self.parcel("p1", "111")
        self.parcel("p2", "222")
        self.parcel("p3")  # no tracking number: not asked
        self.parcel("p4", "444")
        late(self.db, self.shipper, "p4", "refused", by="mona", now=T0 + 1)  # has its result
        rep = late_mod.check(self.db, [self.shipper], lambda t: {"111": ("delivered", 45)}.get(t, (None, 47)),
                             now=T0 + 3 * 86400)
        self.assertEqual((rep["asked"], rep["recorded"], rep["failed"]), (2, 1, 0))
        rows = self.ship.case("p1")
        self.assertEqual((rows[-1]["result"], rows[-1]["detail"]["by"]), ("delivered", "api"))
        self.assertEqual(settle(self.shipper, rows, T0 + 4 * 86400)[0], GOOD)

    def test_an_api_result_counts_in_tonights_study(self):
        """Review late r1 finding 3: the study reads rows before the night's own time, so a result
        saved at that time waited for the next night."""
        from engine import study
        self.parcel("p1", "111")
        now = T0 + 3 * 86400
        late_mod.check(self.db, [self.shipper], lambda t: ("delivered", 45), now=now)
        self.assertLess(self.ship.case("p1")[-1]["at"], now)
        cases = study._read(self.shipper, self.ship.window(now - 30 * 86400, now), now)
        self.assertEqual([(c.id, c.status) for c in cases], [("p1", GOOD)])

    def test_a_failed_call_is_counted_and_the_limit_holds(self):
        for n in range(5):
            self.parcel(f"p{n}", f"{n}00", at=T0 + n)

        def down(t):
            raise OSError("down")
        rep = late_mod.check(self.db, [self.shipper], down, now=T0 + 86400, limit=3)
        self.assertEqual((rep["asked"], rep["failed"], rep["recorded"]), (3, 3, 0))

    def test_sales_orders_carry_no_tracking_number_so_the_api_asks_nothing_for_them(self):
        """The limit in the module line: a Sales order row names the store's order number only."""
        self.assertEqual(SALES.late(), ((), ("delivered", "refused")))
        self.results.record("chat-1", "order_created", stage="ordering",
                            detail={"order": "#1001", "store": "shopify", "total": 1, "cod_risk": "low", "reasons": []})
        rows = self.results.case("chat-1")
        now = rows[-1]["at"] + 60
        self.assertEqual(settle(SALES, rows, now)[0], GOOD)
        self.assertEqual(late_mod.waiting(self.db, SALES, now), [])
        self.results.record("chat-1", "delivered", detail={"order": "#1001", "bosta": "555"})
        self.assertEqual(late_mod.waiting(self.db, SALES, now + 60), [])  # it has its second signal

    def test_no_key_runs_nothing(self):
        self.parcel("p1", "111")
        self.assertIsNone(late_mod.run(self.db, [self.shipper], now=T0, key=""))
        self.assertIn("not run", late_mod.line(None))
        rep = late_mod.run(self.db, [self.shipper], now=T0 + 1, key=KEY, opener=Opener(view(45)))
        self.assertEqual(rep["recorded"], 1)
        self.assertIn("1 results recorded", late_mod.line(rep))


class NightWiring(unittest.TestCase):
    """reflection/night.py courier_check: this agent's own cases, through the patched network only."""
    setUp, parcel = NightCheck.setUp, NightCheck.parcel

    def test_the_night_asks_for_its_own_waiting_cases(self):
        from unittest import mock
        from reflection import night
        self.parcel("p1", "111")
        op = Opener(view(45))
        with mock.patch.dict("os.environ", {bosta.API_KEY: KEY}), mock.patch("kit.env.load", return_value=[]), \
                mock.patch("kit.net.open_once", op):
            rep = night.courier_check(self.db, self.shipper, T0 + 86400)
        self.assertEqual((rep["asked"], rep["recorded"]), (1, 1))
        self.assertEqual(op.reqs[0].full_url, bosta.API_BASE + "111")
        self.assertEqual(self.ship.case("p1")[-1]["result"], "delivered")
        self.assertIn("1 results recorded", late_mod.line(rep))
        self.assertNotIn(KEY, late_mod.line(rep))


if __name__ == "__main__":
    unittest.main()
