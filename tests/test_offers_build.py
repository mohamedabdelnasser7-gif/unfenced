"""Build asks for offers and the pages show them (decision 105, job C), and the name clash line (decision 106).

T5: Quick start's card call carries the offers (no extra model call), Build writes offers.json beside the
sample data, and once kit/turn.py reads it (job A5) the agent and its practice store step see them.
T10: /new shows the card's Offers block, the Overview shows and adds offers, and the Arena item shows the
store team's real rate and the wins as sales and closes when its report has them. Fake models only."""
import dataclasses
import json
import time
import unittest

from kit import offers, turn
from reflection import morning as mo, pages, quickstart as qs
from tests.fake_model import say
import tests.test_arena_practice as tap
from tests.test_any_agent import PageCase, sample_reply
from tests.test_quickstart import CASE, exam_reply, no_keys, plug_reply

OFFERS = [{"what": "Free delivery", "terms": "on any order", "when": "the delivery fee is the worry", "kind": "delivery",
           "covers": ["delivery fee"]},
          {"what": "10% off a second item", "terms": "the cheaper one", "when": "they want two",
           "kind": "nth_item", "percent_off": 10}]


def offer_card(key="stock_watcher", name="Stock watcher", offers_=OFFERS, question=""):
    """tests/test_quickstart.py card_reply with offers on the card."""
    return say(json.dumps({"card": {
        "name": name, "key": key, "does": "Checks stock every morning and tells you which items run low.",
        "case": CASE, "good": "You hear about a low item a day before it runs out.",
        "bad": "You hear about a low item only after it ran out.", "never": ["Never orders stock by itself"],
        "needs": [{"what": "Your store's stock", "tool": "store"}], "offers": offers_},
        "question": question, "follow": "Here is my first guess. Add or change anything before I build it."}))


def a5_landed():
    return "offers" in {f.name for f in dataclasses.fields(turn.Agent)}


class BuildWritesOffers(PageCase):  # T5
    def setUp(self):
        PageCase.setUp(self)
        self.m.db_path = str(self.folder / "ascent.db")  # the live page, so the built agent joins it
        keys = no_keys()
        keys.start()
        self.addCleanup(keys.stop)

    def built(self, card):
        self.page(card, plug_reply(), exam_reply(), sample_reply())
        self.send("an agent for my stock, free delivery on everything and 10% off a second item")
        said = self.build()
        self.assertTrue(said.startswith("Built Stock watcher"), said)
        return self.folder / "agents" / "stock_watcher"

    def test_the_card_call_asks_for_offers_and_build_writes_them_beside_the_sample_data(self):
        folder = self.built(offer_card())
        self.assertEqual(len(self.model.calls), 4)  # card, plug, exam, sample data: no extra call for offers
        prompt = self.model.calls[0]["messages"][0]["content"]
        self.assertIn("offers: what the agent may offer a customer who hesitates", prompt)
        self.assertIn("ask what they can offer a customer who hesitates (for an agent that does not sell: what it "
                      "may give)", prompt)
        self.assertIn('"offers": []', prompt)
        got = offers.read(folder)
        self.assertEqual([o["what"] for o in got["offers"]], ["Free delivery", "10% off a second item"])
        self.assertEqual(got["offers"][1]["percent_off"], 10)
        self.assertEqual(offers.percents(got), {offers.Decimal("10")})
        self.assertTrue((folder / "sample-data.json").exists())
        self.assertNotIn("Its offers could not be saved", self.p.run.error or "")

    def test_no_offers_on_the_card_writes_no_file(self):
        folder = self.built(offer_card(offers_=[]))
        self.assertFalse((folder / offers.FILE).exists())
        self.assertTrue((folder / "plug.json").exists())

    def test_the_turn_and_its_practice_store_step_read_them(self):
        folder = self.built(offer_card())
        if not a5_landed():
            self.skipTest("kit/turn.py reads offers.json in job A5, not merged on this branch yet")
        self.assertTrue(turn.load(folder).offers["offers"])


class PracticeStoreStepShowsTheOffer(tap.Base):  # T5, the practice side
    def test_the_store_step_in_a_practice_match_carries_the_offer(self):
        if not a5_landed():
            self.skipTest("kit/turn.py and the store tool give offers in jobs A2 and A5, not merged here yet")
        offers.write(self.folder, OFFERS)
        seen = []

        def agent(messages, tools):
            if messages[-1]["role"] == "tool":
                seen.append(messages[-1]["content"])
                return say(tap.ANSWER)
            return tap.tool_call("store", {"query": "mercurial"})
        code, _ = self.main("--quick", "--json", world=tap.World(agent=agent))
        self.assertEqual(code, 0, self.err)
        self.assertTrue(seen)
        self.assertIn("Free delivery", seen[0])


class CardOffersAreCleaned(unittest.TestCase):
    def test_offers_are_capped_cleaned_and_read_back_by_the_model_without_ids(self):
        card = {"name": "x", "key": "x", "does": "d", "good": "g", "bad": "b", "case": CASE, "never": [], "needs": [],
                "offers": [dict(OFFERS[0], what="<b>Free</b> delivery" + chr(0x2014) + "today", names=["hidden"])]
                + [{"what": "no kind"}, {"kind": "made_up", "what": "odd"}] + [OFFERS[1]] * 9}
        got = qs.clean_card({"card": card, "question": "", "follow": "Change anything."})["card"]["offers"]
        self.assertEqual(len(got), qs.MOST_OFFERS - 2)  # two of the first six had no known kind
        self.assertEqual(got[0]["what"], "bFree/b delivery, today")
        self.assertNotIn("names", got[0])
        self.assertEqual(got[0]["id"], "offer_1")
        back = qs._model_card(dict(card, offers=got))["offers"]
        self.assertNotIn("id", back[0])
        self.assertEqual(back[1]["percent_off"], 10)

    def test_a_card_with_no_offers_has_no_offers_key(self):
        card = {"name": "x", "key": "x", "does": "d", "good": "g", "bad": "b", "case": CASE, "never": [], "needs": []}
        self.assertNotIn("offers", qs.clean_card({"card": card, "question": "", "follow": "Ok."})["card"])


class NameClash(PageCase):  # decision 106
    def test_a_card_named_sales_says_so_before_build_and_build_refuses_it(self):
        self.page(offer_card(key="sales", name="Sales"))
        self.send("a sales agent for my shop")
        page = self.get()
        line = ("Sales is the name of the built-in Beyond the Limits agent. Pick another name for yours, for example "
                "sales_mystore.")
        self.assertIn(f'<p class="err" role="status" dir="auto">{line}</p>', page)
        self.assertLess(page.index(line), page.index('action="/quickstart/build"'))  # before Build is pressed
        with self.assertRaises(mo.Refused) as e:
            self.build()
        self.assertEqual(str(e.exception), line)
        self.assertEqual(len(self.model.calls), 1)  # refused before any model call
        flash = self.p.get("/new", {}, "t", line)
        self.assertIn(f'{line} <a href="/agents/sales">Open ', flash)

    def test_another_agents_name_says_so_with_a_free_example(self):
        (self.folder / "agents" / "stock_watcher").mkdir(parents=True)
        (self.folder / "agents" / "stock_watcher_2").mkdir()
        self.page(offer_card())
        self.send("an agent for my stock")
        line = ("There is an agent called stock_watcher already. Pick another name for yours, for example "
                "stock_watcher_3.")
        self.assertIn(line, self.get())
        with self.assertRaises(mo.Refused) as e:
            self.build()
        self.assertEqual(str(e.exception), line)

    def test_a_free_name_shows_no_line(self):
        self.page(offer_card())
        self.send("an agent for my stock")
        page = self.get()
        self.assertNotIn("Pick another name", page)
        self.assertIsNone(self.p.quick.name_clash(self.m, {"key": "", "name": "!!!"}))  # no name: Build says it
        self.assertEqual(qs.taken_line("a" * 41, {"a" * 41: 1}, None), f"There is an agent called {'a' * 41} already. "
                         f"Pick another name for yours, for example {'a' * 39}_2.")


class OffersOnThePages(PageCase):  # T10
    def setUp(self):
        PageCase.setUp(self)
        self.m.db_path = str(self.folder / "ascent.db")
        keys = no_keys()
        keys.start()
        self.addCleanup(keys.stop)

    def test_new_shows_the_offers_block_on_the_card(self):
        self.page(offer_card())
        self.send("an agent for my stock")
        page = self.get()
        self.assertIn("<dt>Offers</dt>", page)
        self.assertIn("Free delivery. On any order. When: the delivery fee is the worry.", page)
        self.assertIn("10% off a second item. The cheaper one. When: they want two.", page)

    def test_overview_shows_offers_and_adds_more_for_an_agent_made_here_only(self):
        self.page(offer_card(offers_=[]), plug_reply(), exam_reply(), sample_reply())
        self.send("an agent for my stock")
        self.build()
        page = self.p.get("/agents/stock_watcher", {}, "t")
        self.assertIn('<h3 id="of-h">Offers</h3>', page)
        self.assertIn(pages.OFFERS_NONE, page)
        self.assertIn(f'action="{mo.OFFERS_PATH}"', page)
        self.assertNotIn(f'action="{mo.OFFERS_PATH}"', self.p.get("/agents/stock_watcher", {}, ""))  # no token
        add = mo.TWO_TAB_ACTIONS[mo.OFFERS_PATH]
        said = add(self.m, {"agent": ["stock_watcher"], "text": ["Free gift wrap; any order; a birthday\n\n"
                                                                    "15% off; paid today; price is the worry"]})
        self.assertEqual(said, "Added 2 offers. Its next practice and its replies read them.")
        got = self.m.offers("stock_watcher")["offers"]
        self.assertEqual([(o["id"], o["kind"], o.get("percent_off")) for o in got],
                         [("own_1", "choice", None), ("own_2", "choice", 15)])
        page = self.p.get("/agents/stock_watcher", {}, "t")
        self.assertIn("Free gift wrap. Any order. When: a birthday.", page)
        self.assertIn(pages.OFFERS_SAID, page)
        self.assertEqual(add(self.m, {"agent": ["stock_watcher"], "text": ["Free name tag"]}),
                         "Added 1 offer. Its next practice and its replies read them.")
        self.assertEqual(self.m.offers("stock_watcher")["offers"][-1]["id"], "own_3")
        for agent, text, words in (("sales", "x", "Only an agent made here"), ("stock_watcher", " \n ; ", "one offer a line"),
                                   ("stock_watcher", "x" * (mo.MAX_OFFERS_TEXT + 1), "At most")):
            with self.assertRaises(mo.Refused) as e:
                add(self.m, {"agent": [agent], "text": [text]})
            self.assertIn(words, str(e.exception))
        self.assertNotIn('id="of-h"', self.p.get("/agents/sales", {}, "t"))

    def report(self, **extra):
        item = dict({"agent": "sales", "run": "r1", "kind": "arena_rounds", "line": "Arena run r1.", "at": time.time(),
                     "gate_won": 5, "gate_played": 10, "needs": 7}, **extra)
        (self.folder / "arena-sales-r1.json").write_text(json.dumps(item), encoding="utf-8")

    def test_the_arena_item_shows_the_team_rate_and_the_sales_and_closes(self):
        self.page()
        self.report(gate_mix={"team_rate": {"won": 3, "chats": 40}}, sales=4, closes=1)
        page = self.p.get("/agents/sales", {"tab": ["arena"]}, "t")
        self.assertIn("The store team&#x27;s real rate on these customers: 3 of 40 chats. Report only; the bar stays "
                      "7 of 10.", page)
        self.assertIn("Won as a sale: 4. Won as a correct close: 1.", page)
        self.report(team_rate=[2, 30])
        page = self.p.get("/agents/sales", {"tab": ["arena"]}, "t")
        self.assertIn("2 of 30 chats", page)
        self.assertNotIn("Won as a sale", page)

    def test_an_item_without_them_or_with_odd_values_shows_no_line(self):
        self.page()
        self.report(team_rate={"won": 9, "chats": 3}, sales="4", closes=-1)
        page = self.p.get("/agents/sales", {"tab": ["arena"]}, "t")
        self.assertNotIn("real rate on these customers", page)
        self.assertNotIn("Won as a sale", page)
        self.assertEqual(mo.offer_lines({"team_rate": {"won": 1, "chats": 2}}),
                         ["The store team's real rate on these customers: 1 of 2 chats. Report only."])


if __name__ == "__main__":
    unittest.main()
