"""DECISIONS item 98: no cap on lessons in the study, a deadline and a queue. The study writes and
examines every lesson it finds; once it is past its deadline, a person pressed Stop or the day's
model call cap is reached, every lesson not examined yet goes to the agent's queue, and the next
study takes the queued ones first, with their sources and kind. Scripted parts and a counting
exam only: no model, no network."""
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from arena import run as arena_run
from engine import exam as engine_exam
from engine import risk, study
from engine import study_queue as queue
from engine.lessons import IDEA, PATTERN, Lessons
from engine.log import Log
from engine.study import Study
from kit.db import Db
from reflection import night as night_mod
from reflection import scheduler as sc
from tests import plugs
from tests import study_fakes as fk

NOW = fk.NOW
WALL = "near the old stone wall by the gate"  # the beds' note: a line that copies it copies a case
WORDS = ("north", "south", "east", "west", "middle", "corner", "upper", "lower", "back")  # no digits: a digit is high
NINE = [fk.candidate(fk.EARLY, pattern=f"pattern {w}", lesson=f"Water the {w} beds early in the morning.")
        for w in WORDS]
FIVE_IDEAS = [{"lesson": f"Try the {w} path first on a round.", "situation": "A round.", "stages": ["all"]}
              for w in WORDS[:5]]
COPIES = {"lesson": f"Water the beds {WALL} first.", "situation": "A round.", "stages": ["grown"]}
NEW = fk.candidate(fk.EARLY, pattern="pattern new", lesson="Water the new beds early in the morning.")
MARKS = {c["pattern"]: "early" for c in NINE + [NEW]}
CAIRO = ZoneInfo("Africa/Cairo")


def always_low(text, high_about, low_about):
    return risk.LOW


class Exam:
    """The eval gate from a script: every lesson passes; it keeps each line it examined. after: called
    after each exam with the count so far (a test presses Stop or fills the cap there)."""

    def __init__(self, after=None):
        self.seen, self.after = [], after

    def __call__(self, text, stages):
        self.seen.append(text)
        if self.after is not None:
            self.after(len(self.seen))
        return engine_exam.Result(True, [engine_exam.Row(1, "s1", "guard", True)], calls=1)


class Ideas:
    def __init__(self, *ideas):
        self.ideas, self.calls = list(ideas), []

    def __call__(self, plug, sample, limit, known):
        self.calls.append(limit)
        return [dict(i) for i in self.ideas]


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        self.log = Log(self.db, self.plug)
        fk.beds(self.log, note=WALL)
        self.exam = Exam()
        self.lessons = Lessons(self.db, self.plug, judge=always_low, exam=self.exam)

    def study(self, candidates=(), ideas=(), **kw):
        self.ideas = Ideas(*ideas)
        return Study(self.db, self.plug, proposer=fk.Proposer(*candidates), tagger=fk.Tagger(MARKS),
                     lessons=self.lessons, ideas=self.ideas, **kw)

    def run_study(self, candidates=(), ideas=(), study_kw=None, **run_kw):
        run_kw.setdefault("take_queue", True)  # as the night and Run reflection run it
        return self.study(candidates, ideas, **(study_kw or {})).run(fk.SINCE, fk.UNTIL, now=NOW, **run_kw)

    def texts(self):
        return [les["text"] for les in self.lessons.mine()]


class NoCap(Base):
    def test_every_candidate_past_five_is_written_and_examined(self):
        rep = self.run_study(NINE)
        self.assertEqual(len(rep["candidates"]), 9)
        self.assertEqual(sorted(self.texts()), sorted(c["lesson"] for c in NINE))
        self.assertEqual(sorted(self.exam.seen), sorted(c["lesson"] for c in NINE))  # every one took the exam
        self.assertEqual(rep["dropped"], [])

    def test_every_idea_past_three_is_written_and_examined(self):
        rep = self.run_study(ideas=FIVE_IDEAS)
        self.assertEqual([i["lesson_id"] is not None for i in rep["ideas"]], [True] * 5)
        self.assertEqual(sorted(self.exam.seen), sorted(i["lesson"] for i in FIVE_IDEAS))

    def test_one_trial_runs_on_a_stage_at_a_time(self):
        self.run_study(NINE)
        states = [les["state"] for les in self.lessons.mine()]
        self.assertEqual(states.count("trying"), 1)  # every lesson is on stage all: the rest wait their turn
        self.assertEqual(states.count("waiting"), 8)


class Deadline(Base):
    def test_a_deadline_in_the_past_queues_everything_not_examined(self):
        rep = self.run_study(NINE, FIVE_IDEAS, deadline=time.time() - 1)
        self.assertEqual((self.texts(), self.exam.seen, rep["cards"]), ([], [], []))
        self.assertEqual(rep["stopped"], study.PAST_DEADLINE)
        self.assertEqual(len(rep["queued"]), 9)  # the ideas part did not run after the stop
        self.assertEqual(self.ideas.calls, [])
        self.assertEqual(queue.count(self.db, self.plug.agent), 9)
        self.assertEqual({c["verdict"] for c in rep["candidates"]}, {f"{study.QUEUED} ({study.PAST_DEADLINE})"})

    def test_the_deadline_is_read_before_each_lesson(self):
        clock = [0.0]

        def tick(n):
            clock[0] = 100.0 if n >= 3 else 0.0
        self.exam.after = tick
        rep = self.run_study(NINE, study_kw={"clock": lambda: clock[0]}, deadline=50.0)
        self.assertEqual(len(self.exam.seen), 3)
        self.assertEqual(len(self.texts()), 3)
        self.assertEqual(len(rep["queued"]), 6)
        self.assertEqual(queue.count(self.db, self.plug.agent), 6)

    def test_no_deadline_runs_to_the_end(self):
        rep = self.run_study(NINE)
        self.assertIsNone(rep["stopped"])
        self.assertEqual((rep["queued"], queue.count(self.db, self.plug.agent)), ([], 0))


class Stop(Base):
    def test_stop_pressed_queues_the_rest(self):
        pressed = []
        self.exam.after = lambda n: pressed.append(True) if n == 2 else None
        rep = self.run_study(NINE, FIVE_IDEAS, stop=lambda: bool(pressed))
        self.assertEqual(len(self.exam.seen), 2)
        self.assertEqual(rep["stopped"], study.STOP_PRESSED)
        self.assertEqual(len(rep["queued"]), 7)
        self.assertEqual(queue.count(self.db, self.plug.agent), 7)
        self.assertTrue(any(study.STOP_PRESSED in n for n in rep["notes"]))

    def test_a_stop_check_that_fails_queues_never_drops(self):
        def broken():
            raise RuntimeError("the page is gone")
        rep = self.run_study(NINE, stop=broken)
        self.assertEqual(self.exam.seen, [])
        self.assertEqual(len(rep["queued"]), 9)
        self.assertIn("RuntimeError", rep["stopped"])

    def test_the_night_takes_the_stop_check(self):
        pressed = [True]
        rep = night_mod.night(self.db, self.plug, until=fk.UNTIL, days=30, others=[], judge=always_low,
                              proposer=fk.Proposer(*NINE), tagger=fk.Tagger(MARKS), fit=fk.Fit(), adapter=fk.Adapter(),
                              stop=lambda: pressed[0])
        self.assertEqual((rep["stopped"], len(rep["queued"])), (study.STOP_PRESSED, 9))
        self.assertEqual(queue.count(self.db, self.plug.agent), 9)
        self.assertIn("stopped: a person pressed Stop; queued for the next study: 9", night_mod.text(rep, self.plug))


class CallCap(Base):
    def test_the_call_cap_queues_the_rest(self):
        spent = []
        self.exam.after = lambda n: spent.append(n)
        rep = self.run_study(NINE, capped=lambda: len(spent) >= 4)
        self.assertEqual(len(self.exam.seen), 4)
        self.assertEqual(rep["stopped"], study.CAP_REACHED)
        self.assertEqual(queue.count(self.db, self.plug.agent), 5)

    def test_the_night_reads_the_days_call_count(self):
        with tempfile.TemporaryDirectory() as home:
            capped = night_mod.day_cap_reached(home)
            self.assertFalse(capped())  # no count yet
            path = Path(home) / arena_run.CALLS_FILE
            path.write_text(json.dumps({"day": arena_run.today(), "calls": arena_run.DEFAULT_CAP}), encoding="utf-8")
            self.assertTrue(capped())
            path.write_text("not a count", encoding="utf-8")
            self.assertTrue(capped())  # fails closed, as Calls does
            rep = night_mod.night(self.db, self.plug, until=fk.UNTIL, days=30, others=[], judge=always_low,
                                  proposer=fk.Proposer(*NINE), tagger=fk.Tagger(MARKS), fit=fk.Fit(),
                                  adapter=fk.Adapter(), capped=capped)
        self.assertEqual((rep["stopped"], len(rep["queued"])), (study.CAP_REACHED, 9))


class NextRun(Base):
    def test_queued_lessons_go_first_next_run_and_keep_their_sources_and_kind(self):
        first = self.run_study(NINE[:2], [COPIES], deadline=time.time() - 1)
        queued_sources = [json.loads(r["item"])["source"] for r in self.rows()]
        self.assertEqual(len(first["queued"]), 2)
        self.assertEqual(queue.count(self.db, self.plug.agent), 2)
        # the second run: no deadline, ideas again, and a new candidate of its own
        rep = self.run_study([NEW], [COPIES])
        self.assertEqual([q["lesson"] for q in rep["from_queue"]], [c["lesson"] for c in NINE[:2]])
        mine = self.lessons.mine()
        self.assertEqual([les["text"] for les in mine[:2]], [c["lesson"] for c in NINE[:2]])  # written first
        self.assertEqual(mine[2]["text"], NEW["lesson"])
        self.assertEqual([les["source"] for les in mine[:2]], queued_sources)  # the source line it was found with
        self.assertEqual({les["kind"] for les in mine[:2]}, {PATTERN})
        self.assertEqual(self.exam.seen[:2], [c["lesson"] for c in NINE[:2]])  # the full exam, first
        self.assertEqual(queue.count(self.db, self.plug.agent), 0)
        self.assertEqual([r["outcome"] for r in self.rows()], ["written", "written"])

    def test_a_queued_idea_keeps_its_kind_and_the_cases_it_was_read_on(self):
        study = self.study([], [COPIES])  # Stop is pressed once the idea part has answered
        study.run(fk.SINCE, fk.UNTIL, now=NOW, stop=lambda: bool(self.ideas.calls))
        self.assertEqual(queue.count(self.db, self.plug.agent), 1)
        self.assertEqual(self.exam.seen, [])
        rep = self.run_study()  # the next run's idea part gives nothing: only the queue writes
        les = self.lessons.get(rep["from_queue"][0]["lesson_id"])
        self.assertEqual(les["kind"], IDEA)
        self.assertEqual((les["risk"], les["state"]), ("high", "waiting"))  # copies a case: the copy check saw its cases
        self.assertIn(risk.COPIED, les["risk_why"])

    def test_a_line_queued_twice_waits_once(self):
        self.run_study(NINE[:3], deadline=time.time() - 1)
        self.run_study(NINE[:3], deadline=time.time() - 1)
        self.assertEqual(queue.count(self.db, self.plug.agent), 3)

    def test_a_queued_line_that_is_a_lesson_by_then_is_not_written_again(self):
        self.run_study(NINE[:1], deadline=time.time() - 1)
        self.lessons.propose(NINE[0]["lesson"], ["all"], source="by hand", sources=[], now=NOW)
        rep = self.run_study()
        self.assertEqual(rep["from_queue"][0]["why"], study.KNOWN)
        self.assertEqual(self.texts(), [NINE[0]["lesson"]])
        self.assertEqual(queue.count(self.db, self.plug.agent), 0)

    def test_a_run_stopped_again_leaves_the_queue_in_order(self):
        self.run_study(NINE[:3], deadline=time.time() - 1)
        rep = self.run_study([NEW], deadline=time.time() - 1)
        self.assertEqual(rep["from_queue"], [])
        self.assertEqual([r["lesson"] for r in self.rows() if r["taken_at"] is None],
                         [c["lesson"] for c in NINE[:3]] + [NEW["lesson"]])

    def test_a_run_that_does_not_take_the_queue_leaves_it_alone(self):  # an Arena round: its exam is scoped
        self.run_study(NINE[:2], deadline=time.time() - 1)
        rep = self.study([NEW]).run(fk.SINCE, fk.UNTIL, now=NOW)
        self.assertEqual((rep["from_queue"], self.texts()), ([], [NEW["lesson"]]))
        self.assertEqual(queue.count(self.db, self.plug.agent), 2)

    def test_the_night_takes_the_queue_first(self):
        first = self.night(NINE[:2], deadline=time.time() - 1)  # the scheduled night past 09:00
        self.assertEqual(len(first["queued"]), 2)
        rep = self.night([NEW])
        self.assertEqual([q["lesson"] for q in rep["from_queue"]], [c["lesson"] for c in NINE[:2]])
        self.assertEqual(self.texts(), [c["lesson"] for c in NINE[:2]] + [NEW["lesson"]])
        self.assertEqual(queue.count(self.db, self.plug.agent), 0)
        self.assertEqual(len(rep["links"]["lessons"]), 3)  # each queued lesson keeps its cases in the links
        self.assertTrue(all(link["cases"] for link in rep["links"]["lessons"]))
        self.assertIn("from the queue, first: 2", night_mod.text(rep, self.plug))

    def night(self, candidates, **kw):
        return night_mod.night(self.db, self.plug, until=fk.UNTIL, days=30, others=[], judge=always_low,
                               proposer=fk.Proposer(*candidates), tagger=fk.Tagger(MARKS), fit=fk.Fit(),
                               adapter=fk.Adapter(), **kw)

    def rows(self):
        with self.db.tx() as c:
            return [dict(r) for r in c.execute("SELECT * FROM study_queue ORDER BY id")]


class QueueCount(unittest.TestCase):
    def test_the_count_reads_without_changing_a_database_with_no_queue(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        self.assertEqual(queue.count(db, "waterer"), 0)
        with db.tx() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'study_queue'").fetchone())

    def test_the_count_is_per_agent_and_drops_when_taken(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        queue.ensure(db)
        a = queue.add(db, "waterer", kind=PATTERN, part="pattern", lesson="One.", item={}, why="x", now=1)
        queue.add(db, "waterer", kind=IDEA, part="idea", lesson="Two.", item={}, why="x", now=2)
        queue.add(db, "fan", kind=IDEA, part="idea", lesson="Three.", item={}, why="x", now=3)
        self.assertEqual((queue.count(db, "waterer"), queue.count(db, "fan")), (2, 1))
        self.assertTrue(queue.take(db, "waterer", a, outcome="written", now=4))
        self.assertFalse(queue.take(db, "waterer", a, outcome="written", now=5))  # taken once
        self.assertEqual(queue.count(db, "waterer"), 1)

    def test_a_row_is_never_rewritten_or_deleted(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        queue.ensure(db)
        a = queue.add(db, "waterer", kind=PATTERN, part="pattern", lesson="One.", item={}, why="x", now=1)
        for sql in ("UPDATE study_queue SET lesson = 'Other.' WHERE id = ?", "DELETE FROM study_queue WHERE id = ?"):
            with self.assertRaises(Exception), db.tx() as c:
                c.execute(sql, (a,))
        self.assertEqual(queue.waiting(db, "waterer")[0]["lesson"], "One.")


class NightDeadline(unittest.TestCase):
    def test_the_deadline_is_the_next_nine_in_the_morning_cairo(self):
        start = datetime(2026, 11, 10, 3, 0, tzinfo=CAIRO).timestamp()
        nine = datetime(2026, 11, 10, 9, 0, tzinfo=CAIRO).timestamp()
        self.assertEqual(sc.deadline_for(start, CAIRO, limit=10 * 3600), nine)
        late = datetime(2026, 11, 10, 10, 0, tzinfo=CAIRO).timestamp()
        tomorrow = datetime(2026, 11, 11, 9, 0, tzinfo=CAIRO).timestamp()
        self.assertEqual(sc.deadline_for(late, CAIRO, limit=48 * 3600), tomorrow)

    def test_the_childs_limit_comes_first_when_it_is_sooner(self):
        start = datetime(2026, 11, 10, 3, 0, tzinfo=CAIRO).timestamp()
        self.assertEqual(sc.deadline_for(start, CAIRO, limit=4 * 3600), start + 4 * 3600 - sc.GRACE)

    def test_a_night_from_three_runs_to_nine_and_its_limit_stays_under_stale(self):
        start = datetime(2026, 11, 10, 3, 0, tzinfo=CAIRO).timestamp()
        nine = datetime(2026, 11, 10, 9, 0, tzinfo=CAIRO).timestamp()
        self.assertEqual(sc.deadline_for(start, CAIRO), nine)  # the default limit no longer cuts it at 07:30
        self.assertGreaterEqual(start + sc.LIMIT - sc.GRACE, nine)
        self.assertLess(sc.LIMIT, sc.STALE)

    def test_the_scheduler_gives_each_night_its_deadline(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        start = datetime(2026, 11, 10, 6, 0, tzinfo=CAIRO).timestamp()
        got = []
        s = sc.Scheduler(db, "/fake/ascent.db", when=(3, CAIRO), clock=lambda: start, holder="here",
                         find=lambda: [("alpha", Path("alpha/plug.json"))],
                         run=lambda path, db_path, now, deadline=None: got.append((now, deadline)) or 0)
        s.once()
        self.assertEqual(got, [(start, datetime(2026, 11, 10, 9, 0, tzinfo=CAIRO).timestamp())])

    def test_the_child_command_carries_the_deadline(self):
        seen = {}

        class Child:
            pid, stdin = 0, mock.Mock()

            def __init__(self, cmd, **kw):
                seen["cmd"] = cmd

            def wait(self, timeout=None):
                return 0
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sc.subprocess, "Popen", Child):
            sc.run_night("alpha/plug.json", str(Path(d) / "ascent.db"), 1.0, deadline=2.5)
        self.assertEqual(seen["cmd"][-2:], ["--deadline", "2.5"])


if __name__ == "__main__":
    unittest.main()
