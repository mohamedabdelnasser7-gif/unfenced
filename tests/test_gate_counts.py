"""The eval gate's counts (new, 2026-10-31; DECISIONS items 27 and 28): the cases each lesson fixed
and broke, McNemar's exact check on them, saved with the lesson's exam row, in the night report
and on the Morning page. The pass or fail rule does not move."""
import dataclasses
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from arena import gate, run
from engine import exam as engine_exam
from engine import lessons as engine_lessons
from engine.log import Log
from kit.db import Db
from reflection import PLUG
from reflection import exam, night
from reflection import morning as page_mod
from tests import plugs
from tests import study_fakes as fk
from tests.fake_model import Buyer, FakeModel, Seller, clean_env, say
from tests.test_arena_gate import LESSON, past
from tests.test_engine_lessons import always_low
from tests.test_ideas import SHADE, WALL, Ideas

Row, Pair, Result = engine_exam.Row, engine_exam.Pair, engine_exam.Result
LINE = "Water the shaded beds last."

# lesson_exams as it was before the counts (engine/exam.py at 249a588), to make an older database
OLD_TABLE = """
CREATE TABLE IF NOT EXISTS lesson_exams (
  lesson_id INTEGER PRIMARY KEY REFERENCES lessons (id),
  agent TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
  situation INTEGER,
  check_name TEXT,
  why TEXT,
  calls INTEGER NOT NULL DEFAULT 0,
  parts TEXT NOT NULL DEFAULT '{}',
  at REAL NOT NULL
);
CREATE TRIGGER IF NOT EXISTS lesson_exams_never_changed BEFORE UPDATE ON lesson_exams
BEGIN SELECT RAISE(ABORT, 'an exam row is never changed'); END;
CREATE TRIGGER IF NOT EXISTS lesson_exams_never_deleted BEFORE DELETE ON lesson_exams
BEGIN SELECT RAISE(ABORT, 'an exam row is never deleted'); END;
"""


def old_save(c, agent, lesson_id, result, now=None):
    """The save from before the counts: no count columns."""
    first = result.first
    c.execute("INSERT INTO lesson_exams (lesson_id, agent, passed, situation, check_name, why, calls, parts, at) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (lesson_id, agent, int(result.passed), first.situation if first else None,
               first.check if first else None, first.why if first else None, int(result.calls),
               json.dumps(result.parts()), time.time() if now is None else now))


def pairs(fixed=0, broke=0, right=0, wrong=0):
    """A hand-made set of pairs with these counts."""
    out = [Pair(f"situation f{i}", False, True) for i in range(fixed)]
    out += [Pair(f"situation b{i}", True, False) for i in range(broke)]
    out += [Pair(f"situation r{i}", True, True) for i in range(right)]
    return out + [Pair(f"situation w{i}", False, False) for i in range(wrong)]


def counted(passed, fixed=0, broke=0, right=0, wrong=0, fail_at=9):
    """An examiner whose result carries hand-made pairs; a fail names situation fail_at."""
    rows = [Row(1, "a", "guard", True)] if passed else [Row(fail_at, "a", "guard", False, "no_shop", "why")]
    return lambda text, tags: Result(passed, rows, calls=2, pairs=pairs(fixed, broke, right, wrong))


class McNemar(unittest.TestCase):
    """Known values of the exact two-sided binomial at even odds (the same as scipy's binomtest)."""

    def test_known_values(self):
        for fixed, broke, want in ((10, 0, 2 / 1024), (0, 10, 2 / 1024), (5, 5, 1.0), (8, 2, 0.109375),
                                   (2, 8, 0.109375), (9, 1, 22 / 1024), (6, 0, 0.03125), (5, 0, 0.0625),
                                   (1, 0, 1.0), (3, 2, 1.0), (20, 5, 0.004077315330505371)):
            with self.subTest(fixed=fixed, broke=broke):
                self.assertAlmostEqual(engine_exam.mcnemar(fixed, broke), want, places=12)

    def test_no_changed_case_makes_no_claim(self):
        self.assertIsNone(engine_exam.mcnemar(0, 0))
        self.assertEqual(engine_exam.chance_words(0, 0, None), "nothing changed either way")

    def test_only_whole_counts(self):
        for bad in (-1, 1.5, True, "3", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                engine_exam.mcnemar(bad, 1)

    def test_words(self):
        def words(f, b):
            return engine_exam.chance_words(f, b, engine_exam.mcnemar(f, b))
        self.assertEqual((words(10, 0), words(0, 10), words(5, 5), words(5, 0), words(6, 0), words(0, 0)),
                         ("likely a real gain", "likely real harm", "could be chance", "could be chance",
                          "likely a real gain", "nothing changed either way"))

    def test_p_text(self):
        self.assertEqual([engine_exam.p_text(p) for p in (2 / 1024, 1.0, 0.0001, 0.109375, 0.03125, None)],
                         ["0.002", "1", "under 0.001", "0.109", "0.031", "none"])


class Counts(unittest.TestCase):
    def test_counts_on_a_hand_made_set(self):
        before = [Row(1, "a", "guard", False, "x"), Row(2, "b", "guard", True), Row(3, "c", "real", True),
                  Row(4, "d", "real", False, "y"), Row(5, "e", "real", False, engine_exam.ANSWER, "the answer raised"),
                  Row(6, "f", "real", True), Row(7, "g", "real", False, "z"), Row(8, "h", "real", True)]
        after = [Row(1, "a", "guard", True), Row(2, "b", "guard", False, "x"), Row(3, "c", "real", True),
                 Row(4, "d", "real", False, "y"), Row(5, "e", "real", True),
                 Row(6, "f", "real", False, engine_exam.ANSWER, "the model could not answer"),
                 Row(7, "g", "real", True)]  # situation 8 never ran with the lesson
        got = engine_exam.pair_rows(before, after)
        self.assertEqual(got, [Pair("situation 1", False, True), Pair("situation 2", True, False),
                               Pair("situation 3", True, True), Pair("situation 4", False, False),
                               Pair("situation 7", False, True)])
        eff = engine_exam.effect(got)
        self.assertEqual({k: eff[k] for k in ("fixed", "broke", "both_right", "both_wrong", "fixed_cases", "broke_cases")},
                         {"fixed": 2, "broke": 1, "both_right": 1, "both_wrong": 1,
                          "fixed_cases": ["situation 1", "situation 7"], "broke_cases": ["situation 2"]})
        self.assertEqual(eff["p"], 1.0)

    def test_bigger_set_and_none(self):
        eff = engine_exam.effect(pairs(fixed=7, broke=2, right=38, wrong=3))
        self.assertEqual((eff["fixed"], eff["broke"], eff["both_right"], eff["both_wrong"]), (7, 2, 38, 3))
        self.assertAlmostEqual(eff["p"], 0.1796875)
        self.assertIsNone(engine_exam.effect([]))
        self.assertIsNone(engine_exam.effect_of(None))
        self.assertIsNone(engine_exam.effect_of({"fixed": None, "broke": None, "p_value": None}))

    def test_line(self):
        self.assertEqual(engine_exam.effect_line(engine_exam.effect_of({"fixed": 10, "broke": 0, "p_value": 2 / 1024})),
                         "gate counts: fixed 10, broke 0, McNemar p 0.002 (likely a real gain)")
        self.assertEqual(engine_exam.effect_line(engine_exam.effect_of({"fixed": 0, "broke": 0, "p_value": None})),
                         "gate counts: fixed 0, broke 0 (nothing changed either way)")


class FakeKept:
    def __init__(self, ids):
        self.ids = list(ids)

    def live(self):
        return [{"id": i, "state": engine_lessons.KEPT} for i in self.ids] + [{"id": 99, "state": engine_lessons.TRYING}]


SITS = exam.situations(PLUG)


class Examiner(unittest.TestCase):
    """The Sales agent's examiner with count=True: the run without the new line, once per kept set."""

    def setUp(self):
        self.runs = []

    def fake_run(self, plug, model, *, kept=None, lesson=None, stop_at_first=False, sits=None, safety=None):
        self.runs.append({"lesson": lesson, "stop": stop_at_first, "sits": None if sits is None else len(sits)})
        bad = lambda n, check: Row(n, "abcd"[n - 1], "guard", False, check, "why", ((check, "why"),))  # noqa: E731
        good = lambda n: Row(n, "abcd"[n - 1], "guard", True)  # noqa: E731
        if lesson is None:  # without: 1 wrong (order, safety), 2 right, 3 right, 4 wrong (script, style)
            return Result(False, [bad(1, "order"), good(2), good(3), bad(4, "script")], calls=4)
        words = lesson[0].lower()
        if "break" in words:  # a safety check newly fails on 2
            return Result(False, [good(1), bad(2, "order"), good(3), good(4)], calls=5)
        if "style" in words:  # only a style check newly fails on 2: reported, never blocking
            return Result(False, [good(1), bad(2, "script"), good(3), good(4)], calls=5)
        if "worse" in words:  # style only, but it breaks 2 and fixes 1
            return Result(False, [bad(1, "order"), bad(2, "script"), bad(3, "echo"), good(4)], calls=5)
        if "same" in words:  # the safety fail of 1 was there before: not new
            return Result(False, [bad(1, "order"), good(2), good(3), good(4)], calls=5)
        return Result(True, [good(1), good(2), good(3), good(4)], calls=6)

    def examiner(self, kept=None):
        self.enterContext(mock.patch.object(exam, "situations", lambda plug: SITS[:4]))
        self.enterContext(mock.patch.object(exam, "run", side_effect=self.fake_run))
        return exam.Examiner(PLUG, kept=kept, model=object(), count=True)

    def test_counts_and_the_run_without_once_per_kept_set(self):
        kept = FakeKept([3, 1])
        ex = self.examiner(kept)
        r1 = ex("Fix both.", ("asking",))
        r2 = ex("This one will break situation 2.", ("asking",))
        kept.ids.append(7)  # a lesson kept since: the run without is made again
        ex("Fix both.", ("asking",))
        self.assertEqual([(x["lesson"] is None, x["stop"], x["sits"]) for x in self.runs],
                         [(True, False, 4), (False, False, 4), (False, False, 4), (True, False, 4), (False, False, 4)])
        self.assertEqual(ex._kept_ids(), (1, 3, 7))
        e1, e2 = engine_exam.effect(r1.pairs), engine_exam.effect(r2.pairs)
        self.assertEqual((r1.passed, e1["fixed"], e1["broke"], r1.calls), (True, 2, 0, 6 + 4))
        self.assertEqual((r2.passed, e2["fixed"], e2["broke"], r2.calls), (False, 2, 1, 5))  # the run without counted once
        self.assertEqual(r2.line(), "failed the exam: situation 2, check order")

    def test_the_pass_rule(self):
        """DECISIONS item 75: no safety check newly fails, and fixed at least broke; style only reports."""
        ex = self.examiner(FakeKept([1]))
        style, worse, same = ex("A style slip on 2.", ("asking",)), ex("Worse on wording.", ("asking",)), \
            ex("The same fail on 1.", ("asking",))
        e = engine_exam.effect(style.pairs)
        self.assertEqual((style.passed, e["fixed"], e["broke"], style.line()), (True, 2, 1, ""))
        self.assertEqual([r.check for r in style.rows if not r.passed], ["script"])  # still reported in the rows
        self.assertFalse(worse.passed)
        self.assertEqual((worse.first.check, worse.first.why), (engine_exam.COUNTS, "it broke 2 situations and fixed 1"))
        self.assertTrue(same.passed)

    def test_plug_safety_overrides_the_default(self):
        plug = dataclasses.replace(PLUG, exam=dataclasses.replace(PLUG.exam, safety=("script",)))
        self.assertEqual(engine_exam.safety_of(plug, exam.SAFETY), ("script",))
        self.assertEqual(engine_exam.safety_of(PLUG, exam.SAFETY), exam.SAFETY)
        self.enterContext(mock.patch.object(exam, "situations", lambda p: SITS[:4]))
        self.enterContext(mock.patch.object(exam, "run", side_effect=self.fake_run))
        ex = exam.Examiner(plug, kept=FakeKept([1]), model=object(), count=True)
        self.assertFalse(ex("A style slip on 2.", ("asking",)).passed)  # script blocks for this plug
        self.assertTrue(ex("This one will break situation 2.", ("asking",)).passed)  # order only reports here

    def test_count_off_is_the_gate_as_before(self):
        ex = exam.Examiner(PLUG, model=object())
        with mock.patch.object(exam, "run", side_effect=self.fake_run):
            r = ex("Fix both.", ("asking",))
        self.assertEqual([(x["lesson"] is None, x["stop"]) for x in self.runs], [(False, True)])
        self.assertEqual(r.pairs, [])

    def test_a_real_run_pairs_every_situation(self):
        """Through the real exam, on a model that answers the same with and without the line."""
        clean_env(self)

        class Same:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                return say("هسأل الفريق وأرد عليك.")

        r = exam.Examiner(PLUG, model=Same(), count=True)("Answer greetings warmly, then ask what they need.", ("asking",))
        eff = engine_exam.effect(r.pairs)
        self.assertEqual((len(r.rows), len(r.pairs), eff["fixed"], eff["broke"], eff["p"]), (50, 50, 0, 0, None))
        self.assertTrue(r.passed)  # nothing newly fails and nothing broke (DECISIONS item 75)
        self.assertFalse(all(row.passed for row in r.rows))  # its fails are still in the rows

    def test_sales_exam_counts(self):
        self.assertTrue(night.sales_exam(PLUG)(None).count)


class GatePairs(unittest.TestCase):
    """arena/gate.py keeps the exam's pairs and adds one for each rerun the verdict judged."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def gate(self, examiner, agent, customer, wins=None):
        return gate.Gate(examiner, wins=wins or [past()], agent_model=agent, customer_model=customer,
                         calls=run.Calls(self.dir / "calls.json", 300, day="2026-10-30"))

    def test_a_kept_win_adds_a_pair_right_on_both_sides(self):
        r = self.gate(counted(True, fixed=1, right=2), Seller(), Buyer())(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual(r.pairs[-1], Pair("rerun m1", True, True))
        eff = engine_exam.effect(r.pairs)
        self.assertEqual((eff["fixed"], eff["broke"], eff["both_right"]), (1, 0, 3))

    def test_a_win_now_lost_counts_as_broke_and_still_holds(self):
        r = self.gate(counted(True, fixed=3), Seller("The Football Boots, Black are 700 EGP."), Buyer())(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(r.first.check, gate.CHECK)
        self.assertEqual(r.pairs[-1], Pair("rerun m1", True, False))
        eff = engine_exam.effect(r.pairs)
        self.assertEqual((eff["fixed"], eff["broke"], eff["broke_cases"]), (3, 1, ["rerun m1"]))

    def test_exam_fail_keeps_its_pairs_and_reruns_nothing(self):
        customer = FakeModel()
        r = self.gate(counted(False, fixed=2, broke=1), FakeModel(), customer)(LESSON, ("all",))
        self.assertEqual((r.passed, len(r.pairs), customer.calls), (False, 3, []))

    def test_a_rerun_never_judged_is_no_pair(self):
        r = self.gate(counted(True, fixed=1), FakeModel(), FakeModel(), wins=[dict(past(), persona=None)])(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(r.pairs, pairs(fixed=1))


class Saved(unittest.TestCase):
    """The counts go with the lesson's exam row; a database from before them gets the columns."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = Path(d.name) / "old.db"

    def open(self):
        db = Db(self.path)
        self.addCleanup(db.close)
        return db

    def test_saved_with_the_row(self):
        db = self.open()
        les = engine_lessons.Lessons(db, PLUG, judge=always_low, exam=counted(False, fixed=10, right=30, wrong=1))
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        row = les.exam_of(i)
        self.assertEqual((row["passed"], row["fixed"], row["broke"]), (0, 10, 0))
        self.assertAlmostEqual(row["p_value"], 2 / 1024)
        detail = json.loads(row["effect"])
        self.assertEqual((len(detail["fixed_cases"]), detail["broke_cases"], detail["both_right"], detail["both_wrong"]),
                         (10, [], 30, 1))
        self.assertEqual(engine_exam.effect_of(row)["words"], "likely a real gain")
        self.assertEqual(les.get(i)["state"], "waiting")  # held as before: the counts decide nothing

    def test_no_pairs_no_counts(self):
        db = self.open()
        les = engine_lessons.Lessons(db, PLUG, judge=always_low,
                                     exam=lambda t, s: Result(True, [Row(1, "a", "guard", True)], calls=1))
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        row = les.exam_of(i)
        self.assertEqual((row["fixed"], row["broke"], row["p_value"], row["effect"]), (None, None, None, None))
        self.assertIsNone(engine_exam.effect_of(row))
        self.assertEqual(les.get(i)["state"], "trying")

    def test_migration_on_an_old_database(self):
        db = self.open()
        with mock.patch.object(engine_exam, "ensure", lambda d: d.script(OLD_TABLE)), \
                mock.patch.object(engine_exam, "save", old_save):
            les = engine_lessons.Lessons(db, PLUG, judge=always_low, exam=counted(False, fixed=4))
            old = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        cols = [r[1] for r in db.conn.execute("PRAGMA table_info(lesson_exams)")]
        self.assertNotIn("fixed", cols)
        db.close()
        db = self.open()  # opened again with today's code
        les = engine_lessons.Lessons(db, PLUG, judge=always_low, exam=counted(False, fixed=6, broke=0))
        cols = [r[1] for r in db.conn.execute("PRAGMA table_info(lesson_exams)")]
        self.assertEqual(cols[-5:], ["fixed", "broke", "p_value", "effect", "fails"])
        row = les.exam_of(old)
        self.assertEqual((row["fixed"], row["p_value"]), (None, None))  # not counted, never zero
        self.assertIsNone(engine_exam.effect_of(row))
        self.assertEqual(engine_exam.held_line(row), "failed the exam: situation 9, check no_shop")
        new = les.propose("Ask for the size first.", ["asking"], sources=[])
        self.assertEqual(engine_exam.effect_of(les.exam_of(new)),
                         {"fixed": 6, "broke": 0, "p": 0.03125, "words": "likely a real gain"})
        with self.assertRaises(sqlite3.DatabaseError):  # the rows still never change
            with db.tx() as c:
                c.execute("UPDATE lesson_exams SET fixed = 1 WHERE lesson_id = ?", (old,))
        engine_exam.ensure(db)  # again: nothing to add
        page = page_mod.Morning(db, [PLUG], by="mona", judge=always_low)  # the page opens it too
        self.assertEqual({i["id"]: i["gate"] is None for a in page.view()["agents"] for i in a["waiting"]},
                         {old: True, new: False})

    def test_a_column_another_connection_added_first(self):
        db = self.open()
        engine_exam.ensure(db)

        class Stale:  # its column list was read before another connection added the columns
            def __init__(self, c):
                self.c = c

            def execute(self, sql, *args):
                return iter([]) if sql.startswith("PRAGMA") else self.c.execute(sql, *args)

        class Late:
            script = db.script

            @contextmanager
            def tx(self):
                with db.tx() as c:
                    yield Stale(c)

        engine_exam.ensure(Late())  # "duplicate column" is taken as done


class NightCounts(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        fk.beds(Log(self.db, self.plug), note=WALL)

    def run_night(self, exam=None):
        return night.night(self.db, self.plug, until=fk.UNTIL, days=30, others=[], judge=always_low,
                           proposer=fk.Proposer(), tagger=fk.Tagger(), ideas=Ideas(SHADE), exam=exam)

    def test_the_card_and_the_report_carry_the_counts(self):
        rep = self.run_night(lambda kept: counted(False, fixed=6, right=40))
        card, = rep["cards"]
        self.assertEqual(card["gate"], {"fixed": 6, "broke": 0, "p": 0.03125, "words": "likely a real gain"})
        out = night.text(rep, self.plug)
        self.assertIn("check no_shop; a person's Yes on its card starts it anyway\n"
                      "      gate counts: fixed 6, broke 0, McNemar p 0.031 (likely a real gain)", out)

    def test_no_counts_no_line(self):
        rep = self.run_night(lambda kept: counted(True))
        self.assertNotIn("gate", rep["cards"][0])
        self.assertNotIn("gate counts", night.text(rep, self.plug))


class PageCounts(unittest.TestCase):
    """Each card waiting for a yes says fixed N, broke M, and the p-value in words."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.db = Db(Path(d.name) / "page.db")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)

    def page(self, examiner):
        return page_mod.Morning(self.db, [self.plug], by="mona", judge=always_low, exams={"waterer": examiner})

    def test_the_card_shows_the_counts_in_words(self):
        page = self.page(counted(False, fixed=10, right=30))
        page.idea("waterer", LINE, "seedling", now=fk.NOW)
        view = page.view(now=fk.NOW)
        card, = view["cards"]
        self.assertEqual(card["gate"]["words"], "likely a real gain")
        line = "Checked before use: fixed 10, broke 0. Likely a real gain."
        for token in ("t", None):
            html = page_mod.render(view, token=token)
            self.assertEqual(html.count(line), 1)
            self.assertIn(f'<p class="gain">{line}</p>', html)
        self.assertNotIn("p-value", page_mod.render(view, token="t"))

    def test_each_kind_of_words(self):
        for (fixed, broke), words in (((5, 5), "Could be chance."), ((0, 0), "Nothing changed either way."),
                                      ((0, 7), "Likely real harm.")):
            with self.subTest(fixed=fixed, broke=broke):
                item = {"fixed": fixed, "broke": broke, "p": engine_exam.mcnemar(fixed, broke)}
                item["words"] = engine_exam.chance_words(fixed, broke, item["p"])
                self.assertEqual(page_mod.gate_line(item), f"Checked before use: fixed {fixed}, broke {broke}. {words}")

    def test_no_counts_no_line(self):
        page = self.page(lambda t, s: Result(False, [Row(9, "a", "guard", False, "no_shop", "why")], calls=1))
        page.idea("waterer", LINE, "seedling", now=fk.NOW)
        view = page.view(now=fk.NOW)
        self.assertIsNone(view["cards"][0]["gate"])
        self.assertNotIn("Checked before use", page_mod.render(view, token="t"))

    def test_a_lesson_on_trial_shows_no_count_line(self):
        page = self.page(counted(True, fixed=3))
        self.assertIn("It is on trial.", page.idea("waterer", LINE, "seedling", now=fk.NOW))
        self.assertNotIn("Checked before use", page_mod.render(page.view(now=fk.NOW), token="t"))


if __name__ == "__main__":
    unittest.main()
