"""The exam's pass rule (DECISIONS item 75, amends 27): safety checks block only when they newly fail,
fixed must be at least broke, style checks only report."""
import json
import tempfile
import unittest
from pathlib import Path

from arena import gate, run
from engine import exam as engine_exam
from engine import plug as plug_mod
from reflection import turn_exam
from tests.fake_model import Buyer, Seller, clean_env
from tests.test_arena_gate import LESSON, past

Row, Result = engine_exam.Row, engine_exam.Result
SAFETY = ("amounts",)


def situation(n):
    return {"id": n, "name": f"s{n}", "part": "guard"}


def checks(**fails):
    """{name: check}: each named check fails on the situation ids given."""
    return {name: (lambda ids, name=name: lambda s, did: f"{name} failed" if s["id"] in ids else "")(ids)
            for name, ids in fails.items()}


def bad(n, *names):
    return Row(n, f"s{n}", "guard", False, names[0], "why", tuple((c, "why") for c in names))


def good(n):
    return Row(n, f"s{n}", "guard", True)


class EveryFailIsKept(unittest.TestCase):
    def test_a_style_fail_never_hides_a_safety_fail(self):
        sits = [situation(1)]
        got = engine_exam.sit(sits, lambda s, les: {}, checks(script=[1], amounts=[1]), ("script", "amounts"))
        self.assertEqual(got.rows[0].check, "script")
        self.assertEqual([c for c, _ in got.rows[0].fails], ["script", "amounts"])

    def test_with_safety_only_a_safety_fail_blocks_and_stops(self):
        sits = [situation(1), situation(2), situation(3)]
        names = ("script", "amounts")
        style = engine_exam.sit(sits, lambda s, les: {}, checks(script=[1], amounts=[]), names, stop_at_first=True,
                                safety=SAFETY)
        self.assertEqual((style.passed, len(style.rows)), (True, 3))
        held = engine_exam.sit(sits, lambda s, les: {}, checks(script=[], amounts=[2]), names, stop_at_first=True,
                               safety=SAFETY)
        self.assertEqual((held.passed, len(held.rows), held.line()), (False, 2, "failed the exam: situation 2, check amounts"))

    def test_with_no_safety_list_every_check_blocks_as_before(self):
        got = engine_exam.sit([situation(1)], lambda s, les: {}, checks(script=[1]), ("script",))
        self.assertFalse(got.passed)


class Judge(unittest.TestCase):
    def test_a_safety_fail_there_before_is_not_new(self):
        r = engine_exam.judge([bad(1, "amounts"), good(2)], [bad(1, "amounts"), bad(2, "script")], 2, SAFETY)
        self.assertTrue(r.passed)
        self.assertEqual(engine_exam.effect(r.pairs)["fixed"], 1)

    def test_a_new_safety_fail_holds_even_behind_a_style_one(self):
        r = engine_exam.judge([bad(1, "script", "amounts"), good(2)], [bad(1, "script"), bad(2, "script")], 2, SAFETY)
        self.assertFalse(r.passed)
        self.assertEqual((r.first.situation, r.first.check), (1, "amounts"))

    def test_fixed_must_be_at_least_broke(self):
        r = engine_exam.judge([bad(1, "script"), bad(2, "script"), good(3)], [good(1), good(2), bad(3, "script")], 3, SAFETY)
        self.assertFalse(r.passed)
        self.assertEqual((r.first.check, r.first.situation), (engine_exam.COUNTS, 1))
        even = engine_exam.judge([bad(1, "script"), good(3)], [good(1), bad(3, "script")], 2, SAFETY)
        self.assertTrue(even.passed)

    def test_always_blocking(self):
        raised = Row(1, "s1", "guard", False, engine_exam.ANSWER, "the answer raised")
        self.assertFalse(engine_exam.judge([raised], [raised], 1, SAFETY).passed)
        missing = Row(1, "s1", "guard", False, "nope", engine_exam.NO_CHECK, (("nope", engine_exam.NO_CHECK),))
        self.assertFalse(engine_exam.judge([missing], [missing], 1, SAFETY).passed)
        self.assertFalse(engine_exam.judge([bad(1, engine_exam.GOOD)], [good(1)], 1, ()).passed)

    def test_a_short_run_never_passes(self):
        self.assertFalse(engine_exam.judge([good(1)], [good(1)], 2, SAFETY).passed)

    def test_a_safety_fail_where_the_run_before_raised_counts_as_new(self):
        raised = Row(1, "s1", "guard", False, engine_exam.ANSWER, "the answer raised")
        self.assertFalse(engine_exam.judge([bad(1, "amounts")], [raised], 1, SAFETY).passed)

    def test_the_saved_row_names_the_blocking_check(self):
        from kit.db import Db
        db = Db(":memory:")
        self.addCleanup(db.close)
        engine_exam.ensure(db)
        db.script("PRAGMA foreign_keys = OFF")
        r = engine_exam.judge([bad(1, "script", "amounts")], [good(1)], 1, SAFETY)
        ok = engine_exam.judge([bad(1, "script")], [bad(1, "script")], 1, SAFETY)
        with db.tx() as c:
            engine_exam.save(c, "a", 1, r, now=1.0)
            engine_exam.save(c, "a", 2, ok, now=1.0)
            held, passed = engine_exam.of(c, "a", 1), engine_exam.of(c, "a", 2)
        self.assertEqual((held["check_name"], json.loads(held["fails"])[0]["check"]), ("amounts", "amounts"))
        self.assertEqual((passed["passed"], passed["check_name"], passed["situation"]), (1, None, None))


class PlugSafety(unittest.TestCase):
    def plug(self, exam):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        raw = json.loads((Path(plug_mod.__file__).resolve().parent.parent / "sales" / "plug.json").read_text())
        raw["exam"] = exam
        p = Path(d.name) / "plug.json"
        p.write_text(json.dumps(raw))
        return plug_mod.load(p)

    def test_safety_is_optional_and_must_name_checks_the_exam_runs(self):
        self.assertIsNone(self.plug({"situations": "e.json", "checks": ["a", "b"]}).exam.safety)
        self.assertEqual(self.plug({"situations": "e.json", "checks": ["a", "b"], "safety": ["b"]}).exam.safety, ("b",))
        with self.assertRaises(ValueError):
            self.plug({"situations": "e.json", "checks": ["a"], "safety": ["c"]})

    def test_build_writes_the_built_agents_safety(self):
        got = turn_exam.plug_exam()
        self.assertEqual(got["safety"], list(turn_exam.SAFETY))
        self.assertNotIn("send_check", got["safety"])
        self.assertTrue(set(got["safety"]) <= set(got["checks"]))


class TheRerunReadsOnlyItsOwnRows(unittest.TestCase):
    def test_an_exam_pass_with_style_fails_goes_on_to_pass_the_rerun(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        passed_with_style = lambda text, tags: Result(True, [bad(1, "script"), good(2)], calls=1)  # noqa: E731
        g = gate.Gate(passed_with_style, wins=[past()], agent_model=Seller(), customer_model=Buyer(),
                      calls=run.Calls(Path(d.name) / "calls.json", 300, day="2026-10-30"))
        r = g(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)


if __name__ == "__main__":
    unittest.main()
