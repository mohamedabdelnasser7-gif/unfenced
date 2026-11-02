"""Try again (arena/retry.py, reflection/morning.py Morning.try_again, reflection/pages.py try_again): after
an Arena run stopped, only the matches it lost are played again against the same practice customers, with
the kept lessons and the corrections that passed; the result shows on the Arena screen and never counts for
the gate. Fake models only, no network; the cards are made here."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from arena import retry, rounds, run
from engine import plug as plug_mod
from engine import risk
from kit.db import Db
from reflection import PLUG
from reflection import morning as mo
from reflection import pages
from reflection.lessons import Lessons as SalesLessons
from tests.fake_model import clean_env
from tests.test_arena_hotfix import FIX, correct
from tests.test_arena_rounds import Agent
from tests.test_arena_run import Customer, card

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0


class Seen:
    """A customer model that keeps the system message of every call (which practice customer it plays)."""

    def __init__(self, inner, seen):
        self.inner, self.seen = inner, seen

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.seen.append(messages[0]["content"])
        return self.inner.chat(messages, tools, effort, max_tokens, whole)


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        self.m = mo.Morning(self.db, plugs, judge=lambda *a: risk.LOW, reports=self.dir, db_path=self.path)
        self.agent, self.customer, self.seen = Agent(), Customer(("price",)), []
        self.m.retry_models = lambda: (self.agent, Seen(self.customer, self.seen))
        self.m.retry_start = lambda work, name: work()  # at once, so the test reads what it wrote

    def stuck(self, buyers=()):
        """A run where the held-out customers leave: stuck, its item and its lost matches saved here."""
        cards = [card(1, "size"), card(2, "price"), card(3, "fit")]
        a = run.Arena(cards, agent_model=Agent(), customer_model=Customer(buyers), state=self.dir,
                      calls=run.Calls(self.dir / run.CALLS_FILE, 1000), held_out=["persona-02", "persona-03"],
                      trust={"matches": 4, "wins": 3, "zero_failed_checks": True}, matches=1, now=lambda: NOW)
        rep = a.run()
        self.assertEqual(rep["stopped"], run.STUCK)
        # both held-out customers in the item's lost matches, whichever the gate drew in its last round
        self.assertEqual(set(retry.saved_lost(self.dir, rep["run"], ["persona-02", "persona-03"])),
                         {"persona-02", "persona-03"})
        path = self.dir / rep["stuck"]["file"]
        item = json.loads(path.read_text(encoding="utf-8"))
        item["lost"] = [{"card": c, "why": "the customer left", "quote": {"turn": 1, "who": "agent", "text": "Hello"}}
                        for c in ("persona-02", "persona-02", "persona-03")]
        path.write_text(json.dumps(item), encoding="utf-8")
        return rep

    def item(self):
        return self.m.read_arena()[0]["sales"]


class Refusals(Base):
    def test_no_lost_match_is_refused(self):
        (self.dir / "arena-sales-r1.json").write_text(json.dumps(
            {"agent": "sales", "kind": "arena_rounds", "at": NOW, "run": "r1", "line": "x", "lost": [],
             "gate_won": 4, "gate_played": 4, "needs": 3}), encoding="utf-8")
        with self.assertRaises(mo.Refused) as e:
            self.m.try_again("sales")
        self.assertIn("lost no practice match", str(e.exception))
        empty = Db(":memory:")
        self.addCleanup(empty.close)
        with self.assertRaises(mo.Refused):  # no Arena item at all
            mo.Morning(empty, list(self.m.plugs.values()), reports=self.dir / "none",
                       db_path=self.dir / "none.db").try_again("sales")

    def test_a_try_running_is_refused(self):
        self.stuck()
        self.m._trying.add("sales")
        with self.assertRaises(mo.Refused) as e:
            self.m.try_again("sales")
        self.assertIn("running for this agent already", str(e.exception))
        self.assertEqual(list(self.dir.glob("arena-sales-retry-*.json")), [])

    def test_a_full_cap_is_refused(self):
        self.stuck()
        (self.dir / run.CALLS_FILE).write_text(json.dumps({"day": run.today(), "calls": run.DEFAULT_CAP}),
                                               encoding="utf-8")
        with self.assertRaises(mo.Refused) as e:
            self.m.try_again("sales")
        self.assertIn("cap has no room", str(e.exception))
        self.assertFalse(self.m.trying("sales"))

    def test_another_agent_and_no_database_are_refused(self):
        with self.assertRaises(mo.Refused) as e:
            self.m.try_again("stock_watch")
        self.assertEqual(str(e.exception), mo.TRY_NOT_BUILT)
        self.m.db_path = None
        with self.assertRaises(mo.Refused):
            self.m.try_again("sales")


class Replay(Base):
    def test_a_retry_item_is_written_and_read(self):
        rep = self.stuck()
        before = self.item()
        self.assertEqual(retry.lost_cards(before["lost"]), ["persona-02", "persona-03"])  # each card once
        said = self.m.try_again("sales")
        self.assertEqual(said, retry.STARTED)
        self.assertFalse(self.m.trying("sales"))
        files = list(self.dir.glob("arena-sales-retry-*.json"))
        self.assertEqual(len(files), 1)
        saved = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual((saved["kind"], saved["retried"]), (retry.KIND, rep["run"]))
        self.assertNotIn("gate_won", saved)
        got = {r["card"]: r for r in saved["results"]}
        self.assertEqual(got["persona-02"]["result"], retry.WON_AGAIN)  # the price customer buys now
        self.assertEqual(got["persona-03"]["result"], retry.STILL_LOST)  # the fit customer still leaves
        self.assertTrue(got["persona-03"]["quote"]["text"])
        after = self.item()
        self.assertEqual(after["file"], before["file"])  # the run's item stays the agent's item
        self.assertEqual({r["card"]: r["result"] for r in after["retry"]["results"]},
                         {"persona-02": "won", "persona-03": "lost"})

    def test_same_customers_and_the_count_file(self):
        self.stuck()
        calls_before = json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]
        matches_before = (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8")
        self.m.try_again("sales")
        saved = self.item()["retry"]
        self.assertTrue(saved["results"])
        self.assertGreater(json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"], calls_before)
        self.assertEqual((self.dir / run.MATCHES_FILE).read_text(encoding="utf-8"), matches_before)  # no past wins added
        worries = {c.split("Your worry is ")[1].split(".")[0] for c in self.seen}
        self.assertEqual(worries, {"price", "fit"})  # the same two practice customers the run lost to

    def test_an_older_retry_is_hidden_by_a_newer_run(self):
        self.stuck()
        self.m.try_again("sales")
        self.assertIsNotNone(self.item()["retry"])
        (self.dir / "arena-sales-r9.json").write_text(json.dumps(
            {"agent": "sales", "kind": "arena_stuck", "at": NOW + 999_999, "run": "r9", "line": "x",
             "lost": [{"card": "persona-02", "why": "left", "quote": {"turn": 1, "who": "agent", "text": "Hi"}}],
             "gate_won": 0, "gate_played": 4, "needs": 3}), encoding="utf-8")
        self.assertIsNone(self.item()["retry"])

    def test_a_failure_in_the_thread_becomes_the_screen_line(self):
        self.stuck()

        def broken():
            raise RuntimeError("the route is busy")
        self.m.retry_models = broken
        self.m.try_again("sales")
        self.assertFalse(self.m.trying("sales"))
        self.assertIn("the route is busy", self.m.try_note("sales"))


class GateIgnoresIt(Base):
    def test_a_retry_that_won_everything_does_not_pass_the_gate(self):
        self.stuck()
        self.customer = Customer(("price", "fit"))
        self.m.try_again("sales")
        self.assertTrue(all(r["result"] == "won" for r in self.item()["retry"]["results"]))
        gate = self.m.gate("sales")
        self.assertFalse(gate["passed"])
        self.assertIn("did not pass the gate", gate["said"])

    def test_a_retry_with_gate_counts_written_in_is_still_ignored(self):
        self.stuck()
        (self.dir / "arena-sales-retry-x.json").write_text(json.dumps(
            {"agent": "sales", "kind": retry.KIND, "at": NOW + 10, "run": "retry-x", "retried": "r1", "line": "x",
             "gate_won": 9, "gate_played": 9, "needs": 1, "results": []}), encoding="utf-8")
        self.assertEqual(self.item()["kind"], "arena_stuck")
        self.assertFalse(self.m.gate("sales")["passed"])


class Hotfixes(Base):
    def test_the_replay_plays_with_the_passed_corrections(self):
        self.stuck()
        correct(self.path, FIX)
        self.m.try_again("sales")
        self.assertTrue(self.agent.systems)
        self.assertTrue(all(FIX in s for s in self.agent.systems))
        saved = json.loads(next(self.dir.glob("arena-sales-retry-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(saved["hotfixes"]), 1)

    def test_a_held_correction_is_not_handed(self):
        from tests.test_arena_hotfix import failed
        self.stuck()
        correct(self.path, FIX, exam=failed)
        self.m.try_again("sales")
        self.assertFalse(any(FIX in s for s in self.agent.systems))

    def test_the_pool_reads_the_live_corrections(self):
        correct(self.path, FIX)
        pool = rounds.Pool(SalesLessons(self.db), hotfixes=lambda: rounds.live_hotfixes(self.path, PLUG.agent))
        pool.refresh()
        self.assertIn(FIX, [p["text"] for p in pool.pick("greeting", "hi")])


class Screen(Base):
    def page(self, token="t"):
        return pages.Pages(self.m).get("/new/build", {"agent": ["sales"]}, token)

    def test_the_button_sits_under_the_lost_matches(self):
        self.stuck()
        page = self.page()
        form = page.split('action="/tryagain"')[1].split("</form>")[0]
        self.assertIn('name="agent" value="sales"', form)
        self.assertIn('name="token" value="t"', form)
        self.assertIn('name="back" value="/new/build?agent=sales"', form)
        self.assertLess(page.index("Practice matches"), page.index('action="/tryagain"'))
        self.assertNotIn('action="/tryagain"', self.page(token=None))

    def test_no_button_with_no_lost_match(self):
        (self.dir / "arena-sales-r1.json").write_text(json.dumps(
            {"agent": "sales", "kind": "arena_rounds", "at": NOW, "run": "r1", "line": "x", "lost": [],
             "gate_won": 4, "gate_played": 4, "needs": 3}), encoding="utf-8")
        self.assertNotIn("Try again", self.page())

    def test_while_a_try_runs(self):
        self.stuck()
        self.m._trying.add("sales")
        page = self.page()
        self.assertIn("Trying again...", page)
        self.assertNotIn('action="/tryagain"', page)

    def test_tiles_say_won_again_or_still_lost(self):
        self.stuck()
        self.m.try_again("sales")
        page = self.page()
        tiles = page.split('class="tiles"')[1].split("</section>")[0]
        won = tiles.split('class="tile won"')[1].split("</article>")[0]
        lost = tiles.split('class="tile lost"')[1].split("</article>")[0]
        self.assertIn("Won again", won)
        self.assertNotIn("Correct this", won)
        self.assertIn("Still lost", lost)
        self.assertIn("Correct this", lost)
        self.assertEqual(tiles.count("<article"), 2)  # one tile a retried case

    def test_a_built_agent_shows_it_greyed_out(self):
        m = self.m
        m.read_arena = lambda: ({"stock_watch": {"file": "arena-stock_watch-1.json", "at": NOW, "line": "",
                                                 "lost": [{"card": "c1", "why": "x", "turn": 1, "who": "agent",
                                                           "text": "Hello"}], "rounds": [], "kind": "arena_rounds",
                                                 "gate_won": None, "gate_played": None, "retry": None}}, [])
        page = pages.build(m, "stock_watch", {"token": "t", "q": "", "day": None, "path": "/new/build", "m": m,
                                              "now": None})
        self.assertIn('title="Not built for this agent yet"', page)
        self.assertNotIn('action="/tryagain"', page)

    def test_back_returns_to_the_agents_arena_screen(self):
        p = pages.Pages(self.m)
        self.assertEqual(p.back("/new/build?agent=sales"), "/new/build?agent=sales")
        self.assertEqual(p.back("/new/build?agent=Bad-Name"), "/new/build")
        self.assertEqual(p.back("/agents?agent=sales"), "/agents")


class OverTheServer(Base):
    def setUp(self):
        super().setUp()
        self.p = pages.Pages(self.m)
        self.server = mo.make_server(self.m, port=0, pages=self.p)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(5)
        self.addCleanup(stop)

    def post(self, token, origin=True):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{self.port}"
        body = urllib.parse.urlencode([("token", token), ("back", "/new/build?agent=sales"),
                                       ("agent", "sales")]).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/tryagain", data=body, method="POST",
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, ""

    def test_post_needs_the_token_and_the_origin(self):
        self.stuck()
        self.assertEqual(self.post("wrong")[0], 403)
        self.assertEqual(self.post(self.server.token, origin=False)[0], 403)
        self.assertEqual(list(self.dir.glob("arena-sales-retry-*.json")), [])
        status, page = self.post(self.server.token)
        self.assertEqual(status, 200)
        self.assertIn(retry.STARTED, page)  # the flash, on the agent's Arena screen
        self.assertIn("Won again", page)
        self.assertEqual(len(list(self.dir.glob("arena-sales-retry-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
