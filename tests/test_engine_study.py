"""Step 5 part B1: one night's study for one agent, on the made-up plugs. It counts every
result kind it read first; a pending case is no loss and a case with an outside cause is
left out; the model parts only propose and tag, and the code counts and decides with the
gap rule; each winner is written through the agent's own risk check, at most a few new low
risk lessons a night. The model parts are fakes here."""
import random
import unittest

from engine import risk, study
from engine.lessons import DAY, Lessons
from engine.log import Log
from engine.study import Study, chance_better
from kit.db import Db
from tests import plugs
from tests import study_fakes as fk


def always_low(text, high_about, low_about):
    return risk.LOW


class Night(unittest.TestCase):
    """A waterer with its log, its lessons and a study made from fakes."""

    data = plugs.WATERER

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(self.data, self)
        self.log = Log(self.db, self.plug)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)

    def study(self, *candidates, tagger=None, **kw):
        self.proposer = kw.pop("proposer", None) or fk.Proposer(*candidates)
        self.tagger = tagger or fk.Tagger()
        return Study(self.db, self.plug, proposer=self.proposer, tagger=self.tagger, lessons=self.lessons, **kw)

    def run_night(self, *candidates, **kw):
        return self.study(*candidates, **kw).run(fk.SINCE, fk.UNTIL, now=fk.NOW)


class CountsFirst(Night):
    def test_every_result_kind_read_is_counted(self):
        fk.beds(self.log)
        fk.case(self.log, "dry1", "skip", "skipped", "wilted", stage="grown")
        self.log.act("wet1", "water", result="ran_off", at=fk.UNTIL - 2 * DAY)  # no deciding result yet: pending
        rep = self.run_night()
        self.assertEqual(rep["agent"], "waterer")
        self.assertEqual(rep["read"]["cases"], 22)
        self.assertEqual(rep["read"]["rows"], 43)
        self.assertEqual(rep["read"]["actions"], {"water": 21, "skip": 1})
        self.assertEqual(rep["read"]["results"],
                         {"soaked": 20, "ran_off": 1, "skipped": 1, "grew": 10, "wilted": 11})
        self.assertEqual(rep["decided"], {"good": 10, "bad": 11})
        self.assertEqual(rep["pending"], 1)

    def test_a_declared_result_never_seen_is_counted_as_zero(self):
        fk.case(self.log, "b1", "water", "soaked", "grew")
        rep = self.run_night()
        self.assertEqual(rep["read"]["results"], {"soaked": 1, "ran_off": 0, "skipped": 0, "grew": 1, "wilted": 0})

    def test_lessons_given_are_counted_by_case(self):
        tone = self.lessons.propose("Visit the shady beds first.", ["all"], now=fk.T0, sources=[])
        fk.case(self.log, "b1", "water", "soaked", "grew", lessons=[tone])
        fk.case(self.log, "b2", "water", "soaked", "grew", lessons=[tone])
        fk.case(self.log, "b3", "water", "soaked", "grew")
        self.assertEqual(self.run_night()["read"]["lessons_given"], {tone: 2})

    def test_a_pending_case_is_not_a_loss(self):
        fk.beds(self.log)
        for n in range(6):  # watered late, no slow result yet, so pending
            fk.case(self.log, f"new{n}", "water", "soaked", at=fk.UNTIL - 2 * DAY, stage="seedling", early=False)
        rep = self.run_night(fk.EARLY)
        self.assertEqual(rep["pending"], 6)
        self.assertEqual(rep["decided"], {"good": 10, "bad": 10})
        cand = rep["candidates"][0]
        self.assertEqual((cand["without"]["cases"], cand["without"]["good"]), (10, 2))
        views = [v for call in self.tagger.calls for v in call["cases"]]
        views += [v for call in self.proposer.calls for v in call["sample"]]
        notes = {s["detail"].get("note") for v in views for s in v["steps"] if s.get("detail")}
        self.assertEqual(len(notes), 20)  # the settled beds only, each with its own note
        self.assertNotIn(None, notes)     # no pending bed (they have no note) reached a model part

    def test_a_case_with_no_deciding_result_stays_pending_whatever_its_age(self):
        fk.beds(self.log)
        for n in range(8):  # 20 days old, twice the plug's 10 days: no timer settles them (item 66)
            fk.case(self.log, f"old{n}", "water", "soaked", at=fk.UNTIL - 20 * DAY, stage="seedling", early=False)
        rep = self.run_night(fk.EARLY)
        self.assertEqual(rep["decided"], {"good": 10, "bad": 10})
        self.assertEqual(rep["pending"], 8)
        cand = rep["candidates"][0]
        self.assertEqual((cand["without"]["cases"], cand["without"]["good"]), (10, 2))

    def test_a_result_after_the_window_end_is_not_known_yet(self):
        fk.case(self.log, "b1", "water", "soaked", at=fk.UNTIL - DAY, stage="seedling")
        self.log.result("b1", "grew", at=fk.UNTIL + DAY)
        rep = self.run_night()
        self.assertEqual((rep["pending"], rep["decided"]["good"], rep["read"]["results"]["grew"]), (1, 0, 0))

    def test_a_case_is_read_when_any_of_its_rows_falls_in_the_window(self):
        fk.case(self.log, "old", "water", "soaked", at=fk.SINCE - 2 * DAY, stage="seedling")
        self.log.result("old", "grew", at=fk.SINCE + DAY)
        fk.case(self.log, "gone", "water", "soaked", "grew", at=fk.SINCE - 10 * DAY)
        rep = self.run_night()
        self.assertEqual((rep["read"]["cases"], rep["read"]["rows"], rep["decided"]["good"]), (1, 2, 1))

    def test_a_case_with_an_outside_cause_is_left_out_with_its_cause(self):
        fk.beds(self.log)
        for n in range(5):  # watered early, wilted from frost: not the agent's doing
            fk.case(self.log, f"frost{n}", "water", "soaked", "wilted", cause="frost", stage="seedling", early=True)
        fk.case(self.log, "pests1", "water", "soaked", "wilted", cause="pests", stage="seedling", early=True)
        rep = self.run_night(fk.EARLY)
        self.assertEqual(rep["left_out"]["count"], 6)
        self.assertEqual(rep["left_out"]["by_cause"], {"frost": 5, "pests": 1})
        self.assertIn({"case": "pests1", "result": "wilted", "causes": ["pests"]}, rep["left_out"]["cases"])
        self.assertEqual(rep["decided"], {"good": 10, "bad": 10})
        cand = rep["candidates"][0]
        self.assertEqual((cand["with"]["cases"], cand["with"]["good"]), (10, 8))
        self.assertEqual(len(self.tagger.calls[0]["cases"]), 20)

    def test_the_window_must_have_a_length(self):
        with self.assertRaises(ValueError):
            self.study().run(fk.UNTIL, fk.SINCE)


class Patterns(Night):
    def test_a_clear_pattern_becomes_a_lesson_on_trial_with_its_card(self):
        fk.beds(self.log)
        rep = self.run_night(fk.EARLY)
        self.assertEqual(len(rep["cards"]), 1)
        card = rep["cards"][0]
        les = self.lessons.get(card["lesson_id"])
        self.assertEqual((les["text"], les["state"], les["risk"], les["share"], les["stages"]),
                         (fk.EARLY["lesson"], "trying", "low", 0.5, ["all"]))
        self.assertEqual(les["ends_at"], fk.NOW + 7 * DAY)
        self.assertEqual(card["change"], fk.EARLY["lesson"])
        self.assertEqual(card["situation"], fk.EARLY["situation"])
        self.assertEqual(card["moves"], {"result": "grew", "shows_in_days": [3.0, 10.0]})
        self.assertEqual(card["must_not_worsen"],
                         {"results": ["ran_off"], "about": "Water that runs off is wasted and washes the soil away."})
        self.assertEqual(card["cases"], {"with": 10, "without": 10, "total": 20, "good_with": 8, "good_without": 2})
        self.assertAlmostEqual(card["sure"], chance_better(8, 10, 2, 10), places=6)
        self.assertGreater(card["sure"], 0.99)
        self.assertEqual((card["state"], card["risk"], card["from"]), ("trying", "low", None))
        self.assertEqual((card["level"], card["accept_high"]), ("careful", False))
        self.assertEqual(rep["candidates"][0]["verdict"], study.LESSON)
        self.assertEqual(rep["candidates"][0]["lesson_id"], card["lesson_id"])

    def test_the_source_text_lists_the_counts(self):
        fk.beds(self.log)
        card = self.run_night(fk.EARLY)["cards"][0]
        src = self.lessons.get(card["lesson_id"])["source"]
        self.assertEqual(card["source"], src)
        for part in ("night study", "8 of 10", "2 of 10", "grew", fk.EARLY["pattern"]):
            self.assertIn(part, src)
        self.assertNotIn("\N{EM DASH}", src)
        self.assertNotIn("\N{EN DASH}", src)

    def test_a_pattern_that_hurts_makes_a_lesson_to_avoid_it(self):
        fk.beds(self.log, early_good=0, early_bad=0, late_good=0, late_bad=0)
        for n in range(10):
            fk.case(self.log, f"bare{n}", "water", "soaked", "grew" if n < 2 else "wilted", stage="seedling", bare=True)
            fk.case(self.log, f"mulch{n}", "water", "soaked", "grew" if n < 8 else "wilted", stage="seedling",
                    bare=False)
        rep = self.run_night(fk.MULCH)
        card = rep["cards"][0]
        self.assertEqual((card["change"], card["stages"]), (fk.MULCH["lesson"], ["seedling"]))
        self.assertAlmostEqual(card["sure"], chance_better(8, 10, 2, 10), places=6)
        self.assertEqual(card["cases"]["good_with"], 2)

    def test_the_wrong_direction_makes_no_lesson(self):
        fk.beds(self.log)
        rep = self.run_night(fk.candidate(fk.EARLY, helps=False, lesson="Water the beds late in the day."))
        self.assertEqual(rep["cards"], [])
        self.assertEqual(rep["candidates"][0]["verdict"], study.NO_GAP)
        self.assertLess(rep["candidates"][0]["chance"], 0.01)
        self.assertEqual(self.lessons.mine(), [])

    def test_no_clear_gap_makes_no_lesson(self):
        fk.beds(self.log, early_good=6, early_bad=4, late_good=5, late_bad=5)
        rep = self.run_night(fk.EARLY)
        cand = rep["candidates"][0]
        self.assertEqual(cand["verdict"], study.NO_GAP)
        self.assertAlmostEqual(cand["chance"], chance_better(6, 10, 5, 10), places=6)
        self.assertLess(cand["chance"], study.CHANCE)
        self.assertEqual(self.lessons.mine(), [])

    def test_too_few_cases_on_a_side_makes_no_lesson(self):
        fk.beds(self.log, early_good=4, early_bad=0, late_good=0, late_bad=10)
        rep = self.run_night(fk.EARLY)
        self.assertEqual(rep["candidates"][0]["verdict"], study.FEW_CASES)
        self.assertGreater(rep["candidates"][0]["chance"], 0.99)  # clear, but four cases are too few
        self.assertEqual(self.lessons.mine(), [])

    def test_too_few_sources_makes_no_lesson(self):
        data = plugs.changed(plugs.WATERER, source={"about": "The gardener who asked.", "known_by": "row"})
        plug = plugs.load(data, self)
        log = Log(self.db, plug)
        lessons = Lessons(self.db, plug, judge=always_low)
        for n in range(20):  # every early bed comes from one of two gardeners
            early = n < 10
            good = n < 8 or n >= 18
            fk.case(log, f"bed{n}", "water", "soaked", "grew" if good else "wilted", stage="seedling", early=early,
                    source=f"gardener{n % 2}" if early else f"gardener{n}")
        rep = Study(self.db, plug, proposer=fk.Proposer(fk.EARLY), tagger=fk.Tagger(),
                    lessons=lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        cand = rep["candidates"][0]
        self.assertEqual((cand["with"]["sources"], cand["without"]["sources"]), (2, 10))
        self.assertEqual(cand["verdict"], study.FEW_SOURCES)
        self.assertEqual(lessons.mine(), [])

    def test_three_sources_on_each_side_are_enough(self):
        data = plugs.changed(plugs.WATERER, source={"about": "The gardener who asked.", "known_by": "row"})
        plug = plugs.load(data, self)
        log = Log(self.db, plug)
        for n in range(20):
            fk.case(log, f"bed{n}", "water", "soaked", "grew" if (n < 8 or n >= 18) else "wilted", stage="seedling",
                    early=n < 10, source=f"gardener{n % 3}")
        rep = Study(self.db, plug, proposer=fk.Proposer(fk.EARLY), tagger=fk.Tagger(),
                    lessons=Lessons(self.db, plug, judge=always_low)).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        self.assertEqual(rep["candidates"][0]["verdict"], study.LESSON)

    def test_high_risk_waits_for_a_yes(self):
        fk.beds(self.log)
        rep = self.run_night(fk.candidate(fk.EARLY, lesson="Spray pesticide on the beds early in the morning."))
        card = rep["cards"][0]
        self.assertEqual((card["risk"], card["state"], card["waits_for"]), ("high", "waiting", None))
        self.assertIn("chemicals: pesticide", card["risk_why"])
        self.assertEqual((card["level"], card["accept_high"]), (None, False))
        self.assertEqual(rep["switches"], {"level": "careful", "share": 0.5, "days": 7,
                                           "accept_high": {"on": False, "by": None, "until": None, "ran_out": False}})

    def test_the_stub_judge_makes_every_lesson_wait(self):
        fk.beds(self.log)
        self.lessons = Lessons(self.db, self.plug)
        card = self.run_night(fk.EARLY)["cards"][0]
        self.assertEqual((card["risk"], card["state"]), ("high", "waiting"))

    def test_the_case_texts_are_the_sources_so_copied_words_are_caught(self):
        fk.beds(self.log, note="the old gardener said keep the hose low by the fence")
        rep = self.run_night(fk.candidate(fk.EARLY, lesson="Keep the hose low by the fence, early in the morning."))
        card = rep["cards"][0]
        self.assertEqual((card["risk"], card["state"]), ("high", "waiting"))
        self.assertIn("core: copied from source", card["risk_why"])

    def test_the_model_never_decides_the_numbers(self):
        fk.beds(self.log)
        def odd(view):
            return view["steps"][0]["detail"]["note"] in ("round 1", "round 2", "round 3")

        greedy = fk.candidate(fk.EARLY, chance=0.99, cases=500, verdict="lesson", sure=1.0)
        rep = self.run_night(greedy, tagger=fk.Tagger(odd=odd))
        cand = rep["candidates"][0]
        self.assertEqual(cand["unknown"], 3)
        self.assertEqual(cand["with"]["cases"] + cand["without"]["cases"], 17)
        card = rep["cards"][0]
        self.assertEqual(card["cases"]["total"], 17)
        self.assertLess(card["sure"], 1.0)

    def test_the_tagger_never_sees_the_deciding_result(self):
        fk.beds(self.log)
        self.run_night(fk.EARLY)
        for view in self.tagger.calls[0]["cases"]:
            self.assertNotIn("deciding", view)
            self.assertNotIn("good", view)
            for step in view["steps"]:
                self.assertNotIn(step.get("result"), ("grew", "wilted"))
        sample = self.proposer.calls[0]["sample"]
        self.assertTrue(all(view["deciding"] in ("grew", "wilted") for view in sample))

    def test_no_case_id_or_source_goes_to_the_model_parts(self):
        fk.beds(self.log, prefix="secretbed")
        self.run_night(fk.EARLY)
        shown = repr(self.proposer.calls) + repr(self.tagger.calls)
        self.assertNotIn("secretbed", shown)

    def test_the_proposer_reads_a_small_sample_with_good_and_bad(self):
        fk.beds(self.log, early_good=30, early_bad=5, late_good=5, late_bad=30)
        self.run_night(fk.EARLY)
        call = self.proposer.calls[0]
        self.assertLessEqual(len(call["sample"]), study.SAMPLE)
        good = [v for v in call["sample"] if v["good"]]
        self.assertEqual((len(good), len(call["sample"]) - len(good)), (study.SAMPLE // 2, study.SAMPLE // 2))
        self.assertEqual((call["limit"], call["known"]), (study.ANSWER_MAX, []))

    def test_only_good_or_only_bad_cases_ask_no_proposer(self):
        fk.beds(self.log, early_bad=0, late_bad=0)
        rep = self.run_night(fk.EARLY)
        self.assertEqual((self.proposer.calls, rep["candidates"], rep["cards"]), ([], [], []))
        self.assertTrue(rep["notes"])

    def test_one_answer_past_the_size_bound_is_named_never_kept_quietly(self):
        fk.beds(self.log)
        many = [fk.candidate(fk.EARLY, pattern=f"pattern {n}", lesson=f"Lesson {n}.") for n in range(9)]
        marks = {c["pattern"]: "early" for c in many}
        rep = self.run_night(*many, tagger=fk.Tagger(marks), limit=2)
        self.assertEqual(len(self.tagger.calls), 2)
        self.assertEqual(len(rep["candidates"]), 2)
        self.assertEqual([d["candidate"] for d in rep["dropped"]], [f"pattern {n}" for n in range(2, 9)])
        self.assertEqual({d["why"] for d in rep["dropped"]}, {study.past_bound(2)})

    def test_a_bad_candidate_is_dropped_and_said(self):
        fk.beds(self.log)
        bad = ["just a line", fk.candidate(fk.EARLY, stages=["flowering"]),
               fk.candidate(fk.EARLY, lesson="two\nlines"), fk.candidate(fk.EARLY, helps="yes"),
               fk.candidate(fk.EARLY, lesson="x" * 301), {"pattern": fk.EARLY["pattern"]}]
        rep = self.run_night(*bad, fk.EARLY, limit=10)
        self.assertEqual(len(rep["dropped"]), 6)
        self.assertTrue(all(d["why"] for d in rep["dropped"]))
        self.assertEqual(len(rep["cards"]), 1)

    def test_the_same_pattern_twice_is_tagged_once(self):
        fk.beds(self.log)
        rep = self.run_night(fk.EARLY, fk.candidate(fk.EARLY, lesson="Water early."))
        self.assertEqual(len(self.tagger.calls), 1)
        self.assertEqual(len(rep["cards"]), 1)

    def test_a_failing_proposer_or_tagger_makes_no_lesson(self):
        fk.beds(self.log)
        rep = self.run_night(proposer=fk.Proposer(fk.EARLY, fail=True))
        self.assertEqual((rep["cards"], self.lessons.mine()), ([], []))
        self.assertTrue(any("proposer" in n for n in rep["notes"]))
        rep = self.run_night(fk.EARLY, tagger=fk.Tagger(fail=True))
        self.assertEqual((rep["cards"], self.lessons.mine()), ([], []))
        self.assertEqual(rep["candidates"][0]["verdict"], study.FEW_CASES)
        self.assertTrue(any("tagger" in n for n in rep["notes"]))

    def test_a_proposer_that_answers_no_list_makes_no_lesson(self):
        fk.beds(self.log)

        def odd(plug, sample, limit, known):
            return {"pattern": "x"}
        rep = self.study(proposer=odd).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        self.assertEqual((rep["candidates"], rep["cards"]), ([], []))
        self.assertTrue(rep["notes"])

    def test_a_lesson_already_there_is_not_written_twice(self):
        fk.beds(self.log)
        first = self.run_night(fk.EARLY)["cards"][0]["lesson_id"]
        rep = self.run_night(fk.candidate(fk.EARLY, lesson="  water the beds EARLY in the morning. "))
        self.assertEqual(rep["cards"], [])
        self.assertEqual(rep["candidates"][0]["verdict"], study.KNOWN)
        self.assertEqual([les["id"] for les in self.lessons.mine()], [first])
        self.assertEqual(self.proposer.calls[0]["known"], [fk.EARLY["lesson"]])

    def test_a_pulled_lesson_is_never_written_again(self):
        fk.beds(self.log)
        first = self.run_night(fk.EARLY)["cards"][0]["lesson_id"]
        self.lessons.pull(first, "faded")
        rep = self.run_night(fk.candidate(fk.EARLY, lesson="  water the beds EARLY in the morning. "))
        self.assertEqual(self.proposer.calls[0]["known"], [fk.EARLY["lesson"]])  # the proposer is told
        self.assertEqual(rep["candidates"][0]["verdict"], study.PULLED_BEFORE)
        self.assertEqual(rep["cards"], [])
        self.assertEqual([(les["id"], les["state"]) for les in self.lessons.mine()], [(first, "pulled")])

    def test_steps_carry_the_lessons_given_as_text(self):
        tone = self.lessons.propose("Visit the shady beds first.", ["all"], now=fk.T0, sources=[])
        fk.beds(self.log)
        fk.case(self.log, "shade1", "water", "soaked", "grew", stage="seedling", early=True, lessons=[tone])
        self.run_night(fk.EARLY)
        steps = [s for call in self.tagger.calls for v in call["cases"] for s in v["steps"]]
        self.assertIn(["Visit the shady beds first."], [s.get("lessons") for s in steps])

    def test_a_study_and_its_lessons_are_one_agent(self):
        fan = Lessons(self.db, plugs.load(plugs.FAN, self))
        with self.assertRaises(ValueError):
            Study(self.db, self.plug, proposer=fk.Proposer(), tagger=fk.Tagger(), lessons=fan)


class NoNightCap(Night):
    """Call 1A: no nightly cap. Every low risk lesson the study writes goes on trial with no yes,
    or waits its turn when its stage has a trial (call 8: one trial per stage)."""

    def five(self, way="way"):
        fk.beds(self.log)
        return [fk.candidate(fk.EARLY, pattern=f"early {n} {way}", lesson=f"Water the beds early, {way} {w}.")
                for n, w in enumerate(("one", "two", "three", "four", "five"))]

    def test_every_new_low_risk_lesson_goes_on_trial_or_waits_its_turn(self):
        five = self.five()
        rep = self.run_night(*five, tagger=fk.Tagger({c["pattern"]: "early" for c in five}))
        self.assertEqual([(c["state"], c["waits_for"] is not None) for c in rep["cards"]],
                         [("trying", False)] + [("waiting", True)] * 4)
        self.assertEqual([les["yes_at"] for les in self.lessons.mine()], [None] * 5)
        self.assertEqual(len(self.lessons.turns()), 4)
        self.assertNotIn("cap", rep)
        self.assertTrue(all("held" not in c for c in rep["cards"]))

    def test_a_second_night_the_same_day_is_not_held_either(self):
        first = self.five()
        self.run_night(*first, tagger=fk.Tagger({c["pattern"]: "early" for c in first}))
        more = [fk.candidate(fk.EARLY, pattern=f"late {w}", lesson=f"Water the beds early, path {w}.")
                for w in ("north", "south", "east")]
        rep = self.study(*more, tagger=fk.Tagger({c["pattern"]: "early" for c in more})).run(
            fk.SINCE, fk.UNTIL, now=fk.NOW + 60)
        self.assertEqual([(c["state"], c["waits_for"] is not None) for c in rep["cards"]], [("waiting", True)] * 3)
        self.assertEqual(len(self.lessons.turns()), 7)

    def test_high_risk_lessons_wait_for_a_yes(self):
        fk.beds(self.log)
        cands = [fk.candidate(fk.EARLY, pattern=f"p{n}", lesson=line) for n, line in enumerate(
            ("Use bleach early.", "Use poison early.", "Water early, way one.", "Water early, way two.",
             "Water early, way three."))]
        rep = self.run_night(*cands, tagger=fk.Tagger({c["pattern"]: "early" for c in cands}))
        low = [c for c in rep["cards"] if c["risk"] == "low"]
        self.assertEqual([(c["state"], c["waits_for"] is not None) for c in low],
                         [("trying", False), ("waiting", True), ("waiting", True)])
        high = [c for c in rep["cards"] if c["risk"] == "high"]
        self.assertEqual([(c["state"], c["waits_for"]) for c in high], [("waiting", None)] * 2)

    def test_the_strongest_pattern_starts_first(self):
        fk.beds(self.log, early_good=6, early_bad=4, late_good=2, late_bad=8)
        for n in range(10):
            fk.case(self.log, f"m{n}", "water", "soaked", "grew" if n < 9 else "wilted", stage="seedling", early=False,
                    bare=False)
            fk.case(self.log, f"x{n}", "water", "soaked", "grew" if n < 1 else "wilted", stage="seedling", early=False,
                    bare=True)
        rep = self.run_night(fk.EARLY, fk.MULCH)
        self.assertEqual([(c["change"], c["state"], c["waits_for"]) for c in rep["cards"]],
                         [(fk.MULCH["lesson"], "trying", None),
                          (fk.EARLY["lesson"], "waiting", [rep["cards"][0]["lesson_id"]])])


class PlugField(unittest.TestCase):
    def test_a_plug_with_a_nightly_cap_is_refused(self):
        for n in (0, 1, 3):
            with self.subTest(n=n), self.assertRaises(ValueError) as e:
                plugs.load(plugs.changed(plugs.WATERER, low_per_night=n), self)
            self.assertIn("low_per_night", str(e.exception))
            self.assertIn("no nightly cap", str(e.exception))


class Chance(unittest.TestCase):
    def test_even_sides_are_even(self):
        for n in (0, 1, 10, 50):
            self.assertAlmostEqual(chance_better(n // 2, n, n // 2, n), 0.5, places=9)

    def test_the_sides_swap(self):
        for a in ((8, 10, 2, 10), (3, 7, 5, 12), (0, 5, 4, 9)):
            g1, n1, g0, n0 = a
            self.assertAlmostEqual(chance_better(g1, n1, g0, n0) + chance_better(g0, n0, g1, n1), 1.0, places=9)

    def test_it_matches_a_simulation(self):
        rng = random.Random(7)
        for g1, n1, g0, n0 in ((8, 10, 2, 10), (6, 10, 5, 10), (3, 5, 20, 40), (1, 6, 0, 6)):
            draws = 40000
            wins = sum(rng.betavariate(1 + g1, 1 + n1 - g1) > rng.betavariate(1 + g0, 1 + n0 - g0)
                       for _ in range(draws))
            self.assertAlmostEqual(chance_better(g1, n1, g0, n0), wins / draws, delta=0.01)

    def test_the_bar_is_the_locked_seventy_five(self):
        self.assertEqual((study.CHANCE, study.MIN_CASES, study.MIN_SOURCES), (0.75, 5, 3))


class LogWindow(Night):
    def test_every_case_with_a_row_in_the_window_with_its_rows_up_to_the_end(self):
        fk.case(self.log, "a", "water", "soaked", at=fk.SINCE - DAY)
        self.log.result("a", "grew", at=fk.SINCE + DAY)
        fk.case(self.log, "b", "water", "soaked", "grew", at=fk.SINCE + 2 * DAY)
        fk.case(self.log, "c", "water", "soaked", "grew", at=fk.SINCE - 9 * DAY)
        self.log.result("b", "wilted", at=fk.UNTIL)
        got = self.log.window(fk.SINCE, fk.UNTIL)
        self.assertEqual(list(got), ["a", "b"])
        self.assertEqual([r["result"] for r in got["a"]], ["soaked", "grew"])
        self.assertEqual([r["result"] for r in got["b"]], ["soaked", "grew"])

    def test_another_agents_window_is_read_by_name(self):
        fan = Log(self.db, plugs.load(plugs.FAN, self))
        fan.act("house1", "spin", result="spun", at=fk.SINCE + DAY)
        self.assertEqual(list(self.log.window(fk.SINCE, fk.UNTIL, agent="fan")), ["house1"])
        self.assertEqual(self.log.window(fk.SINCE, fk.UNTIL), {})


if __name__ == "__main__":
    unittest.main()
