"""Pages review round 1, findings 3 and 10, wired: the correction box calls Lessons.correct (a hotfix on
half the chats at once, the exam first, high risk waits for a yes on Today), and Pull on the agent page is
the real pause switch (kit/switch.py, DECISIONS 54) with Resume when paused, both through the page's
server with its token, Origin and Host checks. Temp databases only, no model call: the examiner is a fake."""
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from engine import exam as exam_mod
from engine import plug as plug_mod
from engine import risk
from engine.lessons import HOTFIX_SHARE, HOTFIX_SOURCE, TRYING, WAITING
from kit import switch
from kit.db import Db
from reflection import morning as mo
from reflection import pages

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0
LOW = "When someone asks for a photo, send the product link first."
HIGH = "When someone asks about the price, send the total with delivery first."


def low(text, high_about, low_about):
    return risk.LOW


def passed(text, tags):
    return exam_mod.Result(True, [exam_mod.Row(1, "s1", "guard", True)], calls=1)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Db(str(Path(self.tmp.name) / "ascent.db"))
        self.addCleanup(self.db.close)
        self.plugs = [plug_mod.load(ROOT / "sales" / "plug.json"), plug_mod.load(ROOT / "assistant" / "plug.json")]
        self.m = mo.Morning(self.db, self.plugs, judge=low, exams={"sales": passed})
        self.p = pages.Pages(self.m)

    def page(self, agent="sales", token="t"):
        return self.p.get(f"/agents/{agent}", {}, token)


class TheSwitchSaysWho(unittest.TestCase):
    """kit/switch.py: pause and resume name who flipped it (by=); an older table gains the column."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def test_by_is_kept(self):
        switch.pause("sales", db=self.db, now=NOW, by="the user")
        self.assertTrue(switch.is_paused("sales", db=self.db))
        self.assertEqual(switch.set_by("sales", db=self.db), "the user")
        switch.resume("sales", db=self.db, now=NOW + 60, by="mona")
        self.assertFalse(switch.is_paused("sales", db=self.db))
        self.assertEqual((switch.set_by("sales", db=self.db), switch.resumed_at("sales", db=self.db)), ("mona", NOW + 60))
        switch.pause("sales", db=self.db, now=NOW + 120)  # the old callers name nobody
        self.assertIsNone(switch.set_by("sales", db=self.db))

    def test_a_table_made_before_by_gains_it(self):
        self.db.script("CREATE TABLE agent_switch (agent TEXT PRIMARY KEY, paused INTEGER NOT NULL "
                       "CHECK (paused IN (0, 1)), at REAL NOT NULL)")
        self.db.conn.execute("INSERT INTO agent_switch VALUES ('sales', 1, ?)", (NOW,))
        self.assertTrue(switch.is_paused("sales", db=self.db))
        switch.resume("sales", db=self.db, now=NOW + 1, by="the user")
        self.assertEqual(switch.set_by("sales", db=self.db), "the user")

    def test_a_bad_name_is_refused_and_nothing_changes(self):
        for bad in ("", "  ", "a\nb", "x" * 81, 7):
            with self.assertRaises(ValueError):
                switch.pause("sales", db=self.db, by=bad)
        self.assertFalse(switch.is_paused("sales", db=self.db))


class PullIsThePauseSwitch(Base):
    """Finding 10: the pause switch pauses the agent for real, signed by the page's person; Resume when
    paused. On the Sales agent's page Pull takes it off WhatsApp (DECISIONS item 77, test_connect.py), so
    while it is not live Pull is greyed out, and a pause left from before still shows Resume."""

    def test_pull_then_resume(self):
        page = self.page()
        self.assertNotIn('action="/pause"', page)
        self.assertNotIn('action="/resume"', page)
        self.assertIn('disabled title="Not live on any channel"', page.split('class="st-r"')[1].split("</section>")[0])
        said = mo.TWO_TAB_ACTIONS["/pause"](self.m, {"agent": ["sales"]}, now=NOW)
        self.assertIn("Paused", said)
        self.assertTrue(switch.is_paused("sales", db=self.db))
        self.assertEqual(switch.set_by("sales", db=self.db), mo.BY)
        page = self.page()
        self.assertIn('aria-label="Status: Paused"', page)
        self.assertIn(pages.STATUS_SAID["Paused"], page)
        self.assertIn('action="/resume"', page)
        self.assertNotIn('action="/pause"', page)
        self.assertIn(">Paused</span>", self.p.get("/agents", {}, "t"))
        self.assertIn("already", self.m.pause("sales", now=NOW + 1))
        said = mo.TWO_TAB_ACTIONS["/resume"](self.m, {"agent": ["sales"]}, now=NOW + 60)
        self.assertIn("Resumed", said)
        self.assertFalse(switch.is_paused("sales", db=self.db))
        self.assertEqual(switch.resumed_at("sales", db=self.db), NOW + 60)  # quiet counts from here
        self.assertNotIn('action="/resume"', self.page())
        self.assertIn("already", self.m.resume("sales", now=NOW + 61))
        self.assertEqual(switch.resumed_at("sales", db=self.db), NOW + 60)  # a second Resume moves nothing

    def test_only_an_agent_whose_code_reads_the_switch_gets_pull(self):
        with self.assertRaises(mo.Refused):
            self.m.pause("assistant")
        with self.assertRaises(mo.Refused):
            self.m.pause("nobody")
        with self.assertRaises(mo.Refused):
            self.m.resume("nobody")
        bar = self.page("assistant").split('class="st-r"')[1].split("</section>")[0]
        self.assertNotIn('action="/pause"', bar)
        self.assertIn("disabled", bar)
        self.assertFalse(self.m.paused("assistant"))

    def test_the_static_page_has_no_pull_form(self):
        bar = self.page(token=None).split('class="st-r"')[1].split("</section>")[0]
        self.assertNotIn("<form", bar)
        self.assertIn("disabled", bar)

    def test_a_page_view_never_makes_the_switch_table(self):
        self.page()
        self.p.get("/agents", {}, "t")
        self.p.get("/", {}, "t")
        with self.db.tx() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'agent_switch'").fetchone())


class OverTheServer(Base):
    """The page's server: Pull, Resume and the correction box as POSTs with the token, Origin and Host checks."""

    def setUp(self):
        super().setUp()
        self.server = mo.make_server(self.m, port=0, pages=self.p)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(5)
        self.addCleanup(stop)

    def post(self, path, fields, *, token=None, origin=True, host=None):
        if token is None:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/agents/sales", timeout=10) as r:
                token = r.read().decode("utf-8").split('name="token" value="')[1].split('"')[0]
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{self.port}"
        if host:
            headers["Host"] = host
        body = urllib.parse.urlencode([("token", token), ("back", "/agents/sales")] + list(fields)).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, ""

    def test_pull_and_resume_over_the_server(self):
        status, page = self.post("/pause", [("agent", "sales")])
        self.assertEqual(status, 200)  # the 303 back to the agent page, followed
        self.assertTrue(switch.is_paused("sales", db=self.db))
        self.assertIn("Paused. It sends nothing", page)
        self.assertIn('action="/resume"', page)
        status, page = self.post("/resume", [("agent", "sales")])
        self.assertFalse(switch.is_paused("sales", db=self.db))
        self.assertNotIn('action="/resume"', page)
        self.assertIn('aria-label="Status: Training"', page)

    def test_no_origin_a_wrong_host_or_a_wrong_token_changes_nothing(self):
        self.assertEqual(self.post("/pause", [("agent", "sales")], origin=False)[0], 403)
        self.assertEqual(self.post("/pause", [("agent", "sales")], host=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self.post("/pause", [("agent", "sales")], token="wrong")[0], 403)
        self.assertFalse(self.m.paused("sales"))
        self.assertEqual(self.post("/correct", [("agent", "sales"), ("line", LOW)], token="wrong")[0], 403)
        self.assertEqual(self.m.lessons["sales"].mine(), [])

    def test_the_correction_box_starts_a_hotfix(self):
        status, page = self.post("/correct", [("agent", "sales"), ("line", LOW)])
        self.assertEqual(status, 200)
        L = self.m.lessons["sales"]
        les = L.mine()[-1]
        self.assertEqual((les["text"], les["state"], les["share"], les["source"]), (LOW, TRYING, HOTFIX_SHARE, HOTFIX_SOURCE))
        self.assertIn("runs now as a hotfix in half the cases", page)
        self.assertIn("Hotfix", page)
        self.post("/correct", [("agent", "sales"), ("line", HIGH)])
        held = L.mine()[-1]
        self.assertEqual((held["text"], held["state"]), (HIGH, WAITING))
        self.assertTrue(L.wants_yes(held["id"]))
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10) as r:
            self.assertIn(HIGH, r.read().decode("utf-8"))  # its Yes card on Today


if __name__ == "__main__":
    unittest.main()
