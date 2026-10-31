"""Call 16: the trial levels, the level switch, a waiting lesson's own level and Accept high
risk (engine/switches.py), and how a trial takes its level when it starts (engine/lessons.py).

The waterer plug's levels are fast (0.8 of cases for 3 days) and careful (0.5 for 7 days).
Every guard here failed on a mutant in a scratch copy before it was kept: each refusal, each
trigger and check, the end time compare, the level read at a trial's start, the own level
before the switch, the waiting check on a lesson's own level, the Accept high risk branch, and
the study's wait for a yes on a line close to a pulled one."""
import sqlite3
import unittest

from engine import risk
from engine import switches as sw
from engine.lessons import DAY, KEPT, PULLED, TRYING, WAITING, Lessons, copied, copied_saved
from engine.log import Log
from engine.study import Study
from kit.db import Db
from reflection import night as night_runner
from tests import plugs
from tests import study_fakes as fk
from tests.kept import kept_lesson

NOW = 1_800_000_000.0  # 15 Jan 2027 08:00 UTC
OWNER, OTHER = "Mona", "Omar"  # made-up people
LOW_A, LOW_B, LOW_C = "Visit the north bed first.", "Visit the grown beds last.", "Wait a little between rounds."
HIGH = "Wash the pots with bleach first."  # "bleach" is on the waterer's high list
MARKED = f"{OWNER} (Accept high risk)"


def always_low(text, high_about, low_about):
    return risk.LOW


def always_high(text, high_about, low_about):
    return risk.HIGH


class Base(unittest.TestCase):
    data = plugs.WATERER

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(self.data, self)
        self.les = Lessons(self.db, self.plug, judge=always_low)
        self.sw = self.les.switches

    def new(self, text, stages=("seedling",), *, now=NOW, trial=True):
        return self.les.propose(text, list(stages), sources=[], trial=trial, now=now)

    def sql(self, statement, args=()):
        with self.db.tx() as c:
            c.execute(statement, args)


class SwitchApi(Base):
    def test_the_level_reads_careful_until_a_person_flips_it(self):
        self.assertEqual(self.sw.level(), {"level": "careful", "share": 0.5, "days": 7, "by": None, "at": None})
        self.assertEqual(self.sw.set_level("fast", OWNER, now=NOW),
                         {"level": "fast", "share": 0.8, "days": 3, "by": OWNER, "at": NOW})
        self.sw.set_level("careful", f"  {OTHER} ", now=NOW + 1)
        self.assertEqual((self.sw.level()["level"], self.sw.level()["by"]), ("careful", OTHER))
        self.assertEqual([(h["value"], h["by"], h["at"]) for h in self.sw.history(sw.LEVEL)],
                         [("fast", OWNER, NOW), ("careful", OTHER, NOW + 1)])

    def test_each_setter_refuses_an_empty_by_and_an_unknown_level(self):
        lid = self.new(HIGH)
        for by in ("", "   ", None, 3, "Mona\nOmar"):
            with self.subTest(by=by):
                for call in (lambda: self.sw.set_level("fast", by), lambda: self.sw.set_accept_high(True, by),
                             lambda: self.sw.set_lesson_level(lid, "fast", by)):
                    with self.assertRaisesRegex(ValueError, "by: the person"):
                        call()
        for level in ("slow", "Fast", "", None, True):
            with self.subTest(level=level):
                with self.assertRaisesRegex(ValueError, "a trial level is fast or careful"):
                    self.sw.set_level(level, OWNER)
                with self.assertRaisesRegex(ValueError, "a trial level is fast or careful"):
                    self.sw.set_lesson_level(lid, level, OWNER)
        self.assertEqual(self.sw.history(), [])

    def test_accept_high_risk_days_are_whole_from_1_to_90(self):
        for days in (0, 91, -1, 1.5, True, "3"):
            with self.subTest(days=days), self.assertRaisesRegex(ValueError, "days: a whole number from 1 to 90"):
                self.sw.set_accept_high(True, OWNER, days=days, now=NOW)
        with self.assertRaisesRegex(ValueError, "days are given only when turning Accept high risk on"):
            self.sw.set_accept_high(False, OWNER, days=3, now=NOW)
        for on in ("yes", 1, None):
            with self.subTest(on=on), self.assertRaisesRegex(ValueError, "on: True or False"):
                self.sw.set_accept_high(on, OWNER, now=NOW)
        self.assertEqual(self.sw.history(), [])
        self.assertEqual(self.sw.set_accept_high(True, OWNER, days=1, now=NOW)["until"], NOW + DAY)
        self.assertEqual(self.sw.set_accept_high(True, OWNER, days=90, now=NOW)["until"], NOW + 90 * DAY)

    def test_accept_high_risk_reads_off_by_itself_at_its_time(self):
        self.assertEqual(self.sw.accept_high(NOW), {"on": False, "by": None, "at": None, "until": None,
                                                    "ran_out": False, "id": None})
        row = self.sw.set_accept_high(True, OWNER, days=2, now=NOW)
        self.assertEqual((row["on"], row["by"], row["at"], row["until"]), (True, OWNER, NOW, NOW + 2 * DAY))
        self.assertEqual(self.sw.accept_high(NOW + 2 * DAY - 1)["on"], True)
        late = self.sw.accept_high(NOW + 2 * DAY)
        self.assertEqual((late["on"], late["ran_out"]), (False, True))
        self.sw.set_accept_high(True, OTHER, now=NOW + 3 * DAY)  # no days: on until a person turns it off
        self.assertEqual(self.sw.accept_high(NOW + 1000 * DAY)["on"], True)
        off = self.sw.set_accept_high(False, OWNER, now=NOW + 4 * DAY)
        self.assertEqual((off["on"], off["ran_out"], off["by"]), (False, False, OWNER))
        self.assertEqual(self.sw.reading(NOW + 4 * DAY)["accept_high"],
                         {"on": False, "by": OWNER, "until": None, "ran_out": False})

    def test_switches_belong_to_their_own_agent(self):
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        self.sw.set_level("fast", OWNER, now=NOW)
        self.sw.set_accept_high(True, OWNER, now=NOW)
        self.assertEqual(fan.switches.level()["level"], "careful")
        self.assertFalse(fan.switches.accept_high(NOW)["on"])
        lid = self.new(HIGH)
        self.assertFalse(fan.switches.set_lesson_level(lid, "fast", OWNER))
        self.assertEqual(fan.switches.history(), [])


class TheTable(Base):
    """The database itself refuses what the code never does."""

    def test_a_row_is_never_changed_deleted_or_replaced(self):
        self.sw.set_level("fast", OWNER, now=NOW)
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never changed"):
            self.sql("UPDATE trial_switches SET value = 'careful'")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never deleted"):
            self.sql("DELETE FROM trial_switches")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never replaced"):
            self.sql("INSERT OR REPLACE INTO trial_switches (id, agent, kind, value, by, at) "
                     "VALUES (1, 'waterer', 'level', 'careful', 'Omar', 0)")
        self.assertEqual(self.sw.level()["level"], "fast")

    def test_a_lesson_level_only_while_the_lesson_waits(self):
        lid = self.new(LOW_A)  # on trial at once
        self.assertEqual(self.les.get(lid)["state"], TRYING)
        with self.assertRaisesRegex(sqlite3.DatabaseError, "only while it waits"):
            self.sql("INSERT INTO trial_switches (agent, kind, lesson_id, value, by, at) "
                     "VALUES ('waterer', 'lesson_level', ?, 'fast', 'Omar', 0)", (lid,))

    def test_the_checks_refuse_a_bad_row(self):
        lid = self.new(HIGH)
        add = "INSERT INTO trial_switches (agent, kind, lesson_id, value, until, by, at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        for row in (("waterer", "level", None, "fast", None, "  ", NOW),        # no person
                    ("waterer", "level", None, "on", None, OWNER, NOW),         # not a level
                    ("waterer", "accept_high", None, "fast", None, OWNER, NOW),  # not on or off
                    ("waterer", "accept_high", None, "off", NOW + DAY, OWNER, NOW),  # an end time on off
                    ("waterer", "accept_high", None, "on", NOW, OWNER, NOW),    # an end time not after now
                    ("waterer", "level", None, "fast", NOW + DAY, OWNER, NOW),  # an end time on a level
                    ("waterer", "level", lid, "fast", None, OWNER, NOW),  # a lesson on the switch
                    ("waterer", "night", None, "fast", None, OWNER, NOW)):      # no such kind
            with self.subTest(row=row), self.assertRaisesRegex(sqlite3.DatabaseError, "CHECK constraint failed"):
                self.sql(add, row)


class TrialLevels(Base):
    def test_a_new_trial_takes_the_switch_level_and_keeps_it_after_a_flip(self):
        a = self.new(LOW_A, ("seedling",))
        self.assertEqual((self.les.get(a)["share"], self.les.get(a)["ends_at"]), (0.5, NOW + 7 * DAY))
        self.sw.set_level("fast", OWNER, now=NOW + 1)
        b = self.new(LOW_B, ("grown",), now=NOW + 2)
        self.assertEqual((self.les.get(b)["share"], self.les.get(b)["ends_at"]), (0.8, NOW + 2 + 3 * DAY))
        self.assertEqual({k: self.les.trial(b)[k] for k in ("share", "days", "level")},
                         {"share": 0.8, "days": 3, "level": "fast"})
        self.assertEqual((self.les.get(a)["share"], self.les.get(a)["ends_at"]), (0.5, NOW + 7 * DAY))
        self.assertEqual({k: self.les.trial(a)[k] for k in ("share", "days", "level")},
                         {"share": 0.5, "days": 7, "level": "careful"})

    def test_a_lesson_waiting_its_turn_takes_the_level_when_its_turn_comes(self):
        a = self.new(LOW_A)
        c = self.new(LOW_C, now=NOW + 1)
        self.assertEqual(list(self.les.turns()), [c])
        self.assertEqual((self.les.trial(c)["level"], self.les.trial(c)["share"]), ("careful", 0.5))
        self.sw.set_level("fast", OWNER, now=NOW + 2)
        self.assertEqual((self.les.trial(c)["level"], self.les.trial(c)["share"]), ("fast", 0.8))  # what it starts with now
        self.les.pull(a, "test", now=NOW + DAY)
        self.assertEqual(self.les.start_turns(NOW + DAY), [c])
        self.assertEqual((self.les.get(c)["state"], self.les.get(c)["share"], self.les.get(c)["ends_at"]),
                         (TRYING, 0.8, NOW + DAY + 3 * DAY))
        self.sw.set_level("careful", OWNER, now=NOW + DAY + 1)
        self.assertEqual({k: self.les.trial(c)[k] for k in ("share", "days", "level")},
                         {"share": 0.8, "days": 3, "level": "fast"})

    def test_a_waiting_lessons_own_level_wins_over_the_switch(self):
        self.sw.set_level("fast", OWNER, now=NOW)
        high = self.new(HIGH)  # waits for a yes
        self.assertTrue(self.sw.set_lesson_level(high, "careful", OTHER, now=NOW + 1))
        self.assertEqual(self.sw.lesson_level(high), {"level": "careful", "by": OTHER, "at": NOW + 1})
        self.assertTrue(self.les.approve(high, OWNER, now=NOW + 2))
        self.assertEqual((self.les.get(high)["share"], self.les.get(high)["ends_at"]), (0.5, NOW + 2 + 7 * DAY))
        self.assertEqual(self.les.trial(high)["level"], "careful")
        # and for a lesson waiting its turn
        c = self.new(LOW_C, now=NOW + 3)
        self.assertIn(c, self.les.turns())
        self.assertTrue(self.sw.set_lesson_level(c, "careful", OTHER, now=NOW + 4))
        self.les.pull(high, "test", now=NOW + DAY)
        self.assertEqual(self.les.start_turns(NOW + DAY), [c])
        self.assertEqual((self.les.get(c)["share"], self.les.trial(c)["level"]), (0.5, "careful"))

    def test_numbers_given_with_the_yes_win_over_both(self):
        self.sw.set_level("fast", OWNER, now=NOW)
        high = self.new(HIGH)
        self.sw.set_lesson_level(high, "careful", OTHER, now=NOW + 1)
        self.assertTrue(self.les.approve(high, OWNER, share=0.3, now=NOW + 2))
        self.assertEqual((self.les.get(high)["share"], self.les.get(high)["ends_at"]), (0.3, NOW + 2 + 7 * DAY))
        self.assertEqual(self.les.trial(high)["level"], "given")

    def test_a_lesson_level_is_refused_once_the_lesson_no_longer_waits(self):
        trying = self.new(LOW_A)
        kept = kept_lesson(self.les, LOW_B, ["grown"], yes_by=OWNER, now=NOW)  # a person's line goes on trial first
        pulled = self.new(HIGH)
        self.les.pull(pulled, "test", now=NOW)
        self.assertEqual([self.les.get(x)["state"] for x in (trying, kept, pulled)], [TRYING, KEPT, PULLED])
        for lid in (trying, kept, pulled, 999):
            with self.subTest(lid=lid):
                self.assertFalse(self.sw.set_lesson_level(lid, "fast", OWNER, now=NOW))
        self.assertEqual(self.sw.history(sw.LESSON), [])


class PersonsLinesAndBringBack(Base):
    """A person's own line and a Bring back go on trial at the level that applies, with the
    person's own yes, never under Accept high risk."""

    def test_a_persons_line_starts_at_the_level_that_applies(self):
        self.sw.set_level("fast", OWNER, now=NOW)
        lid = self.les.add(LOW_B, ["grown"], yes_by=OTHER, now=NOW + 1)
        les, tr = self.les.get(lid), self.les.trial(lid)
        self.assertEqual((les["state"], les["share"], les["ends_at"], les["yes_by"]),
                         (TRYING, 0.8, NOW + 1 + 3 * DAY, OTHER))
        self.assertEqual((tr["level"], tr["accept_high"]), ("fast", None))

    def test_a_persons_line_waiting_its_turn_takes_its_own_level_at_its_turn(self):
        ahead = self.new(LOW_A, ["grown"])
        lid = self.les.add(LOW_B, ["grown"], yes_by=OTHER, now=NOW + 1)
        self.assertEqual(self.les.get(lid)["state"], WAITING)
        self.assertTrue(self.sw.set_lesson_level(lid, "fast", OWNER, now=NOW + 2))
        self.les.pull(ahead, "test", now=NOW + DAY)
        self.assertEqual(self.les.start_turns(NOW + DAY), [lid])
        self.assertEqual((self.les.get(lid)["share"], self.les.trial(lid)["level"]), (0.8, "fast"))

    def test_a_persons_high_line_under_accept_high_risk_keeps_their_own_yes(self):
        self.sw.set_accept_high(True, OWNER, now=NOW)
        lid = self.les.add(HIGH, ["grown"], yes_by=OTHER, now=NOW + 1)
        les = self.les.get(lid)
        self.assertEqual((les["risk"], les["state"], les["yes_by"], les["origin"]), ("high", TRYING, OTHER, "person"))
        self.assertIsNone(self.les.trial(lid)["accept_high"])

    def test_a_bring_back_starts_at_the_level_that_applies(self):
        old = self.new(LOW_A, ["grown"])
        self.les.pull(old, "test", now=NOW + 1)
        self.sw.set_level("fast", OWNER, now=NOW + 2)
        lid = self.les.bring_back(old, OTHER, now=NOW + 3)
        les, tr = self.les.get(lid), self.les.trial(lid)
        self.assertEqual((les["state"], les["share"], les["ends_at"], les["yes_by"]),
                         (TRYING, 0.8, NOW + 3 + 3 * DAY, OTHER))
        self.assertEqual((tr["level"], tr["accept_high"]), ("fast", None))

    def test_a_high_lesson_brought_back_under_accept_high_risk_keeps_the_persons_yes(self):
        old = self.new(HIGH, ["grown"])
        self.assertTrue(self.les.approve(old, OWNER, now=NOW + 1))
        self.les.pull(old, "test", now=NOW + 2)
        self.sw.set_accept_high(True, OWNER, now=NOW + 3)
        lid = self.les.bring_back(old, OTHER, now=NOW + 4)
        les = self.les.get(lid)
        self.assertEqual((les["risk"], les["state"], les["yes_by"]), ("high", TRYING, OTHER))
        self.assertIsNone(self.les.trial(lid)["accept_high"])


class NoNightlyCap(Base):
    data = plugs.changed(plugs.WATERER, stages=[f"bed{i}" for i in range(9)])

    def test_every_low_lesson_starts_with_no_yes_one_trial_a_stage(self):
        ids = [self.new(f"Visit bed {chr(97 + i)} before the others.", (f"bed{i}",)) for i in range(9)]
        self.assertEqual([self.les.get(i)["state"] for i in ids], [TRYING] * 9)
        self.assertEqual([self.les.get(i)["yes_by"] for i in ids], [None] * 9)
        more = self.new("Visit bed a again after lunch.", ("bed0",))
        self.assertEqual((self.les.get(more)["state"], self.les.waits_for(more, NOW)), (WAITING, [ids[0]]))


class AcceptHighRisk(Base):
    def test_off_a_high_lesson_waits_for_a_yes(self):
        high = self.new(HIGH)
        self.assertEqual((self.les.get(high)["state"], self.les.get(high)["yes_by"]), (WAITING, None))
        self.assertIsNone(self.les.trial(high))

    def test_on_a_high_lesson_starts_its_trial_at_the_level_with_the_mark(self):
        row = self.sw.set_accept_high(True, OWNER, now=NOW)
        self.sw.set_level("fast", OTHER, now=NOW)
        high = self.new(HIGH, now=NOW + 5)
        got = self.les.get(high)
        self.assertEqual((got["state"], got["yes_by"], got["yes_at"], got["share"]), (TRYING, MARKED, NOW + 5, 0.8))
        t = self.les.trial(high)
        self.assertEqual((t["level"], t["accept_high"]),
                         ("fast", {"id": row["id"], "by": OWNER, "at": NOW, "until": None}))
        low = self.new(LOW_B, ("grown",), now=NOW + 6)  # a low one carries no mark
        self.assertEqual((self.les.get(low)["yes_by"], self.les.trial(low)["accept_high"]), (None, None))

    def test_a_high_lesson_waiting_its_turn_gets_its_marked_yes_only_as_its_trial_starts(self):
        """Mohamed's call (fix round 1): high risk lessons start without a yes only while the
        switch is on, read again when the trial actually starts."""
        a = self.new(LOW_A)
        row = self.sw.set_accept_high(True, OWNER, now=NOW)
        high = self.new(HIGH, now=NOW + 1)
        got = self.les.get(high)
        self.assertEqual((got["state"], got["yes_by"], got["yes_at"]), (WAITING, None, None))
        self.assertEqual(self.les.waits_for(high, NOW + 1), [a])
        self.assertEqual(self.les.trial(high)["accept_high"]["id"], row["id"])  # the row it began waiting under
        self.les.pull(a, "test", now=NOW + DAY)
        again = self.sw.set_accept_high(True, OTHER, now=NOW + DAY)  # still on at its turn, turned on again by Omar
        self.assertEqual(self.les.start_turns(NOW + DAY + 1), [high])
        got = self.les.get(high)
        self.assertEqual((got["state"], got["yes_by"], got["yes_at"]),
                         (TRYING, f"{OTHER} (Accept high risk)", NOW + DAY + 1))
        self.assertEqual(self.les.trial(high)["accept_high"],
                         {"id": again["id"], "by": OTHER, "at": NOW + DAY, "until": None})  # the row read at the start

    def test_on_when_it_began_waiting_and_off_at_its_turn_it_waits_for_a_yes(self):
        for how in ("ran out", "turned off"):
            with self.subTest(how=how):
                self.setUp()
                a = self.new(LOW_A)
                self.sw.set_accept_high(True, OWNER, days=1, now=NOW)
                high = self.new(HIGH, now=NOW + 1)
                behind = self.new(LOW_C, now=NOW + 2)
                self.assertEqual(self.les.waits_for(behind, NOW + 2), [a, high])
                if how == "turned off":
                    self.sw.set_accept_high(False, OTHER, now=NOW + 3)
                self.les.pull(a, "test", now=NOW + 2 * DAY)
                self.assertEqual(self.les.start_turns(NOW + 2 * DAY), [behind])  # its turn went to the next one
                got = self.les.get(high)
                self.assertEqual((got["state"], got["yes_by"], got["yes_at"]), (WAITING, None, None))
                self.assertIsNone(self.les.trial(high))
                self.assertNotIn(high, self.les.turns())
                self.assertIsNone(self.les.waits_for(high, NOW + 2 * DAY))
                self.assertTrue(self.les.approve(high, OTHER, now=NOW + 3 * DAY))  # a person's yes moves it
                self.assertEqual((self.les.get(high)["yes_by"], self.les.trial(high)["accept_high"]), (OTHER, None))
                self.assertEqual(self.les.waits_for(high, NOW + 3 * DAY), [behind])

    def test_a_switch_row_counts_only_from_its_own_time(self):
        self.sw.set_accept_high(True, OWNER, now=NOW + DAY)
        self.assertFalse(self.sw.accept_high(NOW)["on"])
        early = self.new(HIGH, now=NOW)  # written at a time before the switch was turned on
        self.assertEqual((self.les.get(early)["state"], self.les.get(early)["yes_by"], self.les.trial(early)),
                         (WAITING, None, None))
        self.assertTrue(self.sw.accept_high(NOW + DAY)["on"])
        later = self.new(HIGH, ("grown",), now=NOW + DAY)
        self.assertEqual((self.les.get(later)["state"], self.les.get(later)["yes_by"]), (TRYING, MARKED))

    def test_ran_out_or_turned_off_it_starts_nothing(self):
        self.sw.set_accept_high(True, OWNER, days=1, now=NOW)
        late = self.new(HIGH, now=NOW + DAY)
        self.sw.set_accept_high(True, OWNER, now=NOW + DAY)
        self.sw.set_accept_high(False, OTHER, now=NOW + DAY + 1)
        off = self.new(HIGH, ("grown",), now=NOW + DAY + 2)
        for lid in (late, off):
            self.assertEqual((self.les.get(lid)["state"], self.les.get(lid)["yes_by"], self.les.trial(lid)),
                             (WAITING, None, None))

    def test_a_lesson_held_for_a_yes_still_waits_for_one(self):
        self.sw.set_accept_high(True, OWNER, now=NOW)
        held = self.new(HIGH, trial=False)  # what the study writes for a line close to a pulled one or a clash
        self.assertEqual((self.les.get(held)["state"], self.les.get(held)["yes_by"], self.les.trial(held)),
                         (WAITING, None, None))


class CopiedWords(Base):
    """Mohamed's call (29 Oct, "A yes"): a lesson high because the copy check found a case's
    own words always waits for a person's yes, even while Accept high risk is on, both when it
    is written and at its turn."""
    COPY = "Visit the north bed first before noon."
    CASE = "The gardener said visit the north bed first today."  # made up; shares five words in a row

    def copy(self, now=NOW):
        return self.les.propose(self.COPY, ["seedling"], sources=[self.CASE], now=now)

    def test_copied_reads_the_saved_reasons(self):
        self.assertTrue(copied(["seedling: bleach", "core: copied from source 2"]))
        self.assertFalse(copied(["core: link", "seedling: bleach"]))
        self.assertFalse(copied([]))

    def test_the_saved_reasons_are_split_where_they_were_joined(self):
        """Review t261029u r2: the copy reason can come after another one."""
        self.assertTrue(copied_saved("core: phone number; core: copied from source 1"))
        self.assertFalse(copied_saved("seedling: copied from source"))
        self.assertFalse(copied_saved(None))

    def test_under_the_switch_a_copy_waits_for_a_yes_when_written(self):
        self.sw.set_accept_high(True, OWNER, now=NOW)
        lid = self.copy()
        got = self.les.get(lid)
        self.assertEqual((got["state"], got["yes_by"], got["yes_at"], self.les.trial(lid)), (WAITING, None, None, None))
        self.assertIn("core: copied from source 1", got["risk_why"])
        self.assertTrue(self.les.approve(lid, OTHER, now=NOW + 1))  # a person's yes still moves it
        self.assertEqual((self.les.get(lid)["state"], self.les.get(lid)["yes_by"]), (TRYING, OTHER))

    def test_under_the_switch_a_copy_never_takes_a_turn_behind_a_live_trial(self):
        a = self.new(LOW_A)
        self.sw.set_accept_high(True, OWNER, now=NOW)
        lid = self.copy(now=NOW + 1)
        self.assertIsNone(self.les.trial(lid))
        self.assertNotIn(lid, self.les.turns())
        self.les.pull(a, "test", now=NOW + DAY)
        self.assertEqual(self.les.start_turns(NOW + DAY), [])
        self.assertEqual((self.les.get(lid)["state"], self.les.get(lid)["yes_by"]), (WAITING, None))

    def test_a_queued_copy_with_the_switch_row_is_dropped_at_its_turn(self):
        """An old row could carry the switch's id (written before this rule); at its turn the
        switch is never read for a copy, so its turn goes and it waits for a yes."""
        a = self.new(LOW_A)
        row = self.sw.set_accept_high(True, OWNER, now=NOW)
        lid = self.copy(now=NOW + 1)
        self.sql("INSERT INTO trials (lesson_id, agent, share, days, queued_at, accept_high_id) "
                 "VALUES (?, ?, 1.0, 7, ?, ?)", (lid, self.les.agent, NOW + 1, row["id"]))
        self.assertEqual(self.les.waits_for(lid, NOW + 1), [a])
        self.les.pull(a, "test", now=NOW + DAY)
        self.assertTrue(self.sw.accept_high(NOW + DAY)["on"])
        self.assertEqual(self.les.start_turns(NOW + DAY), [])
        got = self.les.get(lid)
        self.assertEqual((got["state"], got["yes_by"], got["yes_at"], self.les.trial(lid)), (WAITING, None, None, None))


class TheStudy(unittest.TestCase):
    """Accept high risk through the night study, with a judge that calls every lesson high."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        fk.beds(Log(self.db, self.plug))
        self.les = Lessons(self.db, self.plug, judge=always_high)
        first = self.night(fk.EARLY)["cards"][0]
        self.assertEqual((first["state"], bool(first["accept_high"])), (WAITING, False))
        self.les.pull(first["lesson_id"], "faded")
        self.les.switches.set_accept_high(True, OWNER, now=fk.NOW)

    def night(self, *cands, now=fk.NOW):
        study = Study(self.db, self.plug, proposer=fk.Proposer(*cands), tagger=fk.Tagger(), lessons=self.les)
        return study.run(fk.SINCE, fk.UNTIL, now=now)

    def test_a_line_close_to_a_pulled_one_still_waits_for_a_yes(self):
        rep = self.night(fk.candidate(fk.EARLY, lesson="Water the beds early in the mornings."), now=fk.NOW + DAY)
        card = rep["cards"][0]
        self.assertEqual((card["state"], card["close_to_pulled"]), (WAITING, "Water the beds early in the morning."))
        self.assertIsNone(self.les.get(card["lesson_id"])["yes_by"])

    def test_another_high_line_goes_on_trial_and_the_report_says_so(self):
        rep = self.night(fk.candidate(fk.EARLY, lesson="Water the beds late in the evening."), now=fk.NOW + DAY)
        card = rep["cards"][0]
        self.assertEqual((card["state"], card["level"]), (TRYING, "careful"))
        self.assertIs(card["accept_high"], True)
        self.assertEqual(self.les.trial(card["lesson_id"])["accept_high"]["by"], OWNER)
        self.assertEqual(self.les.get(card["lesson_id"])["yes_by"], MARKED)
        self.assertEqual(card["accept_high_by"], OWNER)
        self.assertEqual(night_runner._state(card), "on trial at the careful level, started under Accept high risk "
                                                    "(switched on by Mona)")
        self.assertNotIn("yes", night_runner._state(card))
        self.assertEqual(rep["switches"]["accept_high"], {"on": True, "by": OWNER, "until": None, "ran_out": False})

    def test_a_high_line_waiting_its_turn_under_the_switch_is_marked_and_has_no_yes(self):
        live = Lessons(self.db, self.plug, judge=always_low).propose("Visit the north bed first.", ["all"],
                                                                     sources=[], now=fk.NOW + DAY - 1)
        self.assertEqual(self.les.get(live)["state"], TRYING)
        rep = self.night(fk.candidate(fk.EARLY, lesson="Water the beds late in the evening."), now=fk.NOW + DAY)
        card = rep["cards"][0]
        self.assertEqual((card["state"], card["waits_for"]), (WAITING, [live]))
        self.assertIsNone(self.les.get(card["lesson_id"])["yes_by"])
        self.assertEqual((card["accept_high"], card["accept_high_by"]), (True, OWNER))
        self.assertEqual(night_runner._state(card),
                         f"waits its turn behind lesson {live}; it waits under Accept high risk (switched "
                         "on by Mona) and starts with no yes only if the switch is still on at its turn, else it "
                         "waits for a yes")


class TheNightLine(Base):
    def test_the_night_report_names_both_switches(self):
        line = night_runner.switches_line
        self.assertEqual(line(self.sw.reading(NOW)), "trial level careful: 50% of cases for 7 days; Accept high risk off")
        self.sw.set_level("fast", OWNER, now=NOW)
        self.sw.set_accept_high(True, OWNER, days=2, now=NOW)
        self.assertEqual(line(self.sw.reading(NOW)), "trial level fast: 80% of cases for 3 days; Accept high risk on, "
                                                     "turned on by Mona, until 17 Jan 2027 08:00 UTC")
        self.assertEqual(line(self.sw.reading(NOW + 2 * DAY)), "trial level fast: 80% of cases for 3 days; Accept high "
                                                               "risk off, its days ran out on 17 Jan 2027 08:00 UTC")


if __name__ == "__main__":
    unittest.main()
