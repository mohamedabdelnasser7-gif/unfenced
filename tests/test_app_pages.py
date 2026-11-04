"""The app pages (LOCKS.md "App pages: 1B agent tabs, 2A build page, Console in the top menu"): the top
menu with Console on the agent last looked at, the console's agent picker, the agent page's four tabs as
links, and the build page's thread. A fake model only; nothing here calls the network."""
import tempfile
import unittest
from pathlib import Path

from engine import plug as plug_mod
from kit.db import Db
from reflection import console as console_mod
from reflection import morning as mo
from reflection import pages
from tests.fake_model import FakeModel

ROOT = Path(__file__).resolve().parent.parent


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(self.db.close)
        self.plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        self.m = mo.Morning(self.db, self.plugs, reports=self.folder)
        self.p = pages.Pages(self.m)

    def get(self, path, **query):
        return self.p.get(path, {k: [v] for k, v in query.items()}, "t")


class TopMenu(Base):
    def test_the_top_menu_has_today_agents_and_console(self):
        page = self.get("/")
        nav = page.split('<nav class="tisl', 1)[1].split("</nav>", 1)[0]
        for word in (">Today</a>", ">Agents</a>", ">Console</a>"):
            self.assertIn(word, nav)
        bar = page.split('<nav class="isl"', 1)[1]
        self.assertIn(">Console</a>", bar)

    def test_console_opens_on_the_agent_looked_at_else_sales(self):
        self.assertIn('href="/console?agent=sales"', self.get("/"))
        self.assertIn('href="/console?agent=sales"', self.get("/agents/sales"))
        self.assertIn('href="/console?agent=sales"', self.get("/new"))
        self.assertIsNone(self.get("/agents/nobody"))

    def test_console_has_the_menu_and_an_agent_picker_and_keeps_its_policy(self):
        page = self.get("/console", agent="sales")
        menu = page.split('<div class="menu">', 1)[1].split("</div>", 1)[0]
        self.assertIn('aria-current="page">Console</a>', menu)
        self.assertIn('<a class="sel" href="/console?agent=sales" aria-current="true">sales</a>', menu)
        csp = self.p.csp_for("/console")
        self.assertIn("script-src 'sha256-", csp)
        self.assertEqual(csp, console_mod.csp())
        self.assertNotIn("script-src", self.p.csp_for("/agents"))

    def test_the_menu_keeps_the_demo_day(self):
        p = pages.Pages(days={1: self.m, 2: self.m})
        page = p.get("/agents/sales", {"day": ["2"]}, "t")
        self.assertIn('href="/console?agent=sales&amp;day=2"', page)
        self.assertIn('href="/agents?day=2"', page)


def lost_run():
    return {"sales": {"file": "arena-sales-1.json", "at": 1_793_000_000.0, "line": "", "rounds": [],
                      "kind": "arena_rounds", "gate_won": None, "gate_played": None,
                      "lost": [{"card": "c1", "why": "it named a price with no value", "turn": 1, "who": "agent",
                                "text": "This one is 900 pounds, want it?"}]}}, []


class AgentTabs(Base):
    def test_four_tabs_as_links_the_one_shown_marked(self):
        page = self.get("/agents/sales")
        nav = page.split('<nav class="atabs"', 1)[1].split("</nav>", 1)[0]
        self.assertIn('<a class="on" href="/agents/sales" aria-current="page">Overview</a>', nav)
        for tab, word in (("arena", "Arena"), ("live", "Live"), ("lessons", "Lessons")):
            self.assertIn(f'<a href="/agents/sales?tab={tab}">{word}</a>', nav)
        arena = self.get("/agents/sales", tab="arena")
        self.assertIn('<a class="on" href="/agents/sales?tab=arena" aria-current="page">Arena</a>', arena)
        self.assertIn('<a class="on" href="/agents/sales" aria-current="page">Overview</a>',
                      self.get("/agents/sales", tab="nonsense"))
        self.assertNotIn("<script", page)

    def test_overview_holds_the_status_the_switches_and_the_correction_box(self):
        page = self.get("/agents/sales")
        for part in ('aria-label="Status"', 'action="/correct"', "Roll back", "Pull", "Since yesterday",
                     "Newest lessons", 'class="cons" href="/console?agent=sales"'):
            self.assertIn(part, page)
        self.assertNotIn("Practice matches", page)
        self.assertNotIn("Reflection notes", page)
        self.assertNotIn('action="/try/sales"', page)

    def test_arena_tab_has_correct_this_and_try_again_back_to_the_arena_tab(self):
        self.m.read_arena = lost_run
        page = self.get("/agents/sales", tab="arena")
        self.assertIn("Practice matches", page)
        form = page.split('class="fix"')[1].split("</details>")[0]
        self.assertIn('action="/correct"', form)
        self.assertIn('name="back" value="/agents/sales?tab=arena"', form)
        self.assertIn('action="/tryagain"', page)
        again = page.split('action="/tryagain"')[1].split("</form>")[0]
        self.assertIn('name="back" value="/agents/sales?tab=arena"', again)
        self.assertNotIn('action="/correct"', page.split('class="fix"')[0])  # no box outside the tile

    def test_live_tab_says_not_live_and_holds_try_sales(self):
        self.p = pages.Pages(self.m, try_model=FakeModel())
        page = self.get("/agents/sales", tab="live")
        self.assertIn("No live chats", page)
        self.assertIn("Not live yet.", page)
        self.assertIn('action="/try/sales"', page)
        self.assertIn('name="back" value="/agents/sales?tab=live"', page)

    def test_lessons_tab_has_lessons_and_reflection_notes(self):
        page = self.get("/agents/sales", tab="lessons")
        self.assertIn('id="l-h">Lessons</h3>', page)
        self.assertIn("Reflection notes", page)

    def test_an_answer_comes_back_to_its_tab(self):
        self.assertEqual(self.p.back("/agents/sales?tab=arena"), "/agents/sales?tab=arena")
        self.assertEqual(self.p.back("/agents/sales?tab=live"), "/agents/sales?tab=live")
        self.assertEqual(self.p.back("/agents/sales?tab=overview"), "/agents/sales")
        self.assertEqual(self.p.back("/agents/sales?tab=<x>"), "/agents/sales")
        self.assertEqual(self.p.back("/agents?tab=arena"), "/agents")


if __name__ == "__main__":
    unittest.main()
