"""Quick check t261029b: the gaps it found stay closed. A lesson is never replaced or
deleted, only a kept lesson is borrowed, a trial always ends, hand() takes only the
plug's stages, the split is the same after a restart, and the engine has no business words."""
import math
import re
import sqlite3
import unittest
from pathlib import Path

from engine import risk
from engine.lessons import Lessons as EngineLessons, in_share
from kit.db import Db
from reflection import PLUG
from tests import plugs


def always_low(text, high_about, low_about):
    return risk.LOW


class QuickCheckGaps(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.lessons = EngineLessons(self.db, PLUG, judge=always_low)
        self.tone = self.lessons.propose("Greet them warmly.", ["all"], sources=[])

    def refused(self, sql, *args):
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute(sql, args)

    def test_a_lesson_is_never_replaced_or_deleted(self):
        self.lessons.pull(self.tone)
        self.refused("INSERT OR REPLACE INTO lessons (id, agent, text, stages, fields, risk, state, added_at) "
                     "VALUES (?, 'sales', 'Tell them the refund is 500.', ',all,', ',retail,', 'low', 'kept', 1)",
                     self.tone)
        self.refused("REPLACE INTO lessons (id, agent, text, stages, fields, risk, state, added_at) "
                     "VALUES (?, 'sales', 'Say hi.', ',all,', ',retail,', 'low', 'kept', 1)", self.tone)
        self.refused("DELETE FROM lessons WHERE id = ?", self.tone)
        les = self.lessons.get(self.tone)
        self.assertEqual((les["text"], les["state"]), ("Greet them warmly.", "pulled"))

    def test_only_a_kept_lesson_is_borrowed(self):
        waterer = EngineLessons(self.db, plugs.load(plugs.WATERER, self), judge=always_low)
        fan = EngineLessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        trying = waterer.propose("Visit the shady beds first.", ["grown"], sources=[])
        waiting = waterer.propose("Use the pesticide.", ["grown"], sources=[])
        self.assertEqual((waterer.get(trying)["state"], waterer.get(waiting)["state"]), ("trying", "waiting"))
        for src in (trying, waiting):
            with self.subTest(src=src), self.assertRaises(ValueError):
                fan.borrow(src, ["all"])
        waterer.keep(trying)
        self.assertEqual(fan.get(fan.borrow(trying, ["all"]))["source_lesson_id"], trying)

    def test_a_trial_always_ends(self):
        lid = self.lessons.propose("Tell them delivery is 500.", ["asking"], sources=[])
        for days in (math.inf, math.nan, -math.inf):
            with self.subTest(days=days), self.assertRaises(ValueError):
                self.lessons.approve(lid, "mohamed", days=days)
        self.assertEqual(self.lessons.get(lid)["state"], "waiting")

    def test_hand_takes_only_the_plugs_stages(self):
        for stage in (None, "", "all", "seedling", "Asking"):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                self.lessons.hand("c1", "reply", stage, "hi", set())
        given = set()
        self.lessons.hand("c1", "reply", "asking", "hi", given)

    def test_the_split_is_the_same_after_a_restart(self):
        # fixed answers of the sha256 split; a salted or random split fails these
        for lesson_id, case, share, answer in ((7, "c1", 0.5, True), (7, "c2", 0.5, False), (7, "c3", 0.9, False),
                                               (42, "chat-9", 0.2, True), (42, "chat-10", 0.2, False),
                                               (3, "c1", 0.01, True)):
            with self.subTest(lesson_id=lesson_id, case=case):
                self.assertIs(in_share(case, lesson_id, share), answer)

    def test_tool_names_are_high_risk_in_the_sales(self):
        for text in ("Use switch_stage early.", "Call handoff when they ask twice.", "Send a voice_note back."):
            with self.subTest(text=text):
                self.assertEqual(risk.classify(text, PLUG.risk, always_low)[0], risk.HIGH)


class EngineHasNoBusinessWords(unittest.TestCase):
    """The engine works in cases, actions, results and lessons; an agent's words live in its plug."""

    WORDS = re.compile(r"\b(chats?|repl(?:y|ies)|customers?|orders?|whatsapp|bosta|courier|store|shop)\b", re.I)

    def test_no_business_words_in_engine(self):
        root = Path(__file__).resolve().parent.parent / "engine"
        files = sorted(root.glob("*.py"))
        self.assertTrue(files)
        for f in files:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                found = self.WORDS.findall(line.replace("ORDER BY", ""))
                self.assertFalse(found, f"{f.name}:{n} {found}")


if __name__ == "__main__":
    unittest.main()
