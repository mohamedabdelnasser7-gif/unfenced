"""Any agent, round 2 (2026-11-04): what three agents built on the real model showed (a support desk, a
gym lead follower, a coffee caption writer). tests/three_agents.json holds their cards, plugs, first
instructions and night lessons as the real model wrote them; nothing here calls the network."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from engine import plug as plug_mod
from engine import risk as risk_mod
from kit import send_check, turn
from kit.chats import Chats
from kit.db import Db
from reflection import quickstart as qs
from tests.fake_model import FakeModel, clean_env, say, tool_call
from tests.test_any_agent import PageCase
from tests.test_console import Base as ConsoleBase
from engine import lessons as lessons_mod
from reflection import console

THREE = json.loads((Path(__file__).resolve().parent / "three_agents.json").read_text(encoding="utf-8"))


def cleaned(name):
    """The agent's plug as Build writes it now: the model's plug through clean_plug with its card."""
    a = THREE[name]
    raw = {k: v for k, v in a["plug"].items() if k != "exam"}
    return plug_mod.from_dict(qs.clean_plug(raw, name, a["card"]["tools"], a["card"]))


def low(text, high_about, low_about):
    return risk_mod.LOW  # the judge's clear low, so only the code check can make a lesson high


class OwnWorkIsNotHighRisk(unittest.TestCase):
    """Every night lesson of a built agent waited for a yes (9 of 9): any digit was high, and the model put
    the agent's own work (reply, caption, trial, book, next step, time) in its high words."""

    def test_the_nine_night_lessons_are_low_except_the_one_on_fees_and_refunds(self):
        got = {}
        for name, a in THREE.items():
            plug = cleaned(name)
            for n, text in enumerate(a["lessons"], 1):
                got[(name, n)] = risk_mod.classify(text, plug.risk, low)
        highs = {k: why for k, (level, why) in got.items() if level == risk_mod.HIGH}
        self.assertEqual(sorted(highs), [("support_calm_helper", 2)], highs)
        why = highs[("support_calm_helper", 2)]
        self.assertIn("money: fee", why)
        self.assertIn("money: refund", why)
        self.assertEqual(len(got), 9)

    def test_the_old_plugs_marked_all_nine(self):
        """The plugs as the model wrote them: every lesson high from the code check alone."""
        for name, a in THREE.items():
            plug = plug_mod.from_dict({k: v for k, v in a["plug"].items() if k != "exam"})
            for text in a["lessons"]:
                self.assertTrue(risk_mod.code_check(text, plug.risk), (name, text))

    def test_money_refunds_personal_data_and_outside_promises_stay_high_for_every_agent(self):
        risky = ["Offer a 20% discount to a lead who hesitates.", "Say the price is 450 when asked.",
                 "Mention the 1,200 pound package.", "Tell them the refund goes out today.",
                 "Offer a replacement for any broken item.", "Ask for their home address before booking.",
                 "Send the customer's address with the reply.", "Share the lead's phone number with the coach.",
                 "Promise the order will arrive tomorrow.", "Guarantee delivery by Sunday.",
                 "Add a payment link to the caption.", "Waive the fee for late orders.",
                 "Tell the customer the courier will deliver it today.", "قول للعميل ان الخصم ٢٠٪."]
        for name in THREE:
            plug = cleaned(name)
            for text in risky:
                level, why = risk_mod.classify(text, plug.risk, low)
                self.assertEqual(level, risk_mod.HIGH, (name, text))

    def test_counts_times_and_the_verb_address_are_not_money(self):
        plug = cleaned("support_calm_helper")
        for text in ["Keep the reply to 3 short lines.", "Answer within 2 minutes of the ticket.",
                     "Address their worry first, then give the next step.", "Ask for one photo of the item.",
                     "Reply to the ticket and tag it as late."]:
            self.assertEqual(risk_mod.code_check(text, plug.risk), [], text)

    def test_the_cleaner_drops_own_work_vague_words_tool_names_and_every_number_patterns(self):
        card = {"does": "Writes a short reply to each ticket and tags it.",
                "case": {"input": "a ticket", "starts": "person", "output": "a reply and a tag",
                         "ends": "when the reply is sent"}}
        risk = {"high": {"about": "Anything that goes out.", "words": {
                    "goes_out": ["reply", "send", "replies", "forward", "orders"], "promise": ["next step", "time", "refund"],
                    "personal_data": ["name", "address", "phone"]},
                    "patterns": {"number": ["[0-9]", "\\d+"], "personal_data": ["@"]}, "tools": ["x"]},
                "low": {"about": "Tone."}}
        out = qs.clean_risk(risk, card, ["orders"])
        words = out["high"]["words"]
        self.assertEqual(words["goes_out"], ["forward"])
        self.assertEqual(words["promise"][0], "refund")
        self.assertNotIn("next step", words["promise"])
        self.assertEqual(words["personal_data"][0], "phone")
        self.assertNotIn("address", words["personal_data"])  # the pattern reads it, never the verb
        self.assertNotIn("number", out["high"]["patterns"])
        self.assertEqual(out["high"]["patterns"]["personal_data"][0], "@")
        self.assertEqual(out["high"]["tools"], ["orders"])
        self.assertEqual(out["high"]["about"], qs.HIGH_ABOUT)
        self.assertIn("a reply and a tag", out["low"]["about"])
        self.assertTrue(out["low"]["about"].endswith("Tone."))
        for group, items in qs.CORE_WORDS.items():
            self.assertTrue(set(items) <= set(words[group]))

    def test_the_build_prompt_asks_the_same(self):
        self.assertIn("Its normal work is never high", qs.BUILD_PROMPT)
        self.assertNotIn("anything that goes out in the user's name", qs.BUILD_PROMPT)


def agent_folder(root, name, instructions=None):
    """One of the three agents as Build writes its folder now, under root/agents/<name>."""
    a = THREE[name]
    folder = Path(root) / "agents" / name
    folder.mkdir(parents=True)
    raw = {k: v for k, v in a["plug"].items() if k != "exam"}
    (folder / "plug.json").write_text(json.dumps(qs.clean_plug(raw, name, a["card"]["tools"], a["card"])),
                                      encoding="utf-8")
    (folder / "card.json").write_text(json.dumps(a["card"]), encoding="utf-8")
    (folder / "instructions.md").write_text(instructions or a["instructions"], encoding="utf-8")
    return folder


class TheirOwnNumbers(unittest.TestCase):
    """A support agent's reply that named the customer's postal code 6000 failed "amounts not in the store
    data": the Sales agent's whole amounts rule judged an agent that quotes no prices."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    NOT_PRICES = ["Your order ORD-1004 to 45 Rue Habib Bourguiba, Gabes 6000 is on its way.",
                  "Ticket 48213 is tagged as late.", "Your order 6000 left the warehouse.",
                  "We open at 10:30 on 12 Nov, see you then.", "You have 150 points so far.",
                  "Your trial is on Tuesday at 6pm, for 1500 seconds of fun."]
    PRICES = ["The delivery fee is 85 EGP.", "It costs 450.", "The price is 300 for the month.",
              "Shipping comes to 120.", "That is 999 جنيه."]

    def test_only_prices_and_fees_are_held_to_the_data_for_any_agent_but_sales(self):
        for text in self.NOT_PRICES:
            self.assertEqual(send_check.check(text, text, priced_only=True, stock=False), (True, ""), text)
        for text in self.PRICES:
            passed, why = send_check.check(text, text, priced_only=True)
            self.assertFalse(passed, text)
            self.assertIn("amounts are not in the store", why)
        self.assertTrue(send_check.check("The delivery fee is 85 EGP.", "", amounts=[85], priced_only=True)[0])

    def test_the_sales_check_is_whole(self):
        for text in self.NOT_PRICES[:3]:
            passed, why = send_check.check(text, text)
            self.assertFalse(passed, text)
            self.assertIn("amounts are not in the store", why)
        self.assertFalse(send_check.check("Only 3 left in your size.", "")[0])
        self.assertTrue(send_check.check("Only 3 left in your size.", "", priced_only=True, stock=False)[0])

    def test_a_built_agent_reads_prices_only_and_the_stock_rule_only_with_the_store(self):
        agent = turn.load(agent_folder(self.root, "support_calm_helper"))
        self.assertEqual((agent.full_check, agent.priced_only, agent.stock), (True, True, False))
        leads = turn.load(agent_folder(self.root, "lead_trial_booker"))
        self.assertEqual((leads.full_check, leads.priced_only, leads.stock), (True, True, False))

    def turn(self, agent, reply):
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "c1")
        sent = []
        out = turn.turn(agent, "Where is my order?", chats=chats, chat_id=cid, model=FakeModel(*[say(reply)] * 4),
                        send=lambda to, text: sent.append(text), customer_id="c1")
        return out, sent

    def test_the_support_agent_names_the_postal_code_and_a_made_up_fee_is_still_refused(self):
        agent = turn.load(agent_folder(self.root, "support_calm_helper"))
        out, sent = self.turn(agent, self.NOT_PRICES[0])
        self.assertEqual((out.outcome, sent), ("replied", [self.NOT_PRICES[0]]))
        out, sent = self.turn(agent, "The delivery fee is 999 EGP.")
        self.assertEqual((out.outcome, sent), ("no_safe_reply", []))
        out, sent = self.turn(agent, "Your order is on its way \u2014 sorry for the wait.")
        self.assertEqual((out.outcome, sent), ("no_safe_reply", []))  # house style holds for every agent


class HouseStyleInTheInstructions(unittest.TestCase):
    """The three agents' instructions never said the house style, so first replies failed on dashes and **."""

    def test_none_of_the_three_said_it_and_build_adds_it(self):
        for name, a in THREE.items():
            self.assertNotIn("dash", a["instructions"].lower(), name)
            plug = {k: v for k, v in a["plug"].items() if k != "exam"}
            got, words, why = qs.QuickStart._plug_from(
                json.dumps({"plug": plug, "instructions": a["instructions"]}), name, a["card"]["tools"], a["card"])
            self.assertIsNone(why, name)
            self.assertTrue(words.startswith(a["instructions"].strip()))
            self.assertTrue(words.startswith(f"{a['instructions'].strip()}\n\n{qs.HOUSE_STYLE}"))  # then how it acts
            self.assertEqual(words.count(qs.HOUSE_STYLE), 1)
        for rule in ("markdown", "**", "em or en dashes", "emoji"):
            self.assertIn(rule, qs.HOUSE_STYLE)
        self.assertEqual(send_check.style_problems(qs.HOUSE_STYLE.replace("**", "")), [])


class EveryStepHasAnAction(unittest.TestCase):
    """The judge failed the support agent for a ticket it never tagged (tag_ticket was declared, but its
    instructions never named take_action or the step) and the leads agent for a trial it never booked (no
    action could book it: the prompt said to leave out anything not connected, and the calendar was not)."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    def built(self, name):
        a = THREE[name]
        plug = {k: v for k, v in a["plug"].items() if k != "exam"}
        got, words, why = qs.QuickStart._plug_from(
            json.dumps({"plug": plug, "instructions": a["instructions"]}), name, a["card"]["tools"], a["card"])
        self.assertIsNone(why, name)
        return got, words

    def test_the_steps_each_case_end_and_good_line_name(self):
        self.assertEqual(qs.steps(THREE["support_calm_helper"]["card"]), [("ticket", "tagged")])
        self.assertEqual(qs.steps(THREE["lead_trial_booker"]["card"]), [("trial session", "booked")])
        self.assertEqual(qs.steps(THREE["coffee_caption_writer"]["card"]), [])  # delivered: the reply does it
        card = {"case": {"ends": "when the lead is not interested or the order is not booked"},
                "good": "The customer is happy and the refund is approved."}
        self.assertEqual(qs.steps(card), [("refund", "approved")])
        self.assertEqual(qs.steps({}), [])
        self.assertEqual(qs.steps({"case": "x", "good": None}), [])

    def test_only_the_leads_agent_gets_a_booking_action_and_it_says_the_calendar_is_not_connected(self):
        support, _ = self.built("support_calm_helper")
        self.assertEqual(support["actions"], THREE["support_calm_helper"]["plug"]["actions"])
        writer, _ = self.built("coffee_caption_writer")
        self.assertEqual(writer["actions"], THREE["coffee_caption_writer"]["plug"]["actions"])
        leads, _ = self.built("lead_trial_booker")
        before = THREE["lead_trial_booker"]["plug"]["actions"]
        self.assertEqual(list(leads["actions"]), list(before) + ["mark_trial_session_booked"])
        said = leads["actions"]["mark_trial_session_booked"]
        self.assertIn("trial session is booked", said)
        self.assertIn("Calendar to book trial sessions is not connected yet", said)
        self.assertIsNone(qs.check_plug(leads))
        connected = json.loads(json.dumps(THREE["lead_trial_booker"]["card"]))
        connected["needs"][2]["connected"] = True
        self.assertNotIn("not connected", qs.add_steps(before, connected)["mark_trial_session_booked"])

    def test_the_instructions_say_how_to_take_each_step_and_name_the_real_tools(self):
        for name, a in THREE.items():
            plug, words = self.built(name)
            self.assertIn(qs.ACT_NOTE, words, name)
            self.assertIn("take_action", words)
            for act in plug["actions"]:
                if act != "reply":
                    self.assertIn(f"{act} (", words, (name, act))
            self.assertIn(f"The case ends {a['card']['case']['ends']}", words)
            self.assertEqual(words.count(qs.HOUSE_STYLE), 1)
        _, words = self.built("support_calm_helper")
        tools_line = next(x for x in words.splitlines() if x.startswith("Your tools: "))
        named = set(tools_line[len("Your tools: "):].split(".")[0].split(", "))
        self.assertEqual(named, {"find_order", "draft_order", "delivery"})
        for name in ("lead_trial_booker", "coffee_caption_writer"):  # WhatsApp is the channel, no tool to run
            self.assertNotIn("Your tools:", self.built(name)[1], name)

    def test_the_built_leads_agent_is_offered_the_booking_and_a_turn_records_it(self):
        agent = turn.load(agent_folder(self.root, "lead_trial_booker"))
        self.assertIn("mark_trial_session_booked", agent.acts)
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open("whatsapp", "c1")
        model = FakeModel(tool_call(turn.ACT_TOOL, {"action": "mark_trial_session_booked", "note": "Tuesday 6pm"}),
                          *[say("See you Tuesday at 6pm for your free trial.")] * 4)
        out = turn.turn(agent, "Tuesday at 6 works for me", chats=chats, chat_id=cid, model=model,
                        send=lambda to, text: None, customer_id="c1")
        self.assertEqual(out.outcome, "replied")
        self.assertEqual(out.actions, [{"action": "mark_trial_session_booked", "note": "Tuesday 6pm"}])

    def test_the_card_says_before_build_that_it_records_the_booking_until_the_calendar_is_connected(self):
        from reflection import pages
        wait = pages.STEP_WAIT.format(thing="trial session", done="booked")
        html = pages.plan_card(THREE["lead_trial_booker"]["card"])
        self.assertEqual(html.count(wait), 1)
        tile = html[html.index("calendar to book trial sessions"):]
        self.assertLess(tile.index(wait), tile.index("</div>"))
        connected = json.loads(json.dumps(THREE["lead_trial_booker"]["card"]))
        connected["needs"][2]["connected"] = True
        self.assertNotIn("Until it is connected", pages.plan_card(connected))
        for name in ("support_calm_helper", "coffee_caption_writer"):
            self.assertNotIn("Until it is connected", pages.plan_card(THREE[name]["card"]), name)

    def test_the_build_prompt_asks_for_every_step_as_an_action(self):
        self.assertIn("declare it as an action the agent records", qs.BUILD_PROMPT)
        self.assertIn("instructions say when it takes each declared action", qs.BUILD_PROMPT)
        self.assertNotIn("is not connected yet: leave it out", qs.BUILD_PROMPT)


def tiles(html):
    """Each need tile of a card, from its start to the next tile's (the last one to the card's end)."""
    cuts = [m.start() for m in re.finditer(r'<details class="need">|<div class="file on">', html)]
    return [html[x:y] for x, y in zip(cuts, cuts[1:] + [len(html)])]


class ConnectionTiles(unittest.TestCase):
    """The + on a need tile was only an icon: nothing told the user how to connect it or what to do instead."""

    def setUp(self):
        from unittest import mock
        import os
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SHOPIFY", "WHATSAPP"))}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def card(self, needs):
        return dict(THREE["lead_trial_booker"]["card"], needs=needs)

    def test_each_tile_opens_how_to_connect_that_one_need_with_a_sheet_and_mcp_greyed(self):
        from reflection import pages
        html = pages.plan_card(THREE["lead_trial_booker"]["card"])
        got = tiles(html)
        self.assertEqual(len(got), 3)
        for t in got:
            self.assertTrue(t.startswith('<details class="need"><summary class="file"'), t)
            self.assertIn(pages.icon("plus"), t[:t.index("</summary>")])
            self.assertIn(pages.SHEET + "</b>" + pages.SHEET_LATER, t)  # before Build: no box to link to yet
            self.assertEqual(t.count(pages.MCP_NEXT), 1)
        leads, chat, calendar = got
        self.assertIn(pages.HOW_OTHER, leads)
        self.assertIn(pages.HOW_OTHER, calendar)
        for key in ("WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"):
            self.assertIn(key, chat)
        self.assertIn(pages.QUICK_NEXT.format(name="WhatsApp"), chat)
        self.assertNotIn("Connected", html)  # WhatsApp is on the card as connected, but no keys are set
        self.assertNotIn('href="#', html)
        self.assertNotIn("<a", html.split(pages.MCP_NEXT)[0][-200:])

    def test_the_sheet_links_to_the_add_data_box_once_it_is_on_the_page(self):
        from reflection import pages
        html = pages.plan_card(THREE["lead_trial_booker"]["card"], sheet=True)
        self.assertEqual(html.count(f'<a href="#{pages.DATA_ID}">{pages.SHEET}</a>{pages.SHEET_NOW}'), 3)
        self.assertIn(f'id="{pages.DATA_ID}"', pages.data_form({"token": "t", "q": "", "path": "/new"}, "x"))

    def test_the_store_tile_says_connected_only_with_its_keys_and_any_tool_gets_a_plain_line(self):
        from unittest import mock
        import os
        from reflection import pages
        needs = [{"what": "Your store's products", "tool": "store", "connected": True},
                 {"what": "Your CRM contacts", "tool": "crm", "connected": False},
                 {"what": "Orders", "tool": "orders", "connected": True}]
        html = pages.plan_card(self.card(needs))
        store, crm, orders = tiles(html)
        self.assertIn(pages.HOW_STORE, store)
        self.assertIn(pages.STORE_SAMPLE, store)
        self.assertNotIn("Connected", store)
        self.assertIn(pages.HOW_OTHER, crm)
        self.assertTrue(orders.startswith('<div class="file on">'))  # no keys needed: connected, no + to open
        self.assertIn(pages.MCP_NEXT, orders)
        self.assertNotIn("<details", orders)
        with mock.patch.dict(os.environ, {"SHOPIFY_STORE": "x.myshopify.com", "SHOPIFY_TOKEN": "t"}):
            store = tiles(pages.plan_card(self.card(needs)))[0]
        self.assertTrue(store.startswith('<div class="file on">'))
        self.assertIn("Connected: Store", store)
        self.assertIn(pages.MCP_NEXT, store)


class TilesOnThePage(PageCase):
    """On the page: Build stays open with every need unconnected, and once built the sheet line reaches the box."""

    def test_build_is_offered_with_nothing_connected_and_the_built_page_links_the_box(self):
        from reflection import pages
        from tests.test_quickstart import card_reply, exam_reply, no_keys, plug_reply
        from tests.test_any_agent import sample_reply
        self.m.db_path = str(self.folder / "ascent.db")  # the live page, so the built agent joins it
        with no_keys():
            self.page(card_reply(), plug_reply(), exam_reply(), sample_reply())
            self.send("an agent for my stock")
            before = self.get()
            self.assertIn('action="/quickstart/build"', before)
            self.assertEqual(before.count('<details class="need">'), 2)
            self.assertNotIn(f'href="#{pages.DATA_ID}"', before)
            self.build()
            after = self.get()
        self.assertIn(f'id="{pages.DATA_ID}"', after)
        self.assertEqual(after.count(f'href="#{pages.DATA_ID}"'), 2)



class WhyItWaits(ConsoleBase):
    """The console showed HELD with no reason: nobody could tell a lesson waited for its money words."""

    HIGH = "Waive the delivery fee and offer a refund when the order is late."
    LOW = "Greet the customer warmly before you answer."

    def setUp(self):
        super().setUp()
        self.plug = self.m.plugs["sales"]
        les = lessons_mod.Lessons(self.db, self.plug, judge=lambda *a: risk_mod.LOW)
        self.high = les.propose(self.HIGH, ["all"], source="night study", sources=[])
        self.low = les.propose(self.LOW, ["all"], source="night study", sources=[])

    def rows(self):
        with self.db.tx() as c:
            return [tuple(r) for r in c.execute("SELECT * FROM lessons ORDER BY id")]

    def test_a_high_lesson_says_why_from_the_risk_check_and_a_low_one_says_nothing(self):
        before = self.rows()
        data = console.collect(self.m, "sales")
        rows = {x["id"]: x for x in data["lessons"]}
        level, found = risk_mod.classify(self.HIGH, self.plug.risk, lambda *a: risk_mod.LOW)
        self.assertEqual(level, risk_mod.HIGH)
        why = rows[self.high]["why"]
        self.assertEqual(why, console.risk_reason("; ".join(found)))
        self.assertTrue(why.startswith("high risk: "), why)
        self.assertIn("refund", why)
        self.assertEqual(rows[self.low]["why"], "")
        table = self.page(view="reflect")
        self.assertEqual(table.count('<small class="why">'), 1)
        self.assertIn(f'{self.HIGH}</a><small class="why">{console.h(why)}</small>', table)
        dec = self.page(view="reflect", row=f"l.{self.high}", pane="dec").split('class="drawer"')[1]
        self.assertIn("Why it waits", dec)
        self.assertIn(console.h(why), dec)
        low = self.page(view="reflect", row=f"l.{self.low}", pane="dec").split('class="drawer"')[1]
        self.assertNotIn("Why it waits", low)
        self.assertNotIn("high risk", low)
        self.assertEqual(self.rows(), before)  # read only

    def test_the_reason_reads_every_kind_of_saved_line_and_never_fills_in(self):
        self.assertEqual(console.risk_reason("money: fee; money: refund"), "high risk: money (fee, refund)")
        self.assertEqual(console.risk_reason("core: link; personal_data: phone; money: /\\d{3,}/; tool: orders"),
                         "high risk: link, personal data (phone), money, tool (orders)")
        self.assertEqual(console.risk_reason("judge: unsure, counted as high"), "high risk: judge unsure")
        for empty in (None, "", " "):
            self.assertEqual(console.risk_reason(empty), f"high risk: {console.NOT_SAVED}")
        with self.db.tx() as c:  # a high lesson saved with no reasons: the console says so, never guesses one
            bare = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, source, origin, kind, "
                             "added_at) VALUES ('sales', 'Offer the bundle.', ',all,', ',,', 'high', 'waiting', "
                             "'seed', 'agent', 'pattern', 1)").lastrowid
        rows = {x["id"]: x for x in console.collect(self.m, "sales")["lessons"]}
        self.assertEqual(rows[bare]["why"], f"high risk: {console.NOT_SAVED}")
        self.assertNotIn(console.NOT_SAVED, rows[self.high]["why"])


class SampleDataInTheConsole(PageCase):
    def setUp(self):
        PageCase.setUp(self)
        self.m.db_path = str(self.folder / "ascent.db")

    def test_a_built_agent_shows_its_sample_data_line_as_on_its_card(self):
        from tests.test_any_agent import CARD_LINE, sample_reply
        from tests.test_quickstart import card_reply, exam_reply, no_keys, plug_reply
        with no_keys():
            self.page(card_reply(), plug_reply(), exam_reply(), sample_reply())
            self.send("an agent for my stock")
            self.build()
            page = self.p.get("/console", {"agent": ["stock_watcher"]}, "t")
            sales = self.p.get("/console", {"agent": ["sales"]}, "t")
        self.assertEqual(page.count('<p class="sline mono">'), 1)
        self.assertIn(f'<p class="sline mono">{console.h(CARD_LINE)}</p>', page)
        self.assertNotIn('class="sline', sales)



# The meal planner as the real model wrote its card on 2026-11-04: two needs only the user can tell, and
# no question at all (the prompt let it ask only about where a case ends).
MEAL = {"name": "Weekly Dinner Planner", "key": "weekly_dinner_planner", "kind": "meal_planning",
        "does": "It creates a balanced seven day dinner plan and a clear grocery list for you.",
        "case": {"input": "a request for next weeks dinners", "starts": "person",
                 "output": "a seven day dinner menu and its grocery list", "ends": "when the plan and list are sent"},
        "good": "Dinners are varied and easy to cook and the grocery list matches the meals exactly so shopping is simple.",
        "bad": "The plan repeats meals or the grocery list is missing items so you cannot shop or cook as planned.",
        "never": ["never includes ingredients you marked as allergy",
                  "never suggests a meal without adding its ingredients to the grocery list"],
        "needs": [{"what": "your food preferences and allergies", "tool": "", "ask": True},
                  {"what": "your household size and cooking time", "tool": "", "ask": True}]}
FOLLOW = "You can add or change anything before it builds."


def meal(question):
    return say(json.dumps({"card": MEAL, "question": question, "follow": FOLLOW}))


class AskOnce(PageCase):
    """The meal planner needed the user's preferences, allergies and household size, and asked nothing."""

    def draft(self):
        return json.loads((self.folder / qs.DRAFT_FILE).read_text(encoding="utf-8"))["turns"]

    def test_the_prompt_asks_for_a_need_only_the_user_can_tell_once(self):
        for part in ('"ask": true only when no tool or file holds it', "ask for that need",
                     "Never ask again for anything they already said or were asked here",
                     "They can build without answering"):
            self.assertIn(part, qs.CARD_PROMPT)
        self.assertNotIn("and only when where one case ends is unclear", qs.CARD_PROMPT)

    def test_ask_is_kept_only_on_a_need_no_tool_holds(self):
        card = dict(MEAL, needs=MEAL["needs"] + [{"what": "Your store's stock", "tool": "store", "ask": True},
                                                 {"what": "your hours", "tool": "", "ask": "yes"}])
        needs = qs.clean_card({"card": card, "question": "", "follow": FOLLOW})["card"]["needs"]
        self.assertEqual([n.get("ask") for n in needs], [True, True, None, None])

    def test_each_need_is_asked_once_and_never_again_once_answered(self):
        q1 = "What do you love to eat, and any allergies?"
        q2 = "How many people do you cook for, and how much time do you have?"
        self.page(meal(q1), meal("Any allergies I should know about?"), meal(q2), meal(q2), meal(""))
        self.send("a meal planner for my weekly dinners")
        self.assertIn(console.h(q1), self.get())
        self.send("No nuts, we love pasta and fish.")
        self.assertEqual(self.draft()[-1]["question"], "")  # allergies again: already asked and answered
        note = self.model.calls[1]["messages"][0]["content"]
        self.assertIn("Asked already, never ask again: your food preferences and allergies.", note)
        self.assertIn("Needs marked ask, not asked yet: your household size and cooking time.", note)
        self.send("Sounds good.")
        self.assertEqual(self.draft()[-1]["question"], q2)  # the other need, asked once
        self.send("Four of us, 30 minutes a night.")
        self.assertEqual(self.draft()[-1]["question"], "")  # the same question again
        self.send("Add a fish night.")
        note = self.model.calls[4]["messages"][0]["content"]
        self.assertIn("Needs marked ask, not asked yet: none.", note)
        self.assertNotIn("In this chat so far", self.model.calls[0]["messages"][0]["content"])
        self.assertEqual([qs.ask_once(q, MEAL, []) for q in (q1, "", q2)], [q1, "", q2])

    def test_build_never_waits_for_an_answer(self):
        from tests.test_quickstart import exam_reply, no_keys, plug_reply
        from tests.test_any_agent import sample_reply
        self.m.db_path = str(self.folder / "ascent.db")
        with no_keys():
            self.page(meal("What do you love to eat, and any allergies?"), plug_reply(), exam_reply(), sample_reply())
            self.send("a meal planner for my weekly dinners")
            page = self.get()
            self.assertIn('action="/quickstart/build"', page)
            self.assertTrue(self.build().startswith("Built Weekly Dinner Planner"))

    def test_the_tile_of_a_need_only_the_user_can_tell_says_to_say_it(self):
        from reflection import pages
        card = qs.clean_card({"card": MEAL, "question": "", "follow": FOLLOW})["card"]
        html = pages.plan_card(card)
        self.assertEqual(html.count(pages.HOW_ASK), 2)
        self.assertNotIn(pages.HOW_OTHER, html)


if __name__ == "__main__":
    unittest.main()
