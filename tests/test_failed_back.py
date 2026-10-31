"""A lesson that fails the eval gate goes back into Reflection (new, 2026-10-31; DECISIONS item
50). Its exam row keeps every failed check with why and the cases it broke; the next night study
gives the proposer and the idea part this agent's failed lines with what each broke, so the next
try is a different line. The same line is never written again, a line close to it waits for a
yes, and the failed lesson is never rewritten and never goes live on its own. Scripted parts and
made-up garden beds only: no model, no network."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import exam as engine_exam
from engine import risk
from engine.lessons import TRYING, WAITING, Lessons
from engine.log import Log
from engine import study as study_mod
from engine.study import FAILED_BEFORE, Study
from kit.db import Db
from reflection import morning, night
from reflection import study as model_study
from sim import run as sim_run
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

    def test_each_kept_why_is_one_short_line(self):  # E8, red team item 5
        why = "it watered\nthe shade " + "x" * 400
        les = Lessons(self.db, self.plug, judge=always_low,
                      exam=lambda t, s: Result(False, [Row(2, "shade_bed", "guard", False, "no_shade", why)], calls=1))
        row = les.exam_of(les.propose(fk.EARLY["lesson"], ["all"], sources=[]))
        kept, = json.loads(row["fails"])
        for got in (kept["why"], row["why"]):
            self.assertNotIn("\n", got)
            self.assertLessEqual(len(got), 300)
            self.assertTrue(got.startswith("it watered the shade x"))

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

    def test_the_morning_page_names_the_failed_line_on_its_card(self):
        rep = self.night(CLOSE)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        until = int(rep["window"]["until"])
        (Path(folder.name) / f"night-{self.plug.agent}-{until}.json").write_text(json.dumps(rep), encoding="utf-8")
        page = morning.render(morning.Morning(self.db, [self.plug], reports=folder.name).view(fk.NOW + fk.DAY),
                              token="t0ken")
        why = f'It comes close to the line "{fk.EARLY["lesson"]}", which failed the eval gate.'
        self.assertIn(morning.h(why), page)
        self.assertNotIn(morning.h("It waits for a person's yes."), page)

    def test_the_simulator_names_the_failed_line_too(self):
        s = sim_run.summary(self.plug, {"read": 0, "seed": 0}, self.night(CLOSE), [self.plug])
        self.assertEqual(s["found"][0]["close_to_failed"], fk.EARLY["lesson"])
        self.assertIn(f'waits for a yes (close to the line "{fk.EARLY["lesson"]}", which failed the eval gate)',
                      sim_run.text(s))

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

    def test_a_failed_line_pulled_with_no_trial_is_still_given(self):  # S1
        self.assertTrue(self.lessons.pull(self.failed_id, "no use"))
        rep = self.night()
        self.assertEqual(rep["failed_given"], [self.failed_id])
        self.assertEqual([f["lesson"] for f in self.proposer.calls[0]["failed"]], [fk.EARLY["lesson"]])

    def test_a_failed_line_a_person_said_yes_to_and_then_pulled_is_not_given(self):  # finding 3
        self.assertTrue(self.lessons.approve(self.failed_id, "Mona"))
        self.assertTrue(self.lessons.pull(self.failed_id, "the trial lost", on_trial=True))
        rep = self.night()
        self.assertEqual(rep["failed_given"], [])
        self.assertNotIn("failed", self.proposer.calls[0])

    def test_a_failed_line_with_a_yes_waiting_its_turn_is_not_given(self):  # finding 3, a yes and no start
        self.lessons.propose("Visit the north beds first.", ["all"], sources=[])  # takes the stage's trial
        self.assertTrue(self.lessons.approve(self.failed_id, "Mona"))
        self.assertEqual(self.lessons.get(self.failed_id)["state"], WAITING)
        self.assertIsNone(self.lessons.trial(self.failed_id)["started_at"])
        self.assertEqual(self.night()["failed_given"], [])
        self.assertTrue(self.lessons.pull(self.failed_id, "no longer"))  # its queued trial row goes with it
        self.assertEqual(self.night()["failed_given"], [])

    def test_a_persons_line_its_exam_still_holds_is_given(self):
        held = self.lessons.add("Water the shaded beds at noon.", ["all"], yes_by="Mona", exam=failing("", ()))
        self.assertEqual(self.lessons.get(held)["state"], WAITING)
        rep = self.night()
        self.assertEqual(rep["failed_given"], [held, self.failed_id])

    def test_a_waiting_lesson_that_passed_its_exam_is_not_given(self):  # S3
        waits = self.lessons.propose("Visit the north beds first.", ["all"], sources=[], trial=False)
        self.assertTrue(self.lessons.exam_of(waits)["passed"])
        self.assertEqual(self.lessons.get(waits)["state"], WAITING)
        rep = self.night()
        self.assertEqual(rep["failed_given"], [self.failed_id])

    def test_the_newest_failed_lines_first_and_at_most_failed_given(self):  # S10, S11
        self.lessons.examiner = failing
        names = ("north", "south", "east", "west", "rose", "herb", "corner", "fence", "pond", "path", "gate", "hill")
        ids = [self.lessons.propose(f"Water the {n} bed at noon.", ["all"], sources=[]) for n in names]
        rep = self.night()
        want = list(reversed([self.failed_id] + ids))[:study_mod.FAILED_GIVEN]
        self.assertEqual(study_mod.FAILED_GIVEN, 10)
        self.assertEqual(rep["failed_given"], want)
        self.assertEqual([f["lesson"] for f in self.proposer.calls[0]["failed"]],
                         [self.lessons.get(i)["text"] for i in want])

    def test_small_rewordings_of_a_failed_line_wait_for_a_yes(self):  # finding 4
        failed = [(study_mod._norm(fk.EARLY["lesson"]), fk.EARLY["lesson"])]
        for line in ("Water beds early.", "Always water the beds early.", "Water the beds early every day.",
                     "Water the beds early, before the sun is up.",
                     "Water the beds early in the morning, then check the shaded ones at noon."):  # one inside
            with self.subTest(line=line):
                self.assertEqual(study_mod._close(line, failed, {fk.EARLY["lesson"]}), fk.EARLY["lesson"])
                self.assertIsNone(study_mod._close(line, failed))  # a pulled line keeps the old rule
        for line in (NEW_TRY["lesson"], "Water the beds late in the evening."):
            self.assertIsNone(study_mod._close(line, failed, {fk.EARLY["lesson"]}), line)

    def test_a_rewording_through_the_night_waits_naming_the_failed_line(self):
        rep = self.night(fk.candidate(fk.EARLY, lesson="Always water the beds early."))
        card, = rep["cards"]
        self.assertEqual((card["state"], card["close_to_failed"]), (WAITING, fk.EARLY["lesson"]))

    def test_a_line_close_to_a_failed_one_still_takes_the_exam(self):  # red team item 4
        self.lessons.examiner = failing
        rep = self.night(CLOSE)
        card, = rep["cards"]
        self.assertEqual(card["close_to_failed"], fk.EARLY["lesson"])
        self.assertFalse(self.lessons.exam_of(card["lesson_id"])["passed"])
        self.assertEqual(card["exam"], "failed the exam: situation 2, check no_shade")

    def test_the_first_fail_given_is_one_short_line(self):  # red team item 5
        long_why = "was won, now lost: left\n(turn 3, agent: " + "A" * 2500 + ")"

        def failing_long(text, tags):
            return Result(False, [Row(2, "rerun-7", "arena", False, engine_exam.RERUN, long_why)], calls=1)

        self.lessons.examiner = failing_long
        self.lessons.propose("Water the beds at dusk.", ["all"], sources=[])
        self.lessons.examiner = passing
        self.night()
        first = self.proposer.calls[0]["failed"][0]["first_fail"]
        self.assertLessEqual(len(first), study_mod.FIRST_FAIL_MAX)
        self.assertNotIn("\n", first)

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
