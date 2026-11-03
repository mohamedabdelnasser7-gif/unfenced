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
