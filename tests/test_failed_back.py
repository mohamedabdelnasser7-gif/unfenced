"""A lesson that fails the eval gate goes back into Reflection (new, 2026-10-31; DECISIONS item
50). Its exam row keeps every failed check with why and the cases it broke; the next night study
gives the proposer and the idea part this agent's failed lines with what each broke, so the next
try is a different line. The same line is never written again, a line close to it waits for a
yes, and the failed lesson is never rewritten and never goes live on its own. Scripted parts and
made-up garden beds only: no model, no network."""
import json
import unittest

from engine import exam as engine_exam
from engine import risk
from engine.lessons import TRYING, WAITING, Lessons
from engine.log import Log
from engine.study import FAILED_BEFORE, Study
from kit.db import Db
from reflection import night
from reflection import study as model_study
from tests import plugs
from tests import study_fakes as fk
from tests.fake_model import FakeModel, clean_env, say

Row, Pair, Result = engine_exam.Row, engine_exam.Pair, engine_exam.Result
CLOSE = fk.candidate(fk.EARLY, lesson="In the morning water the beds early.")
NEW_TRY = fk.candidate(fk.EARLY, lesson="Water the beds early, and skip the shaded ones until noon.")
SHADE_IDEA = {"lesson": "Visit the shaded beds last on a round.", "situation": "A round with shaded beds.",
              "stages": ["all"]}


def always_low(text, high_about, low_about):
    return risk.LOW


def failing(text, tags):
    """A gate that fails: two failed checks, one case broken and one fixed."""
    rows = [Row(1, "dry_bed", "guard", True), Row(2, "shade_bed", "guard", False, "no_shade", "it watered the shade"),
            Row(3, "wet_bed", "real", False, "no_flood", "it flooded a wet bed")]
    return Result(False, rows, calls=3, pairs=[Pair("situation 1", False, True), Pair("situation 2", True, False),
                                                Pair("situation 3", False, False)])


def passing(text, tags):
    return Result(True, [Row(1, "dry_bed", "guard", True)], calls=1, pairs=[Pair("situation 1", True, True)])


class Recorder:
    """A proposer or idea part that keeps what it was given, failed lines included."""

    def __init__(self, *items):
        self.items, self.calls = list(items), []

    def __call__(self, plug, sample, limit, known, **kw):
        self.calls.append({"known": list(known), **kw})
        return [dict(i) for i in self.items]


class Saved(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)

    def test_a_failed_gate_keeps_every_failed_check_and_a_pass_keeps_none(self):
        les = Lessons(self.db, self.plug, judge=always_low, exam=failing)
        bad = les.propose(fk.EARLY["lesson"], ["all"], sources=[])
        row = les.exam_of(bad)
        self.assertEqual(json.loads(row["fails"]), [
            {"situation": 2, "name": "shade_bed", "part": "guard", "check": "no_shade", "why": "it watered the shade"},
            {"situation": 3, "name": "wet_bed", "part": "real", "check": "no_flood", "why": "it flooded a wet bed"}])
        self.assertEqual(engine_exam.broke_cases(row), ["situation 2"])
        self.assertEqual(les.get(bad)["state"], WAITING)
        les.examiner = passing
        good = les.propose(fk.MULCH["lesson"], ["seedling"], sources=[])
        self.assertIsNone(les.exam_of(good)["fails"])
        self.assertEqual(engine_exam.fails_of(les.exam_of(good)), [])

    def test_at_most_max_fails_are_kept(self):
        many = [Row(n, f"s{n}", "guard", False, "no_shade", "why") for n in range(1, engine_exam.MAX_FAILS + 5)]
        les = Lessons(self.db, self.plug, judge=always_low, exam=lambda t, s: Result(False, many, calls=1))
        got = engine_exam.fails_of(les.exam_of(les.propose(fk.EARLY["lesson"], ["all"], sources=[])))
        self.assertEqual(len(got), engine_exam.MAX_FAILS)

    def test_a_row_from_before_the_column_reads_its_first_fail(self):
        row = {"passed": 0, "situation": 9, "check_name": "no_shade", "why": "it watered the shade", "fails": None}
        self.assertEqual(engine_exam.fails_of(row), [{"situation": 9, "name": "", "part": "", "check": "no_shade",
                                                      "why": "it watered the shade"}])


class NextNight(unittest.TestCase):
    """Night one writes a lesson its gate fails; night two is the next study."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        fk.beds(Log(self.db, self.plug))
        self.lessons = Lessons(self.db, self.plug, judge=always_low, exam=failing)
        rep = self.study(fk.Proposer(fk.EARLY)).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        self.failed_id = rep["cards"][0]["lesson_id"]
        self.assertEqual(self.lessons.get(self.failed_id)["state"], WAITING)
        self.lessons.examiner = passing

    def study(self, proposer, ideas=None):
        return Study(self.db, self.plug, proposer=proposer, tagger=fk.Tagger(), lessons=self.lessons, ideas=ideas)

    def night(self, *items, ideas=None):
        self.proposer = Recorder(*items)
        return self.study(self.proposer, ideas).run(fk.SINCE, fk.UNTIL, now=fk.NOW + fk.DAY)

    def test_the_proposer_gets_the_failed_line_with_what_it_broke(self):
        rep = self.night()
        call, = self.proposer.calls
        self.assertEqual(call["failed"], [{
            "lesson": fk.EARLY["lesson"],
            "first_fail": "failed the exam: situation 2, check no_shade: it watered the shade",
            "fails": [{"case": "situation 2 (shade_bed)", "check": "no_shade", "why": "it watered the shade"},
                      {"case": "situation 3 (wet_bed)", "check": "no_flood", "why": "it flooded a wet bed"}],
            "broke_cases": ["situation 2"], "fixed": 1, "broke": 1}])
        self.assertNotIn(fk.EARLY["lesson"], call["known"])  # told as a failed try, not as a lesson it has
        self.assertEqual(rep["failed_given"], [self.failed_id])

    def test_the_night_runner_and_the_arena_study_pass_them_on(self):
        proposer = Recorder()  # reflection/night.py LinkedStudy, which arena/rounds.py runs between rounds
        night.LinkedStudy(self.db, self.plug, proposer=proposer, tagger=fk.Tagger(),
                          lessons=self.lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW + fk.DAY)
        self.assertEqual([f["lesson"] for f in proposer.calls[0]["failed"]], [fk.EARLY["lesson"]])

    def test_the_idea_part_gets_them_too(self):
        ideas = Recorder()
        self.night(ideas=ideas)
        call, = ideas.calls
        self.assertEqual([f["lesson"] for f in call["failed"]], [fk.EARLY["lesson"]])
        self.assertNotIn(fk.EARLY["lesson"], call["known"])

    def test_the_same_line_is_never_written_again(self):
        rep = self.night(fk.EARLY)
        self.assertEqual(rep["candidates"][0]["verdict"], FAILED_BEFORE)
        self.assertEqual(rep["cards"], [])
        self.assertEqual(len(self.lessons.mine()), 1)

    def test_a_line_close_to_a_failed_one_waits_for_a_yes_naming_it(self):
        rep = self.night(CLOSE)
        card, = rep["cards"]
        self.assertEqual((card["state"], card["close_to_failed"], card["close_to_pulled"]),
                         (WAITING, fk.EARLY["lesson"], None))
        self.assertIn(f'close to a line that failed the eval gate: "{fk.EARLY["lesson"]}"', card["source"])
        self.assertIsNone(self.lessons.trial(card["lesson_id"]))
        self.assertEqual(night._state(card),
                         f'waits for a yes (close to the line "{fk.EARLY["lesson"]}", which failed the eval gate)')

    def test_a_different_try_is_a_new_lesson_and_the_failed_one_is_never_rewritten(self):
        before = self.lessons.get(self.failed_id)
        rep = self.night(NEW_TRY)
        card, = rep["cards"]
        self.assertNotEqual(card["lesson_id"], self.failed_id)
        self.assertEqual(card["state"], TRYING)
        self.assertEqual(self.lessons.get(self.failed_id), before)  # still waiting, word for word

    def test_a_failed_line_a_person_said_yes_to_is_no_longer_given(self):
        self.assertTrue(self.lessons.approve(self.failed_id, "Mona"))
        self.assertEqual(self.lessons.get(self.failed_id)["state"], TRYING)
        rep = self.night()
        self.assertNotIn("failed", self.proposer.calls[0])
        self.assertIn(fk.EARLY["lesson"], self.proposer.calls[0]["known"])
        self.assertEqual(rep["failed_given"], [])

    def test_with_no_failed_line_the_parts_are_called_as_before(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        fk.beds(Log(db, self.plug))
        proposer, ideas = Recorder(), Recorder()
        Study(db, self.plug, proposer=proposer, tagger=fk.Tagger(), lessons=Lessons(db, self.plug, judge=always_low),
              ideas=ideas).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        self.assertEqual((list(proposer.calls[0]), list(ideas.calls[0])), (["known"], ["known"]))


class ModelParts(unittest.TestCase):
    """The Meta proposer and idea part send the failed lines as data, beside the cases."""

    def setUp(self):
        clean_env(self)
        self.plug = plugs.load(plugs.WATERER, self)
        self.failed = [{"lesson": fk.EARLY["lesson"], "first_fail": "failed the exam: situation 2, check no_shade",
                        "fails": [], "broke_cases": ["situation 2"], "fixed": 1, "broke": 1}]
        self.sample = [{"id": "k1", "steps": [], "deciding": "grew", "good": True}]

    def body(self, part, **kw):
        fake = FakeModel(say("[]"))
        part(fake)(self.plug, self.sample, 3, ["Visit the shady beds first."], **kw)
        system, data = fake.calls[0]["messages"]
        return system["content"], json.loads(data["content"])

    def test_the_failed_lines_go_as_data_when_given(self):
        for part in (model_study.Proposer, model_study.Ideas):
            with self.subTest(part=part.__name__):
                system, body = self.body(part, failed=self.failed)
                self.assertEqual(body["failed"], self.failed)
                self.assertNotIn(fk.EARLY["lesson"], system)
                self.assertIn("failed its eval gate", system)

    def test_no_failed_key_when_none(self):
        for part in (model_study.Proposer, model_study.Ideas):
            with self.subTest(part=part.__name__):
                self.assertNotIn("failed", self.body(part)[1])
                self.assertNotIn("failed", self.body(part, failed=[])[1])


if __name__ == "__main__":
    unittest.main()
