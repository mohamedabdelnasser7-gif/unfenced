"""The hotfix inside the Arena (arena/rounds.py live_hotfixes and Pool.refresh, arena/run.py; Mohamed
2026-11-02, "So hotfix should be in arena too then", and "It shouldn't make the same mistake in the
same run"): a correction the user types on the live page while a run goes on, once it passed its
exam and runs there as a hotfix, is handed from the next match on. The live database is only read.
Fake models only, no network; the cards are made here."""
import sqlite3
import time
import unittest
from pathlib import Path

from arena import rounds
from engine import exam as engine_exam
from engine import risk
from engine.lessons import HOTFIX_SOURCE, KEPT, MAX_PICK, Lessons
from kit.db import Db
from reflection import PLUG
from reflection.lessons import Lessons as SalesLessons
from tests import plugs
from tests.test_arena_rounds import Base, Customer, GOOD
from tests.kept import kept_lesson

FIX = "Say the size chart link is on the product page."


def low(text, high_about, low_about):
    return risk.LOW


def passed(text, tags):
    return engine_exam.Result(True, [engine_exam.Row(1, "s1", "guard", True)], calls=1)


def failed(text, tags):
    return engine_exam.Result(False, [engine_exam.Row(1, "s1", "guard", False, "price", "no price given")], calls=1)


def correct(path, text, exam=passed, agent_lessons=None, now=None):
    """A correction on the live page, as reflection/morning.py correct saves it."""
    d = Db(str(path))
    try:
        L = agent_lessons(d) if agent_lessons else SalesLessons(d, judge=low)
        return L.correct(text, ["all"], yes_by="the user", exam=exam(text, ()), now=now)
    finally:
        d.close()


def counts(path):
    con = sqlite3.connect(str(path))
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        con.close()


class Reading(Base):
    def test_only_a_passed_running_correction_is_read(self):
        db = self.db()
        d = Db(str(db))
        try:
            kept_lesson(SalesLessons(d), "Ask which size they wear.", ["all"])  # kept, but no correction
        finally:
            d.close()
        before = correct(db, "Tell them it arrives tomorrow.", now=time.time() - 60)
        held = correct(db, "Never name a price.", exam=failed)
        fix = correct(db, FIX)
        got = rounds.live_hotfixes(db, PLUG.agent)
        self.assertEqual([g["live_id"] for g in got], [fix])
        self.assertNotIn(before, [g["live_id"] for g in got])  # high risk: it waits for a yes, so it is not running
        self.assertNotIn(held, [g["live_id"] for g in got])
        one = got[0]
        self.assertEqual((one["id"], one["state"], one["stages"], one["source"]), (-fix, KEPT, ["all"], HOTFIX_SOURCE))
        self.assertEqual(rounds.live_hotfixes(db, "someone_else"), [])

    def test_one_running_before_the_run_started_is_read_too(self):
        """Review merge r1 finding 4: the copy hands kept lessons only, so a hotfix already on trial
        live when the run starts comes from this read or from nowhere."""
        db = self.db()
        before = correct(db, FIX, now=time.time() - 3600)
        self.assertEqual([g["live_id"] for g in rounds.live_hotfixes(db, PLUG.agent)], [before])

    def test_a_built_agents_correction_is_read_by_its_name(self):
        db = self.db()
        plug = plugs.load(plugs.WATERER, self)
        fix = correct(db, "Water the roots, not the leaves.", agent_lessons=lambda d: Lessons(d, plug, judge=low))
        got = rounds.live_hotfixes(db, plug.agent)
        self.assertEqual([g["live_id"] for g in got], [fix])

    def test_the_live_database_is_opened_read_only(self):
        db = self.db()
        correct(db, FIX)
        before = counts(db)
        mtime = Path(db).stat().st_mtime_ns
        rounds.live_hotfixes(db, PLUG.agent)
        self.assertEqual((counts(db), Path(db).stat().st_mtime_ns), (before, mtime))
        with self.assertRaises(sqlite3.Error):  # no database there: an error, never a new file
            rounds.live_hotfixes(self.dir / "none.db", PLUG.agent)
        self.assertFalse((self.dir / "none.db").exists())


class ThePool(Base):
    def pool(self):
        copy = Db(":memory:")
        self.addCleanup(copy.close)
        return rounds.Pool(SalesLessons(copy), hotfixes=lambda: self.got), SalesLessons(copy)

    def fix(self, live_id, text=FIX, stages=("all",)):
        return {"id": -live_id, "live_id": live_id, "text": text, "stages": list(stages), "fields": [],
                "state": KEPT, "score": 0}

    def test_a_correction_is_handed_first_only_after_a_refresh(self):
        pool, copy = self.pool()
        for i in range(MAX_PICK):
            kept_lesson(copy, f"Kept line number {chr(97 + i)}.", ["all"])
        self.got = [self.fix(7)]
        self.assertNotIn(FIX, [p["text"] for p in pool.pick("greeting", "hi")])
        pool.refresh()
        picked = pool.pick("greeting", "hi")
        self.assertEqual(picked[0]["text"], FIX)  # first, so the cap on lessons never cuts it
        self.assertEqual(len(picked), MAX_PICK)
        self.assertEqual(pool.seen, [7])

    def test_one_pulled_live_since_is_no_longer_handed(self):
        pool, _ = self.pool()
        self.got = [self.fix(7)]
        pool.refresh()
        self.got = []
        pool.refresh()
        self.assertEqual(pool.pick("greeting", "hi"), [])

    def test_a_busy_live_database_keeps_the_last_read(self):
        pool, _ = self.pool()
        self.got = [self.fix(7)]
        pool.refresh()

        def busy():
            raise sqlite3.OperationalError("database is locked")
        pool.hotfixes = busy
        pool.refresh()
        self.assertEqual([p["text"] for p in pool.pick("greeting", "hi")], [FIX])
        self.assertIn(rounds.LIVE_BUSY, pool.busy)

    def test_another_stage_and_a_line_the_copy_holds_are_not_handed(self):
        pool, copy = self.pool()
        kept_lesson(copy, FIX, ["all"])
        self.got = [self.fix(7), self.fix(8, "Ask about the colour.", ("closing",))]
        pool.refresh()
        self.assertEqual([p["text"] for p in pool.pick("greeting", "hi")], [FIX])  # the copy's own, once
        self.assertEqual(pool._fixes("closing")[0]["text"], "Ask about the colour.")


class TypedMidRun(Base):
    def run_typing(self, db, exam=passed, **kw):
        """An Arena run on db while the user types FIX on the live page during the first match."""
        import tests.test_arena_rounds as tar
        typed = []

        class Typing(Customer):
            def chat(inner, messages, **more):
                if not typed:
                    typed.append(correct(db, FIX, exam=exam))
                return Customer.chat(inner, messages, **more)
        orig, tar.Customer = tar.Customer, Typing
        try:
            code, rep = self.cli(db, **kw)
        finally:
            tar.Customer = orig
        self.assertTrue(typed)
        return rep

    def test_a_correction_typed_during_a_match_plays_from_the_next_match(self):
        db = self.db()
        self.run_typing(db, ideas=[], rounds_n=1)
        systems = self.agent.systems
        self.assertNotIn(FIX, systems[0])  # the match it was typed in goes on without it
        self.assertIn(FIX, systems[-1])
        live = counts(db)
        self.assertEqual(live.get("lessons"), 1)  # only the correction: no practice data written there
        self.assertEqual(live.get("trace", 0), 0)

    def test_a_correction_held_by_its_exam_is_never_handed(self):
        db = self.db()
        self.run_typing(db, exam=failed, ideas=[], rounds_n=1)
        self.assertFalse(any(FIX in s for s in self.agent.systems))

    def test_the_report_between_rounds_names_the_corrections_handed(self):
        db = self.db()
        rep = self.run_typing(db, ideas=[GOOD], rounds_n=2)
        got = rep["rounds"][0].get("reflection") or {}
        self.assertEqual(len(got.get("hotfixes") or []), 1)
        self.assertTrue(any("corrections from the live page" in n for n in got.get("notes") or []))


if __name__ == "__main__":
    unittest.main()
