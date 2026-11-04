"""Existing agents get the Sample data line, the Add data box and Offers with the Add offers box (2026-11-05;
Mohamed: "existing agents should have the new features too").

The personal assistant (its case folder, decision 109) and the example Family dinner planner keep what is added
in their agent folder beside the database, which their tools and their Arena practice read (kit/turn.py load,
arena/practice.py). The Sales agent has no folder: what is added for it goes to <db folder>/added/sales/
(kit/added.py), which its store tool's catalogue and the store data's offers read. The Marketing agent has no
runtime that reads data, so it shows its Sample data line and no box. Each box's placeholder fits its agent.
The two page CSS fixes: the risk card's line is plain text, and the page chat's No reply is a normal bubble.
Fake models only: no model call, no network, no real data."""
import json
import re
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from assistant import PLUG as ASSISTANT, case
from engine import plug as plug_mod
from kit import added, offers, sample, turn
from kit.db import Db
from kit.tools import data as data_tool, store
from reflection import examples, morning as mo, pages
from reflection.page_css import CSS
from tests.fake_model import clean_env

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "family_dinner_planner"
AGENTS = ("sales", "assistant", FAMILY)
TOKEN = "t"


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.addCleanup(added.use, None)
        self.addCleanup(store._cache.update, at=0.0, items=None)
        self.dir = Path(d.name).resolve()
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        repo = [plug_mod.load(ROOT / "sales" / "plug.json"), ASSISTANT, plug_mod.load(ROOT / "marketing" / "plug.json")]
        self.assertEqual(examples.install(self.path, {p.agent for p in repo}), [FAMILY])
        plugs, built = mo.with_built(repo, self.path)
        self.m = mo.Morning(self.db, plugs, reports=self.dir, db_path=self.path, built=built)
        self.p = pages.Pages(self.m)

    def page(self, agent, token=TOKEN):
        return self.p.get(f"/agents/{agent}", {}, token).split("</style>")[1].split("<script>")[0]

    def form(self, page, path):
        return page.split(f'action="{path}"')[1].split("</form>")[0]


class Boxes(Base):
    def test_each_existing_agent_shows_the_sample_data_line_and_both_boxes_with_a_token(self):
        for agent in AGENTS:
            page = self.page(agent)
            self.assertIn('<h3 id="sd-h">Sample data</h3>', page, agent)
            self.assertIn(f'action="{mo.DATA_PATH}"', page, agent)
            self.assertIn(f'<h3 id="of-h">{pages.OFFERS_HEAD}</h3>', page, agent)
            self.assertIn(f'action="{mo.OFFERS_PATH}"', page, agent)
            self.assertIn(f'name="agent" value="{agent}"', self.form(page, mo.DATA_PATH), agent)
            no_token = self.page(agent, token="")
            self.assertIn('<h3 id="sd-h">Sample data</h3>', no_token, agent)
            self.assertNotIn(f'action="{mo.DATA_PATH}"', no_token, agent)  # no token, no box
            self.assertNotIn(f'action="{mo.OFFERS_PATH}"', no_token, agent)

    def test_each_line_says_what_its_data_is(self):
        self.assertIn(case.DATA_LINE, self.page("assistant"))
        n = len(store._from_demo(store.DEMO_CATALOGUE))
        self.assertIn(pages.h(mo.SALES_DATA_LINE.format(n=n)), self.page("sales"))
        self.assertIn("family dinner profiles", self.page(FAMILY))

    def test_the_sales_offers_show_the_store_data_offers(self):
        page = self.page("sales")
        for o in offers.base()["offers"]:
            self.assertIn(pages.h(pages.offer_text(o)), page)

    def test_marketing_shows_its_line_and_no_box_since_nothing_reads_added_data(self):
        page = self.page("marketing")
        self.assertIn('<h3 id="sd-h">Sample data</h3>', page)
        self.assertIn("Simulated posts", page)
        self.assertNotIn(f'action="{mo.DATA_PATH}"', page)
        self.assertNotIn(f'action="{mo.OFFERS_PATH}"', page)
        with self.assertRaises(mo.Refused):
            self.m.add_data("marketing", "a,b\n1,2")
        with self.assertRaises(mo.Refused):
            self.m.add_offers("marketing", "Free post; on any post; always")
        self.assertFalse((self.dir / added.FOLDER / "marketing").exists())

    def test_an_unknown_agent_or_a_path_takes_nothing(self):
        for who in ("nobody", "../sales", "sales/../x", ""):
            with self.assertRaises(mo.Refused):
                self.m.add_data(who, "title,price\nX,1")
            with self.assertRaises(mo.Refused):
                self.m.add_offers(who, "X; y; z")


class FolderAgents(Base):
    """The assistant and the Family dinner planner: added rows and offers land in their agent folder."""

    def test_added_rows_reach_the_data_tool_and_the_practice_prompt(self):
        for agent, text, word in (("assistant", "contact,email,note\nRana Adel,rana@example.com,dentist friday",
                                   "Rana Adel"),
                                  (FAMILY, "label,size,allergies\nfamily z,4 adults,sesame", "sesame")):
            said = self.m.add_data(agent, text)
            self.assertTrue(said.startswith("Added 1 row"), said)
            folder = self.m.agent_folder(agent)
            self.assertEqual(folder, self.dir / turn.AGENTS / agent)
            got = turn.load(folder)  # what its tools are handed each turn and in each Arena match
            self.assertIn(turn.DATA_TOOL, got.tools)
            rows = data_tool.run({"query": word}, mock.Mock(data=got.data))["rows"]
            self.assertIn(word, json.dumps(rows), agent)
            self.assertEqual(rows[0]["source"], "added by the user")
            self.assertIn(word, sample.for_prompt(got.data), agent)  # the practice customer's rows
            self.assertIn("1 added by you", self.page(agent), agent)  # its Sample data line counts it

    def test_added_offers_reach_the_turn_and_the_data_tool(self):
        for agent in ("assistant", FAMILY):
            said = self.m.add_offers(agent, "A cheaper swap; same meal for less; when the budget is tight")
            self.assertTrue(said.startswith("Added 1 offer"), said)
            got = turn.load(self.m.agent_folder(agent))
            self.assertEqual([o["what"] for o in got.offers["offers"]], ["A cheaper swap"])  # practice reads these
            self.assertIn(turn.DATA_TOOL, got.tools)
            token = offers.OFFERS.set(got.offers)  # as kit/turn.py sets them for its turn
            try:
                out = data_tool.run({}, mock.Mock(data=got.data))
            finally:
                offers.OFFERS.reset(token)
            self.assertEqual([o["what"] for o in out["offers"]], ["A cheaper swap"])
            self.assertIn("A cheaper swap", self.page(agent))

    def test_nothing_goes_into_the_repo(self):
        self.m.add_data("assistant", "contact,email\nRana,rana@example.com")
        self.m.add_offers("assistant", "A short draft; for a quick reply; when rushed")
        self.assertFalse((ROOT / "assistant" / sample.FILE).exists())
        self.assertFalse((ROOT / "examples" / "agents" / FAMILY / offers.FILE).exists())


class Sales(Base):
    """The Sales agent: added rows join its store tool's catalogue, added offers its store data's offers."""

    def test_added_products_reach_the_store_tool_beside_the_database(self):
        said = self.m.add_data("sales", "title,size,price,stock\nZone Training Cap,One size,350,7")
        self.assertTrue(said.startswith("Added 1 row"), said)
        self.assertTrue((self.dir / added.FOLDER / "sales" / sample.FILE).is_file())
        self.assertFalse((ROOT / "demo" / sample.FILE).exists())
        store._cache.update(at=0.0, items=None)
        got = store.run({"query": "zone training cap"}, None)
        self.assertEqual([i["title"] for i in got["items"]], ["Zone Training Cap"])
        self.assertEqual(got["items"][0]["variants"], [{"size": "One size", "price": "350", "stock": "in stock"}])
        self.assertIn("Zone Training Cap", [i["title"] for i in store.catalogue()])  # the Arena reads the same
        self.assertIn("1 row added by you", self.page("sales"))

    def test_real_store_keys_win_over_added_products(self):
        self.m.add_data("sales", "title,price\nZone Training Cap,350")
        with mock.patch.dict("os.environ", {"SHOPIFY_STORE": "x.myshopify.com", "SHOPIFY_TOKEN": "t"}), \
                mock.patch.object(store, "_from_shopify", return_value=[{"title": "Real item"}]):
            store._cache.update(at=0.0, items=None)
            self.assertEqual(store.catalogue(), [{"title": "Real item"}])
            self.assertIn(mo.SALES_REAL_LINE, self.page("sales"))
        store._cache.update(at=0.0, items=None)

    def test_a_row_that_is_not_a_product_is_refused_since_its_store_tool_would_never_read_it(self):
        with self.assertRaises(mo.Refused) as e:
            self.m.add_data("sales", "just a note about the shop")
        self.assertEqual(str(e.exception), mo.SALES_ROWS_ONLY)
        self.assertIsNone(self.m.sample_data("sales"))

    def test_added_offers_reach_the_store_tool_and_the_arena_offers(self):
        before = len(offers.base()["offers"])
        said = self.m.add_offers("sales", "Free gift wrap; with any boots; when it is a present")
        self.assertTrue(said.startswith("Added 1 offer"), said)
        self.assertTrue((self.dir / added.FOLDER / "sales" / offers.FILE).is_file())
        self.assertIsNone(offers.OFFERS.get())  # the Sales agent's turn sets none: it reads the store data's
        now = offers.current()  # what sales/loop.py and arena/run.py Arena.offers_data read
        self.assertEqual(len(now["offers"]), before + 1)
        self.assertEqual(now["offers"][-1]["what"], "Free gift wrap")
        self.assertEqual(len(offers.base()["offers"]), before)  # the demo file is not written
        store._cache.update(at=0.0, items=None)
        self.assertIn("Free gift wrap", [o["what"] for o in store.run({}, None)["offers"]])
        self.assertIn("Free gift wrap", self.page("sales"))

    def test_the_sales_offers_cap_counts_the_store_data_offers(self):
        room = offers.MAX_OFFERS - len(offers.base()["offers"])
        with self.assertRaises(mo.Refused):
            self.m.add_offers("sales", "\n".join(f"Gift {i}; on any order; always" for i in range(room + 1)))
        self.m.add_offers("sales", "\n".join(f"Gift {i}; on any order; always" for i in range(room)))
        self.assertEqual(len(offers.current()["offers"]), offers.MAX_OFFERS)

    def test_with_no_database_nothing_is_added_to_the_store_data(self):
        self.m.add_offers("sales", "Free gift wrap; with any boots; when it is a present")
        added.use(None)
        self.assertEqual(offers.current(), offers.base())


class Placeholders(Base):
    def hints(self, agent):
        page = self.page(agent)
        return (self.form(page, mo.DATA_PATH).split('placeholder="')[1].split('"')[0],
                self.form(page, mo.OFFERS_PATH).split('placeholder="')[1].split('"')[0])

    def test_each_agent_has_its_own_placeholders(self):
        got = {a: self.hints(a) for a in AGENTS}
        self.assertEqual(got["sales"][0], pages.SALES_DATA_HINT)
        self.assertEqual(got["assistant"][0], case.DATA_HINT)
        first = sample.read(self.m.agent_folder(FAMILY))["rows"][0]["row"]
        self.assertEqual(got[FAMILY][0], ", ".join(k.replace("_", " ") for k in list(first)[:pages.MAX_HINT_KEYS]))
        self.assertEqual(len({d for d, _ in got.values()}), 3)
        self.assertEqual(len({o for _, o in got.values()}), 3)
        self.assertIn("swap", got[FAMILY][1])
        for agent, (d, o) in got.items():
            self.assertNotEqual(d, "name, price, stock", agent)
            self.assertNotIn("Free delivery", o, agent)

    def stub(self, card, data=None):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        (Path(d.name) / "card.json").write_text(json.dumps(card), encoding="utf-8")
        return types.SimpleNamespace(agent_folder=lambda a: Path(d.name), sample_data=lambda a: data,
                                     case_kit=lambda a: None)

    def test_an_apartment_agent_gets_a_viewing_offer_and_never_free_delivery(self):
        m = self.stub({"name": "Flat finder", "kind": "rentals", "does": "Answers people asking about apartments for "
                       "rent and books viewings.", "case": {"input": "a question about a flat", "output": "a booked viewing"}})
        self.assertEqual(pages.offer_hint(m, "flat_finder"), "Free second viewing; on a booked viewing; this week")
        self.assertNotIn("Free delivery", pages.offer_hint(m, "flat_finder"))
        self.assertEqual(pages.data_hint(m, "flat_finder"), pages.DATA_HINT)

    def test_columns_come_from_the_first_row_and_a_store_need_or_nothing_has_a_fallback(self):
        rows = {"what": "flats", "rows": [{"by": "made_up", "row": {"area": "Zamalek", "rooms": 2, "rent": 900}}]}
        self.assertEqual(pages.data_hint(self.stub({}, rows), "x"), "area, rooms, rent")
        self.assertEqual(pages.data_hint(self.stub({"needs": [{"tool": "store"}]}), "x"), pages.STORE_DATA_HINT)
        self.assertEqual(pages.offer_hint(self.stub({"does": "Keeps notes."}), "x"), pages.OFFER_HINT)
        self.assertEqual(pages.offer_hint(self.stub({"does": "Sells shoes in a shop."}), "x"),
                         "Free delivery; on any order; always")

    def test_no_dash_or_emoji_in_the_new_words(self):
        words = [pages.DATA_HINT, pages.STORE_DATA_HINT, pages.SALES_DATA_HINT, pages.OFFER_HINT,
                 pages.SALES_OFFER_HINT, case.DATA_HINT, mo.SALES_DATA_LINE, mo.SALES_REAL_LINE, mo.SALES_ROWS_ONLY]
        words += [hint for _, hint in pages.OFFER_HINTS]
        for w in words:
            self.assertIsNone(re.search("[%s%s%s-%s]" % (chr(0x2013), chr(0x2014), chr(0x1F300), chr(0x1FAFF)), w), w)


class Css(unittest.TestCase):
    def rules(self, selector):
        """The bodies of the rules whose whole selector is this one, at any width (a rule starts its line)."""
        return [m.group(1) for m in re.finditer(r"(?m)^\s*" + re.escape(selector) + r"\{([^}]*)\}", CSS)]

    def test_the_risk_card_line_is_plain_text(self):
        self.assertEqual(self.rules(".calm"), [])  # no bare .calm box rule, at any width
        self.assertTrue(self.rules(".calm.sq"))
        self.assertTrue(any("padding:28px 32px" in r for r in self.rules(".calm.sq")))
        lvc = CSS.split(".lvc .calm,.lvc .quiet{")[1].split("}")[0]
        self.assertNotIn("background", lvc)

    def test_the_round_no_button_rule_is_scoped_to_buttons_so_the_no_reply_bubble_is_a_bubble(self):
        self.assertEqual(self.rules(".no"), [])
        self.assertIn("border-radius:50%", self.rules("button.no")[0])
        bubble = self.rules(".try .said.no")[0]
        self.assertIn("background:", bubble)
        self.assertNotIn("width", bubble)


if __name__ == "__main__":
    unittest.main()
