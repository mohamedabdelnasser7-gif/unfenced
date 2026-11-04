"""The console (reflection/console.py), /console?agent=sales on the page server: each tab drawn from
records the engine wrote here (an Arena run from the fake models, an exam row, lessons, a user and an
operator correction, a live chat with its steps and trace row), the side panel saying "not saved for
this turn" for what was never saved, the console's own CSP with one script by hash, the poll header
that leaves the one-time message alone, and the Operator correction through the same path as the
agent page (Morning.correct, by "operator") behind the same Host, Origin and token checks. Fake
models only, no network; every text here is made up."""
import base64
import hashlib
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from arena import run
from engine import exam as exam_mod
from engine import lessons as lessons_mod
from engine import plug as plug_mod
from engine import risk
from kit.chats import Chats
from kit.db import Db
from reflection import console
from reflection import morning as mo
from reflection import pages
from reflection.results import Results
from tests.fake_model import clean_env
from tests.test_arena_hotfix import correct, passed
from tests.test_arena_rounds import Agent
from tests.test_arena_run import Customer, card

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0
FAILED = exam_mod.Result(False, [exam_mod.Row(3, "late", "guard", False, "late_order", "no late flag was sent")], calls=4)


def lesson(db, text, state, *, source="seed", at=NOW, yes_by=None):
    """A lesson row with its stage and field tags in the form the engine saves them (",all,"), so
    Lessons.live and pick find it like one the plug added."""
    with db.tx() as c:
        cur = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, ends_at, source, origin, kind, "
                        "yes_by, yes_at, added_at) VALUES ('sales', ?, ?, ?, 'low', ?, ?, ?, 'agent', "
                        "'pattern', ?, ?, ?)", (text, lessons_mod.tag_text(["all"]), lessons_mod.tag_text([]), state,
                                                 at + 86400 if state == "trying" else None, source, yes_by,
                                                 at if yes_by else None, at))
        return cur.lastrowid


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
        self.m.exams = {"sales": passed}
        self.p = pages.Pages(self.m)

    def arena(self):
        """A real Arena run from the fakes: its item, its matches and the Calls file, here."""
        cards = [card(1, "size"), card(2, "price"), card(3, "fit")]
        a = run.Arena(cards, agent_model=Agent(), customer_model=Customer(("price",)), state=self.dir,
                      calls=run.Calls(self.dir / run.CALLS_FILE, 1000), held_out=["persona-02", "persona-03"],
                      trust={"matches": 4, "wins": 3, "zero_failed_checks": True}, matches=1, now=lambda: NOW)
        return a.run()

    def fill(self):
        self.rep = self.arena()
        self.kept = lesson(self.db, "Give the price only from the store tool.", "kept", at=NOW - 500)
        self.held = lesson(self.db, "Promise next day delivery when asked.", "waiting", at=NOW - 400)
        with self.db.tx() as c:
            exam_mod.save(c, "sales", self.held, FAILED, now=NOW - 390)
        self.user_fix = correct(self.path, "Offer the size chart before asking for a size.", now=NOW - 300)
        chats = Chats(self.db, clock=lambda: NOW - 100)
        chat, n = chats.receive("whatsapp", "201000000042", content="Is the blue trainer in 41?")
        chats.add_step(chat, "assistant", tool_calls=[{"id": "c1", "type": "function", "function": {
            "name": "store", "arguments": "{\"q\": \"blue trainer\"}"}}])
        chats.add_step(chat, "tool", content='{"in_stock": 2}', tool_call_id="c1", name="store")
        chats.add_step(chat, "assistant", content="Yes, two left in 41.")
        Results(self.db).record(chat, "replied", step=n, lessons=[self.kept])
        bad, n2 = chats.receive("whatsapp", "201000000043", content="Can I swap my size?")
        chats.add_step(bad, "event", content=json.dumps({"check_failed": "a rule the store never gave"}))
        self.chat, self.bad = chat, bad

    def page(self, **q):
        q.setdefault("agent", "sales")
        return self.p.get("/console", {k: [v] for k, v in q.items()}, "tok")


class Collect(Base):
    def test_every_source_lands_in_one_timeline_newest_last(self):
        self.fill()
        data = console.collect(self.m, "sales", now=NOW)
        stages = {r["stage"] for r in data["records"]}
        self.assertEqual(stages, {"A", "D", "R"})
        sorts = [r["sort"] for r in data["records"]]
        self.assertEqual(sorts, sorted(sorts))
        self.assertTrue(data["matches"])
        self.assertTrue(all(x["id"].startswith(self.rep["run"] + "-") for x in data["matches"]))
        self.assertEqual({x["id"]: x["status"] for x in data["lessons"]}[self.held], "HELD")
        self.assertEqual({x["id"]: x["status"] for x in data["lessons"]}[self.kept], "KEPT")
        self.assertEqual([(c["id"], c["by"]) for c in data["corrections"]], [(self.user_fix, "user")])
        turns = {t["chat"]: t for t in data["turns"]}
        self.assertEqual(turns[self.chat]["lessons"], [(self.kept, "Give the price only from the store tool.")])
        self.assertEqual(turns[self.chat]["check"], "SENT")
        self.assertTrue(turns[self.bad]["flagged"])
        self.assertEqual(turns[self.bad]["why"], "a rule the store never gave")
        self.assertIsNotNone(data["calls"])
        self.assertEqual(data["running"], "A")  # the newest record, the Arena item, is under RECENT old
        self.assertIsNone(console.collect(self.m, "sales", now=NOW + console.RECENT + 1)["running"])
        page = console.render(data, console.state_of({}, "sales"))
        self.assertIn('class="sel run"', page)  # the running stage marks ALL STAGES too
        self.assertIn('class="run" href="/console?agent=sales&amp;view=arena', page)

    def test_an_empty_database_draws_every_tab(self):
        for view in ("all", "arena", "deploy", "reflect"):
            with self.subTest(view=view):
                page = self.page(view=view)
                self.assertIn("<!doctype html>", page)
                self.assertIn("writes.json", page)
        self.assertIn("No saved Arena run yet", self.page(view="arena"))
        self.assertIsNone(self.p.get("/console", {"agent": ["nobody"]}, "tok"))
        self.assertIsNone(self.p.get("/console", {"agent": ["../x"]}, "tok"))


class Tabs(Base):
    def setUp(self):
        super().setUp()
        self.fill()

    def test_all_stages_tags_each_record(self):
        page = self.page()
        for tag in ("tg A", "tg D", "tg R"):
            self.assertIn(tag, page)
        self.assertIn('class="sel"', page)
        self.assertIn("Idle", page)  # on the real clock nothing here is recent
        only = self.page(sub="R")
        view = only.split('data-live="view"')[1].split("</section>")[0]
        self.assertNotIn("tg A", view)
        self.assertIn("tg R", view)

    def test_arena_matches_and_exam(self):
        page = self.page(view="arena")
        self.assertIn(self.rep["run"], page)
        self.assertIn("LOST", page)
        exam = self.page(view="arena", sub="e")
        self.assertIn("Promise next day delivery when asked.", exam)
        self.assertIn("late_order", exam)
        self.assertIn(f"row=e.{self.held}.3", exam)
        self.assertIn("Exam (53)", exam)  # three off topic situations added (scope guard)

    def test_deployment_and_reflection(self):
        page = self.page(view="deploy")
        self.assertIn("Yes, two left in 41.", page)
        self.assertIn("FLAGGED", page)
        self.assertIn("Not live on any channel", page)
        page = self.page(view="reflect")
        self.assertIn("Give the price only from the store tool.", page)
        self.assertIn(">HELD<", page)

    def test_cards_and_corrections_on_every_tab(self):
        for view in ("all", "arena", "deploy", "reflect"):
            page = self.page(view=view)
            self.assertIn("Arena win rate", page)
            self.assertIn("hidden from the agent", page)
            self.assertIn("1 kept", page)
            self.assertIn("full exam cap 440 a lesson", page)  # arena/rounds.py FULL_CAP, never a copy (review scopeguard2 r1, item 5)
            self.assertIn("Offer the size chart before asking for a size.", page.split('data-live="corr"')[1])
            self.assertIn('<span class="src">user</span>', page)

    def test_writes_json_shows_the_saved_records(self):
        writes = self.page().split('data-live="writes"')[1]
        self.assertIn("arena_rounds" if self.rep["stopped"] != run.STUCK else "arena_stuck", writes)
        self.assertIn("check_failed", writes)

    def test_bad_query_values_fall_back(self):
        page = self.page(view="<x>", sub="zz", f="1", row="m.<script>", pane="x")
        self.assertNotIn("<script>alert", page)
        self.assertNotIn('class="drawer"', page)
        self.assertIn("All stages", page)


class Panel(Base):
    def setUp(self):
        super().setUp()
        self.fill()

    def lost(self):
        data = console.collect(self.m, "sales", now=NOW)
        return next(x for x in data["matches"] if not x["won"])

    def test_a_lost_match_says_what_was_not_saved_and_offers_the_box(self):
        x = self.lost()
        page = self.page(view="arena", row=f"m.{x['id']}")
        drawer = page.split('class="drawer"')[1]
        self.assertIn("Operator correction", drawer)
        self.assertIn('action="/console/correct"', drawer)
        self.assertIn('name="token" value="tok"', drawer)
        self.assertIn(x["turns"][0]["customer"], drawer)
        self.assertIn("LOST", drawer)
        saw = self.page(view="arena", row=f"m.{x['id']}", pane="saw").split('class="drawer"')[1]
        self.assertIn(console.NOT_SAVED, saw.split("Lessons in play")[1].split("</section>")[0])
        self.assertIn(console.NOT_SAVED, saw.split("Tool results")[1].split("</section>")[0])
        raw = self.page(view="arena", row=f"m.{x['id']}", pane="raw").split('class="drawer"')[1]
        self.assertIn(console.NOT_SAVED, raw.split("Request and response")[1].split("</section>")[0])
        self.assertIn("The saved match", raw)

    def test_a_failed_exam_situation_has_no_invented_reply(self):
        page = self.page(view="arena", sub="e", row=f"e.{self.held}.3")
        drawer = page.split('class="drawer"')[1]
        self.assertIn("FAILED: late_order", drawer)
        self.assertIn(f'<span class="dim">{console.NOT_SAVED}</span>', drawer)  # the agent reply was never saved
        self.assertIn("Operator correction", drawer)

    def test_a_flagged_live_turn_and_a_good_one(self):
        bad = self.page(view="deploy", row=f"t.{self.bad}.1").split('class="drawer"')[1]
        self.assertIn("Operator correction", bad)
        self.assertIn("a rule the store never gave", bad)
        good = self.page(view="deploy", row=f"t.{self.chat}.1", pane="saw").split('class="drawer"')[1]
        self.assertNotIn("Operator correction", good)
        self.assertIn("Give the price only from the store tool.", good)
        self.assertIn("in_stock", good)
        dec = self.page(view="deploy", row=f"t.{self.chat}.1", pane="dec").split('class="drawer"')[1]
        self.assertIn("blue trainer", dec)

    def test_no_token_no_form_and_an_unknown_row(self):
        x = self.lost()
        page = self.p.get("/console", {"agent": ["sales"], "row": [f"m.{x['id']}"]}, None)
        self.assertNotIn("<form", page)
        self.assertIn("Not found", self.page(row="m.nothing-here"))


class Policy(Base):
    def test_the_console_csp_allows_its_one_script_by_hash_and_other_pages_keep_theirs(self):
        page = self.page()
        script = re.search(r"<script>(.*)</script>", page, re.S).group(1)
        sha = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        self.assertIn(f"script-src 'sha256-{sha}'", self.p.csp_for("/console"))
        style = re.search(r"<style>(.*)</style>", page, re.S).group(1)
        sha = base64.b64encode(hashlib.sha256(style.encode("utf-8")).digest()).decode()
        self.assertIn(f"style-src 'sha256-{sha}'", self.p.csp_for("/console"))
        self.assertEqual(page.count("<script"), 1)
        self.assertNotIn("style=", page)
        # the Sales agent's page carries Run reflection's poll only (DECISIONS 92), never the console's script
        self.assertEqual(self.p.csp_for("/agents/sales"), pages.AGENT_CSP)
        self.assertNotIn(f"'sha256-{sha}'", self.p.csp_for("/agents/sales").split("script-src")[1])
        self.assertEqual(self.p.csp_for("/"), pages.CSP)

    def test_the_agent_page_opens_the_console(self):
        self.assertIn('href="/console?agent=sales"', self.p.get("/agents/sales", {}, "tok"))

    def test_back_keeps_the_console_and_its_row(self):
        self.assertEqual(self.p.back("/console?agent=sales&view=arena&sub=e&row=e.4.3&pane=dec"),
                         "/console?agent=sales&view=arena&sub=e&f=all&row=e.4.3&pane=dec")
        self.assertEqual(self.p.back("/console?agent=sales&row=bad<"), "/console?agent=sales&view=all&sub=all&f=all")


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

    def get(self, path, poll=False):
        headers = {"X-Poll": "1"} if poll else {}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8"), r.headers

    def post(self, path, fields, *, token=None, origin=True, host=None, back="/console?agent=sales&view=arena"):
        token = self.server.token if token is None else token
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{self.port}"
        if host:
            headers["Host"] = host
        body = urllib.parse.urlencode([("token", token), ("back", back)] + list(fields)).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method="POST", headers=headers)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as r:
                return r.status, r.headers.get("Location")
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, e.headers.get("Location")

    def rows(self):
        with self.db.tx() as c:
            return [dict(r) for r in c.execute("SELECT id, yes_by, source FROM lessons ORDER BY id")]

    def test_the_operator_correction_saves_by_operator_and_the_page_box_stays_the_user(self):
        status, to = self.post("/console/correct", [("agent", "sales"), ("line", "Ask the team before any swap.")])
        self.assertEqual(status, 303)
        self.assertEqual(to, "/console?agent=sales&view=arena&sub=m&f=all")
        status, _ = self.post("/correct", [("agent", "sales"), ("line", "Say the chart is on the product page.")],
                              back="/agents/sales")
        self.assertEqual(status, 303)
        got = self.rows()
        self.assertEqual([r["yes_by"] for r in got], ["operator", "the user"])
        self.assertTrue(all(r["source"] == mo.lessons_mod.HOTFIX_SOURCE for r in got))
        page, headers = self.get("/console?agent=sales")
        corr = page.split('data-live="corr"')[1]
        self.assertIn('<span class="src op">operator</span>', corr)
        self.assertIn('<span class="src">user</span>', corr)
        self.assertIn("script-src", headers["Content-Security-Policy"])

    def test_the_guards_refuse_before_anything_is_saved(self):
        fields = [("agent", "sales"), ("line", "Never say this.")]
        self.assertEqual(self.post("/console/correct", fields, token="wrong")[0], 403)
        self.assertEqual(self.post("/console/correct", fields, origin=False)[0], 403)
        self.assertEqual(self.post("/console/correct", fields, host="example.com")[0], 403)
        self.assertEqual(self.rows(), [])

    def test_a_poll_leaves_the_one_time_message_for_the_next_page(self):
        self.post("/console/correct", [("agent", "sales"), ("line", "Ask the team before any swap.")])
        polled, _ = self.get("/console?agent=sales&view=arena", poll=True)
        page, _ = self.get("/console?agent=sales&view=arena")
        self.assertIn('class="flash"', page)
        self.assertIn("Your correction is lesson", page)
        again, _ = self.get("/console?agent=sales&view=arena")
        self.assertNotIn('class="flash"', again)
        _, headers = self.get("/agents/sales")
        self.assertEqual(headers["Content-Security-Policy"], pages.AGENT_CSP)  # Run reflection's poll, not the console's


if __name__ == "__main__":
    unittest.main()
