"""Try Sales (reflection/try_sales.py, the box on the Sales agent's page): the real Sales agent's turn on
the demo store, no Shopify keys and no operator number inside the model call, the kept lessons handed,
each call counted on the day's Calls file, and nothing written to the page's database, the Arena
files, the exam rows or the connection rows, so a try never counts for the gate, the exam or Connect.
Behind the page's Host, Origin and token checks like every POST. Fake models only, no network."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from arena import match as match_mod
from arena import run
from engine import plug as plug_mod
from engine import risk
from kit import connections
from kit.db import Db
from reflection import morning as mo
from reflection import pages
from reflection import try_sales
from tests.fake_model import FakeModel, clean_env, say
from tests.test_console import lesson

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0
REPLY = "We have the blue trainer in 41, two pairs left."


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self, SHOPIFY_STORE="made-up.example", SHOPIFY_TOKEN="made-up-token", OPERATOR_WHATSAPP="201000000001")
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        self.m = mo.Morning(self.db, plugs, judge=lambda *a: risk.LOW, reports=self.dir, db_path=self.path)
        self.seen, self.systems = [], []
        self.model = FakeModel(*[self.answer] * 6)
        self.p = pages.Pages(self.m, try_model=self.model)

    def answer(self, messages, tools):
        self.seen.append({k: os.environ.get(k) for k in match_mod.KEEP_OUT})
        self.systems.append(messages[0]["content"])
        return say(REPLY)

    def files(self):
        return {p.name: p.read_bytes() for p in self.dir.iterdir()
                if p.is_file() and not p.name.startswith(("ascent.db", "arena-calls"))}

    def counts(self):
        with self.db.tx() as c:
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("chats", "steps", "trace", "lesson_exams", "lessons", "agent_connections") if t in tables}


class Turn(Base):
    def test_a_try_runs_on_the_demo_store_and_never_counts(self):
        kept = lesson(self.db, "Name the sizes left when the blue trainer stock is low.", "kept")
        item = {"agent": "sales", "kind": "arena_rounds", "at": NOW, "run": "r1", "line": "made up", "lost": [],
                "gate_won": 1, "gate_played": 4, "needs": 4, "quick": False}
        (self.dir / "arena-sales-r1.json").write_text(json.dumps(item), encoding="utf-8")
        gate, files, counts = self.m.gate("sales"), self.files(), self.counts()
        conns = connections.history(self.db, "sales")
        said = mo.TWO_TAB_ACTIONS.get("/try/sales") or self.p.actions["/try/sales"]
        self.assertEqual(said(self.m, {"text": ["Is the blue trainer in 41?"]}), "Sales answered.")
        self.assertEqual(self.seen, [{k: None for k in match_mod.KEEP_OUT}])  # no store keys, no operator number inside
        self.assertEqual(os.environ.get("SHOPIFY_TOKEN"), "made-up-token")  # and back after
        self.assertIn("Name the sizes left when the blue trainer stock is low.", self.systems[0])  # the kept lesson is handed
        self.assertEqual(self.p.try_sales.thread()[0]["replies"], [REPLY])
        self.assertEqual(self.m.gate("sales"), gate)
        self.assertEqual(self.files(), files)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(connections.history(self.db, "sales"), conns)
        self.assertEqual(json.loads((self.dir / run.CALLS_FILE).read_text())["calls"], 1)  # counted on the day's cap
        page = self.p.get("/agents/sales", {}, "tok")
        self.assertIn(REPLY, page)
        self.assertIn('action="/try/sales"', page)
        self.assertIn('action="/try/sales/clear"', page)
        self.assertIn(try_sales.NOTE, page)
        self.assertEqual(kept, self.m.lessons["sales"].get(kept)["id"])

    def test_start_over_and_the_limits(self):
        t = self.p.try_sales
        t.say(self.m, "Hello")
        self.assertEqual(t.customer(), "try-1")
        t.clear()
        self.assertEqual((t.thread(), t.customer()), ([], "try-2"))
        for bad, why in (("", "Write a message first."), ("x" * (try_sales.MAX_TEXT + 1), "at most")):
            with self.assertRaises(try_sales.Refused) as e:
                t.say(self.m, bad)
            self.assertIn(why, str(e.exception))
        t.busy = True
        with self.assertRaises(try_sales.Refused) as e:
            t.say(self.m, "Hi")
        self.assertEqual(str(e.exception), try_sales.BUSY)
        t.busy = False
        t.turns = [{"said": "x", "replies": [], "outcome": "replied"}] * try_sales.MAX_TURNS
        with self.assertRaises(try_sales.Refused):
            t.say(self.m, "Hi")

    def test_at_the_cap_or_with_no_key_nothing_is_called(self):
        (self.dir / run.CALLS_FILE).write_text(json.dumps({"day": run.today(), "calls": run.DEFAULT_CAP,
                                                          "cap": run.DEFAULT_CAP}), encoding="utf-8")
        with self.assertRaises(try_sales.Refused) as e:
            self.p.try_sales.say(self.m, "Hi")
        self.assertIn("cap", str(e.exception))
        self.assertEqual(self.seen, [])
        clean_env(self)
        bare = pages.Pages(self.m)
        self.assertFalse(bare.try_sales.ready())
        with self.assertRaises(try_sales.Refused) as e:
            bare.try_sales.say(self.m, "Hi")
        page = bare.get("/agents/sales", {}, "tok")
        self.assertIn("recorded/play.py", page)
        self.assertNotIn('action="/try/sales"', page)

    def test_only_the_sales_page_has_it(self):
        self.assertNotIn("Try Sales", self.p.get("/agents", {}, "tok"))
        self.assertNotIn('action="/try/sales"', self.p.get("/agents/sales", {}, None))


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
        token = self.server.token if token is None else token
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

    def test_the_guards_refuse_and_a_good_post_answers(self):
        for path, fields in (("/try/sales", [("text", "Hi")]), ("/try/sales/clear", [])):
            with self.subTest(path=path):
                self.assertEqual(self.post(path, fields, token="wrong")[0], 403)
                self.assertEqual(self.post(path, fields, origin=False)[0], 403)
                self.assertEqual(self.post(path, fields, host="example.com")[0], 403)
        self.assertEqual(self.seen, [])
        self.assertEqual(self.p.try_sales.chat_no, 1)
        status, page = self.post("/try/sales", [("text", "Is the blue trainer in 41?")])
        self.assertEqual(status, 200)
        self.assertIn(REPLY, page)
        self.assertIn("Sales answered.", page)


if __name__ == "__main__":
    unittest.main()
