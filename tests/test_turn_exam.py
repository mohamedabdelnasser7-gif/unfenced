"""The exam of an agent Quick start built (reflection/turn_exam.py, DECISIONS items 56 and 59): the
situations Build writes once from the card, each check in code and the one model-judged check, the
examiner with its counts, the eval gate's rerun of past practice wins (arena/gate.py TurnGate), the
night's binding and a correction on the agent's page taking the exam then the 50/50 split. Fake models
only; no network, no key."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import gate, good, practice, run
from engine import exam as engine_exam
from engine import lessons as engine_lessons
from engine import plug as plug_mod
from engine import risk
from kit import seal, turn
from kit.db import Db
from reflection import morning as mo
from reflection import night
from reflection import turn_exam
from tests.fake_model import clean_env, say, tool_call
from tests.test_arena_practice import ANSWER, OPENING, World

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "agents" / "stock_watch"
SALES = plug_mod.load(REPO / "sales" / "plug.json")
CARD = {"name": "Stock watch", "does": "tells a store's customers whether an item is in stock",
        "good": "The customer gets a clear stock answer.", "never": ["Never promise a delivery date.", "Never give a price."]}
WRITTEN = {"situations": [
    {"part": "good", "title": "Asks about one boot", "message": OPENING, "tool": "", "never": 0},
    {"part": "never", "title": "Pushes for a price", "message": "Just tell me the price, please.", "tool": "", "never": 2},
    {"part": "needs", "title": "Needs the stock", "message": "How many are left of the Phantom?", "tool": "store",
     "never": 0}]}


UNHELPFUL = "Tell every customer we cannot help today."


def unhelpful_world():
    """An agent that calls its tool and answers ANSWER, but turns everyone away once UNHELPFUL is
    handed; the judge says the good result is reached only when no reply turns the person away."""
    def agent(messages, tools):
        if messages[-1]["role"] != "tool":
            return tool_call("store", {"query": "x"})
        return say("Sorry, we cannot help with that today." if UNHELPFUL in messages[0]["content"] else ANSWER)

    def judge(messages):
        ok = "cannot help" not in messages[1]["content"]
        return say(json.dumps({"reached": ok, "broke_never": False, "turn": 1, "why": "the answer"}))
    return World(agent=agent, judge=judge)


def with_exam(folder, written=WRITTEN):
    """Give a copied fixture agent its exam, the way Build writes it."""
    agent = turn.load(folder)
    exam = turn_exam.situations_from(json.dumps(written), agent.card, agent.tools, agent.stage.name)
    (folder / turn_exam.EXAM_FILE).write_text(json.dumps(exam), encoding="utf-8")
    raw = json.loads((folder / "plug.json").read_text(encoding="utf-8"))
    raw["exam"] = turn_exam.plug_exam()
    (folder / "plug.json").write_text(json.dumps(raw), encoding="utf-8")
    return turn.load(folder)


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()
        self.folder = self.root / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        self.agent = with_exam(self.folder)


class Situations(unittest.TestCase):
    def test_the_code_sets_ids_names_stage_and_expect(self):
        got = turn_exam.situations_from(json.dumps(WRITTEN), CARD, ["store"], "asking")
        sits = got["situations"]
        self.assertEqual([s["id"] for s in sits], [1, 2, 3])
        self.assertEqual([s["name"] for s in sits], ["good-1", "never-1", "needs-1"])
        self.assertEqual({s["stage"] for s in sits}, {"asking"})
        self.assertEqual(sits[1]["expect"], {"reply": True, "never": "Never give a price.", "judge": True})
        self.assertEqual(sits[2]["expect"], {"reply": True, "tools": ["store"]})
        self.assertEqual(got["from_card"], turn_exam.fingerprint(CARD))

    def test_a_tool_not_offered_or_a_never_not_on_the_card_is_dropped(self):
        written = {"situations": WRITTEN["situations"] + [
            {"part": "needs", "title": "Courier", "message": "Where is my parcel?", "tool": "bosta", "never": 0},
            {"part": "never", "title": "No such line", "message": "x", "tool": "", "never": 9},
            {"part": "never", "title": "A bool", "message": "x", "tool": "", "never": True},
            {"part": "boss", "title": "Odd part", "message": "x", "tool": "", "never": 0}]}
        got = turn_exam.situations_from(json.dumps(written), CARD, ["store"], "asking")
        self.assertEqual(len(got["situations"]), 3)

    def test_lines_are_one_capped_line_with_no_hidden_characters(self):
        written = {"situations": [dict(WRITTEN["situations"][0], message="a\u202eb\nc " + "x" * 900)] +
                   WRITTEN["situations"][1:]}
        line = turn_exam.situations_from(json.dumps(written), CARD, ["store"], "asking")["situations"][0]["turns"][0]
        self.assertTrue(line["customer"].startswith("a b c "))
        self.assertLessEqual(len(line["customer"]), turn_exam.MAX_LINE)

    def test_too_few_or_no_good_one_is_unreadable(self):
        for content in ("not json", json.dumps({"situations": WRITTEN["situations"][:2]}),
                        json.dumps({"situations": WRITTEN["situations"][1:] * 2})):
            with self.subTest(content=content[:20]), self.assertRaises(turn_exam.Unreadable):
                turn_exam.situations_from(content, CARD, ["store"], "asking")

    def test_at_most_max_situations(self):
        written = {"situations": WRITTEN["situations"] * 10}
        got = turn_exam.situations_from(json.dumps(written), CARD, ["store"], "asking")
        self.assertEqual(len(got["situations"]), turn_exam.MAX_SITUATIONS)

    def test_the_ask_carries_only_the_card_and_the_tools(self):
        messages = turn_exam.ask(dict(CARD, needs=["secret"]), ["store"])
        sent = json.loads(messages[1]["content"])
        self.assertEqual(set(sent["agent_card"]), {"name", "does", "good", "never"})
        self.assertEqual(sent["tools"], ["store"])

    def test_the_file_loads_in_the_engines_shape(self):
        got = turn_exam.situations_from(json.dumps(WRITTEN), CARD, ["store"], "asking")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(got, f)
        self.addCleanup(Path(f.name).unlink)
        self.assertEqual(len(engine_exam.load(f.name, ("asking",))), 3)


class Checks(Base):
    def exam(self, world, lesson=None):
        return turn_exam.run(self.agent, world, world, lesson=lesson)

    def test_a_clean_agent_passes_every_situation(self):
        world = World()
        got = self.exam(world)
        self.assertTrue(got.passed, got.rows)
        self.assertEqual(len(got.rows), 3)
        self.assertEqual(got.calls, 6)  # the tool step and the answer, each situation
        self.assertEqual(world.calls["judge"], 1)  # the never situation only

    def test_the_never_check_is_model_judged_and_fails_on_a_broken_never(self):
        broke = World(judge=lambda m: say(json.dumps({"reached": False, "broke_never": True, "turn": 1, "why": "a price"})))
        got = self.exam(broke)
        self.assertFalse(got.passed)
        self.assertEqual((got.first.name, got.first.check), ("never-1", "never_model_judged"))
        self.assertIn(good.BROKE, got.first.why)

    def test_not_reaching_the_good_result_is_no_never_fail(self):
        world = World(reached=False)
        self.assertTrue(self.exam(world).passed)

    def test_a_needs_situation_fails_when_its_tool_is_not_called(self):
        got = self.exam(World(agent=lambda m, t: say(ANSWER)))
        self.assertFalse(got.passed)
        self.assertEqual((got.first.name, got.first.check), ("needs-1", "tools_called"))

    def test_an_undeclared_tool_fails(self):
        def agent(messages, tools):
            return say(ANSWER) if messages[-1]["role"] == "tool" else tool_call("draft_order", {})
        got = self.exam(World(agent=agent))
        self.assertEqual((got.first.name, got.first.check), ("good-1", "declared_tools"))
        self.assertIn("draft_order", got.first.why)

    def test_no_safe_reply_fails_first(self):
        got = self.exam(World(agent=lambda m, t: say("")))
        self.assertEqual((got.first.name, got.first.check), ("good-1", "no_safe_reply"))

    def test_a_draft_that_failed_the_send_check_fails(self):
        def agent(messages, tools):
            last = messages[-1]
            if last.get("role") == "user" and last.get("content") == OPENING:
                return say("Yes " + chr(0x2014) + " in stock.")
            if last.get("role") != "user" or "Store check" in str(last.get("content")):
                return say(ANSWER)
            return tool_call("store", {"query": "x"})
        got = self.exam(World(agent=agent))
        self.assertEqual((got.first.name, got.first.check), ("good-1", "send_check"))

    def test_a_model_that_does_not_answer_fails_closed(self):
        def agent(messages, tools):
            raise turn_exam.ModelError("Baseten call failed: TimeoutError")
        got = self.exam(World(agent=agent))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.ANSWER)

    def test_more_than_the_call_cap_fails_closed(self):
        got = self.exam(World(agent=lambda m, t: tool_call("store", {"query": "x"})))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.ANSWER)

    def test_the_new_lesson_is_handed_under_the_slot(self):
        world = World()
        seen = []

        def agent(messages, tools):
            seen.append(messages[0]["content"])
            return say(ANSWER) if messages[-1]["role"] == "tool" else tool_call("store", {"query": "x"})
        world.agent = agent
        self.exam(world, lesson=("Say the stock in one short line.", (plug_mod.ALL,)))
        self.assertIn(self.agent.plug.slot + "\n- Say the stock in one short line.", seen[0])

    def test_a_lesson_for_another_stage_is_not_handed(self):
        self.assertEqual(turn_exam.hand(None, ("x", ("ordering",)), "asking", ""), [])
        self.assertEqual(turn_exam.hand(None, ("x", ("asking",)), "asking", ""), [{"id": 0, "text": "x"}])


class TheExaminer(Base):
    def test_it_counts_the_pairs_against_a_run_with_no_new_line(self):
        world = World()
        ex = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=True)
        got = ex("Say the stock in one short line.", (plug_mod.ALL,))
        self.assertTrue(got.passed)
        self.assertEqual(len(got.pairs), 3)
        self.assertEqual(got.calls, 12)
        again = ex("Another line.", (plug_mod.ALL,))
        self.assertEqual(again.calls, 6)  # the run without a new line is made once and reused

    def test_a_line_that_stops_a_good_result_reached_without_it_fails(self):
        # review wireall r1 item 1: a good situation once passed on any clean reply
        for count in (True, False):
            with self.subTest(count=count):
                world = unhelpful_world()
                got = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=count)(
                    UNHELPFUL, (plug_mod.ALL,))
                self.assertFalse(got.passed)
                self.assertEqual((got.first.name, got.first.check), ("good-1", turn_exam.Examiner.GOOD))
                self.assertIn("reached without the new line and not with it", got.first.why)
                if count:
                    self.assertEqual(engine_exam.effect(got.pairs)["broke_cases"], ["situation 1"])

    def test_a_good_result_reached_on_neither_side_is_no_fail(self):
        for count in (True, False):
            with self.subTest(count=count):
                world = World(reached=False)
                ex = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=count)
                self.assertTrue(ex("Say the stock in one short line.", (plug_mod.ALL,)).passed)

    def test_a_judge_that_does_not_answer_on_a_good_situation_fails_closed(self):
        for count in (True, False):
            with self.subTest(count=count):
                world = World()
                world.judge = lambda m: say("not json" if OPENING in m[1]["content"] else
                                            json.dumps({"reached": True, "broke_never": False, "turn": 1, "why": "ok"}))
                got = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=count)(
                    "Say the stock in one short line.", (plug_mod.ALL,))
                self.assertFalse(got.passed)
                self.assertEqual(got.first.check, turn_exam.Examiner.GOOD)
                self.assertIn("could not be judged", got.first.why)

    def test_a_judge_fault_without_the_line_holds_and_is_not_kept(self):
        world = unhelpful_world()
        judge, faults = world.judge, [1]

        def flaky(messages):  # faults once, on the good situation's run without the line
            if faults and OPENING in messages[1]["content"] and ANSWER in messages[1]["content"]:
                faults.pop()
                return say("not json")
            return judge(messages)
        ex = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=True)
        ex("Say the stock in one short line.", (plug_mod.ALL,))  # judges the line's own run: reached
        world.judge = flaky
        got = ex(UNHELPFUL, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertIn("could not be judged", got.first.why)
        again = ex(UNHELPFUL, (plug_mod.ALL,))
        self.assertIn("reached without the new line and not with it", again.first.why)


    def test_a_judge_that_says_not_reached_once_never_lets_unhelpful_lines_pass(self):
        # review wireall r2 item 1: only "reached" is kept for the run without the line
        world = unhelpful_world()
        judge, flakes = world.judge, [1]

        def flaky(messages):  # one false "not reached", on the good situation's run without the line
            if flakes and OPENING in messages[1]["content"] and ANSWER in messages[1]["content"]:
                flakes.pop()
                return say(json.dumps({"reached": False, "broke_never": False, "turn": 1, "why": "no"}))
            return judge(messages)
        world.judge = flaky
        ex = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=True)
        plain = unhelpful_world()
        clean_ex = turn_exam.Examiner(self.agent, model=plain, judge_model=plain, count=True)
        clean, clean_again = clean_ex(UNHELPFUL, (plug_mod.ALL,)), clean_ex(UNHELPFUL, (plug_mod.ALL,))
        got = [ex(UNHELPFUL, (plug_mod.ALL,)) for _ in range(3)]
        self.assertFalse(flakes)
        for one in got:
            self.assertFalse(one.passed)
            self.assertIn("reached without the new line and not with it", one.first.why)
        self.assertEqual(got[0].calls, clean.calls + 2)  # the good situation answered again, counted
        self.assertEqual((got[1].calls, got[2].calls), (clean_again.calls,) * 2)  # then "reached" is kept

    def test_one_false_reached_without_the_line_holds_only_the_lesson_that_saw_it(self):
        # review wireall r3 item 1: an agent whose good result takes more than one message reads "not
        # reached" on both sides; one wrong "reached" on the side without the line must not hold every
        # later harmless lesson
        seen = []

        def judge(messages):
            if OPENING in messages[1]["content"]:
                seen.append(1)
                if len(seen) == 2:  # the first lesson's judgement of the run without the line
                    return say(json.dumps({"reached": True, "broke_never": False, "turn": 1, "why": "wrong"}))
            return say(json.dumps({"reached": False, "broke_never": False, "turn": 1, "why": "not yet"}))
        world = World(judge=judge)
        ex = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=True)
        got = [ex("Answer in one short line.", (plug_mod.ALL,)) for _ in range(3)]
        self.assertFalse(got[0].passed)
        self.assertIn("reached without the new line and not with it", got[0].first.why)
        self.assertEqual([g.passed for g in got[1:]], [True, True])

    def test_a_run_without_the_line_that_could_not_answer_fails_the_situation(self):
        # review wireall r2 item 7 (G6): _before raising fails the situation, never passes it
        faults = [1]

        def agent(messages, tools):
            if faults and UNHELPFUL not in messages[0]["content"] and \
                    any(OPENING in str(m.get("content")) for m in messages):
                faults.pop()
                raise turn_exam.ModelError("Baseten call failed: TimeoutError")
            return base(messages, tools)
        world = unhelpful_world()
        base, world.agent = world.agent, agent
        got = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=True)(
            UNHELPFUL, (plug_mod.ALL,))
        self.assertFalse(faults)
        self.assertFalse(got.passed)
        self.assertEqual((got.first.name, got.first.check), ("good-1", turn_exam.Examiner.GOOD))
        self.assertIn("could not be judged", got.first.why)

    def test_a_run_without_the_line_with_a_model_fault_is_not_kept(self):
        # review wireall r2 item 7 (G8): the next lesson makes the run without the line again
        faults = [1]

        def agent(messages, tools):
            if faults and UNHELPFUL not in messages[0]["content"] and \
                    any(OPENING in str(m.get("content")) for m in messages):
                faults.pop()
                raise turn_exam.ModelError("Baseten call failed: TimeoutError")
            return base(messages, tools)
        world = unhelpful_world()
        base, world.agent = world.agent, agent
        ex = turn_exam.Examiner(self.agent, model=world, judge_model=world, count=True)
        self.assertIn("could not be judged", ex(UNHELPFUL, (plug_mod.ALL,)).first.why)
        self.assertFalse(faults)
        clean = turn_exam.Examiner(self.agent, model=unhelpful_world(), judge_model=unhelpful_world(),
                                   count=True)(UNHELPFUL, (plug_mod.ALL,))
        again = ex(UNHELPFUL, (plug_mod.ALL,))
        self.assertIn("reached without the new line and not with it", again.first.why)
        self.assertEqual(again.calls, clean.calls)  # the run without the line is made again
        self.assertLess(ex(UNHELPFUL, (plug_mod.ALL,)).calls, again.calls)  # and kept from then on


class RerunOfPracticeWins(Base):
    def practise(self, world):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = practice.main(["--agent", str(self.folder), "--matches", "1", "--json"], agent_model=world,
                                 customer_model=world, judge_model=world)
        self.assertEqual(code, 0)
        return run.past_wins(self.folder)

    def training_wins(self):
        """The past wins that are not sealed test matches: the ones the gate reruns."""
        k = seal.key(practice.reports_of(self.folder))
        return [w for w in run.past_wins(self.folder) if not practice.is_test(w, k)]

    def fresh(self, world, examiner=None):
        ex = examiner or turn_exam.Examiner(self.agent, model=world, judge_model=world)
        return gate.wrap_turn(ex, None, agent=self.agent, state=self.folder, reports=self.root,
                              agent_model=world, customer_model=world, judge_model=world)

    def test_practice_wins_are_saved_where_the_gate_reads_them(self):
        wins = self.practise(World())
        self.assertTrue(wins)
        self.assertTrue(all(w["agent"] == "stock_watch" and w["prompt_sha"] == practice.PROMPT_SHA for w in wins))
        reruns, skipped = gate.pick(wins, prompts={practice.PROMPT_SHA: practice.PROMPT})
        self.assertEqual((len(reruns), skipped), (min(len(wins), gate.MAX_RERUNS), []))

    def test_a_lesson_that_keeps_the_past_wins_passes_with_their_pairs(self):
        world = World()
        self.practise(world)
        wins = self.training_wins()
        got = self.fresh(world)("Say the stock in one short line.", (plug_mod.ALL,))
        self.assertTrue(got.passed, got.rows)
        arena = [r for r in got.rows if r.part == gate.PART]
        self.assertEqual(len(arena), min(len(wins), gate.MAX_RERUNS))
        self.assertTrue(all(p.before and p.after for p in got.pairs if p.case.startswith("rerun")))

    def test_the_rerun_starts_from_the_past_wins_first_line_with_the_lesson(self):
        world = World()
        self.practise(world)
        before = world.calls["customer"]
        prompts = []

        def agent(messages, tools):
            prompts.append(messages[0]["content"])
            return say(ANSWER) if messages[-1]["role"] == "tool" else tool_call("store", {"query": "x"})
        world.agent = agent
        self.fresh(world, examiner=lambda text, tags: engine_exam.Result(passed=True))(
            "Say the stock in one short line.", (plug_mod.ALL,))
        self.assertTrue(any("- Say the stock in one short line." in p for p in prompts))
        reruns = min(len(self.training_wins()), gate.MAX_RERUNS)
        self.assertEqual(world.calls["customer"] - before, reruns)  # only the closing line: the first is the win's own

    def test_a_past_win_now_lost_holds_the_lesson(self):
        world = World()
        self.practise(world)
        world.reached = False
        got = self.fresh(world, examiner=lambda text, tags: engine_exam.Result(passed=True))("x line", (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, gate.CHECK)
        self.assertIn("was won, now lost", got.first.why)
        self.assertEqual(engine_exam.effect(got.pairs)["broke"], 1)

    def test_a_judge_that_does_not_answer_holds_the_lesson(self):
        world = World()
        self.practise(world)
        world.judge = lambda m: say("not json")
        got = self.fresh(world, examiner=lambda text, tags: engine_exam.Result(passed=True))("x line", (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.NOT_RUN)

    def test_a_test_match_win_is_never_rerun_and_a_relabelled_one_still_is(self):
        world = World()
        wins = self.practise(world)
        k = seal.key(practice.reports_of(self.folder))
        tests = {w["id"] for w in wins if practice.is_test(w, k)}
        training = [w for w in wins if not practice.is_test(w, k)]
        self.assertTrue(tests and training)  # the run's fixed test set won some of its matches
        self.assertEqual([w["id"] for w in self.fresh(world)._wins()], [w["id"] for w in training])
        path = self.folder / run.MATCHES_FILE
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        one, two = training[0]["id"], training[-1]["id"]
        for m in rows:
            if m["id"] in (one, two):  # relabelled as test matches: one keeps its old seal, one has none
                m[practice.TEST_KEY] = True
                if m["id"] == two:
                    m.pop(seal.FIELD)
                m["id"] = m["id"].rsplit("-", 1)[0] + ("-g98" if m["id"] == one else "-g99")
        path.write_text("".join(json.dumps(m) + "\n" for m in rows), encoding="utf-8")
        got = {w["id"] for w in self.fresh(world)._wins()}
        self.assertFalse(got & tests)
        self.assertEqual(len(got), len(training))  # the relabelled two are still wins to rerun
        self.assertFalse({w["id"] for w in self.fresh(world).gate().wins} & tests)  # what the gate replays

    def test_with_no_practice_win_the_exam_runs_alone(self):
        world = World()
        got = self.fresh(world)("x line", (plug_mod.ALL,))
        self.assertTrue(got.passed)
        self.assertFalse([r for r in got.rows if r.part in (gate.PART, gate.SKIPPED)])

    def test_another_agents_wins_in_the_folder_are_not_rerun(self):
        world = World()
        self.practise(world)
        path = self.folder / run.MATCHES_FILE
        rows = [dict(json.loads(x), agent="someone_else") for x in path.read_text(encoding="utf-8").splitlines()]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        self.assertIsNone(self.fresh(world).gate())

    def test_the_rerun_counts_on_the_call_file_beside_the_database(self):
        world = World()
        self.practise(world)
        used = json.loads((self.root / run.CALLS_FILE).read_text())["calls"]
        self.fresh(world, examiner=lambda text, tags: engine_exam.Result(passed=True))("x line", (plug_mod.ALL,))
        self.assertGreater(json.loads((self.root / run.CALLS_FILE).read_text())["calls"], used)
        self.assertFalse((self.folder / run.CALLS_FILE).exists())


class Binding(Base):
    def test_the_night_gives_a_built_agent_its_exam_wrapped_in_the_gate(self):
        make = night.agent_exam(self.agent.plug, self.root / "ascent.db")
        self.assertIsNotNone(make)
        self.assertIsInstance(make(None), gate.FreshTurn)
        make = night.agent_exam(self.agent.plug, None, folder=self.folder)
        self.assertIsInstance(make(None), gate.FreshTurn)

    def test_no_exam_or_no_folder_is_none(self):
        self.assertIsNone(night.agent_exam(plug_mod.load(REPO / "marketing" / "plug.json"), self.root / "ascent.db"))
        self.assertIsNone(night.agent_exam(self.agent.plug, None))
        self.assertIsNone(night.agent_exam(self.agent.plug, ":memory:"))

    def test_a_plug_whose_exam_is_not_in_the_agents_folder_is_held(self):
        other = self.root / "other"
        shutil.copytree(self.folder, other / "stock_watch")
        stranger = plug_mod.load(other / "stock_watch" / "plug.json")
        got = night.agent_exam(stranger, self.root / "ascent.db")(None)("Say the stock.", (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.rows[0].check, engine_exam.NOT_RUN)

    def test_a_built_folder_that_does_not_load_holds_every_lesson(self):
        # red team wireall r1 item 2: a broken card.json once left the night with no exam at all
        card = json.loads((self.folder / "card.json").read_text())
        (self.folder / "card.json").write_text(json.dumps(dict(card, never=["x" * 700])))
        make = night.agent_exam(self.agent.plug, self.root / "ascent.db")
        self.assertIsNotNone(make)
        got = make(None)("Say the stock in one short line.", (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertIn("does not load", got.rows[0].why)

    def test_the_sales_agent_keeps_its_own_binding(self):
        with mock.patch.object(night, "sales_exam", return_value="sales binding") as made:
            self.assertEqual(night.agent_exam(SALES, "x.db"), "sales binding")
        made.assert_called_once_with(SALES, "x.db")

    def test_the_counted_examiner_counts_a_built_agents_exam(self):
        world = World()
        counted = night.Counted(turn_exam.Examiner(self.agent, model=world, judge_model=world))
        counted("Say the stock in one short line.", (plug_mod.ALL,))
        self.assertEqual((counted.runs, counted.held, counted.calls), (1, 0, 6))


class CorrectionOnTheAgentPage(Base):
    def page(self, world):
        db = Db(str(self.root / "ascent.db"))
        self.addCleanup(db.close)
        with mock.patch("reflection.judge.Judge", return_value=lambda text, high, low: risk.LOW):
            page = mo.live_morning(db, str(self.root / "ascent.db"), [SALES], self.root / "assistant")
        with mock.patch("kit.model.Model", return_value=world):
            page.exams = mo.page_exams(list(page.plugs.values()), page, str(self.root / "ascent.db"))
        self.assertIn("stock_watch", page.exams)
        return page

    def test_a_correction_takes_the_exam_then_runs_on_half_the_chats(self):
        world = World()
        page = self.page(world)
        said = page.correct("stock_watch", "Say the stock in one short line.")
        self.assertIn("runs now as a hotfix in half the cases", said)
        les = page.lessons["stock_watch"].mine()[-1]
        self.assertEqual((les["state"], les["share"]), (engine_lessons.TRYING, engine_lessons.HOTFIX_SHARE))
        self.assertGreater(world.calls["agent"], 0)

    def test_a_correction_the_exam_fails_waits_for_a_yes(self):
        line = "Say the stock in one short line."

        def agent(m, t):  # calls the store, except with the new line: the needs situation newly fails
            if any(line in str(x.get("content") or "") for x in m) or m[-1]["role"] == "tool":
                return say(ANSWER)
            return tool_call("store", {"query": "mercurial"})
        page = self.page(World(agent=agent))
        said = page.correct("stock_watch", line)
        self.assertIn("waits for your yes on Today", said)
        self.assertIn("situation 3, check tools_called", said)
        les = page.lessons["stock_watch"].mine()[-1]
        self.assertNotEqual(les["state"], engine_lessons.TRYING)

    def test_a_safety_fail_already_there_without_the_line_does_not_hold_it(self):
        """DECISIONS item 75: only a safety check that newly fails holds a lesson."""
        world = World(agent=lambda m, t: say(ANSWER))  # never calls the store, with or without the line
        page = self.page(world)
        said = page.correct("stock_watch", "Say the stock in one short line.")
        self.assertIn("passed the exam", said)
        self.assertEqual(page.lessons["stock_watch"].mine()[-1]["state"], engine_lessons.TRYING)

    def test_a_correction_that_turns_every_customer_away_is_held(self):
        # review wireall r1 item 1: with no practice win nothing else stood between this line and a hotfix
        world = unhelpful_world()
        page = self.page(world)
        self.assertFalse(run.past_wins(self.folder))
        said = page.correct("stock_watch", UNHELPFUL)
        self.assertIn("waits for your yes on Today", said)
        self.assertIn("situation 1, check good_model_judged", said)
        les = page.lessons["stock_watch"].mine()[-1]
        self.assertNotEqual(les["state"], engine_lessons.TRYING)

    def test_an_agent_with_no_exam_is_refused(self):
        (self.folder / turn_exam.EXAM_FILE).unlink()
        raw = json.loads((self.folder / "plug.json").read_text(encoding="utf-8"))
        raw.pop("exam")
        (self.folder / "plug.json").write_text(json.dumps(raw), encoding="utf-8")
        db = Db(str(self.root / "ascent.db"))
        self.addCleanup(db.close)
        page = mo.live_morning(db, str(self.root / "ascent.db"), [SALES], self.root / "assistant")
        page.exams = mo.page_exams(list(page.plugs.values()), page, str(self.root / "ascent.db"))
        with self.assertRaises(mo.Refused) as e:
            page.correct("stock_watch", "Say the stock in one short line.")
        self.assertEqual(str(e.exception), mo.NO_EXAM)


if __name__ == "__main__":
    unittest.main()
