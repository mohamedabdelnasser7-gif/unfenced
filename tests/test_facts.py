"""Call 10, fact cards on the morning page (reflection/facts.py): the Sales agent's usual delivery
days this week against last week, by zone, worked out from made-up results in an in-memory
log; the too few rule; Keep and Dismiss through the page's own server, saved with who and
when; and nothing acting on a fact. The chats, orders and zones are made up. No model, no
network beyond 127.0.0.1."""
import http.client
import re
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

from kit.db import Db
from kit.tools import delivery
from reflection import PLUG as SALES
from reflection import facts as facts_mod
from reflection import morning as mod
from reflection.results import Results
from tests import plugs

DAY = 86400
WEEK = 7 * DAY
NOW = 1_800_000_000.0  # 15 Jan 2027 08:00 UTC
CAIRO, OTHER = "Cairo and Giza", "Other governorates"
OWNER = mod.BY
ROOT = Path(__file__).resolve().parent.parent


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.results = Results(self.db)
        self.morning = mod.Morning(self.db, [SALES], reports=self.dir)
        self.facts = self.morning.facts
        self.n = 1000
        self.t = NOW

    def order(self, days, delivered_at, *, zone=CAIRO, history=(), ref=None, number=True):
        """One made-up chat with an order and its delivered row `days` later. history: which rows
        are marked imported ("order", "delivered"). ref: the order number on the delivered row,
        as Bosta may give it (no # by default)."""
        self.n += 1
        chat = f"test-chat-{self.n}"
        placed = {"store": "shopify", "total": 1510, "cod_risk": "low", "reasons": []}
        if number:
            placed["order"] = f"#{self.n}"
        if zone is not None:
            placed["area"] = zone
        got = {"bosta": f"T{self.n}", "state": 45, "code": None, "at": None}
        if number:
            got["order"] = str(self.n) if ref is None else ref
        if "order" in history:
            placed["history"] = True
        if "delivered" in history:
            got["history"] = True
        self.results.act(chat, "order", result="order_created", detail=placed, at=delivered_at - days * DAY)
        self.results.result(chat, "delivered", detail=got, at=delivered_at)
        return chat

    def week(self, days, *, ago=0, **kw):
        """Deliveries that came in this week (ago 0) or last week (ago 1), an hour apart."""
        for i, d in enumerate(days):
            self.order(d, self.t - ago * WEEK - (i + 1) * 3600, **kw)

    def two_weeks(self, this=(3, 3, 3, 3, 3.5), last=(2, 2, 2, 2, 1), **kw):
        self.week(this, **kw)
        self.week(last, ago=1, **kw)

    def cards(self, now=None):
        return self.morning.view(self.t if now is None else now)["facts"]


class Cards(Base):
    def test_a_card_from_fake_results_with_the_numbers_behind_it(self):
        self.two_weeks()
        [card] = self.cards()
        self.assertEqual(card["fact"], "Orders to Cairo and Giza usually took 3 days to arrive this week, against "
                                       "2 days last week.")
        self.assertEqual((card["this"], card["last"], card["told"]),
                         ({"orders": 5, "usual": 3, "fastest": 3, "slowest": 3.5},
                          {"orders": 5, "usual": 2, "fastest": 1, "slowest": 2}, "1 to 2 days"))
        page = mod.render(self.morning.view(NOW), token="t0ken")
        self.assertIn("Facts from the results: keep or dismiss", page)
        self.assertIn("This week, the 7 days to Fri 15 Jan 2027, 10:00 Cairo: 5 orders delivered, usually 3 days from the "
                      "order, the fastest 3, the slowest 3.5. Last week: 5 orders, usually 2 days, the fastest 1, the "
                      "slowest 2. The delivery data tells customers 1 to 2 days for this zone.", page)
        self.assertIn('action="/keep_fact"', page)
        self.assertIn('action="/dismiss_fact"', page)
        static = mod.render(self.morning.view(NOW), token=None)
        self.assertIn(card["fact"], static)
        self.assertNotIn("<form", static)

    def test_too_few_results_in_either_week_make_no_card(self):
        self.two_weeks(this=(3, 3, 3, 3), zone=CAIRO)
        self.two_weeks(last=(2, 2, 2, 2), zone=OTHER)
        self.assertEqual(self.cards(), [])
        self.assertIn("No fact cards now: too few results", mod.render(self.morning.view(NOW), token="t0ken"))
        self.week([3], zone=CAIRO)
        self.assertEqual([c["key"] for c in self.cards()], [CAIRO])

    def test_each_zone_is_its_own_card_and_orders_with_no_zone_saved_are_one(self):
        self.two_weeks(zone=CAIRO)
        self.two_weeks(this=(5, 5, 6, 6, 6), last=(4, 4, 4, 4, 4), zone=OTHER)
        self.two_weeks(this=(1, 1, 1, 1, 1), last=(1, 1, 1, 1, 1), zone=None)
        self.two_weeks(this=(2, 2, 2, 2, 2), last=(2, 2, 2, 2, 2), zone="x" * 81)  # too long: read as not saved
        got = {c["key"]: c for c in self.cards()}
        self.assertEqual(sorted(got), ["", CAIRO, OTHER])
        self.assertEqual((got[OTHER]["this"]["usual"], got[OTHER]["told"]), (6, "2 to 4 days"))
        self.assertEqual(got[""]["fact"], "Orders whose zone was not saved usually took 1.5 days to arrive this week, "
                                          "against 1.5 days last week.")
        self.assertEqual((got[""]["this"]["orders"], got[""]["told"]), (10, None))

    def test_rows_imported_from_the_past_are_left_out(self):
        for which in (("order",), ("delivered",), ("order", "delivered")):
            with self.subTest(which=which):
                self.setUp()
                self.week([3, 3, 3, 3, 3], history=which)
                self.week([2, 2, 2, 2, 2], ago=1)
                self.assertEqual(self.cards(), [])
                self.week([4, 4, 4, 4, 4])
                [card] = self.cards()
                self.assertEqual(card["this"], {"orders": 5, "usual": 4, "fastest": 4, "slowest": 4})

    def test_a_delivery_counts_only_with_its_own_order_placed_before_it(self):
        self.two_weeks()
        self.order(9, self.t - 3600, ref="#9999")       # names an order its chat never placed
        self.order(-1, self.t - 3600)                   # its order came after the delivered row
        self.order(9, self.t - 3600, number=False)      # no order number on either row
        self.order(3, self.t - 3600, ref="#" + str(self.n + 1))  # the # does not matter
        [card] = self.cards()
        self.assertEqual(card["this"]["orders"], 6)
        self.assertEqual(card["this"]["slowest"], 3.5)

    def test_only_the_last_two_weeks_count_and_the_usual_is_the_median(self):
        self.two_weeks(this=(1, 1, 2, 9, 9))
        self.week([30, 30, 30, 30, 30], ago=2)          # older than two weeks
        self.order(30, self.t + 3600)                   # after now
        [card] = self.cards()
        self.assertEqual((card["this"]["usual"], card["last"]["orders"]), (2, 5))

    def test_every_field_of_a_fact_is_escaped(self):
        self.two_weeks(zone="<b>Zone</b>")
        page = mod.render(self.morning.view(NOW), token="t0ken")
        self.assertNotIn("<b>Zone", page)
        self.assertIn("Orders to &lt;b&gt;Zone&lt;/b&gt; usually took", page)
        self.assertIn('name="key" value="&lt;b&gt;Zone&lt;/b&gt;"', page)

    def test_an_agent_with_no_fact_has_no_cards_and_no_section(self):
        plug = plugs.load(plugs.WATERER, self)
        page = mod.Morning(self.db, [plug], reports=self.dir)
        self.assertEqual(page.view(NOW)["facts"], [])
        self.assertNotIn("Facts from the results", mod.render(page.view(NOW), token="t0ken"))
        self.assertEqual(self.facts.cards("waterer", NOW), [])
        with self.assertRaises(mod.Refused):
            page.keep_fact("waterer", "", "x", now=NOW)
        with self.assertRaises(mod.Refused):
            self.morning.keep_fact("nobody", CAIRO, "x", now=NOW)
        self.two_weeks()  # the Sales agent has results here, but this page has no Sales agent plug
        with self.assertRaises(mod.Refused):
            page.keep_fact("sales", CAIRO, self.cards()[0]["shown"], now=NOW)
        self.assertEqual(self.facts.answers("sales"), [])


class Answers(Base):
    def shown(self, now=None):
        [card] = self.cards(now)
        return card["shown"]

    def test_keep_and_dismiss_are_saved_with_who_and_when(self):
        self.two_weeks(zone=CAIRO)
        self.two_weeks(zone=OTHER)
        cards = {c["key"]: c for c in self.cards()}
        self.assertIn("Kept: Orders to Cairo and Giza", self.morning.keep_fact("sales", CAIRO, cards[CAIRO]["shown"],
                                                                                now=NOW + 1))
        self.morning.dismiss_fact("sales", OTHER, cards[OTHER]["shown"], now=NOW + 2)
        rows = self.facts.answers("sales")
        self.assertEqual([(r["key"], r["answer"], r["by"], r["at"]) for r in rows],
                         [(CAIRO, "keep", OWNER, NOW + 1), (OTHER, "dismiss", OWNER, NOW + 2)])
        self.assertEqual(rows[0]["fact"], cards[CAIRO]["fact"])
        self.assertEqual(rows[0]["numbers"]["this"], cards[CAIRO]["this"])
        self.assertEqual([r["key"] for r in self.facts.kept("sales")], [CAIRO])
        self.assertEqual(self.cards(NOW + 3), [])  # both answered, so neither shows again this week
        page = mod.render(self.morning.view(NOW + 3), token="t0ken")
        self.assertIn(f"sales, kept by {OWNER} on Fri 15 Jan 2027, 10:00 Cairo</span>", page)
        self.assertIn(cards[CAIRO]["fact"], page)
        self.assertNotIn(cards[OTHER]["fact"], page)

    def test_a_fact_that_changed_after_the_page_was_drawn_saves_nothing(self):
        self.two_weeks()
        shown = self.shown()
        self.week([9])
        with self.assertRaisesRegex(mod.Refused, "changed after the page was drawn"):
            self.morning.keep_fact("sales", CAIRO, shown, now=NOW)
        with self.assertRaisesRegex(mod.Refused, "not there now"):
            self.morning.keep_fact("sales", OTHER, shown, now=NOW)
        self.assertEqual(self.facts.answers("sales"), [])

    def test_a_fact_is_answered_once_a_week_and_comes_back_after(self):
        self.two_weeks()
        shown = self.shown()
        self.morning.keep_fact("sales", CAIRO, shown, now=NOW)
        with self.assertRaisesRegex(mod.Refused, "not there now"):
            self.morning.dismiss_fact("sales", CAIRO, shown, now=NOW + 1)
        [card] = facts_mod.delivery_days(self.db.conn, "sales", NOW + 1)
        with self.assertRaisesRegex(ValueError, "answered in the last 7 days"):
            self.facts.answer(card, facts_mod.DISMISS, OWNER, now=NOW + 1)
        for i in range(5):  # deliveries in the week after
            self.order(4, NOW + (i + 1) * DAY)
        self.assertEqual(self.cards(NOW + 6 * DAY), [])          # still inside the week of the answer
        later = NOW + WEEK + 7200
        self.assertEqual([c["key"] for c in self.cards(later)], [CAIRO])
        self.morning.dismiss_fact("sales", CAIRO, self.shown(later), now=later)
        self.assertEqual(self.facts.kept("sales"), [])       # the later Dismiss takes the Keep back
        self.assertEqual(len(self.facts.answers("sales")), 2)

    def test_an_answer_row_is_never_changed_deleted_or_replaced(self):
        self.two_weeks()
        self.morning.keep_fact("sales", CAIRO, self.shown(), now=NOW)
        [row] = self.facts.answers("sales")
        for sql in ("UPDATE fact_answers SET answer = 'dismiss'", "DELETE FROM fact_answers",
                    f"INSERT OR REPLACE INTO fact_answers (id, agent, kind, key, fact, numbers, answer, by, at) "
                    f"VALUES ({row['id']}, 'sales', 'delivery_days', '', 'x', '{{}}', 'keep', 'x', 1)"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                with self.db.tx() as c:
                    c.execute(sql)
        self.assertEqual(self.facts.answers("sales"), [row])
        for answer, by in (("maybe", "x"), ("keep", "  ")):
            with self.subTest(answer=answer, by=by), self.assertRaises(sqlite3.IntegrityError):
                with self.db.tx() as c:
                    c.execute("INSERT INTO fact_answers (agent, kind, key, fact, numbers, answer, by, at) "
                              "VALUES ('sales', 'delivery_days', 'k', 'x', '{}', ?, ?, 1)", (answer, by))
        [card] = facts_mod.delivery_days(self.db.conn, "sales", NOW)
        for answer, by in (("maybe", OWNER), (facts_mod.KEEP, ""), (facts_mod.KEEP, "two\nlines")):
            with self.subTest(answer=answer, by=by), self.assertRaises(ValueError):
                self.facts.answer(dict(card, key="other"), answer, by, now=NOW)


class NothingActs(Base):
    def test_nothing_acts_on_a_dismissed_or_unkept_fact(self):
        before = delivery.quote("Giza")
        self.two_weeks()
        self.assertEqual(self.facts.kept("sales"), [])       # a card no one answered is not kept
        self.morning.dismiss_fact("sales", CAIRO, self.cards()[0]["shown"], now=NOW)
        self.assertEqual(self.facts.kept("sales"), [])       # nor a dismissed one
        self.assertEqual(delivery.quote("Giza"), before)         # the delivery tool reads no fact at all

    def test_no_agent_code_reads_a_fact(self):
        """Only the morning page reads reflection/facts.py; no tool, channel, loop or engine part does."""
        readers = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", "reflection/facts.py")):
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bfacts\b", text) and re.search(r"import\s+facts|reflection\.facts|from\s+reflection\.facts",
                                                         text):
                readers.append(rel)
        self.assertEqual(readers, ["reflection/morning.py"])
        tables = sorted(path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*.py")
                        if "fact_answers" in path.read_text(encoding="utf-8"))
        self.assertEqual([p for p in tables if not p.startswith("tests/")], ["reflection/facts.py", "reflection/morning.py"])


class Served(Base):
    """Keep and Dismiss through the page's own server, at the clock's time."""

    def setUp(self):
        super().setUp()
        self.t = time.time()
        self.server = mod.make_server(self.morning, port=0)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(5)
        self.addCleanup(stop)
        self.here = f"127.0.0.1:{self.port}"

    def call(self, method, path, fields=None, *, origin=True):
        headers = {"Host": self.here}
        body = None
        if fields is not None:
            body = urllib.parse.urlencode(fields)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if origin:
            headers["Origin"] = f"http://{self.here}"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read().decode("utf-8")
        finally:
            conn.close()

    def test_keep_from_the_page_is_saved_and_shown_and_dismiss_is_not_kept(self):
        self.two_weeks(zone=CAIRO)
        self.two_weeks(zone=OTHER)
        page = self.call("GET", "/", origin=False)[1]
        found = dict(re.findall(r'name="key" value="([^"]*)"><input type="hidden" name="shown" value="([0-9a-f]+)">'
                                r'<button type="submit">Keep', page))
        self.assertEqual(sorted(found), [CAIRO, OTHER])
        status, _ = self.call("POST", "/keep_fact", {"token": "wrong", "agent": "sales", "key": CAIRO,
                                                     "shown": found[CAIRO]})
        self.assertEqual(status, 403)
        self.assertEqual(self.facts.answers("sales"), [])
        for path, key in (("/keep_fact", CAIRO), ("/dismiss_fact", OTHER)):
            status, _ = self.call("POST", path, {"token": self.server.token, "agent": "sales", "key": key,
                                                 "shown": found[key]})
            self.assertEqual(status, 303)
        rows = self.facts.answers("sales")
        self.assertEqual([(r["key"], r["answer"], r["by"]) for r in rows], [(CAIRO, "keep", OWNER), (OTHER, "dismiss", OWNER)])
        self.assertTrue(all(self.t <= r["at"] <= time.time() for r in rows))
        page = self.call("GET", "/", origin=False)[1]
        self.assertIn("<h3>Kept facts</h3>", page)
        self.assertIn(f"kept by {OWNER} on {mod._when(rows[0]['at'])}", page)
        self.assertNotIn('action="/keep_fact"', page)
        self.assertEqual([r["key"] for r in self.facts.kept("sales")], [CAIRO])


if __name__ == "__main__":
    unittest.main()
