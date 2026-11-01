"""The three sample days (sim/three_days.py) and the demo server over them (reflection/morning.py
--demo-days): the same seed gives the same days, every row is simulated, and the server serves each
day and tab from a throwaway copy. No model call: the night's parts, the judge and the exam are scripted."""
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from reflection import morning as mo
from sim import three_days

PATHS = ("/", "/agents", "/agents/sales", "/agents/assistant", "/new", "/new/build")


def dump(path):
    conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)  # reads only, leaves no -wal or -shm
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


class ThreeDays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name) / "days"
        three_days.build(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_same_seed_same_days(self):
        other = Path(self.tmp.name) / "again"
        three_days.build(other)
        for d in (1, 2, 3):
            a, b = self.dir / f"day{d}", other / f"day{d}"
            self.assertEqual(sorted(p.name for p in a.iterdir()), sorted(p.name for p in b.iterdir()))
            self.assertEqual(dump(a / "ascent.db"), dump(b / "ascent.db"))
            for f in a.glob("*.json"):
                self.assertEqual(f.read_bytes(), (b / f.name).read_bytes(), f.name)

    def test_refuses_a_folder_with_days(self):
        with self.assertRaises(ValueError):
            three_days.build(self.dir)

    def test_every_row_is_simulated(self):
        for d in (1, 2, 3):
            day = self.dir / f"day{d}"
            meta = json.loads((day / "day.json").read_text(encoding="utf-8"))
            self.assertEqual((meta["day"], meta["simulated"]), (d, True))
            for f in list(day.glob("night-*.json")) + list(day.glob("mode-*.json")):
                self.assertIs(json.loads(f.read_text(encoding="utf-8")).get("simulated"), True, f.name)
            rows = "\n".join(dump(day / "ascent.db"))
            self.assertIn("sim-sales-", rows)
            self.assertIn("simulated user", rows)

    def test_the_story_of_the_three_days(self):
        with tempfile.TemporaryDirectory() as tmp:  # a copy: opening a Morning writes its tables
            pages, dbs = mo.demo_pages(self.dir, tmp)
            try:
                views = {d: m.view(now=pages.at[d]) for d, m in pages.days.items()}
            finally:
                for db in dbs:
                    db.close()
        one, two, three = views[1], views[2], views[3]
        self.assertEqual([c["origin"] for c in one["cards"]], ["agent"])
        self.assertEqual([(c["origin"], c["risk"]) for c in two["cards"]], [("person", "high")])
        self.assertEqual(three["cards"], [])
        sales = {d: next(a for a in v["agents"] if a["agent"] == "sales") for d, v in views.items()}
        self.assertEqual([i["state"] for i in sales[3]["live"]], ["kept", "trying"])
        for v in views.values():  # the mode card waits all three days
            self.assertIsNotNone(next(a for a in v["agents"] if a["agent"] == "assistant")["mode_card"])


class DemoServer(unittest.TestCase):
    """End to end: the demo server on a free port, each day and tab fetched, one answer, stopped."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        src = Path(cls.tmp.name) / "days"
        three_days.build(src)
        cls.pages, cls.dbs = mo.demo_pages(src, Path(cls.tmp.name) / "served")
        cls.server = mo.make_server(cls.pages.morning, port=0, pages=cls.pages)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.src = src

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)
        for db in cls.dbs:
            db.close()
        cls.tmp.cleanup()

    def fetch(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_each_day_and_tab(self):
        for d in (1, 2, 3):
            for path in PATHS:
                status, page = self.fetch(f"{path}?day={d}")
                self.assertEqual(status, 200, (d, path))
                self.assertIn("Sample data", page)
                self.assertIn(f'class="on" href="{path}?day={d}">Day {d}<', page)
                for bad in ("—", "–", "sim-sales-"):
                    self.assertNotIn(bad, page, (d, path))
        self.assertIn("Before you send the summary", self.fetch("/?day=1")[1])
        two = self.fetch("/?day=2")[1]
        self.assertIn("Your correction", two)
        self.assertIn("It waits for your yes because", two)
        self.assertNotIn("on the number list", two)
        self.assertIn("Hotfix", self.fetch("/agents/sales?day=3")[1])
        self.assertIn("Nothing to do here", self.fetch("/new/build?agent=sales&day=1")[1])

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.fetch("/nowhere?day=1")
        self.assertEqual(e.exception.code, 404)
        e.exception.close()

    def test_an_answer_changes_the_copy_only(self):
        before = (self.src / "day3" / "ascent.db").read_bytes()
        cards = {f.name: f.read_bytes() for f in (self.src / "day3").glob("mode-*.json")}
        page = self.fetch("/?day=3")[1]
        token = page.split('name="token" value="')[1].split('"')[0]
        card = page.split('action="/mode"')[1].split('name="card" value="')[1].split('"')[0]
        body = urllib.parse.urlencode({"token": token, "back": "/?day=3", "agent": "assistant", "card": card,
                                       "choice": "drop"}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/mode", data=body, method="POST", headers={
            "Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:  # the redirect lands back on day 3
            after = r.read().decode("utf-8")
        self.assertIn('class="flash"', after)
        self.assertIn("Nothing needs you today", after)
        self.assertEqual((self.src / "day3" / "ascent.db").read_bytes(), before)
        self.assertEqual({f.name: f.read_bytes() for f in (self.src / "day3").glob("mode-*.json")}, cards)
        self.assertIn("A new mode", self.fetch("/?day=1")[1])  # another day's copy is its own

if __name__ == "__main__":
    unittest.main()
