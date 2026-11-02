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
from kit import turn
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


class RerunOfPracticeWins(Base):
    def practise(self, world):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = practice.main(["--agent", str(self.folder), "--matches", "1", "--json"], agent_model=world,
                                 customer_model=world, judge_model=world)
        self.assertEqual(code, 0)
        return run.past_wins(self.folder)

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
        wins = self.practise(world)
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
        reruns = min(len(run.past_wins(self.folder)), gate.MAX_RERUNS)
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

    def test_a_plug_whose_exam_is_not_in_the_agents_folder_gets_none(self):
        other = self.root / "other"
        shutil.copytree(self.folder, other / "stock_watch")
        stranger = plug_mod.load(other / "stock_watch" / "plug.json")
        self.assertIsNone(night.agent_exam(stranger, self.root / "ascent.db"))

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
        self.assertIn("runs now as a hotfix in half the chats", said)
        les = page.lessons["stock_watch"].mine()[-1]
        self.assertEqual((les["state"], les["share"]), (engine_lessons.TRYING, engine_lessons.HOTFIX_SHARE))
        self.assertGreater(world.calls["agent"], 0)

    def test_a_correction_the_exam_fails_waits_for_a_yes(self):
        world = World(agent=lambda m, t: say(ANSWER))  # never calls the store: the needs situation fails
        page = self.page(world)
        said = page.correct("stock_watch", "Say the stock in one short line.")
        self.assertIn("waits for your yes on Today", said)
        self.assertIn("situation 3, check tools_called", said)
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
