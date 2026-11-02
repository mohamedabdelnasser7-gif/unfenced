"""Siblings in the night study (engine/study.py step 6, DECISIONS item 79): agents of one kind that
name the same owner are read first, so a new agent of a kind its owner already runs starts with what
they kept, and a sibling's line goes on trial only through this agent's own eval gate. With no gate
it waits for a yes; it is never kept straight away. The model parts are fakes here."""
import copy
import unittest

from engine import exam as engine_exam
from engine import risk, study
from engine.lessons import Lessons
from engine.study import Study
from kit.db import Db
from tests import plugs
from tests import study_fakes as fk
from tests.kept import kept_lesson
from tests.test_engine_study_across import NOW, UNTIL

THEIRS = "Spin the fans slowly at first."
MINE = "Spin this house's fans slowly at first."
FAR = "Post entries in date sequence."
FAR_MINE = "Spin the fans in house sequence."


def always_low(text, high_about, low_about):
    return risk.LOW


def passing(text, stages):
    return engine_exam.Result(True, [engine_exam.Row(1, "s1", "guard", True)], calls=1)


def failing(text, stages):
    return engine_exam.Result(False, [engine_exam.Row(1, "s1", "guard", False, "guard", "it broke")], calls=1)


def fan(agent, **over):
    d = dict(copy.deepcopy(plugs.FAN), agent=agent)
    d.update(over)
    return d


class Siblings(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.new = plugs.load(fan("fan_new", kind="fans", owner="demo"), self)
        # the sibling shares no field, so only being a sibling puts it before the waterer (same field)
        self.sib = plugs.load(fan("fan_old", kind="fans", owner="demo", fields=["cooling"]), self)
        self.waterer = plugs.load(plugs.WATERER, self)
        self.ledger = plugs.load(plugs.LEDGER, self)
        self.sib_lessons = Lessons(self.db, self.sib, judge=always_low)
        self.kept = kept_lesson(self.sib_lessons, THEIRS, ["all"], yes_by="owner")

    def night(self, exam=None, others=None):
        self.mine = Lessons(self.db, self.new, judge=always_low, exam=exam)
        s = Study(self.db, self.new, proposer=fk.Proposer(), tagger=fk.Tagger(),
                  fit=fk.Fit({THEIRS: "fully", FAR: "partly"}), adapter=fk.Adapter({THEIRS: MINE, FAR: FAR_MINE}),
                  others=[self.waterer, self.ledger, self.sib] if others is None else others, lessons=self.mine)
        return s.run(fk.SINCE, UNTIL, now=NOW)

    def mine_by_text(self):
        return {les["text"]: les for les in self.mine.mine()}

    def test_a_sibling_is_read_first(self):
        rep = self.night(exam=passing)
        self.assertEqual([(a["agent"], a["sibling"]) for a in rep["across"]],
                         [("fan_old", True), ("waterer", False), ("ledger", False)])

    def test_the_siblings_kept_lesson_goes_on_trial_through_the_gate(self):
        rep = self.night(exam=passing)
        les = self.mine_by_text()[MINE]
        self.assertEqual((les["state"], les["source_lesson_id"]), ("trying", self.kept))
        self.assertTrue(self.mine.exam_of(les["id"])["passed"])
        self.assertEqual(rep["cards"][0]["from"], {"agent": "fan_old", "fit": "fully", "lesson": self.kept})
        self.assertNotIn(study.NO_GATE, rep["notes"])

    def test_a_gate_fail_holds_it_for_a_yes(self):
        self.night(exam=failing)
        les = self.mine_by_text()[MINE]
        self.assertEqual(les["state"], "waiting")
        self.assertIsNone(self.mine.trial(les["id"]))

    def test_with_no_gate_a_siblings_line_waits_for_a_yes(self):
        """Nothing a sibling kept goes live here without the gate; another agent's line keeps its old way."""
        kept_lesson(Lessons(self.db, self.ledger, judge=always_low), FAR, ["all"], yes_by="owner")
        rep = self.night(exam=None)
        got = self.mine_by_text()
        self.assertEqual(got[MINE]["state"], "waiting")
        self.assertIsNone(self.mine.trial(got[MINE]["id"]))
        self.assertIn(study.NO_GATE, rep["notes"])
        self.assertEqual(got[FAR_MINE]["state"], "trying")  # not a sibling: step 6 as before
        self.assertNotIn("kept", {les["state"] for les in got.values()})

    def test_who_is_a_sibling(self):
        other_owner = plugs.load(fan("fan_far", kind="fans", owner="other"), self)
        other_kind = plugs.load(fan("fan_odd", kind="vents", owner="demo"), self)
        no_owner = plugs.load(fan("fan_lone", kind="fans"), self)
        no_owner_too = plugs.load(fan("fan_lone2", kind="fans"), self)
        self.assertTrue(study.sibling(self.new, self.sib))
        self.assertFalse(study.sibling(self.new, self.new))
        for o in (other_owner, other_kind, no_owner, self.waterer):
            with self.subTest(other=o.agent):
                self.assertFalse(study.sibling(self.new, o))
        self.assertFalse(study.sibling(no_owner, no_owner_too))  # no owner named: never siblings (item 51)

    def test_another_owners_agent_of_the_kind_is_not_read_first_or_gated(self):
        far = plugs.load(fan("fan_far", kind="fans", owner="other", fields=["cooling"]), self)
        kept_lesson(Lessons(self.db, far, judge=always_low), FAR, ["all"], yes_by="owner")
        rep = self.night(exam=None, others=[self.waterer, far])
        self.assertEqual([(a["agent"], a["sibling"]) for a in rep["across"]], [("waterer", False), ("fan_far", False)])


if __name__ == "__main__":
    unittest.main()
