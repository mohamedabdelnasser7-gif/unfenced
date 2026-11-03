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


if __name__ == "__main__":
    unittest.main()
