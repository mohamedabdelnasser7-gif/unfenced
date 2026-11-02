"""A person's late results on the morning page (DECISIONS items 66 and 67): the waiting cases on
both pages with a button per result (/late_mark), and a sheet upload (/late_sheet, multipart, CSV
of case, result). Each write goes through reflection/results.py late(), once a case for its group,
with who and when. The served tests start a page on a free port and stop it in each test."""
import hashlib
import http.client
import threading
import time
import unittest
import urllib.parse

from engine.log import Log
from kit.db import Db
from reflection import PLUG as SALES
from reflection import late as late_mod
from reflection import morning as mo
from reflection import pages
from tests import plugs

NOW = float(int(time.time()))  # the two tab page draws on the real clock
DAY = 86400.0


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.shipper = plugs.load(plugs.SHIPPER, self)
        self.ship = Log(self.db, self.shipper)
        self.sales = Log(self.db, SALES)
        self.m = mo.Morning(self.db, [self.shipper, SALES])

    def parcel(self, case, order=None, at=NOW - DAY, **extra):
        detail = dict({"order": f"#{order}"} if order else {}, **extra)
        self.ship.act(case, "ship", result="shipped", stage="sending", detail=detail or None, at=at)

    def order(self, chat, number, at=NOW - DAY):
        self.sales.act(chat, SALES.result("order_created").after, result="order_created", stage="ordering",
                       detail={"order": f"#{number}", "store": "shopify"}, at=at)

    def view(self):
        return self.m.late_view(NOW)

    def last(self, log, case):
        return log.case(case)[-1]


class Listed(Base):
    def test_waiting_cases_of_both_kinds_and_none_of_the_rest(self):
        self.parcel("p1", 1001, at=NOW - 3 * DAY)
        self.parcel("p2", 1002, at=NOW - 2 * DAY)
        self.parcel("p3", 1003)
        self.ship.result("p3", "delivered", at=NOW - DAY + 5)  # settled: not listed
        self.parcel("p4", 1004, cause=None, history=True)  # imported from the past: never listed
        self.order("chat-1", 2001)  # a Sales order: waits on its second signal
        self.order("chat-2", 2002)
        self.sales.result("chat-2", "refused", at=NOW - DAY + 5)  # has it
        got = [(c["agent"], c["ref"], c["names"], c["second"]) for c in self.view()["cases"]]
        self.assertEqual(got, [("sales", "2001", ["delivered", "refused"], True),
                               ("shipper", "1001", ["delivered", "refused"], False),
                               ("shipper", "1002", ["delivered", "refused"], False)])
        self.assertEqual(self.view()["agents"], ["sales", "shipper"])

    def test_no_raw_case_id_a_made_reference_and_no_shared_one(self):
        self.parcel("+201001234567")  # no order number: a made reference, never the case id
        self.parcel("p2", 7)
        self.parcel("p3", 7)  # two cases share order 7: neither shown
        ref = "c-" + hashlib.sha256("shipper\0+201001234567".encode()).hexdigest()[:10]
        self.assertEqual([c["ref"] for c in self.view()["cases"]], [ref])
        page = pages.Pages(self.m).get("/", {}, "t0ken")
        self.assertNotIn("201001234567", page.replace(ref, ""))
        self.assertIn(ref, page)

    def test_at_most_a_few_an_agent_the_longest_waiting_first_and_no_count(self):
        for n in range(mo.LATE_SHOWN + 3):
            self.parcel(f"p{n}", 100 + n, at=NOW - 10 * DAY + n)
        refs = [c["ref"] for c in self.view()["cases"]]
        self.assertEqual(refs, [str(100 + n) for n in range(mo.LATE_SHOWN)])
        page = pages.Pages(self.m).get("/", {}, "t0ken")
        self.assertEqual(page.count('name="result" value="delivered"'), mo.LATE_SHOWN)
        self.assertNotIn("more", page.split("Waiting for a result")[1].split("Last night")[0])

    def test_both_pages_draw_buttons_and_the_sheet_form_and_a_static_copy_none(self):
        self.parcel("p1", 1001)
        two = pages.Pages(self.m).get("/", {}, "t0ken")
        a3 = mo.render(self.m.view(NOW), token="t0ken")
        for page in (two, a3):
            self.assertIn("Waiting for a result", page)
            self.assertIn('action="/late_mark"', page)
            self.assertIn('name="case" value="1001"', page)
            self.assertIn('name="result" value="refused"', page)
            self.assertIn('action="/late_sheet" enctype="multipart/form-data"', page)
        self.assertIn('name="back" value="/"', two.split('action="/late_sheet"')[1])
        static = mo.render(self.m.view(NOW), token=None)
        self.assertIn("Order 1001", static)
        self.assertNotIn("late_mark", static)
        self.assertNotIn("late_mark", pages.Pages(self.m).get("/", {}, None))

    def test_nothing_waiting_no_part(self):
        self.assertNotIn("Waiting for a result", pages.Pages(self.m).get("/", {}, "t0ken"))
        self.assertIn("Nothing needs you today", pages.Pages(self.m).get("/", {}, "t0ken"))


class Mark(Base):
    def test_a_mark_is_saved_once_with_who_and_when(self):
        self.parcel("p1", 1001)
        said = self.m.late_mark("shipper", "#1001", "delivered", now=NOW)
        self.assertIn("Saved: delivered for order 1001", said)
        row = self.last(self.ship, "p1")
        self.assertEqual((row["result"], row["at"], row["detail"]), ("delivered", NOW, {"from": "page", "by": mo.BY}))
        with self.assertRaises(mo.Refused):  # it waits for nothing now
            self.m.late_mark("shipper", "1001", "refused", now=NOW + 1)
        self.assertEqual(len(self.ship.case("p1")), 2)

    def test_sales_takes_its_second_signal_only(self):
        self.order("chat-1", 2001)
        with self.assertRaises(mo.Refused):
            self.m.late_mark("sales", "2001", "order_created", now=NOW)
        self.m.late_mark("sales", "2001", "refused", now=NOW)
        self.assertEqual(self.last(self.sales, "chat-1")["result"], "refused")

    def test_refusals_change_nothing(self):
        self.parcel("p1", 1001)
        for agent, ref, result in (("shipper", "1001", "lost"), ("shipper", "9999", "delivered"),
                                   ("nobody", "1001", "delivered"), ("shipper", "../1001", "delivered"),
                                   ("shipper", "", "delivered")):
            with self.subTest(agent=agent, ref=ref, result=result):
                with self.assertRaises(mo.Refused):
                    self.m.late_mark(agent, ref, result, now=NOW)
        self.assertEqual(len(self.ship.case("p1")), 1)

    def test_a_webhook_first_wins(self):
        self.parcel("p1", 1001)
        self.m.late_view(NOW)  # the page was drawn
        late_mod.late(self.db, self.shipper, "p1", "refused", by="webhook", now=NOW)
        with self.assertRaises(mo.Refused):
            self.m.late_mark("shipper", "1001", "delivered", now=NOW + 1)
        self.assertEqual(self.last(self.ship, "p1")["result"], "refused")


class Sheet(Base):
    def setUp(self):
        super().setUp()
        for n in (1, 2, 3):
            self.parcel(f"p{n}", 1000 + n)

    def sheet(self, text, **kw):
        return self.m.late_sheet("shipper", text.encode("utf-8") if isinstance(text, str) else text, now=NOW, **kw)

    def test_good_rows_saved_and_the_rest_skipped_by_row_number(self):
        said = self.sheet("case,result\r\n#1001,Delivered\r\n1002,refused\r\n1002,delivered\r\n9999,delivered\r\n"
                          "1003,lost\r\n1003\r\n<script>x</script>,delivered\r\n\r\n")
        self.assertTrue(said.startswith("Sheet, Shipper: 2 saved, 1 had a result already, 4 skipped and not saved"), said)
        for part in ("row 5: order 9999 does not wait for a result now", "row 6: order 1003 takes delivered or refused",
                     "row 7: it needs two columns", "row 8: the case is not one the page names"):
            self.assertIn(part, said)
        self.assertNotIn("script", said)
        self.assertEqual([self.last(self.ship, c)["result"] for c in ("p1", "p2", "p3")],
                         ["delivered", "refused", "shipped"])
        self.assertEqual(self.last(self.ship, "p1")["detail"], {"from": "sheet", "by": mo.BY})

    def test_a_whole_sheet_refused_saves_nothing(self):
        too_many = "\n".join(f"{1000 + (n % 3) + 1},delivered" for n in range(mo.MAX_SHEET_ROWS + 1))
        for data in (too_many, b"\xff\xfe1001,delivered", "", "case,result\n", b"1001,delivered\x00",
                     b"x" * (mo.MAX_SHEET + 1)):
            with self.subTest(data=data[:30]):
                with self.assertRaises(mo.Refused):
                    self.sheet(data)
        self.assertEqual([self.last(self.ship, c)["result"] for c in ("p1", "p2", "p3")], ["shipped"] * 3)

    def test_an_agent_with_no_late_results_takes_no_sheet(self):
        fast = plugs.changed(plugs.WATERER)
        for r in ("grew", "wilted"):
            fast["results"][r] = {"speed": "fast", "after": "water", "about": r}
        m = mo.Morning(self.db, [plugs.load(fast, self)])
        with self.assertRaises(mo.Refused):
            m.late_sheet("waterer", b"1,grew", now=NOW)


def multipart(fields, boundary="b0und4ry"):
    out = b""
    for name, value in fields:
        if isinstance(value, bytes):
            head = f'Content-Disposition: form-data; name="{name}"; filename="s.csv"\r\nContent-Type: text/csv'
        else:
            head, value = f'Content-Disposition: form-data; name="{name}"', value.encode("utf-8")
        out += f"--{boundary}\r\n{head}\r\n\r\n".encode() + value + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class Served(Base):
    """Both pages served on a free port, each stopped at the end of its test."""

    def serve(self, two_tabs):
        server = mo.make_server(self.m, port=0, pages=pages.Pages(self.m) if two_tabs else None)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(5)
        self.addCleanup(stop)
        return server

    def post(self, server, path, body, kind, origin=True, length=None):
        here = f"127.0.0.1:{server.server_address[1]}"
        headers = {"Host": here, "Content-Type": kind}
        if origin:
            headers["Origin"] = f"http://{here}"
        if length is not None:
            headers["Content-Length"] = str(length)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            conn.request("POST", path, body, headers)
            r = conn.getresponse()
            r.read()
            return r.status
        finally:
            conn.close()

    def test_marks_and_sheets_through_both_servers(self):
        self.parcel("p1", 1001)
        self.parcel("p2", 1002)
        for two_tabs, case, sheet_case in ((False, "p1", "p2"),):
            server = self.serve(two_tabs)
            form = urllib.parse.urlencode({"token": server.token, "agent": "shipper", "case": "1001",
                                           "result": "delivered"})
            self.assertEqual(self.post(server, "/late_mark", form, "application/x-www-form-urlencoded"), 303)
            self.assertEqual(self.last(self.ship, case)["result"], "delivered")
            body, kind = multipart([("token", server.token), ("agent", "shipper"), ("sheet", b"1002,refused\r\n")])
            self.assertEqual(self.post(server, "/late_sheet", body, kind), 303)
            self.assertEqual(self.last(self.ship, sheet_case)["result"], "refused")

    def test_the_two_tab_server_takes_them_with_back(self):
        self.parcel("p1", 1001)
        server = self.serve(True)
        body, kind = multipart([("token", server.token), ("back", "/"), ("agent", "shipper"),
                                ("sheet", b"case,result\n1001,delivered\n")])
        self.assertEqual(self.post(server, "/late_sheet", body, kind), 303)
        self.assertEqual(self.last(self.ship, "p1")["result"], "delivered")

    def test_a_sheet_without_the_token_from_elsewhere_too_big_or_malformed_is_refused(self):
        self.parcel("p1", 1001)
        server = self.serve(False)
        good = [("token", server.token), ("agent", "shipper"), ("sheet", b"1001,delivered")]
        cases = [(multipart(good[1:]), True, 403), (multipart([("token", "guess")] + good[1:]), True, 403),
                 (multipart(good), False, 403),
                 (multipart(good + [("token", server.token)]), True, 400),  # a field twice
                 (multipart(good + [("other", "x")]), True, 400),
                 ((b"not multipart", "multipart/form-data; boundary=zz"), True, 400),
                 ((b"token=x", "application/x-www-form-urlencoded"), True, 415),
                 ((b"x", "multipart/form-data"), True, 400)]
        for (body, kind), origin, want in cases:
            with self.subTest(kind=kind, want=want):
                self.assertEqual(self.post(server, "/late_sheet", body, kind, origin=origin), want)
        big, kind = multipart(good)
        self.assertEqual(self.post(server, "/late_sheet", big, kind, length=mo.MAX_SHEET + 1), 413)
        self.assertEqual(self.last(self.ship, "p1")["result"], "shipped")

    def test_a_mark_without_the_token_is_refused(self):
        self.parcel("p1", 1001)
        server = self.serve(False)
        form = urllib.parse.urlencode({"token": "guess", "agent": "shipper", "case": "1001", "result": "delivered"})
        self.assertEqual(self.post(server, "/late_mark", form, "application/x-www-form-urlencoded"), 403)
        self.assertEqual(self.last(self.ship, "p1")["result"], "shipped")


if __name__ == "__main__":
    unittest.main()
