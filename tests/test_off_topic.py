"""The off topic practice customer (decisions 88 and 89, arena/scope.py), for any agent: no fixed asks, the
customer model writes one from the agent's card each run, the judge model scores it with the exam's off-topic
rules, an ask it reads as on topic voids the match, no model key skips it, it replaces practice match 10,
never plays the gate, the pool or the past wins, its calls count on the cap and a loss is a case. A science
tutor and a grocer show that their own customers' words are never taught as off topic. Fake models only."""
import contextlib
import io
import json
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from arena import practice, run, scope
from kit.model import ModelError
from reflection import exam
from tests.fake_model import clean_env
from tests.test_arena_practice import FIXTURE, World
from tests.test_levels_morning import Page

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

    def __init__(self, writes=(), judges=(), pres=()):
        self.writes, self.judges, self.pres, self.calls = list(writes), list(judges), list(pres), []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        system = messages[0]["content"]
        self.calls.append((system, json.loads(messages[1]["content"]) if len(messages) > 1 else None))
        if system == scope.WRITER:
            got = self.writes.pop(0) if self.writes else {"ask": "write me a poem", "about": "a poem"}
        elif system == scope.JUDGE:
            got = self.judges.pop(0) if self.judges else verdict()
        elif system == scope.PRE:  # the judge on the card and the ask alone, before the match
            got = self.pres.pop(0) if self.pres else {"on_topic": False, "why": "outside its work"}
        else:
            got = None
        if isinstance(got, Exception):  # a model that does not answer
            raise got
        if got is None:
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


@contextlib.contextmanager
def keyed(model):
    """A model key is set: kit.env.load reads no .env, has_key is true and every kit.model.Model() made is model."""
    with mock.patch("kit.env.load", return_value=[]), mock.patch("kit.model.has_key", return_value=True), \
            mock.patch("kit.model.Model", return_value=model):
        yield model


class Notes:
    """The run's quick notes (arena/notes.py RunNotes) as Arena reads them: a note after each lost training match."""

    def __init__(self):
        self.lost = []

    def after_loss(self, m, judged, mid):
        self.lost.append(mid)
        return {"match": mid}

    def clear(self, r):
        return []


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


class RedTeamLows(unittest.TestCase):
    """Red team scopeguard2 r1 item 5."""

    def test_direction_marks_are_taken_out_of_card_lines(self):
        from kit import turn
        text = json.dumps({"name": "Tutor", "does": "tutors \u202escience\u202c \u2066now\u2069",
                           "good": "the student \u200funderstands", "never": [], "needs": [],
                           "case": {"input": "a \u200equestion", "starts": "person", "output": "an answer",
                                    "ends": "when done"}})
        card = turn.read_card(text)
        self.assertEqual((card["does"], card["good"], card["case"]["input"]),
                         ("tutors science now", "the student understands", "a question"))

    def test_every_format_mark_but_the_two_joiners_is_taken_out_of_card_lines(self):
        """Red team scopeguard2 r2 item 7: zero width spaces, word joiners and tag characters go too; the zero
        width non joiner and joiner stay, since Arabic and emoji need them."""
        from kit import turn
        text = json.dumps({"name": "Tutor", "does": "tutors sci\u200bence\u2060 \U000e0049\U000e0047now\ufeff",
                           "good": "the family \U0001f468\u200d\U0001f469 under\u00adstands م\u200cن",
                           "never": [], "needs": [],
                           "case": {"input": "a \u180equestion", "starts": "person", "output": "an answer",
                                    "ends": "when done"}})
        card = turn.read_card(text)
        self.assertEqual((card["does"], card["good"], card["case"]["input"]),
                         ("tutors science now", "the family \U0001f468\u200d\U0001f469 understands م\u200cن",
                          "a question"))

    def test_combining_marks_outside_tashkeel_count_as_spaces(self):
        """Red team scopeguard2 r2 item 6: a combining grapheme joiner never joins words into one; tashkeel never
        splits one."""
        joined = "\u034f".join(["wave"] * 300)
        self.assertEqual(exam.words(joined), 300)
        got = scope.judge(match([joined + " Need a science question?"]), TUTOR, Model(judges=[verdict()]))
        self.assertEqual(got["why"], scope.LONG)
        self.assertEqual(exam.words("ب\u0650س\u0652م\u0650 الل\u0651\u064eه\u0650"), 2)
        self.assertEqual(exam.words("\uff57\uff41\uff56\uff45 wave"), 2)

    def test_an_answer_that_is_not_text_is_unreadable_never_attribute_error(self):
        class Parts:
            def chat(self, messages, **kw):
                return {"content": [{"type": "text", "text": '{"ask": "x", "about": "y"}'}]}
        with self.assertRaises(scope.Unreadable):
            scope.write(GROCER, Parts(), "s")
        with self.assertRaises(ModelError):
            scope.judge(match(), GROCER, Parts())

    def test_an_ask_that_would_end_the_match_is_not_read(self):
        from arena.match import LEAVE
        m = Model(writes=[{"ask": "[leave]", "about": "x"}, {"ask": "Tell me a joke", "about": "a joke"}])
        self.assertEqual(scope.write(GROCER, m, "s")["ask"], "Tell me a joke")
        with self.assertRaises(scope.Unreadable):
            scope.write(GROCER, Model(writes=[{"ask": "ok [DONE]", "about": "x"}, {"ask": "[Leave]", "about": "x"}]),
                        "s")
        self.assertTrue(scope.MARKS.search(LEAVE) and scope.MARKS.search(practice.DONE))


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
        self.assertIn("long", exam.check_scope_reply(sit, {"reply": joined + " boots?"}))  # style (decision 75)
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
        self.kws = []

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
            self.kws.append(kw)
            return fake_match(card, **kw)
        with mock.patch.object(run.match_mod, "play", side_effect=play):
            return a.run()

    def saved_off(self):
        path = self.dir / run.MATCHES_FILE
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        return [m for m in map(json.loads, lines) if m["card"].startswith(scope.PREFIX)]

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
        self.assertEqual(rep["calls"]["used"], 3)  # the writer's, the precheck's and the judge's calls count on the cap
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

    def test_a_judge_that_does_not_answer_is_noted_and_the_run_goes_on(self):
        """Red team scopeguard2 r1 item 3: as a writer that does not answer is."""
        rep = self.go(self.arena(Model(), Model(judges=[ModelError("the model did not answer")])))
        one = rep["rounds"][0]
        self.assertEqual(one["training"]["off_topic"]["result"], run.JUDGE_FAILED)
        self.assertIn("did not answer", one["training"]["off_topic"]["error"])
        self.assertNotEqual(rep["stopped"], run.MODEL_ERROR)
        self.assertEqual((one["training"]["played"], one["gate"]["played"]), (9, 3))

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
        judge = Model()
        rep = self.go(self.arena(Model(), judge, cap=1, matches=10))
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual((judge.asked(scope.PRE), judge.asked(scope.JUDGE)), ([], []))  # the precheck's call is refused

    def test_the_cap_refuses_the_judges_call(self):
        """Review scopeguard2 r1 item 10: the writer and the precheck took the day's last calls, so the judge's
        call is refused: the run stops at the cap, the match is neither saved nor a case and the gate never plays."""
        judge = Model()
        a = self.arena(Model(), judge, cap=2)
        rep = self.go(a)
        training = rep["rounds"][0]["training"]
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual((len(judge.asked(scope.PRE)), judge.asked(scope.JUDGE)), (1, []))
        self.assertTrue(self.opened[9][0].startswith(scope.PREFIX))  # it was played, then the judge was refused
        self.assertEqual((self.saved_off(), training["played"], rep["rounds"][0]["gate"]["played"]), ([], 9, 0))
        self.assertNotIn("off_topic", training)
        self.assertNotIn(f"{a.run_id}-r1-t10", self.cases)
        self.assertEqual(rep["calls"]["used"], 2)

    def test_the_cap_refuses_the_judges_second_try(self):
        judge = Model(judges=["not json"])
        a = self.arena(Model(), judge, cap=3)
        rep = self.go(a)
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual(len(judge.asked(scope.JUDGE)), 1)
        self.assertEqual((self.saved_off(), rep["rounds"][0]["training"]["played"]), ([], 9))
        self.assertNotIn(f"{a.run_id}-r1-t10", self.cases)

    def test_a_cap_reached_while_the_precheck_or_the_judge_answers_stops_it(self):
        """The count is shared: another part of the run on the same cap may reach it while the precheck or the
        judge answers. The check after each call stops the run there: nothing after it plays or is saved."""
        for system in (scope.PRE, scope.JUDGE):
            with self.subTest(system=system[:30]):
                self.cases, self.opened, self.kws = [], [], []
                judge = Model()
                a = self.arena(Model(), judge)
                inner = judge.chat

                def chat(messages, _inner=inner, _a=a, _system=system, **kw):
                    out = _inner(messages, **kw)
                    if messages[0]["content"] == _system:
                        _a.calls.reached = True
                    return out
                judge.chat = chat
                rep = self.go(a)
                training = rep["rounds"][0]["training"]
                self.assertEqual(rep["stopped"], run.CAP)
                self.assertEqual((self.saved_off(), training["played"]), ([], 9))
                self.assertNotIn("off_topic", training)
                self.assertNotIn(f"{a.run_id}-r1-t10", self.cases)
                self.assertEqual(rep["rounds"][0]["gate"]["played"], 0)
                if system == scope.PRE:
                    self.assertEqual(judge.asked(scope.JUDGE), [])
                    self.assertFalse(any(c.startswith(scope.PREFIX) for c, _ in self.opened))  # never played

    def test_the_off_topic_match_is_a_training_match_with_the_quick_notes(self):
        """It is played as a training match (training=True): the run's quick notes are handed to it, as to the
        other practice matches, never to the gate; its loss writes no quick note (an ask outside the work is no
        sale for the next matches to learn from), only a case."""
        notes = Notes()
        a = self.arena(Model(), Model(judges=[verdict(answered=True, declined=False)]))
        a.notes = notes
        rep = self.go(a)
        self.assertTrue(self.opened[9][0].startswith(scope.PREFIX))
        self.assertIs(self.kws[9].get("fast"), notes)
        self.assertTrue(all(kw.get("fast") is notes for kw in self.kws[:10]))
        self.assertFalse(any("fast" in kw for kw in self.kws[10:]))  # the gate plays without them
        self.assertNotIn(f"{a.run_id}-r1-t10", notes.lost)
        self.assertNotIn({"match": f"{a.run_id}-r1-t10"}, rep["rounds"][0]["training"].get("notes", []))
        self.assertIn(f"{a.run_id}-r1-t10", self.cases)

    def test_an_unreadable_judge_is_asked_once_more_and_its_verdict_counts(self):
        judge = Model(judges=["not json", verdict(answered=True, declined=False)])
        a = self.arena(Model(), judge)
        rep = self.go(a)
        training = rep["rounds"][0]["training"]
        self.assertEqual(len(judge.asked(scope.JUDGE)), 2)
        self.assertEqual((training["off_topic"]["result"], training.get("unjudged", 0)), ("lost", 0))
        self.assertIn(f"{a.run_id}-r1-t10", self.cases)
        self.assertEqual(rep["calls"]["used"], 4)  # the writer, the precheck and the judge twice

    def test_a_short_round_plays_none(self):
        writer = Model()
        self.go(self.arena(writer, Model(), matches=9))
        self.assertEqual(writer.asked(scope.WRITER), [])

    def test_a_longer_round_plays_only_match_10(self):
        writer = Model()
        self.go(self.arena(writer, Model(), matches=30))
        ids = [c for c, _ in self.opened]
        self.assertEqual(len(writer.asked(scope.WRITER)), 1)
        self.assertEqual([i for i, c in enumerate(ids) if c.startswith(scope.PREFIX)], [9])
        self.assertEqual([k for k in range(1, 41) if scope.slot(k)], [10])

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

    def practice(self, card, writer, judge, off_topic=True, cap=1000):
        agent = types.SimpleNamespace(name="tutor", card=card, plug=None, data=None, missing=[], tools=[],
                                      stage=types.SimpleNamespace(name="any"))
        cards = [{"id": f"made-up-{i:02d}", "kind": "easy", "want": ["x"], "buy_trigger": ["y"], "made_up": True}
                 for i in range(1, 15)]
        held = [c["id"] for c in cards[:4]]
        return practice.Practice(agent, cards, judge_model=judge, made_up=True, held_out=held, once=True,
                                 agent_model=Model(), customer_model=writer,
                                 calls=run.Calls(self.dir / run.CALLS_FILE, cap),
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

    def test_a_judge_that_does_not_answer_is_noted_and_the_run_goes_on(self):
        p = self.practice(GROCER, Model(), Model(judges=[ModelError("the model did not answer")]))
        rep, opened = self.go(p)
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], run.JUDGE_FAILED)
        self.assertNotEqual(rep["stopped"], run.MODEL_ERROR)
        self.assertEqual(len(opened), 10 + 4)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 4)

    def test_off_by_default_so_no_key_never_fakes_one(self):
        writer = Model()
        _, opened = self.go(self.practice(TUTOR, writer, Model(), off_topic=False))
        self.assertEqual(writer.asked(scope.WRITER), [])
        self.assertEqual(len(opened), 10 + 4)

    def test_the_cap_refuses_the_judges_call(self):
        """Review scopeguard2 r1 item 10, for a built agent: nine practice verdicts, the writer and the precheck
        take the cap, so the off topic judge's call is refused and the run stops there."""
        judge = Model()
        p = self.practice(GROCER, Model(), judge, cap=11)
        rep, opened = self.go(p)
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual((len(judge.asked(scope.PRE)), judge.asked(scope.JUDGE)), (1, []))
        self.assertTrue(opened[9][0].startswith(scope.PREFIX))
        self.assertEqual(len(opened), 10)  # the gate never plays
        self.assertNotIn("off_topic", rep["rounds"][0]["training"])

    def test_an_unreadable_judge_is_asked_once_more_and_its_verdict_counts(self):
        judge = Model(judges=["not json", verdict(answered=True, declined=False)])
        rep, _ = self.go(self.practice(GROCER, Model(), judge))
        self.assertEqual(len(judge.asked(scope.JUDGE)), 2)
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "lost")


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


class Both(World):
    """tests/test_arena_practice.py World for the practice run, with the off topic writer, precheck and judge
    answered by an off topic Model."""

    def __init__(self, off):
        super().__init__()
        self.off = off

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if messages[0]["content"] in (scope.WRITER, scope.PRE, scope.JUDGE):
            return self.off.chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)
        return super().chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)


class KeyedRuns(unittest.TestCase):
    """A run that makes its own models once a key is set plays the off topic customer; a quick practice never
    does (review scopeguard2 r1 item 10, behaviour in place of reading the source)."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()

    def test_the_sales_run_with_a_key_plays_it(self):
        off = Model(writes=[{"ask": "Write me a poem about the sea", "about": "a poem"}])
        out = io.StringIO()
        with keyed(off), mock.patch.object(run.match_mod, "play", side_effect=fake_match), \
                contextlib.redirect_stdout(out):
            run.main(["--matches", "10", "--rounds", "1", "--state", str(self.dir), "--json", "--cards",
                      str(run.DEMO_CARDS)])
        rep = json.loads(out.getvalue())
        self.assertEqual([len(off.asked(s)) for s in (scope.WRITER, scope.PRE, scope.JUDGE)], [1, 1, 1])
        self.assertEqual(rep["rounds"][0]["training"]["off_topic"]["result"], "won")
        self.assertEqual(rep["calls"]["used"], 3)

    def practise(self, *argv):
        folder = self.dir / "agents" / "stock_watch"
        if not folder.exists():
            shutil.copytree(FIXTURE, folder)
        off = Model(writes=[{"ask": "Write me a poem about the sea", "about": "a poem"}])
        world = Both(off)
        out, err = io.StringIO(), io.StringIO()
        with keyed(world), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(practice, "Practice", wraps=practice.Practice) as made:
            practice.main(["--agent", str(folder), "--json", *argv])
        self.assertTrue(out.getvalue(), err.getvalue())
        self.made = made.call_args.kwargs
        return json.loads(out.getvalue()), off, world

    def test_a_practice_with_a_key_plays_it(self):
        rep, off, _ = self.practise("--matches", "10", "--rounds", "1")
        self.assertIs(self.made["off_topic"], True)
        self.assertEqual([len(off.asked(s)) for s in (scope.WRITER, scope.PRE, scope.JUDGE)], [1, 1, 1])
        self.assertIn(rep["rounds"][0]["training"]["off_topic"]["result"], ("won", "lost"))

    def test_a_quick_practice_never_plays_it(self):
        rep, off, world = self.practise("--quick")
        self.assertIs(self.made["off_topic"], False)  # a quick run of one match is never handed it at all
        self.assertEqual(off.calls, [])
        self.assertGreater(world.calls["agent"], 0)  # the quick run played
        self.assertNotIn("off_topic", rep["rounds"][0]["training"])


class MorningRunsIt(Page):
    """Run the Arena on an agent's page sets off_topic only with the models it made after the key check."""

    def started(self, models):
        seen = {}
        self.m.arena_models = models
        with keyed(Model()), mock.patch("arena.practice.practise", side_effect=lambda folder, **kw: seen.update(kw)), \
                mock.patch("arena.run.reflection_models", return_value={}):
            self.m.run_arena("stock_watch")
            self.starts[0][0]()
        self.assertEqual(self.m._arena_note.get("stock_watch"), None)
        return seen

    def test_models_it_made_play_it(self):
        seen = self.started(None)
        self.assertIs(seen["off_topic"], True)
        self.assertIsInstance(seen["judge_model"], Model)

    def test_models_a_test_hands_never_do(self):
        self.assertIs(self.started(lambda: (Model(), Model(), Model()))["off_topic"], False)


if __name__ == "__main__":
    unittest.main()
