"""Deploy is the user's step after the Arena (DECISIONS item 77; kit/connections.py, reflection/morning.py
Morning.connect and disconnect, reflection/pages.py Connections, channels/whatsapp.py App.live).

1. The live state: one row a connect or Pull, never changed or deleted, the latest wins, and a read
   never makes the table.
2. The gate: until the agent's latest Arena gate passed, Connect to WhatsApp is greyed out with the
   reason and the POST is refused; after a pass it connects, and the page says since when and what
   unlocked it. Pull takes it off. No count of the gate shows (item 17).
3. The POSTs carry the page's token and pass its Origin and Host checks, like every other answer.
4. The channel answers only while connected: when not, it sends nothing and logs one line.
5. An agent Quick start built asks for the channels its card names; WhatsApp for it is next.
Temp databases and folders only, no model call, no network."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from channels import whatsapp as wa
from engine import plug as plug_mod
from kit import connections, switch
from kit.chats import Chats
from kit.db import Db
from reflection import morning as mo
from reflection import pages
from reflection.lessons import Lessons
from reflection.results import Results
from sales import quiet
from tests.fake_model import FakeModel, clean_env, say
from tests.test_whatsapp import SendingGraph, payload, text_msg

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_800_000_000.0
WHO = "201111111111"
ANSWER = "أهلا بيك، تحب تعرف إيه؟"


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json")], reports=self.folder)
        self.p = pages.Pages(self.m)

    def arena(self, kind="arena_rounds", won=4, played=4, needs=4, run="r1", at=NOW, **extra):
        item = dict({"agent": "sales", "kind": kind, "at": at, "run": run, "rounds": 2, "gate_won": won,
                     "gate_played": played, "needs": needs, "lost": [], "line": "made up for the test"}, **extra)
        (self.folder / f"arena-sales-{run}.json").write_text(json.dumps(item), encoding="utf-8")

    def page(self, token="t"):
        return self.p.get("/agents/sales", {}, token)

    def conn(self, page):
        return page.split('class="grp sq conn"')[1].split("</section>")[0]

    def bar(self, page):
        return page.split('class="st-r"')[1].split("</section>")[0]


class TheLiveState(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def test_the_latest_row_wins_and_rows_are_never_changed_or_deleted(self):
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))
        connections.connect(self.db, "sales", "whatsapp", why="The gate passed.", by="the user", now=NOW)
        self.assertTrue(connections.live(self.db, "sales", "whatsapp"))
        self.assertEqual(connections.live_agents(self.db), {"sales"})
        connections.disconnect(self.db, "sales", "whatsapp", why="Pull", by="the user", now=NOW + 60)
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))
        self.assertEqual(connections.live_agents(self.db), set())
        self.assertEqual([(h["on"], h["at"]) for h in connections.history(self.db, "sales")],
                         [(True, NOW), (False, NOW + 60)])
        for sql in ("UPDATE agent_connections SET value = 'on'", "DELETE FROM agent_connections"):
            with self.assertRaises(Exception):
                with self.db.tx() as c:
                    c.execute(sql)
        self.assertEqual(len(connections.history(self.db, "sales")), 2)

    def test_a_read_never_makes_the_table(self):
        self.assertEqual(connections.state(self.db, "sales"), {})
        self.assertEqual(connections.live_agents(self.db), set())
        with self.db.tx() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'agent_connections'").fetchone())

    def test_only_a_built_channel_for_its_agent_connects(self):
        for agent, channel in (("sales", "email"), ("marketing", "whatsapp"), ("sales", "sms")):
            with self.assertRaises(ValueError):
                connections.connect(self.db, agent, channel, why="x", by="the user")
        with self.assertRaises(ValueError):
            connections.connect(self.db, "sales", "whatsapp", why="two\nlines", by="the user")
        self.assertEqual(connections.live_agents(self.db), set())


class TheGate(Base):
    def test_no_arena_run_greys_connect_out_with_the_reason_and_refuses_it(self):
        page = self.page()
        box = self.conn(page)
        self.assertNotIn('action="/connect"', page)
        self.assertIn('<button class="yes" type="button" disabled title="Locked until its latest Arena gate passes.">'
                      "Connect to WhatsApp", box)
        self.assertIn("Locked until its latest Arena gate passes. No saved Arena run yet.", box)
        self.assertIn('disabled title="Not live on any channel"', self.bar(page))
        with self.assertRaises(mo.Refused):
            self.m.connect("sales", "whatsapp", now=NOW)
        self.assertEqual(connections.live_agents(self.db), set())

    def test_a_gate_that_did_not_pass_refuses(self):
        for kind, won in (("arena_rounds", 3), ("arena_stuck", 3), ("arena_stuck", 4)):
            with self.subTest(kind=kind, won=won):
                self.arena(kind=kind, won=won)
                self.assertFalse(self.m.gate("sales")["passed"])
                self.assertNotIn('action="/connect"', self.page())
                self.assertIn("did not pass the gate", self.conn(self.page()))
                with self.assertRaises(mo.Refused) as e:
                    self.m.connect("sales", "whatsapp", now=NOW)
                self.assertIn("did not pass the gate", str(e.exception))
                self.assertEqual(connections.live_agents(self.db), set())

    def test_odd_counts_in_a_saved_item_never_pass(self):
        for won, needs in ((True, 1), ("4", 4), (4, 0), (4, None), (-1, -2)):
            with self.subTest(won=won, needs=needs):
                self.arena(won=won, needs=needs)
                self.assertFalse(self.m.gate("sales")["passed"])

    def test_only_the_latest_run_counts(self):
        self.arena(run="r1", at=NOW)
        self.arena(run="r2", at=NOW + 60, won=1)
        self.assertFalse(self.m.gate("sales")["passed"])
        self.arena(run="r3", at=NOW + 120)
        self.assertTrue(self.m.gate("sales")["passed"])

    def test_a_pass_connects_and_the_page_says_since_when_and_what_unlocked_it(self):
        self.arena()
        page = self.page()
        self.assertIn('action="/connect"', page)
        self.assertIn("passed the gate on", self.conn(page))
        self.assertIn('aria-label="Status: Training"', page)
        said = mo.TWO_TAB_ACTIONS["/connect"](self.m, {"agent": ["sales"], "channel": ["whatsapp"]}, now=NOW + 300)
        self.assertEqual(said, "Live on WhatsApp. It answers the next message there.")
        self.assertTrue(connections.live(self.db, "sales", "whatsapp"))
        row = connections.state(self.db, "sales")["whatsapp"]
        self.assertEqual((row["by"], row["at"]), (mo.BY, NOW + 300))
        self.assertIn("passed the gate on", row["why"])
        page = self.page()
        box = self.conn(page)
        self.assertIn(f"Live on WhatsApp since {mo._when(NOW + 300)}. Its latest Arena run passed the gate on "
                      f"{mo._when(NOW)}.", box)
        self.assertIn('<span class="vchip trial">Live</span>', box)
        self.assertNotIn("Connect to WhatsApp", box)
        self.assertIn('aria-label="Status: Live"', page)
        self.assertIn('action="/disconnect"', self.bar(page))
        self.assertIn('<span class="st live">Live</span>', self.p.get("/agents", {}, "t"))
        self.assertIn("already", self.m.connect("sales", "whatsapp", now=NOW + 301))
        self.assertEqual(len(connections.history(self.db, "sales")), 1)

    def test_no_gate_count_on_the_page(self):
        self.arena(won=3, played=5, needs=3)
        box = self.conn(self.page())
        self.assertNotIn("held-out", box)
        self.assertNotIn("3 of 5", box)
        self.assertNotIn("needed", box)

    def test_connect_resumes_a_paused_agent(self):
        self.arena()
        switch.pause("sales", db=self.db, now=NOW, by="the user")
        self.m.connect("sales", "whatsapp", now=NOW + 10)
        self.assertFalse(switch.is_paused("sales", db=self.db))
        self.assertEqual(switch.resumed_at("sales", db=self.db), NOW + 10)

    def test_a_channel_its_card_does_not_ask_for_is_refused(self):
        self.arena()
        for channel in ("email", "", "../whatsapp"):
            with self.assertRaises(mo.Refused):
                self.m.connect("sales", channel)
        with self.assertRaises(mo.Refused):
            self.m.connect("nobody", "whatsapp")
        self.assertEqual(connections.live_agents(self.db), set())


class Pull(Base):
    def test_pull_takes_it_off_and_connect_comes_back(self):
        self.arena()
        self.m.connect("sales", "whatsapp", now=NOW + 10)
        said = mo.TWO_TAB_ACTIONS["/disconnect"](self.m, {"agent": ["sales"]}, now=NOW + 20)
        self.assertEqual(said, "Pulled from WhatsApp. It sends nothing there until you connect it again.")
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))
        self.assertEqual(self.m._live(), set())
        page = self.page()
        self.assertIn('aria-label="Status: Training"', page)
        self.assertIn(f"Pulled {mo._when(NOW + 20)}.", self.conn(page))
        self.assertIn('action="/connect"', page)
        self.assertNotIn('action="/disconnect"', page)
        self.assertEqual(self.m.disconnect("sales", now=NOW + 30), "It is not live on any channel.")
        self.assertEqual(len(connections.history(self.db, "sales")), 2)


class OverTheServer(Base):
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
            token = self.server.token
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

    def test_a_quick_run_never_unlocks_connect(self):
        """Review simplify round 1, finding 1: --quick is a gate of one match, never enough to go live."""
        self.arena(won=1, played=1, needs=1, quick=True)
        gate = self.m.gate("sales")
        self.assertFalse(gate["passed"])
        self.assertIn("quick one", gate["said"])
        status, page = self.post("/connect", [("agent", "sales"), ("channel", "whatsapp")])
        self.assertIn("Not connected.", page)
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))

    def test_connect_is_refused_before_the_gate_and_works_after_then_pull(self):
        status, page = self.post("/connect", [("agent", "sales"), ("channel", "whatsapp")])
        self.assertEqual(status, 200)  # the 303 back, followed: the flash says why
        self.assertIn("Not connected.", page)
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))
        self.arena()
        status, page = self.post("/connect", [("agent", "sales"), ("channel", "whatsapp")])
        self.assertTrue(connections.live(self.db, "sales", "whatsapp"))
        self.assertIn("Live on WhatsApp since", page)
        status, page = self.post("/disconnect", [("agent", "sales")])
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))
        self.assertIn("Pulled from WhatsApp", page)

    def test_no_origin_a_wrong_host_or_a_wrong_token_changes_nothing(self):
        self.arena()
        fields = [("agent", "sales"), ("channel", "whatsapp")]
        self.assertEqual(self.post("/connect", fields, origin=False)[0], 403)
        self.assertEqual(self.post("/connect", fields, host=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self.post("/connect", fields, token="wrong")[0], 403)
        self.assertFalse(connections.live(self.db, "sales", "whatsapp"))
        self.m.connect("sales", "whatsapp")
        self.assertEqual(self.post("/disconnect", [("agent", "sales")], origin=False)[0], 403)
        self.assertEqual(self.post("/disconnect", [("agent", "sales")], token="wrong")[0], 403)
        self.assertTrue(connections.live(self.db, "sales", "whatsapp"))


class TheChannel(unittest.TestCase):
    """channels/whatsapp.py: with no fixed setting it follows Connect and Pull in the database."""

    def setUp(self):
        clean_env(self)
        self.now = NOW
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db, clock=lambda: self.now)
        self.graph = SendingGraph(b"", "audio/ogg")

    def app(self, model=None, **kw):
        return wa.App(self.chats, model or FakeModel(), Lessons(self.db), Results(self.db), self.graph,
                      clock=lambda: self.now, **kw)

    def one(self, app, mid="wamid.m1"):
        app.accept(wa.parse(payload(text_msg(mid, "التوصيل بكام؟", frm=WHO))))
        return app.work_one(app.q.get_nowait())

    def test_not_connected_sends_nothing_and_logs_one_line(self):
        app = self.app(FakeModel())  # a model call would fail the test: FakeModel has no answer queued
        with self.assertLogs("channels.whatsapp", "INFO") as logs:
            self.assertIsNone(self.one(app))
        self.assertEqual(logs.output, [f"INFO:channels.whatsapp:{wa.NOT_LIVE_LOG}"])
        self.assertEqual(self.graph.sent, [])
        self.assertTrue(self.chats.saved("wamid.m1"))  # done, so a restart never answers it late
        self.assertEqual(self.chats.pending(), [])
        self.assertEqual(app.quiet_once(), [])

    def test_connected_answers_and_pull_silences_it_again(self):
        connections.connect(self.db, "sales", "whatsapp", why="The gate passed.", by="the user", now=NOW)
        app = self.app(FakeModel(say(ANSWER)))
        self.assertEqual(self.one(app).outcome, "replied")
        self.assertEqual(self.graph.sent[-1], (WHO, ANSWER))
        connections.disconnect(self.db, "sales", "whatsapp", why="Pull", by="the user", now=NOW + 1)
        sent = len(self.graph.sent)
        self.assertIsNone(self.one(app, "wamid.m2"))
        self.assertEqual(len(self.graph.sent), sent)

    def test_fixed_on_still_stops_at_a_pull_made_after_it_started(self):
        """Review simplify round 1, finding 2: Pull always works, WHATSAPP_LIVE=on included."""
        connections.disconnect(self.db, "sales", "whatsapp", why="Pull", by="the user", now=NOW - 60)
        app = self.app(FakeModel(say(ANSWER)), connected=True)  # a Pull before the start does not count
        self.assertEqual(self.one(app).outcome, "replied")
        connections.disconnect(self.db, "sales", "whatsapp", why="Pull", by="the user", now=NOW + 1)
        sent = len(self.graph.sent)
        self.assertIsNone(self.one(app, "wamid.m2"))
        self.assertEqual(len(self.graph.sent), sent)
        self.assertEqual(app.quiet_once(), [])

    def test_the_setting_fixes_it_either_way(self):
        connections.connect(self.db, "sales", "whatsapp", why="The gate passed.", by="the user", now=NOW)
        self.assertIsNone(self.one(self.app(connected=False)))
        self.assertEqual(self.graph.sent, [])
        self.assertEqual(self.one(self.app(FakeModel(say(ANSWER)), connected=True), "wamid.m2").outcome, "replied")
        self.assertEqual(wa.live_setting(""), None)
        self.assertEqual(wa.live_setting(None), None)
        self.assertIs(wa.live_setting(" ON "), True)
        self.assertIs(wa.live_setting("off"), False)
        with self.assertRaises(SystemExit):
            wa.live_setting("yes")

    def test_a_notice_due_while_not_connected_is_never_sent(self):
        connections.connect(self.db, "sales", "whatsapp", why="The gate passed.", by="the user", now=NOW)
        app = self.app(FakeModel(say(ANSWER)))
        chat_id = self.one(app).chat_id
        connections.disconnect(self.db, "sales", "whatsapp", why="Pull", by="the user", now=NOW + 10)
        self.now += quiet.NOTICE_AFTER + quiet.START_GRACE + 60  # past the quick restart grace
        self.assertEqual(app.quiet_once(), [])  # not connected: no notice and no close
        connections.connect(self.db, "sales", "whatsapp", why="The gate passed.", by="the user", now=self.now)
        sent = len(self.graph.sent)
        self.assertEqual(app.quiet_once(), [(chat_id, "closed")])  # closed silently, no notice
        self.assertEqual(len(self.graph.sent), sent)

    def test_a_state_that_cannot_be_read_answers_nothing(self):
        app = self.app()
        broken = Db(":memory:")
        broken.close()
        app.chats = Chats.__new__(Chats)
        app.chats.db = broken
        with self.assertLogs("channels.whatsapp", "ERROR"):
            self.assertFalse(app.live())


class AQuickStartAgent(unittest.TestCase):
    """An agent Quick start built asks for the channels its card.json tools name: WhatsApp for it is
    next, and any other channel is not connected yet, in one line."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name).resolve()
        where = folder / "agents" / "stock_watch"
        where.mkdir(parents=True)
        for f in (ROOT / "tests" / "agents" / "stock_watch").iterdir():
            (where / f.name).write_bytes(f.read_bytes())
        card = json.loads((where / "card.json").read_text(encoding="utf-8"))
        (where / "card.json").write_text(json.dumps(dict(card, tools=["whatsapp", "email", "store", "bosta_stock", "switch_stage"])), encoding="utf-8")
        db_path = str(folder / "ascent.db")
        self.db = Db(db_path)
        self.addCleanup(self.db.close)
        plugs, built = mo.with_built([plug_mod.load(ROOT / "sales" / "plug.json")], db_path)
        self.m = mo.Morning(self.db, plugs, reports=folder, built=built, db_path=db_path)
        self.p = pages.Pages(self.m)
        (folder / "arena-stock_watch-r1.json").write_text(json.dumps(
            {"agent": "stock_watch", "kind": "arena_rounds", "at": NOW, "run": "r1", "gate_won": 4, "gate_played": 4,
             "needs": 4, "lost": [], "line": "x", "practice": True}), encoding="utf-8")

    def test_whatsapp_is_next_and_other_channels_are_not_connected_yet(self):
        self.assertEqual(self.m.channels_of("stock_watch"), ["whatsapp", "email"])
        self.assertTrue(self.m.gate("stock_watch")["passed"])
        self.assertIn("Its practice in the Arena passed the gate", self.m.gate("stock_watch")["said"])
        page = self.p.get("/agents/stock_watch", {}, "t")
        box = page.split('class="grp sq conn"')[1].split("</section>")[0]
        self.assertIn("Connecting an agent made in Quick start to WhatsApp is next.", box)
        self.assertIn("<b>Email</b><span class=\"vchip\">Not connected</span><small>Not connected yet.</small>", box)
        self.assertNotIn('action="/connect"', page)
        self.assertIn("disabled", box)
        self.assertIn('action="/pause"', page)  # an agent no channel runs keeps Pull as the pause switch
        for channel in ("whatsapp", "email"):
            with self.assertRaises(mo.Refused):
                self.m.connect("stock_watch", channel)
        self.assertEqual(connections.live_agents(self.db), set())


if __name__ == "__main__":
    unittest.main()
