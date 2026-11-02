"""Task t261029s gap 3: Bosta's delivery webhook (channels/bosta.py). Delivered or refused
reaches the chat that placed the order, through the order number its order_created row names;
each message is checked by a secret header in constant time; unknown orders and replays are
refused; a failed attempt is a note for the team, not a result.

Demo data only: the orders, tracking numbers and phone numbers are made up. The server runs
on a free local port and is shut down after each test; nothing reaches the network."""
import hmac
import http.client
import json
import os
import secrets
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from channels import bosta
from kit.db import Db
from reflection.results import Results

SECRET = secrets.token_urlsafe(32)


def body(state=45, ref="#1001", delivery="64f0c0ffee0000000000d001", **more):
    out = {"_id": delivery, "trackingNumber": 48089608, "state": state, "type": "SEND", "timeStamp": 1761700000000,
           "numberOfAttempts": 1, "businessReference": ref}
    out.update(more)
    return out


class Setup(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.results = Results(self.db)
        self.order("chat-1", "#1001")
        self.order("chat-2", "#1002")
        self.told = []
        self.app = bosta.Deliveries(self.results, tell_team=self.told.append)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), bosta.make_handler(SECRET, self.app.accept))
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.port = srv.server_address[1]

    def order(self, chat, name, store="shopify"):
        self.results.record(chat, "order_created", stage="ordering",
                            detail={"order": name, "store": store, "total": 1510, "cod_risk": "low", "reasons": []})

    def post(self, payload, secret=SECRET, path=bosta.PATH, raw=None):
        data = raw if raw is not None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers[bosta.HEADER] = secret
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("POST", path, body=data, headers=headers)
            r = conn.getresponse()
            return r.status, r.read().decode()
        finally:
            conn.close()

    def outcomes(self, chat):
        return [r["outcome"] for r in self.results.for_chat(chat)]

    def headers_only(self, length, secret=SECRET):
        """A POST that declares a body of this length and sends none, so the answer has to come
        without the server reading a body (a server that waits for it times this out)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.putrequest("POST", bosta.PATH)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(length))
            if secret is not None:
                conn.putheader(bosta.HEADER, secret)
            conn.endheaders()
            r = conn.getresponse()
            return r.status, r.read().decode()
        finally:
            conn.close()


class TheResultReachesItsCase(Setup):
    def test_delivered_lands_on_the_chat_that_placed_the_order(self):
        self.assertEqual(self.post(body(45)), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "delivered"])
        self.assertEqual(self.outcomes("chat-2"), ["order_created"])
        row = self.results.for_chat("chat-1")[-1]
        self.assertEqual((row["action"], row["detail"]["order"], row["detail"]["bosta"]), (None, "#1001", "48089608"))

    def test_a_refusal_is_refused(self):
        self.assertEqual(self.post(body(47, exceptionCode=8, exceptionReason="Customer refused")), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(self.told, [])

    def test_a_fulfillment_send_is_a_send(self):
        """Review t261029s finding 2: Bosta's docs list state 45 for Fulfillment Send (FXF_SEND) too."""
        self.assertEqual(self.post(body(45, type="FXF_SEND")), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "delivered"])
        refused = body(47, ref="#1002", delivery="64f0c0ffee0000000000d002", type="FXF_SEND", exceptionCode=8)
        self.assertEqual(self.post(refused), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-2"), ["order_created", "refused"])

    def test_a_reference_without_the_hash_finds_the_order(self):
        self.assertEqual(self.post(body(45, ref="1002")), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-2"), ["order_created", "delivered"])

    def test_the_result_is_recorded_on_the_case_but_never_decides_it(self):
        # an optional result source: the order placed decides the case, delivered or refused after it does not
        from engine import study
        self.post(body(45))
        self.post(body(47, ref="#1002", delivery="64f0c0ffee0000000000d002", exceptionCode=8))
        cases = {c.id: c for c in study._read(self.results.plug, self.results.window(0, 2e12), 2e12)}
        for chat, seen in (("chat-1", "delivered"), ("chat-2", "refused")):
            with self.subTest(chat=chat):
                self.assertEqual((cases[chat].status, cases[chat].deciding), (study.GOOD, "order_created"))
                self.assertIn(seen, [r["result"] for r in cases[chat].rows])


class ReturnedToBusiness(Setup):
    """Mohamed's call 14A (29 Oct): state 46, "Returned to business", is recorded as refused,
    through the same path as a refusal, once per order. These are 46s on the send itself, which
    Bosta's docs do not list but the code still takes; the return leg is ReturnLeg below."""

    def test_a_46_alone_records_refused_once(self):
        self.assertEqual(self.post(body(46)), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        row = self.results.for_chat("chat-1")[-1]
        self.assertEqual((row["detail"]["state"], row["detail"]["order"]), (46, "#1001"))
        self.assertEqual(self.post(body(46, timeStamp=1761700099999)), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(self.told, [])

    def test_a_fulfillment_send_returned_is_refused(self):
        self.assertEqual(self.post(body(46, type="FXF_SEND")), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])

    def test_a_refusal_then_46_is_one_refused_and_no_error(self):
        self.assertEqual(self.post(body(47, exceptionCode=8)), (200, "recorded"))
        self.assertEqual(self.post(body(46, timeStamp=1761700099999)), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(self.results.for_chat("chat-1")[-1]["detail"]["state"], 47)

    def test_a_46_then_a_refusal_is_one_refused(self):
        self.assertEqual(self.post(body(46)), (200, "recorded"))
        self.assertEqual(self.post(body(47, exceptionCode=8)), (409, "already taken"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])

    def test_delivered_then_46_records_nothing_new(self):
        self.assertEqual(self.post(body(45)), (200, "recorded"))
        self.assertEqual(self.post(body(46, timeStamp=1761700099999)), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "delivered"])

    def test_a_46_for_another_order_is_its_own(self):
        """The check is per order: #1002's delivered does not stop #1001's 46."""
        self.assertEqual(self.post(body(45, ref="#1002", delivery="64f0c0ffee0000000000d002")), (200, "recorded"))
        self.assertEqual(self.post(body(46)), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])

    def test_a_46_on_an_exchange_or_a_return_pickup_is_ignored(self):
        """Bosta lists 46 for these too; neither is the order's result."""
        for kind in ("EXCHANGE", "CUSTOMER_RETURN_PICKUP", "SIGN_AND_RETURN", None):
            with self.subTest(kind=kind):
                self.assertEqual(self.post(body(46, type=kind)), (200, "ignored"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])

    def test_a_46_for_an_unknown_order_saves_nothing(self):
        self.assertEqual(self.post(body(46, ref="#9999")), (404, "unknown order"))
        self.assertEqual(self.post(body(46)), (200, "recorded"))

    def test_a_failed_46_write_can_be_sent_again(self):
        with mock.patch.object(bosta, "late", side_effect=RuntimeError("disk full")), \
                self.assertLogs("channels.bosta", "ERROR"):
            self.assertEqual(self.post(body(46))[0], 500)
        self.assertEqual(self.post(body(46)), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])


def returned(ref="#1001", delivery="64f0c0ffee0000000000e001", **more):
    """The send's return leg as it most likely comes: its own delivery, type RTO, state 46,
    the send's businessReference."""
    return body(46, ref=ref, delivery=delivery, type="RTO", trackingNumber=48089699, timeStamp=1761900000000, **more)


class ReturnLeg(Setup):
    """Review t261029x finding 1: a returned send reaches the webhook as its own RTO delivery.
    Its 46 records refused on the order its businessReference names, once per order."""

    def test_a_46_on_the_return_leg_records_refused_once(self):
        self.assertEqual(self.post(returned()), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        row = self.results.for_chat("chat-1")[-1]
        self.assertEqual((row["detail"]["state"], row["detail"]["order"], row["detail"]["bosta"]),
                         (46, "#1001", "48089699"))
        self.assertEqual(self.post(returned()), (200, "already recorded"))
        self.assertEqual(self.post(returned(delivery="64f0c0ffee0000000000e002")), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(self.outcomes("chat-2"), ["order_created"])
        self.assertEqual(self.told, [])

    def test_a_refusal_on_the_send_then_its_return_leg_is_one_refused(self):
        self.assertEqual(self.post(body(47, exceptionCode=8)), (200, "recorded"))
        self.assertEqual(self.post(returned()), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(self.results.for_chat("chat-1")[-1]["detail"]["state"], 47)

    def test_a_return_leg_then_the_sends_refusal_is_one_refused(self):
        """Review t261029x r2 finding 1: a refusal takes its order first, so a 47 with code 8
        after the return leg is a replay, not a second refused."""
        self.assertEqual(self.post(returned()), (200, "recorded"))
        self.assertEqual(self.post(body(47, exceptionCode=8))[0], 409)
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])

    def test_two_failed_attempts_then_the_return_leg_is_refused(self):
        """Review t261029x r2 finding 2: the usual way a return arrives. Attempts are notes and
        never mark the order, so the return leg still records refused."""
        with self.assertLogs("channels.bosta", "WARNING"):
            self.assertEqual(self.post(body(47, exceptionCode=1, numberOfAttempts=1)), (200, "noted"))
            self.assertEqual(self.post(body(47, exceptionCode=1, numberOfAttempts=2, timeStamp=1761786400000)),
                             (200, "noted"))
        self.assertEqual(self.post(returned()), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(len(self.told), 2)

    def test_delivered_then_a_return_leg_records_nothing(self):
        self.assertEqual(self.post(body(45)), (200, "recorded"))
        self.assertEqual(self.post(returned()), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "delivered"])

    def test_a_46_on_the_send_and_on_its_return_leg_is_one_refused(self):
        self.assertEqual(self.post(body(46)), (200, "recorded"))
        self.assertEqual(self.post(returned()), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])
        self.assertEqual(self.post(returned(ref="#1002", delivery="64f0c0ffee0000000000e002")), (200, "recorded"))
        self.assertEqual(self.post(body(46, ref="#1002", delivery="64f0c0ffee0000000000d002")),
                         (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-2"), ["order_created", "refused"])

    def test_one_order_written_two_ways_is_one_order(self):
        self.assertEqual(self.post(body(47, ref="1001", exceptionCode=8)), (200, "recorded"))
        self.assertEqual(self.post(returned(ref="#1001")), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])

    def test_a_return_leg_for_an_unknown_order_saves_nothing(self):
        with self.assertLogs("channels.bosta", "WARNING"):
            self.assertEqual(self.post(returned(ref="#9999")), (404, "unknown order"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])
        self.assertEqual(self.post(returned()), (200, "recorded"))

    def test_only_the_return_legs_46_counts(self):
        for payload in (body(45, type="RTO"), body(47, type="RTO", exceptionCode=8),
                        body(47, type="RTO", exceptionCode=21), body(48, type="RTO")):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload), (200, "ignored"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])
        self.assertEqual(self.told, [])

    def test_a_failed_refusal_write_leaves_the_order_open(self):
        with mock.patch.object(bosta, "late", side_effect=RuntimeError("disk full")), \
                self.assertLogs("channels.bosta", "ERROR"):
            self.assertEqual(self.post(body(47, exceptionCode=8))[0], 500)
        self.assertEqual(self.post(returned()), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])

    def test_a_failed_write_keeps_the_mark_an_earlier_result_made(self):
        """A second send of the same order fails to save; the first send's delivered still
        marks the order, so the return leg adds nothing."""
        self.assertEqual(self.post(body(45)), (200, "recorded"))
        again = body(45, delivery="64f0c0ffee0000000000d003")
        with mock.patch.object(bosta, "late", side_effect=RuntimeError("disk full")), \
                self.assertLogs("channels.bosta", "ERROR"):
            self.assertEqual(self.post(again)[0], 500)
        self.assertEqual(self.post(returned()), (200, "already recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "delivered"])

    def test_a_failed_return_leg_write_can_be_sent_again(self):
        with mock.patch.object(bosta, "late", side_effect=RuntimeError("disk full")), \
                self.assertLogs("channels.bosta", "ERROR"):
            self.assertEqual(self.post(returned())[0], 500)
        self.assertEqual(self.post(returned()), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "refused"])


class AFailedAttempt(Setup):
    def test_is_a_note_for_the_team_not_a_result(self):
        with self.assertLogs("channels.bosta", "WARNING"):
            got = self.post(body(47, exceptionCode=1, numberOfAttempts=2, exceptionReason="Customer not answering"))
        self.assertEqual(got, (200, "noted"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])
        self.assertEqual(len(self.told), 1)
        self.assertIn("#1001", self.told[0])
        self.assertIn("2", self.told[0])
        self.assertIn("Customer not answering", self.told[0])

    def test_the_same_attempt_twice_is_one_note(self):
        b = body(47, exceptionCode=1)
        with self.assertLogs("channels.bosta", "WARNING"):
            self.post(b)
        self.assertEqual(self.post(b)[0], 409)
        self.assertEqual(len(self.told), 1)

    def test_a_team_note_that_fails_is_logged_only(self):
        def down(text):
            raise RuntimeError("WhatsApp is down")

        self.app.tell_team = down
        with self.assertLogs("channels.bosta", "WARNING") as logs:
            self.assertEqual(self.post(body(47, exceptionCode=3)), (200, "noted"))
        self.assertTrue(any("could not tell the team" in line for line in logs.output))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])


class Refused(Setup):
    def test_a_wrong_or_missing_secret_saves_nothing_and_parses_nothing(self):
        for secret in (None, "", SECRET[:-1], SECRET + "x", "Bearer " + SECRET):
            with self.subTest(secret=secret is None and "none" or len(secret)):
                self.assertEqual(self.post(body(45), secret=secret)[0], 403)
                self.assertEqual(self.post(None, secret=secret, raw=b"{not json")[0], 403)
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])

    def test_the_secret_is_compared_in_constant_time(self):
        with mock.patch.object(bosta.hmac, "compare_digest", wraps=hmac.compare_digest) as cmp:
            self.assertTrue(bosta.secret_ok(SECRET, SECRET))
            self.assertFalse(bosta.secret_ok("x" * len(SECRET), SECRET))
        self.assertEqual(cmp.call_count, 2)

    def test_an_unknown_order_saves_nothing(self):
        with self.assertLogs("channels.bosta", "WARNING"):
            self.assertEqual(self.post(body(45, ref="#9999")), (404, "unknown order"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])

    def test_an_order_two_chats_name_is_unknown(self):
        self.order("chat-3", "#1001")
        with self.assertLogs("channels.bosta", "WARNING"):
            self.assertEqual(self.post(body(45))[0], 404)
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])
        self.assertEqual(self.outcomes("chat-3"), ["order_created"])

    def test_a_demo_order_is_not_a_shipped_order(self):
        """Review t261029s finding 1: the demo store's numbers also start at #1001."""
        self.order("chat-3", "#1003", store="demo")
        with self.assertLogs("channels.bosta", "WARNING"):
            self.assertEqual(self.post(body(45, ref="#1003"))[0], 404)
        self.assertEqual(self.outcomes("chat-3"), ["order_created"])
        self.order("chat-4", "#1003")
        self.assertEqual(self.post(body(45, ref="#1003")), (200, "recorded"))
        self.assertEqual(self.outcomes("chat-4"), ["order_created", "delivered"])
        self.assertEqual(self.outcomes("chat-3"), ["order_created"])

    def test_a_replay_saves_nothing_twice(self):
        self.assertEqual(self.post(body(45))[0], 200)
        self.assertEqual(self.post(body(45)), (409, "already taken"))
        self.assertEqual(self.post(body(45, timeStamp=1761700099999))[0], 409)  # one result per delivery
        self.assertEqual(self.outcomes("chat-1"), ["order_created", "delivered"])

    def test_a_failed_write_can_be_sent_again(self):
        with mock.patch.object(bosta, "late", side_effect=RuntimeError("disk full")), \
                self.assertLogs("channels.bosta", "ERROR"):
            self.assertEqual(self.post(body(45))[0], 500)
        self.assertEqual(self.post(body(45)), (200, "recorded"))

    def test_an_unreadable_body_is_400(self):
        for payload in ([body(45)], {"state": 45, "businessReference": "#1001"}, dict(body(45), state="45"),
                        body(45, ref=""), body(45, ref=None), body(45, _id=None), body(45, ref="#" + "1" * 80)):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload)[0], 400)
        self.assertEqual(self.post(None, raw=b"{not json")[0], 400)
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])

    def test_other_states_and_other_kinds_are_ignored(self):
        for payload in (body(24), body(48), body(49), body(100), body(47, exceptionCode=21),
                        body(45, type="RTO"), body(45, type="CUSTOMER_RETURN_PICKUP"), body(45, type=None)):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload), (200, "ignored"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])
        self.assertEqual(self.told, [])

    def test_a_body_over_the_cap_is_413(self):
        """Review t261029s finding 3: the cap holds for a caller with the secret."""
        for length in (bosta.MAX_BODY + 1, 64 * 1024 * 1024):
            with self.subTest(length=length):
                self.assertEqual(self.headers_only(length), (413, "too large"))

    def test_a_negative_length_is_413(self):
        self.assertEqual(self.headers_only(-1), (413, "too large"))

    def test_a_big_body_without_the_secret_is_403_and_never_read(self):
        """Review t261029s finding 3: no byte of the body is read before the secret is checked."""
        for length in (bosta.MAX_BODY, bosta.MAX_BODY + 1, -1):
            for secret in (None, "x" * len(SECRET)):
                with self.subTest(length=length, secret=secret is None and "none" or "wrong"):
                    self.assertEqual(self.headers_only(length, secret=secret), (403, "forbidden"))
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])

    def test_only_its_own_path(self):
        self.assertEqual(self.post(body(45), path="/webhook")[0], 404)
        self.assertEqual(self.outcomes("chat-1"), ["order_created"])


class TheMapping(unittest.TestCase):
    def test_the_reason_reaches_the_team_as_one_line(self):
        """Red team late r1 finding 4: line breaks in the courier's reason never reach the team line."""
        ev = bosta.read_event(body(47, exceptionCode=8, exceptionReason=" Customer\n\nrefused\r\n  at door "))
        self.assertEqual(ev.why, "Customer refused at door")

    def test_bostas_fields_are_read_in_one_place(self):
        ev = bosta.read_event(body(47, exceptionCode=8, exceptionReason="x" * 500))
        self.assertEqual((ev.delivery, ev.tracking, ev.state, ev.kind, ev.order, ev.code, ev.attempts),
                         ("64f0c0ffee0000000000d001", "48089608", 47, "SEND", "#1001", 8, 1))
        self.assertEqual(len(ev.why), bosta.MAX_TEXT)
        self.assertEqual(bosta.outcome(ev), "refused")

    def test_a_bool_is_not_a_state(self):
        self.assertIsNone(bosta.read_event(body(True)))


class Start(unittest.TestCase):
    def test_it_does_not_start_without_a_long_secret(self):
        for value in (None, "short"):
            env = {k: v for k, v in os.environ.items() if k != "BOSTA_WEBHOOK_SECRET"}
            if value is not None:
                env["BOSTA_WEBHOOK_SECRET"] = value
            with mock.patch.dict(os.environ, env, clear=True), mock.patch("kit.env.load", return_value=[]), \
                    mock.patch("logging.basicConfig"), mock.patch("kit.db.Db") as db, \
                    mock.patch.object(bosta, "ThreadingHTTPServer") as server:
                with self.assertRaises(SystemExit) as cm:
                    bosta.main()
            self.assertIn("BOSTA_WEBHOOK_SECRET", str(cm.exception.code))
            db.assert_not_called()
            server.assert_not_called()

    def test_the_handler_refuses_a_short_secret(self):
        with self.assertRaises(ValueError):
            bosta.make_handler("short", lambda p: (200, "ok"))


if __name__ == "__main__":
    unittest.main()
