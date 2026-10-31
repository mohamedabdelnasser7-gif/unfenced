"""Step 3: lessons carry their agent, risk, state, share, end date, field tags and source.
A Sales agent lesson never reaches another agent; a lesson with a number or promise is
high every time."""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import lessons as engine_lessons
from engine import risk
from engine.lessons import DAY, Lessons as EngineLessons, in_share
from kit.db import Db
from reflection import PLUG
from reflection.lessons import TEAM, Lessons
from tests import plugs
from tests.kept import kept_lesson

NOW = 1_800_000_000.0


def always_low(text, high_about, low_about):
    """A judge that says low to everything: what is still high was caught by the code check."""
    return risk.LOW


NUMBERS = [
    "Tell them delivery is 500.",
    "Say the boots are ٥٠٠ جنيه.",
    "Say ۵۰۰ for the pair.",
    "Say the total is five hundred.",
    "قول إن التوصيل بخمسين جنيه.",
    "قول السعر خمسمية.",
    "Quote it as ５００.",
    "Say it costs fifty.",
    "Give them 10% off.",
    "Say 1,500 for both.",
    "Tell them it is twenty pounds less.",
    "Say half the fee.",
    "Use ½ of the usual.",
    "قول له تلات أيام.",
    "Tell them it is five​hundred.",
    "Tell them it is fi​ve hundred.",
    "Say the price plainly, the number then جنيه.",
    "Say ثلاثمائة.",
    "2olo el se3r.",
]
PROMISES = [
    "Promise them a refund if it does not fit.",
    "Tell them we can exchange it any time.",
    "Say it arrives tomorrow.",
    "Tell them they get their money back.",
    "Say we guarantee the fit.",
    "قول له هيوصل بكرة.",
    "قوله نقدر نستبدلها.",
    "أوعدهم إنها هتوصل.",
    "قول إن عندنا استرجاع.",
    "Tell them it will be there on Sunday.",
    "Say we always replace a broken pair.",
    "Tell them the refunds are quick.",
    "Say delivery takes one day.",
]
POLICY_AND_DATA = [
    "Ask for their address before the summary.",
    "Never cancel without asking the team.",
    "Tell them we take cash on delivery only.",
    "Use their name and phone number in the summary.",
    "Check stock with the store tool first.",
]
TONE = [  # low risk on the starter list: tone, wording, the order of questions, when to ask for the size, greetings
    "Greet them warmly before anything else.",
    "Ask for the size before the colour.",
    "Keep replies short and friendly.",
    "Answer in the language they wrote in.",
    "Thank them when they say yes.",
    "رحب بيهم بلطف.",
    "اسأل عن المقاس الأول.",
]
MARKERS = ["500", "٥٠٠", "۵۰۰", "５０", "7", "fifty", "five hundred", "twenty", "half", "خمسين", "تلاتة", "ميتين",
           "refund", "exchange", "tomorrow", "guarantee", "بكرة", "استرجاع", "استبدال", "هيوصل", "promise", "10%"]
HIDDEN = ["​", "‌", "‍", "­", "⁠", "﻿"]


class RiskCheck(unittest.TestCase):
    def level(self, text, judge=always_low):
        return risk.classify(text, PLUG.risk, judge)[0]

    def test_a_number_is_high_every_time(self):
        for text in NUMBERS:
            with self.subTest(text=text):
                self.assertEqual(self.level(text), risk.HIGH)

    def test_a_promise_is_high_every_time(self):
        for text in PROMISES:
            with self.subTest(text=text):
                self.assertEqual(self.level(text), risk.HIGH)

    def test_store_policy_and_personal_data_are_high(self):
        for text in POLICY_AND_DATA:
            with self.subTest(text=text):
                self.assertEqual(self.level(text), risk.HIGH)

    def test_a_number_or_promise_anywhere_in_a_tone_lesson_is_high(self):
        rnd = random.Random(261029)
        for i in range(600):
            words = rnd.choice(TONE).split()
            marker = rnd.choice(MARKERS)
            if rnd.random() < 0.3:
                marker = rnd.choice([marker.upper(), marker.title()])
            if rnd.random() < 0.4 and len(marker) > 1:  # a hidden character inside the marker
                at = rnd.randrange(1, len(marker))
                marker = marker[:at] + rnd.choice(HIDDEN) + marker[at:]
            if rnd.random() < 0.2 and not marker.isascii():
                marker = marker[0] + "ـ" + marker[1:]  # an Arabic stretch mark
            words.insert(rnd.randrange(len(words) + 1), marker)
            text = " ".join(words)
            with self.subTest(i=i, text=text):
                self.assertEqual(self.level(text), risk.HIGH)

    def test_tone_alone_is_low_only_on_a_clear_low_from_the_judge(self):
        for text in TONE:
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk), [])
                self.assertEqual(self.level(text), risk.LOW)
                self.assertEqual(self.level(text, risk.no_judge), risk.HIGH)  # the stub is unsure: high
                self.assertEqual(self.level(text, lambda *a: risk.HIGH), risk.HIGH)
                self.assertEqual(self.level(text, lambda *a: "LOW"), risk.HIGH)
                self.assertEqual(self.level(text, lambda *a: None), risk.HIGH)

                def broken(*a):
                    raise TimeoutError("judge down")
                self.assertEqual(self.level(text, broken), risk.HIGH)

    def test_the_judge_is_asked_only_when_the_code_finds_nothing(self):
        asked = []

        def judge(text, high_about, low_about):
            asked.append((text, high_about, low_about))
            return risk.LOW
        risk.classify("Say it costs 60.", PLUG.risk, judge)
        self.assertEqual(asked, [])
        risk.classify(TONE[0], PLUG.risk, judge)
        self.assertEqual(asked, [(TONE[0], PLUG.risk.high_about, PLUG.risk.low_about)])

    def test_the_lines_name_what_made_it_high(self):
        level, why = risk.classify("Promise a refund of 50.", PLUG.risk)
        self.assertEqual(level, risk.HIGH)
        self.assertIn("promise: refund", why)
        self.assertIn("number: /[0-9]/", why)
        self.assertIn("tool: draft_order", risk.classify("Call draft_order early.", PLUG.risk)[1])

    def test_another_agents_list_is_its_own(self):
        waterer = plugs.load(plugs.WATERER, self)
        self.assertEqual(risk.classify("Promise a refund.", waterer.risk, always_low)[0], risk.LOW)
        self.assertEqual(risk.classify("Use the pesticide.", waterer.risk, always_low)[0], risk.HIGH)
        self.assertEqual(risk.classify("Use the sprayer.", waterer.risk, always_low)[0], risk.HIGH)


class States(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.low = EngineLessons(self.db, PLUG, judge=always_low)

    def ids(self, case, stage="asking", now=NOW + 1):
        return [p["id"] for p in self.low.pick(stage, "", case=case, now=now)]

    def test_a_low_risk_lesson_is_tried_on_a_share_until_its_end_date(self):
        lid = self.low.propose("Greet them warmly before anything else.", ["all"], source="study", now=NOW, sources=[])
        les = self.low.get(lid)
        # the share comes from the plug; test_engine_hand pins its value
        self.assertEqual((les["risk"], les["state"], les["share"], les["ends_at"], les["yes_by"]),
                         ("low", "trying", PLUG.level("careful").share, NOW + PLUG.level("careful").days * DAY, None))
        self.assertEqual((les["agent"], les["fields"], les["source_lesson_id"]), ("sales", ["retail"], None))
        cases = [f"chat-{i}" for i in range(2000)]
        given = [c for c in cases if self.ids(c) == [lid]]
        self.assertTrue(abs(len(given) - len(cases) * PLUG.level("careful").share) < 100, len(given))
        self.assertEqual(given, [c for c in cases if self.ids(c) == [lid]])  # the same case, the same answer
        self.assertEqual(self.ids(None), [])  # no case: only lessons given in every case
        self.assertEqual(self.ids(given[0], now=NOW + PLUG.level("careful").days * DAY), [])  # past its end date
        self.assertTrue(self.low.keep(lid))
        self.assertEqual(self.low.get(lid)["ends_at"], None)
        self.assertTrue(all(self.ids(c, now=NOW + 30 * DAY) == [lid] for c in cases[:200]))
        self.assertEqual(self.ids(None), [lid])

    def test_a_high_risk_lesson_waits_for_a_yes(self):
        lid = self.low.propose("Tell them delivery is 500.", ["asking"], now=NOW, sources=[])
        les = self.low.get(lid)
        self.assertEqual((les["risk"], les["state"], les["yes_by"]), ("high", "waiting", None))
        self.assertIn("number", les["risk_why"])
        self.assertEqual(self.ids("chat-1"), [])
        self.assertFalse(self.low.keep(lid))  # nothing skips the yes
        self.assertTrue(self.low.approve(lid, "mohamed", share=1, days=3, now=NOW))
        les = self.low.get(lid)
        self.assertEqual((les["state"], les["yes_by"], les["yes_at"], les["ends_at"]),
                         ("trying", "mohamed", NOW, NOW + 3 * DAY))
        self.assertEqual(self.ids("chat-1"), [lid])
        self.assertFalse(self.low.approve(lid, "mohamed"))  # a yes is given once
        self.assertTrue(self.low.keep(lid))
        self.assertEqual(self.low.get(lid)["state"], "kept")

    def test_the_stub_judge_makes_every_new_lesson_wait(self):
        stub = EngineLessons(self.db, PLUG)
        lid = stub.propose("Greet them warmly before anything else.", ["all"], now=NOW, sources=[])
        self.assertEqual((stub.get(lid)["risk"], stub.get(lid)["state"]), ("high", "waiting"))

    def test_add_is_a_lesson_with_a_yes_already(self):
        lid = kept_lesson(self.low, "Say the fee once.", ["ordering"], yes_by="mohamed", now=NOW)
        les = self.low.get(lid)
        self.assertEqual((les["risk"], les["state"], les["share"], les["yes_by"]), ("high", "kept", 1.0, "mohamed"))
        self.assertEqual(self.ids(None, "ordering"), [lid])
        with self.assertRaises(ValueError):
            kept_lesson(self.low, "Say the fee once.", ["ordering"], yes_by=" ")

    def test_a_pulled_lesson_is_never_given_again(self):
        lid = kept_lesson(self.low, "Keep replies short.", ["all"], yes_by=TEAM)
        self.assertTrue(self.low.pull(lid, "the team asked"))
        self.assertFalse(self.low.pull(lid))
        self.assertFalse(self.low.approve(lid, "mohamed"))
        self.assertFalse(self.low.keep(lid))
        self.assertEqual(self.ids(None), [])
        self.assertEqual(self.low.get(lid)["pulled_why"], "the team asked")

    def test_refuses_a_bad_lesson(self):
        for text, stages in (("two\nlines", ["all"]), ("", ["all"]), ("x" * 301, ["all"]), ("ok", []),
                             ("ok", ["seedling"]), ("ok", "asking")):
            with self.subTest(text=text, stages=stages), self.assertRaises(ValueError):
                self.low.propose(text, stages, sources=[])
        lid = self.low.propose("Tell them delivery is 500.", ["asking"], sources=[])
        for share, days in ((0, 3), (1.5, 3), (0.5, 0)):
            with self.assertRaises(ValueError):
                self.low.approve(lid, "mohamed", share=share, days=days)

    def test_in_share_is_stable_and_respects_the_ends(self):
        self.assertTrue(in_share(None, 1, 1.0))
        self.assertFalse(in_share(None, 1, 0.5))
        self.assertEqual([in_share(f"c{i}", 7, 0.3) for i in range(50)], [in_share(f"c{i}", 7, 0.3) for i in range(50)])


class DatabaseGuards(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.lessons = EngineLessons(self.db, PLUG, judge=always_low)
        self.high = self.lessons.propose("Tell them delivery is 500.", ["asking"], sources=[])
        self.tone = self.lessons.propose("Greet them warmly.", ["all"], sources=[])

    def refused(self, sql, *args):
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute(sql, args)

    def test_a_high_risk_lesson_is_never_given_without_a_yes(self):
        self.refused("UPDATE lessons SET state = 'kept' WHERE id = ?", self.high)
        self.refused("UPDATE lessons SET state = 'trying', ends_at = 9e9 WHERE id = ?", self.high)
        self.refused("INSERT INTO lessons (agent, text, stages, fields, risk, state, added_at) "
                     "VALUES ('sales', 'say 500', ',all,', ',', 'high', 'kept', 1)")
        self.assertEqual(self.lessons.get(self.high)["state"], "waiting")

    def test_never_rewritten_and_pulled_stays_pulled(self):
        for column, value in (("text", "something else"), ("stages", ",all,"), ("agent", "waterer"),
                              ("risk", "low"), ("risk_why", "x"), ("fields", ",gardening,"), ("source", "x"),
                              ("source_lesson_id", self.tone), ("added_at", 1)):
            with self.subTest(column=column):
                self.refused(f"UPDATE lessons SET {column} = ? WHERE id = ?", value, self.high)
        self.refused("UPDATE lessons SET ends_at = NULL WHERE id = ?", self.tone)  # a trial has an end date
        self.assertTrue(self.lessons.approve(self.high, "mohamed"))
        self.refused("UPDATE lessons SET yes_by = NULL, yes_at = NULL WHERE id = ?", self.high)
        self.refused("UPDATE lessons SET yes_by = 'someone else' WHERE id = ?", self.high)
        self.assertTrue(self.lessons.pull(self.tone))
        self.refused("UPDATE lessons SET state = 'trying' WHERE id = ?", self.tone)
        self.assertTrue(self.lessons.set_score(self.tone, 2.5))  # the score may move


class OneAgentsLessonsStayItsOwn(unittest.TestCase):
    """A Sales agent lesson never reaches another agent; borrowing makes a new lesson."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.front = Lessons(self.db)
        self.waterer = EngineLessons(self.db, plugs.load(plugs.WATERER, self), judge=always_low)
        self.fan = EngineLessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        self.ledger = EngineLessons(self.db, plugs.load(plugs.LEDGER, self), judge=always_low)
        self.front_ids = [kept_lesson(self.front, t, ["all"]) for t in ("Water the plants on a round.", "Greet them warmly.",
                                                               "Ask for the size first.")]
        self.front_ids.append(kept_lesson(self.front, "Say the price plainly.", ["asking"]))

    def test_a_sales_lesson_never_reaches_another_agent(self):
        mine = kept_lesson(self.waterer, "Water the seedlings first.", ["seedling"], yes_by="grower")
        texts = ["Water the plants on a round.", "greet warmly size price", "", None]
        for other in (self.waterer, self.fan, self.ledger):
            for stage in (None, "seedling", "grown", "open", "asking", "all"):
                for case in (None, "c1", "bed-3", 7):
                    for text in texts:
                        got = {p["id"] for p in other.pick(stage, text, case=case)}
                        if stage in other.plug.stages:  # hand() refuses a stage the plug does not have
                            got |= {p["id"] for p in other.hand(case or "c1", next(iter(other.plug.actions)), stage,
                                                                text, set())}
                        self.assertFalse(got & set(self.front_ids), (other.agent, stage, case, text))
            self.assertFalse({p["id"] for p in other.live()} & set(self.front_ids))
            self.assertFalse({p["id"] for p in other.mine()} & set(self.front_ids))
            for fid in self.front_ids:
                self.assertIsNone(other.get(fid))
                self.assertFalse(other.pull(fid))
                self.assertFalse(other.keep(fid))
                self.assertFalse(other.approve(fid, "someone"))
                self.assertFalse(other.set_score(fid, 99))
        self.assertEqual([self.front.get(f)["state"] for f in self.front_ids], ["kept"] * 4)
        self.assertEqual({self.front.get(f)["score"] for f in self.front_ids}, {0.0})
        self.assertEqual([p["id"] for p in self.waterer.pick("seedling", "")], [mine])
        self.assertNotIn(mine, [p["id"] for p in self.front.pick("asking", "water the seedlings")])

    def test_borrowing_needs_the_same_field_and_makes_a_new_lesson(self):
        for fid in self.front_ids:  # retail is not gardening or bookkeeping
            for other in (self.waterer, self.fan, self.ledger):
                with self.assertRaises(ValueError):
                    other.borrow(fid, ["all"])
        src = kept_lesson(self.waterer, "Check the soil before watering.", ["grown"], yes_by="grower")
        with self.assertRaises(ValueError):
            self.ledger.borrow(src, ["all"])
        with self.assertRaises(ValueError):
            self.waterer.borrow(src, ["all"])  # its own lesson
        with self.assertRaises(ValueError):
            self.fan.borrow(99999, ["all"])
        new = self.fan.borrow(src, ["all"])
        les = self.fan.get(new)
        self.assertNotEqual(new, src)
        self.assertEqual((les["agent"], les["text"], les["source_lesson_id"], les["fields"], les["state"], les["risk"]),
                         ("fan", "Check the soil before watering.", src, ["gardening"], "trying", "low"))
        self.assertIn("waterer", les["source"])
        self.assertNotIn(src, [p["id"] for p in self.fan.pick(None, "soil", case="house-1")])
        self.assertNotIn(new, [p["id"] for p in self.waterer.pick("grown", "soil", case="bed-1")])

    def test_a_borrowed_lesson_is_checked_by_the_borrowers_own_list(self):
        src = kept_lesson(self.waterer, "Use 2 cups of water.", ["grown"], yes_by="grower")
        new = self.fan.borrow(src, ["all"])
        self.assertEqual((self.fan.get(new)["risk"], self.fan.get(new)["state"]), ("high", "waiting"))
        stub_fan = EngineLessons(self.db, self.fan.plug)
        tone = kept_lesson(self.waterer, "Visit the shady beds first.", ["grown"], yes_by="grower")
        self.assertEqual(stub_fan.get(stub_fan.borrow(tone, ["all"]))["state"], "waiting")  # unsure is high
        self.waterer.pull(tone)
        with self.assertRaises(ValueError):
            self.fan.borrow(tone, ["all"])

    def test_the_database_refuses_a_lesson_borrowed_from_its_own_agent(self):
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, added_at, source_lesson_id) "
                          "VALUES ('sales', 'x', ',all,', ',', 'low', 'waiting', 1, ?)", (self.front_ids[0],))


OLD_LESSONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  stages TEXT NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
  source TEXT,
  added_at REAL NOT NULL,
  retired_at REAL,
  retired_why TEXT
);
CREATE TRIGGER IF NOT EXISTS lessons_never_rewritten
BEFORE UPDATE OF text, stages ON lessons
BEGIN SELECT RAISE(ABORT, 'a lesson is never rewritten; retire it and add a new one'); END;
CREATE TRIGGER IF NOT EXISTS lessons_stay_retired
BEFORE UPDATE OF status ON lessons WHEN OLD.status = 'retired'
BEGIN SELECT RAISE(ABORT, 'a retired lesson stays retired'); END;
"""
OLD_LESSONS = [  # (text, stages, score, status, source, added_at, retired_at, retired_why)
    ("Say the price plainly, the number then جنيه.", ",asking,", 1.5, "active", "morning 27 Oct", 100.0, None, None),
    ("Greet them warmly.", ",all,", 0.0, "active", None, 101.0, None, None),
    ("Never say الجوز.", ",asking,ordering,", -1.0, "retired", "night", 102.0, 150.0, "replaced"),
    ("An old free tag.", ",someday,", 0.0, "active", "", 103.0, None, None),
]


class MoveOldLessons(unittest.TestCase):
    def old_database(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name) / "ascent.db"
        conn = sqlite3.connect(path)
        conn.executescript(OLD_LESSONS_SCHEMA)
        conn.executemany("INSERT INTO lessons (text, stages, score, status, source, added_at, retired_at, retired_why) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", OLD_LESSONS)
        conn.commit()
        conn.close()
        db = Db(path)
        self.addCleanup(db.close)
        return db

    def test_every_lesson_moves_with_its_id_and_values(self):
        db = self.old_database()
        lessons = Lessons(db)
        for i, (text, stages, score, status, source, added_at, retired_at, why) in enumerate(OLD_LESSONS, start=1):
            les = lessons.get(i)
            self.assertEqual((les["text"], engine_lessons.tag_text(les["stages"]), les["score"], les["source"],
                              les["added_at"], les["pulled_at"], les["pulled_why"]),
                             (text, stages, score, source, added_at, retired_at, why), i)
            self.assertEqual(les["state"], "kept" if status == "active" else "pulled", i)
            self.assertEqual((les["agent"], les["yes_by"], les["fields"]), ("sales", TEAM, ["retail"]), i)
        self.assertEqual(lessons.get(1)["risk"], "high")
        self.assertEqual([p["id"] for p in lessons.pick("asking", "price")], [1, 2])
        with db.tx() as c:
            names = {r["name"] for r in c.execute("SELECT name FROM sqlite_master")}
        self.assertNotIn("lessons_before_engine", names)
        self.assertNotIn("lessons_stay_retired", names)
        self.assertTrue({"lessons_never_rewritten", "lessons_stay_pulled", "lessons_yes_stays"} <= names)
        with self.assertRaises(sqlite3.DatabaseError):
            with db.tx() as c:
                c.execute("UPDATE lessons SET text = 'x' WHERE id = 1")
        with self.assertRaises(sqlite3.DatabaseError):
            with db.tx() as c:
                c.execute("UPDATE lessons SET state = 'kept' WHERE id = 3")

    def test_it_moves_once(self):
        db = self.old_database()
        Lessons(db)
        lessons = Lessons(db)
        self.assertEqual(len(lessons.mine()), len(OLD_LESSONS))
        self.assertEqual(kept_lesson(lessons, "A new one.", ["all"]), len(OLD_LESSONS) + 1)


if __name__ == "__main__":
    unittest.main()
