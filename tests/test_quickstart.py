"""Quick start (reflection/quickstart.py) on New agent: the card the model guesses, at most one
question, the second message written for the chat, an edit that rewrites the card, the plug folder
Build writes, the checker's refusal, slug and path attacks, the page's token and Origin checks, and
no key. A fake model only; nothing here calls the network."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

from engine import plug as plug_mod
from kit.db import Db
from reflection import morning as mo
from reflection import pages
from reflection import quickstart as qs
from tests.fake_model import FakeModel, say

ROOT = Path(__file__).resolve().parent.parent


def card_reply(name="Stock watcher", key="stock_watcher", question="Which store do you sell on?",
               follow="Here is my first guess. Add or change anything you like before I build it.", needs=None):
    return say(json.dumps({"card": {
        "name": name, "key": key, "does": "Checks stock every morning and tells you which items run low.",
        "good": "You hear about a low item a day before it runs out.",
        "never": ["Never orders stock by itself", "Never messages a supplier"],
        "needs": needs if needs is not None else [{"what": "Your store's stock", "tool": "store"},
                                                   {"what": "Bosta stock reports", "tool": "bosta"}]},
        "question": question, "follow": follow}))


def plug_dict(**over):
    d = {"agent": "anything", "about": "Watches stock and tells the user what runs low.",
         "case": "One day of stock checks; the case id is day:YYYY-MM-DD.", "fields": ["retail"], "stages": ["watching"],
         "actions": {"check": "Read the stock level of every product.", "alert": "Write the user a short note on low items."},
         "results": {"checked": {"speed": "fast", "shows_in_days": [0, 0], "after": "check"},
                     "alerted": {"speed": "fast", "shows_in_days": [0, 0], "after": "alert"},
                     "missed": {"speed": "fast", "shows_in_days": [0, 1]},
                     "day_clean": {"speed": "fast", "shows_in_days": [0, 1]}},
         "causes": {}, "source": {"about": "The day itself.", "known_by": "case"},
         "harm": {"results": ["missed"]}, "decides": {"good": "day_clean", "bad": ["missed"]},
         "risk": {"high": {"about": "Anything that goes out, money and numbers."}, "low": {"about": "The note's tone."}},
         "trial": {"fast": {"share": 0.9, "days": 1}, "careful": {"share": 0.9, "days": 1}},
         "exam": {"situations": "../../x.json", "checks": ["a"]}, "slot": "Lessons from past days:"}
    d.update(over)
    return d


def plug_reply(plug=None, instructions="You watch the store's stock and tell the user what runs low."):
    return say(json.dumps({"plug": plug if plug is not None else plug_dict(), "instructions": instructions}))


class QuickStartPage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(self.db.close)
        self.plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        self.m = mo.Morning(self.db, self.plugs, reports=self.folder)

    def page(self, *script):
        self.model = FakeModel(*script)
        self.p = pages.Pages(self.m, model=self.model)
        return self.p

    def send(self, text):
        return self.p.actions["/quickstart"](self.m, {"text": [text]})

    def build(self):
        return self.p.actions["/quickstart/build"](self.m, {})

    def get(self):
        return self.p.get("/new", {}, "t")

    def test_the_guess_card_is_shown(self):
        self.page(card_reply())
        before = self.get()
        self.assertIn("Start the build", before)
        self.assertNotIn('class="plan"', before)
        self.assertIsNone(self.send("i want an agent to track my stock in bosta"))
        page = self.get()
        for words in ("Stock watcher", "Checks stock every morning", "a day before it runs out",
                      "Never orders stock by itself", "Your store&#x27;s stock", "Connected: Store",
                      "Bosta stock reports", "Not connected yet", "i want an agent to track my stock in bosta"):
            self.assertIn(words, page)
        self.assertIn('action="/quickstart/build"', page)
        self.assertIn('action="/quickstart"', page)
        self.assertNotIn("—", page.split("</style>")[1])
        sent = self.model.calls[0]["messages"]
        self.assertEqual(sent[-1], {"role": "user", "content": "i want an agent to track my stock in bosta"})
        self.assertIn("at most one question", sent[0]["content"])

    def test_at_most_one_question(self):
        self.page(card_reply(question="Which store do you use? And which city are you in?",
                             follow="Is that right? You can add or change anything before it builds."))
        self.send("an agent for my stock")
        page = self.get().split("</style>")[1]
        self.assertIn('<p class="uq" dir="auto">Which store do you use?</p>', page)
        self.assertNotIn("which city", page)
        body = page.split('class="thread"')[1].split('<form id="qs-say"')[0]
        self.assertLessEqual(body.count("?"), 1)
        self.assertEqual(qs.one_question("A? B? C?"), "A?")
        self.assertEqual(qs.one_question("هل عندك متجر؟ وفين؟"), "هل عندك متجر؟")

    def test_no_question_when_nothing_matters(self):
        self.page(card_reply(question=""))
        self.send("an agent for my stock")
        self.assertNotIn('class="uq"', self.get())

    def test_the_second_message_is_written_for_each_chat(self):
        one = "Your stock watcher is ready to shape. Change any line you like before it builds."
        two = "That is my guess for your clinic bookings. Add whatever I missed before it builds."
        self.page(card_reply(follow=one))
        self.send("an agent for my stock")
        first = self.get()
        self.assertIn(f'<p class="uf" dir="auto">{one}</p>', first)
        self.p.actions["/quickstart/clear"](self.m, {})
        self.model.script.append(card_reply(name="Clinic desk", key="clinic_desk", follow=two))
        self.send("an agent that books my clinic patients")
        second = self.get()
        self.assertIn(two, second)
        self.assertNotIn(one, second)
        source = (ROOT / "reflection" / "quickstart.py").read_text(encoding="utf-8") + \
            (ROOT / "reflection" / "pages.py").read_text(encoding="utf-8")
        self.assertNotIn(one, source)
        self.assertNotIn(two, source)

    def test_no_second_message_means_no_card_and_no_stand_in_words(self):
        self.page(card_reply(follow=""))
        with self.assertRaises(mo.Refused):
            self.send("an agent for my stock")
        self.assertNotIn('class="uf"', self.get())
        self.assertFalse((self.folder / qs.DRAFT_FILE).exists())

    def test_an_answer_rewrites_the_card(self):
        self.page(card_reply(), card_reply(name="Shopify stock alert", key="shopify_stock_alert", question=""))
        self.send("an agent for my stock")
        self.send("I sell on Shopify, call it Shopify stock alert")
        page = self.get()
        self.assertIn("Shopify stock alert", page)
        self.assertNotIn("<h3 dir=\"auto\">Stock watcher</h3>", page)
        sent = self.model.calls[1]["messages"]
        self.assertEqual([x["role"] for x in sent], ["system", "user", "assistant", "user"])
        self.assertIn("Stock watcher", sent[2]["content"])
        self.assertEqual(page.count('class="plan"'), 1)

    def test_build_writes_the_plug_folder(self):
        self.page(card_reply(), plug_reply())
        self.send("an agent for my stock")
        said = self.build()
        self.assertIn("agents/stock_watcher", said)
        where = self.folder / "agents" / "stock_watcher"
        self.assertEqual(sorted(p.name for p in where.iterdir()), sorted(qs.FILES))
        plug = plug_mod.load(where / "plug.json")
        self.assertEqual(plug.agent, "stock_watcher")
        self.assertIsNone(plug.exam)
        self.assertEqual({k: (v.share, v.days) for k, v in plug.levels.items()}, {"fast": (0.5, 7), "careful": (0.2, 14)})
        self.assertIn("store", plug.risk.tools)
        self.assertIn(("number", "[0-9]"), plug.risk.patterns)
        card = json.loads((where / "card.json").read_text(encoding="utf-8"))
        self.assertEqual(card["good"], "You hear about a low item a day before it runs out.")
        self.assertEqual(card["tools"], ["store"])  # Bosta is not in the repo: on the card, not connected, not in the plug
        self.assertEqual([n["connected"] for n in card["needs"]], [True, False])
        self.assertIn("watch the store", (where / "instructions.md").read_text(encoding="utf-8"))
        self.assertIn("Built. Its files are in agents/stock_watcher", self.get())
        self.assertIn("level", card)
        self.assertNotIn("bosta", json.dumps(json.loads((where / "plug.json").read_text(encoding="utf-8"))["risk"]))

    def test_an_invalid_plug_is_fixed_once_or_refused(self):
        bad = plug_dict(decides={"good": "nothing_declared", "bad": []})
        self.page(card_reply(), plug_reply(bad), plug_reply())
        self.send("an agent for my stock")
        said = self.build()
        self.assertIn("failed the check", said)
        self.assertIn("not a declared result", said)
        fix = self.model.calls[2]["messages"][-1]["content"]
        self.assertIn("not a declared result", fix)
        self.assertTrue((self.folder / "agents" / "stock_watcher" / "plug.json").is_file())

    def test_a_plug_never_sends_a_chat_to_a_person(self):
        self.assertNotIn("handoff", qs.TOOLS)
        self.assertIsNotNone(qs.check_plug(qs.clean_plug(plug_dict(stages=["watching", "with_person"]), "a", [])))
        self.page(card_reply(needs=[{"what": "A person to take over", "tool": "handoff"}]))
        self.send("an agent for my stock")
        self.assertIn("Not connected yet", self.get())

    def test_a_plug_that_fails_twice_writes_nothing(self):
        bad = plug_dict(results={})
        self.page(card_reply(), plug_reply(bad), say("not json at all"))
        self.send("an agent for my stock")
        with self.assertRaises(mo.Refused) as e:
            self.build()
        self.assertIn("Not built", str(e.exception))
        self.assertIn("Nothing was written", str(e.exception))
        agents = self.folder / "agents"
        self.assertEqual(list(agents.iterdir()) if agents.exists() else [], [])

    def test_slug_and_path_attacks(self):
        self.assertEqual(qs.slug("../../etc/passwd"), "etc_passwd")
        self.assertEqual(qs.slug("/abs/path"), "abs_path")
        self.assertEqual(qs.slug("Stock Watcher!"), "stock_watcher")
        self.assertEqual(qs.slug("..\\..\\win"), "win")
        self.assertEqual(len(qs.slug("a" * 300)), 41)
        for bad in ("..", "../..", "", "12345", "مساعد المخزون", "/"):
            with self.assertRaises(qs.Refused):
                qs.slug(bad)

    def test_a_name_with_path_parts_stays_under_agents(self):
        self.page(card_reply(name="../../outside", key="../../../outside"), plug_reply())
        self.send("an agent for my stock")
        self.build()
        self.assertTrue((self.folder / "agents" / "outside" / "plug.json").is_file())
        self.assertFalse((self.folder.parent / "outside").exists())

    def test_an_agents_link_is_refused(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        os.symlink(other.name, self.folder / "agents")
        self.page(card_reply(), plug_reply())
        self.send("an agent for my stock")
        with self.assertRaises(mo.Refused):
            self.build()
        self.assertEqual(os.listdir(other.name), [])

    def test_a_taken_name_is_refused(self):
        self.page(card_reply(name="Sales", key="sales"))
        self.send("a sales agent")
        with self.assertRaises(mo.Refused):
            self.build()
        self.page(card_reply())
        self.send("an agent for my stock")
        (self.folder / "agents" / "stock_watcher").mkdir(parents=True)
        with self.assertRaises(mo.Refused):
            self.build()
        self.assertEqual(os.listdir(self.folder / "agents" / "stock_watcher"), [])

    def test_untrusted_words_are_escaped_and_capped(self):
        self.page(card_reply(name="<script>alert(1)</script>" + "x" * 200, key="ok_name",
                             needs=[{"what": '<img src=x onerror="a()">', "tool": "../store"}] * 20))
        self.send("<b>hi</b>")
        page = self.get().split("</style>")[1]
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img", page)
        self.assertNotIn("<b>hi</b>", page)
        self.assertIn("&lt;script&gt;", page)
        card = qs.QuickStart().draft(self.m)["turns"][-1]["card"]
        self.assertLessEqual(len(card["name"]), qs.CAPS["name"])
        self.assertEqual(len(card["needs"]), qs.MOST_NEEDS)
        self.assertFalse(any(n["connected"] for n in card["needs"]))
        with self.assertRaises(mo.Refused):
            self.send("x" * (qs.MAX_TEXT + 1))

    def test_model_calls_are_capped_each_minute(self):
        self.page(*[card_reply() for _ in range(qs.CALLS_PER_MINUTE + 1)])
        for _ in range(qs.CALLS_PER_MINUTE):
            self.p.actions["/quickstart/clear"](self.m, {})
            self.send("an agent for my stock")
        with self.assertRaises(mo.Refused):
            self.send("one more")

    def test_no_key_says_so_plainly(self):
        env = {k: v for k, v in os.environ.items() if k not in ("META_API_KEY", "BASETEN_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True):
            p = pages.Pages(self.m)
            page = p.get("/new", {}, "t")
            self.assertIn("No model key is set", page)
            with self.assertRaises(mo.Refused) as e:
                p.actions["/quickstart"](self.m, {"text": ["an agent for my stock"]})
            self.assertIn("No model key is set", str(e.exception))

    def test_no_database_folder_says_so(self):
        m = mo.Morning(self.db, self.plugs)
        p = pages.Pages(m, model=FakeModel())
        self.assertIn("needs the database folder", p.get("/new", {}, "t"))
        with self.assertRaises(mo.Refused):
            p.actions["/quickstart"](m, {"text": ["an agent"]})

    def test_a_broken_draft_file_reads_as_empty(self):
        (self.folder / qs.DRAFT_FILE).write_text('{"turns": [{"card": "x"}]}', encoding="utf-8")
        self.page()
        self.assertNotIn('class="plan"', self.get())


class QuickStartServer(unittest.TestCase):
    """The server's token, Origin and Host checks on every Quick start POST."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json")], reports=self.folder)
        self.model = FakeModel(card_reply(), plug_reply())
        self.server = mo.make_server(self.m, port=0, pages=pages.Pages(self.m, model=self.model))
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(5)
        self.addCleanup(stop)

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def fetch(self, path):
        with urllib.request.urlopen(self.url(path), timeout=10) as r:
            return r.read().decode("utf-8")

    def post(self, path, fields, origin=None, token=None):
        if token is None:
            token = self.fetch("/new").split('name="token" value="')[1].split('"')[0]
        body = urllib.parse.urlencode(([("token", token)] if token else []) + list(fields)).encode()
        req = urllib.request.Request(self.url(path), data=body, method="POST", headers={
            "Origin": origin or f"http://127.0.0.1:{self.port}", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # the 303 back to /new, followed
                self.last = r.read().decode("utf-8")
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_token_and_origin_are_checked(self):
        fields = [("back", "/new"), ("text", "an agent for my stock")]
        self.assertEqual(self.post("/quickstart", fields, token=""), 403)
        self.assertEqual(self.post("/quickstart", fields, token="wrong"), 403)
        self.assertEqual(self.post("/quickstart", fields, origin="http://evil.example"), 403)
        self.assertEqual(self.post("/quickstart/build", [("back", "/new")], token="wrong"), 403)
        self.assertEqual(self.model.calls, [])
        self.assertFalse((self.folder / qs.DRAFT_FILE).exists())
        self.assertEqual(self.post("/quickstart", fields), 200)  # 303 back to /new, followed
        self.assertIn("Stock watcher", self.fetch("/new"))
        self.assertEqual(self.post("/quickstart/build", [("back", "/new")]), 200)
        self.assertTrue((self.folder / "agents" / "stock_watcher" / "plug.json").is_file())
        self.assertIn("Built Stock watcher", self.last)  # the flash, shown once

    def test_the_page_keeps_its_policy(self):
        with urllib.request.urlopen(self.url("/new"), timeout=10) as r:
            csp = r.headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertNotIn("script-src", csp)


if __name__ == "__main__":
    unittest.main()
