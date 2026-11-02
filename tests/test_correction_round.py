"""A correction's practice round (DECISIONS item 70, arena/gate.py CorrectionRound and
FreshTurn.correction): for a built agent whose good result can take more than one message, a
correction that passed the exam plays one practice round of fresh matches with the correction handed
first, and goes live as a hotfix only when every match is won. An agent whose every win came at the
first turn keeps the exam only hotfix. Fake models only; no network, no key."""
import contextlib
import io
import json
from unittest import mock

from arena import gate, practice, run
from engine import exam as engine_exam
from engine import lessons as engine_lessons
from engine import plug as plug_mod
from engine import study
from kit.model import ModelError
from tests.fake_model import say
from tests.test_arena_practice import THANKS, World
from tests.test_turn_exam import Base, CorrectionOnTheAgentPage

FRESH = "Do you have the Copa in size 44?"  # the line a round's customer opens with, never an exam line
LINE = "Say the stock in one short line."
PASSED = lambda text, tags: engine_exam.Result(passed=True)  # noqa: E731


def round_world(round_won=True):
    """World whose customer opens with FRESH and whose judge says the good result is reached in the
    round only when round_won (the exam's situations never carry FRESH, so they pass)."""
    def customer(messages):
        return say(FRESH if len(messages) == 2 else THANKS)

    def judge(messages):
        ok = round_won or FRESH not in messages[1]["content"]
        return say(json.dumps({"reached": ok, "broke_never": False, "turn": 1, "why": "the answer"}))
    return World(customer=customer, judge=judge)


class Rounds(Base):
    def practise(self, world, turn=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = practice.main(["--agent", str(self.folder), "--matches", "1", "--json"], agent_model=world,
                                 customer_model=world, judge_model=world)
        self.assertEqual(code, 0)
        if turn is not None:  # the wins as if their good result came at this turn
            path = self.folder / run.MATCHES_FILE
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            for r in rows:
                r["quote"] = dict(r["quote"], turn=turn)
            path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        self.assertTrue(run.past_wins(self.folder))

    def fresh(self, world, examiner=PASSED):
        return gate.wrap_turn(examiner, None, agent=self.agent, state=self.folder, reports=self.root,
                              agent_model=world, customer_model=world, judge_model=world)

    def round_rows(self, got):
        return [r for r in got.rows if r.part == gate.ROUND_PART]


class NeedsRound(Rounds):
    def test_every_win_at_the_first_turn_keeps_the_exam_only_hotfix(self):
        self.practise(World())
        world = round_world(round_won=False)  # a round would be lost, so none is played
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertTrue(got.passed, got.rows)
        self.assertEqual(self.round_rows(got), [])

    def test_a_win_after_the_first_turn_plays_the_round(self):
        world = round_world()
        self.practise(world, turn=2)
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertTrue(got.passed, got.rows)
        played = self.round_rows(got)
        self.assertEqual(len(played), gate.ROUND_MATCHES)
        self.assertTrue(all(r.passed and r.check == "" for r in played))

    def test_no_practice_win_yet_plays_the_round(self):
        world = round_world()
        self.assertFalse(run.past_wins(self.folder))
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertEqual(len(self.round_rows(got)), gate.ROUND_MATCHES)

    def test_a_case_that_starts_with_the_agent_plays_the_round(self):
        world = round_world()
        self.practise(world)
        self.agent.card["case"] = {"input": "a new lead in the list", "starts": "agent",
                                   "output": "a follow up message", "ends": "the lead answers or a week passes"}
        self.assertTrue(gate.needs_round(self.agent, run.past_wins(self.folder)))
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertEqual(len(self.round_rows(got)), gate.ROUND_MATCHES)

    def test_a_win_with_no_readable_turn_plays_the_round(self):
        self.assertTrue(gate.needs_round(self.agent, [{"quote": {"turn": "1"}}]))
        self.assertTrue(gate.needs_round(self.agent, [{"quote": {"turn": True}}]))
        self.assertFalse(gate.needs_round(self.agent, [{"quote": {"turn": 1}}, {"quote": {"turn": 1}}]))

    def test_a_plain_lesson_takes_no_round(self):
        world = round_world(round_won=False)
        got = self.fresh(world)(LINE, (plug_mod.ALL,))
        self.assertTrue(got.passed)
        self.assertEqual(self.round_rows(got), [])


class TheRound(Rounds):
    def test_the_correction_is_handed_first_in_fresh_matches(self):
        prompts, openings = [], []

        def agent(messages, tools):
            prompts.append(messages[0]["content"])
            openings.append(messages[-1]["content"])
            return say("Yes, in stock.")
        world = round_world()
        world.agent = agent
        before = (self.folder / run.MATCHES_FILE).exists()
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertTrue(got.passed, got.rows)
        self.assertTrue(prompts and all("- " + LINE in p for p in prompts))
        self.assertIn(FRESH, openings)
        self.assertEqual((self.folder / run.MATCHES_FILE).exists(), before)  # no match saved
        self.assertEqual(got.pairs, [])
        self.assertGreater(got.calls, 0)

    def test_a_lost_match_holds_the_correction_with_its_line(self):
        world = round_world(round_won=False)
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, gate.ROUND_CHECK)
        self.assertEqual(got.line(), "failed the practice round, at match 1")
        self.assertEqual(len(self.round_rows(got)), 1)  # it stops at the first loss
        self.assertIn("lost:", got.first.why)

    def test_one_win_and_one_loss_still_holds_it(self):
        seen = []

        def judge(messages):
            seen.append(1)
            return say(json.dumps({"reached": len(seen) == 1, "broke_never": False, "turn": 1, "why": "x"}))
        world = round_world()
        world.judge = judge
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual([r.passed for r in self.round_rows(got)], [True, False])
        self.assertEqual(got.line(), "failed the practice round, at match 2")

    def test_a_judge_that_does_not_answer_holds_it(self):
        world = round_world()
        world.judge = lambda m: say("not json")
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.NOT_RUN)

    def test_a_customer_model_error_holds_it(self):
        world = round_world()

        def customer(messages):
            raise ModelError("Baseten call failed: TimeoutError")
        world.customer = customer
        got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.NOT_RUN)
        self.assertIn("model error", got.first.why)

    def test_the_cap_holds_it(self):
        world = round_world()
        fresh = self.fresh(world)
        fresh.cap = 1
        (self.root / run.CALLS_FILE).write_text(json.dumps({"day": run.today(), "calls": 1, "cap": 1}))
        got = fresh.correction(LINE, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.NOT_RUN)
        self.assertIn("cap", got.first.why)

    def test_no_practice_customer_that_can_win_holds_it(self):
        world = round_world()
        with mock.patch("arena.madeup.for_agent", return_value=([{"id": "persona-01", "unwinnable": True}], False)):
            got = self.fresh(world).correction(LINE, (plug_mod.ALL,))
        self.assertFalse(got.passed)
        self.assertEqual(got.first.check, engine_exam.NOT_RUN)

    def test_a_failed_exam_plays_no_round(self):
        world = round_world()
        failed = engine_exam.Result(passed=False, rows=[engine_exam.Row(1, "x", "good", False, "c", "why")])
        got = self.fresh(world, examiner=lambda text, tags: failed).correction(LINE, (plug_mod.ALL,))
        self.assertIs(got, failed)

    def test_the_night_names_a_failed_round_match(self):
        self.assertEqual(study._case_name({"situation": 2, "name": "persona-03", "check": engine_exam.ROUND}),
                         "practice round match 2 (persona-03)")


class OnTheAgentPage(Base):
    page = CorrectionOnTheAgentPage.page

    def test_a_correction_whose_round_is_lost_waits_for_a_yes(self):
        world = round_world(round_won=False)
        page = self.page(world)
        said = page.correct("stock_watch", LINE)
        self.assertIn("waits for your yes on Today", said)
        self.assertIn("failed the practice round, at match 1", said)
        les = page.lessons["stock_watch"].mine()[-1]
        self.assertNotEqual(les["state"], engine_lessons.TRYING)

    def test_a_correction_whose_round_is_won_runs_as_a_hotfix(self):
        world = round_world()
        page = self.page(world)
        said = page.correct("stock_watch", LINE)
        self.assertIn("runs now as a hotfix in half the chats", said)
        les = page.lessons["stock_watch"].mine()[-1]
        self.assertEqual((les["state"], les["share"]), (engine_lessons.TRYING, engine_lessons.HOTFIX_SHARE))
