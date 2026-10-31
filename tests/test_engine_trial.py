"""Step 6: the trial and its verdict, on the made-up plugs. A lesson on trial is compared
with the old way over the same days; the stop rule pauses it early on harm; at its end the
numbers decide, kept or pulled, on settled cases only; one trial per stage at a time; a
kept lesson leaves a small holdback on the old way. No model, no network."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import plug as engine_plug
from engine import risk
from engine.lessons import KEPT, PULLED, TRYING, WAITING, Lessons
from engine.log import Log
from engine.study import Study
from engine.trial import Trials, worst_cost
from kit.db import Db
from tests import plugs
from tests import study_fakes as fk
from tests.kept import kept_lesson

DAY = 86400
NOW = fk.NOW


def always_low(text, high_about, low_about):
    return risk.LOW


def trial_plug(**trial):
    """The waterer with a serious result and its trial settings."""
    data = plugs.changed(plugs.WATERER)
    data["results"]["flooded"] = {"speed": "fast", "shows_in_days": [0, 0], "after": "water",
                                  "about": "The bed flooded."}
    data["harm"] = {"results": ["ran_off", "flooded"], "about": "Wasted water.", "serious": ["flooded"]}
    data["trial"] = dict({"fast": {"share": 0.5, "days": 7}, "careful": {"share": 0.5, "days": 7}}, **trial)
    return data


class PlugTrialFields(unittest.TestCase):
    def test_defaults_holdback_and_worst_cost(self):
        p = plugs.load(plugs.WATERER, self)
        self.assertEqual((p.trial_holdback, p.trial_worst_cost), (0.05, 0.02))
        self.assertEqual(p.harm.serious, ())

    def test_a_plug_sets_them(self):
        p = plugs.load(trial_plug(holdback=0.1, worst_cost=0.03), self)
        self.assertEqual((p.trial_holdback, p.trial_worst_cost), (0.1, 0.03))
        self.assertEqual(p.harm.serious, ("flooded",))
        self.assertEqual(plugs.load(trial_plug(holdback=0), self).trial_holdback, 0.0)

    def test_bad_values_are_refused(self):
        for trial, words in (({"holdback": 1}, "holdback"), ({"holdback": -0.1}, "holdback"),
                             ({"worst_cost": 1.5}, "worst_cost"), ({"worst_cost": "low"}, "worst_cost"),
                             ({"length": 3}, "unknown key")):
            with self.subTest(trial=trial), self.assertRaisesRegex(ValueError, words):
                plugs.load(trial_plug(**trial), self)

    def test_serious_names_declared_results_once(self):
        for serious, words in ((["burst"], "not a declared result"), (["flooded", "flooded"], "named twice"),
                               ("flooded", "a list")):
            data = trial_plug()
            data["harm"]["serious"] = serious
            with self.subTest(serious=serious), self.assertRaisesRegex(ValueError, words):
                engine_plug.from_dict(data)
        data = trial_plug()
        data["harm"]["serious"] = ["wilted"]  # a slow result may be serious too
        self.assertEqual(engine_plug.from_dict(data).harm.serious, ("wilted",))


class Bed(unittest.TestCase):
    """A waterer with a serious result, its log and its lessons."""

    trial = {}

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(trial_plug(**self.trial), self)
        self.log = Log(self.db, self.plug)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)

    def new(self, text, stages=("all",), now=NOW):
        return self.lessons.propose(text, list(stages), sources=[], now=now)

    def state(self, lid):
        return self.lessons.get(lid)["state"]


class OneTrialPerStage(Bed):
    def test_a_second_lesson_on_a_stage_on_trial_waits_its_turn(self):
        first = self.new("Water the seedlings slowly.", ["seedling"])
        second = self.new("Water the seedlings at the root.", ["seedling"])
        third = self.new("Water the grown beds deeply.", ["grown"])
        self.assertEqual([self.state(i) for i in (first, second, third)], [TRYING, WAITING, TRYING])
        self.assertEqual(self.lessons.waits_for(second, NOW), [first])
        self.assertIsNone(self.lessons.waits_for(first, NOW))
        self.assertEqual(self.lessons.trial(second), {"share": 0.5, "days": 7.0, "queued_at": NOW, "started_at": None,
                                                      "worst_cost": None, "good": None, "bad": None, "harm": None,
                                                      "serious": None, "windows": None, "level": "careful",
                                                      "accept_high": None})  # copied when it starts
        self.assertEqual(self.lessons.trial(first)["started_at"], NOW)
        self.assertEqual([les["id"] for les in self.lessons.live("seedling", NOW)], [first])

    def test_all_meets_every_stage(self):
        first = self.new("Water the grown beds deeply.", ["grown"])
        every = self.new("Visit the shaded beds last.", ["all"])
        seedling = self.new("Water the seedlings slowly.", ["seedling"])
        self.assertEqual(self.lessons.waits_for(every, NOW), [first])
        self.assertEqual(self.lessons.waits_for(seedling, NOW), [every])  # the older one waiting goes first

    def test_turns_start_the_oldest_first_once_the_stage_is_free(self):
        first = self.new("Water the seedlings slowly.", ["seedling"])
        second = self.new("Water the seedlings at the root.", ["seedling"], now=NOW + 1)
        third = self.new("Water the seedlings twice.", ["seedling"], now=NOW + 2)
        self.assertEqual(self.lessons.start_turns(NOW + DAY), [])
        self.assertEqual(self.lessons.start_turns(NOW + 7 * DAY), [second])
        self.assertEqual((self.state(second), self.lessons.get(second)["ends_at"]), (TRYING, NOW + 14 * DAY))
        self.assertEqual(self.lessons.trial(second)["started_at"], NOW + 7 * DAY)
        self.assertEqual(self.lessons.waits_for(third, NOW + 7 * DAY), [second])
        self.assertEqual(self.state(first), TRYING)  # ended, waiting for its verdict, given in no case

    def test_a_pulled_lesson_leaves_its_turn(self):
        self.new("Water the seedlings slowly.", ["seedling"])
        second = self.new("Water the seedlings at the root.", ["seedling"])
        self.lessons.pull(second, "not wanted", now=NOW)
        self.assertEqual(self.lessons.turns(), {})
        self.assertIsNone(self.lessons.trial(second))  # its turn is gone, not just hidden
        self.assertEqual(self.lessons.start_turns(NOW + 8 * DAY), [])

    def test_a_yes_on_a_lesson_waiting_its_turn_keeps_its_place(self):
        self.new("Water the seedlings slowly.", ["seedling"])
        second = self.new("Water the seedlings at the root.", ["seedling"])
        third = self.new("Water the seedlings twice.", ["seedling"], now=NOW + 60)
        self.assertTrue(self.lessons.approve(second, "mona", now=NOW + DAY))
        self.assertEqual(self.lessons.trial(second)["queued_at"], NOW)
        self.assertEqual(self.lessons.waits_for(third, NOW + DAY)[-1], second)
        self.assertEqual(self.lessons.start_turns(NOW + 7 * DAY), [second])

    def test_a_turn_queued_later_does_not_start_earlier(self):
        self.new("Water the seedlings slowly.", ["seedling"], now=NOW + DAY)
        later = self.new("Water the seedlings at the root.", ["seedling"], now=NOW + 2 * DAY)
        self.assertEqual(self.state(later), WAITING)
        self.assertEqual(self.lessons.start_turns(NOW), [])
        self.assertEqual(self.state(later), WAITING)

    def test_replace_moves_only_a_lesson_waiting_for_its_first_yes(self):
        old = kept_lesson(self.lessons, "Water the grown beds at noon.", ["grown"], yes_by="mona", now=NOW - DAY)
        trying = self.new("Water the seedlings slowly.", ["seedling"])
        held = self.lessons.propose("Use bleach on the seedlings.", ["seedling"], sources=[], now=NOW)
        self.assertTrue(self.lessons.approve(held, "mona", now=NOW))  # a yes, waiting its turn
        for lid in (trying, held):
            with self.subTest(state=self.state(lid)):
                self.lessons.clash(lid, old, now=NOW)
                self.assertFalse(self.lessons.replace(lid, "sam", now=NOW + 60))
                self.assertEqual(self.state(old), KEPT)  # nothing pulled

    def test_a_yes_on_a_busy_stage_keeps_the_yes_and_waits(self):
        first = self.new("Water the seedlings slowly.", ["seedling"])
        held = self.lessons.propose("Use bleach on the seedlings.", ["seedling"], sources=[], now=NOW)
        self.assertEqual(self.lessons.get(held)["risk"], "high")
        self.assertTrue(self.lessons.approve(held, "mona", now=NOW + 60))
        les = self.lessons.get(held)
        self.assertEqual((les["state"], les["yes_by"]), (WAITING, "mona"))
        self.assertEqual(self.lessons.waits_for(held, NOW + 60), [first])
        self.assertFalse(self.lessons.approve(held, "sam", now=NOW + 120))  # a yes is given once
        self.assertEqual(self.lessons.start_turns(NOW + 7 * DAY), [held])
        self.assertEqual(self.state(held), TRYING)

    def test_a_persons_own_line_waits_its_turn_then_goes_on_trial(self):
        first = self.new("Water the seedlings slowly.", ["seedling"])
        own = self.lessons.add("Water the seedlings at the root.", ["seedling"], yes_by="mona", now=NOW)
        les = self.lessons.get(own)
        self.assertEqual((les["state"], les["origin"], les["yes_by"]), (WAITING, "person", "mona"))
        self.assertEqual(self.lessons.waits_for(own, NOW), [first])
        self.assertEqual(self.lessons.start_turns(NOW + 7 * DAY), [own])
        les = self.lessons.get(own)
        self.assertEqual((les["state"], les["share"], les["ends_at"]), (TRYING, 0.5, NOW + 14 * DAY))

    def test_a_persons_own_line_needs_no_yes_even_at_high_risk(self):
        own = self.lessons.add("Use 2 cups of water.", ["seedling"], yes_by="mona", now=NOW)  # a number: high
        les = self.lessons.get(own)
        self.assertEqual((les["risk"], les["state"], les["share"], les["ends_at"]), ("high", TRYING, 0.5, NOW + 7 * DAY))
        self.assertEqual(self.lessons.trial(own)["started_at"], NOW)
        study = self.lessons.propose("Use 3 cups of water.", ["grown"], sources=[], now=NOW)  # the study's high line waits
        self.assertEqual((self.lessons.get(study)["state"], self.lessons.get(study)["origin"]), (WAITING, "agent"))

    def test_a_trial_started_later_does_not_block_an_earlier_time(self):
        self.new("Water the seedlings slowly.", ["seedling"])
        back = self.new("Water the seedlings at the root.", ["seedling"], now=NOW - 30 * DAY)
        self.assertEqual(self.state(back), TRYING)

    def test_pause_ends_a_trial_now_and_frees_its_stage(self):
        first = self.new("Water the seedlings slowly.", ["seedling"])
        second = self.new("Water the seedlings at the root.", ["seedling"])
        self.assertTrue(self.lessons.pause(first, NOW + DAY))
        self.assertFalse(self.lessons.pause(first, NOW + DAY + 1))
        self.assertEqual((self.state(first), self.lessons.get(first)["ends_at"]), (TRYING, NOW + DAY))
        self.assertEqual(self.lessons.live("seedling", NOW + DAY), [])
        self.assertEqual(self.lessons.start_turns(NOW + DAY), [second])

    def test_keep_with_a_holdback_leaves_a_share_on_the_old_way(self):
        lid = self.new("Water the seedlings slowly.", ["seedling"])
        given = {c for c in range(400) if self.lessons.pick("seedling", "", case=c, now=NOW)}
        self.assertTrue(self.lessons.keep(lid, holdback=0.05))
        les = self.lessons.get(lid)
        self.assertEqual((les["state"], les["share"], les["ends_at"]), (KEPT, 0.95, None))
        kept = {c for c in range(400) if self.lessons.pick("seedling", "", case=c, now=NOW)}
        self.assertTrue(given < kept, "a case given it on trial keeps it")
        self.assertTrue(10 <= 400 - len(kept) <= 35, len(kept))
        with self.assertRaises(ValueError):
            self.lessons.keep(lid, holdback=1)
        other = self.new("Water the grown beds deeply.", ["grown"])
        self.assertTrue(self.lessons.keep(other))
        self.assertEqual(self.lessons.get(other)["share"], 1.0)


class ReplaceIt(Bed):
    """A new lesson that goes against a live one raises a "replace it?" card instead of both running."""

    def night(self, clash, *candidates):
        fk.beds(self.log)
        st = Study(self.db, self.plug, proposer=fk.Proposer(*candidates), tagger=fk.Tagger(), lessons=self.lessons,
                   clash=clash)
        return st.run(fk.SINCE, fk.UNTIL, now=NOW)

    def test_a_clash_waits_for_a_yes_and_names_both_lessons(self):
        live = kept_lesson(self.lessons, "Water the beds at noon.", ["all"], yes_by="mona", now=NOW - DAY)
        asked = []
        rep = self.night(lambda plug, new, old: asked.append((new, old)) or True, fk.EARLY)
        card = rep["cards"][0]
        self.assertEqual(card["replace"], {"lesson_id": live, "line": "Water the beds at noon.", "ask": "replace it?",
                                           "sure": True, "with": card["lesson_id"]})
        self.assertEqual((card["state"], card["waits_for"]), (WAITING, None))
        self.assertEqual(asked, [({"lesson": fk.EARLY["lesson"], "stages": ["all"]},
                                  {"lesson": "Water the beds at noon.", "stages": ["all"]})])
        self.assertEqual(self.lessons.clashes(card["lesson_id"]), {"replaces": [live], "replaced_by": []})
        self.assertEqual(self.lessons.clashes(live), {"replaces": [], "replaced_by": [card["lesson_id"]]})
        self.assertTrue(self.lessons.replace(card["lesson_id"], "mona", now=NOW + 60))
        self.assertEqual((self.state(live), self.lessons.get(live)["pulled_why"]),
                         (PULLED, f"replaced by lesson {card['lesson_id']}"))
        self.assertEqual(self.state(card["lesson_id"]), TRYING)

    def test_no_clash_runs_as_before(self):
        kept_lesson(self.lessons, "Water the beds at noon.", ["all"], yes_by="mona", now=NOW - DAY)
        card = self.night(lambda plug, new, old: False, fk.EARLY)["cards"][0]
        self.assertEqual((card["state"], card["replace"]), (TRYING, None))

    def test_a_failing_or_unsure_check_holds_it_not_sure(self):
        live = kept_lesson(self.lessons, "Water the beds at noon.", ["all"], yes_by="mona", now=NOW - DAY)

        def down(plug, new, old):
            raise RuntimeError("down")
        rep = self.night(down, fk.EARLY)
        self.assertEqual((rep["cards"][0]["state"], rep["cards"][0]["replace"]["sure"]), (WAITING, False))
        self.assertIn(f"the clash check failed on lesson {live} (RuntimeError); counted as against", rep["notes"])

    def test_a_lesson_on_other_stages_is_not_asked(self):
        seedlings = fk.candidate(fk.EARLY, stages=["seedling"])
        for stage, asked_about in (("grown", []), ("seedling", [["seedling"]])):  # the same stage is the control
            with self.subTest(stage=stage):
                self.setUp()
                live = kept_lesson(self.lessons, "Water the beds at noon.", [stage], yes_by="mona", now=NOW - DAY)
                asked = []
                cards = self.night(lambda plug, new, old: asked.append(old["stages"]) or True, seedlings)["cards"]
                self.assertEqual((len(cards), asked), (1, asked_about))
                self.assertEqual(cards[0]["replace"] and cards[0]["replace"]["lesson_id"],
                                 live if asked_about else None)


class OnTrial(Bed):
    """One lesson on trial on the seedling stage, from NOW to NOW + 7 days, and its beds."""

    def setUp(self):
        super().setUp()
        self.lid = self.new("Water the seedlings slowly.", ["seedling"])
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.n = 0

    def bed(self, *, given, good=True, fast="soaked", cause=None, fast_cause=None, at=NOW + DAY, slow=True):
        self.n += 1
        cid = f"bed{self.n}"
        self.log.act(cid, "water", result=fast, cause=fast_cause, stage="seedling", lessons=[self.lid] if given else [],
                     at=at)
        if slow:
            self.log.result(cid, "grew" if good else "wilted", cause=cause, at=at + 3 * DAY)
        return cid

    def beds(self, given, good, bad, **kw):
        return [self.bed(given=given, good=True, **kw) for _ in range(good)] + \
               [self.bed(given=given, good=False, **kw) for _ in range(bad)]

    def check(self, at):
        rep = self.trials.check(at)
        return rep, {t["lesson_id"]: t for t in rep["trials"]}.get(self.lid)

    def restart(self, data):
        """The same lesson on trial, in a new database, under another plug."""
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(data, self)
        self.log = Log(self.db, self.plug)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)
        self.lid = self.new("Water the seedlings slowly.", ["seedling"])
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.n = 0


class Guards(OnTrial):
    def test_a_check_before_the_trial_starts_skips_it(self):
        self.bed(given=True)
        self.assertIsNone(self.check(NOW - DAY)[1])
        self.assertEqual(self.check(NOW + 2 * DAY)[1]["status"], "on trial")

    def test_a_trial_and_its_lessons_belong_to_one_agent(self):
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        with self.assertRaisesRegex(ValueError, "belong to one agent"):
            Trials(self.db, self.plug, lessons=fan)


class StopRule(OnTrial):
    def test_harm_at_exactly_double_pauses_it_and_just_under_does_not(self):
        for without, status in ((20, "paused"), (19, "on trial")):  # 3 in 10 against 3 in 20, then 3 in 19
            with self.subTest(without=without):
                self.setUp()
                self.beds(True, 7, 0)
                self.beds(True, 3, 0, fast="ran_off")
                self.beds(False, without - 3, 0)
                self.beds(False, 3, 0, fast="ran_off")
                self.assertEqual(self.check(NOW + 2 * DAY)[1]["status"], status)

    def test_two_cases_with_harm_never_pause_it_however_many_harm_rows(self):
        for cid in self.beds(True, 2, 0, fast="ran_off"):
            self.log.act(cid, "water", result="ran_off", stage="seedling", lessons=[self.lid], at=NOW + DAY + 60)
        self.beds(True, 8, 0)
        self.beds(False, 38, 0)
        self.beds(False, 2, 0, fast="ran_off")
        _, t = self.check(NOW + 2 * DAY)
        self.assertEqual((t["status"], t["harm"]["with"]), ("on trial", 2))  # 2 in 10 against 2 in 40

    def test_harm_counts_only_from_the_first_row_given_the_lesson_on(self):
        for n in range(6):
            cid = f"old{n}"
            if n < 3:  # harm before the trial
                self.log.act(cid, "water", result="ran_off", stage="seedling", at=NOW - 2 * DAY)
            else:  # harm in the trial, before the case was given the lesson
                self.log.act(cid, "water", result="ran_off", stage="seedling", at=NOW + DAY - 60)
            self.log.act(cid, "water", result="soaked", stage="seedling", lessons=[self.lid], at=NOW + DAY)
        self.beds(True, 4, 0)
        self.beds(False, 38, 0)
        self.beds(False, 2, 0, fast="ran_off")
        _, t = self.check(NOW + 2 * DAY)
        self.assertEqual((t["status"], t["with"]["cases"], t["harm"]["with"]), ("on trial", 10, 0))

    def test_a_serious_result_the_plug_does_not_name_harm_is_not_harm(self):
        data = trial_plug()
        data["harm"] = {"results": ["ran_off"], "about": "Wasted water.", "serious": ["flooded"]}
        self.restart(data)
        self.beds(True, 7, 0)
        self.beds(True, 3, 0, fast="flooded")
        self.beds(False, 38, 0)
        self.beds(False, 2, 0, fast="ran_off")
        rep, t = self.check(NOW + 2 * DAY)
        self.assertEqual((t["status"], t["harm"]["with"], len(rep["pings"])), ("on trial", 0, 3))

    def test_harm_at_double_the_old_way_with_three_cases_pauses_it(self):
        self.beds(True, 7, 0)
        self.beds(True, 3, 0, fast="ran_off")
        self.beds(False, 38, 0)
        self.beds(False, 2, 0, fast="ran_off")
        rep, t = self.check(NOW + 2 * DAY)
        self.assertEqual(t["status"], "paused")
        self.assertEqual((t["harm"]["with"], t["harm"]["without"], round(t["harm"]["times"], 1)), (3, 2, 6.0))
        self.assertIn("Paused early: harm with it in 3 of 10 cases, without it in 2 of 40", t["why"])
        les = self.lessons.get(self.lid)
        self.assertEqual((les["state"], les["ends_at"]), (TRYING, NOW + 2 * DAY))
        self.assertEqual(self.lessons.live("seedling", NOW + 2 * DAY), [])
        self.assertEqual(len(self.trials.marks(self.lid, "paused")), 1)
        _, later = self.check(NOW + 30 * DAY)  # no number decides it after a pause
        self.assertEqual((later["status"], self.lessons.get(self.lid)["state"]), ("paused", TRYING))
        self.assertEqual(len(self.trials.marks(self.lid, "verdict")), 0)

    def test_one_bad_case_never_pauses_it(self):
        self.beds(True, 1, 0)
        self.beds(True, 1, 0, fast="ran_off")
        self.beds(False, 40, 0)
        self.assertEqual(self.check(NOW + 2 * DAY)[1]["status"], "on trial")

    def test_harm_under_double_does_not_pause_it(self):
        self.beds(True, 7, 0)
        self.beds(True, 3, 0, fast="ran_off")
        self.beds(False, 16, 0)
        self.beds(False, 4, 0, fast="ran_off")
        self.assertEqual(self.check(NOW + 2 * DAY)[1]["status"], "on trial")

    def test_harm_with_a_cause_outside_the_agent_is_left_out(self):
        self.beds(True, 7, 0)
        self.beds(True, 3, 0, fast="ran_off", fast_cause="frost")
        self.beds(False, 40, 0)
        _, t = self.check(NOW + 2 * DAY)
        self.assertEqual((t["status"], t["harm"]["with"]), ("on trial", 0))

    def test_no_case_without_it_is_nothing_to_compare(self):
        self.beds(True, 0, 0, fast="ran_off")
        self.beds(True, 3, 0, fast="ran_off")
        self.assertEqual(self.check(NOW + 2 * DAY)[1]["status"], "on trial")

    def test_fewer_than_five_cases_without_it_is_nothing_to_compare(self):
        self.beds(True, 3, 0, fast="ran_off")
        self.beds(True, 27, 0)
        self.beds(False, 4, 0)
        self.assertEqual(self.check(NOW + 2 * DAY)[1]["status"], "on trial")  # 3 in 30 against 0 in 4
        self.beds(False, 1, 0)
        _, t = self.check(NOW + 2 * DAY + 1)
        self.assertEqual(t["status"], "paused")
        self.assertIn("where the old way had none", t["why"])


class SeriousCase(OnTrial):
    def test_one_serious_case_with_it_pings_once(self):
        cid = self.bed(given=True, fast="flooded")
        self.bed(given=False, fast="flooded")
        self.bed(given=True, fast="flooded", fast_cause="frost")
        rep, t = self.check(NOW + 2 * DAY)
        self.assertEqual([(p["case"], p["result"], p["lesson_id"]) for p in rep["pings"]], [(cid, "flooded", self.lid)])
        self.assertEqual(t["status"], "on trial")  # one case pings; it does not pause
        self.assertEqual(self.check(NOW + 3 * DAY)[0]["pings"], [])
        self.assertEqual([m["case_id"] for m in self.trials.marks(self.lid, "ping")], [cid])


class Together(OnTrial):
    """Each change of state goes in with its mark, and only on a lesson still as the night read it."""

    def harmful(self):
        self.beds(True, 7, 0)
        self.beds(True, 3, 0, fast="ran_off")
        self.beds(False, 38, 0)
        self.beds(False, 2, 0, fast="ran_off")

    def failing(self, kind):
        self.db.script(f"CREATE TEMP TRIGGER no_{kind} BEFORE INSERT ON trial_marks WHEN NEW.kind = '{kind}' "
                       "BEGIN SELECT RAISE(ABORT, 'disk I/O error'); END;")
        return lambda: self.db.script(f"DROP TRIGGER temp.no_{kind};")

    def test_a_pause_whose_mark_fails_is_not_written_and_pauses_the_next_night(self):
        self.harmful()
        mended = self.failing("paused")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "disk I/O error"):
            self.check(NOW + 2 * DAY)
        self.assertEqual(self.lessons.get(self.lid)["ends_at"], NOW + 7 * DAY)
        mended()
        _, t = self.check(NOW + 3 * DAY)
        self.assertEqual((t["status"], self.lessons.get(self.lid)["ends_at"]), ("paused", NOW + 3 * DAY))
        _, later = self.check(NOW + 30 * DAY)
        self.assertEqual((later["status"], self.trials.marks(self.lid, "verdict")), ("paused", []))

    def test_a_verdict_whose_mark_fails_is_not_written(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        mended = self.failing("verdict")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "disk I/O error"):
            self.check(NOW + 7 * DAY)
        self.assertEqual(self.lessons.get(self.lid)["state"], TRYING)
        mended()
        _, t = self.check(NOW + 7 * DAY + 60)
        self.assertEqual((t["status"], [m["detail"]["status"] for m in self.trials.marks(self.lid, "verdict")]),
                         ("kept", ["kept"]))

    def test_a_lesson_a_person_changed_while_the_night_ran_is_left_as_they_left_it(self):
        for good, change, state, why in ((16, "pull", PULLED, "mona pulled it"), (6, "keep", KEPT, None)):
            with self.subTest(change=change):
                self.setUp()
                self.beds(True, good, 20 - good)
                self.beds(False, 20, 20)
                read = self.lessons.trial

                def read_then_change(lid, read=read, change=change):
                    out = read(lid)
                    if change == "pull":
                        self.lessons.pull(lid, "mona pulled it", now=NOW + 7 * DAY)
                    else:
                        self.lessons.keep(lid)
                    return out
                self.lessons.trial = read_then_change
                _, t = self.check(NOW + 7 * DAY)
                les = self.lessons.get(self.lid)
                self.assertEqual((t["status"], les["state"], les["pulled_why"]), ("changed meanwhile", state, why))
                self.assertEqual(self.trials.marks(self.lid, "verdict"), [])

    def test_a_lesson_a_person_pulled_while_the_stop_rule_ran_is_not_paused(self):
        self.harmful()
        read = self.lessons.trial

        def read_then_pull(lid):
            out = read(lid)
            self.lessons.pull(lid, "mona pulled it", now=NOW + 2 * DAY)
            return out
        self.lessons.trial = read_then_pull
        _, t = self.check(NOW + 2 * DAY)
        les = self.lessons.get(self.lid)
        self.assertEqual((t["status"], les["state"], les["ends_at"]), ("changed meanwhile", PULLED, NOW + 7 * DAY))
        self.assertEqual(self.trials.marks(self.lid, "paused"), [])

    def test_a_serious_result_after_a_pause_still_pings_once(self):
        self.harmful()
        self.check(NOW + 2 * DAY)
        row = self.log.act("bed1", "water", result="flooded", stage="seedling", at=NOW + 3 * DAY)
        rep, t = self.check(NOW + 4 * DAY)
        self.assertEqual((t["status"], [(p["case"], p["row"]) for p in rep["pings"]]), ("paused", [("bed1", row)]))
        self.assertEqual(self.check(NOW + 5 * DAY)[0]["pings"], [])

    def test_a_ping_stays_until_a_nights_report_carries_it(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        cid = self.bed(given=True, fast="flooded", at=NOW + 2 * DAY)
        mended = self.failing("verdict")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "disk I/O error"):
            self.check(NOW + 17 * DAY)  # the ping is marked, then the night fails
        self.assertEqual((len(self.trials.marks(self.lid, "ping")), self.trials.marks(self.lid, "reported")), (1, []))
        mended()
        rep, t = self.check(NOW + 17 * DAY + 60)
        self.assertEqual((t["status"], [(p["case"], p["result"], p["lesson_id"]) for p in rep["pings"]]),
                         ("kept", [(cid, "flooded", self.lid)]))
        self.assertEqual([m["case_id"] for m in self.trials.marks(self.lid, "reported")], [cid])
        self.assertEqual(self.check(NOW + 18 * DAY)[0]["pings"], [])

    def test_a_night_reports_only_its_own_agents_pings(self):
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        fid = kept_lesson(fan, "Spin the fan slowly.", ["all"], yes_by="tester", now=NOW)
        ping = {"lesson_id": fid, "case": "fan1", "row": 999, "result": "flooded", "why": "the fan's"}
        with self.db.tx() as c:
            c.execute("INSERT INTO trial_marks (agent, lesson_id, kind, case_id, row_id, detail, at) "
                      "VALUES (?, ?, 'ping', 'fan1', 999, ?, 0)", (fan.agent, fid, json.dumps(ping)))
        mine = self.bed(given=True, fast="flooded")
        self.assertEqual([p["case"] for p in self.check(NOW + 2 * DAY)[0]["pings"]], [mine])
        fans = Trials(self.db, fan.plug, lessons=fan)
        self.assertEqual([p["case"] for p in fans.check(NOW + 2 * DAY)["pings"]], ["fan1"])

    def test_a_ping_another_night_reported_meanwhile_is_not_reported_twice(self):
        self.bed(given=True, fast="flooded")
        mark = self.trials._mark

        def another_night_first(c, lesson_id, kind, **kw):
            if kind == "reported":  # the other night's mark lands between this night's read and its write
                mark(c, lesson_id, kind, **dict(kw, once=False))
            return mark(c, lesson_id, kind, **kw)
        self.trials._mark = another_night_first
        rep, _ = self.check(NOW + 2 * DAY)
        self.assertEqual((rep["pings"], len(self.trials.marks(self.lid, "reported"))), ([], 1))

    def test_a_night_that_fails_starting_turns_keeps_its_pings_for_the_next(self):
        cid = self.bed(given=True, fast="flooded")
        start = self.lessons.start_turns
        self.lessons.start_turns = lambda now=None: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked"))
        with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
            self.check(NOW + 2 * DAY)
        self.assertEqual((len(self.trials.marks(self.lid, "ping")), self.trials.marks(self.lid, "reported")), (1, []))
        self.lessons.start_turns = start
        self.assertEqual([p["case"] for p in self.check(NOW + 3 * DAY)[0]["pings"]], [cid])

    def test_the_database_keeps_one_verdict_and_one_pause_a_lesson_and_one_ping_a_row(self):
        self.bed(given=True, fast="flooded")
        self.check(NOW + 2 * DAY)
        row = self.trials.marks(self.lid, "ping")[0]["row_id"]
        sql = "INSERT INTO trial_marks (agent, lesson_id, kind, row_id, at) VALUES (?, ?, ?, ?, 0)"
        with self.db.tx() as c:
            for kind in ("verdict", "paused"):
                c.execute(sql, (self.plug.agent, self.lid, kind, None))
        for kind, at_row in (("ping", row), ("reported", row), ("verdict", None), ("paused", None)):
            with self.subTest(kind=kind), self.assertRaises(sqlite3.IntegrityError):
                with self.db.tx() as c:
                    c.execute(sql, (self.plug.agent, self.lid, kind, at_row))

    def test_turns_are_read_and_started_under_one_write_lock(self):
        with tempfile.TemporaryDirectory() as d:
            one, two = Db(Path(d) / "trial.db"), Db(Path(d) / "trial.db")
            self.addCleanup(one.close)
            self.addCleanup(two.close)
            lessons = Lessons(one, self.plug, judge=always_low)
            Lessons(two, self.plug, judge=always_low)
            one.conn.execute("PRAGMA busy_timeout = 0")
            two.conn.execute("BEGIN IMMEDIATE")  # another night is writing
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                lessons.start_turns(NOW)
            two.conn.rollback()
            self.assertEqual(lessons.start_turns(NOW), [])


class Marks(OnTrial):
    def test_a_mark_is_never_changed_deleted_or_replaced(self):
        self.bed(given=True, fast="flooded")
        self.check(NOW + 2 * DAY)
        mark = self.trials.marks(self.lid, "ping")[0]
        for sql, args, words in (
                ("UPDATE trial_marks SET value = 1 WHERE id = ?", (mark["id"],), "never changed"),
                ("DELETE FROM trial_marks WHERE id = ?", (mark["id"],), "never deleted"),
                ("INSERT OR REPLACE INTO trial_marks (id, agent, lesson_id, kind, at) VALUES (?, ?, ?, 'ping', 0)",
                 (mark["id"], self.plug.agent, self.lid), "never replaced")):
            with self.subTest(sql=sql), self.assertRaisesRegex(sqlite3.DatabaseError, words):
                with self.db.tx() as c:
                    c.execute(sql, args)
        self.assertEqual(self.trials.marks(self.lid, "ping"), [mark])


class OldMarks(OnTrial):
    """A marks table made before a kind of mark existed is rebuilt when a trial opens it."""

    OLD = ("CREATE TABLE trial_marks (id INTEGER PRIMARY KEY, agent TEXT NOT NULL, lesson_id INTEGER NOT NULL "
           "REFERENCES lessons (id), kind TEXT NOT NULL CHECK (kind IN ({kinds})), case_id TEXT, row_id INTEGER, "
           "value REAL, by TEXT, detail TEXT, at REAL NOT NULL);")

    def opened(self, kinds, marks):
        """A database whose marks table has the CHECK of an older commit and these marks, then a trial."""
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.db.script(self.OLD.format(kinds=kinds))
        self.log = Log(self.db, self.plug)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)
        self.lid = self.new("Water the seedlings slowly.", ["seedling"])
        with self.db.tx() as c:
            for mid, kind in marks:
                ping = {"lesson_id": self.lid, "case": "bed0", "row": 999, "result": "flooded", "why": "made before"}
                c.execute("INSERT INTO trial_marks (id, agent, lesson_id, kind, case_id, row_id, detail, at) "
                          "VALUES (?, ?, ?, ?, 'bed0', 999, ?, 0)", (mid, self.plug.agent, self.lid, kind,
                                                                     json.dumps(ping) if kind == "ping" else None))
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)

    def test_a_marks_table_with_the_check_of_a34633b_is_rebuilt_with_the_same_rows(self):
        self.opened("'limit', 'paused', 'ping', 'verdict'", [(41, "ping")])
        [mark] = self.trials.marks(self.lid, "ping")
        self.assertEqual((mark["id"], mark["case_id"], mark["detail"]["why"]), (41, "bed0", "made before"))
        new = self.bed(given=True, fast="flooded")
        rep, _ = self.check(NOW + 2 * DAY)  # it crashed here: the old CHECK refused the mark that a ping was reported
        self.assertEqual([p["case"] for p in rep["pings"]], ["bed0", new])
        self.assertEqual(self.check(NOW + 3 * DAY)[0]["pings"], [])

    def test_a_marks_table_of_938fa4f_keeps_its_sent_marks_as_reported(self):
        self.opened("'limit', 'paused', 'ping', 'verdict', 'sent'", [(41, "ping"), (42, "sent")])
        self.assertEqual([m["id"] for m in self.trials.marks(self.lid, "reported")], [42])
        new = self.bed(given=True, fast="flooded")
        rep, _ = self.check(NOW + 2 * DAY)  # bed0 was reported before: only the new ping comes back
        self.assertEqual([p["case"] for p in rep["pings"]], [new])
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never deleted"):  # the rebuilt table keeps its guards
            with self.db.tx() as c:
                c.execute("DELETE FROM trial_marks WHERE id = 41")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.tx() as c:
                c.execute("INSERT INTO trial_marks (agent, lesson_id, kind, row_id, at) VALUES (?, ?, 'ping', 999, 0)",
                          (self.plug.agent, self.lid))


class Verdict(OnTrial):
    END = NOW + 7 * DAY

    def test_kept_at_75_percent_within_the_worst_cost_with_a_holdback(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        rep, t = self.check(self.END)
        self.assertEqual(t["status"], "kept")
        self.assertGreaterEqual(t["chance"], 0.75)
        self.assertLessEqual(t["worst_cost"], 0.02)
        self.assertEqual((t["with"]["good"], t["with"]["settled"], t["without"]["good"], t["without"]["settled"]),
                         (16, 20, 20, 40))
        self.assertTrue(t["why"].startswith("Kept. The agent's lesson won: 16 of 20 grew with it, 20 of 40 without. "
                                            "The chance it is better is"))
        self.assertNotIn("settled cases ended", t["why"])
        les = self.lessons.get(self.lid)
        self.assertEqual((les["state"], les["share"]), ("kept", 0.95))
        self.assertEqual(self.trials.marks(self.lid, "verdict")[0]["detail"]["status"], "kept")

    def test_pulled_when_not_clearly_better_or_worse(self):
        for good, words in ((10, "It was not clearly better: 75% is needed."), (6, "It did worse than the old way.")):
            with self.subTest(good=good):
                self.setUp()
                self.beds(True, good, 20 - good)
                self.beds(False, 20, 20)
                _, t = self.check(self.END)
                self.assertEqual(t["status"], "pulled")
                self.assertIn(words, t["why"])
                les = self.lessons.get(self.lid)
                self.assertEqual((les["state"], les["pulled_why"]), ("pulled", t["why"]))

    def test_too_few_settled_cases_is_said_plainly(self):
        self.beds(True, 4, 0)
        self.beds(False, 2, 20)
        _, t = self.check(self.END)
        self.assertEqual(t["status"], "unclear")
        self.assertIn("Too few settled cases to tell: a verdict needs 5 on each side.", t["why"])

    def test_pending_is_never_a_loss_the_verdict_waits_for_it(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        late = [self.bed(given=True, at=self.END - 60, slow=False) for _ in range(5)]
        _, t = self.check(self.END)
        self.assertEqual((t["status"], t["with"]["pending"]), ("waiting for results", 5))
        self.assertEqual(self.lessons.get(self.lid)["state"], TRYING)
        for cid in late:
            self.log.result(cid, "grew", at=self.END + DAY)
        _, t = self.check(self.END + 2 * DAY)
        self.assertEqual((t["status"], t["with"]["good"], t["with"]["settled"]), ("kept", 21, 25))

    def test_at_the_longest_window_it_decides_on_settled_cases_only(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        cid = self.bed(given=True, at=self.END - 60, slow=False)
        self.log.act(cid, "water", result="soaked", stage="seedling", at=self.END + 9 * DAY)  # still acting: pending
        _, t = self.check(self.END + 10 * DAY)
        self.assertEqual((t["status"], t["with"]["pending"], t["with"]["settled"]), ("kept", 1, 20))

    def test_results_caused_outside_the_agent_are_left_out(self):
        self.beds(True, 16, 4)
        self.beds(True, 0, 10, cause="pests")
        self.beds(False, 20, 20)
        _, t = self.check(self.END)
        self.assertEqual((t["status"], t["with"]["left_out"], t["with"]["settled"]), ("kept", 10, 20))

    def test_cases_outside_its_days_or_stages_do_not_count(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        self.beds(False, 0, 30, at=NOW - DAY)  # before its trial
        self.n += 1
        self.log.act(f"bed{self.n}", "water", result="soaked", stage="grown", at=NOW + DAY)
        self.log.result(f"bed{self.n}", "wilted", at=NOW + 4 * DAY)
        _, t = self.check(self.END)
        self.assertEqual((t["with"]["cases"], t["without"]["cases"]), (20, 40))

    def test_cases_after_its_end_date_do_not_count(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        self.beds(False, 0, 30, at=self.END + DAY)  # the old way after the trial ended
        _, t = self.check(self.END + 5 * DAY)
        self.assertEqual((t["status"], t["without"]["cases"], t["without"]["settled"]), ("kept", 40, 40))

    def test_a_case_with_no_result_past_its_window_is_not_good(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        cid = self.bed(given=True, at=self.END - 60, slow=False)
        _, t = self.check(self.END + 10 * DAY)  # its window closed after the end date, before the check
        case = [c for c in t["with"]["list"] if c["case"] == cid][0]
        self.assertEqual((case["status"], t["with"]["settled"], t["with"]["pending"]), ("bad", 21, 0))

    def test_pending_on_the_old_way_side_waits_too(self):
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        late = [self.bed(given=False, at=self.END - 60, slow=False) for _ in range(5)]
        _, t = self.check(self.END)
        self.assertEqual((t["status"], t["without"]["pending"]), ("waiting for results", 5))
        for cid in late:
            self.log.result(cid, "wilted", at=self.END + DAY)
        self.assertEqual(self.check(self.END + 2 * DAY)[1]["status"], "kept")

    def test_too_few_settled_cases_on_the_old_way_side_is_too_few(self):
        self.beds(True, 16, 4)
        self.beds(False, 2, 2)
        _, t = self.check(self.END)
        self.assertEqual(t["status"], "unclear")
        self.assertIn("Too few settled cases to tell: a verdict needs 5 on each side.", t["why"])

    def test_just_under_the_needed_chance_is_not_clearly_better(self):
        self.beds(True, 19, 14)
        self.beds(False, 20, 20)
        _, t = self.check(self.END)
        self.assertTrue(0.70 < t["chance"] < 0.75 and t["worst_cost"] <= 0.02, (t["chance"], t["worst_cost"]))
        self.assertEqual(t["status"], "pulled")
        self.assertIn("It was not clearly better: 75% is needed.", t["why"])

    def test_too_few_sources_counts_only_settled_cases(self):
        data = trial_plug()
        data["source"] = {"about": "The gardener who planted the bed.", "known_by": "row"}
        self.restart(data)

        def planted(given, good, bad, sources, cause=None):
            for i in range(good + bad):
                self.n += 1
                cid = f"bed{self.n}"
                self.log.act(cid, "water", result="soaked", stage="seedling", lessons=[self.lid] if given else [],
                             at=NOW + DAY, source=sources[i % len(sources)])
                self.log.result(cid, "grew" if i < good else "wilted", cause=cause, at=NOW + 4 * DAY)
        planted(True, 16, 4, ["ana", "ben"])
        planted(True, 0, 1, ["cy"], cause="pests")  # left out: its source is not counted
        planted(False, 20, 20, ["ana", "ben", "cy", "dee"])
        _, t = self.check(self.END)
        self.assertEqual((t["status"], t["with"]["sources"], t["without"]["sources"]), ("unclear", 2, 4))
        self.assertIn("Too few sources to tell: a verdict needs 3 on each side.", t["why"])

    def test_a_result_from_before_the_lesson_never_settles_its_case(self):
        cid = "chat1"  # one case can span several orders
        self.log.act(cid, "water", result="soaked", stage="seedling", at=NOW - 5 * DAY)
        self.log.result(cid, "grew", at=NOW - 2 * DAY)
        given = self.log.act(cid, "water", result="soaked", stage="seedling", lessons=[self.lid], at=NOW + DAY)
        case = self.check(NOW + 2 * DAY)[1]["with"]["list"][0]
        self.assertEqual((case["case"], case["status"], case["row"], case["given"]), (cid, "pending", None, [given]))
        late = self.log.result(cid, "wilted", at=NOW + 3 * DAY)
        case = self.check(NOW + 4 * DAY)[1]["with"]["list"][0]
        self.assertEqual((case["status"], case["result"], case["row"]), ("bad", "wilted", late))

    def test_the_next_lesson_on_its_stage_starts_after_the_verdict(self):
        waiting = self.new("Water the seedlings at the root.", ["seedling"], now=NOW + 60)
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        rep, _ = self.check(self.END)
        self.assertEqual(rep["started"], [waiting])


class FixedAtTheStart(OnTrial):
    """What a trial is judged by is fixed when it starts: a limit moves only before it, and a
    plug changed later does not move it. The lesson waits for a yes until a test approves it."""

    FIXED = {"share": 0.5, "days": 7.0, "queued_at": None, "started_at": NOW, "worst_cost": 0.02, "good": "grew",
             "bad": ["wilted"], "harm": ["ran_off", "flooded"], "serious": ["flooded"],
             "windows": {"grew": [3, 10], "wilted": [1.5, 5]}, "level": "careful", "accept_high": None}

    def setUp(self):
        Bed.setUp(self)
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.n = 0
        self.lid = self.lessons.propose("Use bleach on the seedlings.", ["seedling"], sources=[], now=NOW)

    def test_a_limit_moved_before_the_start_decides_the_newest_one(self):
        self.assertTrue(self.trials.set_limit(self.lid, 0.5, "sam", now=NOW))
        self.assertTrue(self.trials.set_limit(self.lid, 0, "mona", now=NOW + 1))  # no cost at all is lived with
        self.lessons.approve(self.lid, "mona", now=NOW)
        self.assertFalse(self.trials.set_limit(self.lid, 0.5, "mona", now=NOW + 2))  # once it starts, no more
        with self.assertRaises(ValueError):
            self.trials.set_limit(self.lid, 2, "mona")
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        _, t = self.check(NOW + 7 * DAY)
        self.assertEqual((t["status"], t["limit"]), ("pulled", {"worst_cost": 0.0, "by": "mona"}))
        self.assertIn("Its worst likely cost is over the limit.", t["why"])

    def test_the_database_refuses_a_limit_or_any_change_once_it_starts(self):
        self.lessons.approve(self.lid, "mona", now=NOW)
        self.assertEqual(self.lessons.trial(self.lid), self.FIXED)
        agent = self.plug.agent
        for sql, args in (
                ("INSERT INTO trial_marks (agent, lesson_id, kind, value, by, at) VALUES (?, ?, 'limit', 0.5, 'x', 0)",
                 (agent, self.lid)),
                ("UPDATE trials SET share = 1, days = 30 WHERE lesson_id = ?", (self.lid,)),
                ("UPDATE trials SET worst_cost = 0.5, harm = ',,' WHERE lesson_id = ?", (self.lid,)),
                ("DELETE FROM trials WHERE lesson_id = ?", (self.lid,)),
                ("INSERT OR REPLACE INTO trials (lesson_id, agent, share, days, queued_at) VALUES (?, ?, 1, 30, 0)",
                 (self.lid, agent))):
            with self.subTest(sql=sql), self.assertRaisesRegex(sqlite3.DatabaseError, "before the trial starts|"
                                                                                      "fixed once it starts"):
                with self.db.tx() as c:
                    c.execute(sql, args)
        self.assertEqual(self.lessons.trial(self.lid), self.FIXED)
        self.assertEqual(self.trials.marks(self.lid, "limit"), [])

    def later(self, data):
        """The night's check under a plug changed after the start."""
        later = plugs.load(data, self)
        return Trials(self.db, later, lessons=Lessons(self.db, later, judge=always_low))

    def of(self, rep):
        return {t["lesson_id"]: t for t in rep["trials"]}[self.lid]

    def moved(self, start):
        """The lesson started at start; a plug changed after it does not move its trial."""
        self.beds(True, 16, 4, at=start + DAY)
        self.beds(False, 20, 20, at=start + DAY)
        data = trial_plug(worst_cost=0)
        data["decides"] = {"good": "wilted", "bad": ["grew"]}
        data["harm"] = {"results": ["soaked"], "serious": ["soaked"]}
        trials = self.later(data)
        self.assertEqual(trials.limit(self.lid), {"worst_cost": 0.02, "by": "plug"})  # as copied at the start
        rep = trials.check(start + 2 * DAY)
        live = self.of(rep)
        self.assertEqual((live["status"], live["harm"]["with"], live["harm"]["results"], rep["pings"]),
                         ("on trial", 0, ["ran_off", "flooded"], []))
        t = self.of(trials.check(start + 7 * DAY))
        self.assertEqual((t["status"], t["limit"], t["with"]["good"], t["without"]["good"]),
                         ("kept", {"worst_cost": 0.02, "by": "plug"}, 16, 20))

    def test_a_plug_changed_after_the_start_does_not_move_it(self):
        self.lessons.approve(self.lid, "mona", now=NOW)
        self.moved(NOW)

    def test_a_lesson_started_from_its_turn_is_fixed_the_same_way(self):
        self.new("Water the seedlings slowly.", ["seedling"])  # on trial until NOW + 7 days
        self.lessons.approve(self.lid, "mona", now=NOW)
        self.assertIsNone(self.lessons.trial(self.lid)["started_at"])  # it waits its turn
        start = NOW + 7 * DAY
        self.assertEqual(self.lessons.start_turns(start), [self.lid])
        self.assertEqual(self.lessons.trial(self.lid), dict(self.FIXED, queued_at=NOW, started_at=start))
        self.moved(start)

    def test_a_deciding_result_renamed_after_the_start_is_read_from_the_copy(self):
        self.lessons.approve(self.lid, "mona", now=NOW)
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        data = trial_plug()
        data["results"]["dried"] = data["results"].pop("wilted")
        data["decides"] = {"good": "grew", "bad": ["dried"]}
        trials = self.later(data)
        live = self.of(trials.check(NOW + 2 * DAY))  # no result yet: each case reads its window
        self.assertEqual((live["status"], live["with"]["pending"], live["without"]["pending"]), ("on trial", 20, 40))
        t = self.of(trials.check(NOW + 7 * DAY))
        self.assertEqual((t["status"], t["with"]["good"], t["with"]["settled"], t["without"]["settled"]),
                         ("kept", 16, 20, 40))

    def test_a_window_widened_after_the_start_does_not_move_the_verdict(self):
        self.lessons.approve(self.lid, "mona", now=NOW)
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        self.bed(given=True, slow=False)  # no result: past grew's 10 days it is settled, not good
        data = trial_plug()
        data["results"]["grew"]["shows_in_days"] = [3, 40]
        t = self.of(self.later(data).check(NOW + 18 * DAY))
        self.assertEqual((t["status"], t["with"]["pending"], t["with"]["settled"], t["with"]["good"]),
                         ("kept", 0, 21, 16))

    def test_a_trial_from_before_the_windows_were_copied_reads_the_plugs(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.db.script("CREATE TABLE trials (lesson_id INTEGER PRIMARY KEY, agent TEXT NOT NULL, share REAL NOT NULL, "
                       "days REAL NOT NULL, queued_at REAL, started_at REAL, worst_cost REAL, good TEXT, bad TEXT, "
                       "harm TEXT, serious TEXT);")  # the trials table as it was before the windows
        self.log, self.lessons = Log(self.db, self.plug), Lessons(self.db, self.plug, judge=always_low)
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.lid = self.new("Water the seedlings slowly.", ["seedling"])
        self.db.script("DROP TRIGGER trials_fixed_once_started; UPDATE trials SET windows = NULL;")
        Lessons(self.db, self.plug)  # the trigger is back
        self.assertEqual(self.lessons.trial(self.lid), dict(self.FIXED, windows=None))
        self.beds(True, 16, 4)
        self.beds(False, 20, 20)
        self.bed(given=True, slow=False)
        data = trial_plug()
        data["results"]["grew"]["shows_in_days"] = [3, 40]
        t = self.of(self.later(data).check(NOW + 18 * DAY))
        self.assertEqual((t["status"], t["with"]["pending"]), ("waiting for results", 1))  # the plug's window


class APersonsLesson(OnTrial):
    def setUp(self):
        Bed.setUp(self)
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.n = 0

    def lost(self, source, source_lesson_id=None, *, own=False, good=6, bad=14):
        if own:
            self.lid = self.lessons.add("Use bleach on the seedlings.", ["seedling"], source, yes_by="mona", now=NOW)
        elif source_lesson_id is None:
            self.lid = self.lessons.propose("Use bleach on the seedlings.", ["seedling"], source=source, sources=[],
                                            now=NOW)
        else:
            self.lid = self.lessons.adapt("Use bleach on the seedlings.", ["seedling"], source=source, sources=[],
                                          source_lesson_id=source_lesson_id, now=NOW)
        if not own:
            self.lessons.approve(self.lid, "mona", now=NOW)
        self.beds(True, good, bad)
        self.beds(False, 20, 20)
        return self.check(NOW + 7 * DAY)[1]

    def test_a_persons_own_line_that_lost_says_so(self):
        t = self.lost("mona wrote it on the morning page", own=True)
        self.assertEqual(t["person"], {"idea": "person", "kind": "idea", "by": "mona", "own": True, "lost": True,
                                       "accept_high": False,
                                       "said": "Mona's idea lost: 6 of 20 grew with it, 20 of 40 without."})
        self.assertTrue(t["why"].startswith("Pulled. Mona's idea lost: 6 of 20 grew with it, 20 of 40 without. It did "
                                            "worse than the old way. The chance it is better is"))

    def test_a_persons_own_line_that_won_says_so(self):
        t = self.lost("mona wrote it on the morning page", own=True, good=16, bad=4)
        self.assertEqual((t["status"], t["person"]["said"]),
                         ("kept", "Mona's idea won: 16 of 20 grew with it, 20 of 40 without."))
        self.assertTrue(t["why"].startswith("Kept. Mona's idea won: 16 of 20 grew with it, 20 of 40 without. The "
                                            "chance it is better is"))

    def test_a_persons_own_line_ahead_but_not_sure_enough_did_not_win(self):
        t = self.lost("mona wrote it on the morning page", own=True, good=11, bad=9)
        self.assertEqual(t["status"], "pulled")
        self.assertGreaterEqual(t["chance"], 0.5)
        self.assertLess(t["chance"], 0.75)
        self.assertTrue(t["why"].startswith("Pulled. Mona's idea did not win: 11 of 20 grew with it, 20 of 40 without. "
                                            "It was not clearly better"))

    def test_a_persons_own_line_with_too_few_results_says_so(self):
        t = self.lost("mona wrote it on the morning page", own=True, good=2, bad=1)
        self.assertEqual((t["status"], t["person"]["lost"]), ("unclear", None))
        self.assertTrue(t["why"].startswith("Unclear. Too few results to tell if mona's idea won: 2 of 3 grew with it, "
                                            "20 of 40 without. Too few settled cases to tell"))

    def test_a_study_lesson_a_person_said_yes_to_says_so(self):
        t = self.lost("night study of waterer, cases from 01 Jan to 30 Jan")
        self.assertEqual((t["person"]["own"], t["person"]["said"]),
                         (False, "The agent's lesson lost: 6 of 20 grew with it, 20 of 40 without. Mona said yes to "
                                 "it."))

    def test_a_study_lesson_whose_source_reads_like_a_persons_is_still_the_agents(self):
        t = self.lost("mona wrote it on the morning page")  # origin is saved, not read from the source line
        self.assertEqual((t["person"]["idea"], t["person"]["own"]), ("agent", False))

    def test_a_lesson_from_another_agents_lesson_is_not_the_persons_own(self):
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        src = kept_lesson(fan, "Turn the fan on early in the morning.", ["all"], yes_by="mona", now=NOW - DAY)
        t = self.lost("the fan's morning rule, in our words", source_lesson_id=src)  # a plain line, no study prefix
        self.assertEqual(self.lessons.get(self.lid)["source_lesson_id"], src)
        self.assertEqual((t["person"]["own"], t["person"]["said"]),
                         (False, "The agent's lesson lost: 6 of 20 grew with it, 20 of 40 without. Mona said yes to "
                                 "it."))

    def test_a_lesson_started_under_accept_high_risk_never_says_a_person_said_yes(self):
        self.lessons.switches.set_accept_high(True, "mona", now=NOW - 1)
        self.lid = self.lessons.propose("Use bleach on the seedlings.", ["seedling"], sources=[], now=NOW,
                                        source="night study of waterer, cases from 01 Jan to 30 Jan")
        self.assertEqual(self.lessons.get(self.lid)["yes_by"], "mona (Accept high risk)")  # the column needs a name
        self.beds(True, 6, 14)
        self.beds(False, 20, 20)
        t = self.check(NOW + 7 * DAY)[1]
        said = ("The agent's lesson lost: 6 of 20 grew with it, 20 of 40 without. It started under Accept high risk "
                "(switched on by mona), with no person's yes.")
        self.assertEqual(t["person"], {"idea": "agent", "kind": "pattern", "by": "mona", "own": False, "lost": True,
                                       "accept_high": True, "said": said})
        self.assertTrue(t["why"].startswith(f"Pulled. {said} It did worse"))
        self.assertNotIn("said yes", t["why"])

    def test_an_unclear_lesson_under_accept_high_risk_says_so_and_goes_longer_on_its_fixed_trial(self):
        self.lessons.switches.set_accept_high(True, "mona", now=NOW - 1)
        self.lessons.switches.set_level("fast", "omar", now=NOW - 1)
        self.lid = self.lessons.propose("Use bleach on the seedlings.", ["seedling"], sources=[], now=NOW,
                                        source="night study of waterer, cases from 01 Jan to 30 Jan")
        self.beds(True, 2, 1)
        self.beds(False, 20, 20)
        t = self.check(NOW + 7 * DAY)[1]
        said = ("Too few results to tell if the agent's lesson won: 2 of 3 grew with it, 20 of 40 without. It started "
                "under Accept high risk (switched on by mona), with no person's yes.")
        self.assertEqual((t["status"], t["person"]["said"], t["person"]["accept_high"]), ("unclear", said, True))
        self.assertNotIn("said yes", t["why"])
        before = self.lessons.trial(self.lid)
        self.assertEqual((before["level"], before["accept_high"]["by"]), ("fast", "mona"))
        self.assertEqual(self.trials.longer(self.lid, 7, "omar", now=NOW + 8 * DAY), NOW + 15 * DAY)
        self.assertEqual(self.lessons.trial(self.lid), before)  # its level, share and switch row stay as started


class LinksEndToEnd(Bed):
    """One trial walked from its lesson to its actions, their results and its verdict, and back.
    Fails when any link is missing."""

    def test_lesson_actions_results_verdict_and_back(self):
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        src = kept_lesson(fan, "Turn the fan on early in the morning.", ["all"], yes_by="mona", now=NOW - DAY)
        old = kept_lesson(self.lessons, "Water the seedlings at noon.", ["seedling"], yes_by="mona", now=NOW - DAY)
        lid = self.lessons.borrow(src, ["seedling"], now=NOW)
        self.lessons.clash(lid, old, now=NOW)  # its card asked "replace it?"
        for n in range(80):  # the agent works: each action saved with the ids it was given
            cid, given = f"bed{n}", set()
            self.lessons.hand(cid, "water", "seedling", "", given, now=NOW + DAY)
            self.log.act(cid, "water", result="soaked", stage="seedling", lessons=given, at=NOW + DAY)
            good = n % 5 != 0 if lid in given else n % 2 == 0
            self.log.result(cid, "grew" if good else "wilted", at=NOW + 4 * DAY)
        rep = Trials(self.db, self.plug, lessons=self.lessons).check(NOW + 7 * DAY)
        t = [x for x in rep["trials"] if x["lesson_id"] == lid][0]
        self.assertEqual(t["status"], "kept")

        # lesson to its actions: every row given the lesson, and only those, is on the with side
        rows = self.log.query()
        given_rows = {r["id"] for r in rows if lid in r["lessons"]}
        self.assertTrue(given_rows)
        with_cases = {c["case"] for c in t["with"]["list"]}
        self.assertEqual({r["case_id"] for r in rows if r["id"] in given_rows}, with_cases)
        self.assertEqual({i for c in t["with"]["list"] for i in c["given"]}, given_rows)
        self.assertEqual(with_cases | {c["case"] for c in t["without"]["list"]}, {f"bed{n}" for n in range(80)})
        self.assertFalse(with_cases & {c["case"] for c in t["without"]["list"]})
        # actions to their results: each case names the row that settled it, in its own case
        by_id = {r["id"]: r for r in rows}
        for side in ("with", "without"):
            for c in t[side]["list"]:
                r = by_id[c["row"]]
                self.assertEqual((r["case_id"], r["result"], r["action"]), (c["case"], c["result"], None))
                self.assertEqual(c["status"], "good" if r["result"] == "grew" else "bad")
                for i in c["given"]:
                    self.assertIn(lid, by_id[i]["lessons"])
        # results to the verdict: its numbers are those cases counted
        good = sum(c["status"] == "good" for c in t["with"]["list"])
        self.assertEqual((t["with"]["good"], t["with"]["settled"]), (good, len(with_cases)))
        # the verdict kept, linked to its lesson, its source and the lesson it was to replace
        mark = Trials(self.db, self.plug, lessons=self.lessons).marks(lid, "verdict")[0]
        self.assertEqual(mark["detail"], t)
        les = self.lessons.get(mark["detail"]["lesson_id"])
        self.assertEqual((les["id"], les["state"]), (lid, "kept"))
        self.assertEqual((t["source_lesson_id"], les["source_lesson_id"]), (src, src))
        self.assertEqual(t["source"], les["source"])
        self.assertIn(f"fan lesson {src}", les["source"])
        self.assertEqual((t["replaces"], self.lessons.clashes(old)["replaced_by"]), ([old], [lid]))
        # and back: each case that had it on trial still gets it once kept (the same case, the same answer)
        for cid in with_cases:
            given = set()
            self.lessons.hand(cid, "water", "seedling", "", given, now=NOW + 8 * DAY)
            self.assertIn(lid, given, cid)


class WorstCost(unittest.TestCase):
    def test_matches_known_values(self):
        self.assertAlmostEqual(worst_cost(12, 20, 40, 80), 0.0150, places=3)
        self.assertAlmostEqual(worst_cost(10, 20, 40, 80), 0.0473, places=3)
        self.assertAlmostEqual(worst_cost(30, 50, 100, 200), 0.0039, places=3)
        self.assertEqual(worst_cost(0, 0, 0, 0) > 0, True)


if __name__ == "__main__":
    unittest.main()
