"""The night note to another agent (engine/handover.py, DECISIONS items 6, 12, 19 and 33): the night
study's hand over track. A plug names the kinds of pattern in its lost cases that are another
agent's matter; the engine counts them, sends at most one short note a night per receiving agent
only from a kind seen in at least 3 sources, and never writes such a line as a lesson.

The engine tests use the waterer plug with a made up receiving agent, so no business word is
needed. No test calls a model: the spotter and the writer are fakes, and the Meta parts take a
scripted model. No test reads arena/real/, data/ or any .env."""
import contextlib
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import handover
from engine import plug as plug_mod
from engine.fast import guard
from engine.lessons import TRYING, WAITING, Lessons
from engine.log import Log
from engine.study import HANDED, MIN_SOURCES, TAGGED, Study
from kit import model as kit_model
from kit.db import Db
from reflection import PLUG as SALES
from reflection import morning as page_mod
from reflection import night
from reflection import study as parts
from tests import plugs
from tests import study_fakes as fk
from tests.fake_model import FakeModel, clean_env, say

TO = "garden_blog"
HANDS = {TO: {"about": "Writes the garden's posts.",
              "kinds": {"heat": "Beds lost to a heat wave the waterer cannot change.",
                        "playful": "A playful moment at the bed. The waterer never jokes, so it is for the posts, "
                                   "never a lesson."}}}
GARDEN = plugs.changed(plugs.WATERER, hands_over=HANDS)
LINE = "Playful moments come up often at the beds; a light post could carry that mood."
JOKE = {"pattern": "The waterer joked with the bed.", "helps": True,
        "lesson": "Joke with the bed when it is playful.", "situation": "A playful bed.", "stages": ["all"]}
JOKE_IDEA = {"lesson": "Joke with the bed on a calm day.", "situation": "", "stages": ["all"]}
WORDS = "the bed of Ahmed laughed at the hose and said the roses look thirsty"


def always_low(text, high_about, low_about):
    return "low"


class Spotter:
    """Reads the moment mark in a case's steps; a line with "joke" in it is playful."""

    def __init__(self, *, fail=False, fail_lines=False):
        self.fail, self.fail_lines = fail, fail_lines
        self.calls = []

    def __call__(self, plug, kinds, items):
        self.calls.append({"kinds": copy.deepcopy(kinds), "items": copy.deepcopy(items)})
        if self.fail or (self.fail_lines and any("lesson" in i for i in items)):
            raise RuntimeError("the spotter is down")
        out = {}
        for it in items:
            if "steps" in it:
                marks = [s["detail"].get("moment") for s in it["steps"] if isinstance(s.get("detail"), dict)]
                out[it["id"]] = marks[0] if marks and marks[0] else "none"
            else:
                out[it["id"]] = "playful" if "joke" in it["lesson"].lower() else "none"
        return out


class Writer:
    def __init__(self, line=LINE):
        self.line = line
        self.calls = []

    def __call__(self, plug, receiver, found):
        self.calls.append({"receiver": copy.deepcopy(receiver), "found": copy.deepcopy(found)})
        return self.line


class Ideas:
    def __init__(self, *items):
        self.items = list(items)

    def __call__(self, plug, sample, limit, known):
        return copy.deepcopy(self.items)


def lost(log, n, moment, prefix, *, source=None, note=None):
    """n beds that wilted, each with a moment mark; each its own source unless one is given."""
    for i in range(n):
        fk.case(log, f"{prefix}{i}", "water", "soaked", "wilted", stage="seedling", source=source, moment=moment,
                note=note or f"{prefix} round {i}")


class Setup(unittest.TestCase):
    data = GARDEN

    def setUp(self):
        self.plug = plugs.load(self.data, self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.log = Log(self.db, self.plug)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)

    def study(self, *, spotter=None, writer=None, proposer=None, tagger=None, ideas=None, hand=True):
        self.spotter = spotter or Spotter()
        self.writer = writer or Writer()
        track = (handover.Track(self.db, self.plug, spotter=self.spotter, writer=self.writer)
                 if hand else None)
        return Study(self.db, self.plug, proposer=proposer or fk.Proposer(), tagger=tagger or fk.Tagger(),
                     lessons=self.lessons, ideas=ideas, hand_over=track).run(fk.SINCE, fk.UNTIL, now=fk.NOW)


class TheFloor(Setup):
    def test_two_sources_send_no_note(self):
        lost(self.log, 2, "playful", "play")
        rep = self.study()
        self.assertEqual(rep["hand_over"]["notes"], [])
        playful, = [k for k in rep["hand_over"]["kinds"] if k["kind"] == "playful"]
        self.assertEqual((playful["cases"], playful["sources"], playful["verdict"]), (2, 2, handover.FEW_SOURCES))
        self.assertEqual(self.writer.calls, [])
        self.assertEqual(handover.received(self.db, TO), [])

    def test_three_sources_send_one_note(self):
        self.assertEqual(MIN_SOURCES, 3)
        lost(self.log, 3, "playful", "play")
        rep = self.study()
        note, = rep["hand_over"]["notes"]
        self.assertEqual((note["to"], note["kind"], note["text"], note["cases"], note["sources"]),
                         (TO, "playful", LINE, 3, 3))
        self.assertEqual(sorted(note["case_ids"]), ["play0", "play1", "play2"])
        got, = handover.received(self.db, TO)
        self.assertEqual((got["from"], got["kind"], got["text"], got["cases"]), ("waterer", "playful", LINE, 3))
        self.assertEqual(handover.received(self.db, "waterer"), [])

    def test_one_note_a_night_the_kind_with_more_sources(self):
        lost(self.log, 3, "playful", "play")
        lost(self.log, 4, "heat", "hot")
        rep = self.study()
        note, = rep["hand_over"]["notes"]
        self.assertEqual(note["kind"], "heat")
        verdicts = {k["kind"]: k["verdict"] for k in rep["hand_over"]["kinds"]}
        self.assertEqual(verdicts, {"heat": handover.NOTE, "playful": handover.BEATEN})
        self.assertEqual(len(self.writer.calls), 1)


    def test_a_tie_goes_to_the_kind_the_plug_names_first(self):
        self.assertEqual(list(HANDS[TO]["kinds"]), ["heat", "playful"])
        lost(self.log, 3, "playful", "play")
        lost(self.log, 3, "heat", "hot")
        note, = self.study()["hand_over"]["notes"]
        self.assertEqual((note["kind"], note["sources"], note["cases"]), ("heat", 3, 3))

    def test_a_left_out_case_counts_only_when_its_result_was_not_good(self):
        lost(self.log, 2, "playful", "play")
        fk.case(self.log, "frosted", "water", "soaked", "wilted", stage="seedling", cause="frost", moment="playful",
                note="frost round")
        fk.case(self.log, "grown", "water", "soaked", "grew", stage="seedling", cause="frost", moment="playful",
                note="grown round")
        rep = self.study()
        note, = rep["hand_over"]["notes"]
        self.assertEqual(sorted(note["case_ids"]), ["frosted", "play0", "play1"])
        self.assertEqual(sorted(c["case"] for c in rep["left_out"]["cases"]), ["frosted", "grown"])

    def test_the_spotter_reads_blind_views_only(self):
        lost(self.log, 3, "playful", "play")
        self.study()
        views = self.spotter.calls[0]["items"]
        self.assertEqual(len(views), 3)
        for v in views:
            self.assertEqual(set(v), {"id", "steps"})  # no deciding result and no good flag
            self.assertRegex(v["id"], r"^k[0-9]+$")
            self.assertEqual([s.get("result") for s in v["steps"]], ["soaked"])  # no slow result

    def test_over_tagged_lost_cases_the_spotter_reads_a_seeded_sample(self):
        self.assertEqual(TAGGED, 200)
        lost(self.log, TAGGED + 5, "playful", "play")
        note, = self.study()["hand_over"]["notes"]
        first = {v["id"] for v in self.spotter.calls[0]["items"]}
        self.assertEqual((len(first), note["cases"], note["sources"]), (TAGGED, TAGGED, TAGGED))
        self.setUp()
        lost(self.log, TAGGED + 5, "playful", "play")
        self.study()
        self.assertEqual({v["id"] for v in self.spotter.calls[0]["items"]}, first)


class OneSourceManyCases(Setup):
    data = plugs.changed(GARDEN, source={"about": "The gardener who asked for the round.", "known_by": "row"})

    def test_one_source_never_sends_a_note_alone(self):
        lost(self.log, 6, "playful", "play", source="gardener1")
        rep = self.study()
        playful, = [k for k in rep["hand_over"]["kinds"] if k["kind"] == "playful"]
        self.assertEqual((playful["cases"], playful["sources"]), (6, 1))
        self.assertEqual(rep["hand_over"]["notes"], [])

    def test_on_equal_sources_the_kind_with_more_cases_wins(self):
        for n, who in enumerate(("gardener1", "gardener2", "gardener3", "gardener3")):
            lost(self.log, 1, "playful", f"play{n}_", source=who)
        for n, who in enumerate(("gardener1", "gardener2", "gardener3")):
            lost(self.log, 1, "heat", f"hot{n}_", source=who)
        rep = self.study()
        kinds = {k["kind"]: (k["sources"], k["cases"], k["verdict"]) for k in rep["hand_over"]["kinds"]}
        self.assertEqual(kinds, {"heat": (3, 3, handover.BEATEN), "playful": (3, 4, handover.NOTE)})
        note, = rep["hand_over"]["notes"]
        self.assertEqual(note["kind"], "playful")

class AJokeIsHandedOver(Setup):
    def jokes(self):
        """A joke pattern that wins the gap rule: joked with 8 of 11 grew, without 2 of 10. The 3
        joked beds that wilted were playful moments, each its own source."""
        n = 0
        for joked, grew, count in ((True, True, 8), (True, False, 3), (False, True, 2), (False, False, 8)):
            for _ in range(count):
                n += 1
                fk.case(self.log, f"bed{n}", "water", "soaked", "grew" if grew else "wilted", stage="seedling",
                        joked=joked, moment="playful" if joked else None, note=f"round {n}")

    def run_jokes(self, **kw):
        self.jokes()
        return self.study(proposer=fk.Proposer(JOKE), tagger=fk.Tagger({JOKE["pattern"]: "joked"}), **kw)

    def test_without_the_track_the_joke_would_be_a_lesson(self):
        rep = self.run_jokes(hand=False)
        self.assertEqual([c["change"] for c in rep["cards"]], [JOKE["lesson"]])
        self.assertIsNone(rep["hand_over"])

    def test_the_joke_line_never_becomes_a_lesson_and_goes_to_the_receiving_agent(self):
        rep = self.run_jokes()
        self.assertEqual(rep["cards"], [])
        self.assertEqual([les["text"] for les in self.lessons.mine()], [])
        cand, = rep["candidates"]
        self.assertEqual(cand["verdict"], HANDED)
        self.assertEqual(cand["handed_to"], {"agent": TO, "kind": "playful"})
        self.assertIsNone(cand["lesson_id"])
        note, = rep["hand_over"]["notes"]
        self.assertEqual((note["to"], note["kind"], note["sources"]), (TO, "playful", 3))

    def test_a_joke_idea_is_handed_over_too(self):
        lost(self.log, 1, None, "calm")
        rep = self.study(ideas=Ideas(JOKE_IDEA))
        idea, = rep["ideas"]
        self.assertIsNone(idea["lesson_id"])
        self.assertTrue(idea["why"].startswith(f"not written: handed over to {TO} (playful)"), idea["why"])
        self.assertEqual(self.lessons.mine(), [])

    def test_a_failing_sort_holds_the_line_for_a_yes(self):
        rep = self.run_jokes(spotter=Spotter(fail_lines=True))
        card, = rep["cards"]
        self.assertEqual(card["state"], WAITING)
        self.assertIn("the hand over sort failed on a line (RuntimeError); it waits for a yes", rep["notes"])

    def sorted_by_the_meta_spotter(self, answer):
        """The jokes night with the real spotter part sorting each line on one scripted answer;
        the case views still go to the test spotter."""
        clean_env(self)
        meta, cases = parts.Spotter(FakeModel(*[say(answer)] * 20)), Spotter()

        def spotter(plug, kinds, items):
            return (meta if any("lesson" in i for i in items) else cases)(plug, kinds, items)

        return self.run_jokes(spotter=spotter)

    def test_an_unusable_sort_answer_holds_the_line_for_a_yes(self):
        held = "the hand over sort failed on a line (PartError: the spotter gave no usable answer for the line); " \
               "it waits for a yes"
        for answer in ("not json", json.dumps({}), json.dumps([]), json.dumps({"l2": "none"}),
                       json.dumps({"l1": 7}), json.dumps({"l1": "made up"}), '```json\n{"l1": "playful"}\n``'):
            with self.subTest(answer=answer):
                self.setUp()
                rep = self.sorted_by_the_meta_spotter(answer)
                card, = rep["cards"]
                self.assertEqual((card["change"], card["state"]), (JOKE["lesson"], WAITING))
                self.assertIn(held, rep["notes"])
                self.assertEqual(rep["candidates"][0]["lesson_id"], card["lesson_id"])

    def test_only_an_answer_of_none_writes_the_line_and_a_kind_hands_it_over(self):
        rep = self.sorted_by_the_meta_spotter(json.dumps({"l1": "none"}))
        card, = rep["cards"]
        self.assertEqual((card["change"], card["state"]), (JOKE["lesson"], TRYING))
        self.assertFalse([n for n in rep["notes"] if "sort" in n])
        self.setUp()
        rep = self.sorted_by_the_meta_spotter(json.dumps({"l1": "playful"}))
        self.assertEqual(rep["cards"], [])
        self.assertEqual(rep["candidates"][0]["verdict"], HANDED)

    def test_a_line_that_is_none_of_the_kinds_is_written_as_usual(self):
        self.jokes()
        rep = self.study(proposer=fk.Proposer(fk.EARLY), tagger=fk.Tagger({fk.EARLY["pattern"]: "joked"}))
        card, = rep["cards"]
        self.assertEqual((card["change"], card["state"]), (fk.EARLY["lesson"], TRYING))


class NoWordsCopied(Setup):
    def refused(self, line):
        lost(self.log, 3, "playful", "play", note=WORDS)
        rep = self.study(writer=Writer(line))
        playful, = [k for k in rep["hand_over"]["kinds"] if k["kind"] == "playful"]
        self.assertEqual(rep["hand_over"]["notes"], [])
        self.assertEqual(playful["verdict"], handover.NOT_SENT)
        self.assertEqual(handover.received(self.db, TO), [])
        return playful["why"]

    def test_a_name_from_the_cases_is_refused(self):
        why = self.refused("Ahmed keeps joking at the beds; a post could use that mood.")
        self.assertIn("names a word from the source's own words: ahmed", why.lower())

    def test_copied_words_are_refused(self):
        why = self.refused("People say the roses look thirsty; a post could use that mood.")
        self.assertIn("copies 3 or more words in a row", why)

    def test_a_number_is_refused(self):
        self.assertIn("number: /[0-9]/", self.refused("Three beds, 3 times, joked with the hose."))

    def test_the_plug_high_risk_list_does_not_hold_the_note(self):
        line = "Playful talk of poison near the sprayer comes up at the beds; a light post could carry that mood."
        self.assertTrue(guard(line, self.plug))  # the plug's own high risk list would refuse it
        lost(self.log, 3, "playful", "play")
        note, = self.study(writer=Writer(line))["hand_over"]["notes"]
        self.assertEqual(note["text"], line)

    def test_the_writer_never_sees_a_case(self):
        lost(self.log, 3, "playful", "play", note=WORDS)
        rep = self.study()
        note, = rep["hand_over"]["notes"]
        self.assertEqual(note["text"], LINE)
        sent = json.dumps(self.writer.calls)
        for word in ("Ahmed", "roses", "hose", "play0", "steps"):
            self.assertNotIn(word, sent)
        self.assertEqual(self.writer.calls[0]["found"],
                         {"kind": "playful", "about": HANDS[TO]["kinds"]["playful"], "cases": 3, "sources": 3})
        self.assertEqual(self.writer.calls[0]["receiver"], {"agent": TO, "about": HANDS[TO]["about"]})
        # the spotter reads blind views: keys only, never a case id
        self.assertNotIn("play0", json.dumps(self.spotter.calls))


class TheRow(Setup):
    def test_a_note_is_never_rewritten_and_a_rerun_writes_none(self):
        lost(self.log, 3, "playful", "play")
        first = self.study()["hand_over"]["notes"][0]
        again = self.study()["hand_over"]["notes"][0]
        self.assertFalse(first["again"])
        self.assertTrue(again["again"])
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(len(handover.received(self.db, TO)), 1)
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute("UPDATE handed_over SET text = 'changed' WHERE id = ?", (first["id"],))

    def window(self, since, until, spotter=None):
        track = handover.Track(self.db, self.plug, spotter=spotter or Spotter(), writer=Writer())
        return Study(self.db, self.plug, proposer=fk.Proposer(), tagger=fk.Tagger(), lessons=self.lessons,
                     hand_over=track).run(since, until, now=until)["hand_over"]["notes"]

    def test_a_second_run_minutes_later_writes_no_second_note(self):
        lost(self.log, 3, "playful", "play")
        first, = self.window(fk.SINCE, fk.UNTIL)
        again, = self.window(fk.SINCE + 300, fk.UNTIL + 300)
        self.assertEqual((first["again"], again["again"], again["id"]), (False, True, first["id"]))
        self.assertEqual(len(handover.received(self.db, TO)), 1)

    def test_the_next_night_sends_no_note_on_the_same_cases_and_one_when_new_cases_come(self):
        lost(self.log, 3, "playful", "play")
        first, = self.window(fk.SINCE, fk.UNTIL)
        rep = self.window(fk.SINCE + fk.DAY, fk.UNTIL + fk.DAY)  # the windows overlap, no new case
        self.assertEqual(rep, [])
        for n in range(3):
            fk.case(self.log, f"next{n}", "water", "soaked", "wilted", at=fk.UNTIL + fk.DAY, stage="seedling",
                    moment="playful", note=f"next round {n}")
        later, = self.window(fk.UNTIL, 2 * fk.UNTIL - fk.SINCE)
        self.assertFalse(later["again"])
        self.assertNotEqual(later["id"], first["id"])
        self.assertTrue({"next0", "next1", "next2"} <= set(later["case_ids"]))
        self.assertEqual(len(handover.received(self.db, TO)), 2)

    def test_a_night_that_starts_a_few_seconds_early_still_writes_its_note(self):
        lost(self.log, 3, "playful", "play")
        first, = self.window(fk.SINCE, fk.UNTIL)
        for n in range(3):
            fk.case(self.log, f"next{n}", "water", "soaked", "wilted", at=fk.UNTIL + fk.DAY, stage="seedling",
                    moment="playful", note=f"next round {n}")
        later, = self.window(fk.UNTIL - 4, 2 * fk.UNTIL - fk.SINCE - 4)  # the clock ran 4 seconds early
        self.assertFalse(later["again"])
        self.assertNotEqual(later["id"], first["id"])
        self.assertEqual(len(handover.received(self.db, TO)), 2)

    def test_a_new_kind_on_cases_sent_before_is_still_sent(self):
        lost(self.log, 3, "playful", "play")
        first, = self.window(fk.SINCE, fk.UNTIL)

        def heat(plug, kinds, items):
            return {it["id"]: "heat" for it in items if "steps" in it}
        later, = self.window(fk.SINCE + fk.DAY, fk.UNTIL + fk.DAY, spotter=heat)
        self.assertEqual((later["kind"], later["again"]), ("heat", False))
        self.assertEqual(sorted(later["case_ids"]), sorted(first["case_ids"]))

    def test_a_night_runs_from_noon_to_noon_in_cairo(self):
        noon = 1768989600.0  # 2026-01-21 12:00 in Cairo (UTC+2)
        self.assertEqual(handover.night_of(noon + 60), "2026-01-21")
        self.assertEqual(handover.night_of(noon + 15 * 3600), "2026-01-21")  # 03:00 the next morning
        self.assertEqual(handover.night_of(noon - 60), "2026-01-20")

    def test_the_table_itself_keeps_one_note_a_night(self):
        handover.Track(self.db, self.plug, spotter=Spotter(), writer=Writer())
        sql = ("INSERT OR IGNORE INTO handed_over (from_agent, to_agent, kind, text, cases, sources, since, until, "
               "written_at, night) VALUES (?, ?, 'playful', 'A line.', '[]', 3, 0, 1, 0, ?)")
        with self.db.tx() as c:
            self.assertEqual(c.execute(sql, ("waterer", TO, "2026-01-20")).rowcount, 1)
            self.assertEqual(c.execute(sql, ("waterer", TO, "2026-01-20")).rowcount, 0)  # the same night
            self.assertEqual(c.execute(sql, ("waterer", "other", "2026-01-20")).rowcount, 1)  # another receiver
            self.assertEqual(c.execute(sql, ("fan", TO, "2026-01-20")).rowcount, 1)  # another sender
            self.assertEqual(c.execute(sql, ("waterer", TO, "2026-01-21")).rowcount, 1)  # the next night

    def test_a_failing_spotter_hands_nothing_over(self):
        lost(self.log, 3, "playful", "play")
        rep = self.study(spotter=Spotter(fail=True))
        self.assertEqual(rep["hand_over"]["notes"], [])
        self.assertIn("waterer: the spotter failed (RuntimeError); nothing handed over", rep["notes"])

    def test_a_plug_with_no_hands_over_sends_nothing_and_sorts_nothing(self):
        plug = plugs.load(plugs.WATERER, self)
        spotter = Spotter()
        track = handover.Track(self.db, plug, spotter=spotter, writer=Writer())
        lost(Log(self.db, plug), 3, "playful", "play")
        rep = Study(self.db, plug, proposer=fk.Proposer(), tagger=fk.Tagger(), lessons=Lessons(self.db, plug),
                    hand_over=track).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        self.assertEqual(rep["hand_over"], {"kinds": [], "notes": []})
        self.assertEqual(spotter.calls, [])


class ThePlug(unittest.TestCase):
    def load(self, hands):
        return plug_mod.from_dict(plugs.changed(plugs.WATERER, hands_over=hands))

    def test_it_reads_the_receiving_agents_and_kinds(self):
        h, = self.load(HANDS).hands_over
        self.assertEqual((h.agent, h.about, dict(h.kinds)), (TO, HANDS[TO]["about"], HANDS[TO]["kinds"]))
        self.assertEqual(plug_mod.from_dict(plugs.WATERER).hands_over, ())

    def test_it_refuses_what_is_wrong(self):
        for hands, why in (({"waterer": {"kinds": {"a": "A line."}}}, "never to itself"),
                           ({TO: {"kinds": {}}}, "at least one entry"),
                           ({TO: {"kinds": {"a": "A line."}, "extra": 1}}, "unknown key"),
                           ({TO: {"kinds": {"a": "A line."}}, "other": {"kinds": {"a": "Again."}}}, "one agent only"),
                           ({"Bad Name": {"kinds": {"a": "A line."}}}, "lowercase")):
            with self.subTest(why=why):
                with self.assertRaises(ValueError) as cm:
                    self.load(hands)
                self.assertIn(why, str(cm.exception))

    def test_the_sales_plug_hands_three_kinds_to_marketing(self):
        h, = SALES.hands_over
        self.assertEqual(h.agent, "marketing")
        self.assertEqual(set(h.kinds), {"worth", "unknown", "playful"})
        self.assertIn("never jokes", h.kinds["playful"])


class TheNightAndTheMorning(Setup):
    def setUp(self):
        super().setUp()
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        lost(self.log, 3, "playful", "play")

    def night(self, **kw):
        return night.night(self.db, self.plug, until=fk.UNTIL, days=30, others=[], judge=always_low,
                           proposer=fk.Proposer(), tagger=fk.Tagger(), **kw)

    def test_the_report_shows_the_note_as_one_quiet_line(self):
        rep = self.night(spotter=Spotter(), note_writer=Writer())
        out = night.text(rep, self.plug)
        lines = [ln for ln in out.splitlines() if "note to" in ln]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(f'  note to {TO}: "{LINE}" (playful, 3 cases from 3 sources: '), lines[0])
        for cid in ("play0", "play1", "play2"):
            self.assertIn(cid, lines[0])

    def test_two_runs_of_one_night_minutes_apart_hand_over_one_note(self):
        first = self.night(spotter=Spotter(), note_writer=Writer())["hand_over"]["notes"]
        again = night.night(self.db, self.plug, until=fk.UNTIL + 300, days=30, others=[], judge=always_low,
                            proposer=fk.Proposer(), tagger=fk.Tagger(), spotter=Spotter(),
                            note_writer=Writer())["hand_over"]["notes"]
        self.assertEqual([(n["id"], n["again"]) for n in first + again], [(1, False), (1, True)])
        self.assertEqual(len(handover.received(self.db, TO)), 1)

    def test_scripted_parts_hand_nothing_over(self):
        rep = self.night()
        self.assertIsNone(rep["hand_over"])
        self.assertNotIn("note to", night.text(rep, self.plug))

    def test_the_runner_gives_the_meta_parts(self):
        got = {}

        def runner(db, plug, **kw):
            got.update(kw)
            raise night.Refused("stopped here")

        with mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]), \
                mock.patch.object(night, "night", side_effect=runner), \
                mock.patch("pathlib.Path.is_file", return_value=True), mock.patch.object(night, "Db"), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(night.main(["--db", "none.db"], until=fk.UNTIL), 2)
        self.assertIsInstance(got["spotter"], parts.Spotter)
        self.assertIsInstance(got["note_writer"], parts.NoteWriter)

    def test_the_morning_page_shows_one_quiet_line_with_no_case_id_and_no_button(self):
        rep = self.night(spotter=Spotter(), note_writer=Writer())
        night.save(rep, self.dir / "agent.db")
        page = page_mod.Morning(self.db, [self.plug], reports=self.dir, judge=always_low)
        view = page.view(now=fk.UNTIL)
        a, = view["agents"]
        self.assertEqual(a["night"]["handed"], [{"to": TO, "text": LINE}])
        html = page_mod.render(view, token="t0ken")
        line = f'<p class="meta handed" dir="auto">Note to {TO}: {page_mod.h(LINE)}</p>'
        self.assertEqual(html.count(line), 1)
        self.assertEqual(html.count('class="meta handed"'), 1)
        for cid in ("play0", "play1", "play2"):
            self.assertNotIn(cid, html)


class TheMetaParts(unittest.TestCase):
    """The spotter and the note writer on a scripted model: the study route, high effort, strict reading."""

    def setUp(self):
        clean_env(self)
        self.plug = plugs.load(GARDEN, self)
        self.kinds = [{"kind": "playful", "to": TO, "about": "A playful moment."}]

    def test_both_take_the_study_route(self):
        self.assertTrue(parts.Spotter.on_study_route)
        self.assertTrue(parts.NoteWriter.on_study_route)

    def test_the_spotter_keeps_only_declared_kinds(self):
        fake = FakeModel(say(json.dumps({"k1": "playful", "k2": "none", "k3": "made up", "k4": 7})))
        items = [{"id": f"k{n}", "steps": []} for n in range(1, 5)]
        got = parts.Spotter(fake)(self.plug, self.kinds, items)
        self.assertEqual(got, {"k1": "playful", "k2": "none"})
        self.assertEqual(fake.calls[0]["effort"], kit_model.EFFORT_STUDY)
        system, data = fake.calls[0]["messages"]
        self.assertIn("playful", system["content"])
        self.assertEqual(json.loads(data["content"]), {"items": items})

    def test_the_spotter_asks_in_batches_past_twenty_items(self):
        self.assertEqual(parts.BATCH, 20)
        items = [{"id": f"k{n}", "steps": []} for n in range(1, 26)]
        fake = FakeModel(say(json.dumps({i["id"]: "playful" for i in items[:20]})),
                         say(json.dumps({"k21": "none", "k22": "playful", "k1": "none"})))
        got = parts.Spotter(fake)(self.plug, self.kinds, items)
        self.assertEqual([len(json.loads(c["messages"][1]["content"])["items"]) for c in fake.calls], [20, 5])
        want = {f"k{n}": "playful" for n in range(1, 21)}
        want.update(k21="none", k22="playful")  # k1 in the second answer is not in that batch: not read
        self.assertEqual(got, want)

    def test_the_writer_reads_strictly_and_sees_no_case(self):
        found = {"kind": "playful", "about": "A playful moment.", "cases": 3, "sources": 3}
        receiver = {"agent": TO, "about": "Writes posts."}
        for answer, want in ((json.dumps({"note": LINE}), LINE), (json.dumps({"note": None}), None),
                             ("not json", None), (json.dumps({"note": LINE, "more": 1}), None)):
            with self.subTest(answer=answer):
                fake = FakeModel(say(answer))
                self.assertEqual(parts.NoteWriter(fake)(self.plug, receiver, found), want)
                system, data = fake.calls[0]["messages"]
                self.assertEqual(json.loads(data["content"]), found)
                self.assertIn(TO, system["content"])


if __name__ == "__main__":
    unittest.main()
