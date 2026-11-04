"""Sample data for any agent (DECISIONS 107, 2026-11-04): when the data an agent's job needs is missing from
what its tools return, the store's stock here, it comes from sample data made for that job and every tool
answer built from it says so ("data": kit/sample.py LABEL). The demo store's sample stock is a separate layer,
never written as tracked stock; Build's sample step asks for stock under the key the store tool reads; the
agent page says the agent is using sample data. Fake models only, no network, no real data."""
import json
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from kit import sample, turn
from kit.tools import data as data_tool, store
from reflection import pages, quickstart as qs
from tests.fake_model import FakeModel, say, tool_call
from tests.test_any_agent import CardShowsSampleData, PageCase, STORE_SET
from tests.test_arena_practice import FIXTURE
from tests.test_quickstart import no_keys

LEVELS = {"in stock", "few left", "out"}


def fresh():
    store._cache.update(at=0.0, items=None, sampled=False)


class DemoSampleStock(unittest.TestCase):
    def setUp(self):
        keys = no_keys()
        keys.start()
        self.addCleanup(keys.stop)
        fresh()
        self.addCleanup(fresh)

    def test_the_layer_is_separate_and_covers_every_variant(self):
        cat = json.loads(store.DEMO_CATALOGUE.read_text(encoding="utf-8"))["variables"]
        skus = [v["sku"] for p in cat.values() if p["productType"] != "Printing" for v in p["variants"]]
        self.assertTrue(all(v["inventoryItem"]["tracked"] is False for p in cat.values() for v in p["variants"]))
        self.assertFalse(any("inventoryQuantities" in v for p in cat.values() for v in p["variants"]))
        layer = store.sample_stock(store.DEMO_SAMPLE_STOCK)
        self.assertEqual(sorted(layer), sorted(skus))
        levels = {store.stock_level(q) for q in layer.values()}
        self.assertEqual(levels, LEVELS)

    def test_with_no_store_connected_every_variant_has_a_sample_level_and_the_answer_is_labelled(self):
        got = store.run({}, None)
        self.assertEqual(got["data"], sample.LABEL)
        variants = [v for i in got["items"] if i["type"] != "Printing" for v in i["variants"]]
        self.assertTrue(variants)
        self.assertTrue(all(v.get("stock") in LEVELS for v in variants))
        self.assertEqual(store.run({"query": "phantom"}, None)["data"], sample.LABEL)

    def test_with_no_layer_there_is_no_stock_and_no_label(self):
        with mock.patch.object(store, "DEMO_SAMPLE_STOCK", Path("/nonexistent/sample-stock.json")):
            got = store.run({}, None)
        self.assertNotIn("data", got)
        self.assertFalse(any("stock" in v for i in got["items"] for v in i["variants"]))

    def test_a_real_store_is_never_labelled(self):
        with mock.patch.dict(os.environ, STORE_SET), \
                mock.patch.object(store, "_from_shopify", return_value=[{"title": "Real item"}]):
            got = store.run({}, None)
        self.assertEqual((got["items"], "data" in got), ([{"title": "Real item"}], False))


class StockWatchReadsSampleStock(unittest.TestCase):
    """The fixture stock agent: Build's sample step, then a practice turn whose store answer carries stock
    levels and the sample label."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.folder = Path(d.name).resolve() / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        keys = no_keys()
        keys.start()
        self.addCleanup(keys.stop)
        fresh()
        self.addCleanup(fresh)

    def store_answer(self, question="Is the runner in stock?"):
        from kit.chats import Chats
        from kit.db import Db
        agent = turn.load(self.folder)
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "c1")
        model = FakeModel(tool_call("store", {"query": ""}), say("It is in stock."))
        turn.turn(agent, question, chats=chats, chat_id=cid, model=model, send=lambda *a: None, customer_id="c1")
        out = [m for m in model.calls[1]["messages"] if m["role"] == "tool"][0]["content"]
        return json.loads(out)

    def test_builds_sample_step_asks_for_stock_and_the_turn_reads_it_labelled(self):
        rows = [{"title": "Blue Runner", "size": "42", "stock": 2}, {"title": "Blue Runner", "size": "43", "stock": 9},
                {"title": "Trail Cap", "stock": 0}]
        sent = []

        def chat(messages, cap):
            sent.append(messages)
            return json.dumps({"what": "products with stock counts", "rows": rows})
        card = json.loads((self.folder / "card.json").read_text(encoding="utf-8"))
        card = dict(card, key="stock_watch", needs=[{"what": n, "tool": "store"} for n in card["needs"]])
        made = qs.QuickStart._sample(types.SimpleNamespace(_chat=chat), card)
        self.assertIn("under the key stock", sent[0][0]["content"])
        sample.write(self.folder, made)
        got = self.store_answer()
        self.assertEqual(got["data"], sample.LABEL)
        stock = {(i["title"], v.get("size")): v["stock"] for i in got["items"] for v in i["variants"]}
        self.assertEqual(stock, {("Blue Runner", "42"): "few left", ("Blue Runner", "43"): "in stock",
                                 ("Trail Cap", None): "out"})
        self.assertEqual(data_tool.run({}, types.SimpleNamespace(data=sample.read(self.folder)))["data"], sample.LABEL)

    def test_with_no_sample_products_the_turn_reads_the_demo_sample_stock_labelled(self):
        got = self.store_answer()
        self.assertEqual(got["data"], sample.LABEL)
        self.assertTrue(all(v.get("stock") in LEVELS for i in got["items"] if i["type"] != "Printing"
                            for v in i["variants"]))

    def test_a_stock_word_the_model_may_use_is_read(self):
        items = sample.store_items(sample.made("products", [{"title": "Cap", "availability": "low stock"},
                                                            {"title": "Hat", "stock_status": "available"}]))
        self.assertEqual([i["variants"][0]["stock"] for i in items], ["few left", "in stock"])


class PageSaysSampleData(PageCase):
    setUp = CardShowsSampleData.setUp

    def test_the_overview_says_it_uses_sample_data_until_the_store_is_connected(self):
        CardShowsSampleData.built(self)
        page = self.p.get("/agents/stock_watcher", {}, "t")
        self.assertIn(pages.USING_SAMPLE, page)
        with mock.patch.dict(os.environ, STORE_SET):
            self.assertNotIn(pages.USING_SAMPLE, self.p.get("/agents/stock_watcher", {}, "t"))


if __name__ == "__main__":
    unittest.main()
