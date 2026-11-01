"""The three sample days (sim/three_days.py) and the demo server over them (reflection/morning.py
--demo-days): the same seed gives the same days, every row is simulated, and the server serves each
day and tab from a throwaway copy. No model call: the night's parts, the judge and the exam are scripted."""
import json
from datetime import datetime
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from kit.db import Db
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
            for f in list(a.glob("*.json")) + list((a / "assistant").glob("*")):
                self.assertEqual(f.read_bytes(), (b / f.relative_to(a)).read_bytes(), f.name)

    def test_refuses_a_folder_with_days(self):
        with self.assertRaises(ValueError):
            three_days.build(self.dir)

    def test_three_working_mornings_in_a_row(self):
        at = [json.loads((self.dir / f"day{d}" / "day.json").read_text(encoding="utf-8"))["at"] for d in (1, 2, 3)]
        self.assertEqual([mo._today(t) for t in at], ["Sun 1 Nov, 09:00 Cairo", "Mon 2 Nov, 09:00 Cairo",
                                                      "Tue 3 Nov, 09:00 Cairo"])
        self.assertEqual([b - a for a, b in zip(at, at[1:])], [mo.DAY, mo.DAY])
        for t in at:  # the Egypt work week: Sunday to Thursday
            self.assertNotIn(datetime.fromtimestamp(t, mo.CAIRO).strftime("%a"), ("Fri", "Sat"))
        with self.assertRaises(ValueError):  # a sample that would cross a weekend is refused
            three_days.mornings("2026-11-04")

    def test_every_row_is_simulated(self):
        for d in (1, 2, 3):
            day = self.dir / f"day{d}"
            meta = json.loads((day / "day.json").read_text(encoding="utf-8"))
            self.assertEqual((meta["day"], meta["simulated"]), (d, True))
            saved = list(day.glob("night-*.json")) + list(day.glob("mode-*.json")) + list(day.glob("arena-*.json"))
            self.assertTrue(saved)
            for f in saved:
                self.assertIs(json.loads(f.read_text(encoding="utf-8")).get("simulated"), True, f.name)
            rows = "\n".join(dump(day / "ascent.db"))
            self.assertIn("sim-sales-", rows)
            self.assertIn("simulated user", rows)

    def views(self):
        with tempfile.TemporaryDirectory() as tmp:  # a copy: opening a Morning writes its tables
            pages, dbs = mo.demo_pages(self.dir, tmp)
            try:
                return {d: m.view(now=pages.at[d]) for d, m in pages.days.items()}, pages
            finally:
                for db in dbs:
                    db.close()

    def test_the_story_of_the_three_days(self):
        views, _ = self.views()
        one, two, three = views[1], views[2], views[3]
        self.assertEqual([c["origin"] for c in one["cards"]], ["agent"])
        mine = [c for c in two["cards"] if c["origin"] == "person"]  # day 2: the correction waits for a yes
        self.assertEqual([(c["risk"], c["state"]) for c in mine], [("high", "waiting")])
        self.assertEqual(mine[0]["text"], json.loads(three_days.SAMPLE.read_text(encoding="utf-8"))["correction"])
        for word in ("team", "whatsapp", "confirm"):  # DECISIONS 53: no hand-off to the team
            self.assertNotIn(word, mine[0]["text"].lower())
        sales = {d: next(a for a in v["agents"] if a["agent"] == "sales") for d, v in views.items()}
        three_items = {i["origin"]: i for i in sales[3]["live"] + sales[3]["waiting"]}
        self.assertEqual(three_items["person"]["state"], mo.TRYING)  # day 3: after the yes it is on trial
        self.assertEqual(three_items["agent"]["state"], mo.WAITING)  # and the lesson waits its turn
        self.assertTrue(three_items["agent"]["queued"])
        self.assertEqual([c for c in three["cards"]], [])
        modes = [next(a for a in v["agents"] if a["agent"] == "assistant")["mode_card"]["name"] for v in
                 (one, two, three)]
        self.assertEqual(modes, ["gym", "lunch", "prayer"])  # a new mode each night, the one before answered

    def test_every_night_shows_the_engine_at_work(self):
        from reflection import pages as pages_mod
        views, _ = self.views()
        said = {}
        for d, v in views.items():
            for a in v["agents"]:
                lines = pages_mod.night_lines(a, v["at"])
                self.assertNotIn("A quiet night. Nothing changed.", lines, (d, a["agent"]))
                self.assertLessEqual(len(lines), 2, (d, a["agent"]))  # LOCKS: one line per agent, two at most
                said[(d, a["agent"])] = lines
        for d in (1, 2, 3):
            self.assertIn("It found a new mode for you", " ".join(said[(d, "assistant")]))
        self.assertRegex(said[(1, "sales")][0], r"^Reflection read \d+ chats and wrote a new lesson\.$")
        self.assertEqual(said[(1, "sales")][1], "It practised with made-up customers in the Arena.")
        self.assertEqual(said[(2, "sales")][0], "Your correction passed the exam and waits for your yes.")
        self.assertRegex(said[(2, "sales")][1], r"^Reflection read \d+ chats\.$")
        self.assertRegex(said[(3, "sales")][0], r"^Your correction ran in \d+ chats, no harm seen\.$")
        self.assertRegex(said[(3, "sales")][1], r"^Reflection read \d+ chats")
        said = {k: " ".join(v) for k, v in said.items()}
        for text in said.values():
            for bad in ("sim-sales-", "—", "–", "held-out"):
                self.assertNotIn(bad, text)

    def test_a_practice_run_is_saved_each_night(self):
        views, pages = self.views()
        for d, v in views.items():
            arena = next(a for a in v["agents"] if a["agent"] == "sales")["arena"]
            self.assertEqual(pages.at[d] - arena["at"], 7 * 3600)  # the night before the morning, 02:00 Cairo
            self.assertTrue(arena["lost"])
            for x in arena["lost"]:
                self.assertTrue(x["card"].startswith("persona-"))  # the made-up cards (demo/personas)
                self.assertTrue(x["text"])


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
        self.assertIn("Waits for your yes on Today", self.fetch("/agents/sales?day=2")[1])
        three = self.fetch("/agents/sales?day=3")[1]
        self.assertIn("Hotfix", three)
        self.assertIn("Reflection checked it last night: it ran in", three)
        self.assertNotIn("Reflection checks it tonight", three)
        self.assertNotIn("held-out", three)  # the Arena note in plain words, no matches won
        self.assertIn("See where it slipped", three)
        self.assertNotIn("day=live", self.fetch("/?day=1")[1])  # no --db, no Live tab
        for d in (1, 2, 3):
            today = self.fetch(f"/?day={d}")[1]
            self.assertNotIn("A quiet night", today)
            self.assertIn("Reflection read ", today)

    def test_the_agent_list_shows_on_each_day(self):
        for d in (1, 2, 3):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/agents?day={d}", timeout=10) as r:
                self.assertEqual((r.status, r.url), (200, f"http://127.0.0.1:{self.port}/agents?day={d}"))  # no redirect
                page = r.read().decode("utf-8")
            self.assertIn(f'href="/new?day={d}">', page)
            self.assertIn("New agent</a>", page)
            for agent in ("sales", "assistant"):
                self.assertIn(f'<a class="agl" href="/agents/{agent}?day={d}">', page)
            self.assertIn("<h1>Agents</h1>", page)

    def test_practice_matches_on_screen_two(self):
        for d in (1, 2, 3):
            page = self.fetch(f"/new/build?agent=sales&day={d}")[1]
            self.assertIn("Nothing to do here", page)
            self.assertIn('class="climb"', page)
            self.assertIn('class="tile lost"', page)
            self.assertNotIn("No saved practice run yet", page)
            for bad in ("persona-", "held-out", " won", " of 5"):  # no card id, no won and lost total
                self.assertNotIn(bad, page)

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

class LiveTab(unittest.TestCase):
    """--demo-days with --db: Day 1, Day 2, Day 3, then Live on the real database (here a temp one),
    with real answers and no Sample data label; the sample copies never change."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        three_days.build(root / "days")
        live_path = root / "live" / "ascent.db"
        live_path.parent.mkdir()
        cls.live_db = Db(str(live_path))
        live = mo.live_morning(cls.live_db, str(live_path), mo.repo_plugs(), root / "live" / "assistant")
        live.exams = {"sales": three_days.examiner}  # main() gives the live page its exam (page_exams)
        cls.pages, cls.dbs = mo.demo_pages(root / "days", root / "served", live=live)
        cls.server = mo.make_server(cls.pages.morning, port=0, pages=cls.pages)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)
        for db in cls.dbs:
            db.close()
        cls.live_db.close()
        cls.tmp.cleanup()

    def fetch(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.read().decode("utf-8")

    def test_the_switch_ends_with_live(self):
        one = self.fetch("/agents?day=1")
        self.assertIn('href="/agents?day=3">Day 3</a><a class="" href="/agents?day=live">Live</a>', one)
        self.assertIn("Sample data", one)
        for path in PATHS:
            page = self.fetch(f"{path}?day=live")
            self.assertIn(f'class="on" href="{path}?day=live">Live<', page)
            self.assertNotIn("Sample data", page)
        self.assertIn("Nothing needs you today", self.fetch("/?day=live"))
        self.assertIn('href="/new?day=live">', self.fetch("/agents?day=live"))

    def test_a_live_answer_goes_to_the_live_database_only(self):
        sample = (self.root / "days" / "day1" / "ascent.db").read_bytes()
        page = self.fetch("/agents/sales?day=live")
        token = page.split('name="token" value="')[1].split('"')[0]
        body = urllib.parse.urlencode({"token": token, "back": "/agents/sales?day=live", "agent": "sales",
                                       "line": "Ask which colour they like before you send the summary."}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/correct", data=body, method="POST", headers={
            "Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertTrue(r.url.endswith("/agents/sales?day=live"))
            self.assertIn("Ask which colour they like", r.read().decode("utf-8"))
        texts = [i["text"] for a in self.pages.live.view()["agents"] for i in a["live"] + a["waiting"]]
        self.assertIn("Ask which colour they like before you send the summary.", texts)
        held = self.pages.live.lessons["sales"].mine()[-1]  # the page's judge is not sure, so it waits for a yes
        self.assertEqual(held["state"], "waiting")
        self.pages.live.no(held["id"], "a test")  # Live's Today is empty again for the other tests
        one = self.pages.days[1].view(now=self.pages.at[1])
        self.assertNotIn("Ask which colour", json.dumps(one))
        self.assertEqual((self.root / "days" / "day1" / "ascent.db").read_bytes(), sample)

    def test_without_days_there_is_no_switch(self):
        from reflection import pages as pages_mod
        p = pages_mod.Pages(self.pages.live, live=self.pages.live)
        self.assertIsNone(p.live)
        self.assertNotIn("day=live", p.get("/", {}, "t"))


if __name__ == "__main__":
    unittest.main()
