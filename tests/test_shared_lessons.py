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
from unittest import mock

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


def down(messages, tools):
    """A model step that fails, as a host that is down does."""
    raise RuntimeError("down")


class SharedLessons(unittest.TestCase):
    kind = "fans"

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "shared"
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.new, self.folder = plugs.owned(fan("fan_new", kind=self.kind, owner="demo"), self)
        self.pool = shared.Pool(self.kind, self.root)

    def agent(self, name, **over):
        return plugs.load(fan(name, kind=self.kind, **over), self)

    def seen_at(self, *owners, text=PATTERN):
        for n, o in enumerate(owners):
            self.pool.add(shared.LESSON, text if n == 0 else NEAR, o, f"lesson:x:{n}")
        return self.pool.shared(shared.LESSON)[0]["id"] if len(set(owners)) >= 2 else None

    def night(self, exam=None, others=(), writer=None, fit=None, give=shared.GIVE, limit=study.ANSWER_MAX):
        self.mine = Lessons(self.db, self.new, judge=always_low, exam=exam)
        self.fit = fit or fk.Fit({PATTERN: "fully", SIB: "fully", FAR: "partly"})
        self.link = shared.Link.for_agent(self.new, self.folder, writer or writer_of(), self.root, give=give)
        s = Study(self.db, self.new, proposer=fk.Proposer(), tagger=fk.Tagger(), fit=self.fit,
                  adapter=fk.Adapter({PATTERN: MINE, SIB: SIB_MINE, FAR: FAR_MINE}), others=list(others),
                  lessons=self.mine, shared=self.link, limit=limit)
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

    def test_every_pattern_not_taken_is_read_with_no_cap(self):  # DECISIONS item 98
        self.seen_at("north", "south")
        for n, o in enumerate(("north", "south")):
            self.pool.add(shared.LESSON, FILTERS, o, f"lesson:y:{n}")
        self.assertEqual(len(self.pool.shared(shared.LESSON)), 2)
        self.assertEqual(len(self.night(exam=passing, limit=1)["shared"]["lessons"]), 2)

    def test_a_pattern_seen_at_one_owner_is_not_read(self):
        self.seen_at("north", "north")
        rep = self.night(exam=passing)
        self.assertEqual(rep["shared"]["read"], 0)
        self.assertNotIn(MINE, self.by_text())
        self.assertEqual(self.fit.calls, [])

    def test_a_pattern_its_own_owner_gave_is_not_read_back(self):
        self.seen_at(shared.owner_id(self.folder), "south")
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
                  shared=shared.Link.for_agent(self.new, self.folder, writer_of(), self.root))
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

    def test_a_writer_that_fails_is_asked_once_a_night(self):
        mine = Lessons(self.db, self.new, judge=always_low)
        for text in ("Explain the quiet setting first when the grower asks about noise twice.",
                     "Show the filter choices before the price when the grower asks about dust."):
            kept_lesson(mine, text, ["all"], yes_by="owner")
        model = FakeModel(down, say(json.dumps({"pattern": GIVEN})))
        rep = self.night(exam=passing, writer=shared.Writer(model=model))
        self.assertEqual(len(model.calls), 1)
        self.assertEqual([g["why"] for g in rep["shared"]["given"]], ["the writer failed (PartError)"])

    def test_a_lesson_the_writer_gives_no_line_for_never_holds_back_the_next(self):
        # review crossowner round 3, item 1: the first lesson always gets no line; the second is still
        # given the same night, and the first is asked again one more night, then kept as given
        mine = Lessons(self.db, self.new, judge=always_low)
        stuck_text = "Explain the quiet setting first when the grower asks about noise twice."
        stuck = kept_lesson(mine, stuck_text, ["all"], yes_by="owner")
        later = kept_lesson(mine, "Show the filter choices before the price when the grower asks about dust.",
                            ["all"], yes_by="owner")
        asked = []

        def writer(what, kind, data):
            asked.append(data["lesson"])
            return None if data["lesson"] == stuck_text else GIVEN

        rep = self.night(exam=passing, writer=writer, give=2)
        given = {g["lesson"]: g for g in rep["shared"]["given"]}
        self.assertEqual(len(asked), 2)
        self.assertEqual(given[stuck]["why"], "the writer gave no line; asked again another night")
        self.assertIsNotNone(given[later]["pattern"])
        rep = self.night(exam=passing, writer=writer, give=2)
        self.assertEqual(asked[2:], [stuck_text])
        self.assertEqual([g["why"] for g in rep["shared"]["given"]], ["the writer gave no line; not asked again"])
        rep = self.night(exam=passing, writer=writer, give=2)
        self.assertEqual((len(asked), rep["shared"]["given"]), (3, []))

    def test_a_lesson_still_on_trial_is_not_given(self):
        mine = Lessons(self.db, self.new, judge=always_low)
        lid = mine.add("Explain the quiet setting first when the grower asks about noise twice.", ["all"],
                       yes_by="owner", skip_exam=True)
        self.assertEqual(mine.get(lid)["state"], "trying")
        rep = self.night(exam=passing)  # the writer has no script: asking it would be a row here
        self.assertEqual(rep["shared"]["given"], [])

    def test_a_lesson_from_the_pool_is_not_given_back(self):
        self.seen_at("north", "south")
        self.night(exam=passing)
        les = self.by_text()[MINE]
        self.assertTrue(self.mine.keep(les["id"]))
        rep = self.night(exam=passing)  # the writer has no script: asking it would fail the run
        self.assertEqual(rep["shared"]["given"], [])

    def pooled_kept(self):
        """A lesson this agent took from a pattern two other owners gave, kept: its row."""
        self.seen_at("north", "south")
        self.night(exam=passing)
        les = self.by_text()[MINE]
        self.assertTrue(self.mine.keep(les["id"]))
        return les

    def assert_not_given_back(self, rep):
        self.assertEqual(rep["shared"]["given"], [])  # the writer has no script: asking it is a row here
        self.assertEqual([len(set(p["owners"])) for p in self.pool.shared(shared.LESSON)], [2])

    def test_a_pooled_lesson_brought_back_and_kept_is_not_given_back(self):
        les = self.pooled_kept()
        self.assertTrue(self.mine.pull(les["id"], "too pushy", now=NOW))
        back = self.mine.bring_back(les["id"], "the user", now=NOW)
        self.assertTrue(self.mine.keep(back))
        self.assert_not_given_back(self.night(exam=passing))

    def test_a_pooled_lesson_edited_and_kept_is_not_given_back(self):
        from reflection import morning
        les = self.pooled_kept()
        new = morning.person_line(self.mine, "Explain the quiet setting first when the grower asks about noise.",
                                  les["stages"], by="the user", old=les, now=NOW)
        self.assertTrue(self.mine.pull(les["id"], f"{morning.EDITED}the user into lesson {new}", now=NOW))
        self.mine.start_turns(NOW)
        self.assertTrue(self.mine.keep(new))
        self.assert_not_given_back(self.night(exam=passing))

    def sibling_night(self, les, writer):
        """A sibling of the same owner copies kept lesson les, keeps it and runs its night: the report."""
        folder = self.folder.parent / "fan_sib"
        folder.mkdir()
        (folder / "plug.json").write_text(json.dumps(fan("fan_sib", kind=self.kind, owner="demo")), encoding="utf-8")
        sib = plugs.plug.load(folder / "plug.json")
        theirs = Lessons(self.db, sib, judge=always_low)
        copied = theirs.borrow(les["id"], les["stages"], now=NOW)
        self.assertTrue(theirs.keep(copied))
        link = shared.Link.for_agent(sib, folder, writer, self.root)
        self.assertTrue(link.owner)
        return Study(self.db, sib, proposer=fk.Proposer(), tagger=fk.Tagger(), fit=fk.Fit({}), adapter=fk.Adapter({}),
                     lessons=theirs, shared=link).run(fk.SINCE, UNTIL, now=NOW)

    def test_a_pooled_lesson_a_sibling_copied_is_not_given_back_by_the_sibling(self):
        self.assert_not_given_back(self.sibling_night(self.pooled_kept(), writer_of()))

    def test_a_copied_lesson_that_never_came_from_the_pool_is_still_given(self):
        mine = Lessons(self.db, self.new, judge=always_low)
        lid = kept_lesson(mine, "Explain the quiet setting first when the grower asks about noise twice.", ["all"],
                          yes_by="owner")
        rep = self.sibling_night(mine.get(lid), writer_of(GIVEN))
        self.assertEqual(len(rep["shared"]["given"]), 1)
        self.assertIsNotNone(rep["shared"]["given"][0]["pattern"])

    def test_a_chain_longer_than_the_lineage_read_is_not_given(self):
        mine = Lessons(self.db, self.new, judge=always_low)
        lid = kept_lesson(mine, "Explain the quiet setting first when the grower asks about noise twice.", ["all"],
                          yes_by="owner")
        with mock.patch.object(study, "LINEAGE", 1):
            rep = self.sibling_night(mine.get(lid), writer_of())
        self.assertEqual(rep["shared"]["given"], [])

    def test_the_night_runner_reads_the_pool_and_its_text_names_it(self):
        self.seen_at("north", "south")
        link = shared.Link.for_agent(self.new, self.folder, writer_of(), self.root)
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
        return plugs.owned(d, self)

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
                plug, folder = self.plug_of(kind)
                db = Db(":memory:")
                self.addCleanup(db.close)
                mine = Lessons(db, plug, judge=always_low)
                stages = list(plug.stages)[:1] or ["all"]
                s = Study(db, plug, proposer=fk.Proposer(), tagger=fk.Tagger(),
                          fit=fk.Fit({PATTERN: "partly", GIVEN: "fully"}),
                          adapter=fk.Adapter({PATTERN: MINE, GIVEN: "never this"}, stages=stages), lessons=mine,
                          shared=shared.Link.for_agent(plug, folder, writer_of(), root))
                rep = s.run(fk.SINCE, UNTIL, now=NOW)
                got = {les["text"]: les for les in mine.mine()}
                self.assertEqual(set(got), {MINE})
                self.assertEqual(got[MINE]["state"], "waiting")  # no gate on these lessons
                self.assertIn(study.POOL_NO_GATE, rep["notes"])


class RemintedOwnerId(unittest.TestCase):
    """Red team crossowner round 2, item 2: deleting an owner's owner-id file makes a new id. What was
    given is kept by the lesson's own id, so the same lesson is not given again, and the owner's name
    with its new id gives nothing until the operator clears the name."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "shared"
        self.plug, self.folder = plugs.owned(fan("fan_a", kind="fans", owner="demo"), self)

    def link(self, *lines):
        return shared.Link.for_agent(self.plug, self.folder, writer_of(*lines), self.root)

    def test_a_deleted_owner_id_neither_gives_a_lesson_again_nor_counts_as_a_second_owner(self):
        first = self.link(PATTERN)
        self.assertIsNotNone(first.give_lesson("fan_a", {"id": 7, "text": GIVEN})["pattern"])
        (self.folder.parent / shared.OWNER_ID_FILE).unlink()
        asked = []
        again = shared.Link.for_agent(self.plug, self.folder, lambda *a: asked.append(a) or NEAR, self.root)
        self.assertNotEqual(again.owner, first.owner)
        self.assertEqual(again.give_lesson("fan_a", {"id": 7, "text": GIVEN})["why"], "given before")
        held = again.give_lesson("fan_a", {"id": 8, "text": FILTERS})
        self.assertEqual(held["why"], shared.HELD)
        self.assertFalse(held.get("asked"))
        self.assertEqual(asked, [])  # held before the writer is asked
        self.assertEqual(shared.Pool("fans", self.root).shared(shared.LESSON), [])
        # the same name and id through add() itself is held too (two nights at once)
        got, why = again.pool.add(shared.LESSON, NEAR, again.owner, "lesson:9", name="demo")
        self.assertEqual((got, why), (None, [shared.HELD]))
        self.assertEqual(shared.clear_owner(self.root, "demo"), ["fans"])
        cleared = self.link(NEAR).give_lesson("fan_a", {"id": 8, "text": FILTERS})
        # review crossowner round 3, item 4: the new id takes the old one's place; one owner, not two
        self.assertEqual(cleared["owners"], 1)
        pool = shared.Pool("fans", self.root)
        self.assertEqual([p["owners"] for p in pool.patterns], [[pool.owner_hash(again.owner)]])
        self.assertEqual(pool.shared(shared.LESSON), [])
        self.assertNotIn(pool.owner_hash(first.owner), (self.root / "patterns-fans.json").read_text())
        self.assertEqual(pool.cleared, {})

    def test_a_cleared_name_takes_its_old_hash_place_on_every_pattern_never_twice(self):
        pool = shared.Pool("fans", self.root)
        pool.add(shared.LESSON, PATTERN, "owner-id:old", "k1", name="demo")
        pool.add(shared.LESSON, GIVEN, "owner-id:old", "k2", name="demo")
        pool.add(shared.LESSON, GIVEN, "owner-id:new", "k3")  # the new id on one pattern already, no name
        self.assertEqual(shared.clear_owner(self.root, "demo"), ["fans"])
        pool = shared.Pool("fans", self.root)
        pool.add(shared.LESSON, FILTERS, "owner-id:new", "k4", name="demo")
        new = pool.owner_hash("owner-id:new")
        self.assertEqual([p["owners"] for p in shared.Pool("fans", self.root).patterns], [[new], [new], [new]])

    def given_under(self, owner):
        pool = shared.Pool("fans", self.root)
        pool.add(shared.LESSON, PATTERN, owner, "k1", name="demo")
        return self.root / "patterns-fans.json"

    def test_a_name_row_moved_to_another_owner_hash_reads_broken(self):
        # review crossowner round 3, item 6 (R-B9): the name's seal is checked, so a name moved by hand
        # to a new owner id's hash (to give under it without the operator) breaks the read
        path = self.given_under("owner-id:old")
        data = json.loads(path.read_text())
        new = shared.Pool("fans", self.root).owner_hash("owner-id:new")
        row = data["names"][0]
        data["names"] = [row[:32] + new + row[64:]]
        path.write_text(json.dumps(data))
        pool = shared.Pool("fans", self.root)
        self.assertTrue(pool.broken)
        self.assertEqual(pool.ready("k2", "owner-id:new", "demo"), shared.BROKEN)

    def test_clear_on_a_broken_pool_is_refused_and_writes_nothing(self):
        # review crossowner round 3, item 6 (R-B12): rows that fail their seals, names still good
        path = self.given_under("owner-id:old")
        data = json.loads(path.read_text())
        data["patterns"][0]["owners"] = [o[:32] + "0" * 16 for o in data["patterns"][0]["owners"]]
        path.write_text(json.dumps(data))
        before = path.read_bytes()
        with self.assertRaises(shared.Refused):
            shared.clear_owner(self.root, "demo")
        self.assertEqual(path.read_bytes(), before)
        path.write_text("{cut short", encoding="utf-8")
        with self.assertRaises(shared.Refused):
            shared.clear_owner(self.root, "demo")
        self.assertEqual(path.read_text(encoding="utf-8"), "{cut short")

    def test_a_cleared_row_whose_seal_fails_reads_broken(self):
        shared.Pool("fans", self.root).add(shared.LESSON, PATTERN, "owner-id:old", "k1", name="demo")
        shared.clear_owner(self.root, "demo")
        path = self.root / "patterns-fans.json"
        data = json.loads(path.read_text())
        row = data["cleared"][0]
        data["cleared"] = [row[:32] + "0" * 32 + row[64:]]  # moved to another owner hash by hand
        path.write_text(json.dumps(data))
        self.assertTrue(shared.Pool("fans", self.root).broken)


if __name__ == "__main__":
    unittest.main()
