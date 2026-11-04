"""The shared pool in the night study (engine/study.py step 6, reflection/shared.py; DECISIONS item 83):
lesson patterns of the agent's kind seen at 2 or more other owners are read right after the siblings,
each through the fit check, the adapter and the agent's own eval gate, never live straight away and
never kept directly; with no gate each waits for a yes. A pattern seen at one owner, or at this
agent's own owner, is not read. The night gives the pool its kept lessons as clean patterns. Any
kind: sales, support and a kind Build made. The model parts and the writer are fakes."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from engine import exam as engine_exam
from engine import risk, study
from engine.lessons import Lessons
from engine.study import Study
from kit.db import Db
from reflection import night as night_mod
from reflection import shared
from tests import plugs
from tests import study_fakes as fk
from tests.fake_model import FakeModel, say
from tests.kept import kept_lesson
from tests.test_engine_study_across import NOW, UNTIL

ROOT = Path(__file__).resolve().parent.parent
PATTERN = "When a customer goes quiet after hearing the cost, offer a smaller size before they leave."
NEAR = "If the customer goes quiet after hearing the cost, offer a smaller size before they leave."
MINE = "Offer this house's smaller fan when the grower goes quiet at the cost."
SIB = "Spin the fans slowly at first."
SIB_MINE = "Spin this house's fans slowly at first."
FAR = "Post entries in date sequence."
FAR_MINE = "Spin the fans in house sequence."
GIVEN = "When the grower asks twice about noise, explain the quiet setting before anything else."
FILTERS = "When the grower asks about dust, show the filter choices before anything else."


def always_low(text, high_about, low_about):
    return risk.LOW


def passing(text, stages):
    return engine_exam.Result(True, [engine_exam.Row(1, "s1", "guard", True)], calls=1)


def failing(text, stages):
    return engine_exam.Result(False, [engine_exam.Row(1, "s1", "guard", False, "guard", "it broke")], calls=1)


def writer_of(*lines):
    return shared.Writer(model=FakeModel(*[say(json.dumps({"pattern": x})) for x in lines]))


def fan(agent, **over):
    d = dict(copy.deepcopy(plugs.FAN), agent=agent)
    d.update(over)
    return d


class SharedLessons(unittest.TestCase):
    kind = "fans"

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "shared"
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.new = self.agent("fan_new", owner="demo")
        self.pool = shared.Pool(self.kind, self.root)

    def agent(self, name, **over):
        return plugs.load(fan(name, kind=self.kind, **over), self)

    def seen_at(self, *owners, text=PATTERN):
        for n, o in enumerate(owners):
            self.pool.add(shared.LESSON, text if n == 0 else NEAR, o, f"lesson:x:{n}")
        return self.pool.shared(shared.LESSON)[0]["id"] if len(set(owners)) >= 2 else None

    def night(self, exam=None, others=(), writer=None, fit=None, give=shared.GIVE):
        self.mine = Lessons(self.db, self.new, judge=always_low, exam=exam)
        self.fit = fit or fk.Fit({PATTERN: "fully", SIB: "fully", FAR: "partly"})
        self.link = shared.Link.for_plug(self.new, writer or writer_of(), self.root, give=give)
        s = Study(self.db, self.new, proposer=fk.Proposer(), tagger=fk.Tagger(), fit=self.fit,
                  adapter=fk.Adapter({PATTERN: MINE, SIB: SIB_MINE, FAR: FAR_MINE}), others=list(others),
                  lessons=self.mine, shared=self.link)
        return s.run(fk.SINCE, UNTIL, now=NOW)

    def by_text(self):
        return {les["text"]: les for les in self.mine.mine()}

    def test_a_pattern_from_two_owners_goes_on_trial_through_the_gate(self):
        pid = self.seen_at("north", "south")
        rep = self.night(exam=passing)
        les = self.by_text()[MINE]
        self.assertEqual(les["state"], "trying")
        self.assertTrue(self.mine.exam_of(les["id"])["passed"])
        self.assertIn(f"pattern {pid}, learned from 2 owners", les["source"])
        self.assertEqual(shared.owners_in(les["source"]), 2)
        self.assertEqual(rep["cards"][0]["from"], {"agent": "shared_pool", "pool": pid, "owners": 2, "fit": "fully"})
        self.assertEqual(rep["shared"]["read"], 1)
        self.assertEqual(self.fit.calls[0]["other"], "shared_pool")
        self.assertNotIn(study.POOL_NO_GATE, rep["notes"])

    def test_a_gate_fail_holds_it_for_a_yes(self):
        self.seen_at("north", "south")
        self.night(exam=failing)
        les = self.by_text()[MINE]
        self.assertEqual(les["state"], "waiting")
        self.assertIsNone(self.mine.trial(les["id"]))

    def test_with_no_gate_it_waits_for_a_yes_and_is_never_kept(self):
        self.seen_at("north", "south")
        rep = self.night(exam=None)
        les = self.by_text()[MINE]
        self.assertEqual(les["state"], "waiting")
        self.assertIsNone(self.mine.trial(les["id"]))
        self.assertIn(study.POOL_NO_GATE, rep["notes"])
        self.assertNotIn("kept", {x["state"] for x in self.mine.mine()})

    def test_a_pattern_seen_at_one_owner_is_not_read(self):
        self.seen_at("north", "north")
        rep = self.night(exam=passing)
        self.assertEqual(rep["shared"]["read"], 0)
        self.assertNotIn(MINE, self.by_text())
        self.assertEqual(self.fit.calls, [])

    def test_a_pattern_its_own_owner_gave_is_not_read_back(self):
        self.seen_at("demo", "south")
        rep = self.night(exam=passing)
        self.assertEqual(rep["shared"]["read"], 0)
        self.assertNotIn(MINE, self.by_text())

    def test_a_pattern_taken_before_is_not_asked_again(self):
        self.seen_at("north", "south")
        self.night(exam=None)
        rep = self.night(exam=None)
        self.assertEqual(rep["shared"]["lessons"], [])
        self.assertEqual([les["text"] for les in self.mine.mine()].count(MINE), 1)

    def test_the_pool_comes_right_after_the_siblings(self):
        self.seen_at("north", "south")
        sib = self.agent("fan_old", owner="demo", fields=["cooling"])
        far = plugs.load(plugs.LEDGER, self)
        kept_lesson(Lessons(self.db, sib, judge=always_low), SIB, ["all"], yes_by="owner")
        kept_lesson(Lessons(self.db, far, judge=always_low), FAR, ["all"], yes_by="owner")
        self.night(exam=passing, others=[far, sib])
        self.assertEqual([c["other"] for c in self.fit.calls], ["fan_old", "shared_pool", "ledger"])

    def test_with_no_fit_check_the_pool_is_not_read(self):
        self.seen_at("north", "south")
        self.mine = Lessons(self.db, self.new, judge=always_low)
        s = Study(self.db, self.new, proposer=fk.Proposer(), tagger=fk.Tagger(), lessons=self.mine,
                  shared=shared.Link.for_plug(self.new, writer_of(), self.root))
        rep = s.run(fk.SINCE, UNTIL, now=NOW)
        self.assertIn("no fit check or adapter given; other agents were not read, nor the shared pool", rep["notes"])
        self.assertEqual(self.mine.mine(), [])

    def test_kept_lessons_are_given_once_as_clean_patterns(self):
        mine = Lessons(self.db, self.new, judge=always_low)
        lid = kept_lesson(mine, "Explain the quiet setting first when the grower asks about noise twice.", ["all"],
                          yes_by="owner")
        leak = kept_lesson(mine, "Tell the grower our number when they ask.", ["all"], yes_by="owner")
        rep = self.night(exam=passing, writer=writer_of(GIVEN, "Call the grower back on 01012345678 at once."))
        given = {g["lesson"]: g for g in rep["shared"]["given"]}
        self.assertIsNotNone(given[lid]["pattern"])
        self.assertIsNone(given[leak]["pattern"])
        self.assertTrue(given[leak]["why"].startswith("dropped: "))
        raw = (self.root / f"patterns-{self.kind}.json").read_text()
        self.assertIn(GIVEN, raw)
        self.assertNotIn("01012345678", raw)
        self.assertNotIn("demo", raw)
        rep = self.night(exam=passing)  # the fake writer has no script left: nothing is asked again
        self.assertEqual(rep["shared"]["given"], [])

    def test_at_most_give_kept_lessons_reach_the_writer_a_night_oldest_first(self):
        mine = Lessons(self.db, self.new, judge=always_low)
        first = kept_lesson(mine, "Explain the quiet setting first when the grower asks about noise twice.", ["all"],
                            yes_by="owner")
        second = kept_lesson(mine, "Show the filter choices before the price when the grower asks about dust.",
                             ["all"], yes_by="owner")
        rep = self.night(exam=passing, writer=writer_of(GIVEN), give=1)
        self.assertEqual([g["lesson"] for g in rep["shared"]["given"]], [first])
        self.assertIsNotNone(rep["shared"]["given"][0]["pattern"])
        rep = self.night(exam=passing, writer=writer_of(FILTERS), give=1)
        self.assertEqual([g["lesson"] for g in rep["shared"]["given"]], [second])

    def test_a_lesson_from_the_pool_is_not_given_back(self):
        self.seen_at("north", "south")
        self.night(exam=passing)
        les = self.by_text()[MINE]
        self.assertTrue(self.mine.keep(les["id"]))
        rep = self.night(exam=passing)  # the writer has no script: asking it would fail the run
        self.assertEqual(rep["shared"]["given"], [])

    def test_the_night_runner_reads_the_pool_and_its_text_names_it(self):
        self.seen_at("north", "south")
        link = shared.Link.for_plug(self.new, writer_of(), self.root)
        rep = night_mod.night(self.db, self.new, days=30, until=UNTIL, others=[], judge=always_low,
                              proposer=fk.Proposer(), tagger=fk.Tagger(), fit=fk.Fit({PATTERN: "fully"}),
                              adapter=fk.Adapter({PATTERN: MINE}), shared=link)
        self.assertEqual(rep["links"]["lessons"][0]["from_agent"], "shared_pool")
        self.assertIn(f"from the shared pool of {self.kind} agents: 1 patterns seen at 2 or more other owners, "
                      "1 taken on through the gate; 0 kept lessons given to the pool", night_mod.text(rep, self.new))


class AnyKind(unittest.TestCase):
    """The same path for any kind: sales, support and a kind Build made (tests/agents/stock_watch)."""

    def plug_of(self, kind):
        if kind == "stock_watch":
            d = json.loads((ROOT / "tests" / "agents" / "stock_watch" / "plug.json").read_text())
            d.update(agent="stock_new", kind="stock_watch", owner="demo")  # Build writes the kind into the plug
        else:
            d = fan(f"{kind}_new", kind=kind, owner="demo")
        return plugs.load(d, self)

    def test_each_kind_reads_only_its_own_pool_and_goes_through_the_gate(self):
        for kind in ("sales", "support", "stock_watch"):
            with self.subTest(kind=kind):
                d = tempfile.TemporaryDirectory()
                self.addCleanup(d.cleanup)
                root = Path(d.name) / "shared"
                pool = shared.Pool(kind, root)
                pool.add(shared.LESSON, PATTERN, "north", "a")
                pool.add(shared.LESSON, NEAR, "south", "b")
                shared.Pool("other_kind", root).add(shared.LESSON, GIVEN, "north", "c")
                shared.Pool("other_kind", root).add(shared.LESSON, GIVEN, "south", "d")
                plug = self.plug_of(kind)
                db = Db(":memory:")
                self.addCleanup(db.close)
                mine = Lessons(db, plug, judge=always_low)
                stages = list(plug.stages)[:1] or ["all"]
                s = Study(db, plug, proposer=fk.Proposer(), tagger=fk.Tagger(),
                          fit=fk.Fit({PATTERN: "partly", GIVEN: "fully"}),
                          adapter=fk.Adapter({PATTERN: MINE, GIVEN: "never this"}, stages=stages), lessons=mine,
                          shared=shared.Link.for_plug(plug, writer_of(), root))
                rep = s.run(fk.SINCE, UNTIL, now=NOW)
                got = {les["text"]: les for les in mine.mine()}
                self.assertEqual(set(got), {MINE})
                self.assertEqual(got[MINE]["state"], "waiting")  # no gate on these lessons
                self.assertIn(study.POOL_NO_GATE, rep["notes"])


if __name__ == "__main__":
    unittest.main()
