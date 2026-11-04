"""Any agent, not only the stock one (2026-11-03): the judge's unreadable answer, sample data made at
Build and added by the user, the Run the Arena button and the card's wording. Fake models only, no
network, no real data."""
import json
import unittest

from arena import practice, run, tag
from tests.fake_model import say
import tests.test_arena_practice as tap
from tests.test_arena_practice import World

GOOD = json.dumps({"reached": True, "broke_never": False, "turn": 1, "why": "a clear answer"})


def judge_script(*answers):
    """A judge that gives each answer in turn, then GOOD."""
    left = list(answers)
    return lambda messages: say(left.pop(0) if left else GOOD)


class UnreadableJudge(tap.Base):
    def test_the_rule_is_the_taggers_three_in_a_row(self):
        self.assertEqual(practice.UNREAD_IN_A_ROW, tag.MAX_FAILS)

    def test_one_unreadable_answer_is_asked_again_and_the_match_is_judged(self):
        world = World(judge=judge_script("I think it went well."))
        code, rep = self.main("--matches", "2", "--json", world=world)
        self.assertEqual((code, rep["stopped"]), (0, run.PASSED), self.err)
        self.assertNotIn("unjudged", rep["rounds"][0]["training"])
        self.assertEqual(rep["rounds"][0]["training"]["played"], 2)

    def test_a_match_read_twice_and_still_unreadable_is_unjudged_and_the_run_goes_on(self):
        world = World(judge=judge_script("no json", "still no json"))
        code, rep = self.main("--matches", "2", "--json", world=world)
        self.assertNotEqual(rep["stopped"], run.MODEL_ERROR)
        train = rep["rounds"][0]["training"]
        self.assertEqual((train["unjudged"], train["played"]), (1, 1))
        self.assertEqual(len(self.matches()), 1 + rep["rounds"][0]["gate"]["played"])
        self.assertTrue(all("won" in m for m in self.matches()))

    def test_three_unjudged_matches_in_a_row_stop_the_run(self):
        world = World(judge=lambda messages: say("never json"))
        code, rep = self.main("--matches", "4", "--json", world=world)
        self.assertEqual((code, rep["stopped"]), (1, run.MODEL_ERROR))
        self.assertIn("3 matches in a row", rep["error"])
        self.assertEqual(world.calls["judge"], 6)  # each match asked twice
        self.assertEqual(self.matches(), [])


if __name__ == "__main__":
    unittest.main()


class CardWording(unittest.TestCase):
    """The build page card: each case line has its label, then the model's words, never run together or
    with the label's word twice."""

    def card(self, **case):
        base = {"input": "daily morning time trigger", "starts": "agent", "output": "a stock report",
                "ends": "when the morning report is sent"}
        return {"name": "Stock tracker", "does": "Reports stock.", "case": dict(base, **case), "good": "A clear report.",
                "bad": "No report.", "never": [], "needs": []}

    def test_labels_and_values_are_apart_and_no_word_shows_twice(self):
        from reflection import pages
        html = pages.plan_card(self.card())
        self.assertIn("<b>It is over:</b> when the morning report is sent", html)
        self.assertNotIn("when when", html.lower())
        self.assertIn("<b>Who starts:</b> The agent writes first", html)
        self.assertNotIn("Starts</b> The", html)
        self.assertIn("<b>Comes in:</b> daily morning time trigger", html)
        self.assertNotIn("Arrives daily", html)

    def test_the_labels_own_words_are_cut_from_the_models_line(self):
        from reflection import pages
        html = pages.plan_card(self.card(ends="Over when the report is sent", input="Arrives: a ticket"))
        self.assertIn("<b>It is over:</b> when the report is sent", html)
        self.assertIn("<b>Comes in:</b> a ticket", html)

    def test_the_card_writer_asks_for_parts_that_read_under_a_label(self):
        from reflection import quickstart as qs
        self.assertIn('starts with "when"', qs.CARD_PROMPT)
        self.assertIn("never start it with the label's words", qs.CARD_PROMPT)


# ---- sample data made at Build, read by the agent's tools, the practice customer and the judge ----

import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

from kit import sample, turn  # noqa: E402
from kit.tools import data as data_tool, store  # noqa: E402
from reflection import morning as mo, pages, quickstart as qs  # noqa: E402
from tests.fake_model import FakeModel  # noqa: E402
import tests.test_quickstart as tq  # noqa: E402
from tests.test_quickstart import card_reply, exam_reply, plug_reply  # noqa: E402

PRODUCTS = [{"title": "Blue Runner", "price": 1200, "stock": 2, "size": "42"},
            {"title": "Blue Runner", "price": 1200, "stock": 30, "size": "43"},
            {"title": "Trail Cap", "price": 300, "stock": 0}]


def sample_reply(rows=None, what="products with stock counts"):
    return say(json.dumps({"what": what, "rows": PRODUCTS if rows is None else rows}))


class PageCase(unittest.TestCase):
    """The setUp of tests/test_quickstart.py QuickStartPage, without its tests."""
    setUp, page, send, build, get = (tq.QuickStartPage.setUp, tq.QuickStartPage.page, tq.QuickStartPage.send,
                                     tq.QuickStartPage.build, tq.QuickStartPage.get)


class BuildMakesSampleData(PageCase):
    def built(self, *after):
        self.page(card_reply(), plug_reply(), exam_reply(), *after)
        self.send("an agent for my stock")
        said = self.build()
        self.assertTrue(said.startswith("Built Stock watcher"), said)
        return self.folder / "agents" / "stock_watcher"

    def test_one_call_writes_made_up_rows_that_fit_the_card_into_the_agents_folder(self):
        folder = self.built(sample_reply())
        got = sample.read(folder)
        self.assertEqual(got["what"], "products with stock counts")
        self.assertEqual([r["by"] for r in got["rows"]], [sample.MADE_UP] * 3)
        ask = self.model.calls[-1]["messages"]
        self.assertIn("made-up dataset", ask[0]["content"])
        self.assertIn("Checks stock every morning", ask[1]["content"])  # the card is what it fits
        self.assertEqual(self.p.run.done["data"], "Sample data made for this agent: products with stock counts, 3 made up.")

    def test_an_answer_with_no_rows_builds_the_agent_with_none(self):
        folder = self.built(say("no rows today"))
        self.assertFalse((folder / sample.FILE).exists())
        self.assertTrue((folder / "plug.json").exists())
        self.assertEqual(self.p.run.done["data"], qs.NO_SAMPLE)

    def test_rows_and_values_are_capped_and_plain(self):
        rows = [{"title": f"<b>Item</b> {n}", "note": "x" * 400, "nested": {"a": 1}} for n in range(50)]
        folder = self.built(sample_reply(rows))
        got = sample.read(folder)
        self.assertEqual(len(got["rows"]), sample.MAX_MADE)
        one = got["rows"][0]["row"]
        self.assertEqual(one["title"], "bItem/b 0")
        self.assertEqual(len(one["note"]), sample.MAX_CELL)
        self.assertEqual(one["nested"], '{"a": 1}')


class TheAgentReadsIt(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.folder = Path(d.name).resolve() / "agents" / "stock_watch"
        shutil.copytree(tap.FIXTURE, self.folder)
        sample.write(self.folder, sample.made("products with stock counts", PRODUCTS))
        self.env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                if not k.startswith("SHOPIFY")}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        store._cache.update(at=0.0, items=None)
        self.addCleanup(store._cache.update, at=0.0, items=None)

    def test_a_folder_with_sample_data_offers_the_data_tool_and_it_returns_the_marked_rows(self):
        agent = turn.load(self.folder)
        self.assertIn(turn.DATA_TOOL, agent.tools)
        ctx = mock.Mock(data=agent.data)
        got = data_tool.run({"query": "trail"}, ctx)
        self.assertEqual([r["title"] for r in got["rows"]], ["Trail Cap"])
        self.assertEqual(got["rows"][0]["source"], "made up")
        self.assertFalse(data_tool.run({}, mock.Mock(data=None))["ok"])

    def test_a_folder_with_none_offers_no_data_tool(self):
        (self.folder / sample.FILE).unlink()
        self.assertNotIn(turn.DATA_TOOL, turn.load(self.folder).tools)

    def test_the_store_reads_the_sample_products_as_levels_with_no_keys_and_real_keys_win(self):
        items = sample.store_items(sample.read(self.folder))
        token = store.SAMPLE.set(items)
        try:
            got = store.run({"query": "runner"}, None)["items"]
            self.assertEqual([v["stock"] for v in got[0]["variants"]], ["few left", "in stock"])
            self.assertEqual(store.catalogue()[1]["variants"][0]["stock"], "out")
            with mock.patch.dict(os.environ, {"SHOPIFY_STORE": "x.myshopify.com", "SHOPIFY_TOKEN": "t"}), \
                    mock.patch.object(store, "_from_shopify", return_value=[{"title": "Real item"}]):
                store._cache.update(at=0.0, items=None)
                self.assertEqual(store.catalogue(), [{"title": "Real item"}])
        finally:
            store.SAMPLE.reset(token)
        store._cache.update(at=0.0, items=None)
        self.assertNotIn("Blue Runner", json.dumps(store.catalogue()))  # outside the turn: the demo catalogue

    def test_a_turn_hands_the_store_its_sample_products(self):
        from kit.chats import Chats
        from kit.db import Db
        from tests.fake_model import tool_call
        agent = turn.load(self.folder)
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "c1")
        model = FakeModel(tool_call("store", {"query": "cap"}), say("The Trail Cap is out."))
        turn.turn(agent, "Is the cap in stock?", chats=chats, chat_id=cid, model=model, send=lambda *a: None,
                  customer_id="c1")
        tool_out = [m for m in model.calls[1]["messages"] if m["role"] == "tool"][0]["content"]
        self.assertIn("Trail Cap", tool_out)
        self.assertIn('"out"', tool_out)
        self.assertIsNone(store.SAMPLE.get())


class PracticeSeesTheSameData(tap.Base):
    def setUp(self):
        super().setUp()
        sample.write(self.folder, sample.made("products with stock counts", PRODUCTS))

    def test_the_customer_and_the_judge_read_the_rows_the_agent_reads(self):
        seen = []
        world = World(customer=lambda messages: seen.append(messages[0]["content"]) or say(
            "Is the cap in stock?" if len(messages) == 2 else "Thanks " + practice.DONE))
        code, rep = self.main("--quick", "--json", world=world)
        self.assertEqual(code, 0, self.err)
        self.assertIn(practice.DATA_LINE, seen[0])
        self.assertIn("Trail Cap", seen[0])
        self.assertEqual(world.judged[0]["data"][2]["title"], "Trail Cap")
        self.assertIn(turn.DATA_TOOL, rep["tools"])


# ---- the card shows the sample data, and the user can add more (build page, Overview, /agents/data) ----

import dataclasses  # noqa: E402
import http.client  # noqa: E402
import urllib.parse  # noqa: E402
import threading  # noqa: E402

from channels import whatsapp  # noqa: E402
from kit import tools as kit_tools  # noqa: E402
from tests.test_late_marks import multipart  # noqa: E402
from tests.test_quickstart import no_keys  # noqa: E402

CARD_LINE = "Sample data made for this agent: products with stock counts, 3 made up."
WA_SET = dict.fromkeys(whatsapp.REQUIRED_ENV, "fake")      # every WhatsApp key set, to a fake value
STORE_SET = dict.fromkeys(("SHOPIFY_STORE", "SHOPIFY_TOKEN"), "fake")  # both Shopify keys, fake values


class CardShowsSampleData(PageCase):
    def setUp(self):
        PageCase.setUp(self)
        self.m.db_path = str(self.folder / "ascent.db")  # the live page, so the built agent joins it
        keys = no_keys()
        keys.start()
        self.addCleanup(keys.stop)

    def built(self):
        self.page(card_reply(), plug_reply(), exam_reply(), sample_reply())
        self.send("an agent for my stock")
        before = self.get()
        self.assertNotIn(f'action="{mo.DATA_PATH}"', before)  # no add box before it is built
        self.assertNotIn("Sample data made", before)
        self.assertTrue(self.build().startswith("Built Stock watcher"))
        return self.get()

    def test_the_card_says_it_made_sample_data_and_the_build_page_takes_more(self):
        page = self.built()
        self.assertIn(CARD_LINE, page)
        form = page.split(f'action="{mo.DATA_PATH}"')[1].split("</form>")[0]
        for part in ('enctype="multipart/form-data"', 'name="text"', 'type="file" name="file"',
                     'name="agent" value="stock_watcher"', pages.DATA_NOTE):
            self.assertIn(part, form)

    def test_overview_shows_the_sample_data_and_the_add_box(self):
        self.built()
        page = self.p.get("/agents/stock_watcher", {}, "t")
        self.assertIn('<h3 id="sd-h">Sample data</h3>', page)
        self.assertIn(CARD_LINE, page)
        self.assertIn(f'action="{mo.DATA_PATH}"', page)
        self.assertNotIn(f'action="{mo.DATA_PATH}"', self.p.get("/agents/stock_watcher", {}, ""))  # no token, no box
        self.assertNotIn("Sample data", self.p.get("/agents/sales", {}, "t"))  # only an agent made here

    def test_a_store_need_is_sample_data_with_no_keys_and_connected_with_them(self):
        page = self.built()
        need = page.split("Your store&#x27;s stock")[1].split("</small>")[0]
        self.assertIn(pages.STORE_SAMPLE, need)
        self.assertNotIn("Connected", need)
        with mock.patch.dict(os.environ, STORE_SET):
            need = self.get().split("Your store&#x27;s stock")[1].split("</small>")[0]
        self.assertIn("Connected: Store", need)

    def test_a_whatsapp_need_is_connected_only_with_its_keys(self):
        self.page(card_reply(needs=[{"what": "Customer chats", "tool": "whatsapp"}]))
        self.send("an agent for my customer chats")

        def need():
            return self.get().split("Customer chats")[1].split("</small>")[0]
        self.assertIn("Not connected yet", need())
        self.assertNotIn("Connected: WhatsApp", need())
        one_missing = dict(WA_SET)
        one_missing[whatsapp.REQUIRED_ENV[0]] = ""
        with mock.patch.dict(os.environ, one_missing):
            self.assertNotIn("Connected: WhatsApp", need())
        with mock.patch.dict(os.environ, WA_SET):
            self.assertIn("Connected: WhatsApp", need())


class AddData(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.folder = self.dir / "agents" / "stock_watch"
        shutil.copytree(tap.FIXTURE, self.folder)
        sample.write(self.folder, sample.made("products with stock counts", PRODUCTS))
        from engine import plug as plug_mod
        from kit.db import Db
        self.db = Db(str(self.dir / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "sales" / "plug.json")], reports=self.dir,
                            built={"stock_watch"}, db_path=self.dir / "ascent.db")

    def rows(self):
        return sample.read(self.folder)["rows"]

    def test_pasted_csv_json_and_plain_lines_and_a_file_are_added_as_the_users(self):
        said = self.m.add_data("stock_watch", "name,price,stock\nRed Cap,250,4\nGrey Scarf,90,0\n")
        self.assertEqual(said, "Added 2 rows to its sample data. Its next practice reads them.")
        self.m.add_data("stock_watch", json.dumps([{"title": "Blue Bag", "price": 800}]))
        self.assertEqual(self.m.add_data("stock_watch", "call Sara back on Sunday"),
                         "Added 1 row to its sample data. Its next practice reads them.")
        self.m.add_data("stock_watch", "", b"title,price\nGreen Hat,150\n")
        rows = self.rows()
        self.assertEqual([r["by"] for r in rows], [sample.MADE_UP] * 3 + [sample.USER] * 5)
        self.assertEqual(rows[3]["row"], {"name": "Red Cap", "price": "250", "stock": "4"})
        self.assertEqual(rows[5]["row"], {"title": "Blue Bag", "price": 800})
        self.assertEqual(rows[6]["row"], {"text": "call Sara back on Sunday"})
        self.assertEqual(rows[7]["row"], {"title": "Green Hat", "price": "150"})
        self.assertEqual(sample.words(sample.read(self.folder)),
                         "Sample data made for this agent: products with stock counts, 3 made up, 5 added by you.")
        self.assertEqual(sample.rows_of(sample.read(self.folder))[-1]["source"], "added by the user")

    def test_markup_is_stripped_and_nothing_is_run(self):
        with mock.patch("builtins.eval") as ev, mock.patch("builtins.exec") as ex:
            self.m.add_data("stock_watch", '<script>alert(1)</script>\n__import__("os").system("x")')
        ev.assert_not_called()
        ex.assert_not_called()
        got = [r["row"]["text"] for r in self.rows()[3:]]
        self.assertEqual(got, ["scriptalert(1)/script", '__import__("os").system("x")'])

    def test_refusals_save_nothing(self):
        before = (self.folder / sample.FILE).read_bytes()
        cases = [("sales", "a,b\n1,2", b""), ("stock_watch", "", b""), ("stock_watch", "  \n ", b""),
                 ("stock_watch", "\n".join(f"row {n}" for n in range(sample.MAX_ADD + 1)), b""),
                 ("stock_watch", "x" * (sample.MAX_TEXT + 1), b""), ("stock_watch", "", b"\xff\xfe\x00bad"),
                 ("stock_watch", "", b"a" * (sample.MAX_UPLOAD + 1)), ("stock_watch", "[{broken", b"")]
        for agent, text, raw in cases:
            with self.subTest(agent=agent, text=text[:20], raw=raw[:10]):
                with self.assertRaises(mo.Refused):
                    self.m.add_data(agent, text, raw)
        self.assertEqual((self.folder / sample.FILE).read_bytes(), before)
        with self.assertRaises(mo.Refused):  # the same folder, but the page does not count it as made here
            mo.Morning(self.db, [], built=(), db_path=self.dir / "ascent.db").add_data("stock_watch", "a")


class DataPost(AddData):
    def serve(self, two_tabs=True):
        server = mo.make_server(self.m, port=0, pages=pages.Pages(self.m) if two_tabs else None)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(5)
        self.addCleanup(stop)
        return server

    def post(self, server, body, kind, length=None):
        here = f"127.0.0.1:{server.server_address[1]}"
        headers = {"Host": here, "Content-Type": kind, "Origin": f"http://{here}"}
        if length is not None:
            headers["Content-Length"] = str(length)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            conn.request("POST", mo.DATA_PATH, body, headers)
            r = conn.getresponse()
            r.read()
            return r.status
        finally:
            conn.close()

    def test_the_token_the_size_cap_and_the_form_are_checked(self):
        server = self.serve()
        before = (self.folder / sample.FILE).read_bytes()
        good = [("agent", "stock_watch"), ("text", "Red Cap\nGrey Scarf")]
        cases = [(multipart(good), 403), (multipart([("token", "guess")] + good), 403),
                 (multipart([("token", server.token)] + good + [("other", "x")]), 400),
                 (multipart([("token", server.token), ("token", server.token)] + good), 400),
                 ((b"agent=stock_watch&text=Red", "application/x-www-form-urlencoded"), 415)]
        for (body, kind), want in cases:
            with self.subTest(want=want, body=body[:60]):
                self.assertEqual(self.post(server, body, kind), want)
        body, kind = multipart([("token", server.token)] + good)
        self.assertEqual(self.post(server, body, kind, length=mo.MAX_DATA_POST + 1), 413)
        self.assertEqual((self.folder / sample.FILE).read_bytes(), before)
        self.assertEqual(self.post(server, body, kind), 303)
        self.assertEqual([r["row"]["text"] for r in self.rows()[3:]], ["Red Cap", "Grey Scarf"])
        body, kind = multipart([("token", server.token), ("agent", "stock_watch"), ("file", b"title,price\nHat,90\n")])
        self.assertEqual(self.post(server, body, kind), 303)
        self.assertEqual(self.rows()[-1], {"by": sample.USER, "row": {"title": "Hat", "price": "90"}})

    def test_the_one_page_server_has_no_data_post(self):
        server = self.serve(two_tabs=False)
        body, kind = multipart([("token", server.token), ("agent", "stock_watch"), ("text", "Red Cap")])
        self.assertEqual(self.post(server, body, kind), 404)


class DataAmountsPass(TheAgentReadsIt):
    def test_the_data_tool_is_on_the_list_whose_amounts_the_full_check_accepts(self):
        self.assertIn(data_tool.NAME, kit_tools.AMOUNT_TOOLS)
        from kit.chats import Chats
        from kit.db import Db
        from tests.fake_model import tool_call
        sample.write(self.folder, sample.made("open tickets", [{"ticket": "late parcel", "fee": 175}]))
        agent = dataclasses.replace(turn.load(self.folder), full_check=True)
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "c1")
        sent = []
        model = FakeModel(tool_call("data", {"query": "parcel"}), say("The fee for the late parcel is 175 EGP."))
        got = turn.turn(agent, "What is the fee for the late parcel?", chats=chats, chat_id=cid, model=model,
                        send=lambda to, text: sent.append(text), customer_id="c1")
        self.assertEqual(got.outcome, "replied", got)
        self.assertEqual(sent, ["The fee for the late parcel is 175 EGP."])


# ---- Run the Arena on an agent's page (Morning.run_arena, Pages._arena, ARENA_SCRIPT) ----

from arena import retry as retry_mod  # noqa: E402
from tests.fake_model import clean_env  # noqa: E402

ARENA_TAB = {"tab": ["arena"]}


class RunTheArena(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.folder = self.dir / "agents" / "stock_watch"
        shutil.copytree(tap.FIXTURE, self.folder)
        from engine import plug as plug_mod
        from kit.db import Db
        self.db = Db(str(self.dir / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(tq.ROOT / "sales" / "plug.json")], reports=self.dir,
                            db_path=self.dir / "ascent.db")
        self.assertEqual(self.m.add_built(), ["stock_watch"])
        self.world = World()
        self.m.arena_models = lambda: (self.world, self.world, self.world)
        self.m.arena_shape = {"matches": 1, "rounds": 1}
        self.starts = []
        self.m.arena_start = lambda work, name: self.starts.append((work, name))
        self.p = pages.Pages(self.m)

    def tab(self, token="t"):
        """The Arena tab's markup, without its style and its script."""
        return self.p.get("/agents/stock_watch", ARENA_TAB, token).split("</style>")[1].split("<script>")[0]

    def test_the_button_starts_a_full_practice_in_the_background_and_the_tab_follows_it(self):
        page = self.tab()
        self.assertIn(f'action="{pages.ARENA_PATH}"', page)
        self.assertIn('value="/agents/stock_watch?tab=arena"', page)  # it comes back to the Arena tab
        self.assertIn(pages.ARENA_SAID, page)
        self.assertEqual(self.m.run_arena("stock_watch"), mo.ARENA_STARTED)
        self.assertEqual([n for _, n in self.starts], ["arena-stock_watch"])
        self.assertTrue(self.m.arena_running("stock_watch"))
        page = self.tab()
        self.assertIn('data-live="arena" data-running', page)
        self.assertIn("Running the Arena: its first matches are starting.", page)
        self.assertNotIn(f'action="{pages.ARENA_PATH}"', page)
        with self.assertRaises(mo.Refused):  # one run at a time per agent
            self.m.run_arena("stock_watch")
        self.assertEqual(len(self.starts), 1)
        self.starts[0][0]()  # the thread's work, here
        self.assertFalse(self.m.arena_running("stock_watch"))
        saved = self.m.read_arena()[0]["stock_watch"]
        self.assertIsNot(saved.get("quick"), True)  # a full run, so its gate can count
        self.assertGreater(self.world.calls["judge"], 0)
        page = self.tab()
        self.assertIn('data-live="arena"', page)
        self.assertNotIn("data-running", page)
        self.assertIn("Newest run", page)
        self.assertIn(f'action="{pages.ARENA_PATH}"', page)  # it can run again

    def test_progress_counts_the_matches_played_since_it_started(self):
        matches = self.folder / "arena-matches.jsonl"
        matches.write_text('{"old": 1}\n', encoding="utf-8")
        self.m.run_arena("stock_watch")
        self.assertEqual(self.m.arena_played("stock_watch"), 0)
        with open(matches, "a", encoding="utf-8") as f:
            f.write('{"a": 1}\n{"b": 2}\n')
        self.assertEqual(self.m.arena_played("stock_watch"), 2)
        self.assertIn("Running the Arena: 2 practice matches played so far.", self.tab())
        self.assertIn('role="status">Running the Arena', self.p.get("/agents/stock_watch", {}, "t"))  # Overview too

    def test_refusals_start_nothing(self):
        for agent in ("sales", "nobody", "../agents"):
            with self.subTest(agent=agent), self.assertRaises(mo.Refused) as e:
                self.m.run_arena(agent)
            self.assertEqual(str(e.exception), mo.ARENA_NOT_HERE)
        with mock.patch.object(retry_mod, "has_room", return_value=False), self.assertRaises(mo.Refused) as e:
            self.m.run_arena("stock_watch")
        self.assertIn("model call cap", str(e.exception))
        self.m.arena_models = None
        with mock.patch("kit.model.has_key", return_value=False), self.assertRaises(mo.Refused) as e:
            self.m.run_arena("stock_watch")
        self.assertIn("No model key", str(e.exception))
        self.assertEqual(self.starts, [])
        self.assertFalse(self.m.arena_running("stock_watch"))
        self.assertNotIn("Run the Arena", self.p.get("/agents/sales", ARENA_TAB, "t"))  # Sales has Try again

    def test_a_run_that_fails_says_why_and_the_button_comes_back(self):
        self.m.arena_models = lambda: (tap.raises, tap.raises, tap.raises)
        self.m.arena_start = lambda work, name: work()
        self.m.run_arena("stock_watch")
        self.assertFalse(self.m.arena_running("stock_watch"))
        page = self.tab()
        self.assertIn("The last run could not finish (", page)
        self.assertIn(f'action="{pages.ARENA_PATH}"', page)

    def test_the_page_refuses_it_while_building_or_while_its_first_practice_runs(self):
        go = self.p.actions[pages.ARENA_PATH]
        self.p.run = pages.BuildRun(self.m)  # a build that has not written its files yet
        with self.assertRaises(mo.Refused) as e:
            go(self.m, {"agent": ["stock_watch"]})
        self.assertIn("It is building", str(e.exception))
        self.p.run.agent = "other_agent"  # a build of another agent leaves this one free
        self.p.quick._running.add("stock_watch")
        with self.assertRaises(mo.Refused) as e:
            go(self.m, {"agent": ["stock_watch"]})
        self.assertIn("first short practice", str(e.exception))
        self.p.quick._running.discard("stock_watch")
        self.assertEqual(go(self.m, {"agent": ["stock_watch"]}), mo.ARENA_STARTED)

    def test_overview_shows_it_while_there_is_no_run(self):
        page = self.p.get("/agents/stock_watch", {}, "t")
        self.assertIn('<h3 id="ra-h">The Arena</h3>', page)
        self.assertIn('value="/agents/stock_watch"', page.split(f'action="{pages.ARENA_PATH}"')[1].split("</form>")[0])
        self.m.arena_start = lambda work, name: work()
        self.m.run_arena("stock_watch")
        self.assertNotIn('id="ra-h"', self.p.get("/agents/stock_watch", {}, "t"))  # a run is saved now
        self.assertNotIn(f'action="{pages.ARENA_PATH}"', self.p.get("/agents/stock_watch", {}, ""))  # no token

    def test_only_its_page_carries_the_hashed_script_and_the_policy_that_allows_it(self):
        page = self.p.get("/agents/stock_watch", ARENA_TAB, "t")
        self.assertIn(f"<script>{pages.ARENA_SCRIPT}</script>", page)
        policy = self.p.csp_for("/agents/stock_watch")
        self.assertEqual(policy, pages.AGENT_CSP)
        self.assertIn(f"script-src 'sha256-{pages._sha(pages.ARENA_SCRIPT)}'", policy)
        self.assertIn("connect-src 'self'", policy)
        self.assertNotIn("script-src", self.p.csp_for("/agents/sales"))
        self.assertNotIn("<script>", self.p.get("/agents/sales", ARENA_TAB, "t"))
        self.assertNotIn("script-src", self.p.csp_for("/agents/stock_watch/rollback"))
        self.assertIn("'X-Poll':'1'", pages.ARENA_SCRIPT)


class ArenaPost(RunTheArena):
    def test_the_post_needs_the_token(self):
        server = DataPost.serve(self)
        here = f"127.0.0.1:{server.server_address[1]}"

        def post(token):
            form = urllib.parse.urlencode({"token": token, "agent": "stock_watch", "back": "/agents/stock_watch"})
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            try:
                conn.request("POST", pages.ARENA_PATH, form, {"Host": here, "Origin": f"http://{here}",
                                                             "Content-Type": "application/x-www-form-urlencoded"})
                r = conn.getresponse()
                r.read()
                return r.status, r.getheader("Location")
            finally:
                conn.close()
        self.assertEqual(post("guess")[0], 403)
        self.assertEqual(self.starts, [])
        self.assertEqual(post(server.token), (303, "/agents/stock_watch"))
        self.assertEqual(len(self.starts), 1)
