"""Calls 2A and 13A (29 Oct): each lesson saves whose idea it is, a person's or the agent's,
and a trial that ends with too few results is unclear: it is given in no case and waits for a
person to keep it on trial longer or drop it, on the engine and on the morning page. Offline,
on the made-up waterer, in memory or temporary SQLite."""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import lessons as lessons_mod
from engine import trial as trial_mod
from engine.lessons import DAY, KEPT, PULLED, TRYING, WAITING, Lessons
from engine.log import Log
from engine.trial import Trials
from kit.db import Db
from reflection import morning as mod
from tests import plugs
from tests.kept import kept_lesson
from tests.test_engine_trial import NOW, OnTrial, always_low, trial_plug

END = NOW + 7 * DAY


class Ended(OnTrial):
    """The seedling lesson on trial from NOW to END; ended() gives it too few results."""

    def ended(self):
        self.beds(True, 2, 1)
        self.beds(False, 20, 20)
        return self.check(END)[1]


class Unclear(Ended):
    def test_too_few_results_end_unclear_and_change_nothing_about_the_lesson(self):
        t = self.ended()
        les = self.lessons.get(self.lid)
        self.assertEqual((t["status"], les["state"], les["ends_at"], les["share"]), ("unclear", TRYING, END, 0.5))
        self.assertEqual(self.trials.marks(self.lid, "verdict"), [])
        [m] = self.trials.marks(self.lid, "unclear")
        self.assertEqual((m["value"], m["at"], m["detail"]["with"]["settled"], m["detail"]["without"]["settled"]),
                         (END, END, 3, 40))
        self.assertIn("2 of 3 grew with it, 20 of 40 without.", t["why"])
        self.assertIn("The chance it is better is", t["why"])
        self.assertIn(trial_mod.UNCLEAR_ASK, t["why"])

    def test_an_unclear_lesson_is_given_in_no_case(self):
        before, after = set(), set()
        for i in range(20):
            self.lessons.hand(f"chat{i}", "water", "seedling", "slowly", before, now=NOW + DAY)
        self.assertEqual(before, {self.lid})
        self.ended()
        for i in range(20):
            self.lessons.hand(f"chat{i}", "water", "seedling", "slowly", after, now=END + 1)
        self.assertEqual(after, set())

    def test_a_later_night_says_unclear_again_and_writes_no_new_mark(self):
        self.ended()
        _, t = self.check(END + DAY)
        self.assertEqual((t["status"], t["unclear_at"]), ("unclear", END))
        self.assertEqual(len(self.trials.marks(self.lid, "unclear")), 1)
        self.assertEqual(self.state(self.lid), TRYING)

    def test_the_database_keeps_one_unclear_mark_for_each_end_date(self):
        self.ended()
        with self.assertRaises(sqlite3.IntegrityError), self.db.tx() as c:
            c.execute("INSERT INTO trial_marks (agent, lesson_id, kind, value, at) VALUES (?, ?, 'unclear', ?, ?)",
                      (self.plug.agent, self.lid, END, END + 1))
        self.assertEqual(len(self.trials.marks(self.lid, "unclear")), 1)

    def test_an_unclear_lesson_frees_its_stage(self):
        self.ended()
        other = self.new("Water the seedlings at the root.", ["seedling"], now=END + 60)
        self.assertEqual(self.state(other), TRYING)

    def test_a_lesson_a_person_changed_while_the_night_ran_gets_no_unclear_mark(self):
        for change, state in (("pull", PULLED), ("keep", KEPT)):
            with self.subTest(change=change):
                self.setUp()
                self.beds(True, 2, 1)
                self.beds(False, 20, 20)
                read = self.lessons.trial

                def read_then_change(lid, read=read, change=change):
                    out = read(lid)
                    if change == "pull":
                        self.lessons.pull(lid, "mona pulled it", now=END)
                    else:
                        self.lessons.keep(lid)
                    return out
                self.lessons.trial = read_then_change
                _, t = self.check(END)
                self.assertEqual((t["status"], self.state(self.lid)), ("changed meanwhile", state))
                self.assertEqual(self.trials.marks(self.lid, "unclear"), [])


class Longer(Ended):
    def test_the_days_and_who_are_checked(self):
        self.ended()
        for days in (0, 91, -1, 1.5, 7.0, True, "3", None):
            with self.subTest(days=days), self.assertRaisesRegex(ValueError, "days"):
                self.trials.longer(self.lid, days, "mona", now=END + DAY)
        for by in ("", "  ", "a\nb", "a\rb", None, 7):
            with self.subTest(by=by), self.assertRaisesRegex(ValueError, "by"):
                self.trials.longer(self.lid, 7, by, now=END + DAY)
        self.assertEqual((self.trials.marks(self.lid, "longer"), self.lessons.get(self.lid)["ends_at"]), ([], END))

    def test_one_day_and_ninety_days_are_allowed(self):
        for days in (1, trial_mod.LONGER_DAYS):
            with self.subTest(days=days):
                self.setUp()
                self.ended()
                self.assertEqual(self.trials.longer(self.lid, days, "mona", now=END + DAY), END + DAY + days * DAY)

    def test_refused_unless_it_waits_after_an_unclear_trial(self):
        self.beds(True, 2, 1)
        self.beds(False, 20, 20)
        self.assertIsNone(self.trials.longer(self.lid, 7, "mona", now=NOW + DAY))  # still on trial
        self.assertIsNone(self.trials.longer(self.lid, 7, "mona", now=END + DAY))  # ended, no night judged it yet
        self.assertIsNone(self.trials.unclear(self.lid, END + DAY))
        kept = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="mona", now=NOW)
        self.assertIsNone(self.trials.longer(kept, 7, "mona", now=END + DAY))
        self.assertIsNone(self.trials.longer(9999, 7, "mona", now=END + DAY))
        self.assertEqual((self.lessons.get(self.lid)["ends_at"], self.trials.marks(self.lid, "longer")), (END, []))

    def test_refused_while_another_lesson_is_on_trial_on_its_stages(self):
        self.ended()
        other = self.new("Water the seedlings at the root.", ["seedling"], now=END + 60)
        self.assertIsNone(self.trials.longer(self.lid, 7, "mona", now=END + DAY))
        self.assertEqual(self.trials.unclear(self.lid, END + DAY)["ahead"], [other])
        self.assertEqual((self.lessons.get(self.lid)["ends_at"], self.trials.marks(self.lid, "longer")), (END, []))
        later = END + 60 + 7 * DAY  # that trial's end date has passed
        self.assertEqual(self.trials.longer(self.lid, 7, "mona", now=later), later + 7 * DAY)

    def test_a_trial_on_other_stages_does_not_block_it(self):
        self.ended()
        grown = self.new("Water the grown beds deeply.", ["grown"], now=END + 60)
        self.assertEqual(self.state(grown), TRYING)
        self.assertEqual(self.trials.unclear(self.lid, END + DAY)["ahead"], [])
        self.assertEqual(self.trials.longer(self.lid, 7, "mona", now=END + DAY), END + 8 * DAY)

    def test_kept_longer_it_is_given_again_and_the_numbers_so_far_count(self):
        self.ended()
        trial = self.lessons.trial(self.lid)
        self.beds(False, 0, 30, at=END + DAY)  # the old way while it waited for a person: not counted
        at = END + 3 * DAY
        new_end = self.trials.longer(self.lid, 7, " mona ", now=at)
        self.assertEqual(new_end, at + 7 * DAY)
        les = self.lessons.get(self.lid)
        self.assertEqual((les["state"], les["share"], les["ends_at"]), (TRYING, 0.5, new_end))
        self.assertEqual(self.lessons.trial(self.lid), trial)  # its start, share and what it is judged by
        [m] = self.trials.marks(self.lid, "longer")
        self.assertEqual((m["by"], m["at"], m["value"], m["detail"]),
                         ("mona", at, new_end, {"from": END, "to": new_end, "days": 7}))
        self.assertEqual([les["id"] for les in self.lessons.live("seedling", at + 1)], [self.lid])
        self.assertIsNone(self.trials.unclear(self.lid, at + 1))
        self.assertEqual(self.check(at + DAY)[1]["status"], "on trial")
        self.beds(True, 4, 0, at=at + DAY)
        _, t = self.check(new_end)
        self.assertNotEqual(t["status"], "unclear")
        self.assertEqual((t["with"]["good"], t["with"]["settled"], t["without"]["good"], t["without"]["settled"]),
                         (6, 7, 20, 40))

    def test_too_few_again_at_the_new_end_is_unclear_again(self):
        self.ended()
        new_end = self.trials.longer(self.lid, 7, "mona", now=END + DAY)
        _, t = self.check(new_end)
        self.assertEqual(t["status"], "unclear")
        self.assertEqual([m["value"] for m in self.trials.marks(self.lid, "unclear")], [END, new_end])
        self.assertEqual(self.trials.unclear(self.lid, new_end + 1)["ends_at"], new_end)


class Drop(Ended):
    def test_drop_pulls_it_with_who_dropped_it_and_keeps_its_numbers(self):
        self.ended()
        for by in ("", "a\nb", None):
            with self.subTest(by=by), self.assertRaisesRegex(ValueError, "by"):
                self.trials.drop(self.lid, by, now=END + DAY)
        self.assertTrue(self.trials.drop(self.lid, " mona ", now=END + DAY))
        les = self.lessons.get(self.lid)
        self.assertEqual((les["state"], les["pulled_why"], les["pulled_at"]),
                         (PULLED, "unclear, dropped by mona", END + DAY))
        self.assertFalse(self.trials.drop(self.lid, "mona", now=END + 2 * DAY))
        self.assertIsNone(self.trials.longer(self.lid, 7, "mona", now=END + 2 * DAY))
        self.assertEqual(len(self.trials.marks(self.lid, "unclear")), 1)

    def test_refused_unless_it_waits_after_an_unclear_trial(self):
        self.beds(True, 2, 1)
        self.beds(False, 20, 20)
        self.assertFalse(self.trials.drop(self.lid, "mona", now=NOW + DAY))  # still on trial
        self.assertFalse(self.trials.drop(self.lid, "mona", now=END + DAY))  # ended, no night judged it yet
        kept = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="mona", now=NOW)
        self.assertFalse(self.trials.drop(kept, "mona", now=END + DAY))
        self.assertEqual((self.state(self.lid), self.state(kept)), (TRYING, KEPT))


class Extend(OnTrial):
    def test_a_later_end_date_only_once_the_end_date_it_read_has_passed(self):
        for bad in (END, END - 1, float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "later than now"):
                self.lessons.extend(self.lid, bad, was=END, now=END)
        self.assertFalse(self.lessons.extend(self.lid, END + DAY, was=END - DAY, now=END))  # another end date
        self.assertFalse(self.lessons.extend(self.lid, END + DAY, was=END, now=END - 1))  # not passed yet
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        self.assertFalse(fan.extend(self.lid, END + DAY, was=END, now=END))  # another agent's lesson
        self.assertEqual(self.lessons.get(self.lid)["ends_at"], END)
        self.assertTrue(self.lessons.extend(self.lid, END + DAY, was=END, now=END))
        self.assertEqual(self.lessons.get(self.lid)["ends_at"], END + DAY)

    def test_a_kept_or_pulled_lesson_is_not_extended(self):
        kept = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="mona", now=NOW)
        self.assertFalse(self.lessons.extend(kept, END + DAY, was=None, now=END))
        self.lessons.pull(self.lid, "test", now=END, on_trial=True)
        self.assertFalse(self.lessons.extend(self.lid, END + DAY, was=END, now=END))
        self.assertEqual(self.lessons.get(self.lid)["state"], PULLED)


class OneWriter(unittest.TestCase):
    def test_longer_and_drop_read_and_change_under_one_write_lock(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "trial.db"
        db = Db(path)
        self.addCleanup(db.close)
        plug = plugs.load(trial_plug(), self)
        lessons = Lessons(db, plug, judge=always_low)
        log = Log(db, plug)
        trials = Trials(db, plug, lessons=lessons)
        lid = lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        for i in range(3):
            log.act(f"bed{i}", "water", result="soaked", stage="seedling", lessons=[lid], at=NOW + DAY)
            log.result(f"bed{i}", "grew", at=NOW + 4 * DAY)
        self.assertEqual(trials.check(END)["trials"][0]["status"], "unclear")
        tried, read = [], trial_mod._lesson_row

        def another_writer(*a):  # runs right after the answer's first read
            spy = sqlite3.connect(str(path), timeout=0)
            try:
                spy.execute("BEGIN IMMEDIATE")
                tried.append("written")
                spy.rollback()
            except sqlite3.OperationalError as e:
                tried.append(str(e))
            finally:
                spy.close()
            return read(*a)
        with mock.patch.object(trial_mod, "_lesson_row", another_writer):
            new_end = trials.longer(lid, 7, "mona", now=END + DAY)
            self.assertEqual(trials.check(new_end)["trials"][0]["status"], "unclear")
            self.assertTrue(trials.drop(lid, "mona", now=new_end + 1))
        self.assertEqual(tried, ["database is locked", "database is locked"])
        spy = sqlite3.connect(str(path), timeout=0)  # and the lock is let go after
        spy.execute("BEGIN IMMEDIATE")
        spy.rollback()
        spy.close()


OLD_TABLE = lessons_mod.TABLE.replace("  origin TEXT CHECK (origin IN ('person', 'agent')),\n", "")


class Origin(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(trial_plug(), self)

    def test_each_lesson_saves_whose_idea_it_is(self):
        lessons = Lessons(self.db, self.plug, judge=always_low)
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        src = kept_lesson(fan, "Spin the fan slowly at dawn.", ["all"], yes_by="mona", now=NOW)
        made = {"add": lessons.add("Water the grown beds deeply.", ["grown"], yes_by="mona", now=NOW),
                "propose": lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW),
                "adapt": lessons.adapt("Water the beds slowly at dawn.", ["seedling"], sources=[],
                                       source=f"adapted fully from fan lesson {src}", source_lesson_id=src, now=NOW),
                "borrow": lessons.borrow(src, ["grown"], now=NOW)}
        self.assertEqual({k: lessons.get(i)["origin"] for k, i in made.items()},
                         {"add": "person", "propose": "agent", "adapt": "agent", "borrow": "agent"})
        self.assertEqual(fan.get(src)["origin"], "person")

    def test_whose_idea_it_is_is_never_rewritten(self):
        lessons = Lessons(self.db, self.plug, judge=always_low)
        lid = lessons.add("Water the grown beds deeply.", ["grown"], yes_by="mona", now=NOW)
        for origin in ("agent", None):
            with self.subTest(origin=origin), self.assertRaisesRegex(sqlite3.DatabaseError, "never rewritten"), \
                    self.db.tx() as c:
                c.execute("UPDATE lessons SET origin = ? WHERE id = ?", (origin, lid))
        self.assertEqual(lessons.get(lid)["origin"], "person")
        self.no_third_origin()

    def no_third_origin(self):
        """The database takes only "person" or "agent" as whose idea a lesson is."""
        with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"), self.db.tx() as c:
            c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, origin, added_at) "
                      "VALUES ('waterer', 'A line.', ',seedling,', ',garden,', 'low', 'waiting', 'robot', ?)", (NOW,))

    def old_rows(self, n=8):
        """Lessons written before the origin was saved, as the old code wrote them; the first n."""
        rows = [("kept", "mona", 'edited by mona from lesson 1: "Water at noon."', None),  # a person's edit
                ("kept", "mona", "", None),  # a person's own line
                ("trying", "mona", "night study of waterer, cases from 01 Jan to 30 Jan", None),
                ("trying", "mona", "adapted fully from fan lesson 1", None),
                ("kept", "mona", "borrowed from fan lesson 1", None),
                ("trying", None, "night study of waterer", None),  # low risk, no yes
                ("kept", "mona", "the fan's morning rule, in our words", 1),  # from another lesson
                ("waiting", None, "", None)]  # no yes and no source: the agent's
        ids = []
        with self.db.tx() as c:
            for state, by, source, from_id in rows[:n]:
                cur = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, share, ends_at, source, "
                                "source_lesson_id, yes_by, yes_at, added_at) VALUES ('waterer', ?, ',seedling,', "
                                "',garden,', 'low', ?, 1, ?, ?, ?, ?, ?, ?)",
                                (f"Line {len(ids)}.", state, END if state == "trying" else None, source, from_id, by,
                                 None if by is None else NOW, NOW))
                ids.append(cur.lastrowid)
        return ids

    def test_an_old_database_gets_the_column_and_each_lessons_origin(self):
        self.db.script(OLD_TABLE)
        ids = self.old_rows()
        lessons = Lessons(self.db, self.plug, judge=always_low)
        self.assertEqual([lessons.get(i)["origin"] for i in ids],
                         ["person", "person", "agent", "agent", "agent", "agent", "agent", "agent"])
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never rewritten"), self.db.tx() as c:
            c.execute("UPDATE lessons SET origin = 'agent' WHERE id = ?", (ids[0],))
        self.no_third_origin()

    def test_an_old_lesson_started_under_accept_high_risk_is_the_agents(self):
        self.db.script(OLD_TABLE)
        with self.db.tx() as c:  # no study source, yet its yes is the switch's mark, not a person's line
            lid = c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, share, ends_at, source, "
                            "yes_by, yes_at, added_at) VALUES ('waterer', 'Wash the pots with bleach first.', "
                            "',seedling,', ',garden,', 'high', 'trying', 0.5, ?, '', 'mona (Accept high risk)', ?, ?)",
                            (END, NOW, NOW)).lastrowid
        lessons = Lessons(self.db, self.plug, judge=always_low)
        self.assertEqual(lessons.get(lid)["origin"], "agent")

    def test_a_row_an_older_copy_writes_later_is_read_when_the_lessons_open_again(self):
        Lessons(self.db, self.plug, judge=always_low)
        ids = self.old_rows(3)  # an older copy of the code, on the same file, writes no origin
        lessons = Lessons(self.db, self.plug, judge=always_low)
        self.assertEqual([lessons.get(i)["origin"] for i in ids], ["person", "person", "agent"])


BASE = float(int(time.time()) - 40 * DAY)  # in the past, so an answer made at the real time finds it ended
P_END = BASE + 7 * DAY


class Page(unittest.TestCase):
    """The morning page with one unclear lesson on the seedling stage, ended 33 days ago."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(trial_plug(), self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)
        self.lid = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=BASE)
        log = Log(self.db, self.plug)
        n = 0
        for given, good, count in ((True, True, 2), (True, False, 1), (False, True, 20), (False, False, 20)):
            for _ in range(count):
                n += 1
                log.act(f"bed{n}", "water", result="soaked", stage="seedling", lessons=[self.lid] if given else [],
                        at=BASE + DAY)
                log.result(f"bed{n}", "grew" if good else "wilted", at=BASE + 4 * DAY)
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.trials.check(P_END)
        self.morning = mod.Morning(self.db, [self.plug])

    def agent(self, now):
        return next(a for a in self.morning.view(now)["agents"] if a["agent"] == "waterer")

    def test_an_unclear_lesson_is_a_card_with_its_numbers(self):
        v = self.morning.view(P_END + DAY)
        [u] = v["unclear"]
        self.assertEqual((u["id"], u["ended"], u["ahead"], u["days"], u["good"], u["status"]),
                         (self.lid, P_END, [], 7, "grew", "unclear"))
        self.assertEqual((u["sides"]["with"]["settled"], u["sides"]["with"]["good"], u["sides"]["without"]["settled"],
                          u["sides"]["without"]["good"]), (3, 2, 40, 20))
        self.assertEqual(u["said"], "Too few results to tell if the agent's lesson won: 2 of 3 grew with it, 20 of 40 "
                                    "without.")
        self.assertIsInstance(u["chance"], float)
        self.assertEqual(u["mark_id"], self.trials.marks(self.lid, "unclear")[0]["id"])
        self.assertEqual([c["id"] for c in v["cards"]], [])  # not a card that waits for a first yes
        self.assertIn(self.lid, [i["id"] for i in self.agent(P_END + DAY)["live"]])

    def test_the_card_has_keep_longer_and_drop_with_the_token_and_the_static_page_has_none(self):
        page = mod.render(self.morning.view(P_END + DAY), token="t0ken")
        self.assertIn('<h2 id="u-h">Unclear: too few results to tell</h2>', page)
        self.assertIn('<form method="post" action="/longer"><input type="hidden" name="token" value="t0ken">'
                      f'<input type="hidden" name="lesson" value="{self.lid}"><input type="text" name="days" value="7"',
                      page)
        self.assertIn('<form method="post" action="/drop"><input type="hidden" name="token" value="t0ken">', page)
        self.assertIn('<span class="lab">Settled cases that ended grew</span><div class="stat"><b class="num">2'
                      '<small>of</small>3</b><span>given the lesson, from 3 sources</span></div><div class="stat">'
                      '<b class="num">20<small>of</small>40</b><span>the old way, from 40 sources</span>', page)
        self.assertIn("Too few results to tell if the agent&#x27;s lesson won: 2 of 3 grew with it, 20 of 40 without.",
                      page)
        static = mod.render(self.morning.view(P_END + DAY))
        self.assertIn("Unclear: too few results to tell", static)
        for form in ('action="/longer"', 'action="/drop"', "<form"):
            self.assertNotIn(form, static)

    def test_an_agent_with_no_plug_gets_no_unclear_card(self):
        fan = plugs.load(plugs.FAN, self)
        self.assertEqual(mod.Morning(self.db, [fan]).view(P_END + DAY)["unclear"], [])

    def test_keep_longer_checks_its_days_and_the_lesson(self):
        for days in ("0", "91", "abc", "", "1.5", "-1", "1000"):
            with self.subTest(days=days), self.assertRaisesRegex(mod.Refused, "Days: a whole number from 1 to 90"):
                self.morning.longer(self.lid, days, now=P_END + DAY)
        kept = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="mona", now=BASE)
        with self.assertRaisesRegex(mod.Refused, "does not wait after an unclear trial"):
            self.morning.longer(kept, "7", now=P_END + DAY)
        other = self.lessons.propose("Water the seedlings at the root.", ["seedling"], sources=[], now=P_END + 60)
        with self.assertRaisesRegex(mod.Refused, f"lesson {other} is on trial on its stages until"):
            self.morning.longer(self.lid, "7", now=P_END + DAY)
        [u] = self.morning.view(P_END + DAY)["unclear"]
        self.assertEqual(u["ahead"], [other])
        self.assertIn(f"Lesson <a href=\"#l{other}\">", mod.render(self.morning.view(P_END + DAY), token="t0ken"))
        self.assertEqual(self.lessons.get(self.lid)["ends_at"], P_END)

    def test_the_pages_answers_keep_it_longer_then_drop_it(self):
        said = mod.ACTIONS["/longer"](self.morning, {"lesson": [str(self.lid)], "days": [" 7 "]})
        les = self.lessons.get(self.lid)
        self.assertTrue(said.startswith(f"Lesson {self.lid} is on trial again until "), said)
        self.assertAlmostEqual(les["ends_at"], time.time() + 7 * DAY, delta=60)
        self.assertEqual(self.trials.marks(self.lid, "longer")[0]["by"], "the owner")
        with self.assertRaisesRegex(mod.Refused, "does not wait after an unclear trial"):
            mod.ACTIONS["/drop"](self.morning, {"lesson": [str(self.lid)]})
        self.assertEqual(self.morning.view()["unclear"], [])

    def test_drop_from_the_page_and_the_trials_list_says_what_happened(self):
        [t] = self.agent(P_END + DAY)["trials"]
        self.assertEqual((t["status"], t["sides_from"]),
                         ("unclear, waits for you", f"unclear mark {self.trials.marks(self.lid, 'unclear')[0]['id']}"))
        self.assertEqual([m["kind"] for m in t["marks"]], ["unclear"])
        said = mod.ACTIONS["/drop"](self.morning, {"lesson": [str(self.lid)]})
        self.assertEqual(said, f"Lesson {self.lid} dropped. It is never given again.")
        les = self.lessons.get(self.lid)
        self.assertEqual((les["state"], les["pulled_why"]), (PULLED, "unclear, dropped by the owner"))
        [t] = self.agent(time.time())["trials"]
        self.assertEqual((t["status"], t["why"]), ("unclear, then dropped", "unclear, dropped by the owner"))
        with self.assertRaisesRegex(mod.Refused, "does not wait after an unclear trial"):
            self.morning.drop(self.lid)

    def test_an_edited_line_starts_its_trial_once_the_old_lesson_is_pulled(self):
        on_trial = self.lessons.propose("Water the grown beds at dawn.", ["grown"], sources=[], now=P_END)
        said = self.morning.edit(on_trial, "Water the grown beds at dusk.", now=P_END + 60)
        new = max(les["id"] for les in self.lessons.mine())
        self.assertEqual((self.lessons.get(new)["state"], said),
                         (TRYING, f"Lesson {on_trial} edited: the new line is lesson {new}. It is on trial."))
        item = next(i for i in self.agent(P_END + 120)["live"] if i["id"] == new)
        self.assertIn("On trial as the owner's own line", item["why"])

    def test_an_edited_line_waits_its_turn_behind_another_trial(self):
        kept = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="mona", now=BASE)
        self.lessons.propose("Water the grown beds at dawn.", ["grown"], sources=[], now=P_END)
        said = self.morning.edit(kept, "Water the grown beds at dusk.", now=P_END + 60)
        new = max(les["id"] for les in self.lessons.mine())
        self.assertEqual((self.lessons.get(new)["state"], said),
                         (WAITING, f"Lesson {kept} edited: the new line is lesson {new}. It waits its turn."))


if __name__ == "__main__":
    unittest.main()


class Whose(unittest.TestCase):
    """Review t261029v r1 finding 4: the Sales agent's team add path reads as the team's line."""

    def test_the_owner_of_a_line_reads_plainly(self):
        from engine.trial import _whose
        self.assertEqual([_whose("mona"), _whose("team"), _whose(None)], ["mona's", "the team's", "a person's"])
