"""The run shape of decision 113, Stop for Arena runs and the day's call cap setting (Mohamed 2026-11-05: at most
30 matches; round 1 is 10 practice matches and the gate, a gate at the level passes at once; when it misses, the
study, 10 more practice matches and no gate, and the run passes on its average over the 30 at 7 of 10 with no
broken never line; Arena runs need a Stop button; the daily call cap goes to 3000). Scripted matches only: no
model call, no network."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import levels, practice, retry, run
from engine import plug as plug_mod
from kit.db import Db
from reflection import morning as mo
from tests.test_arena_practice import FIXTURE

ROOT = Path(__file__).resolve().parent.parent
TRUST = {"matches": 10, "wins": 7, "zero_failed_checks": True}
NOW = 1_800_000_000.0


def env(**values):
    """os.environ with the cap setting removed, then values set."""
    out = {k: v for k, v in os.environ.items() if k != run.CAP_ENV}
    out.update(values)
    return mock.patch.dict(os.environ, out, clear=True)


class Scripted(run.Arena):
    """arena/run.py Arena with each match's result scripted: gate[r] is round r's gate wins (the first that many
    gate matches won, the rest lost), practice[r] its practice wins the same way (none by default), never[r] the
    practice match numbers of round r that lost and broke a never line. after(n) is called once n matches have
    played, so a test can press Stop mid run."""

    def __init__(self, folder, gate, after=None, practice=None, never=None, **kw):
        cards = run.load_cards(run.DEMO_CARDS)
        calls = run.Calls(folder / run.CALLS_FILE, 10_000)
        super().__init__(cards, agent_model=object(), customer_model=object(), calls=calls, trust=dict(TRUST),
                         state=folder, now=lambda: NOW, **kw)
        self.gate_script, self.after, self.played = gate, after, 0
        self.practice_script, self.never_script = practice or {}, never or {}

    def play(self, card, match_id, *, opening=None, lessons=None, replay=None, training=False):
        self.played += 1
        if self.after is not None:
            self.after(self.played)
        r = int(match_id.rsplit("-r", 1)[1].split("-")[0])
        broke = False
        if training:
            k = int(match_id.rsplit("-t", 1)[1])
            broke = k in self.never_script.get(r, ())
            won = k <= self.practice_script.get(r, 0) and not broke
        else:
            k = int(match_id.rsplit("-g", 1)[1])
            won = k <= self.gate_script.get(r, 0)
        judged = {"won": won, "why": "order placed" if won else "the customer left after this reply",
                  "quote": {"turn": 1, "who": "agent", "text": "a reply"}}
        if broke:
            judged["never_broken"] = True
        return {"id": match_id, "card": card["id"]}, judged


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.folder = Path(d.name).resolve()
        p = env()
        p.start()
        self.addCleanup(p.stop)

    def arena(self, gate, matches=3, **kw):
        return Scripted(self.folder, gate, matches=matches, **kw)

    def full(self, gate, **kw):
        """The real shape: 10 practice matches a round, a gate of 10, 2 rounds."""
        return self.arena(gate, matches=10, **kw)

    def morning(self):
        db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(db.close)
        return mo.Morning(db, [plug_mod.load(ROOT / "sales" / "plug.json")], reports=self.folder)


class TheShape(Base):
    def test_two_rounds_the_second_practice_only_for_the_sales_agent_and_every_level(self):
        self.assertEqual(run.DEFAULT_ROUNDS, 2)
        self.assertEqual(run.parser().parse_args(["--state", "x"]).rounds, 2)
        for level, shape in levels.LEVELS.items():
            with self.subTest(level=level):
                self.assertEqual((shape["rounds"], shape["matches"]), (2, 10))

    def test_a_gate_at_the_level_passes_at_once_after_20(self):
        a = self.full({1: 7})
        rep = a.run()
        self.assertEqual((rep["stopped"], len(rep["rounds"]), a.played), (run.PASSED, 1, 20))
        self.assertNotIn("passed_on", rep)
        self.assertNotIn("passed_on", rep["item"])
        self.assertTrue(self.morning().gate("sales")["passed"])

    def test_a_missed_gate_plays_10_more_practice_matches_and_no_gate_30_at_most(self):
        studied = []
        a = self.full({1: 6, 2: 10}, between=lambda r: studied.append(r) or {"after_round": r, "cases": 0})
        rep = a.run()
        self.assertEqual((a.played, len(rep["rounds"]), studied), (30, 2, [1]))
        two = rep["rounds"][1]
        self.assertTrue(two.get("practice_only"))
        self.assertEqual((two["training"]["played"], two["gate"]["played"]), (10, 0))
        self.assertEqual(rep["stopped"], run.ROUNDS)
        self.assertNotIn("passed_on", rep)
        item = rep["item"]
        self.assertEqual((item["gate_won"], item["gate_played"]), (6, 10))  # the gate that played, not round 2
        self.assertTrue(item["lost"])  # the page shows the losses
        self.assertEqual(item["line"], "The Arena played 30 matches and did not pass: 6 of 10 gate matches won, "
                                       "7 needed, and 6 of 30 in all.")
        self.assertEqual(item["reflection"][1]["practice_only"], True)
        self.assertIn("no gate (practice only)", run.text(rep))
        self.assertFalse(self.morning().gate("sales")["passed"])


class TheAverage(Base):
    def test_21_of_30_passes_on_its_average(self):
        rep = self.full({1: 6}, practice={1: 8, 2: 7}).run()
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual(len(rep["rounds"]), 2)
        self.assertEqual(rep["passed_on"], run.AVERAGE)
        avg = rep["average"]
        self.assertEqual((avg["won"], avg["played"], avg["practice"], avg["gate"]), (21, 30, 20, 10))
        item = rep["item"]
        self.assertEqual((item["stopped"], item["passed_on"]), (run.PASSED, run.AVERAGE))
        self.assertEqual(item["line"], "Passed on its average over 30 matches: 21 of 30.")
        self.assertIn("Passed on its average over 30 matches: 21 of 30.", run.text(rep))
        m = self.morning()
        gate = m.gate("sales")
        self.assertTrue(gate["passed"])  # unlocks Connect like a gate pass
        self.assertTrue(gate["said"].startswith("Passed on its average over 30 matches: 21 of 30."))
        status = m.arena_status("sales")
        self.assertEqual(status["line"], "Passed on its average over 30 matches: 21 of 30. " + mo.READY)
        self.assertEqual(status["next"], "connect")

    def test_20_of_30_fails(self):
        rep = self.full({1: 6}, practice={1: 7, 2: 7}).run()
        self.assertEqual(rep["stopped"], run.ROUNDS)
        self.assertNotIn("passed_on", rep)
        self.assertFalse(self.morning().gate("sales")["passed"])

    def test_a_never_line_in_round_two_practice_fails(self):
        rep = self.full({1: 6}, practice={1: 8, 2: 8}, never={2: {10}}).run()  # still 21 won, one broke a line
        self.assertEqual(rep["rounds"][1]["training"]["never_broken"], 1)
        self.assertEqual(rep["stopped"], run.ROUNDS)
        self.assertNotIn("passed_on", rep)
        self.assertFalse(self.morning().gate("sales")["passed"])

    def test_an_unjudged_match_means_not_all_30_finished(self):
        a = self.full({1: 6}, practice={1: 9, 2: 10})
        real = a.play

        def play(card, match_id, **kw):
            return run.UNJUDGED if match_id.endswith("-r2-t05") else real(card, match_id, **kw)
        a.play = play
        rep = a.run()
        self.assertEqual(rep["stopped"], run.ROUNDS)  # 24 of 29 judged is past 7 of 10, still no pass

    def test_the_quick_run_never_passes_on_its_average(self):
        a = self.full({1: 6}, practice={1: 10, 2: 10})
        a.quick = True
        rep = a.run()
        self.assertNotEqual(rep["stopped"], run.PASSED)
        self.assertNotIn("passed_on", rep)

    def test_a_hand_made_average_claim_does_not_pass(self):
        item = {"agent": "sales", "kind": "arena_rounds", "at": NOW, "run": "r1", "rounds": 2, "gate_won": 6,
                "gate_played": 10, "needs": 7, "lost": [], "line": "written by hand", "quick": False,
                "stopped": "passed", "passed_on": "average",
                "average": {"won": 21, "played": 30, "practice": 20, "gate": 10, "never_broken": 0,
                            "failed_checks": 0}}
        (self.folder / "arena-sales-r1.json").write_text(json.dumps(item), encoding="utf-8")
        gate = self.morning().gate("sales")
        self.assertFalse(gate["passed"])  # no seal from an Arena run
        self.assertIn("carries no seal", gate["said"])


class BuiltAgentAverage(Base):
    """arena/practice.py Practice: the average reads the gate's round rule checks (_clean) and every match's never
    lines."""

    def practice(self, no_failed_checks=False, size=10, wins=7):
        p = practice.Practice.__new__(practice.Practice)
        p.trust, p.quick = dict(TRUST, matches=size, wins=wins, no_failed_checks=no_failed_checks), False
        p.matches, p.rounds = 10, 2
        return p

    @staticmethod
    def rounds(first, gate, second, size=10, broke=0, failed=0, practice_broke=(0, 0)):
        return [{"round": 1, "training": {"played": 10, "won": first, "never_broken": practice_broke[0]},
                 "gate": {"played": size, "won": gate, "lost": [], "never_broken": broke, "failed_checks": failed}},
                {"round": 2, "practice_only": True,
                 "training": {"played": 10, "won": second, "never_broken": practice_broke[1]},
                 "gate": {"played": 0, "won": 0, "lost": []}}]

    def test_21_of_30_clean_passes_and_20_fails(self):
        p = self.practice()
        self.assertEqual(p._average(self.rounds(8, 6, 7))["won"], 21)
        self.assertIsNone(p._average(self.rounds(7, 6, 7)))
        self.assertIsNone(p._average(self.rounds(8, 6, 7)[:1]))  # round 2 never played

    def test_a_never_line_anywhere_fails(self):
        p = self.practice()
        self.assertIsNone(p._average(self.rounds(8, 6, 7, broke=1)))
        self.assertIsNone(p._average(self.rounds(8, 6, 7, practice_broke=(1, 0))))
        self.assertIsNone(p._average(self.rounds(8, 6, 7, practice_broke=(0, 1))))

    def test_a_failed_safety_check_in_the_gate_holds_it_only_where_the_level_asks(self):
        failed = self.rounds(8, 6, 7, failed=1)
        self.assertIsNotNone(self.practice()._average(failed))
        self.assertIsNone(self.practice(no_failed_checks=True)._average(failed))

    def test_high_reads_10_plus_20_plus_10_at_16_of_20(self):
        p = self.practice(no_failed_checks=True, size=20, wins=16)
        self.assertEqual(p._average(self.rounds(9, 15, 8, size=20))["played"], 40)  # 32 of 40
        self.assertIsNone(p._average(self.rounds(9, 15, 7, size=20)))  # 31 of 40

    def test_a_short_gate_or_short_practice_fails(self):
        p = self.practice()
        short = self.rounds(8, 6, 7)
        short[0]["gate"]["played"] = 9
        self.assertIsNone(p._average(short))
        short = self.rounds(9, 6, 7)
        short[1]["training"]["played"] = 9
        self.assertIsNone(p._average(short))

    def test_quick_never(self):
        p = self.practice()
        p.quick = True
        self.assertIsNone(p._average(self.rounds(10, 6, 10)))

    def test_the_round_pass_keeps_its_rule(self):
        p = self.practice()
        one = self.rounds(0, 7, 0)[0]
        self.assertTrue(p._passed(one))
        one["gate"]["never_broken"] = 1
        self.assertFalse(p._passed(one))

    def test_the_page_checks_the_average_again(self):
        avg = {"won": 21, "played": 30, "practice": 20, "gate": 10, "never_broken": 0, "failed_checks": 0}
        self.assertEqual(mo.Morning._average_pass({"average": avg}, 10, 7), avg)
        self.assertIsNone(mo.Morning._average_pass({"average": dict(avg, won=20)}, 10, 7))
        self.assertIsNone(mo.Morning._average_pass({"average": dict(avg, played=29)}, 10, 7))
        self.assertIsNone(mo.Morning._average_pass({"average": dict(avg, practice=10, played=20)}, 10, 7))
        self.assertIsNone(mo.Morning._average_pass({"average": dict(avg, never_broken=1)}, 10, 7))
        self.assertIsNone(mo.Morning._average_pass({"average": avg}, 10, 7, clean=False))
        self.assertIsNone(mo.Morning._average_pass({"average": avg}, 20, 16))  # a gate of 20 needs 20 played


class Stop(Base):
    def test_stop_ends_the_run_as_stopped_and_it_never_passes(self):
        pressed = []
        a = self.arena({1: 10, 2: 10, 3: 10}, after=lambda n: pressed.append(n) if n == 2 else None)
        a.stop = lambda: bool(pressed)
        rep = a.run()
        self.assertEqual(rep["stopped"], run.STOPPED)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 0)  # ended before the gate began
        self.assertNotIn("passed_on", rep)
        self.assertIn("item", rep)  # saved, so the page shows what played
        self.assertEqual(rep["item"]["stopped"], run.STOPPED)
        self.assertIn("You stopped the Arena", rep["item"]["line"])
        self.assertFalse(self.morning().gate("sales")["passed"])

    def test_a_stop_mid_gate_never_passes_on_the_count_so_far(self):
        a = self.arena({1: 10})
        a.stop = lambda: a.played >= 3 + 9  # 3 practice matches, then 9 gate matches won
        with mock.patch.object(run, "parallel", return_value=3):
            rep = a.run()
        self.assertEqual(rep["stopped"], run.STOPPED)
        self.assertEqual((rep["rounds"][0]["gate"]["won"], rep["rounds"][0]["gate"]["played"]), (9, 9))
        gate = self.morning().gate("sales")
        self.assertFalse(gate["passed"])  # 9 won is past the 7 needed, still no pass
        self.assertIn("was stopped", gate["said"])

    def test_a_stop_between_rounds_ends_before_the_study(self):
        studied = []
        a = self.arena({1: 2, 2: 10}, between=lambda r: studied.append(r))
        a.stop = lambda: a.played >= 3 + 10  # pressed during round 1's gate, after its last match
        rep = a.run()
        self.assertEqual((rep["stopped"], len(rep["rounds"]), studied), (run.STOPPED, 1, []))

    def test_the_page_registers_stop_for_an_arena_run(self):
        m = self.morning()
        with self.assertRaises(mo.Refused):
            m.stop_run("sales")
        self.assertTrue(m.arena_hold("sales", self.folder))
        flag = m.arena_stop("sales")
        self.assertFalse(flag())
        self.assertEqual(m.stop_run("sales"), mo.ARENA_STOPPING)
        self.assertTrue(flag())
        m.arena_release("sales")
        self.assertIsNone(m.arena_stop("sales"))
        with self.assertRaises(mo.Refused):
            m.stop_run("sales")

    def test_the_page_shows_stop_while_an_arena_run_goes(self):
        from reflection import pages
        m = self.morning()
        m.db_path = self.folder / "ascent.db"  # the Sales agent with its database folder: Run the Arena is here
        self.assertTrue(m.arena_hold("sales", self.folder))
        self.addCleanup(m.arena_release, "sales")
        ctx = {"token": "t", "path": "/agents/sales", "q": ""}
        got = pages.run_arena(m, "sales", ctx, "/agents/sales")
        self.assertIn(f'action="{mo.STOP_PATH}"', got)
        self.assertIn(mo.ARENA_STOP_SAID, got)
        self.assertNotIn(mo.STOP_PATH, pages.run_arena(m, "sales", dict(ctx, token=None), "/agents/sales"))

    def test_play_hands_stop_to_the_arena(self):
        seen = {}

        def fake_run(arena):
            seen["stop"] = arena.stop
            return {"stopped": run.STOPPED, "calls": {}}
        args = run.parser().parse_args(["--state", str(self.folder), "--cards", str(run.DEMO_CARDS)])
        flag = (lambda: True)
        with mock.patch.object(run.Arena, "run", fake_run):
            run.play(args, agent_model=object(), customer_model=object(), stop=flag)
        self.assertIs(seen["stop"], flag)


class TheCap(Base):
    def test_the_setting_is_read_at_use_with_3000_by_default(self):
        self.assertEqual(run.daily_cap(), 3000)
        self.assertEqual(run.Calls(self.folder / run.CALLS_FILE).cap, 3000)
        self.assertIsNone(run.parser().parse_args(["--state", "x"]).cap)
        for raw, want in (("500", 500), ("0", 1), ("-3", 1), ("lots", 3000), ("", 3000), (" 2500 ", 2500)):
            with self.subTest(raw=raw), env(**{run.CAP_ENV: raw}):
                self.assertEqual(run.daily_cap(), want)
                self.assertEqual(run.Calls(self.folder / run.CALLS_FILE).cap, want)
        self.assertEqual(run.Calls(self.folder / run.CALLS_FILE, 7).cap, 7)  # a given cap still wins

    def test_has_room_reads_the_setting(self):
        (self.folder / run.CALLS_FILE).write_text(json.dumps({"day": run.today(), "calls": 1500}), encoding="utf-8")
        self.assertTrue(retry.has_room(self.folder))
        with env(**{run.CAP_ENV: "1500"}):
            self.assertFalse(retry.has_room(self.folder))
        (self.folder / run.CALLS_FILE).write_text(json.dumps({"day": run.today(), "calls": 3000}), encoding="utf-8")
        self.assertFalse(retry.has_room(self.folder))

    def test_a_practice_run_takes_the_setting_and_high_keeps_at_least_1500(self):
        root = self.folder / "owner" / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, root)

        class Seen(Exception):
            pass

        def calls(path, cap, limit=None):
            raise Seen(cap)

        def cap_for(level, setting=None):
            levels.write(root, level)
            with env(**({} if setting is None else {run.CAP_ENV: setting})), \
                    mock.patch.object(run, "Calls", calls), self.assertRaises(Seen) as got:
                practice.practise(root, agent_model=object(), customer_model=object(), judge_model=object())
            return got.exception.args[0]
        self.assertEqual(cap_for("medium"), 3000)
        self.assertEqual(cap_for("low", "800"), 800)
        self.assertEqual(cap_for("high"), 3000)
        self.assertEqual(cap_for("high", "900"), 1500)
        self.assertEqual(cap_for("high", "3000"), 3000)


if __name__ == "__main__":
    unittest.main()
