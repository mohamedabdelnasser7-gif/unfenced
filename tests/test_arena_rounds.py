"""The Arena between rounds (arena/rounds.py, new 2026-10-31; DECISIONS items 8, 9a and 27): the
night study on a round's lost matches, every new lesson through the eval gate, only the lessons
that pass handed to the next round, and every model call counted against the Arena's cap. Fake
models only, no network; the cards are made here, never read from arena/real/."""
import contextlib
import io
import json
import os
import sqlite3
import stat
import tempfile
import time
import unittest
from pathlib import Path

from arena import rounds, run
from arena.rounds import DAY
from engine import exam as engine_exam
from engine.lessons import TRYING, WAITING
from kit.db import Db
from reflection import PLUG
from reflection.lessons import Lessons as SalesLessons
from reflection.results import Results
from tests.fake_model import BUY, Seller, clean_env, say
from tests.kept import kept_lesson

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

    def cli(self, db, ideas, *, refuse=(), cap=1000, rounds_n=2, state=None, accept=False, buyers=(), cards=None,
            full=None):
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
            reflection = {"study": self.night, "open": self.night, "exam": self.exam_model, "examiner": self.exams}
            if full is not None:
                reflection["full"] = full
            code = run.main(argv, agent_model=self.agent, customer_model=self.customer, reflection=reflection)
        return code, json.loads(out.getvalue())

    def lessons(self, db):
        d = Db(str(db))
        self.addCleanup(d.close)
        L = SalesLessons(d)
        return {les["text"]: les for les in L.mine()}, L

    def arena_lessons(self, db):
        """The lessons in the Arena's own copy of the database (DECISIONS item 46)."""
        return self.lessons(db.with_name(db.name + run.ARENA_SUFFIX))

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
        saved, _ = self.lessons(db)  # the live database: only the lesson that passed
        self.assertEqual(saved[GOOD]["state"], TRYING)
        self.assertNotIn(BAD, saved)
        practised, _ = self.arena_lessons(db)
        self.assertEqual(practised[BAD]["state"], WAITING)  # held by the gate, in the Arena's copy only

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
        self.assertEqual(saved, {})  # refused: it never reaches the live database
        practised, _ = self.arena_lessons(db)
        self.assertEqual(practised[GOOD]["state"], WAITING)

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
        self.assertEqual(saved, {})
        practised, _ = self.arena_lessons(db)
        self.assertEqual({practised[GOOD]["state"], practised[BAD]["state"]}, {WAITING})  # nothing unchecked goes ahead
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
        self.assertEqual(self.lessons(db)[0], {})
        saved, L = self.arena_lessons(db)
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


def dump(path):
    """Every row of every table in the database at path, by table, as text: for a before and after."""
    c = sqlite3.connect(str(path))
    try:
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE "
                                          "'sqlite_%' ORDER BY name")]
        return {t: sorted(repr(tuple(r)) for r in c.execute(f'SELECT * FROM "{t}"')) for t in tables}
    finally:
        c.close()


class LiveStaysLive(Base):
    """DECISIONS item 46: the Arena practises on its own copy of the database, and the live one
    changes only by a lesson that passed the eval gate."""

    def live_db(self):
        db = self.db()
        d = Db(str(db))
        L = SalesLessons(d)
        kept_lesson(L, "Say the price and the delivery fee together.", ["all"])
        Results(d).act("live-chat-1", PLUG.result("replied").after, result="replied", stage="asking", step=1,
                       detail={"customer": "How much?", "reply": "16,500 EGP."}, at=1_000_000.0)
        d.close()
        return db

    def copy_of(self, db):
        return db.with_name(db.name + run.ARENA_SUFFIX)

    def arena_cases(self, path):
        d = Db(str(path))
        self.addCleanup(d.close)
        with d.tx() as c:
            return {r[0] for r in c.execute("SELECT case_id FROM trace WHERE json_extract(detail, '$.arena') = 1")}

    def test_the_live_database_gains_only_the_lesson_that_passed(self):
        db = self.live_db()
        before = dump(db)
        code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD])
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"]), (1, 1))
        after = dump(db)
        for table, rows in before.items():  # nothing the live database held is changed or removed
            self.assertLessEqual(set(rows), set(after[table]), table)
        added = {t: sorted(set(after[t]) - set(before.get(t, []))) for t in after}
        added = {t: rows for t, rows in added.items() if rows}
        self.assertEqual(sorted(added), ["lesson_exams", "lessons", "trials"])
        self.assertEqual([len(added[t]) for t in ("lesson_exams", "lessons", "trials")], [1, 1, 1])
        self.assertIn(GOOD, added["lessons"][0])
        self.assertNotIn(BAD, repr(after))
        live, L = self.lessons(db)
        passed = [one for one in got["lessons"] if one["passed"]][0]
        self.assertEqual(passed["live_id"], live[GOOD]["id"])
        self.assertNotIn("live_id", [one for one in got["lessons"] if not one["passed"]][0])
        self.assertEqual(live[GOOD]["state"], TRYING)  # a Canary on the live share, as the live rules start it
        self.assertEqual(L.exam_of(live[GOOD]["id"])["passed"], 1)
        self.assertEqual(self.arena_cases(db), set())  # the lost matches are cases in the copy only
        self.assertGreaterEqual(len(self.arena_cases(self.copy_of(db))), got["cases"])  # each round's losses
        practised, _ = self.arena_lessons(db)
        self.assertLessEqual({GOOD, BAD, "Say the price and the delivery fee together."}, set(practised))

    def test_a_run_with_no_lesson_passed_leaves_the_live_database_as_it_was(self):
        for ideas, refuse, rounds_n in (([GOOD], (), 1), ([GOOD, BAD], (GOOD, BAD), 2)):
            with self.subTest(rounds=rounds_n):
                db = self.live_db() if rounds_n == 1 else self.db("second")
                if rounds_n == 2:
                    d = Db(str(db))
                    kept_lesson(SalesLessons(d), "Name the size chart.", ["all"])
                    d.close()
                before = dump(db)
                code, rep = self.cli(db, ideas, refuse=refuse, rounds_n=rounds_n)
                self.assertEqual(dump(db), before)
                self.assertTrue(self.arena_cases(self.copy_of(db)))

    def test_each_run_starts_from_a_fresh_copy_of_the_live_database(self):
        db = self.live_db()
        copy = self.copy_of(db)
        copy.write_text("not a database", encoding="utf-8")
        copy.with_name(copy.name + "-wal").write_text("a stale side file", encoding="utf-8")
        self.cli(db, [GOOD, BAD], refuse=[BAD])
        self.assertIn(BAD, self.arena_lessons(db)[0])
        self.cli(db, [], rounds_n=1)  # the next run copies the live database again
        practised, L = self.arena_lessons(db)
        self.assertEqual(practised[GOOD]["state"], TRYING)
        # DECISIONS item 50: the line the gate refused comes with its exam row, still waiting, never live
        self.assertEqual(practised[BAD]["state"], WAITING)
        self.assertEqual(L.exam_of(practised[BAD]["id"])["passed"], 0)
        self.assertNotIn(BAD, self.lessons(db)[0])

    def test_a_line_refused_in_one_run_stays_refused_in_the_next(self):
        """Review round 1, finding 1: the failed line, its exam row with it, is carried into the next
        run's copy, so the study does not write it again even when the exam would pass it now."""
        db = self.live_db()
        code, rep = self.cli(db, [BAD], refuse=[BAD])
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"]), (0, 1))
        for run_no in (2, 3):  # carried again from a copy that was itself carried into
            with self.subTest(run=run_no):
                code, rep = self.cli(db, [BAD], refuse=())
                got = rep["rounds"][0]["reflection"]
                self.assertEqual((got["proposed"], got["passed"]), (0, 0))
                self.assertEqual(self.exams.seen, [])
                self.assertNotIn(BAD, self.lessons(db)[0])
                practised, L = self.arena_lessons(db)
                self.assertEqual(practised[BAD]["state"], WAITING)
                self.assertEqual(L.exam_of(practised[BAD]["id"])["passed"], 0)
                self.assertEqual(sum(1 for x in L.mine() if x["text"] == BAD), 1)

    def test_only_failed_untried_waiting_lessons_are_carried(self):
        db = self.live_db()
        copy = self.copy_of(db)
        d = Db(str(copy))
        low = lambda text, high_about, low_about: "low"  # noqa: E731

        def examiner(ok):
            def examine(text, tags):
                row = engine_exam.Row(1, "price asked", "exam", ok, "" if ok else "price", "" if ok else "no price")
                return engine_exam.Result(passed=ok, rows=[row], calls=1)
            return examine
        passed = SalesLessons(d, judge=low, exam=examiner(True)).propose(GOOD, ["all"], source="s", sources=[])
        failed = SalesLessons(d, judge=low, exam=examiner(False)).propose(BAD, ["all"], source="s", sources=[])
        L = SalesLessons(d)
        no_exam = L.propose("Name the size chart.", ["all"], source="s", sources=[])
        pulled_failed = SalesLessons(d, judge=low, exam=examiner(False)).propose(
            "Thank the customer at the end.", ["all"], source="s", sources=[])
        self.assertEqual(L.exam_of(pulled_failed)["passed"], 0)
        self.assertTrue(L.pull(pulled_failed, "the team"))
        self.assertEqual(L.get(failed)["state"], WAITING)
        self.assertIsNone(L.trial(failed))
        d.close()
        run.arena_copy(db)
        practised, L2 = self.arena_lessons(db)
        self.assertEqual(sorted(practised), sorted(["Say the price and the delivery fee together.", BAD]))
        self.assertGreater(practised[BAD]["id"], 1)
        row = L2.exam_of(practised[BAD]["id"])
        self.assertEqual((row["passed"], row["check_name"]), (0, "price"))
        self.assertIsNone(practised[BAD]["source_lesson_id"])
        del passed, no_exam

    def test_hand_live_follows_the_live_rules_and_refuses_a_lesson_that_failed(self):
        def examiner(ok):
            def examine(text, tags):
                row = engine_exam.Row(1, "price asked", "exam", ok, "" if ok else "price", "" if ok else "no price")
                return engine_exam.Result(passed=ok, rows=[row], calls=1)
            return examine
        copy, live = Db(":memory:"), Db(":memory:")
        self.addCleanup(copy.close)
        self.addCleanup(live.close)
        low = lambda text, high_about, low_about: "low"  # noqa: E731
        practised = SalesLessons(copy, judge=low, exam=examiner(True))
        passed = practised.propose(GOOD, ["all"], source="night study of sales", sources=[])
        self.assertEqual(practised.get(passed)["state"], TRYING)
        failing = SalesLessons(copy, judge=low, exam=examiner(False))
        failed = failing.propose(BAD, ["all"], source="night study of sales", sources=[])
        L = SalesLessons(live)
        on_trial = L.add("Name the size chart.", ["all"])  # a live trial on the same stage
        self.assertEqual(L.get(on_trial)["state"], TRYING)
        new = rounds.hand_live(copy, L, passed, now=time.time())
        les = L.get(new)
        self.assertEqual((les["text"], les["state"], les["risk"], les["origin"]), (GOOD, WAITING, "low", "agent"))
        trial = L.trial(new)
        self.assertIsNone(trial["started_at"])  # waits its turn behind the live trial
        self.assertIsNotNone(trial["queued_at"])
        self.assertEqual(L.exam_of(new)["passed"], 1)
        with self.assertRaises(ValueError):
            rounds.hand_live(copy, L, failed)
        self.assertEqual(sorted(x["text"] for x in L.mine()), sorted([GOOD, "Name the size chart."]))


    def test_a_lesson_that_fails_the_full_exam_is_not_handed_live(self):
        """Review simplify round 1 (red team A): the scoped exam alone never reaches real customers; a
        passed lesson takes the full exam before hand_live, and one that fails it stays in the Arena."""
        db = self.live_db()
        before = dump(db)
        code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD], full=Exams([GOOD]))
        got = rep["rounds"][0]["reflection"]
        passed = [one for one in got["lessons"] if one["passed"]][0]
        self.assertIsNone(passed["live_id"])
        self.assertIn(rounds.FULL_HELD, passed["live"])
        self.assertTrue(passed["full_exam"].startswith("held"))
        self.assertEqual(dump(db), before)

    def test_a_lesson_that_passes_the_full_exam_is_handed_live(self):
        db = self.live_db()
        code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD], full=Exams([]))
        got = rep["rounds"][0]["reflection"]
        passed = [one for one in got["lessons"] if one["passed"]][0]
        self.assertEqual(passed["full_exam"], "passed")
        live, _ = self.lessons(db)
        self.assertEqual(passed["live_id"], live[GOOD]["id"])

    def test_a_full_exam_that_raises_hands_nothing(self):
        db = self.live_db()
        before = dump(db)
        def broken(plug, kept, model):
            def run_it(text, tags):
                raise RuntimeError("no model")
            return run_it
        code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD], full=broken)
        passed = [one for one in rep["rounds"][0]["reflection"]["lessons"] if one["passed"]][0]
        self.assertIsNone(passed["live_id"])
        self.assertEqual(dump(db), before)

    def test_the_real_run_takes_the_full_exam_before_live(self):
        from reflection import exam as exam_mod_sales
        made = rounds.full_examiner(PLUG, None, None)
        self.assertIsInstance(made, exam_mod_sales.Examiner)
        self.assertFalse(made.scope)
        self.assertIsNone(made.cap)

    def test_a_busy_live_database_is_noted_on_the_round_and_the_report_still_comes(self):
        """Review round 1, finding 4: sqlite3.Error from the live database leaves the run and its report."""
        from unittest import mock
        db = self.live_db()
        before = dump(db)
        with mock.patch.object(rounds, "hand_live", side_effect=sqlite3.OperationalError("database is locked")):
            code, rep = self.cli(db, [GOOD, BAD], refuse=[BAD])
        self.assertEqual(code, 1)
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"]), (1, 1))
        passed = [one for one in got["lessons"] if one["passed"]][0]
        self.assertIsNone(passed["live_id"])
        self.assertIn(rounds.LIVE_BUSY, passed["live"])
        self.assertTrue(any(rounds.LIVE_BUSY in n for n in got["notes"]), got["notes"])
        self.assertEqual(dump(db), before)
        self.assertEqual(len(rep["rounds"]), 2)  # the run went on to its next round


class HandLive(unittest.TestCase):
    """arena/rounds.py hand_live on its own (review round 1, finding 2): the live risk and yes rules."""

    def setUp(self):
        self.copy, self.live = Db(":memory:"), Db(":memory:")
        self.addCleanup(self.copy.close)
        self.addCleanup(self.live.close)
        self.now = time.time()

    @staticmethod
    def examiner(ok):
        def examine(text, tags):
            row = engine_exam.Row(1, "price asked", "exam", ok, "" if ok else "price", "" if ok else "no price")
            return engine_exam.Result(passed=ok, rows=[row], calls=1)
        return examine

    def high_tried(self):
        """A high risk lesson that passed and went on trial in the copy, under the copy's Accept high risk."""
        high = lambda text, high_about, low_about: "high"  # noqa: E731
        P = SalesLessons(self.copy, judge=high, exam=self.examiner(True))
        P.switches.set_accept_high(True, "the user", now=self.now - 10)
        lid = P.propose(HIGH, ["all"], source="night study of sales", sources=[], now=self.now - 5)
        self.assertEqual(P.get(lid)["state"], TRYING)
        return lid

    def raw(self, db, text, *, agent="sales", state=WAITING, risk="low", source=None, passed=True):
        """A lesson written straight to db, with a passed or failed exam row and no trial."""
        SalesLessons(db)
        with db.tx() as c:
            lid = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, source_lesson_id, added_at, "
                            "origin, kind) VALUES (?, ?, 'all', 'retail', ?, ?, ?, ?, 'agent', 'idea')",
                            (agent, text, risk, state, source, self.now - 100)).lastrowid
            engine_exam.save(c, agent, lid, engine_exam.Result(passed=passed, rows=[], calls=1), self.now - 50)
        return lid

    def test_high_risk_waits_for_a_yes_while_the_live_accept_is_off(self):
        lid = self.high_tried()
        L = SalesLessons(self.live)
        new = rounds.hand_live(self.copy, L, lid, now=self.now)
        les = L.get(new)
        self.assertEqual((les["risk"], les["state"], les["yes_by"]), ("high", WAITING, None))
        self.assertIsNone(L.trial(new))

    def test_high_risk_starts_under_the_live_accept(self):
        lid = self.high_tried()
        L = SalesLessons(self.live)
        L.switches.set_accept_high(True, "the owner", now=self.now - 1)
        new = rounds.hand_live(self.copy, L, lid, now=self.now)
        les = L.get(new)
        self.assertEqual((les["risk"], les["state"]), ("high", TRYING))
        self.assertIsNotNone(les["yes_at"])
        self.assertIsNotNone(L.trial(new)["accept_high"])

    def test_high_risk_waits_once_the_live_accept_has_run_out(self):
        lid = self.high_tried()
        L = SalesLessons(self.live)
        L.switches.set_accept_high(True, "the owner", days=1, now=self.now - 3 * DAY)
        new = rounds.hand_live(self.copy, L, lid, now=self.now)
        self.assertEqual((L.get(new)["state"], L.get(new)["yes_by"]), (WAITING, None))
        self.assertIsNone(L.trial(new))

    def test_low_risk_with_no_trial_in_the_copy_waits_live(self):
        lid = self.raw(self.copy, GOOD)
        L = SalesLessons(self.live)
        new = rounds.hand_live(self.copy, L, lid, now=self.now)
        self.assertEqual((L.get(new)["risk"], L.get(new)["state"]), ("low", WAITING))
        self.assertIsNone(L.trial(new))
        self.assertEqual(L.exam_of(new)["passed"], 1)

    def test_a_pulled_lesson_or_another_agents_is_refused(self):
        pulled = self.raw(self.copy, GOOD, state="pulled")
        other = self.raw(self.copy, BAD, agent="support")
        L = SalesLessons(self.live)
        for lid in (pulled, other, 999):
            with self.subTest(lesson=lid), self.assertRaises(ValueError):
                rounds.hand_live(self.copy, L, lid, now=self.now)
        self.assertEqual(L.mine(), [])

    def test_clashes_and_the_source_name_the_live_lesson_by_its_words(self):
        """Review round 1, finding 7 (red team 4): a copy id can name another lesson live."""
        shared = self.raw(self.copy, "Say the price first.")
        source = self.raw(self.copy, "Greet by name.", agent="support")
        lid = self.raw(self.copy, GOOD, source=source)
        with self.copy.tx() as c:
            c.execute("INSERT INTO lesson_clashes (lesson_id, live_id, agent, at) VALUES (?, ?, 'sales', ?)",
                      (lid, shared, self.now))
        for text, agent in (("A live line added since the copy.", "sales"), ("Another one.", "sales"),
                            ("Say the price first.", "sales"), ("Greet by name.", "support")):
            self.raw(self.live, text, agent=agent)
        L = SalesLessons(self.live)
        new = rounds.hand_live(self.copy, L, lid, now=self.now)
        with self.live.tx() as c:
            by_text = {r["text"]: r["id"] for r in c.execute("SELECT id, text FROM lessons")}
            clashes = [r["live_id"] for r in c.execute("SELECT live_id FROM lesson_clashes WHERE lesson_id = ?", (new,))]
        self.assertNotEqual(by_text["Say the price first."], shared)  # the ids differ, as they do after the copy
        self.assertEqual(clashes, [by_text["Say the price first."]])
        self.assertEqual(L.get(new)["source_lesson_id"], by_text["Greet by name."])
        gone = self.raw(self.copy, BAD, source=source)  # its source and its clash are not live: none written
        with self.copy.tx() as c:
            c.execute("INSERT INTO lesson_clashes (lesson_id, live_id, agent, at) VALUES (?, ?, 'sales', ?)",
                      (gone, lid, self.now))
        with self.live.tx() as c:
            c.execute("UPDATE lessons SET state = 'pulled', pulled_at = ? WHERE text = 'Greet by name.'", (self.now,))
        new2 = rounds.hand_live(self.copy, L, gone, now=self.now)
        with self.live.tx() as c:
            self.assertEqual([r[0] for r in c.execute("SELECT live_id FROM lesson_clashes WHERE lesson_id = ?",
                                                      (new2,))], [new])
        self.assertEqual(L.get(new2)["source_lesson_id"], by_text["Greet by name."])  # pulled, still its source


class ArenaCopy(unittest.TestCase):
    """arena/run.py arena_copy: the live file is never removed or written, and the copy is a new file."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def live(self, name="ascent.db", wal=False):
        path = self.dir / name
        db = Db(str(path))
        if wal:
            db.conn.execute("PRAGMA wal_autocheckpoint = 0")
        with db.tx() as c:
            c.execute("CREATE TABLE t (x)")
            c.execute("INSERT INTO t VALUES ('live')")
        if wal:
            self.addCleanup(db.close)
            return path, db
        db.close()
        return path, None

    @staticmethod
    def rows(path):
        c = sqlite3.connect(str(path))
        try:
            return [r[0] for r in c.execute("SELECT x FROM t")]
        finally:
            c.close()

    def test_the_live_file_under_the_copy_name_is_refused_before_anything_is_removed(self):
        """Red team round 1, finding 1."""
        real = self.dir / "X.arena"  # --db X, a link to X.arena: the live file is the copy's name
        c = sqlite3.connect(str(real))
        c.executescript("CREATE TABLE t (x); INSERT INTO t VALUES ('live');")
        c.close()
        (self.dir / "X").symlink_to(real.name)
        with self.assertRaises(run.Refused):
            run.arena_copy(self.dir / "X")
        self.assertEqual(self.rows(real), ["live"])
        for how in ("symlink", "hard link"):
            with self.subTest(how=how):
                live, _ = self.live(f"{how[0]}.db")
                copy = live.with_name(live.name + run.ARENA_SUFFIX)
                copy.symlink_to(live) if how == "symlink" else os.link(live, copy)
                with self.assertRaises(run.Refused):
                    run.arena_copy(live)
                self.assertEqual(self.rows(live), ["live"])
                self.assertTrue(os.path.lexists(copy))

    def test_a_copy_side_file_that_is_the_live_side_file_is_refused(self):
        live, db = self.live(wal=True)
        wal = live.with_name(live.name + "-wal")
        self.assertGreater(wal.stat().st_size, 0)
        os.link(wal, live.with_name(live.name + run.ARENA_SUFFIX + "-wal"))
        with self.assertRaises(run.Refused):
            run.arena_copy(live)
        self.assertGreater(wal.stat().st_size, 0)

    def test_the_copy_is_a_new_private_file_and_old_side_files_go(self):
        live, _ = self.live()
        os.chmod(live, 0o644)
        copy = live.with_name(live.name + run.ARENA_SUFFIX)
        copy.symlink_to(self.dir / "nowhere.db")  # a dangling link left at the copy's name
        stale = {s: copy.with_name(copy.name + s) for s in run.SIDE_FILES}
        for p in stale.values():
            p.write_bytes(b"stale side file")
        from unittest import mock
        with mock.patch.object(run.sqlite3, "connect", wraps=sqlite3.connect) as opened:
            got = run.arena_copy(live)
        self.assertEqual(got, copy)
        self.assertFalse(copy.is_symlink())
        self.assertFalse((self.dir / "nowhere.db").exists())
        self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o600)
        self.assertEqual(self.rows(copy), ["live"])
        for p in stale.values():
            self.assertFalse(p.exists() and p.read_bytes() == b"stale side file", p)
        first = opened.call_args_list[0]
        self.assertTrue(first.args[0].endswith("?mode=ro") and first.kwargs.get("uri"), first)  # live only read

    def test_a_link_planted_after_the_old_copy_goes_is_never_written_through(self):
        """Red team round 1, finding 2: the copy is made with O_EXCL and O_NOFOLLOW."""
        import pathlib
        from unittest import mock
        live, _ = self.live()
        copy = live.with_name(live.name + run.ARENA_SUFFIX)
        real_unlink = pathlib.Path.unlink
        for how in ("symlink", "hard link"):
            with self.subTest(how=how):
                if os.path.lexists(copy):
                    os.unlink(copy)
                copy.write_text("last run's copy", encoding="utf-8")

                def planted(path, *a, **k):
                    real_unlink(path, *a, **k)
                    if path == copy:
                        os.symlink(live.name, copy) if how == "symlink" else os.link(live, copy)

                with mock.patch.object(pathlib.Path, "unlink", planted), self.assertRaises(run.Refused):
                    run.arena_copy(live)
                self.assertEqual(self.rows(live), ["live"])
                self.assertEqual(os.stat(copy).st_ino, os.stat(live).st_ino)  # the planted name, left as it was

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
