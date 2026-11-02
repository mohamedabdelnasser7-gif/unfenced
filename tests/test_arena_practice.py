"""Arena practice for an agent made by Quick start (new, 2026-11-01): kit/turn.py, arena/madeup.py,
arena/good.py and arena/practice.py, on fake models only, never the network. No chat goes to a
person (DECISIONS items 53 and 57): after MAX_FAILED_CHECKS failed drafts nothing is sent and the
turn is no_safe_reply. The last class builds an agent with Quick start's own Build and plays it."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from arena import good, madeup, practice, run
from kit import turn
from kit.chats import Chats
from kit.db import Db
from kit.model import ModelError
from reflection import morning
from reflection import quickstart as qs
from tests.fake_model import FakeModel, clean_env, say, tool_call
from tests.test_quickstart import card_reply, exam_reply, plug_reply

REPO = Path(run.__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "agents" / "stock_watch"
OPENING = "Is the Mercurial boot in stock?"
ANSWER = "Yes, that boot is in stock."
THANKS = "Thanks, that is all I needed " + practice.DONE
PEOPLE = [
    {"want": ["a boot in stock"], "worry": "it may be sold out", "settles_it": ["a clear stock answer"],
     "language": "english", "length": "short", "opening": "stock", "examples": [OPENING]},
    {"want": ["a quick answer"], "worry": "waiting", "settles_it": ["a yes or no"], "language": "arabic",
     "length": "short", "opening": "greeting", "examples": ["متاح؟"]},
    {"want": ["to know about sizes"], "worry": "the size", "settles_it": ["the size in stock"],
     "language": "franco", "length": "medium", "opening": "size", "examples": ["el size da mawgood?"]},
    {"want": ["the boot"], "worry": "the colour", "settles_it": ["the colour in stock"], "language": "english",
     "length": "medium", "opening": "colour", "examples": ["Do you have it in black?"]},
    {"want": ["a discount"], "worry": "the price", "settles_it": ["a lower price"], "language": "english",
     "length": "long", "opening": "price", "examples": ["Can you do it cheaper?"]},
    {"want": ["a boot the store never sold"], "worry": "nothing fits", "settles_it": ["a boot that does not exist"],
     "language": "english", "length": "short", "opening": "a made-up boot", "examples": ["Do you have the X1?"],
     "why_not": "the boot does not exist"},
]


class World:
    """One fake model for every side, told apart by the system prompt: the made-up customers, the
    customer, the agent and the judge. agent: a callable (messages, tools) -> message for the agent's
    side, else it looks the item up with the store tool and answers ANSWER. reached: the judge's word."""

    def __init__(self, agent=None, reached=True, judge=None, people=None, customer=None):
        self.agent, self.reached, self.judge, self.customer = agent, reached, judge, customer
        self.people = PEOPLE if people is None else people
        self.calls = {"cards": 0, "customer": 0, "agent": 0, "judge": 0}
        self.offered, self.judged = [], []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        if system == madeup.SYSTEM:
            self.calls["cards"] += 1
            return say(json.dumps({"customers": self.people}))
        if system == good.SYSTEM:
            self.calls["judge"] += 1
            self.judged.append(json.loads(messages[1]["content"]))
            if self.judge is not None:
                return self.judge(messages)
            return say(json.dumps({"reached": self.reached, "broke_never": False, "turn": 1, "why": "a clear answer"}))
        if system.startswith("You are a person writing on WhatsApp"):
            self.calls["customer"] += 1
            if self.customer is not None:
                return self.customer(messages)
            return say(OPENING if len(messages) == 2 else THANKS)
        self.calls["agent"] += 1
        self.offered.append(sorted(t["function"]["name"] for t in tools or []))
        if self.agent is not None:
            return self.agent(messages, tools)
        if messages[-1]["role"] == "tool":
            return say(ANSWER)
        return tool_call("store", {"query": "mercurial"})


def raises(*_, **__):
    raise ModelError("Baseten call failed: TimeoutError")


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()          # the folder beside the database
        self.folder = self.root / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)

    def main(self, *argv, world=None, agent=None, customer=None, judge=None):
        world = world or World()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = practice.main(["--agent", str(self.folder), *argv], agent_model=agent or world,
                                 customer_model=customer or world, judge_model=judge or world)
        self.err = err.getvalue()
        return code, (json.loads(out.getvalue()) if "--json" in argv and out.getvalue() else out.getvalue())

    def matches(self):
        path = self.folder / run.MATCHES_FILE
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def files(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())


class EndToEnd(Base):
    def test_a_fixture_plug_practises_and_writes_the_files_a_sales_run_writes(self):
        code, rep = self.main("--matches", "2", "--json")
        self.assertEqual(code, 0, self.err)
        self.assertEqual((rep["agent"], rep["stopped"], rep["made_up"]), ("stock_watch", run.PASSED, True))
        item = rep["item"]
        saved = json.loads((self.root / item["file"]).read_text(encoding="utf-8"))
        self.assertEqual(item["file"], f"arena-stock_watch-{rep['run']}.json")
        self.assertEqual((saved["kind"], saved["agent"], saved["made_up"], saved["practice"]),
                         ("arena_rounds", "stock_watch", True, True))
        # the Morning page and screen 2 read it with their own reader, unchanged
        read, problems = morning.Morning.read_arena(types.SimpleNamespace(reports=self.root))
        self.assertEqual(problems, [])
        self.assertEqual(read["stock_watch"]["file"], item["file"])
        ms = self.matches()
        self.assertEqual(len(ms), 2 + rep["trust"]["matches"])
        for m in ms:
            self.assertEqual((m["agent"], m["won"], m["ended"], m["made_up"]), ("stock_watch", True, "done", True))
            self.assertEqual(m["turns"][0]["replies"], [ANSWER])
            self.assertEqual(m["turns"][0]["tools"], ["store"])
            self.assertTrue(m["persona"]["made_up"])
            self.assertEqual(m["prompt_sha"], practice.PROMPT_SHA)
            self.assertEqual(m["closing"], "Thanks, that is all I needed")
        self.assertEqual(json.loads((self.root / run.CALLS_FILE).read_text())["calls"],
                         rep["calls"]["used"])

    def test_the_agent_gets_its_instructions_and_starts_from_zero(self):
        world = World()
        self.main("--quick", world=world)
        agent = turn.load(self.folder)
        # the agent's first call: its instructions alone (no lesson slot), then the customer's line
        rec = Recorder(world)
        card = madeup.read(self.folder / madeup.FOLDER, agent.name, agent.card)[0]
        practice.play(agent, card, agent_model=rec, customer_model=world)
        system = rec.seen[0][0]
        self.assertEqual(system, {"role": "system", "content": agent.instructions})
        self.assertNotIn(agent.plug.slot, system["content"])
        self.assertEqual(rec.seen[0][-1], {"role": "user", "content": OPENING})


class Recorder:
    def __init__(self, inner):
        self.inner, self.seen = inner, []

    def chat(self, messages, tools=None, **kw):
        self.seen.append(messages)
        return self.inner.chat(messages, tools=tools, **kw)


class Tools(Base):
    def test_only_the_tools_the_plug_names_that_exist_are_offered(self):
        world = World()
        code, rep = self.main("--quick", "--json", world=world)
        self.assertEqual(code, 0, self.err)
        self.assertEqual(set(map(tuple, world.offered)), {("store",)})
        self.assertEqual(rep["tools"], ["store"])
        self.assertEqual(rep["tools_left_out"], ["bosta_stock", "switch_stage"])

    def test_quick_start_tool_keys_read_as_the_tool_files_behind_them(self):
        plug = json.loads((self.folder / "plug.json").read_text())
        plug["risk"]["high"]["tools"] = ["calendar", "orders", "store", "whatsapp"]
        (self.folder / "plug.json").write_text(json.dumps(plug))
        a = turn.load(self.folder)
        self.assertEqual(a.tools, ("find_order", "draft_order", "store"))
        self.assertEqual(a.missing, ("calendar",))  # whatsapp is the channel the chat is on, no tool
        self.assertTrue(set(turn.QUICK_TOOLS) <= set(qs.TOOLS))

    def test_a_tool_the_plug_does_not_name_never_runs(self):
        def agent(messages, tools):
            if messages[-1]["role"] == "tool":
                return say(ANSWER)
            return tool_call("draft_order", {"items": [], "name": "Demo", "governorate": "Giza", "address": "1 St"})
        world = World(agent=agent)
        self.main("--quick", world=world)
        m = self.matches()[0]
        self.assertEqual(m["turns"][0]["tools"], ["draft_order"])
        self.assertFalse(m["order"])
        a = turn.load(self.folder)
        db = Db(":memory:")
        try:
            chats = Chats(db)
            cid = chats.open("whatsapp", "201000000099")
            with practice.match_mod.demo_store():
                turn.turn(a, OPENING, chats=chats, chat_id=cid, model=world, send=lambda *x: None,
                          customer_id="201000000099")
            result = [json.loads(s["content"]) for s in chats.steps(cid) if s["role"] == "tool"][0]
        finally:
            db.close()
        self.assertEqual(result, {"ok": False, "feedback": "The tool draft_order is not available at this stage."})


class NoSend(Base):
    def test_no_message_leaves_and_no_key_but_the_model_is_used(self):
        """Shopify keys and an operator number in env are taken away for the match; a turn whose drafts all
        fail the send check sends nothing, the network is never opened and the only way out is the
        match's list. The match ends there and is lost."""
        os.environ.update(SHOPIFY_STORE="shop.example", SHOPIFY_TOKEN="not-a-key", OPERATOR_WHATSAPP="201000000001")

        def agent(messages, tools):
            return say("It is 99,999 EGP.")
        world = World(agent=agent)
        opened = []
        with mock.patch("kit.net.open_once", side_effect=lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(
                AssertionError("the network was opened"))), \
                mock.patch("channels.whatsapp.Graph.send", side_effect=AssertionError("a WhatsApp send")):
            code, rep = self.main("--quick", "--json", world=world)
        self.assertEqual(opened, [])
        m = self.matches()[0]
        self.assertEqual((m["ended"], m["turns"][0]["outcome"]), ("no_safe_reply", "no_safe_reply"))
        self.assertEqual((m["turns"][0]["replies"], len(m["turns"]), m["won"]), ([], 1, False))
        self.assertEqual(world.calls["agent"], len(self.matches()) * turn.MAX_FAILED_CHECKS)  # one turn a match
        self.assertEqual(os.environ["OPERATOR_WHATSAPP"], "201000000001")  # put back after the match

    def test_nothing_is_written_outside_the_run_folder(self):
        before = {p for p in REPO.rglob("*") if "__pycache__" not in p.parts and ".git" not in p.parts}
        code, rep = self.main("--matches", "1", "--json")
        self.assertEqual(code, 0, self.err)
        cards = [f"agents/stock_watch/practice-cards/persona-{i:02d}.json" for i in range(1, 7)]
        self.assertEqual(self.files(), sorted(
            ["agents/stock_watch/card.json", "agents/stock_watch/instructions.md", "agents/stock_watch/plug.json",
             f"agents/stock_watch/{run.MATCHES_FILE}", run.CALLS_FILE, "arena-calls.lock", rep["item"]["file"]]
            + cards))
        after = {p for p in REPO.rglob("*") if "__pycache__" not in p.parts and ".git" not in p.parts}
        self.assertEqual(after - before, set())


class Void(Base):
    def test_an_agent_model_error_voids_the_match(self):
        code, rep = self.main("--quick", "--json", agent=types.SimpleNamespace(chat=raises))
        self.assertEqual((code, rep["stopped"]), (1, run.MODEL_ERROR))
        self.assertEqual(rep["error"], practice.AGENT_SILENT)
        self.assertEqual(self.matches(), [])  # dropped, never a loss

    def test_a_customer_model_error_voids_the_match(self):
        world = World()
        cards, _ = madeup.for_agent(self.folder, "stock_watch", turn.load(self.folder).card, world)
        code, rep = self.main("--quick", "--json", world=world, customer=types.SimpleNamespace(chat=raises))
        self.assertEqual((code, rep["stopped"]), (1, run.MODEL_ERROR))
        self.assertIn("TimeoutError", rep["error"])
        self.assertEqual(self.matches(), [])

    def test_a_judge_that_fails_or_cannot_be_read_voids_the_match(self):
        for judge in (lambda m: raises(), lambda m: say("I think it went well."),
                      lambda m: say(json.dumps({"reached": "true", "broke_never": False}))):
            with self.subTest(judge=judge):
                (self.folder / run.MATCHES_FILE).unlink(missing_ok=True)
                code, rep = self.main("--quick", "--json", world=World(judge=judge))
                self.assertEqual((code, rep["stopped"]), (1, run.MODEL_ERROR))
                self.assertEqual(self.matches(), [])

    def test_unreadable_practice_customers_stop_the_run(self):
        code, _ = self.main("--quick", world=World(people="not a list"))
        self.assertEqual(code, 2)
        self.assertIn("could not be read", self.err)
        self.assertFalse((self.folder / madeup.FOLDER).exists())


class MadeUp(Base):
    def test_cards_are_marked_made_up_in_the_real_card_shape(self):
        world = World()
        cards, written = madeup.for_agent(self.folder, "stock_watch", turn.load(self.folder).card, world)
        self.assertTrue(written)
        self.assertEqual([c["kind"] for c in cards], list(madeup.KINDS))
        real = json.loads((run.DEMO_CARDS / "persona-01.json").read_text(encoding="utf-8"))
        for c in cards:
            self.assertTrue(set(real) <= set(c), set(real) - set(c))
            self.assertEqual((c["made_up"], c["chats"], c["won"], c["lost"]), (True, 0, 0, 0))
        never = [c for c in cards if c["unwinnable"]]
        self.assertEqual([c["kind"] for c in never], ["never"])
        self.assertEqual(never[0]["why_unwinnable"], "the boot does not exist")
        self.assertEqual([c["patience"]["most"] for c in cards], [3, 3, 2, 2, 1, 1])
        # the model's words only: what it wrote about the kind or the mark is never read
        again, written = madeup.for_agent(self.folder, "stock_watch", turn.load(self.folder).card, world)
        self.assertFalse(written)
        self.assertEqual((again, world.calls["cards"]), (cards, 1))

    def test_a_changed_card_writes_new_customers(self):
        world = World()
        madeup.for_agent(self.folder, "stock_watch", turn.load(self.folder).card, world)
        card = json.loads((self.folder / "card.json").read_text())
        card["good"] = "The customer gets the stock answer and the size."
        (self.folder / "card.json").write_text(json.dumps(card))
        _, written = madeup.for_agent(self.folder, "stock_watch", turn.load(self.folder).card, world)
        self.assertTrue(written)
        self.assertEqual(world.calls["cards"], 2)

    def test_the_level_is_stricter_while_the_customers_are_made_up(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        trust = Path(outside.name) / "trust.json"
        trust.write_text(json.dumps({"stock_watch": {"matches": 4, "wins": 3, "zero_failed_checks": False}}))
        code, rep = self.main("--matches", "1", "--trust", str(trust), "--json")
        self.assertEqual(code, 0, self.err)
        self.assertEqual(rep["trust"], {"matches": 4, "wins": 4, "zero_failed_checks": True, "made_up": True,
                                        "trial": {"level": "careful", "share": 0.2, "days": 14}})
        self.assertTrue(rep["fact_checks"])
        cards = {c["id"]: c for c in madeup.read(self.folder / madeup.FOLDER, "stock_watch",
                                                  turn.load(self.folder).card)}
        self.assertTrue(rep["held_out_cards"])
        self.assertFalse(any(cards[i]["unwinnable"] for i in rep["held_out_cards"]))
        # one lost gate match fails the stricter level
        judge = iter([True, True, True, False] * 3)
        world = World(judge=lambda m: say(json.dumps({"reached": next(judge), "broke_never": False, "turn": 1})))
        code, rep = self.main("--matches", "1", "--trust", str(trust), "--json", world=world)
        self.assertEqual((code, rep["stopped"]), (1, run.ROUNDS))
        self.assertTrue(rep["item"]["lost"])

    def test_real_cards_given_keep_the_level_as_it_is(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        trust = Path(outside.name) / "trust.json"
        trust.write_text(json.dumps({"stock_watch": {"matches": 4, "wins": 3}}))
        code, rep = self.main("--matches", "1", "--trust", str(trust), "--cards", str(run.DEMO_CARDS), "--json")
        self.assertEqual(rep["trust"], {"matches": 4, "wins": 3, "zero_failed_checks": True})
        self.assertFalse(rep["made_up"])


class Judge(unittest.TestCase):
    CARD = {"good": "A clear stock answer.", "never": ["Never give a price."]}

    def match(self, **turn_fields):
        t = {"n": 1, "customer": OPENING, "replies": [ANSWER], "failed": []}
        t.update(turn_fields)
        return {"turns": [t]}

    def test_strict_answers(self):
        cases = [({"reached": True, "broke_never": False, "turn": 1}, True),
                 ({"reached": True, "broke_never": True, "turn": 1}, False),
                 ({"reached": False, "broke_never": False}, False)]
        for answer, won in cases:
            with self.subTest(answer=answer):
                world = World(judge=lambda m, a=answer: say("```json\n" + json.dumps(a) + "\n```"))
                v = good.judge(self.match(), self.CARD, world)
                self.assertEqual(v["won"], won)
                self.assertEqual(world.judged[0]["good"], self.CARD["good"])
                self.assertEqual(world.judged[0]["never"], self.CARD["never"])
        v = good.judge(self.match(), self.CARD, World(judge=lambda m: say(json.dumps(
            {"reached": True, "broke_never": True, "turn": 1, "why": "it gave a price"}))))
        self.assertEqual(v["why"], f"{good.BROKE}: it gave a price")
        self.assertEqual(v["quote"], {"turn": 1, "who": "agent", "text": ANSWER})

    def test_code_decides_first_with_no_model_call(self):
        world = World()
        v = good.judge(self.match(replies=[], failed=[{"check": "send_check", "why": "No emoji."}]), self.CARD, world)
        self.assertEqual((v["won"], v["why"]), (False, f"{good.FAILED}: No emoji."))
        self.assertEqual(good.judge(self.match(replies=[]), self.CARD, world)["why"], good.SILENT)
        self.assertEqual(good.judge({"turns": []}, self.CARD, world)["why"], good.NO_TURNS)
        none = {"ended": "no_safe_reply", "turns": [
            {"n": 1, "customer": OPENING, "replies": [ANSWER], "failed": []},
            {"n": 2, "customer": "And in black?", "replies": [], "failed": [{"check": "send_check", "why": "No emoji."}]}]}
        self.assertEqual(good.judge(none, self.CARD, world, facts=False)["why"], good.NO_SAFE)
        self.assertEqual(world.calls["judge"], 0)


class SendCheck(Base):
    def turn(self, agent, drafts):
        script = list(drafts)
        model = World(agent=lambda m, t: say(script.pop(0)))
        db = Db(":memory:")
        sent = []
        try:
            chats = Chats(db)
            cid = chats.open("whatsapp", "201000000099")
            with practice.match_mod.demo_store():
                out = turn.turn(agent, OPENING, chats=chats, chat_id=cid, model=model,
                                send=lambda to, text: sent.append(text), customer_id="201000000099")
        finally:
            db.close()
        return out, sent

    def test_the_full_check_for_a_plug_that_replies_and_the_style_check_for_others(self):
        full = turn.load(self.folder)
        out, sent = self.turn(full, ["It is 99,999 EGP.", "It is 99,999 EGP.", "It is 99,999 EGP."])
        self.assertEqual((out.outcome, sent), ("no_safe_reply", []))
        self.assertEqual(len(out.failed), turn.MAX_FAILED_CHECKS)
        plug = json.loads((self.folder / "plug.json").read_text())
        plug["actions"] = {"note": "A note to the owner."}
        plug["results"] = {"noted": {"speed": "fast", "shows_in_days": [0, 0], "after": "note"}}
        plug["harm"], plug["decides"] = {"results": ["noted"]}, {"good": "noted", "bad": []}
        plug["risk"]["high"]["tools"] = ["store"]
        (self.folder / "plug.json").write_text(json.dumps(plug))
        style_only = turn.load(self.folder)
        self.assertFalse(style_only.full_check)
        out, sent = self.turn(style_only, ["It is 16,500 EGP."])
        self.assertEqual((out.outcome, sent), ("replied", ["It is 16,500 EGP."]))
        out, sent = self.turn(style_only, ["It is in stock — yes.", "It is in stock, yes."])
        self.assertEqual((out.outcome, sent), ("replied", ["It is in stock, yes."]))
        out, sent = self.turn(style_only, ["A — b"] * 3)
        self.assertEqual((out.outcome, sent, out.failed[0]["check"]), ("no_safe_reply", [], "send_check"))


class Refusals(Base):
    def test_folders_and_files_refused(self):
        code, _ = self.main("--quick", world=World())
        self.assertEqual(code, 0, self.err)
        with contextlib.redirect_stderr(io.StringIO()) as err:  # the fixture in the repo would get Arena files
            self.assertEqual(practice.main(["--agent", str(FIXTURE)], agent_model=World(), customer_model=World(),
                                           judge_model=World()), 2)
        self.assertIn("inside the repo", err.getvalue())
        plug = json.loads((self.folder / "plug.json").read_text())
        for change, why in ((lambda: (self.folder / "plug.json").write_text(json.dumps(dict(plug, agent="other"))),
                             "its folder is stock_watch"),
                            (lambda: (self.folder / "card.json").write_text(json.dumps({"name": "x", "does": "y"})),
                             "card.json good"),
                            (lambda: (self.folder / "instructions.md").write_text("  "), "instructions.md is empty")):
            with self.subTest(why=why):
                shutil.rmtree(self.folder)
                shutil.copytree(FIXTURE, self.folder)
                change()
                code, _ = self.main("--quick", world=World())
                self.assertEqual(code, 2)
                self.assertIn(why, self.err)

    def test_cards_from_outside_the_owner_folder_are_refused(self):
        # red team wireall r1 item 1: another owner's real cards, or the repo's, never play this agent
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        for cards, why in ((Path(other.name), "outside the agent's owner folder"),
                           (run.ROOT / "arena" / "real" / "cards", "outside the agent's owner folder")):
            with self.subTest(cards=str(cards)):
                code, _ = self.main("--quick", "--cards", str(cards), world=World())
                self.assertEqual(code, 2)
                self.assertIn(why, self.err)
        code, _ = self.main("--quick", "--cards", str(run.DEMO_CARDS), world=World())
        self.assertEqual(code, 0, self.err)

    def test_deeply_nested_json_is_left_out(self):
        # red team wireall r1 item 3: JSON too deep for the parser is left out, never a crash. How deep
        # json.loads goes depends on the Python build, so the parser's RecursionError is made here.
        from arena import grow
        deep, loads = "[[[deep]]]", json.loads

        def parse(text, *a, **k):
            if text == deep:
                raise RecursionError("maximum recursion depth exceeded")
            return loads(text, *a, **k)
        bad = self.root / "agents" / "deep"
        bad.mkdir()
        (bad / "plug.json").write_text(deep)
        real = grow.owner_of(self.folder) / madeup.REAL_FOLDER
        real.mkdir()
        (real / "persona-01.json").write_text(deep)
        with mock.patch("json.loads", side_effect=parse):
            self.assertEqual([a.name for a in turn.built(self.root)], ["stock_watch"])
            self.assertIsNone(madeup.owner_cards(self.folder))

    def test_the_sales_agent_practises_through_its_own_run(self):
        sales = self.root / "agents" / "sales"
        shutil.copytree(FIXTURE, sales)
        plug = json.loads((sales / "plug.json").read_text())
        (sales / "plug.json").write_text(json.dumps(dict(plug, agent="sales")))
        self.folder = sales
        code, _ = self.main("--quick", world=World())
        self.assertEqual(code, 2)
        self.assertIn("arena/run.py", self.err)


class QuickStartFit(unittest.TestCase):
    """The two fit: a folder written by Quick start's Build (reflection/quickstart.py) plays one practice
    match end to end, on fake models only."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()  # the folder beside the database

    def test_a_folder_built_by_quick_start_plays_one_match(self):
        needs = [{"what": "Your store's stock", "tool": "store"}, {"what": "Customer chats", "tool": "whatsapp"},
                 {"what": "Bosta stock levels", "tool": "store"}]
        page = types.SimpleNamespace(reports=self.root, plugs={})
        quick = qs.QuickStart(FakeModel(card_reply(needs=needs), plug_reply(), exam_reply()))
        quick.say(page, "an agent that tells my customers what is in stock")
        self.assertIn("agents/stock_watcher", quick.build(page))
        folder = self.root / qs.AGENTS / "stock_watcher"
        self.assertEqual(sorted(p.name for p in folder.iterdir()), sorted(qs.FILES))  # the three, and its exam
        agent = turn.load(folder)
        self.assertEqual((agent.name, agent.tools, agent.missing, agent.full_check), ("stock_watcher", ("store",), (),
                                                                                       True))  # it connects whatsapp
        self.assertEqual(agent.card["needs"], ["Your store's stock", "Customer chats", "Bosta stock levels"])
        world = World()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = practice.main(["--agent", str(folder), "--quick", "--json"], agent_model=world,
                                 customer_model=world, judge_model=world)
        self.assertEqual(code, 0, err.getvalue())
        rep = json.loads(out.getvalue())
        self.assertEqual((rep["agent"], rep["stopped"], rep["made_up"], rep["tools"]),
                         ("stock_watcher", run.PASSED, True, ["store"]))
        ms = [json.loads(x) for x in (folder / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        self.assertTrue(ms)
        for m in ms:
            self.assertEqual((m["agent"], m["won"], m["ended"]), ("stock_watcher", True, "done"))
            self.assertEqual((m["turns"][0]["replies"], m["turns"][0]["tools"]), ([ANSWER], ["store"]))
        self.assertEqual(world.judged[0]["good"], "You hear about a low item a day before it runs out.")
        read, problems = morning.Morning.read_arena(types.SimpleNamespace(reports=self.root))
        self.assertEqual((problems, read["stock_watcher"]["file"]), ([], rep["item"]["file"]))

    def test_a_built_card_that_names_another_agent_is_refused(self):
        page = types.SimpleNamespace(reports=self.root, plugs={})
        quick = qs.QuickStart(FakeModel(card_reply(), plug_reply(), exam_reply()))
        quick.say(page, "an agent for my stock")
        quick.build(page)
        folder = self.root / qs.AGENTS / "stock_watcher"
        card = json.loads((folder / "card.json").read_text(encoding="utf-8"))
        (folder / "card.json").write_text(json.dumps(dict(card, agent="other")), encoding="utf-8")
        with self.assertRaises(turn.Refused) as e:
            turn.load(folder)
        self.assertIn("its folder is stock_watcher", str(e.exception))


class StackReviewRound1(unittest.TestCase):
    """Review round 1 (2026-11-01), items 2, 4 and 6 on kit/turn.py: the card's tools bound the plug, an agent
    whose card connects whatsapp gets the full send check, at most MAX_CALLS_PER_STEP calls run in one step,
    and no file in the folder is read through a link."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def built(self, needs):
        page = types.SimpleNamespace(reports=self.root, plugs={})
        quick = qs.QuickStart(FakeModel(card_reply(needs=needs), plug_reply(), exam_reply()))
        quick.say(page, "an agent that tells my customers what is in stock")
        quick.build(page)
        return self.root / qs.AGENTS / "stock_watcher"

    def turn(self, agent, model):
        db = Db(":memory:")
        sent = []
        try:
            chats = Chats(db)
            cid = chats.open("whatsapp", "201000000099")
            with practice.match_mod.demo_store():
                out = turn.turn(agent, OPENING, chats=chats, chat_id=cid, model=model,
                                send=lambda to, text: sent.append(text), customer_id="201000000099")
            steps = chats.steps(cid)
        finally:
            db.close()
        return out, sent, steps

    def test_a_plug_tool_the_card_does_not_connect_is_refused(self):
        folder = self.built([{"what": "Your store's stock", "tool": "store"}])
        self.assertEqual(turn.load(folder).tools, ("store",))
        plug = json.loads((folder / "plug.json").read_text(encoding="utf-8"))
        plug["risk"]["high"]["tools"] = ["store", "cod_risk", "draft_order"]
        (folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
        with self.assertRaises(turn.Refused) as e:
            turn.load(folder)
        self.assertIn("the card does not connect: cod_risk, draft_order", str(e.exception))
        card = json.loads((folder / "card.json").read_text(encoding="utf-8"))
        (folder / "card.json").write_text(json.dumps(dict(card, tools="store")), encoding="utf-8")
        with self.assertRaises(turn.Refused) as e:
            turn.load(folder)
        self.assertIn("card.json tools", str(e.exception))

    def test_an_agent_that_connects_whatsapp_gets_the_full_send_check(self):
        """A made up price is refused for an agent that talks to customers, though its plug has no reply action."""
        folder = self.built([{"what": "Your store's stock", "tool": "store"}, {"what": "Customer chats", "tool": "whatsapp"}])
        agent = turn.load(folder)
        self.assertNotIn(turn.REPLY_ACTION, agent.plug.actions)
        self.assertTrue(agent.full_check)
        price = "It is 99,999 EGP."
        out, sent, _ = self.turn(agent, World(agent=lambda m, t: say(price)))
        self.assertEqual((out.outcome, sent, len(out.failed)), ("no_safe_reply", [], turn.MAX_FAILED_CHECKS))
        quiet = turn.load(self.built_again([{"what": "Your store's stock", "tool": "store"}]))
        self.assertFalse(quiet.full_check)  # no customers: the style check only
        out, sent, _ = self.turn(quiet, World(agent=lambda m, t: say(price)))
        self.assertEqual((out.outcome, sent), ("replied", [price]))

    def built_again(self, needs):
        shutil.rmtree(self.root / qs.AGENTS)
        (self.root / qs.DRAFT_FILE).unlink()
        return self.built(needs)

    def test_at_most_max_calls_per_step_run(self):
        folder = self.built([{"what": "Your store's stock", "tool": "store"}])
        many = turn.MAX_CALLS_PER_STEP + 1

        def agent(messages, tools):
            if messages[-1]["role"] == "tool":
                return say(ANSWER)
            call = tool_call("store", {"query": "mercurial"})
            call["tool_calls"] = [dict(call["tool_calls"][0], id=f"c{i}") for i in range(many)]
            return call
        out, sent, steps = self.turn(turn.load(folder), World(agent=agent))
        self.assertEqual((out.outcome, sent), ("replied", [ANSWER]))
        results = [json.loads(s["content"]) for s in steps if s["role"] == "tool"]
        self.assertEqual(len(results), many)
        self.assertEqual(results[-1], dict(turn.loop.TOO_MANY_CALLS))
        self.assertTrue(all(r != turn.loop.TOO_MANY_CALLS for r in results[:-1]))

    def test_no_file_is_read_through_a_link(self):
        folder = self.built([{"what": "Your store's stock", "tool": "store"}])
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        real = Path(outside.name) / "instructions.md"
        real.write_text("Words from outside the folder.", encoding="utf-8")
        (folder / "instructions.md").unlink()
        os.symlink(real, folder / "instructions.md")
        with self.assertRaises(turn.Refused) as e:
            turn.load(folder)
        self.assertIn("no instructions.md", str(e.exception))


class SalesUnchanged(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_a_sales_run_keeps_its_name_and_files(self):
        from tests.test_arena_run import Agent, Customer
        self.assertEqual(run.Arena.agent, "sales")
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.main(["--cards", str(run.DEMO_CARDS), "--matches", "1", "--rounds", "1", "--state", d.name,
                             "--json"], agent_model=Agent(), customer_model=Customer(buyers=()))
        rep = json.loads(out.getvalue())
        self.assertEqual((code, rep["agent"]), (1, "sales"))
        self.assertNotIn("made_up", rep)
        self.assertNotIn("item", rep)  # a Sales run with no study between rounds writes no item, as before
        self.assertTrue((Path(d.name) / run.MATCHES_FILE).exists())
        self.assertEqual(sorted(p.name for p in Path(d.name).glob("arena-sales-*.json")), [])


if __name__ == "__main__":
    unittest.main()
