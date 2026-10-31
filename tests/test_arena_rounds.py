"""The Arena between rounds (arena/rounds.py, new 2026-10-31; DECISIONS items 8, 9a and 27): the
night study on a round's lost matches, every new lesson through the eval gate, only the lessons
that pass handed to the next round, and every model call counted against the Arena's cap. Fake
models only, no network; the cards are made here, never read from arena/real/."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from arena import rounds, run
from engine import exam as engine_exam
from engine.lessons import TRYING, WAITING
from kit.db import Db
from reflection import PLUG
from reflection.lessons import Lessons as SalesLessons
from tests.fake_model import BUY, Seller, clean_env, say

GOOD = "Ask the customer which size they wear first."
BAD = "Keep each reply short and plain."
HIGH = "Promise a free exchange when the size does not fit."
IDEA_HEAD = "You suggest new things"
JUDGE_HEAD = "You sort one lesson"


def card(i, worry):
    return {"id": f"persona-{i:02d}", "worry": worry, "unwinnable": False, "want": ["boots"],
            "buy_trigger": ["a clear answer"], "patience": {"median": 1, "most": 1}, "examples": [],
            "style": {"language": {"english": 1.0}, "length": {"short": 1.0}, "opening": {"price": 1.0}},
            "arena_weight": 0.5}


class Agent(Seller):
    """The fake_model Seller, keeping the system message of every call (the lessons it was handed)."""

    def __init__(self):
        super().__init__()
        self.systems = []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.systems.append(messages[0]["content"])
        return super().chat(messages, tools, effort, max_tokens, whole)


class Customer:
    """Buys when its worry is in buyers (BUY, then yes to the summary), else leaves after its first
    line; with no buyers every match is lost."""

    def __init__(self, buyers=()):
        self.buyers, self.calls = set(buyers), 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        worry = messages[0]["content"].split("Your worry is ")[1].split(".")[0]
        if len(messages) == 2:
            return say("How much is the Mercurial Vapor 17 Elite?")
        if worry not in self.buyers:
            return say("[leave]")
        return say("yes" if "Confirm?" in (messages[-1]["content"] or "") else BUY)


class Night:
    """The night study's model: the idea part answers with the given lessons, the risk judge says
    high for a line with a promise in it and low otherwise, anything else gets an empty list. At its
    first call it notes how many agent calls came before and the Arena's count then."""

    def __init__(self, ideas, agent, calls_file):
        self.ideas, self.agent, self.calls_file = list(ideas), agent, calls_file
        self.calls, self.agent_before, self.count_at_first = 0, None, None

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        if self.agent_before is None:
            self.agent_before = len(self.agent.systems)
            self.count_at_first = json.loads(Path(self.calls_file).read_text(encoding="utf-8"))["calls"]
        system = messages[0]["content"]
        if system.startswith(IDEA_HEAD):
            return say(json.dumps([{"lesson": x, "situation": "Any chat.", "stages": ["all"]} for x in self.ideas]))
        if system.startswith(JUDGE_HEAD):
            return say("high" if "promise" in messages[1]["content"].lower() else "low")
        return say("[]")


class ExamModel:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        return say("ok")


class Exams:
    """A stand-in exam: one model call through the model it is given (so the cap counts it), then a
    pass unless the line is in refuse, with one pair (wrong before, right after a pass)."""

    def __init__(self, refuse=()):
        self.refuse, self.seen = set(refuse), []

    def __call__(self, plug, kept, model):
        def examine(text, tags):
            model.chat([{"role": "system", "content": "exam"}, {"role": "user", "content": text}])
            self.seen.append(text)
            ok = text not in self.refuse
            row = engine_exam.Row(1, "price asked", "exam", ok, "" if ok else "price", "" if ok else "no price given")
            return engine_exam.Result(passed=ok, rows=[row], calls=1, pairs=[engine_exam.Pair("price asked", False, ok)])
        return examine


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.cards = self.dir / "cards"
        self.cards.mkdir()
        for c in (card(1, "price"), card(2, "fit")):
            (self.cards / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")
        self.trust = self.dir / "trust.json"
        self.trust.write_text(json.dumps({"sales": {"matches": 1, "wins": 1}}), encoding="utf-8")

    def db(self, name="agent"):
        folder = self.dir / name
        folder.mkdir()
        path = folder / "ascent.db"
        Db(str(path)).close()
        return path

    def cli(self, db, ideas, *, refuse=(), cap=1000, rounds_n=2, state=None, accept=False, buyers=(), cards=None):
        self.agent, self.customer = Agent(), Customer(buyers)
        calls_file = (run.state_dir(db) if db else Path(state)) / run.CALLS_FILE
        self.night, self.exam_model, self.exams = Night(ideas, self.agent, calls_file), ExamModel(), Exams(refuse)
        if accept:
            d = Db(str(db))
            SalesLessons(d).switches.set_accept_high(True, "the user")
            d.close()
        where = ["--db", str(db)] if db else ["--state", str(state)]
        argv = ["--cards", str(cards or self.cards), "--matches", "2", "--rounds", str(rounds_n), "--held-out", "persona-02",
                "--trust", str(self.trust), "--cap", str(cap), "--json"] + where
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = run.main(argv, agent_model=self.agent, customer_model=self.customer,
                            reflection={"study": self.night, "open": self.night, "exam": self.exam_model,
                                        "examiner": self.exams})
        return code, json.loads(out.getvalue())

    def lessons(self, db):
        d = Db(str(db))
        self.addCleanup(d.close)
        L = SalesLessons(d)
        return {les["text"]: les for les in L.mine()}, L

    def round_two(self):
        """The agent's system messages after the night study, and before it."""
        k = self.night.agent_before
        self.assertIsNotNone(k, "the night study never ran")
        return self.agent.systems[:k], self.agent.systems[k:]


class Between(Base):
    def test_round_two_uses_the_lesson_round_one_passed_and_never_the_refused_one(self):
        db = self.db()
        code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD])
        self.assertEqual(code, 1)
        self.assertEqual(rep["stopped"], run.ROUNDS)
        self.assertEqual(len(rep["rounds"]), 2)
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["cases"], got["proposed"], got["passed"], got["refused"], got["handed"]), (2, 2, 1, 1, 1))
        self.assertEqual((got["fixed"], got["broke"]), (1, 0))
        self.assertNotIn("reflection", rep["rounds"][1])  # no step after the last round
        self.assertEqual(sorted(self.exams.seen), sorted([GOOD, BAD]))  # every new lesson took the gate
        before, after = self.round_two()
        self.assertTrue(before and after)
        self.assertFalse(any(GOOD in s for s in before))
        self.assertTrue(all(GOOD in s for s in after), after[0])
        self.assertFalse(any(BAD in s for s in self.agent.systems))
        saved, _ = self.lessons(db)
        self.assertEqual(saved[GOOD]["state"], TRYING)
        self.assertEqual(saved[BAD]["state"], WAITING)  # held by the gate: it waits for a yes

    def test_the_report_and_the_morning_item_show_each_round(self):
        from reflection import morning
        db = self.db()
        code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD])
        item = json.loads((run.state_dir(db) / rep["item"]["file"]).read_text(encoding="utf-8"))
        self.assertEqual(item["kind"], "arena_rounds")
        self.assertEqual([r["round"] for r in item["reflection"]], [1, 2])
        first = item["reflection"][0]
        self.assertEqual((first["gate_won"], first["gate_played"]), (0, 1))
        self.assertEqual({k: first["reflection"][k] for k in ("proposed", "passed", "refused", "handed")},
                         {"proposed": 2, "passed": 1, "refused": 1, "handed": 1})
        self.assertIsNone(item["reflection"][1]["reflection"])
        lines = run.text(rep)
        self.assertIn("Reflection after round 1: night study of 2 lost matches; lessons proposed 2, passed 1, "
                      "refused 1, handed to round 2 1; eval gate fixed 1, broke 0", lines)
        d = Db(str(db))
        self.addCleanup(d.close)
        page = morning.Morning(d, [PLUG], reports=run.state_dir(db))
        view = page.view(item["at"])
        a = [x for x in view["agents"] if x["agent"] == run.AGENT][0]
        self.assertEqual(a["arena"]["file"], rep["item"]["file"])
        html = morning.render(view, token=None)
        self.assertIn("Round 1: gate 0 of 1 won; then Reflection on 2 lost matches: lessons proposed 2, passed 1, "
                      "refused 1, handed to the next round 1; eval gate fixed 1, broke 0.", html)
        self.assertIn("Round 2: gate 0 of 1 won.", html)

    def test_every_call_of_the_night_study_counts_against_the_arena_cap(self):
        db = self.db()
        self.cli(db, [GOOD, BAD], refuse=[BAD])
        saved = json.loads((run.state_dir(db) / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]
        night_calls = self.night.calls + self.exam_model.calls
        self.assertGreaterEqual(self.night.calls, 3)  # the idea part and a judge call for each lesson
        self.assertEqual(self.exam_model.calls, 2)
        self.assertEqual(saved, len(self.agent.calls) + self.customer.calls + night_calls)

    def past_win(self, db):
        """One earlier run whose matches are all won (worry size), so the gate has past wins to rerun."""
        won = self.dir / "won"
        won.mkdir()
        for c in (card(1, "size"), card(2, "size")):
            (won / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")
        code, rep = self.cli(db, [], rounds_n=1, buyers={"size"}, cards=won)
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertTrue(run.past_wins(run.state_dir(db)))
        self.count_before = json.loads((run.state_dir(db) / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]

    def test_the_gate_reruns_past_wins_on_the_same_cap_and_a_win_kept_passes(self):
        db = self.db()
        self.past_win(db)
        code, rep = self.cli(db, [GOOD], buyers={"size"})
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["handed"]), (1, 1))
        rerun = got["calls"] - self.night.calls - self.exam_model.calls
        self.assertGreater(rerun, 0)  # the rerun's agent and customer calls, taken in the step between
        saved = json.loads((run.state_dir(db) / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]
        self.assertEqual(saved - self.count_before, len(self.agent.calls) + self.customer.calls + self.night.calls
                         + self.exam_model.calls)
        _, after = self.round_two()
        self.assertTrue(all(GOOD in s for s in after))

    def test_a_lesson_whose_rerun_loses_a_past_win_is_refused_and_never_reaches_round_two(self):
        db = self.db()
        self.past_win(db)
        code, rep = self.cli(db, [GOOD], buyers=())  # the past win is lost on its rerun
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"], got["handed"], got["broke"]), (0, 1, 0, 1))
        self.assertEqual(self.exams.seen, [GOOD])  # the exam passed it; the rerun held it
        self.assertIn("failed the Arena rerun", got["lessons"][0]["why"])
        _, after = self.round_two()
        flags = [GOOD in s for s in after]  # the rerun hands the new line first, then round 2 never does
        self.assertTrue(True in flags and False in flags)
        self.assertEqual(flags, sorted(flags, reverse=True))
        saved, _ = self.lessons(db)
        self.assertEqual(saved[GOOD]["state"], WAITING)

    def test_a_cap_reached_in_the_night_study_stops_the_run_cleanly(self):
        self.cli(self.db("measure"), [GOOD, BAD], refuse=[BAD])
        before_night = self.night.count_at_first - 1  # the Arena's count before the first night call
        db = self.db()
        code, rep = self.cli(db, [GOOD, BAD], cap=before_night + 1)  # room for the idea part's call only
        self.assertEqual(code, 1)
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual(len(rep["rounds"]), 1)  # no second round
        got = rep["rounds"][0]["reflection"]
        self.assertEqual(got["stopped"], "cap")
        self.assertEqual((got["proposed"], got["passed"], got["refused"], got["handed"]), (2, 0, 2, 0))
        self.assertIn(rounds.CAP_NOTE, got["notes"])
        self.assertEqual(self.night.calls, 1)
        self.assertEqual((self.exam_model.calls, self.exams.seen), (0, []))
        _, after = self.round_two()
        self.assertEqual(after, [])
        self.assertEqual(json.loads((run.state_dir(db) / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"],
                         before_night + 1)
        saved, _ = self.lessons(db)
        self.assertEqual({saved[GOOD]["state"], saved[BAD]["state"]}, {WAITING})  # nothing unchecked goes ahead
        self.assertIn("stopped at the model call cap", run.text(rep))

    def test_a_high_risk_lesson_takes_the_gate_and_still_waits_for_a_yes(self):
        db = self.db()
        code, rep = self.cli(db, [HIGH])
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["proposed"], got["passed"], got["handed"], got["waits_for_yes"]), (1, 1, 0, 1))
        self.assertEqual(self.exams.seen, [HIGH])  # it took the gate though it waits for a yes
        saved, L = self.lessons(db)
        les = saved[HIGH]
        self.assertEqual((les["risk"], les["state"]), ("high", WAITING))
        self.assertIsNone(les["yes_at"])
        self.assertEqual(L.exam_of(les["id"])["passed"], 1)  # its card shows the gate's result
        self.assertFalse(any(HIGH in s for s in self.agent.systems))

    def test_a_refused_high_risk_lesson_waits_with_its_held_line(self):
        db = self.db()
        code, rep = self.cli(db, [HIGH], refuse=[HIGH])
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"], got["handed"], got["waits_for_yes"]), (0, 1, 0, 0))
        saved, L = self.lessons(db)
        self.assertEqual(L.exam_of(saved[HIGH]["id"])["passed"], 0)
        self.assertFalse(any(HIGH in s for s in self.agent.systems))

    def test_under_accept_high_risk_a_passed_high_risk_lesson_goes_on_as_the_engine_allows(self):
        db = self.db()
        code, rep = self.cli(db, [HIGH], accept=True)
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["handed"]), (1, 1))
        self.assertEqual(self.exams.seen, [HIGH])
        _, after = self.round_two()
        self.assertTrue(after and all(HIGH in s for s in after))
        saved, L = self.lessons(db)
        self.assertEqual(saved[HIGH]["state"], TRYING)
        self.assertIsNotNone(L.trial(saved[HIGH]["id"])["accept_high"])

    def test_under_accept_high_risk_a_refused_high_risk_lesson_is_never_handed(self):
        db = self.db()
        code, rep = self.cli(db, [HIGH], refuse=[HIGH], accept=True)
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"], got["handed"]), (0, 1, 0))
        self.assertFalse(any(HIGH in s for s in self.agent.systems))

    def test_no_db_means_no_step_between_rounds(self):
        state = self.dir / "state"
        code, rep = self.cli(None, [GOOD], state=state)
        self.assertEqual(len(rep["rounds"]), 2)
        self.assertFalse(any("reflection" in r for r in rep["rounds"]))
        self.assertEqual((self.night.calls, self.exam_model.calls), (0, 0))
        self.assertNotIn("item", rep)
        self.assertFalse(list(state.glob("arena-sales-*.json")))

    def test_one_round_with_a_db_has_no_step_between(self):
        db = self.db()
        code, rep = self.cli(db, [GOOD], rounds_n=1)
        self.assertNotIn("reflection", rep["rounds"][0])
        self.assertEqual(self.night.calls, 0)

    def test_the_cli_refuses_fake_agent_models_with_no_models_for_the_step_between(self):
        db = self.db()
        argv = ["--cards", str(self.cards), "--matches", "1", "--rounds", "2", "--held-out", "persona-02",
                "--trust", str(self.trust), "--db", str(db)]
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = run.main(argv, agent_model=Agent(), customer_model=Customer())
        self.assertEqual(code, 2)
        self.assertIn("Not run:", err.getvalue())


class Keys(unittest.TestCase):
    def test_a_real_run_names_the_key_the_night_study_needs_before_it_starts(self):
        from unittest import mock
        from reflection import night
        with mock.patch.object(night, "missing_keys", return_value=["BASETEN_API_KEY"]):
            with self.assertRaises(run.Refused) as got:
                run.reflection_models()
        self.assertIn("needs BASETEN_API_KEY", str(got.exception))


class GoesAhead(unittest.TestCase):
    def les(self, state, risk="low"):
        return {"state": state, "risk": risk}

    def test_only_a_pass_that_may_go_ahead_with_no_further_yes(self):
        trial = {"started_at": None}
        self.assertTrue(rounds.goes_ahead(self.les(TRYING), trial, True))
        self.assertTrue(rounds.goes_ahead(self.les("kept"), trial, True))
        self.assertTrue(rounds.goes_ahead(self.les(WAITING), trial, True))  # low risk, waiting its turn
        self.assertFalse(rounds.goes_ahead(self.les(TRYING), trial, False))  # refused, whatever its state
        self.assertFalse(rounds.goes_ahead(self.les("kept"), trial, False))
        self.assertFalse(rounds.goes_ahead(self.les(WAITING), None, True))  # waits for a yes
        self.assertFalse(rounds.goes_ahead(self.les(WAITING, "high"), trial, True))  # high risk waits for its turn
        self.assertFalse(rounds.goes_ahead(self.les("pulled"), trial, True))
        self.assertFalse(rounds.goes_ahead(None, trial, True))


if __name__ == "__main__":
    unittest.main()
