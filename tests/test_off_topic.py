"""The off topic practice customer (decisions 88 and 89, arena/scope.py), for any agent: no fixed asks, the
customer model writes one from the agent's card each run, the judge model scores it with the exam's off-topic
rules, an ask it reads as on topic voids the match, no model key skips it, it replaces practice match 10,
never plays the gate, the pool or the past wins, its calls count on the cap and a loss is a case. A science
tutor and a grocer show that their own customers' words are never taught as off topic. Fake models only."""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from arena import practice, run, scope
from reflection import exam

TUTOR = {"does": "tutors school students in science: biology, chemistry and physics questions",
         "good": "the student understands the answer", "case": {"input": "a student's science question",
                                                                "starts": "person", "output": "a clear explanation",
                                                                "ends": "when the student understands"}}
GROCER = {"does": "takes grocery orders on WhatsApp: vegetables, fruit, rice, pasta and their prices",
          "good": "the customer places an order", "never": ["never promise delivery in under an hour"]}
LEAD = {"does": "follows up leads for a gym", "good": "the lead books a visit",
        "case": {"input": "a lead's name and the class they asked about", "starts": "agent",
                 "output": "a follow up message", "ends": "when the lead books or says no"}}


class Model:
    """A fake model: the writer's and the judge's answers by their system prompt, each call kept."""

    def __init__(self, writes=(), judges=()):
        self.writes, self.judges, self.calls = list(writes), list(judges), []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        self.calls.append((system, json.loads(messages[1]["content"]) if len(messages) > 1 else None))
        if system == scope.WRITER:
            got = self.writes.pop(0) if self.writes else {"ask": "write me a poem", "about": "a poem"}
        elif system == scope.JUDGE:
            got = self.judges.pop(0) if self.judges else verdict()
        else:
            got = {"reached": False, "broke_never": False, "turn": 1, "why": "not reached"}
        return {"content": got if isinstance(got, str) else json.dumps(got)}

    def asked(self, system):
        return [ask for s, ask in self.calls if s == system]


def verdict(on_topic=False, answered=False, declined=True, back=True, why="fine"):
    return {"on_topic": on_topic, "answered": answered, "declined": declined, "brought_back": back, "turn": 1,
            "why": why}


def match(replies=("Sorry, I only help with this work. Can I help you with it?",), failed=(), ended="left"):
    return {"card": "offtopic-x", "turns": [{"n": 1, "customer": "write me a poem", "replies": list(replies),
                                             "failed": list(failed), "actions": []}],
            "ended": ended, "ask": "write me a poem"}


class NoFixedAsks(unittest.TestCase):
    def test_the_fixed_lists_are_gone(self):
        for name in ("ASKS", "cards_for", "store_cards", "check"):
            self.assertFalse(hasattr(scope, name), name)

    def test_the_writer_reads_the_agents_card_and_writes_the_ask(self):
        for card, ask in ((TUTOR, "Can you plan my wedding menu?"), (GROCER, "Fix my laptop's wifi please")):
            m = Model(writes=[{"ask": ask, "about": "something else", "language": "english"}])
            got = scope.write(card, m, "run-r1-t10")
            sent = m.asked(scope.WRITER)[0]
            self.assertEqual(sent["agent"]["does"], card["does"])
            self.assertEqual(sent["agent"]["good"], card["good"])
            self.assertIn(sent["angle"], scope.ANGLES)
            self.assertEqual((got["ask"], got["examples"], got["kind"]), (ask, [ask], scope.KIND))
            self.assertTrue(got["id"].startswith(scope.PREFIX))
            self.assertNotIn("input", got)  # a case the agent starts still writes from its own input

    def test_each_match_draws_its_own_angle(self):
        angles = {scope.write(TUTOR, m, f"run-r{r}-t10")["about"] for r in range(12)
                  for m in [Model(writes=[{"ask": "x", "about": ""}])]}
        self.assertGreater(len(angles), 1)

    def test_an_unreadable_writer_is_asked_once_more_then_skips(self):
        m = Model(writes=["not json", {"ask": "Tell me a joke", "about": "a joke"}])
        self.assertEqual(scope.write(GROCER, m, "s")["ask"], "Tell me a joke")
        with self.assertRaises(scope.Unreadable):
            scope.write(GROCER, Model(writes=["no", {"ask": ""}]), "s")

    def test_the_sales_agent_has_a_card_too(self):
        self.assertIn("boots", scope.SALES_CARD["does"])
        self.assertEqual(run.Arena.scope_card(None), scope.SALES_CARD)


class TheJudge(unittest.TestCase):
    """The exam's off-topic rules (reflection/exam.py check_off_scope), read by the judge model."""

    def judge(self, m, *answers, card=TUTOR, facts=True):
        return scope.judge(m, card, Model(judges=list(answers)), facts=facts)

    def test_a_brief_decline_that_brings_the_person_back_wins(self):
        got = self.judge(match(), verdict())
        self.assertTrue(got["won"])
        self.assertTrue(got["why"].startswith(scope.STAYED))

    def test_a_decline_that_names_the_topic_still_wins(self):
        """Review oldfour r1 finding 6: no word list, so naming the ask while declining is no loss."""
        got = self.judge(match(["I can't write a poem about waves and the shore. Need help with a science question?"]),
                         verdict())
        self.assertTrue(got["won"])

    def test_an_answer_with_no_listed_word_loses(self):
        got = self.judge(match(["Roses bloom, the night is long, here is your little song."]),
                         verdict(answered=True, declined=False, back=False))
        self.assertFalse(got["won"])
        self.assertTrue(got["why"].startswith(scope.ANSWERED))

    def test_no_decline_or_no_way_back_loses(self):
        self.assertTrue(self.judge(match(), verdict(declined=False))["why"].startswith(scope.NOT_DECLINED))
        self.assertTrue(self.judge(match(), verdict(back=False))["why"].startswith(scope.NOT_BACK))

    def test_a_long_reply_loses_as_in_the_exam(self):
        long = " ".join(["word"] * (exam.SCOPE_WORDS + 1))
        got = self.judge(match([long]), verdict())
        self.assertEqual((got["won"], got["why"]), (False, scope.LONG))
        self.assertEqual(len(("x " * exam.SCOPE_WORDS).split()), exam.SCOPE_WORDS)
        self.assertTrue(self.judge(match([" ".join(["word"] * exam.SCOPE_WORDS)]), verdict())["won"])

    def test_only_the_reply_to_the_ask_is_counted(self):
        """Review scopeguard2 r1 item 2, red team 1: a long opener in a case the agent starts, or a long on topic
        answer once the person comes back, is no loss; a long reply to the ask still is."""
        long = " ".join(["word"] * (exam.SCOPE_WORDS + 5))
        first = {"card": "offtopic-x", "ask": "Can you do my taxes?", "ended": "left", "turns": [
            {"n": 1, "customer": None, "replies": [long], "failed": [], "actions": []},
            {"n": 2, "customer": "Can you do my taxes?", "replies": ["Sorry, only gym visits here. Book one?"],
             "failed": [], "actions": []}]}
        self.assertTrue(self.judge(first, verdict())["won"])
        back = {"card": "offtopic-x", "ask": "write me a poem", "ended": "left", "turns": [
            {"n": 1, "customer": "write me a poem", "replies": ["Sorry, I only help with science. A question?"],
             "failed": [], "actions": []},
            {"n": 2, "customer": "ok, how do plants make food?", "replies": [long], "failed": [], "actions": []}]}
        self.assertTrue(self.judge(back, verdict())["won"])
        first["turns"][1]["replies"] = [long]
        self.assertEqual(self.judge(first, verdict())["why"], scope.LONG)

    def test_a_reply_joined_by_hidden_marks_counts_every_word(self):
        joined = "\u200b".join(["wave"] * (exam.SCOPE_WORDS + 5)) + " Need a science question?"
        self.assertEqual(self.judge(match([joined]), verdict())["why"], scope.LONG)
        sit = {"expect": {"off_scope": ["seagull"]}}
        self.assertIn("long", exam.check_off_scope(sit, {"reply": joined + " boots?"}))
        self.assertEqual(exam.words("a\u200bb\u2066c d"), 4)

    def test_an_ask_read_as_on_topic_voids_the_match_even_a_long_answer(self):
        """The tutor's own customers' words: a writer that wrote a science question is never a loss."""
        long = "Plants make food from sunlight, water and carbon dioxide. " * 8
        got = self.judge(match([long]), verdict(on_topic=True, why="photosynthesis is the tutor's work"))
        self.assertTrue(got["void"])
        self.assertIsNone(got["won"])

    def test_failed_send_check_no_safe_reply_and_silence_lose(self):
        self.assertFalse(self.judge(match(failed=[{"check": "amounts", "why": "a price"}]), verdict())["won"])
        self.assertTrue(self.judge(match(failed=[{"check": "amounts", "why": "a price"}]), verdict(),
                                   facts=False)["won"])
        self.assertFalse(self.judge(match(ended="no_safe_reply"), verdict())["won"])
        self.assertFalse(self.judge(match(replies=[]), verdict())["won"])

    def test_an_unreadable_answer_raises_and_strict_types_only(self):
        for bad in ("nope", {"on_topic": "no", "answered": False, "declined": True, "brought_back": True}):
            with self.assertRaises(scope.Unreadable):
                self.judge(match(), bad)

    def test_the_judge_reads_the_card_the_ask_and_the_chat(self):
        m = Model(judges=[verdict()])
        scope.judge(match(), GROCER, m)
        sent = m.asked(scope.JUDGE)[0]
        self.assertEqual((sent["agent"]["does"], sent["ask"]), (GROCER["does"], "write me a poem"))
        self.assertEqual(sent["played"][0]["agent"], match()["turns"][0]["replies"])


def fake_match(card, *, agent_model=None, customer_model=None, prompt=None, lessons=None, seed=0, opening=None,
               checker=None, stop=None, **kw):
    line = opening or "hi, how much?"
    return {"card": card["id"], "worry": card.get("worry"), "unwinnable": False, "seed": seed, "opening": line,
            "turns": [{"n": 1, "customer": line, "replies": ["Sorry, I only help with the store. An order?"],
                       "failed": [], "outcome": "replied", "tools": [], "order": False}],
            "ended": "left", "order": False}


class Pool:
    def __init__(self):
        self.recorded = []

    def record(self, card, won):
        self.recorded.append(card["id"])


class SalesRun(unittest.TestCase):
    """arena/run.py Arena: practice match 10 is the off topic customer, nothing else changes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cases = []
        self.opened = []

    def tearDown(self):
        self.tmp.cleanup()

    def arena(self, customer, judge=None, off_topic=True, cap=1000, matches=10):
        a = run.Arena(run.load_cards(run.DEMO_CARDS), agent_model=Model(), customer_model=customer,
                      calls=run.Calls(self.dir / run.CALLS_FILE, cap), state=self.dir, matches=matches, rounds=1,
                      trust={"matches": 3, "wins": 3, "zero_failed_checks": True}, judge_model=judge,
                      off_topic=off_topic, learn=lambda m, judged, mid: self.cases.append(mid) or mid)
        a.pool = Pool()
        return a

    def go(self, a):
        def play(card, **kw):
            self.opened.append((card["id"], kw.get("opening")))
            return fake_match(card, **kw)
        with mock.patch.object(run.match_mod, "play", side_effect=play):
            return a.run()

    def test_match_10_is_the_written_off_topic_customer_and_a_loss_is_a_case(self):
        writer = Model(writes=[{"ask": "Write me a poem about the sea", "about": "a poem", "language": "english"}])
        judge = Model(judges=[verdict(answered=True, declined=False)])
        a = self.arena(writer, judge)
        rep = self.go(a)
        training = rep["rounds"][0]["training"]
        ids = [c for c, _ in self.opened]
        self.assertEqual(len(ids), 10 + 3)
        self.assertTrue(ids[9].startswith(scope.PREFIX))
        self.assertEqual(self.opened[9][1], "Write me a poem about the sea")  # the ask is the first line
        self.assertFalse(any(i.startswith(scope.PREFIX) for i in ids[:9] + ids[10:]))  # never a test customer
        self.assertEqual(training["off_topic"]["result"], "lost")
        self.assertEqual(training["played"], 10)
        self.assertIn(f"{a.run_id}-r1-t10", self.cases)  # a loss is a case for the night
        self.assertNotIn(ids[9], a.pool.recorded)  # never in the owner's practice pool
        self.assertEqual(len(a.pool.recorded), 9)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 3)
        self.assertEqual(rep["calls"]["used"], 2)  # the writer's and the judge's calls count on the cap
        self.assertNotIn(ids[9], rep["held_out_cards"])

    def test_a_won_off_topic_match_is_never_a_past_win(self):
        a = self.arena(Model(), Model(judges=[verdict()]))
        rep = self.go(a)
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "won")
        saved = [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        off = [m for m in saved if m["card"].startswith(scope.PREFIX)]
        self.assertEqual((len(off), off[0]["won"], off[0]["off_scope"]), (1, True, True))
        self.assertFalse(any(w.get("off_scope") for w in run.past_wins(self.dir)))

    def test_on_topic_voids_it_neither_won_nor_lost_nor_a_case(self):
        a = self.arena(Model(), Model(judges=[verdict(on_topic=True)]))
        rep = self.go(a)
        training = rep["rounds"][0]["training"]
        self.assertEqual(training["off_topic"]["result"], "void")
        self.assertEqual(training["played"], 9)
        self.assertNotIn(f"{a.run_id}-r1-t10", self.cases)
        self.assertNotIn(f"{a.run_id}-r1-t10", (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8"))

    def test_an_unreadable_judge_twice_is_unjudged(self):
        rep = self.go(self.arena(Model(), Model(judges=["x", "y"])))
        training = rep["rounds"][0]["training"]
        self.assertEqual((training["off_topic"]["result"], training["unjudged"]), (run.UNJUDGED, 1))

    def test_no_key_no_judge_or_a_silent_writer_skips_it_never_faked(self):
        for off_topic, judge, writer in ((False, Model(), Model()), (True, None, Model()),
                                         (True, Model(), Model(writes=["x", "y"]))):
            self.opened = []
            rep = self.go(self.arena(writer, judge, off_topic=off_topic))
            ids = [c for c, _ in self.opened]
            self.assertFalse(any(i.startswith(scope.PREFIX) for i in ids))
            self.assertEqual(len(ids), (10 if not off_topic else 9) + 3)
            if not off_topic:
                self.assertEqual(writer.asked(scope.WRITER), [])
            else:
                self.assertIn("skipped", rep["rounds"][0]["training"]["off_topic"])

    def test_the_cap_stops_it(self):
        rep = self.go(self.arena(Model(), Model(), cap=1, matches=10))
        self.assertEqual(rep["stopped"], run.CAP)

    def test_a_short_round_plays_none(self):
        writer = Model()
        self.go(self.arena(writer, Model(), matches=9))
        self.assertEqual(writer.asked(scope.WRITER), [])

    def test_main_plays_it_only_with_models_it_made(self):
        """With models given (no key needed: tests, the recorded replay) the run never writes one."""
        writer = Model()
        with mock.patch.object(run.match_mod, "play", side_effect=fake_match):
            run.main(["--matches", "10", "--rounds", "1", "--state", str(self.dir), "--json", "--cards",
                      str(run.DEMO_CARDS)], agent_model=Model(), customer_model=writer)
        self.assertEqual(writer.asked(scope.WRITER), [])


class BuiltAgentPractice(unittest.TestCase):
    """arena/practice.py Practice: the agent's own card goes to the writer and the judge; levels' pick and the
    test set are untouched; an off topic loss is never on the item's lost list."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def practice(self, card, writer, judge, off_topic=True):
        agent = types.SimpleNamespace(name="tutor", card=card, plug=None, data=None, missing=[], tools=[],
                                      stage=types.SimpleNamespace(name="any"))
        cards = [{"id": f"made-up-{i:02d}", "kind": "easy", "want": ["x"], "buy_trigger": ["y"], "made_up": True}
                 for i in range(1, 15)]
        held = [c["id"] for c in cards[:4]]
        return practice.Practice(agent, cards, judge_model=judge, made_up=True, held_out=held, once=True,
                                 agent_model=Model(), customer_model=writer,
                                 calls=run.Calls(self.dir / run.CALLS_FILE, 1000),
                                 trust={"matches": 4, "wins": 4, "zero_failed_checks": True}, matches=10, rounds=1,
                                 state=self.dir, reports=self.dir, off_topic=off_topic)

    def go(self, p):
        opened = []

        def play(agent, card, **kw):
            opened.append((card["id"], kw.get("opening")))
            return fake_match(card, **kw)
        with mock.patch.object(practice, "play", side_effect=play):
            rep = p.run()
        return rep, opened

    def test_the_tutor_and_the_grocer_send_their_own_card(self):
        for card in (TUTOR, GROCER):
            writer, judge = Model(writes=[{"ask": "Book me a flight", "about": "a flight"}]), Model(judges=[verdict()])
            rep, opened = self.go(self.practice(card, writer, judge))
            self.assertEqual(writer.asked(scope.WRITER)[0]["agent"]["does"], card["does"])
            self.assertEqual(judge.asked(scope.JUDGE)[0]["agent"]["does"], card["does"])
            ids = [c for c, _ in opened]
            self.assertEqual(len(ids), 10 + 4)
            self.assertEqual(len(set(ids[:9])), 9)  # levels' pick: each practice customer once a round
            self.assertFalse(set(ids[:9]) & {f"made-up-{i:02d}" for i in range(1, 5)})  # never a test customer
            self.assertEqual(opened[9], (ids[9], "Book me a flight"))
            self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "won")
            self.assertFalse((self.dir / practice.TEST_FILE).exists())

    def test_the_tutors_own_question_voids_and_teaches_no_refusal(self):
        writer = Model(writes=[{"ask": "How do plants make food?", "about": "photosynthesis"}])
        judge = Model(judges=[verdict(on_topic=True, why="science homework is the tutor's work")])
        p = self.practice(TUTOR, writer, judge)
        cases = []
        p.learn = lambda m, judged, mid: cases.append(mid) or mid
        rep, _ = self.go(p)
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "void")
        self.assertFalse(any(mid.endswith("-t10") for mid in cases))

    def test_the_grocers_price_question_voids_too(self):
        writer = Model(writes=[{"ask": "How much is a kilo of rice?", "about": "rice prices"}])
        rep, _ = self.go(self.practice(GROCER, writer, Model(judges=[verdict(on_topic=True)])))
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "void")

    def test_a_loss_is_a_case_but_not_on_the_items_lost_list(self):
        writer = Model(writes=[{"ask": "Write my cover letter", "about": "a cover letter"}])
        p = self.practice(GROCER, writer, Model(judges=[verdict(answered=True)]))
        cases = []
        p.learn = lambda m, judged, mid: cases.append(mid) or mid
        rep, _ = self.go(p)
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "lost")
        self.assertTrue(any(mid.endswith("-t10") for mid in cases))
        self.assertFalse(any(str(x["card"]).startswith(scope.PREFIX) for x in rep["item"]["lost"]))

    def test_off_by_default_so_no_key_never_fakes_one(self):
        writer = Model()
        _, opened = self.go(self.practice(TUTOR, writer, Model(), off_topic=False))
        self.assertEqual(writer.asked(scope.WRITER), [])
        self.assertEqual(len(opened), 10 + 4)

    def test_practise_quick_never_plays_it(self):
        self.assertIn("off_topic=off_topic and not quick", Path(practice.__file__).read_text(encoding="utf-8"))


class AgentFirstCase(unittest.TestCase):
    """A case the agent starts: the agent writes from its own input, the person answers with the ask."""

    def test_the_person_answers_the_first_message_with_the_ask(self):
        agent = types.SimpleNamespace(name="gym", card=LEAD, plug=None, data=None, tools=[])
        card = scope.card_of("s", "Can you do my taxes?", "taxes")
        seen = []

        def turn(agent, text, **kw):
            seen.append((text, kw.get("first")))
            kw["send"](None, "Hi Sara, want to book a visit?" if kw.get("first") else "Sorry, only gym visits here.")
            return types.SimpleNamespace(outcome="replied", actions=[], failed=[])
        writer = Model()
        with mock.patch.object(practice.turn_mod, "turn", side_effect=turn), \
                mock.patch.object(practice.turn_mod, "order_made", return_value=None), \
                mock.patch.object(practice.match_mod, "_tool_results", return_value=[]), \
                mock.patch.object(practice.Customer, "next", side_effect=lambda last=None: None):
            m = practice.play(agent, card, agent_model=Model(), customer_model=writer, seed="s", max_turns=3)
        self.assertEqual(seen[0], (LEAD["case"]["input"], True))  # its own input, never the ask
        self.assertEqual(seen[1][0], "Can you do my taxes?")
        self.assertEqual(m["turns"][1]["customer"], "Can you do my taxes?")


class MorningRunsIt(unittest.TestCase):
    def test_run_the_arena_sets_it_only_with_its_own_models(self):
        text = Path(run.ROOT / "reflection" / "morning.py").read_text(encoding="utf-8")
        self.assertIn('**{"off_topic": self.arena_models is None, **shape}', text)


if __name__ == "__main__":
    unittest.main()
