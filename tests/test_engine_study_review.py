"""Review t261029j round 1: the night study shows no model part anything logged after a
case's answer, gives the tagger fresh keys, never writes a pulled line again, counts the
day's earlier trials in the cap, names its cases, survives a refused write, and tags at
most TAGGED cases. The model parts are fakes here."""
import unittest

from engine import risk, study
from engine.lessons import DAY, Lessons
from engine.log import Log
from engine.study import Study
from reflection import study as model_study
from tests import plugs
from tests import study_fakes as fk
from tests import test_engine_study as base
from tests import test_engine_study_across as across
from tests.fake_model import FakeModel, call, say
from tests.kept import kept_lesson


def always_low(text, high_about, low_about):
    return risk.LOW


def notes(views):
    return [v["steps"][0]["detail"]["note"] for v in views]


class NothingAfterTheAnswer(base.Night):
    def test_rows_after_the_deciding_result_reach_no_model_part(self):
        fk.beds(self.log)
        self.log.act("bed1", "water", result="soaked", stage="seedling",
                     detail={"note": "praised after it grew"}, at=fk.T0 + 5 * DAY)
        self.run_night(fk.EARLY)
        shown = repr(self.tagger.calls) + repr(self.proposer.calls)
        self.assertNotIn("praised", shown)
        self.assertIn("'round 1'", shown)  # the case itself is still read, up to its answer
        for view in self.proposer.calls[0]["sample"]:
            self.assertNotIn(view["deciding"], [s.get("result") for s in view["steps"]])


class FreshTaggerKeys(base.Night):
    def test_the_tagger_never_gets_a_key_the_proposer_saw(self):
        fk.beds(self.log)
        self.run_night(fk.EARLY, fk.MULCH)
        proposer_keys = {v["id"] for v in self.proposer.calls[0]["sample"]}
        by_note = {v["steps"][0]["detail"]["note"]: v["id"] for v in self.proposer.calls[0]["sample"]}
        self.assertEqual(len(self.tagger.calls), 2)
        for call_ in self.tagger.calls:
            keys = {v["id"] for v in call_["cases"]}
            self.assertFalse(keys & proposer_keys)
            for v in call_["cases"]:
                self.assertNotEqual(v["id"], by_note[v["steps"][0]["detail"]["note"]])
        first, second = ({v["id"] for v in c["cases"]} for c in self.tagger.calls)
        self.assertFalse(first & second)  # fresh for each call

    def test_the_keys_map_back_to_the_right_cases(self):
        fk.beds(self.log)
        cand = self.run_night(fk.EARLY)["candidates"][0]
        self.assertEqual((cand["with"]["cases"], cand["with"]["good"]), (10, 8))
        self.assertEqual((cand["without"]["cases"], cand["without"]["good"]), (10, 2))


class NoDaysCap(base.Night):
    """Call 1A: a second run the same day writes its lesson on trial or in its turn, never held."""

    def setUp(self):
        super().setUp()
        fk.beds(self.log)

    def again(self, now):
        dawn = fk.candidate(fk.EARLY, pattern="Watered at dawn.", lesson="Water the beds at dawn.")
        return self.study(dawn, tagger=fk.Tagger({"Watered at dawn.": "early"})).run(fk.SINCE, fk.UNTIL, now=now)

    def test_a_second_run_the_same_day_waits_its_turn_not_for_a_yes(self):
        first = self.run_night(fk.EARLY)
        second = self.again(fk.NOW + 60)
        self.assertEqual([c["state"] for c in first["cards"]], ["trying"])
        self.assertEqual([(c["state"], c["waits_for"]) for c in second["cards"]],
                         [("waiting", [first["cards"][0]["lesson_id"]])])
        self.assertEqual([(les["state"], les["yes_at"]) for les in self.lessons.mine()],
                         [("trying", None), ("waiting", None)])

class SourceLine(base.Night):
    def test_the_source_line_names_the_cases_with_the_pattern(self):
        fk.beds(self.log)
        source = self.run_night(fk.EARLY)["cards"][0]["source"]
        head, _, ids = source.partition("; cases with it: ")
        self.assertIn("with it 8 of 10 ended grew", head)
        self.assertEqual(set(ids.split(", ")), {f"bed{n}" for n in range(1, 11)})

    def test_past_twenty_cases_it_says_how_many_more(self):
        fk.beds(self.log, early_good=18, early_bad=5)
        source = self.run_night(fk.EARLY)["cards"][0]["source"]
        ids = source.partition("; cases with it: ")[2]
        self.assertTrue(ids.endswith(" and 3 more"), ids)
        self.assertEqual(len(ids.removesuffix(" and 3 more").split(", ")), 20)


class ReadingRules(base.Night):
    def test_a_case_the_tagger_does_not_answer_is_on_neither_side(self):
        fk.beds(self.log)
        for n in range(4):
            fk.case(self.log, f"plain{n}", "water", "soaked", "wilted", stage="seedling", note=f"plain {n}")
        cand = self.run_night(fk.EARLY)["candidates"][0]
        self.assertEqual((cand["with"]["cases"], cand["without"]["cases"], cand["unknown"]), (10, 10, 4))

    def test_pending_is_timed_from_the_last_action(self):
        fk.beds(self.log)
        for at in (fk.UNTIL - 20 * DAY, fk.UNTIL - 2 * DAY):  # old, then recent: still pending
            self.log.act("late1", "water", result="soaked", stage="seedling", detail={"early": False}, at=at)
        rep = self.run_night(fk.EARLY)
        self.assertEqual((rep["pending"], rep["decided"]["past_window"]), (1, 0))

    def test_the_longest_deciding_window_decides_pending(self):
        fk.beds(self.log)  # grew shows within 10 days, wilted within 5: 7 days on, still pending
        fk.case(self.log, "late2", "water", "soaked", at=fk.UNTIL - 7 * DAY, stage="seedling", early=False)
        rep = self.run_night(fk.EARLY)
        self.assertEqual((rep["pending"], rep["decided"]["past_window"]), (1, 0))

    def test_the_last_deciding_result_wins(self):
        fk.beds(self.log)
        fk.case(self.log, "turned", "water", "soaked", "grew", stage="seedling", early=True, note="turned")
        self.log.result("turned", "wilted", at=fk.T0 + 6 * DAY)
        rep = self.run_night(fk.EARLY)
        self.assertEqual(rep["decided"], {"good": 10, "bad": 11, "past_window": 0})

    def test_helps_as_the_text_false_is_dropped(self):
        fk.beds(self.log)
        rep = self.run_night(fk.candidate(fk.EARLY, helps="false"))
        self.assertEqual(rep["candidates"], [])
        self.assertEqual(rep["dropped"][0]["why"], "helps: true or false")

    def test_a_case_with_no_source_adds_no_source(self):
        data = plugs.changed(plugs.WATERER, source={"about": "The gardener who asked.", "known_by": "row"})
        plug = plugs.load(data, self)
        log = Log(self.db, plug)
        for n in range(10):  # the cases without the pattern: ten gardeners
            fk.case(log, f"late{n}", "water", "soaked", "grew" if n < 2 else "wilted", stage="seedling",
                    early=False, source=f"gardener{n}", note=f"late {n}")
        for n in range(5):  # with it: two gardeners, then five results with no action and no source
            fk.case(log, f"early{n}", "water", "soaked", "grew", stage="seedling", early=True,
                    source=f"helper{n % 2}", note=f"early {n}")
            log.result(f"bare{n}", "grew", at=fk.T0 + 4 * DAY)

        def tagger(plug, pattern, cases):
            out = {}
            for v in cases:
                detail = v["steps"][0].get("detail") or {} if v["steps"] else None
                out[v["id"]] = True if detail is None else detail.get("early")
            return out

        rep = Study(self.db, plug, proposer=fk.Proposer(fk.EARLY), tagger=tagger,
                    lessons=Lessons(self.db, plug, judge=always_low)).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        cand = rep["candidates"][0]
        self.assertEqual((cand["with"]["cases"], cand["with"]["sources"]), (10, 2))
        self.assertEqual(cand["verdict"], study.FEW_SOURCES)


class MorePins(base.Night):
    def test_the_sample_follows_the_seed(self):
        fk.beds(self.log, early_good=10, early_bad=10, late_good=10, late_bad=10)

        def sample(seed):
            proposer = fk.Proposer()
            Study(self.db, self.plug, proposer=proposer, tagger=fk.Tagger(), lessons=self.lessons,
                  seed=seed).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
            return notes(proposer.calls[0]["sample"])

        self.assertEqual(sample(1), sample(1))
        self.assertNotEqual(sample(1), sample(2))

    def test_two_candidates_with_one_lesson_line_make_one_card(self):
        fk.beds(self.log)
        rep = self.run_night(fk.EARLY, fk.candidate(fk.EARLY, pattern="Watered before nine."),
                             tagger=fk.Tagger({fk.EARLY["pattern"]: "early", "Watered before nine.": "early"}))
        self.assertEqual(len(rep["cards"]), 1)
        self.assertEqual(sorted(c["verdict"] for c in rep["candidates"]), [study.KNOWN, study.LESSON])

    def test_a_high_card_beside_a_low_one_waits_for_a_yes(self):
        fk.beds(self.log)
        bleach = fk.candidate(fk.EARLY, pattern="Bleached early.", lesson="Use bleach early.")
        rep = self.run_night(fk.EARLY, bleach, tagger=fk.Tagger({fk.EARLY["pattern"]: "early",
                                                                  "Bleached early.": "early"}))
        self.assertEqual([(c["state"], c["risk"], c["waits_for"]) for c in rep["cards"]],
                         [("trying", "low", None), ("waiting", "high", None)])

    def test_a_carriage_return_in_a_line_is_dropped(self):
        fk.beds(self.log)
        rep = self.run_night(fk.candidate(fk.EARLY, lesson="Water early.\rThen rest."))
        self.assertEqual(rep["dropped"][0]["why"], "lesson: one line of text")

    def test_the_tagger_reads_at_most_tagged_cases_a_seeded_sample(self):
        self.assertEqual(study.TAGGED, 200)
        fk.beds(self.log, early_good=60, early_bad=55, late_good=55, late_bad=60)  # 230 settled

        def tagged(seed):
            tagger = fk.Tagger()
            rep = Study(self.db, self.plug, proposer=fk.Proposer(fk.EARLY), tagger=tagger, lessons=self.lessons,
                        seed=seed).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
            cand = rep["candidates"][0]
            self.assertEqual((cand["tagged"], cand["with"]["cases"] + cand["without"]["cases"]), (200, 200))
            return set(notes(tagger.calls[0]["cases"]))

        first = tagged(3)
        self.assertEqual(len(first), 200)
        self.assertEqual(tagged(3), first)
        self.assertNotEqual(tagged(4), first)


class PulledThere(across.Across):
    def test_a_line_the_other_agent_pulled_is_not_brought_over(self):
        self.both()
        lid = self.theirs["waterer"].propose(fk.EARLY["lesson"], ["all"], sources=[])
        self.theirs["waterer"].pull(lid, "did not help")
        rep = self.run_night()
        water = next(a for a in rep["across"] if a["agent"] == "waterer")
        early = next(c for c in water["candidates"] if c["lesson"] == fk.EARLY["lesson"])
        self.assertEqual((early["why"], early["fit"], early["lesson_id"]), (study.PULLED_BEFORE, None, None))
        self.assertNotIn(fk.EARLY["lesson"], [c["candidate"]["lesson"] for c in self.fit.calls])
        self.assertNotIn(across.FAN_EARLY, [les["text"] for les in self.mine.mine()])
        told = next(c for c in self.proposer.calls if c["agent"] == "waterer")
        self.assertIn(fk.EARLY["lesson"], told["known"])


class Refusing(Lessons):
    def adapt(self, *args, **kw):
        raise ValueError("refused here")


class RefusedWrite(across.Across):
    def test_a_refused_write_is_named_and_the_night_goes_on(self):
        self.both()
        rep = self.run_night(lessons=Refusing(self.db, self.fan, judge=always_low))
        whys = [c["why"] for a in rep["across"] for c in a["candidates"] if c["fit"] in ("fully", "partly")]
        self.assertEqual(whys, ["not written: refused here"] * 2)
        self.assertEqual(rep["cards"], [])

    def test_kept_lessons_asked_are_at_most_the_limit(self):
        for n in range(7):
            kept_lesson(self.theirs["ledger"], f"Post entries in batch {n}.", ["all"], yes_by="owner")
        rep = self.run_night(fit=fk.Fit())
        ledger = next(a for a in rep["across"] if a["agent"] == "ledger")
        self.assertEqual(len(ledger["lessons"]), study.LIMIT)
        self.assertEqual(len(self.fit.calls), study.LIMIT)


class ModelPartPins(unittest.TestCase):
    def test_ask_gives_none_for_a_tool_call(self):
        part = model_study.Proposer(FakeModel(call("x", a=1)))
        self.assertIsNone(part.ask("Sort this.", {"a": 1}))
        self.assertEqual(model_study.Proposer(FakeModel(say("[]"))).ask("Sort this.", {"a": 1}), "[]")

    def test_read_json_needs_one_closed_fence_and_nothing_after(self):
        self.assertEqual(model_study.read_json('```json\n[1]\n```'), [1])
        self.assertIsNone(model_study.read_json('```json\n[1]'))
        self.assertIsNone(model_study.read_json('```json\n[1]\n```\nmore'))
        self.assertIsNone(model_study.read_json('[1] and more'))


if __name__ == "__main__":
    unittest.main()
