"""The rules an agent is examined on are in its own prompt (DECISIONS item 94): the send check's style,
script and amount rules, and prices and fees from tools only, read from the send check's own words
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
        self.assertEqual(send_check.style_problems(send_check.prompt_rules().replace("**", "")), [])
        self.assertLess(len(send_check.prompt_rules().split()), 180)  # eight short plain lines, not the check's code

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


class TrySales(TryBase):
    def test_try_sales_shows_the_rules(self):
        said = self.p.actions["/try/sales"]
        self.assertEqual(said(self.m, {"text": ["Is the blue trainer in 41?"]}), "Sales answered.")
        for rule in STYLE + FULL:
            self.assertIn(rule, self.systems[0])


if __name__ == "__main__":
    unittest.main()
