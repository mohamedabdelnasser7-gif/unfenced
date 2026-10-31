"""Fixes from review t261029l round 3 and red team t261029h round 2 (29 Oct). Offline, on the
made-up plugs, in memory SQLite.

2. A sign is part of a line: 10% and 10, > and <, two emoji stay two lines.
3. A line that waits because it comes close to a pulled one says so in its source line and in
   the simulator's text.
4. The cap counts trials from a day either side of the night's now, so a backfill run a month
   back is not held by today's trials.
5. The Arabic dot word must start its word; the spelling دات counts too.
6. Gaps the mutant sweep found: the close check reads adapted lines, the other agent's pulled
   lines and kept lessons, compares against every pulled line, and reads look alike letters.
A part whose label fails does not stop the night.
From review t261029h round 2: only a PartError's text reaches the notes, and the tagger, fit
check and adapter notes each carry the reason.
"""
import http.client
import json
import unittest

from engine import risk, study
from engine.lessons import DAY, TRYING, WAITING
from engine.study import PartError
from kit import model as kit_model
from reflection import study as model_study
from sim import run as sim_run
from tests.fake_model import FakeModel
from tests import plugs
from tests import study_fakes as fk
from tests import test_engine_core_marks as core
from tests import test_engine_r2_minor as r2_minor
from tests import test_engine_study as base
from tests import test_engine_study_across as across
from tests import test_engine_study_r2 as r2
from tests.kept import kept_lesson

FAN_VAR = "Turn the fan on early in the mornings."


class Signs(base.Night):
    def test_a_sign_makes_a_new_line(self):
        for a, b in (("Open the post with \N{FIRE}.", "Open the post with \N{MONEY WITH WINGS}."),
                     ("Offer 10% off.", "Offer 10 off."), ("Water when it is > 5.", "Water when it is < 5."),
                     ("Add +10.", "Add 10."), ("Pay $5.", "Pay \N{POUND SIGN}5."), ("خصم 10٪.", "خصم 10.")):
            with self.subTest(a=a):
                self.assertNotEqual(study._norm(a), study._norm(b))

    def test_sentence_punctuation_still_makes_no_new_line(self):
        self.assertEqual(study._norm("Water the beds, early!"), study._norm("water the beds early"))

    def test_a_live_line_with_a_sign_does_not_drop_the_line_without_it(self):
        fk.beds(self.log)
        self.run_night(fk.candidate(fk.EARLY, lesson="Give the beds 10% more water early."))
        rep = self.study(fk.candidate(fk.EARLY, lesson="Give the beds 10 more water early.")).run(
            fk.SINCE, fk.UNTIL, now=fk.NOW + 2 * DAY)
        self.assertEqual([c["change"] for c in rep["cards"]], ["Give the beds 10 more water early."])


class CloseNamed(r2.PulledLineTest):
    def test_the_source_line_names_the_pulled_line(self):
        card = self.again("Water the beds early each morning.")["cards"][0]
        self.assertEqual(card["state"], WAITING)
        self.assertIn('close to a pulled line: "Water the beds early in the morning."',
                      self.les.get(card["lesson_id"])["source"])

    def test_the_simulator_says_why_it_waits(self):
        rep = self.again("Water the beds early each morning.")
        s = sim_run.summary(self.plug, {"read": 0, "seed": 0}, rep, [self.plug])
        self.assertEqual(s["found"][0]["close_to_pulled"], "Water the beds early in the morning.")
        self.assertIn('waits for a yes (close to the pulled line "Water the beds early in the morning.")',
                      sim_run.text(s))


class CapBothSides(r2_minor.OneANight):
    def test_a_backfill_a_month_back_is_not_held_by_todays_trials(self):
        self.run_night(fk.EARLY)
        back = self.dawn(fk.NOW - 30 * DAY)
        self.assertEqual([c["state"] for c in back["cards"]], [TRYING])


class ArabicDot(r2_minor.SpelledLinks):
    def test_the_dot_word_inside_a_longer_word_is_not_a_dot(self):
        self.check(["عدوت كوم الرمل.", "غدوت نت بدري.", "النقطة نت كانت ضعيفة."], high=False)

    def test_dat_is_a_dot(self):
        self.check(["ابعتلهم الجنينة دات كوم بعدين."], high=True)

    def test_the_point_word_before_other_latin_words_is_plain_writing(self):
        self.check(["خلي بالك من نقطة online دي.", "دي نقطة me مش فاهمها.", "دي نقطة co مهمة."],
                   high=False)

    def test_the_point_word_still_counts_before_the_common_endings(self):
        self.check(["ابعتلهم الجنينة نقطة info بعدين.", "ابعتلهم الجنينة نقطة org بعدين."], high=True)

    def test_the_dot_word_still_counts_before_any_ending(self):
        self.check(["ابعتلهم الجنينة دوت online بعدين.", "ابعتلهم الجنينة دات me بعدين."], high=True)


class CloseEverywhere(across.Across):
    def card(self, rep, text):
        got = [c for c in rep["cards"] if c["change"] == text]
        return (got[0]["state"], got[0]["close_to_pulled"]) if got else None

    def test_an_adapted_line_close_to_any_of_my_pulled_lines_waits(self):  # m10, m13
        self.both()
        self.mine.pull(self.mine.propose("Check the vents every week.", ["all"], sources=[]), "x")
        self.mine.pull(self.mine.propose(across.FAN_EARLY, ["all"], sources=[]), "hurt")
        rep = self.run_night(adapter=fk.Adapter({fk.EARLY["lesson"]: FAN_VAR, fk.TWICE["lesson"]: across.FAN_TWICE}),
                             others=[self.waterer])
        self.assertEqual(self.card(rep, FAN_VAR), (WAITING, across.FAN_EARLY))

    def test_an_adapted_line_close_to_their_pulled_line_waits(self):  # m11
        self.both()
        t = self.theirs["waterer"]
        t.pull(t.propose("Water the beds early each morning.", ["all"], sources=[]), "hurt")
        same = fk.EARLY["lesson"]
        rep = self.run_night(adapter=fk.Adapter({same: same, fk.TWICE["lesson"]: across.FAN_TWICE}),
                             others=[self.waterer])
        self.assertEqual(self.card(rep, same), (WAITING, "Water the beds early each morning."))

    def test_a_kept_line_close_to_my_pulled_line_waits(self):  # m12
        self.both()
        kept_lesson(self.theirs["waterer"], "Run the fan early in the morning.", ["all"], yes_by="mona")
        self.mine.pull(self.mine.propose(across.FAN_EARLY, ["all"], sources=[]), "hurt")
        rep = self.run_night(candidates=(), fit=fk.Fit({"Run the fan early in the morning.": "fully"}),
                             adapter=fk.Adapter({"Run the fan early in the morning.": FAN_VAR}), others=[self.waterer])
        self.assertEqual(self.card(rep, FAN_VAR), (WAITING, across.FAN_EARLY))


class LookAlikes(r2.PulledLineTest):
    def test_look_alike_letters_and_accents_are_pulled_before(self):  # m02
        for line in ("W\N{CYRILLIC SMALL LETTER A}ter the beds early in the morning.",
                     "Water the beds early in the mornin\N{LATIN SMALL LETTER G WITH ACUTE}."):
            with self.subTest(line=ascii(line)):
                rep = self.again(line)
                self.assertEqual([c["verdict"] for c in rep["candidates"]], [study.PULLED_BEFORE])


class BadLabel(base.Night):
    def test_a_label_that_fails_does_not_stop_the_night(self):
        class Proposer(fk.Proposer):
            @property
            def label(self):
                raise RuntimeError("no label")
        fk.beds(self.log)
        rep = self.run_night(proposer=Proposer(fk.EARLY))
        self.assertEqual(rep["parts"]["proposer"], "Proposer")
        self.assertEqual(len(rep["cards"]), 1)


MARK = "MARKER case text from a customer"


def boom(error):
    def raise_it(messages, tools):
        raise error
    return raise_it


class NamedFailures(base.Night):
    """Review t261029h round 2: only a PartError's text reaches the notes; each part's note
    carries the reason."""

    def test_any_other_error_is_named_by_its_type_only(self):  # N2
        class Proposer(fk.Proposer):
            def __call__(self, *a):
                raise ValueError(MARK)
        fk.beds(self.log)
        rep = self.run_night(proposer=Proposer())
        self.assertIn("waterer: the proposer failed (ValueError); no candidates", rep["notes"])
        self.assertNotIn(MARK, json.dumps(rep))

    def test_the_tagger_note_carries_the_reason(self):  # N4
        fk.beds(self.log)
        tagger = model_study.Tagger(FakeModel(boom(kit_model.ModelError("Meta answered 429 Too Many Requests"))))
        rep = self.run_night(fk.EARLY, tagger=tagger)
        self.assertEqual(rep["cards"], [])
        self.assertIn("waterer: the tagger failed (PartError: Meta answered 429 Too Many Requests); "
                      "its cases count as unknown", rep["notes"])

    def test_an_error_that_is_not_an_os_error_is_wrapped(self):  # N26
        part = model_study.Proposer(FakeModel(boom(http.client.IncompleteRead(b"x"))))
        with self.assertRaisesRegex(PartError, "^the model call failed: IncompleteRead$"):
            part(self.plug, [], 3, [])


class NamedFailuresAcross(across.Across):
    def test_the_fit_and_adapter_notes_carry_the_reason(self):  # N5, N6
        self.both()
        down = kit_model.ModelError("Baseten answered 503 Service Unavailable")
        rep = self.run_night(fit=model_study.FitCheck(FakeModel(boom(down), boom(down))), others=[self.waterer])
        self.assertIn("the fit check failed on a waterer candidate (PartError: Baseten answered 503 Service "
                      "Unavailable); counted as not", rep["notes"])
        rep = self.run_night(fit=fk.Fit({fk.EARLY["lesson"]: "fully", fk.TWICE["lesson"]: "fully"}),
                             adapter=model_study.Adapter(FakeModel(boom(down), boom(down))), others=[self.waterer])
        self.assertIn("the adapter failed on a waterer candidate (PartError: Baseten answered 503 Service "
                      "Unavailable); nothing written", rep["notes"])


class NoTrail(unittest.TestCase):
    """Red team t261029h round 1 note: a ModelError or PartError keeps no link to the error it
    replaced, whose __context__ would hold the request (key header, customer text)."""

    def model(self, error):
        def opener(req, timeout):
            raise error
        return kit_model.Model(api_key="k-test", opener=opener)

    def assert_no_trail(self, e):
        self.assertIsNone(e.__context__)
        self.assertIsNone(e.__cause__)

    def test_the_model_error_drops_the_original(self):
        import urllib.error
        for error in (urllib.error.HTTPError("https://x", 500, "Server Error", {}, None),
                      urllib.error.URLError(MARK), TimeoutError(MARK), ValueError(MARK)):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(kit_model.ModelError) as got:
                    self.model(error).chat([{"role": "user", "content": MARK}])
                self.assert_no_trail(got.exception)

    def test_an_answer_with_no_message_drops_the_original(self):
        class Answer:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"choices": []}'
        m = kit_model.Model(api_key="k-test", opener=lambda req, timeout: Answer())
        with self.assertRaises(kit_model.ModelError) as got:
            m.chat([])
        self.assert_no_trail(got.exception)


class NoTrailPart(base.Night):
    def test_the_part_error_drops_the_original(self):
        for error in (kit_model.ModelError("Meta answered 429 Too Many Requests"), ValueError(MARK)):
            with self.subTest(error=type(error).__name__):
                part = model_study.Proposer(FakeModel(boom(error)))
                with self.assertRaises(PartError) as got:
                    part(self.plug, [], 3, [])
                self.assertIsNone(got.exception.__context__)
                self.assertIsNone(got.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
