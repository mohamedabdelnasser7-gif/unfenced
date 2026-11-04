"""The rules an agent is examined on are in its own prompt (DECISIONS item 94): the send check's style
and banned words, and for the full check sympathy lines, links, script, amount rules, prices and fees from
tools only and, where it is held, the stock count, read from the send check's own words
(kit/send_check.py prompt_rules), so the prompt and the check never drift apart. The Sales agent
(sales/loop.py) and any agent kit/turn.py runs (a card Quick start built, a folder written by hand) get
them, on every path: the live WhatsApp reply, the Arena, the exam, the built agent's exam and Try Sales.
Fake models only; nothing here calls the network or reads arena/real."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import factcheck, match
from channels import whatsapp as wa
from channels.base import Message
from kit import send_check, turn
from kit.chats import Chats
from kit.db import Db
from reflection import PLUG, exam, turn_exam
from reflection.lessons import Lessons
from reflection.results import Results
from sales import loop, stages
from tests.fake_model import Buyer, FakeModel, Outbox, Seller, clean_env, say
from tests.test_try_sales import Base as TryBase
from tests.test_whatsapp import SendingGraph, payload, text_msg

ROOT = Path(__file__).resolve().parent.parent
HAND_WRITTEN = ROOT / "tests" / "agents" / "stock_watch"
ASKING = stages.STAGES["asking"]

# What the old prompt never said, in the check's words: each is a rule the exam fails a reply on.
STYLE = ("Never use em dashes or en dashes.", "Never use a hyphen with spaces as a dash.", "No emoji.", "No markdown.")
FULL = ("Reply in Egyptian Arabic, in Arabic letters", "Reply in Franco, in Latin letters and numbers, no Arabic letters",
        "Reply in English, no Arabic letters", "Reply in plain English, not Franco.", "16,500 EGP", "16,500 geneh",
        "Write every amount in digits", "Use only prices and fees from tool results")


def sales_prompt():
    return loop.system_prompt(ASKING, [])["content"]


def write_built(root, name, tools):
    """An agent folder the way Quick start's Build writes one: its card names the tools it connects."""
    folder = Path(root) / turn.AGENTS / name
    folder.mkdir(parents=True)
    plug = json.loads((HAND_WRITTEN / "plug.json").read_text(encoding="utf-8"))
    plug["agent"] = name
    plug["risk"]["high"]["tools"] = []
    (folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
    (folder / "instructions.md").write_text("You answer a made-up shop's customers in one or two short lines.",
                                            encoding="utf-8")
    card = {"agent": name, "name": name.replace("_", " "), "does": "answers a made-up shop's customers",
            "good": "The customer gets a clear answer.", "never": ["Never promise a date."], "needs": [],
            "tools": list(tools), "level": "careful", "at": 0}
    (folder / "card.json").write_text(json.dumps(card), encoding="utf-8")
    return folder


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def assert_full(self, prompt):
        for rule in STYLE + FULL:
            self.assertIn(rule, prompt)

    def assert_style_only(self, prompt):
        for rule in STYLE:
            self.assertIn(rule, prompt)
        for rule in FULL:
            self.assertNotIn(rule, prompt)


class ThePromptHoldsTheRules(Base):
    def test_the_sales_prompt_holds_each_rule_it_is_examined_on(self):
        prompt = sales_prompt()
        self.assert_full(prompt)
        self.assertTrue(prompt.startswith(loop.INSTRUCTIONS + "\n\n"))  # the instructions first, as written
        rules = send_check.prompt_rules()
        for _, fix in send_check.BANNED:  # the banned words' own fixes name the words, so they are taken out first
            rules = rules.replace(fix, "")
        self.assertEqual(send_check.style_problems(rules.replace("**", "")), [])
        # twelve short plain lines, not the check's code (180 before the four rules it left out, review examrules
        # round 1, item 1)
        self.assertLess(len(send_check.prompt_rules().split()), 262)

    def test_a_built_agents_card_gets_the_rules_its_check_holds(self):
        talks = turn.load(write_built(self.root, "shop_helper", ["whatsapp"]))
        self.assertTrue(talks.full_check)
        self.assert_full(turn.system_prompt(talks)["content"])
        quiet = turn.load(write_built(self.root, "note_taker", []))  # no customer channel: the house style only
        self.assertFalse(quiet.full_check)
        self.assert_style_only(turn.system_prompt(quiet)["content"])

    def test_a_folder_written_by_hand_gets_them_too(self):
        agent = turn.load(HAND_WRITTEN)
        self.assertTrue(agent.full_check)
        self.assert_full(turn.system_prompt(agent)["content"])
        self.assertTrue(turn.system_prompt(agent)["content"].startswith(agent.instructions + "\n\n"))

    def test_every_rule_the_check_feeds_back_is_in_the_prompt(self):
        """The feedback of each rule the exam reads by name (reflection/exam.py CHECKS: style, script,
        amounts) is said in the prompt in the same words."""
        prompt = sales_prompt()
        bad = {"dashes": ("Yes \u2014 in stock.", "Yes - in stock."), "emoji": ("In stock \U0001F600",),
               "markdown": ("**In stock**",)}
        for name, replies in bad.items():
            for reply in replies:
                found = dict(send_check.named_style(reply))
                self.assertIn(found[name], prompt, reply)
        english = dict(send_check.named_problems("It is 16,500 \u062c\u0646\u064a\u0647.", "How much is it?"))
        self.assertIn(english["script"].split(" (this reply")[0].split(". ", 1)[1], prompt)
        arabic = dict(send_check.named_problems("It is in stock.", "\u0645\u0648\u062c\u0648\u062f\u061f"))
        self.assertIn(arabic["script"].split(". ", 1)[1].rstrip("."), prompt)
        amounts = dict(send_check.named_problems("It is 99,999 EGP.", "How much?", amounts=[16500]))
        self.assertIn("Use only prices and fees from tool results, or say you do not have that number.",
                      amounts["amounts"])
        self.assertIn("Use only prices and fees from tool results, or say you do not have that number.", prompt)
        digits = dict(send_check.named_problems("It is sixteen thousand EGP.", "How much?"))
        self.assertIn(digits["digits"], prompt)


class AChangedRuleChangesThePrompt(Base):
    NEW = "Never send an emoji or an emoticon."

    def test_a_changed_rule_word_moves_the_check_and_every_prompt_together(self):
        agent = turn.load(HAND_WRITTEN)
        with mock.patch.object(send_check, "NO_EMOJI", self.NEW, create=True):
            self.assertEqual(send_check.style_problems("In stock \U0001F600"), [self.NEW])
            for prompt in (sales_prompt(), turn.system_prompt(agent)["content"]):
                self.assertIn(self.NEW, prompt)
                self.assertNotIn("No emoji.", prompt)
        with mock.patch.dict(getattr(send_check, "CURRENCY_SAID", {}), {"english": "LE"}):
            self.assertIn("16,500 LE", sales_prompt())
            self.assertNotIn("16,500 EGP", sales_prompt())
            why = dict(send_check.named_problems("It is 16,500 \u062c\u0646\u064a\u0647.", "How much?"))["script"]
            self.assertIn("16,500 LE", why)

    def test_a_changed_plug_changes_the_rules_in_the_prompt(self):
        """A folder written by hand gets the full rules while its plug declares the reply action, as its
        check does; with that action gone, the house style only."""
        folder = self.root / "stock_watch"
        shutil.copytree(HAND_WRITTEN, folder)
        self.assert_full(turn.system_prompt(turn.load(folder))["content"])
        plug = json.loads((folder / "plug.json").read_text(encoding="utf-8"))
        plug["actions"] = {"note": "One note for the team."}
        for r in plug["results"].values():
            if r.get("after") == "reply":
                r["after"] = "note"
        (folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
        agent = turn.load(folder)
        self.assertFalse(agent.full_check)
        self.assert_style_only(turn.system_prompt(agent)["content"])


class NoPathWithoutTheRules(Base):
    """Every path a reply is written on reaches the model with the rules in its system prompt."""

    def test_the_live_whatsapp_reply(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        model = FakeModel(say("\u0645\u0648\u062c\u0648\u062f."))
        app = wa.App(Chats(db), model, Lessons(db), Results(db), SendingGraph(b"", "audio/ogg"), connected=True)
        app.accept(wa.parse(payload(text_msg("m1", "\u0645\u0648\u062c\u0648\u062f\u061f", frm="201111111111"))))
        app.work_one(app.q.get_nowait())
        self.assert_full(model.calls[0]["messages"][0]["content"])

    def test_the_sales_loop_on_its_own(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        model = FakeModel(say("In stock."))
        loop.turn(Message(channel="whatsapp", customer_id="201111111112", text="Is it in stock?"), chats=Chats(db),
                  model=model, lessons=Lessons(db), results=Results(db), send=Outbox())
        self.assert_full(model.calls[0]["messages"][0]["content"])

    def test_the_arena_match(self):
        card = json.loads((ROOT / "demo" / "personas" / "cards" / "persona-01.json").read_text(encoding="utf-8"))
        agent = Seller()
        match.play(card, agent_model=agent, customer_model=Buyer(), max_turns=1,
                   checker=lambda reply, said, ran, orders: factcheck.check(reply, said, ran, orders))
        self.assertTrue(agent.calls)
        for c in agent.calls:
            self.assert_full(c["messages"][0]["content"])

    def test_the_sales_exam(self):
        model = FakeModel(say("\u0647\u0633\u0623\u0644 \u0627\u0644\u0641\u0631\u064a\u0642."))
        exam.answer(exam.situations(PLUG)[0], None, model=model)
        self.assert_full(model.calls[0]["messages"][0]["content"])

    def test_a_built_agents_turn_and_its_exam(self):
        agent = turn.load(write_built(self.root, "shop_helper", ["whatsapp"]))
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open(turn.practice_channel(agent), "201000000099")
        model = FakeModel(say("Yes, we have it."))
        turn.turn(agent, "Do you have it?", chats=chats, chat_id=cid, model=model, send=lambda to, t: None,
                  customer_id="201000000099")
        self.assert_full(model.calls[0]["messages"][0]["content"])
        model = FakeModel(say("Yes, we have it."))
        turn_exam.answer({"id": 1, "turns": [{"customer": "Do you have it?"}]}, None, agent=agent, model=model)
        self.assert_full(model.calls[0]["messages"][0]["content"])

    def test_every_turn_caller_goes_through_the_two_prompt_builders(self):
        """A new path is noticed: the modules that run a reply turn are the known ones, and only the two
        system_prompt builders read an agent's instructions into a system message."""
        callers, readers = set(), set()
        for path in sorted(ROOT.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", "assistant/")) or "/." in rel:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bloop\.turn\(|\bturn_mod\.turn\(|\bturn\.turn\(", text):
                callers.add(rel)
            if re.search(r"\bINSTRUCTIONS\b|\.instructions\b", text):
                readers.add(rel)
        self.assertEqual(callers, {"channels/whatsapp.py", "arena/match.py", "arena/practice.py", "reflection/exam.py",
                                   "reflection/turn_exam.py", "reflection/try_sales.py"})
        self.assertEqual(readers, {"sales/loop.py", "kit/turn.py"})
        self.assert_full(sales_prompt())
        self.assert_full(turn.system_prompt(turn.load(HAND_WRITTEN))["content"])


class TheFourRulesItLeftOut(Base):
    """Review examrules round 1, item 1: the prompt left out four rules the check enforces, the stock count
    (on the exam's SAFETY list), sympathy lines, banned words (part of the house style, so every agent is held
    to them) and links. Each is said in the feedback's own words, only where its rule applies."""
    STOCK = "Only 3 pairs left."

    def test_each_rule_the_check_feeds_back_is_said_in_the_sales_prompt(self):
        prompt = sales_prompt()
        got = dict(send_check.named_problems("See https://shop.example/x", "Do you have a link?"))
        self.assertIn(got["links"], prompt)
        got = dict(send_check.named_problems(self.STOCK, "Is it in stock?"))
        self.assertIn(got["stock"], prompt)
        for reply in ("sorry to hear that, it is in stock.", "Sorry for the inconvenience, it is in stock."):
            why = dict(send_check.named_problems(reply, "Is it in stock?"))["sympathy"]
            self.assertIn(why.split('"). ', 1)[1], prompt)  # the rule after the line it quotes
        for reply in ("el goz b 16,500 geneh", "\u0627\u0644\u062c\u0648\u0632 \u0628 16,500 \u062c\u0646\u064a\u0647",
                      "\u0647\u062a\u0628\u0642\u0649 \u0645\u0631\u062a\u0627\u062d"):
            for why in (fb for name, fb in send_check.named_problems(reply, "bkam") if name == "banned"):
                self.assertIn(why, prompt, reply)
        self.assertEqual(len([n for n, _ in send_check.named_problems("el goz", "bkam") if n == "banned"]), 1)

    def test_the_sympathy_examples_are_lines_the_check_refuses(self):
        for line in send_check.SYMPATHY_SHOWN:
            self.assertIn(line, send_check.SYMPATHY)
            self.assertIn(f'"{line}"', sales_prompt())
            self.assertIn("sympathy", dict(send_check.named_problems(f"{line}, it is in stock.", "stock?")))

    def test_the_stock_line_only_where_the_check_holds_the_rule(self):
        agents = {"sales": None, "hand": turn.load(HAND_WRITTEN),
                  "shop": turn.load(write_built(self.root, "shop_helper", ["whatsapp", "store"])),
                  "talks": turn.load(write_built(self.root, "talker", ["whatsapp"])),
                  "quiet": turn.load(write_built(self.root, "note_taker", []))}
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open(turn.CHANNEL, "201000000098")
        held = {}
        for name, agent in agents.items():
            if agent is None:
                prompt, held[name] = sales_prompt(), not send_check.check(self.STOCK, "Is it in stock?")[0]
            else:
                prompt = turn.system_prompt(agent)["content"]
                held[name] = not turn._check(agent, self.STOCK, "Is it in stock?", set(), set(), (), frozenset(),
                                             chats, cid)[0]
            self.assertEqual(send_check.NO_STOCK_COUNT in prompt, held[name], name)
        self.assertEqual(held, {"sales": True, "hand": True, "shop": True, "talks": False, "quiet": False})
        self.assertIn(send_check.NO_STOCK_COUNT, send_check.prompt_rules(True, True))
        self.assertNotIn(send_check.NO_STOCK_COUNT, send_check.prompt_rules(True, False))
        self.assertNotIn(send_check.NO_STOCK_COUNT, send_check.prompt_rules(False, True))

    def test_an_agent_with_the_house_style_only_is_told_the_banned_words_and_nothing_of_whatsapp(self):
        quiet = turn.load(write_built(self.root, "note_taker", []))
        self.assertFalse(quiet.full_check)
        prompt = turn.system_prompt(quiet)["content"]
        for _, fix in send_check.BANNED:
            self.assertIn(fix, prompt)
        for line in (send_check.ON_WHATSAPP, "WhatsApp", send_check.NO_SYMPATHY, send_check.ONLY_STORE_LINKS,
                     send_check.NO_STOCK_COUNT):
            self.assertNotIn(line, prompt)
        self.assertIn(send_check.NO_MARKDOWN, prompt)
        # its feedback is the house style's, unchanged (review examrules round 1, item 4: the prompt only)
        passed, why = turn._check(quiet, "**Noted**", "", set(), set(), (), frozenset(), None, None)
        self.assertEqual((passed, why), (False, "No markdown. WhatsApp shows the ** as they are."))
        for agent in (turn.load(HAND_WRITTEN), None):
            prompt = sales_prompt() if agent is None else turn.system_prompt(agent)["content"]
            self.assertIn("No markdown. WhatsApp shows the ** as they are.", prompt)

    def test_a_changed_word_moves_the_feedback_and_the_prompt_together(self):
        agent = turn.load(HAND_WRITTEN)
        new = {"NO_STOCK_COUNT": "Say in stock, few left or out, never a number.",
               "ONLY_STORE_LINKS": "Only the store tool's image links.",
               "NO_SYMPATHY": "Skip sympathy, answer.",
               "ON_WHATSAPP": "WhatsApp prints the stars."}
        bad = {"NO_STOCK_COUNT": ("stock", self.STOCK), "ONLY_STORE_LINKS": ("links", "See nike.com"),
               "NO_SYMPATHY": ("sympathy", "sorry to hear, it is in stock."), "ON_WHATSAPP": ("markdown", "**Yes**")}
        for const, words in new.items():
            with mock.patch.object(send_check, const, words):
                name, reply = bad[const]
                self.assertIn(words, dict(send_check.named_problems(reply, "Is it in stock?"))[name], const)
                for prompt in (sales_prompt(), turn.system_prompt(agent)["content"]):
                    self.assertIn(words, prompt, const)
        fix = "Never write el goz. Name the boot."
        banned = [(p, fix if "goz" in p.pattern else f) for p, f in send_check.BANNED]
        with mock.patch.object(send_check, "BANNED", banned):
            self.assertIn(fix, dict(send_check.named_problems("el goz", "bkam"))["banned"])
            self.assertIn(fix, sales_prompt())
            self.assertNotIn("Never write el goz. Say the price plainly.", sales_prompt())


class TheRulesComeBeforeTheLessons(Base):
    """Review examrules round 1, item 3: no test held the rules ahead of the lesson slot, so moving them after
    it (both builders) passed. The rules come first, then the plug's slot line and its lessons."""
    LESSON = {"id": 7, "text": "Name the delivery fee only from the delivery tool."}

    def assert_rules_then_slot(self, prompt, rules, plug):
        self.assertEqual(prompt.count(rules), 1)
        self.assertEqual(prompt.count(plug.slot), 1)
        self.assertLess(prompt.index(rules) + len(rules), prompt.index(plug.slot))
        self.assertLess(prompt.index(plug.slot), prompt.index(self.LESSON["text"]))

    def test_the_sales_prompt(self):
        prompt = loop.system_prompt(ASKING, [self.LESSON])["content"]
        self.assert_rules_then_slot(prompt, send_check.prompt_rules(), loop.PLUG)

    def test_any_agent_turn_runs(self):
        for agent in (turn.load(HAND_WRITTEN), turn.load(write_built(self.root, "note_taker", []))):
            prompt = turn.system_prompt(agent, [self.LESSON])["content"]
            self.assert_rules_then_slot(prompt, send_check.prompt_rules(agent.full_check, agent.stock), agent.plug)


class TrySales(TryBase):
    def test_try_sales_shows_the_rules(self):
        said = self.p.actions["/try/sales"]
        self.assertEqual(said(self.m, {"text": ["Is the blue trainer in 41?"]}), "Sales answered.")
        for rule in STYLE + FULL:
            self.assertIn(rule, self.systems[0])


if __name__ == "__main__":
    unittest.main()
