"""Step 5 part B1, decided item 0: an agent's night study also reads the cases and kept
lessons of the other agents in the same database, in any field. Field tags only set which
agents come first. A fit check answers fully, partly or not; for fully or partly an adapter
rewrites the lesson in the agent's own words, and the new lesson names its source, passes
the agent's own risk check and starts as a trial. The model parts are fakes here."""
import unittest

from engine import risk, study
from engine.lessons import DAY, Lessons
from engine.log import Log
from engine.study import Study, chance_better
from kit.db import Db
from tests import plugs
from tests import study_fakes as fk
from tests.kept import kept_lesson

UNTIL = fk.T0 + 60 * DAY  # long enough for a month of books to pass its window
NOW = UNTIL
FAN_EARLY = "Turn the fan on early in the morning."
FAN_TWICE = "Check the fan twice before turning it on."


def always_low(text, high_about, low_about):
    return risk.LOW


class Across(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.waterer = plugs.load(plugs.WATERER, self)
        self.fan = plugs.load(plugs.FAN, self)
        self.ledger = plugs.load(plugs.LEDGER, self)
        self.logs = {p.agent: Log(self.db, p) for p in (self.waterer, self.fan, self.ledger)}
        self.mine = Lessons(self.db, self.fan, judge=always_low)
        self.theirs = {p.agent: Lessons(self.db, p, judge=always_low) for p in (self.waterer, self.ledger)}

    def study(self, *, fit=None, adapter=None, candidates=(fk.EARLY, fk.TWICE), others=None, lessons=None, **kw):
        self.proposer = fk.Proposer(*candidates)
        self.tagger = fk.Tagger()
        self.fit = fit if fit is not None else fk.Fit({fk.EARLY["lesson"]: "partly", fk.TWICE["lesson"]: "fully"})
        self.adapter = adapter if adapter is not None else fk.Adapter({fk.EARLY["lesson"]: FAN_EARLY,
                                                                       fk.TWICE["lesson"]: FAN_TWICE})
        return Study(self.db, self.fan, proposer=self.proposer, tagger=self.tagger, fit=self.fit, adapter=self.adapter,
                     others=[self.ledger, self.waterer] if others is None else others,
                     lessons=lessons or self.mine, **kw)

    def run_night(self, **kw):
        return self.study(**kw).run(fk.SINCE, UNTIL, now=NOW)

    def both(self):
        fk.beds(self.logs["waterer"])
        fk.entries(self.logs["ledger"])

    def lesson(self, text):
        found = [les for les in self.mine.mine() if les["text"] == text]
        self.assertEqual(len(found), 1, text)
        return found[0]


class ReadsEveryField(Across):
    def test_other_agents_are_read_in_any_field_the_closest_first(self):
        self.both()
        rep = self.run_night()
        self.assertEqual([(a["agent"], a["shared_fields"]) for a in rep["across"]],
                         [("waterer", ["gardening"]), ("ledger", [])])
        self.assertEqual([c["agent"] for c in self.proposer.calls], ["waterer", "ledger"])  # the fan has no cases
        self.assertEqual({les["text"] for les in self.mine.mine()}, {FAN_EARLY, FAN_TWICE})
        self.assertEqual([c["change"] for c in rep["cards"]], [FAN_EARLY, FAN_TWICE])

    def test_a_lesson_from_another_field_names_its_source_and_starts_as_a_trial(self):
        self.both()
        rep = self.run_night()
        les = self.lesson(FAN_TWICE)
        self.assertEqual((les["agent"], les["state"], les["risk"], les["source_lesson_id"]), ("fan", "waiting", "low", None))
        # step 6: one trial per stage, so it waits its turn behind the first lesson, its trial fixed
        self.assertEqual(self.mine.waits_for(les["id"], NOW), [self.lesson(FAN_EARLY)["id"]])
        self.assertEqual(self.mine.trial(les["id"]), {"share": 0.5, "days": 7.0, "queued_at": NOW, "started_at": None,
                                                      "worst_cost": None, "good": None, "bad": None, "harm": None,
                                                      "serious": None, "windows": None, "level": "careful",
                                                      "accept_high": None})
        self.assertEqual(self.mine.start_turns(NOW + 7 * DAY), [les["id"]])
        les = self.lesson(FAN_TWICE)
        self.assertEqual((les["state"], les["share"], les["ends_at"]), ("trying", 0.5, NOW + 14 * DAY))
        for part in ("ledger", "fully", "month1", "8 of 10", "2 of 10", fk.TWICE["pattern"]):
            self.assertIn(part, les["source"])
        card = [c for c in rep["cards"] if c["change"] == FAN_TWICE][0]
        self.assertEqual(card["from"]["agent"], "ledger")
        self.assertEqual(card["from"]["fit"], "fully")
        self.assertEqual(sorted(card["from"]["cases"]), sorted(f"month{n}" for n in range(1, 11)))
        self.assertEqual(card["moves"], {"result": "cooled", "shows_in_days": [1.5, 3.0]})
        self.assertEqual(card["must_not_worsen"]["results"], ["stalled"])
        self.assertAlmostEqual(card["sure"], chance_better(8, 10, 2, 10), places=6)
        self.assertEqual(card["cases"]["total"], 20)

    def test_the_fit_and_the_adapter_see_the_two_plugs_and_the_candidate(self):
        self.both()
        self.run_night()
        self.assertEqual([(c["agent"], c["other"]) for c in self.fit.calls], [("fan", "waterer"), ("fan", "ledger")])
        self.assertEqual([c["fit"] for c in self.adapter.calls], ["partly", "fully"])
        cand = self.fit.calls[1]["candidate"]
        self.assertEqual((cand["lesson"], cand["pattern"], cand["situation"]),
                         (fk.TWICE["lesson"], fk.TWICE["pattern"], fk.TWICE["situation"]))
        self.assertNotIn("month1", repr(self.fit.calls) + repr(self.adapter.calls))

    def test_a_fit_of_not_or_an_odd_answer_writes_nothing(self):
        self.both()
        rep = self.run_night(fit=fk.Fit({fk.EARLY["lesson"]: "not", fk.TWICE["lesson"]: "maybe"}))
        self.assertEqual((self.mine.mine(), rep["cards"], self.adapter.calls), ([], [], []))
        self.assertEqual([c["fit"] for a in rep["across"] for c in a["candidates"] if c["verdict"] == study.LESSON],
                         ["not", "not"])

    def test_the_other_agent_must_show_its_own_clear_gap(self):
        fk.entries(self.logs["ledger"], twice_good=5, twice_none=5, once_good=5, once_none=5)
        rep = self.run_night()
        self.assertEqual(self.fit.calls, [])
        self.assertEqual(rep["across"][1]["candidates"][1]["verdict"], study.NO_GAP)
        self.assertEqual(self.mine.mine(), [])

    def test_a_pending_or_left_out_case_of_another_agent_is_not_counted(self):
        fk.entries(self.logs["ledger"])
        for n in range(4):  # still inside the 30 day window
            fk.case(self.logs["ledger"], f"late{n}", "post", "posted", at=UNTIL - 5 * DAY, stage="open", twice=False)
        rep = self.run_night()
        ledger = rep["across"][1]
        self.assertEqual(ledger["read"], {"cases": 24, "good": 10, "bad": 10, "pending": 4, "left_out": 0})

    def test_the_adapted_lesson_passes_this_agents_own_risk_check(self):
        self.both()
        self.run_night(adapter=fk.Adapter({fk.TWICE["lesson"]: "Check the fan 2 times before turning it on."}))
        les = self.lesson("Check the fan 2 times before turning it on.")
        self.assertEqual((les["risk"], les["state"]), ("high", "waiting"))
        self.assertIn("amount", les["risk_why"])

    def test_with_the_stub_judge_an_adapted_lesson_waits(self):
        self.both()
        self.run_night(lessons=Lessons(self.db, self.fan))
        self.assertEqual({les["state"] for les in self.mine.mine()}, {"waiting"})

    def test_words_copied_from_the_other_agents_cases_are_caught(self):
        for n in range(20):
            fk.case(self.logs["ledger"], f"m{n}", "post", "posted", "balanced" if (n < 8 or n >= 18) else None,
                    stage="open", twice=n < 10, note="the auditor wrote balance every page before the close")
        line = "Balance every page before the fan starts."
        self.run_night(adapter=fk.Adapter({fk.TWICE["lesson"]: line}))
        les = self.lesson(line)
        self.assertEqual((les["risk"], les["state"]), ("high", "waiting"))
        self.assertIn("core: copied from source", les["risk_why"])

    def test_the_adapted_lesson_must_fit_this_agents_stages(self):
        self.both()
        rep = self.run_night(adapter=fk.Adapter({fk.TWICE["lesson"]: FAN_TWICE}, stages=["open"]))
        self.assertEqual(self.mine.mine(), [])
        ledger = rep["across"][1]["candidates"][1]
        self.assertEqual(ledger["lesson_id"], None)
        self.assertIn("stage", ledger["why"])

    def test_a_failing_fit_check_or_adapter_writes_nothing(self):
        self.both()
        rep = self.run_night(fit=fk.Fit(fail=True))
        self.assertEqual(self.mine.mine(), [])
        self.assertTrue(any("fit" in n for n in rep["notes"]))
        rep = self.run_night(adapter=fk.Adapter(fail=True))
        self.assertEqual(self.mine.mine(), [])
        self.assertTrue(any("adapter" in n for n in rep["notes"]))

    def test_with_no_fit_check_or_adapter_other_agents_are_not_read(self):
        self.both()
        rep = Study(self.db, self.fan, proposer=fk.Proposer(fk.EARLY), tagger=fk.Tagger(), others=[self.waterer],
                    lessons=self.mine).run(fk.SINCE, UNTIL, now=NOW)
        self.assertEqual(rep["across"], [])
        self.assertTrue(any("other agents" in n for n in rep["notes"]))

    def test_this_agent_in_others_is_not_read_twice(self):
        self.both()
        rep = self.run_night(others=[self.fan, self.waterer])
        self.assertEqual([a["agent"] for a in rep["across"]], ["waterer"])

    def test_an_agent_in_the_log_with_no_plug_given_is_named(self):
        self.both()
        rep = self.run_night(others=[self.waterer])
        self.assertEqual(rep["unread"], ["ledger"])

    def test_the_same_adapted_line_is_not_written_twice(self):
        self.both()
        self.run_night()
        rep = self.run_night()
        self.assertEqual(len(self.mine.mine()), 2)
        self.assertEqual(rep["cards"], [])


class KeptLessons(Across):
    def test_a_kept_lesson_of_another_agent_is_adapted_and_linked(self):
        kept = kept_lesson(self.theirs["ledger"], "Post entries in date sequence.", ["all"], yes_by="owner")
        trying = self.theirs["ledger"].propose("Post small entries first.", ["all"], sources=[])
        pulled = self.theirs["ledger"].add("Post late entries last.", ["all"], yes_by="owner")  # waits its turn
        self.theirs["ledger"].pull(pulled, "faded")
        fit = fk.Fit({t: "partly" for t in ("Post entries in date sequence.", "Post small entries first.",
                                            "Post late entries last.")})
        adapter = fk.Adapter({"Post entries in date sequence.": "Spin the fans in house sequence."})
        rep = self.run_night(fit=fit, adapter=adapter)
        self.assertEqual([c["candidate"]["lesson"] for c in fit.calls], ["Post entries in date sequence."])
        les = self.lesson("Spin the fans in house sequence.")
        self.assertEqual((les["source_lesson_id"], les["state"], les["risk"]), (kept, "trying", "low"))
        self.assertIn(f"ledger lesson {kept}", les["source"])
        self.assertIn("partly", les["source"])
        card = rep["cards"][0]
        self.assertEqual(card["from"], {"agent": "ledger", "fit": "partly", "lesson": kept})
        self.assertEqual((card["sure"], card["cases"]), (None, None))
        self.assertEqual(rep["across"][1]["lessons"],
                         [{"lesson": kept, "fit": "partly", "lesson_id": les["id"], "why": None}])
        self.assertNotIn(trying, [c["lesson"] for a in rep["across"] for c in a["lessons"]])

    def test_a_lesson_already_adapted_is_not_asked_again(self):
        kept_lesson(self.theirs["ledger"], "Post entries in date sequence.", ["all"], yes_by="owner")
        fit = fk.Fit({"Post entries in date sequence.": "fully"})
        adapter = fk.Adapter({"Post entries in date sequence.": "Spin the fans in house sequence."})
        self.run_night(fit=fit, adapter=adapter)
        first = len(fit.calls)
        self.mine.pull(self.mine.mine()[0]["id"], "did not help")
        self.run_night(fit=fit, adapter=adapter)
        self.assertEqual((first, len(fit.calls), len(self.mine.mine())), (1, 1, 1))

    def test_a_kept_lesson_from_the_same_field_comes_first(self):
        kept_lesson(self.theirs["ledger"], "Post entries in date sequence.", ["all"], yes_by="owner")
        kept_lesson(self.theirs["waterer"], "Visit the shady beds first.", ["all"], yes_by="grower")
        fit = fk.Fit({"Post entries in date sequence.": "partly", "Visit the shady beds first.": "fully"})
        adapter = fk.Adapter({"Post entries in date sequence.": "Spin the fans in house sequence.",
                              "Visit the shady beds first.": "Cool the shady houses first."})
        rep = self.run_night(fit=fit, adapter=adapter)
        self.assertEqual([(c["change"], c["state"]) for c in rep["cards"]],
                         [("Cool the shady houses first.", "trying"), ("Spin the fans in house sequence.", "waiting")])
        self.assertEqual(rep["cards"][1]["waits_for"], [rep["cards"][0]["lesson_id"]])  # its turn, not a cap


class NoCap(Across):
    def test_own_lessons_start_first_then_adapted_ones_wait_their_turn(self):
        self.both()
        for n in range(20):
            fk.case(self.logs["fan"], f"house{n}", "spin", "spun", "cooled" if (n < 8 or n >= 18) else None,
                    stage="grown", early=n < 10)
        rep = self.run_night()
        first = rep["cards"][0]["lesson_id"]
        self.assertEqual([(c["change"], c["state"], c["waits_for"]) for c in rep["cards"]],
                         [(fk.EARLY["lesson"], "trying", None), (FAN_EARLY, "waiting", [first]),
                          (FAN_TWICE, "waiting", [first, rep["cards"][1]["lesson_id"]])])
        self.assertEqual([c["agent"] for c in self.proposer.calls], ["fan", "waterer", "ledger"])


class AdaptMethod(Across):
    def test_adapt_takes_a_kept_lesson_from_any_field(self):
        kept = kept_lesson(self.theirs["ledger"], "Post entries in date sequence.", ["all"], yes_by="owner")
        new = self.mine.adapt("Spin the fans in house sequence.", ["grown"], source=f"adapted from ledger lesson {kept}",
                              source_lesson_id=kept, sources=[])
        les = self.mine.get(new)
        self.assertEqual((les["agent"], les["source_lesson_id"], les["state"], les["fields"], les["stages"]),
                         ("fan", kept, "trying", ["gardening"], ["grown"]))

    def test_adapt_refuses_a_lesson_that_is_not_kept_its_own_or_missing(self):
        trying = self.theirs["ledger"].propose("Post small entries first.", ["all"], sources=[])
        own = kept_lesson(self.mine, "Spin slowly at night.", ["all"], yes_by="grower")
        for bad in (trying, own, 99999):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.mine.adapt("Spin the fans in house sequence.", ["all"], source="adapted", source_lesson_id=bad, sources=[])

    def test_adapt_needs_a_source_line(self):
        for bad in ("", "  ", None, "two\nlines"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.mine.adapt("Spin the fans in house sequence.", ["all"], source=bad, sources=[])

    def test_adapt_can_hold_a_low_risk_lesson_for_a_yes(self):
        new = self.mine.adapt("Spin the fans in house sequence.", ["all"], source="adapted from ledger cases m1",
                              trial=False, sources=[])
        self.assertEqual((self.mine.get(new)["risk"], self.mine.get(new)["state"]), ("low", "waiting"))

    def test_propose_can_hold_a_low_risk_lesson_for_a_yes(self):
        new = self.mine.propose("Spin the fans in house sequence.", ["all"], trial=False, sources=[])
        self.assertEqual((self.mine.get(new)["risk"], self.mine.get(new)["state"]), ("low", "waiting"))
        self.assertTrue(self.mine.approve(new, "grower"))


if __name__ == "__main__":
    unittest.main()
