"""Which lessons each place hands the agent (decision 112, amending 81; Mohamed 2026-11-04, a correction he
approved on Today never reached the next chats). Every place reads the live database through
arena/rounds.py live_lessons and hands what a Pool hands. Fake models only, no network.

Coverage. "fix N" fails on the code before this change (ab44c19); "guard" passed there and must keep passing;
"other file" names the test that covers the cell already; "-" is a cell the shared reader covers.

  kind                                 | page chat | Try again       | Arena run       | Train
                                       | (Sales)   | Sales | built   | Sales | built   | Sales | built
  -------------------------------------+-----------+-------+---------+-------+---------+-------+-------
  A correction, exam passed            | guard     | other | -       | other | fix 2   | guard | fix 1
  B correction, exam failed, then Yes  | fix 4     | fix 4 | fix 4   | fix 4 | -       | fix 4 | -
  C correction, exam failed, waiting   | guard     | other | -       | -     | -       | -     | -
  D correction refused (No on Today)   | guard     | -     | -       | -     | -       | -     | -
  E lesson on trial, exam passed       | fix 3     | fix 3 | -       | fix 3 | fix 2+3 | fix 3 | -
  F kept lesson                        | other     | -     | -       | -     | fix 2   | -     | -
  G pulled, or its trial ended         | guard     | -     | -       | -     | -       | guard | -

  The reader (Reader): A, B and E are read, C, D, F (kept comes from the agent's own lessons) and G are not
  (fix 3 and 4); a yes from the high risk switch after a failed exam is not a person's (fix 4). Train Sales guard on G's row: a lesson on trial only in the Arena's copy is never handed.
  Record (fix 5): Try again writes "busy" and, per match, the ids of the lessons it was handed.
  Other files: tests/test_try_sales.py Turn (F), tests/test_try_again.py Hotfixes (A, C),
  tests/test_arena_hotfix.py TypedMidRun (A in the Sales Arena).
  fix 1: Train's Pool reads the live database at its first use (it never refreshes). fix 2: a built agent's
  Arena builds the Pool with no study between rounds. fix 3: lessons on trial are read (decision 112).
  fix 4: a person's yes after a failed exam counts as passing. fix 5: the Try again record.
  Review round 1: a correction paused or past its end date is not read (Reader); a lesson with no exam is read once
  a person's yes starts it (NoExam); a lesson handed on and on trial live is handed once (PoolOnce); Between reads
  the live database again before each exam and gate (Built)."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from arena import rounds, run
from engine import plug as plug_mod
from engine import risk
from engine.lessons import Lessons as EngineLessons
from kit.db import Db
from reflection import PLUG, examples, reflect_now
from reflection import morning as mo
from reflection.lessons import Lessons as SalesLessons
import tests.test_arena_hotfix as hot
import tests.test_arena_rounds as tar
import tests.test_try_again as tta
import tests.test_try_sales as tts
from tests.fake_model import clean_env, say
from tests.kept import kept_lesson
from tests.test_arena_practice import World

FIX = hot.FIX
TRIAL = "Name the delivery days before the price."
AGENT = "family_dinner_planner"
DINNER_FIX = "Always ask how many people eat dinner before you plan the menu."
STUDY = "night study of 2026-11-04"


def on_trial(path, text, stages=("all",), plug=None, now=None):
    """A lesson the agent's study wrote whose exam passed: on trial in the live database at path."""
    d = Db(str(path))
    try:
        L = (EngineLessons(d, plug, judge=hot.low, exam=hot.passed) if plug
             else SalesLessons(d, judge=hot.low, exam=hot.passed))
        lid = L.propose(text, list(stages), source=STUDY, sources=[], now=now)
        assert L.get(lid)["state"] == "trying", L.get(lid)["state"]
        return lid
    finally:
        d.close()


def approved(path, text, plug=None):
    """A correction whose exam failed, then Yes on its Today card (engine Lessons.approve, as Morning.yes)."""
    agent_lessons = (lambda d: EngineLessons(d, plug, judge=hot.low)) if plug else None
    lid = hot.correct(path, text, exam=hot.failed, agent_lessons=agent_lessons)
    d = Db(str(path))
    try:
        L = EngineLessons(d, plug) if plug else SalesLessons(d)
        assert L.approve(lid, "the user")
        assert L.get(lid)["state"] == "trying"
        return lid
    finally:
        d.close()


class Reader(tar.Base):
    def test_live_lessons_reads_the_passed_the_approved_and_the_trials_only(self):
        db = self.db()
        ended = on_trial(db, "Thank them by name.", ("asking",), now=time.time() - 90 * 86400)
        e = on_trial(db, TRIAL, ("asking",))
        g = on_trial(db, "Ask about the colour.", ("my_order",))
        d = Db(str(db))
        try:
            L = SalesLessons(d)
            self.assertTrue(L.pull(g, "pulled on Today"))
            f = kept_lesson(L, "Ask which size they wear.", ["ordering"])
        finally:
            d.close()
        a = hot.correct(db, "Say the shop opens at ten.")
        b = approved(db, FIX)
        c = hot.correct(db, "Never name a price.", exam=hot.failed)
        d_ = hot.correct(db, "Offer a discount.", exam=hot.failed)
        d = Db(str(db))
        try:
            self.assertTrue(SalesLessons(d).pull(d_, "no from the user"))  # No on its Today card (Morning.no)
        finally:
            d.close()
        # two corrections on trial past their end date: one paused (engine/trial.py _stop sets its end date to now,
        # as Lessons.pause does) and one whose trial ended; they wait their turn behind a, so the trial is set here
        paused = hot.correct(db, "Say delivery is free.")
        over = hot.correct(db, "Say returns take two days.")
        d = Db(str(db))
        try:
            with d.tx() as c:
                for lid, end in ((paused, time.time()), (over, time.time() - 30 * 86400)):
                    c.execute("UPDATE lessons SET state = 'trying', ends_at = ? WHERE id = ?", (end, lid))
        finally:
            d.close()
        got = {one["live_id"]: one["hotfix"] for one in rounds.live_lessons(db, PLUG.agent)}
        self.assertEqual(got, {a: True, b: True, e: False})
        for gone in (c, d_, f, g, ended, paused, over):
            self.assertNotIn(gone, got)
        self.assertEqual([one["live_id"] for one in rounds.live_hotfixes(db, PLUG.agent)], [a, b])

    def test_a_yes_from_the_high_risk_switch_is_not_a_persons(self):
        """A lesson whose exam failed, on trial with its yes marked "(Accept high risk)": the switch's yes, never
        a person's, so the reader does not take it as passing."""
        db = self.db()
        d = Db(str(db))
        try:
            L = SalesLessons(d, judge=hot.low, exam=hot.failed)
            lid = L.propose(TRIAL, ["asking"], source=STUDY, sources=[])
            self.assertEqual(L.get(lid)["state"], "waiting")
            with d.tx() as c:
                c.execute("UPDATE lessons SET state = 'trying', ends_at = ?, yes_at = ?, yes_by = ? WHERE id = ?",
                          (time.time() + 86400, time.time(), "the user (Accept high risk)", lid))
        finally:
            d.close()
        self.assertEqual(rounds.live_lessons(db, PLUG.agent), [])


class NoExam(tar.Base):
    """A lesson that took no exam (no lesson_exams row) is handed once a person's yes on Today starts it (decision
    112; Mohamed 2026-11-04, every fix): a high risk one with the switch off, a brought back one, a copied one.
    Never while it waits, nor on the switch's marked yes."""

    def lessons(self, db, judge=hot.low):
        d = Db(str(db))
        self.addCleanup(d.close)
        return SalesLessons(d, judge=judge, exam=hot.passed)

    def read(self, db):
        return {one["live_id"]: one["hotfix"] for one in rounds.live_lessons(db, PLUG.agent)}

    def test_a_high_risk_lesson_with_no_exam_is_handed_after_a_persons_yes(self):
        db = self.db()
        L = self.lessons(db, judge=lambda *a: risk.HIGH)
        lid = L.propose(TRIAL, ["asking"], source=STUDY, sources=[])
        self.assertEqual((L.get(lid)["state"], L.exam_of(lid)), ("waiting", None))
        self.assertEqual(self.read(db), {})  # waiting: never handed
        self.assertTrue(L.approve(lid, "the user"))
        self.assertEqual(L.get(lid)["state"], "trying")
        self.assertEqual(self.read(db), {lid: False})

    def test_a_brought_back_lesson_is_handed(self):
        db = self.db()
        old = on_trial(db, TRIAL, ("asking",))
        L = self.lessons(db)
        self.assertTrue(L.pull(old, "pulled on Today"))
        self.assertEqual(self.read(db), {})
        new = L.bring_back(old, "the user")
        self.assertEqual((L.get(new)["state"], L.exam_of(new)), ("trying", None))
        self.assertEqual(self.read(db), {new: False})

    def test_a_copied_lesson_is_handed_after_a_persons_yes(self):
        db = self.db()
        L = self.lessons(db)
        text = "Tell them the blue trainer comes in sizes forty to forty five today."
        lid = L.propose(text, ["asking"], source=STUDY, sources=[text])
        self.assertTrue(L.get(lid)["risk_why"].startswith(risk.COPIED), L.get(lid)["risk_why"])
        self.assertEqual((L.get(lid)["state"], L.exam_of(lid)), ("waiting", None))
        self.assertEqual(self.read(db), {})
        self.assertTrue(L.approve(lid, "the user"))
        self.assertEqual(self.read(db), {lid: False})

    def test_no_exam_and_the_switchs_yes_is_never_handed(self):
        db = self.db()
        L = self.lessons(db, judge=lambda *a: risk.HIGH)
        lid = L.propose(TRIAL, ["asking"], source=STUDY, sources=[])
        with L.db.tx() as c:
            c.execute("UPDATE lessons SET state = 'trying', ends_at = ?, yes_at = ?, yes_by = ? WHERE id = ?",
                      (time.time() + 86400, time.time(), "the user (Accept high risk)", lid))
        self.assertIsNone(L.exam_of(lid))
        self.assertEqual(self.read(db), {})


class PoolOnce(tar.Base):
    def test_a_lesson_handed_on_and_on_trial_live_is_handed_once(self):
        """A lesson this run passed, handed on and wrote live (hand_live: on trial there) comes back from the live
        read as a trial; the Pool hands its text once, in live() and in pick()."""
        db = self.db()
        copy = db.with_name(db.name + run.ARENA_SUFFIX)
        mine = on_trial(copy, TRIAL, ("asking",))
        on_trial(db, TRIAL, ("asking",))
        d = Db(str(copy))
        self.addCleanup(d.close)
        pool = rounds.Pool(SalesLessons(d), hotfixes=lambda: rounds.live_lessons(str(db), PLUG.agent))
        pool.hand_on(mine)
        pool.refresh()
        self.assertEqual([p["text"] for p in pool.live("asking")].count(TRIAL), 1)
        self.assertEqual([p["text"] for p in pool.pick("asking", "hi")].count(TRIAL), 1)


class PageChat(tts.Base):
    def say(self, text="Is the blue trainer in 41?"):
        said = mo.TWO_TAB_ACTIONS.get("/try/sales") or self.p.actions["/try/sales"]
        said(self.m, {"text": [text]})
        return self.systems[-1]

    def test_a_passed_correction_reaches_the_chat(self):
        hot.correct(self.path, FIX)
        self.assertIn(FIX, self.say())

    def test_a_correction_approved_after_a_failed_exam_reaches_the_next_chat(self):
        lid = hot.correct(self.path, FIX, exam=hot.failed)
        self.assertNotIn(FIX, self.say())  # waiting for its yes: not handed
        self.assertIn("is on trial", self.m.yes(lid, ""))
        self.assertIn(FIX, self.say("And in 42?"))

    def test_a_refused_correction_never_reaches_the_chat(self):
        lid = hot.correct(self.path, FIX, exam=hot.failed)
        self.m.no(lid, "")
        self.assertNotIn(FIX, self.say())

    def test_a_lesson_on_trial_reaches_the_chat_and_stops_once_pulled(self):
        lid = on_trial(self.path, TRIAL)
        self.assertIn(TRIAL, self.say())
        self.assertTrue(self.m.lessons[PLUG.agent].pull(lid, "pulled on Today"))
        self.assertNotIn(TRIAL, self.say("And in 42?"))


class TryAgainSales(tta.Base):
    def saved(self):
        return json.loads(next(self.dir.glob("arena-sales-retry-*.json")).read_text(encoding="utf-8"))

    def test_an_approved_correction_is_handed_and_the_record_names_it(self):
        self.stuck()
        lid = approved(self.path, FIX)
        self.m.try_again("sales")
        self.assertTrue(self.agent.systems)
        self.assertTrue(all(FIX in s for s in self.agent.systems))
        item = self.saved()
        self.assertEqual(item["hotfixes"], [lid])
        self.assertIsNone(item["busy"])  # fix 5: an empty list would say why
        self.assertTrue(item["results"])
        self.assertTrue(all(lid in r["handed"] for r in item["results"]))

    def test_a_lesson_on_trial_is_handed(self):
        self.stuck()
        lid = on_trial(self.path, TRIAL)
        self.m.try_again("sales")
        self.assertTrue(self.agent.systems)
        self.assertTrue(all(TRIAL in s for s in self.agent.systems))
        self.assertEqual(self.saved()["hotfixes"], [])  # a trial is not a correction
        self.assertTrue(all(lid in r["handed"] for r in self.saved()["results"]))


class ArenaSales(tar.Base):
    def test_an_approved_correction_is_handed_in_every_match(self):
        db = self.db()
        approved(db, FIX)
        self.cli(db, [], rounds_n=1)
        self.assertTrue(self.agent.systems)
        self.assertTrue(all(FIX in s for s in self.agent.systems))

    def test_a_lesson_on_trial_is_handed_in_the_next_run(self):
        db = self.db()
        on_trial(db, TRIAL)
        self.cli(db, [], rounds_n=1)
        self.assertTrue(self.agent.systems)
        self.assertTrue(all(TRIAL in s for s in self.agent.systems))


class TrainSales(tar.Base):
    def train(self, db):
        """Train on the Sales agent (reflect_now.run_arena) with its study replaced: what its Pool hands."""
        seen = []

        class Capture:
            def __init__(self, copy, plug, **kw):
                self.pool = kw["pool"]

            def __call__(self, n):
                seen.append([p["text"] for p in self.pool.pick("asking", "hi")])
                return {"lessons": [], "proposed": 0, "notes": []}
        with mock.patch("arena.rounds.Between", Capture):
            reflect_now.run_arena(str(db), PLUG, models={"study": None, "open": None, "exam": None,
                                                          "examiner": None, "full": None},
                                  agent_model=None, customer_model=None,
                                  calls=run.Calls(self.dir / run.CALLS_FILE, 1000),
                                  steps=reflect_now.Steps(reflect_now.READ))
        return seen[0]

    def test_a_passed_correction_is_handed(self):
        db = self.db()
        hot.correct(db, FIX)
        self.assertIn(FIX, self.train(db))

    def test_an_approved_correction_is_handed(self):
        db = self.db()
        approved(db, FIX)
        self.assertIn(FIX, self.train(db))

    def test_a_lesson_on_trial_is_handed(self):
        db = self.db()
        on_trial(db, TRIAL)
        self.assertIn(TRIAL, self.train(db))

    def test_a_trial_only_in_the_arenas_copy_is_not_handed(self):
        """A lesson this run wrote on trial in the copy that the full exam held (FULL_HELD) never reaches the
        live database, so it is never handed: trials are read from the live database only."""
        db = self.db()
        on_trial(reflect_now.arena_path(str(db)), TRIAL)
        self.assertNotIn(TRIAL, self.train(db))


class Built(unittest.TestCase):
    """An agent made here (family_dinner_planner): its Arena, Try again and Train on fake models."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        self.path = self.dir / "ascent.db"
        self.db = Db(str(self.path))
        self.addCleanup(self.db.close)
        self.assertEqual(examples.install(self.path, {"sales"}), [AGENT])
        self.m = mo.Morning(self.db, [plug_mod.load(mo.ROOT / "sales" / "plug.json")], reports=self.dir,
                            db_path=self.path, judge=lambda *a: risk.LOW)
        self.assertEqual(self.m.add_built(), [AGENT])
        self.plug = self.m.plugs[AGENT]
        self.folder = self.dir / "agents" / AGENT
        self.m.arena_shape = {"matches": 1, "rounds": 1}
        self.starts = []
        self.m.arena_start = lambda work, name: self.starts.append(work)
        self.systems = []

    def agent(self, messages, tools):
        self.systems.append(messages[0]["content"])
        return say("Here is your menu.")

    def arena(self, world):
        self.m.arena_models = lambda: (world, world, world)
        self.assertEqual(self.m.run_arena(AGENT, full=True), mo.ARENA_STARTED)
        self.starts.pop()()

    def test_the_arena_with_no_study_hands_the_correction_and_the_kept_lesson(self):
        kept_text = "Suggest one dish the whole family can share."
        kept_lesson(EngineLessons(self.db, self.plug), kept_text, ["all"], yes_by="the user")
        hot.correct(self.path, DINNER_FIX, agent_lessons=lambda d: EngineLessons(d, self.plug, judge=hot.low))
        self.arena(World(agent=self.agent))
        self.assertTrue(self.systems)
        self.assertTrue(all(DINNER_FIX in s and kept_text in s for s in self.systems))

    def test_the_arena_hands_a_lesson_on_trial(self):
        on_trial(self.path, DINNER_FIX, plug=self.plug)
        self.arena(World(agent=self.agent))
        self.assertTrue(self.systems)
        self.assertTrue(all(DINNER_FIX in s for s in self.systems))

    def test_try_again_hands_a_correction_approved_after_a_failed_exam(self):
        self.m.arena_shape = {"matches": 4, "rounds": 1}
        self.arena(World(reached=False))  # every match lost, so there is something to try again
        lid = hot.correct(self.path, DINNER_FIX, exam=hot.failed,
                          agent_lessons=lambda d: EngineLessons(d, self.plug, judge=hot.low))
        self.assertIn("is on trial", self.m.yes(lid, ""))
        win = World(agent=self.agent)
        self.m.retry_models = lambda: (win, win, win)
        self.m.retry_start = lambda work, name: work()
        self.m.try_again(AGENT)
        self.assertTrue(self.systems)
        self.assertTrue(all(DINNER_FIX in s for s in self.systems))
        item = json.loads(sorted(self.dir.glob(f"**/arena-{AGENT}-retry-*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual((item["hotfixes"], item["busy"]), ([lid], None))
        self.assertTrue(all(lid in r["handed"] for r in item["results"]))

    def test_train_hands_a_passed_correction_to_its_exam(self):
        hot.correct(self.path, DINNER_FIX, agent_lessons=lambda d: EngineLessons(d, self.plug, judge=hot.low))
        handed = []

        def make(plug, kept, model):
            handed.append([p["text"] for p in kept.live()])
            return lambda text, stages: hot.passed(text, stages)
        world = World()
        between = reflect_now.train_between(self.db, self.path, self.folder,
                                            models={"study": world, "open": world, "exam": world, "examiner": make},
                                            agent_model=world, customer_model=world, judge_model=world,
                                            steps=reflect_now.Steps(reflect_now.READ))
        between._exam([])
        self.assertIn(DINNER_FIX, handed[0])

    def between(self, seen):
        def make(plug, kept, model):
            def examiner(text, stages):
                seen.append([p["text"] for p in kept.live()])
                return hot.passed(text, stages)
            return examiner
        world = World()
        return reflect_now.train_between(self.db, self.path, self.folder,
                                         models={"study": world, "open": world, "exam": world, "examiner": make},
                                         agent_model=world, customer_model=world, judge_model=world,
                                         steps=reflect_now.Steps(reflect_now.READ))

    def test_train_stops_handing_a_lesson_pulled_between_two_exams(self):
        """Decision 112, read again at every call: Train's Pool reads the live database before each exam, so a
        lesson pulled on Today during Train is not handed to the next exam (Between and BuiltBetween share this)."""
        lid = on_trial(self.path, DINNER_FIX, plug=self.plug)
        seen, path, plug = [], self.path, self.plug

        class Study:
            def __init__(self, db, plug_, *, lessons, **kw):
                self.lessons, self.log = lessons, None

            def run(self, since, until, now=None, stop=None):
                self.lessons.examiner("Ask about the oven.", ["all"])
                d = Db(str(path))
                try:
                    assert EngineLessons(d, plug).pull(lid, "pulled on Today")
                finally:
                    d.close()
                self.lessons.examiner("Ask about the pans.", ["all"])
                return {"notes": [], "cards": []}
        between = self.between(seen)
        between.pending = ["case 1"]
        with mock.patch("reflection.night.LinkedStudy", Study):
            between(1)
        self.assertEqual(len(seen), 2)
        self.assertIn(DINNER_FIX, seen[0])
        self.assertNotIn(DINNER_FIX, seen[1])

    def test_the_gate_reads_the_live_lessons_again(self):
        between = self.between([])
        L = EngineLessons(self.db, self.plug, judge=hot.low, exam=hot.passed)
        lid = L.propose("Ask about the oven.", ["all"], source=STUDY, sources=[])
        with mock.patch.object(between.pool, "refresh", wraps=between.pool.refresh) as spy:
            between._gate(L, hot.passed, lid, time.time())
        spy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
