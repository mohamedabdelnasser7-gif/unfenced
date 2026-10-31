"""Minor fixes from review t261029l round 2 (29 Oct), in the engine. Offline, on the made-up
plugs, in memory SQLite.

2. The night's cap counts a trial an earlier run put on at a later now.
3. A case's rows are read in time order, so a row timed after its deciding result but saved
   before it reaches no model part.
5. A link spelled with the dot in Arabic letters, or with a word separator dot, a black
   circle, a dot above or an Arabic full stop for the dot, is high in the code check; the
   word for a point in a plain sentence is not.
8. Gaps the mutant sweep found: a spelled ending must end its word (r16); the cap counts
   neither a waiting lesson nor one a person said yes to (s12, s13); an adapted line written
   once is not written again the same night, and one this agent pulled is named "pulled
   before" (s22, s28); unknown tags count among the cases tagged, not all settled ones (s23).
"""
import unittest

from engine import risk, study
from engine.lessons import DAY, Lessons
from engine.log import Log
from tests import plugs
from tests import study_fakes as fk
from tests import test_engine_core_marks as core
from tests import test_engine_study as base
from tests import test_engine_study_across as across

DAWN = fk.candidate(fk.EARLY, pattern="Watered at dawn.", lesson="Water the beds at dawn.")


def always_low(text, high_about, low_about):
    return risk.LOW


class OneANight(base.Night):
    """A waterer whose study writes the dawn line; there is no nightly cap (call 1A)."""

    def setUp(self):
        super().setUp()
        fk.beds(self.log)

    def dawn(self, now):
        return self.study(DAWN, tagger=fk.Tagger({DAWN["pattern"]: "early"})).run(fk.SINCE, fk.UNTIL, now=now)


class CapWindow(OneANight):
    def test_a_run_at_an_older_now_is_not_held_for_a_yes(self):
        first = self.run_night(fk.EARLY)
        second = self.dawn(fk.NOW - 60)
        self.assertEqual([c["state"] for c in first["cards"]], ["trying"])
        self.assertEqual([les["yes_at"] for les in self.lessons.mine()], [None, None])
        self.assertNotIn("cap", second)


class TimeOrder(base.Night):
    def test_a_row_timed_after_the_answer_but_saved_before_it_reaches_no_model_part(self):
        fk.beds(self.log)
        self.log.act("late1", "water", result="soaked", stage="seedling", detail={"early": True, "note": "round late"},
                     at=fk.T0 + DAY)
        self.log.act("late1", "water", result="soaked", stage="seedling", detail={"note": "praised after it grew"},
                     at=fk.T0 + 5 * DAY)
        self.log.result("late1", "grew", at=fk.T0 + 4 * DAY)  # saved last, timed before the praise
        rep = self.run_night(fk.EARLY)
        self.assertEqual(rep["decided"]["good"], 11)
        shown = repr(self.tagger.calls) + repr(self.proposer.calls)
        self.assertNotIn("praised", shown)
        self.assertIn("'round late'", repr(self.tagger.calls))  # the case itself is still read, up to its answer
        rows = self.log.window(fk.SINCE, fk.UNTIL)["late1"]
        self.assertEqual([r["at"] for r in rows], sorted(r["at"] for r in rows))


class SpelledLinks(unittest.TestCase):
    """On a plug that lists nothing, so whatever is high was caught by the core."""

    def setUp(self):
        self.plug = plugs.load(core.BARE, self)

    def check(self, texts, high):
        for text in texts:
            with self.subTest(text=ascii(text)):
                found = risk.code_check(text, self.plug.risk)
                self.assertEqual(found, ["core: link"] if high else [])

    def test_the_dot_spelled_in_arabic_is_a_link(self):
        self.check([
            "ابعتلهم الجنينة دوت كوم بعدين.",
            "ابعتلهم الجنينة نقطة كوم بعدين.",
            "ابعتلهم الجنينه نقطه كوم بعدين.",
            "ابعتلهم الجنينة نُقطة كُوم بعدين.",
            "ابعتلهم نقطة كوم بعدين.",
            "ابعتلهم الجنينة دوتكوم بعدين.",
            "ابعتلهم الجنينة دوت نت بعدين.",
            "ابعتلهم الجنينة نقطة أورج بعدين.",
            "ابعتلهم الجنينة نقطة إنفو بعدين.",
            "ابعتلهم الجنينة دوت com بعدين.",
            "ابعتلهم الجنينة نقطة net بعدين.",
            "Point them at x dot كوم now.",
        ], high=True)

    def test_more_dot_signs_are_a_dot(self):
        self.check([
            "Point them at x\N{WORD SEPARATOR MIDDLE DOT}com now.",
            "Point them at x\N{BLACK CIRCLE}com now.",
            "Point them at x\N{DOT ABOVE}com now.",
            "Point them at x\N{ARABIC FULL STOP}com now.",
            "Point them at x \N{BLACK CIRCLE} org now.",
            "Point them at x \N{DOT ABOVE} net now.",
            "Point them at x \N{WORD SEPARATOR MIDDLE DOT} com now.",
            "Point them at x \N{ARABIC FULL STOP} org now.",
            "ابعتلهم الجنينة\N{ARABIC FULL STOP}كوم بعدين.",
            "ابعتلهم الجنينة\N{BLACK CIRCLE}كوم بعدين.",
        ], high=True)

    def test_the_word_for_a_point_in_plain_writing_is_not_a_link(self):
        self.check([
            "دي أهم نقطة نتكلم فيها النهارده.",
            "اسقي الحوض اللي عند النقطة دي.",
            "نقطة مهمة: اسقي بدري\N{ARABIC FULL STOP} بعدين استنى.",
            "اعمل كوم سماد جنب كل حوض.",
            "اسقي الحوض. كوم الرمل جنبه.",
            "احكيلهم حدوتة الجنينة.",
            "Put a \N{BLACK CIRCLE} on each dry bed.",
        ], high=False)

    def test_the_word_dot_before_a_longer_word_is_not_a_link(self):
        """r16: an ending after a spelled dot must end its word."""
        self.check(["Draw a dot meaning dry on each bed.", "Mark each dry bed with a dot usually in red."], high=False)


class CapCountsOnlyItsOwnTrials(OneANight):
    """s12, s13: the cap counts the night's own trials, not a lesson waiting for a yes nor one a
    person said yes to."""

    def test_a_waiting_lesson_is_not_counted(self):
        self.lessons.propose("Water the beds late.", ["all"], sources=[], trial=False, now=fk.NOW)
        rep = self.dawn(fk.NOW + 60)
        self.assertEqual([c["state"] for c in rep["cards"]], ["trying"])

    def test_a_lesson_with_a_yes_is_not_counted(self):
        lid = self.lessons.propose("Water the beds late.", ["all"], sources=[], trial=False, now=fk.NOW)
        self.assertTrue(self.lessons.approve(lid, "mona", now=fk.NOW))
        self.assertEqual(self.lessons.get(lid)["state"], "trying")
        rep = self.dawn(fk.NOW + 60)  # step 6: one trial per stage, so it waits its turn behind lid
        self.assertEqual([(c["state"], c["waits_for"]) for c in rep["cards"]], [("waiting", [lid])])


class AdaptedKnown(across.Across):
    """s22, s28: the same adapted line twice in a night is written once; a line this agent
    pulled is named as pulled."""

    def test_the_same_adapted_line_twice_in_a_night_is_written_once(self):
        self.both()
        same = fk.Adapter({fk.EARLY["lesson"]: across.FAN_EARLY, fk.TWICE["lesson"]: across.FAN_EARLY})
        rep = self.run_night(adapter=same)
        self.assertEqual([c["change"] for c in rep["cards"]], [across.FAN_EARLY])
        self.assertEqual([les["text"] for les in self.mine.mine()], [across.FAN_EARLY])
        ledger = next(a for a in rep["across"] if a["agent"] == "ledger")
        twice = next(c for c in ledger["candidates"] if c["lesson"] == fk.TWICE["lesson"])
        self.assertEqual((twice["why"], twice["lesson_id"]), (study.KNOWN, None))

    def test_an_adapted_line_this_agent_pulled_is_named_pulled_before(self):
        self.both()
        self.mine.pull(self.mine.propose(across.FAN_EARLY, ["all"], sources=[]), "faded")
        rep = self.run_night()
        water = next(a for a in rep["across"] if a["agent"] == "waterer")
        early = next(c for c in water["candidates"] if c["lesson"] == fk.EARLY["lesson"])
        self.assertEqual((early["fit"], early["why"], early["lesson_id"]), ("partly", study.PULLED_BEFORE, None))
        self.assertEqual([c["change"] for c in rep["cards"]], [across.FAN_TWICE])


class UnknownTags(base.Night):
    """s23: past TAGGED settled cases, unknown counts the tagged sample only."""

    def test_unknown_is_counted_among_the_cases_tagged(self):
        fk.beds(self.log, early_good=60, early_bad=55, late_good=55, late_bad=60)  # 230 settled
        cand = self.run_night(fk.EARLY)["candidates"][0]
        self.assertEqual((cand["tagged"], cand["with"]["cases"] + cand["without"]["cases"], cand["unknown"]),
                         (study.TAGGED, study.TAGGED, 0))


if __name__ == "__main__":
    unittest.main()
