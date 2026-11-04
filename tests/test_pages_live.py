"""The two tab page on a live database where an agent answers real chats and no night has run yet
(root's check at 390, 2026-11-01): Today lists the agents the Agents tab lists, an agent with real
chats says it answered chats today, Live only while the user has it connected on a channel (DECISIONS
item 77: real chats are history, never the switch), and the day switch with the Sample chip keeps every
label on one line. Temp databases only, no model call."""
import json
import re
import tempfile
import time
import unittest
from pathlib import Path

from engine import log as log_mod
from kit import connections
from kit.chats import Chats
from kit.db import Db
from reflection import morning as mo
from reflection import pages

ROOT = Path(__file__).resolve().parent.parent


class LiveDatabase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Db(str(Path(tmp.name) / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, mo.repo_plugs(ROOT))
        self.p = pages.Pages(self.m)

    def chat(self, channel="whatsapp", customer="201000000123"):
        chats = Chats(self.db)
        cid = chats.open(channel, customer)
        chats.add_step(cid, "user", content="عايز اعرف المقاسات")
        chats.add_step(cid, "assistant", content="أهلا بيك")
        return cid

    def trace(self, agent, detail=None):
        self.db.script(log_mod.SCHEMA)
        with self.db.tx() as c:
            c.execute("INSERT INTO trace (agent, case_id, action, detail, at) VALUES (?, ?, ?, ?, ?)",
                      (agent, "c1", "reply", None if detail is None else json.dumps(detail), time.time()))

    def connect(self):
        connections.connect(self.db, "sales", "whatsapp", why="The gate passed.", by=mo.BY)

    def status(self, page, agent):
        return re.search(rf'<b>{re.escape(pages.name(agent))}</b><span class="st(?: live)?">([\w ]+)</span>', page).group(1)

    def last_night(self):
        return self.p.get("/", {}, "t").split('aria-label="Last night"')[1]

    # 2. Today lists the agents the Agents tab lists

    def test_today_lists_every_agent_the_agents_tab_lists(self):
        self.chat()
        today, tab = self.last_night(), self.p.get("/agents", {}, "t")
        self.assertNotIn("No agents yet", today)
        for agent in self.m.plugs:
            self.assertIn(f'href="/agents/{agent}"', tab)
            self.assertIn(f"<b>{pages.name(agent)} <span", today)

    def test_real_chats_and_no_night_say_answered_today_with_no_count(self):
        self.chat()
        self.chat(customer="201000000124")
        today = self.last_night()
        sales = today.split(f"<b>{pages.name('sales')} <span")[1].split('<div class="nl">')[0]
        self.assertIn(pages.ANSWERED, sales)
        self.assertNotIn("A quiet night", sales)
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", sales), r"\d")  # no count, of chats or of what is left
        other = today.split(f"<b>{pages.name('marketing')} <span")[1].split('<div class="nl">')[0]
        self.assertIn("No night yet.", other)
        self.assertNotIn(pages.ANSWERED, other)

    def test_history_chats_are_not_answered_today(self):
        self.chat(channel="history:whatsapp")
        self.assertEqual(self.m.answered_since("sales", 0), 0)
        self.assertNotIn(pages.ANSWERED, self.last_night())

    def test_chats_before_the_night_are_not_answered_today(self):
        self.chat()
        self.assertEqual(self.m.answered_since("sales", time.time() + 60), 0)
        self.assertEqual(self.m.answered_since("sales", 0), 1)
        self.assertEqual(self.m.answered_since("marketing", 0), 0)  # the chats store is the Sales agent's

    def test_an_empty_database_still_lists_the_plugs(self):
        today = self.last_night()
        self.assertNotIn("No agents yet", today)
        self.assertEqual(today.count("No night yet."), len(self.m.plugs))

    # 3. Live while connected on a channel; real chats alone stay In practice

    def test_connected_shows_live_on_both_tabs_and_the_agent_page(self):
        self.chat()
        self.assertEqual(self.status(self.p.get("/agents", {}, "t"), "sales"), "In practice")  # chats are history
        self.assertIn('aria-label="Status: In practice"', self.p.get("/agents/sales", {}, "t"))
        self.connect()
        self.assertEqual(self.status(self.p.get("/agents", {}, "t"), "sales"), "Live")
        self.assertIn(f'<b>{pages.name("sales")} <span class="st live">Live</span>', self.last_night())
        page = self.p.get("/agents/sales", {}, "t")
        self.assertIn('aria-label="Status: Live"', page)
        self.assertIn("Working on real cases", page)
        self.assertEqual(self.status(self.p.get("/agents", {}, "t"), "marketing"), "In practice")

    def test_no_chats_or_history_chats_only_stay_training(self):
        self.assertEqual(self.status(self.p.get("/agents", {}, "t"), "sales"), "In practice")
        self.chat(channel="history:whatsapp")
        self.trace("sales", {"history": True, "import_key": "k1"})
        self.assertEqual(self.m._live(), set())
        self.assertIn("Practising in the Arena", self.p.get("/agents/sales", {}, "t"))

    def test_a_real_log_row_is_history_not_live(self):
        self.trace("marketing")
        self.trace("sales", {"history": False})
        self.assertEqual(self.m._live(), set())
        self.assertEqual(self.m._worked(), {"marketing", "sales"})
        self.connect()
        self.assertEqual(self.m._live(), {"sales"})

    def test_live_tab_next_to_sample_days(self):
        self.chat()
        self.connect()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        day = Db(str(Path(tmp.name) / "day1.db"))
        self.addCleanup(day.close)
        p = pages.Pages(days={1: mo.Morning(day, mo.repo_plugs(ROOT))}, live=self.m)
        live = p.get("/", {"day": ["live"]}, "t")
        self.assertIn(pages.ANSWERED, live)
        self.assertIn('<span class="st live">Live</span>', live)
        self.assertNotIn("No agents yet", live)
        sample = p.get("/", {"day": ["1"]}, "t")
        self.assertNotIn(pages.ANSWERED, sample)  # the sample copy has no chats


# 1. Every label on one line at 390

class OneLineAt390(unittest.TestCase):
    def setUp(self):
        days = {}
        for d in (1, 2, 3):
            db = Db(":memory:")
            self.addCleanup(db.close)
            days[d] = mo.Morning(db, mo.repo_plugs(ROOT))
        live = Db(":memory:")
        self.addCleanup(live.close)
        self.p = pages.Pages(days=days, live=mo.Morning(live, mo.repo_plugs(ROOT)))

    def test_phone_bar_says_sample_and_the_wide_bar_says_sample_data(self):
        page = self.p.get("/", {"day": ["1"]}, "t")
        bar = page.split('<header class="bar">')[1].split("</header>")[0]
        self.assertIn('>Sample</span>', bar)
        self.assertNotIn("Sample data<", bar)
        self.assertIn(">Sample data</span>", page.split('<nav class="tisl')[1].split("</nav>")[1])
        for w in ("Day 1", "Day 2", "Day 3", "Live"):
            self.assertIn(f">{w}</a>", bar)
        self.assertNotIn('class="sample"', self.p.get("/", {"day": ["live"]}, "t"))

    def test_labels_never_wrap_and_tighten_on_the_phone(self):
        css = pages.CSS
        self.assertRegex(css, r"\.days a\{[^}]*white-space:nowrap")
        self.assertRegex(css, r"\n\.sample\{[^}]*white-space:nowrap")
        phone = css.split("@media (max-width: 600px){")[-1].split("\n}")[0]
        self.assertIn(".bar .days a{padding:4px 7px}", phone)
        self.assertIn(".bar .sample{padding:4px 8px", phone)


if __name__ == "__main__":
    unittest.main()
