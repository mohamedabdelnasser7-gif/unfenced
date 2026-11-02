"""Live cases, Builder 1 side (DECISIONS items 68, 71 and 72): the card's case and bad result from Quick
start into card.json, kit/turn.py reading them, the take_action tool and the agent-first turn, the
narrower full send check, practice playing a case (a ticket someone sends, a lead the agent writes to
first), each turn's tools and actions, the learn hook, made-up case inputs and case exam situations.
Fake models only, made-up text only; nothing here calls the network or reads arena/real."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from arena import good, madeup, practice, run
from kit import turn
from kit.chats import Chats
from kit.db import Db
from reflection import quickstart as qs
from reflection import turn_exam
from tests.fake_model import FakeModel, clean_env, say, tool_call

REPO = Path(run.__file__).resolve().parent.parent

TICKET_CASE = {"input": "one support ticket: a subject, a body and the account it came from", "starts": "person",
               "output": "a reply that resolves it and a tag", "ends": "the ticket is resolved or tagged"}
LEAD_CASE = {"input": "a new lead's name and what they asked about", "starts": "agent",
             "output": "a short follow up message", "ends": "the lead answers or a week has passed"}
TICKET = "Subject: refund not received. Body: I returned the jacket two weeks ago and the 250 EGP refund is not back."


def plug_for(agent, actions, case_line):
    return {"agent": agent, "about": "A made-up agent for tests.", "case": case_line, "fields": ["support"],
            "stages": ["open"], "actions": actions,
            "results": {"resolved": {"speed": "fast", "shows_in_days": [0, 1]},
                        "unresolved": {"speed": "fast", "shows_in_days": [0, 1]}},
            "causes": {}, "source": {"about": "The person or record behind the case.", "known_by": "case"},
            "harm": {"results": ["unresolved"]}, "decides": {"good": "resolved", "bad": ["unresolved"]},
            "risk": {"high": {"about": "Money and promises.", "tools": []}, "low": {"about": "Tone."}},
            "trial": {"fast": {"share": 0.5, "days": 7}, "careful": {"share": 0.2, "days": 14}},
            "slot": "Lessons from past cases:"}


def write_agent(root, agent, *, case, actions, tools=(), bad="The case is left open with no tag.", card_extra=None):
    folder = Path(root) / "agents" / agent
    folder.mkdir(parents=True)
    (folder / "plug.json").write_text(json.dumps(plug_for(agent, actions, "One case for tests.")), encoding="utf-8")
    (folder / "instructions.md").write_text("You handle one case at a time for a made-up shop.", encoding="utf-8")
    card = {"agent": agent, "name": agent.replace("_", " "), "does": "handles one case for a made-up shop",
            "good": "The case ends resolved with the right tag.", "never": ["Never promise a date."], "needs": [],
            "tools": list(tools), "level": "careful", "at": 0}
    if case is not None:
        card["case"] = case
    if bad:
        card["bad"] = bad
    card.update(card_extra or {})
    (folder / "card.json").write_text(json.dumps(card), encoding="utf-8")
    return folder


TICKET_ACTIONS = {"reply": "One reply on the ticket.", "tag": "Tag the ticket, for example needs the team.",
                  "close": "Close the ticket once it is resolved."}
LEAD_ACTIONS = {"follow_up": "Write one follow up message to the lead."}


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def one_turn(self, agent, text, script, first=False):
        db = Db(":memory:")
        self.addCleanup(db.close)
        chats = Chats(db)
        cid = chats.open(turn.practice_channel(agent), "201000000099")
        sent, model = [], FakeModel(*script)
        out = turn.turn(agent, text, chats=chats, chat_id=cid, model=model, send=lambda to, t: sent.append(t),
                        customer_id="201000000099", first=first)
        return out, sent, model, chats.steps(cid)


class TheCardCarriesTheCase(Base):
    def test_clean_card_keeps_the_case_and_the_bad_result(self):
        got = qs.clean_card({"card": {"name": "Ticket desk", "key": "ticket_desk", "does": "Answers support tickets.",
                                      "case": dict(TICKET_CASE, starts="someone"), "good": "Resolved and tagged right.",
                                      "bad": "Left open.", "never": [], "needs": []},
                             "question": "", "follow": "Change anything before it builds."})
        self.assertEqual(got["card"]["case"], dict(TICKET_CASE, starts="person"))  # anything but agent reads person
        self.assertEqual(got["card"]["bad"], "Left open.")

    def test_a_card_with_no_case_or_no_bad_result_is_sent_again(self):
        base = {"name": "Ticket desk", "key": "t", "does": "Answers tickets.", "good": "Resolved.", "never": [],
                "needs": []}
        for card in (dict(base, bad="Left open."), dict(base, case=TICKET_CASE),
                     dict(base, case=dict(TICKET_CASE, ends=""), bad="Left open.")):
            with self.assertRaises(qs.Refused):
                qs.clean_card({"card": card, "question": "", "follow": "Change anything."})
        old = qs.clean_card({"card": base, "question": "", "follow": "Change anything."}, need_case=False)
        self.assertNotIn("case", old["card"])

    def test_the_card_prompt_asks_for_the_case_and_asks_only_where_a_case_ends(self):
        for words in ('"case"', '"starts"', '"bad"', "where one case ends is unclear", "needs the team"):
            self.assertIn(words, qs.CARD_PROMPT)

    def test_kit_turn_reads_the_case_and_bad_and_an_old_card_reads_as_before(self):
        folder = write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS)
        agent = turn.load(folder)
        self.assertEqual(agent.card["case"], TICKET_CASE)
        self.assertEqual(agent.card["bad"], "The case is left open with no tag.")
        old = turn.load(write_agent(self.root, "old_desk", case=None, bad="", actions=TICKET_ACTIONS))
        self.assertEqual(sorted(old.card), ["does", "good", "name", "needs", "never"])  # its fingerprint holds

    def test_a_case_out_of_shape_is_refused(self):
        for case in ({"input": "x", "starts": "both", "output": "y", "ends": "z"},
                     dict(TICKET_CASE, extra="no"), dict(TICKET_CASE, output=""), "one ticket"):
            with self.subTest(case=case):
                folder = write_agent(self.root, f"bad_{abs(hash(str(case))) % 10000}", case=case, actions=TICKET_ACTIONS)
                with self.assertRaises(turn.Refused):
                    turn.load(folder)


class EmailAndCalendarAreNotConnectedYet(unittest.TestCase):
    """B7: no kit tool reads a mailbox or a calendar, so a built agent's card marks them not connected."""

    def test_email_and_calendar_needs_read_not_connected(self):
        got = qs.clean_card({"card": {"name": "Inbox", "key": "inbox", "does": "Sorts mail.", "case": TICKET_CASE,
                                      "good": "Sorted.", "bad": "Missed.", "never": [],
                                      "needs": [{"what": "Your mailbox", "tool": "email"},
                                                {"what": "Your calendar", "tool": "calendar"},
                                                {"what": "Your store", "tool": "store"}]},
                             "question": "", "follow": "Change anything."})
        self.assertEqual([n["connected"] for n in got["card"]["needs"]], [False, False, True])
        self.assertEqual(qs.connected(got["card"]), ["store"])
        self.assertIn("email: ", qs._tool_lines())
        self.assertIn("not connected for a new agent yet", qs._tool_lines())


class ThePlanCardShowsTheCase(unittest.TestCase):
    """DECISIONS 68: the card shows One case is, the good result and the bad result, in the model's words."""

    def test_one_case_is_good_and_bad_are_shown(self):
        from reflection import pages
        card = {"name": "Lead follow up", "does": "Follows up new leads.", "case": LEAD_CASE, "good": "The lead answers.",
                "bad": "The lead never hears back.", "never": [], "needs": []}
        html = pages.plan_card(card)
        for words in ("One case is", LEAD_CASE["input"], LEAD_CASE["output"], "The agent writes first",
                      "A good result", "A bad result", "The lead never hears back."):
            self.assertIn(words, html.replace("&#x27;", "'"))
        self.assertNotIn("One case is", pages.plan_card(dict(card, case=None, bad="")))


class ATagIsNotAHandOver(unittest.TestCase):
    """DECISIONS 72: a declared tag action such as needs the team passes; a hand over is still refused."""

    def test_tags_pass(self):
        for text in ("Tag the ticket needs the team when a person must act.",
                     "needs_team: Tag the ticket for the team to pick up.",
                     "Tag the ticket for the support team to handle.",
                     "Tag the ticket so a person can deal with it."):
            with self.subTest(text=text):
                self.assertIsNone(qs.names_a_person(text))

    def test_hand_overs_are_still_refused(self):
        for text in ("escalate the ticket to the support team", "hand the ticket to the support team",
                     "Tag the chat and the team will answer the customer", "tag it and hand the ticket to the team",
                     "flag the case and transfer it to a human", "Tag the ticket, then the team will answer you",
                     "The team will answer the customer"):
            with self.subTest(text=text):
                self.assertIsNotNone(qs.names_a_person(text))


class TheFullSendCheck(Base):
    """B4: the full check only when the card connects whatsapp or store; a folder written by hand keeps
    the reply rule."""

    def test_a_ticket_agent_with_a_reply_action_and_no_store_names_a_refund(self):
        agent = turn.load(write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS))
        self.assertFalse(agent.full_check)
        out, sent, _, _ = self.one_turn(agent, TICKET, [say("Your 250 EGP refund was sent today.")])
        self.assertEqual((out.outcome, sent), ("replied", ["Your 250 EGP refund was sent today."]))

    def test_a_card_that_connects_store_or_whatsapp_keeps_every_check(self):
        for tools in (["store"], ["whatsapp"], ["store", "whatsapp"]):
            with self.subTest(tools=tools):
                agent = turn.load(write_agent(self.root, "shop_" + "_".join(tools), case=TICKET_CASE,
                                              actions={"answer": "One answer."}, tools=tools))
                self.assertTrue(agent.full_check)
                out, sent, _, _ = self.one_turn(agent, "How much is it?", [say("It is 99,999 EGP.")] * turn.MAX_FAILED_CHECKS)
                self.assertEqual((out.outcome, sent), ("no_safe_reply", []))

    def test_a_hand_written_folder_keeps_the_reply_rule(self):
        folder = write_agent(self.root, "hand_written", case=None, bad="", actions=TICKET_ACTIONS)
        card = json.loads((folder / "card.json").read_text())
        del card["tools"]
        (folder / "card.json").write_text(json.dumps(card))
        self.assertTrue(turn.load(folder).full_check)


class Actions(Base):
    def test_a_case_agent_takes_a_declared_action_and_it_is_recorded(self):
        agent = turn.load(write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS))
        self.assertEqual(agent.acts, ("tag", "close"))
        out, sent, model, steps = self.one_turn(agent, TICKET, [
            tool_call(turn.ACT_TOOL, {"action": "tag", "note": "needs the team"}),
            say("Thanks, the team will look at your refund.")])
        self.assertEqual(out.actions, [{"action": "tag", "note": "needs the team"}])
        offered = [t["function"]["name"] for t in model.calls[0]["tools"]]
        self.assertIn(turn.ACT_TOOL, offered)
        act = next(t for t in model.calls[0]["tools"] if t["function"]["name"] == turn.ACT_TOOL)
        self.assertEqual(act["function"]["parameters"]["properties"]["action"]["enum"], ["tag", "close"])
        self.assertEqual(sent, ["Thanks, the team will look at your refund."])

    def test_an_undeclared_action_is_not_recorded(self):
        agent = turn.load(write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS))
        out, _, model, _ = self.one_turn(agent, TICKET, [tool_call(turn.ACT_TOOL, {"action": "reply"}),
                                                         say("Done.")])
        self.assertEqual(out.actions, [])
        self.assertIn("declared actions", model.calls[1]["messages"][-1]["content"])

    def test_a_chat_card_offers_no_action_tool(self):
        agent = turn.load(write_agent(self.root, "old_desk", case=None, bad="", actions=TICKET_ACTIONS))
        self.assertEqual(agent.acts, ())
        _, _, model, _ = self.one_turn(agent, "Hello", [say("Hi, how can I help?")])
        self.assertFalse(model.calls[0]["tools"])


class TheAgentWritesFirst(Base):
    def test_a_first_turn_saves_the_input_under_a_frame_and_writes_first(self):
        agent = turn.load(write_agent(self.root, "lead_follow", case=LEAD_CASE, actions=LEAD_ACTIONS))
        out, sent, model, steps = self.one_turn(agent, "Lead: a made-up buyer asked about running shoes.",
                                                [say("Hi, you asked about running shoes. Want to see three picks?")],
                                                first=True)
        self.assertEqual(out.outcome, "replied")
        first_user = next(s for s in steps if s["role"] == "user")["content"]
        self.assertIn("You write first", first_user)
        self.assertIn("running shoes", first_user)
        self.assertEqual(turn.practice_channel(agent), turn.PRACTICE_CHANNEL)


class PractiseWorld:
    """The made-up cards writer, the practice person, the agent and the judge for one case agent."""

    def __init__(self, people, person=None, agent=None, reached=True):
        self.people, self.person, self.agent, self.reached = people, person, agent, reached
        self.systems, self.judged, self.calls = [], [], {"cards": 0, "person": 0, "agent": 0, "judge": 0}

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        self.systems.append(system)
        if system.startswith(madeup.SYSTEM[:60]):
            self.calls["cards"] += 1
            return say(json.dumps({"customers": self.people}))
        if system == good.SYSTEM:
            self.calls["judge"] += 1
            self.judged.append(json.loads(messages[1]["content"]))
            return say(json.dumps({"reached": self.reached, "broke_never": False, "turn": 1, "why": "made up"}))
        if system.startswith(("You are the person behind one case", "You are a person that an agent")):
            self.calls["person"] += 1
            return self.person(messages)
        self.calls["agent"] += 1
        return self.agent(messages, tools)


def person(kind="never", input_=TICKET):
    return {"want": ["the refund back"], "worry": "the money is lost", "settles_it": ["a clear refund date"],
            "language": "english", "length": "short", "opening": "refund", "examples": ["Where is my refund?"],
            "input": input_, **({"why_not": "the refund was never asked for"} if kind == "never" else {})}


class PractiseACase(Base):
    def practise(self, folder, world, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rep = practice.practise(folder, agent_model=world, customer_model=world, judge_model=world, quick=True, **kw)
        return rep

    def test_a_ticket_opens_with_its_input_and_each_turn_carries_tools_and_actions(self):
        folder = write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS)
        agent = turn.load(folder)

        def agent_side(messages, tools):
            if messages[-1]["role"] == "tool":
                return say("Your refund is on its way.")
            return tool_call(turn.ACT_TOOL, {"action": "close", "note": "refund sent"})
        world = PractiseWorld([], person=lambda m: say("Thanks " + practice.DONE), agent=agent_side)
        card = madeup.card_of(1, "easy", person("easy"), agent.name, "x", 2)
        self.assertEqual(card["input"], TICKET)
        m = practice.play(agent, card, agent_model=world, customer_model=world)
        self.assertEqual(m["turns"][0]["customer"], TICKET)  # the case's input, no model call for it
        self.assertEqual((m["turns"][0]["tools"], m["turns"][0]["actions"]), ([], ["close"]))
        self.assertEqual(m["turns"][0]["acted"], [{"action": "close", "note": "refund sent"}])
        self.assertEqual((m["ended"], m["prompt_sha"]), ("done", practice.CASE_SHA))
        person_system = next(s for s in world.systems if s.startswith("You are the person behind one case"))
        self.assertIn(TICKET_CASE["ends"], person_system)
        self.assertIn(practice.CASE_SHA, practice.PROMPTS)

    def test_a_lead_the_agent_writes_to_first_is_a_real_match_with_no_customer_line(self):
        folder = write_agent(self.root, "lead_follow", case=LEAD_CASE, actions=LEAD_ACTIONS)
        agent = turn.load(folder)
        lead = person("easy", input_="Lead: a made-up buyer asked about running shoes on Monday.")
        seen = []
        world = PractiseWorld([], person=lambda m: seen.append(m) or say(practice.LEAVE),
                              agent=lambda m, t: say("Hi, you asked about running shoes. Still looking?"))
        card = madeup.card_of(1, "easy", lead, agent.name, "x", 2)
        m = practice.play(agent, card, agent_model=world, customer_model=world, opening="")
        first = m["turns"][0]
        self.assertEqual((first["customer"], first["input"]), ("", lead["input"]))
        self.assertEqual(first["replies"], ["Hi, you asked about running shoes. Still looking?"])
        self.assertEqual((m["ended"], m["prompt_sha"], len(m["turns"])), ("left", practice.FIRST_SHA, 1))
        self.assertEqual([x["role"] for x in seen[0]], ["system", "user"])  # the agent's message comes first
        self.assertEqual(seen[0][1]["content"], first["replies"][0])
        judged = good.judge(m, agent.card, world, facts=False)
        self.assertTrue(judged["won"])  # agent output with no customer line reaches the judge

    def test_a_lost_training_match_is_handed_to_learn(self):
        folder = write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS)
        handed = []
        world = PractiseWorld([person("easy"), person("easy")], person=lambda m: say("ok " + practice.DONE),
                              agent=lambda m, t: say("We are looking at it."), reached=False)
        rep = self.practise(folder, world, learn=lambda m, judged, mid: handed.append((m["id"], judged["won"])) or mid)
        self.assertEqual(rep["stopped"] != run.PASSED, True)
        self.assertTrue(handed)
        self.assertTrue(all(won is False for _, won in handed))
        cards = sorted((folder / madeup.FOLDER).iterdir())
        self.assertTrue(all("input" in json.loads(p.read_text()) for p in cards))

    def test_the_made_up_cards_ask_for_the_case_and_a_chat_card_asks_as_before(self):
        world = PractiseWorld([person("easy"), person("never")])
        agent = turn.load(write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS))
        madeup.write(agent.name, agent.card, world)
        self.assertEqual(world.systems[-1], madeup.SYSTEM + madeup.CASE_PART)
        old = turn.load(write_agent(self.root, "old_desk", case=None, bad="", actions=TICKET_ACTIONS))
        madeup.write(old.name, old.card, world)
        self.assertEqual(world.systems[-1], madeup.SYSTEM)


class CaseExam(Base):
    def test_case_situations_carry_earlier_turns_and_an_agent_first_case_its_input(self):
        card = {"name": "Ticket desk", "does": "answers tickets", "good": "resolved", "never": ["Never promise a date."],
                "case": TICKET_CASE}
        msgs = turn_exam.ask(card, [])
        self.assertTrue(msgs[0]["content"].endswith(turn_exam.CASE_PART))
        content = json.dumps({"situations": [
            {"part": "good", "title": "A refund", "message": TICKET, "tool": "", "never": 0,
             "before": [{"from": "person", "text": "Hello?"}, {"from": "agent", "text": "Hi, send the details."}]},
            {"part": "never", "title": "Wants a date", "message": "When exactly?", "tool": "", "never": 1},
            {"part": "good", "title": "Another", "message": "My order is late.", "tool": "", "never": 0}]})
        got = turn_exam.situations_from(content, card, [], "open")
        self.assertEqual(got["situations"][0]["turns"],
                         [{"customer": "Hello?"}, {"agent": "Hi, send the details."}, {"customer": TICKET}])
        lead = dict(card, case=LEAD_CASE)
        got = turn_exam.situations_from(content, lead, [], "open")
        self.assertEqual(got["situations"][0]["turns"], [{"input": TICKET, "first": True}])

    def test_an_agent_first_situation_runs_as_a_first_turn(self):
        agent = turn.load(write_agent(self.root, "lead_follow", case=LEAD_CASE, actions=LEAD_ACTIONS))
        s = {"id": 1, "turns": [{"input": "Lead: a made-up buyer.", "first": True}]}
        model = FakeModel(tool_call(turn.ACT_TOOL, {"action": "follow_up", "note": "first touch"}),
                          say("Hi, still looking for shoes?"))
        did = turn_exam.answer(s, None, agent=agent, model=model)
        self.assertEqual((did["reply"], did["customer_text"], did["tools"], did["actions"]),
                         ("Hi, still looking for shoes?", "", [], ["follow_up"]))


class BuildWritesTheCase(Base):
    def test_build_writes_case_bad_and_one_stage(self):
        from reflection import morning as mo
        from engine import plug as plug_mod
        from tests.test_quickstart import card_reply, exam_reply, plug_dict, plug_reply
        m = mo.Morning(Db(str(self.root / "ascent.db")), [plug_mod.load(REPO / "sales" / "plug.json")], reports=self.root)
        self.addCleanup(m.db.close)
        quick = qs.QuickStart(FakeModel(card_reply(case=TICKET_CASE), plug_reply(plug_dict(stages=["new", "waiting"])),
                                        exam_reply()))
        quick.say(m, "an agent for my support tickets")
        quick.build(m)
        folder = self.root / "agents" / "stock_watcher"
        card = json.loads((folder / "card.json").read_text())
        self.assertEqual((card["case"], card["bad"]), (TICKET_CASE, "You hear about a low item only after it ran out."))
        self.assertEqual(json.loads((folder / "plug.json").read_text())["stages"], ["new"])
        self.assertEqual(turn.load(folder).card["case"], TICKET_CASE)

    def test_a_draft_saved_before_cases_is_not_built_until_the_card_is_written_again(self):
        from reflection import morning as mo
        m = mo.Morning(Db(str(self.root / "ascent.db")), [], reports=self.root)
        self.addCleanup(m.db.close)
        (self.root / qs.DRAFT_FILE).write_text(json.dumps({"turns": [{"said": "an agent", "card": {
            "name": "Old", "key": "old", "does": "Does a thing.", "good": "Good.", "never": [], "needs": []},
            "question": "", "follow": "Change anything."}], "built": None, "builds": 0}))
        quick = qs.QuickStart(FakeModel())
        self.assertEqual(len(quick.draft(m)["turns"]), 1)
        with self.assertRaises(qs.Refused) as e:
            quick.build(m)
        self.assertIn("no case yet", str(e.exception))


class BuildStartsAShortPractice(Base):
    """C8: after a successful Build, one short practice in the background, only with the real model."""

    def setUp(self):
        super().setUp()
        from reflection import morning as mo
        self.m = mo.Morning(Db(str(self.root / "ascent.db")), [], reports=self.root)
        self.addCleanup(self.m.db.close)

    def real(self, practise, key=True):
        """QuickStart with no model handed in (the real one), with practise and the model faked."""
        from unittest import mock
        for p in (mock.patch.object(qs.model_mod, "has_key", return_value=key),
                  mock.patch.object(qs.model_mod, "Model", lambda *a, **k: FakeModel()),
                  mock.patch.object(practice, "practise", practise)):
            p.start()
            self.addCleanup(p.stop)
        return qs.QuickStart()

    @staticmethod
    def wait(agent):
        import threading
        for t in threading.enumerate():
            if t.name == f"practice-{agent}":
                t.join(5)

    def test_build_with_a_test_model_starts_no_practice(self):
        from engine import plug as plug_mod
        from reflection import morning as mo
        from tests.test_quickstart import card_reply, exam_reply, plug_reply
        m = mo.Morning(Db(str(self.root / "ascent.db")), [plug_mod.load(REPO / "sales" / "plug.json")], reports=self.root)
        self.addCleanup(m.db.close)
        quick = qs.QuickStart(FakeModel(card_reply(case=TICKET_CASE), plug_reply(), exam_reply()))
        quick.say(m, "an agent for my support tickets")
        said = quick.build(m)
        self.assertNotIn(qs.PRACTISING, said)
        self.assertIsNone(quick.practice_line("stock_watcher"))

    def test_the_real_model_practises_the_new_agent_quick_in_the_background(self):
        got = []
        quick = self.real(lambda folder, **kw: got.append((folder, kw)))
        self.assertEqual(quick.start_practice(self.m, "ticket_desk"), qs.PRACTISING)
        self.wait("ticket_desk")
        (folder, kw), = got
        self.assertEqual(folder, self.root / "agents" / "ticket_desk")
        self.assertIs(kw["quick"], True)
        self.assertIsNone(kw["learn"])  # no database path on this page, so no case is written
        self.assertEqual(quick.practice_line("ticket_desk"), qs.PRACTICE_DONE)

    def test_the_page_never_waits_and_one_practice_runs_at_a_time(self):
        import threading
        go = threading.Event()
        quick = self.real(lambda folder, **kw: go.wait(5))
        self.assertEqual(quick.start_practice(self.m, "ticket_desk"), qs.PRACTISING)
        self.assertEqual(quick.practice_line("ticket_desk"), qs.PRACTISING)  # returned while it still runs
        self.assertEqual(quick.start_practice(self.m, "lead_follow"), qs.PRACTICE_BUSY)
        self.assertIsNone(quick.practice_line("lead_follow"))
        go.set()
        self.wait("ticket_desk")
        self.assertEqual(quick.practice_line("ticket_desk"), qs.PRACTICE_DONE)

    def test_no_key_is_one_plain_line_and_starts_nothing(self):
        got = []
        quick = self.real(lambda folder, **kw: got.append(folder), key=False)
        self.assertEqual(quick.start_practice(self.m, "ticket_desk"), qs.PRACTICE_NO_KEY)
        self.assertEqual(got, [])

    def test_a_practice_that_cannot_run_says_why_and_frees_the_slot(self):
        def refuse(folder, **kw):
            raise run.Refused("the day's model calls are used up")
        quick = self.real(refuse)
        quick.start_practice(self.m, "ticket_desk")
        self.wait("ticket_desk")
        self.assertEqual(quick.practice_line("ticket_desk"),
                         qs.PRACTICE_NOT_RUN.format(why="the day's model calls are used up"))
        self.assertEqual(quick.start_practice(self.m, "lead_follow"), qs.PRACTISING)
        self.wait("lead_follow")

    def test_with_a_database_each_lost_match_goes_to_the_learn_hook(self):
        import sys
        import types
        from unittest import mock
        write_agent(self.root, "ticket_desk", case=TICKET_CASE, actions=TICKET_ACTIONS)
        fake = types.ModuleType("arena.learn_built")
        fake.learner = lambda db, plug: ("learner", plug.agent)
        got = []
        quick = self.real(lambda folder, **kw: got.append(kw["learn"]))
        self.m.db_path = str(self.root / "ascent.db")
        import arena
        with mock.patch.dict(sys.modules, {"arena.learn_built": fake}), \
                mock.patch.object(arena, "learn_built", fake, create=True):
            quick.start_practice(self.m, "ticket_desk")
            self.wait("ticket_desk")
        self.assertEqual(got, [("learner", "ticket_desk")])

    def test_the_new_agent_page_shows_it_is_practising(self):
        from reflection import pages
        from tests.test_quickstart import card_reply, exam_reply, plug_reply
        p = pages.Pages(self.m, model=FakeModel(card_reply(case=TICKET_CASE), plug_reply(), exam_reply()))
        p.actions["/quickstart"](self.m, {"text": ["an agent for my support tickets"]})
        p.actions["/quickstart/build"](self.m, {})
        self.assertNotIn(qs.PRACTISING, p.get("/new", {}, "t"))
        p.quick._practice["stock_watcher"] = qs.PRACTISING
        self.assertIn(qs.PRACTISING, p.get("/new", {}, "t"))


if __name__ == "__main__":
    unittest.main()
