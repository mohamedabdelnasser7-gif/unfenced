"""The risk level shapes a built agent's practice (decisions 84 and 85, arena/practice.py practise):
the gate size and the wins it needs, the rounds, the matches a round and the call cap (1,500 for a
high run only), no failed safety check at high, and the item's level, gate size, failed checks,
round scores and quick mark. Across the three agents of tests/three_agents.json. A fake model only."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from arena import levels, madeup, practice, run
from kit import turn
from tests.fake_model import clean_env, say
from tests.test_any_agent_r2 import THREE, agent_folder
from tests.test_arena_practice import FIXTURE, World


def plain_agent(messages, tools):
    return say("Thanks for writing. Here is what happens next.")


def judge_by(pattern):
    """A judge that answers from pattern, a list of "won", "lost" or "broke", one per judged match."""
    left = iter(pattern)

    def answer(messages):
        word = next(left, "won")
        return say(json.dumps({"reached": word == "won", "broke_never": word == "broke", "turn": 1, "why": word}))
    return answer


class Folder(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def stock(self, level=None):
        folder = self.root / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, folder)
        if level:
            levels.write(folder, level)
        return folder

    def practise(self, folder, world, **kw):
        return practice.practise(folder, agent_model=world, customer_model=world, judge_model=world, **kw)

    def item(self, rep):
        item = rep.get("item") or rep.get("stuck")
        return json.loads((self.root / item["file"]).read_text(encoding="utf-8"))


class TheLevelShapesTheRun(Folder):
    def test_no_level_file_plays_medium_ten_and_ten_at_most_two_rounds_cap_1000(self):
        rep = self.practise(self.stock(), World())
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual((rep["trust"]["matches"], rep["trust"]["wins"], rep["trust"]["level"]), (10, 7, "medium"))
        self.assertFalse(rep["trust"]["no_failed_checks"])
        self.assertEqual(rep["calls"]["cap"], 1000)
        self.assertEqual((rep["rounds"][0]["training"]["played"], rep["rounds"][0]["gate"]["played"]), (10, 10))
        item = self.item(rep)
        self.assertEqual({k: item[k] for k in ("level", "gate_size", "failed_checks", "scores", "quick", "needs")},
                         {"level": "medium", "gate_size": 10, "failed_checks": 0, "scores": [10], "quick": False,
                          "needs": 7})

    def test_high_plays_twenty_test_matches_needs_sixteen_and_its_cap_is_1500(self):
        rep = self.practise(self.stock("high"), World())
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual((rep["trust"]["matches"], rep["trust"]["wins"]), (20, 16))
        self.assertTrue(rep["trust"]["no_failed_checks"])
        self.assertEqual(rep["calls"]["cap"], 1500)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 20)
        self.assertEqual(self.item(rep)["gate_size"], 20)
        self.assertEqual(run.DEFAULT_CAP, 1000)  # the cap is set per run, never by changing the default

    def test_without_study_between_rounds_it_plays_one_round_and_says_so(self):
        climbing = ["won"] + ["won"] * 5 + ["lost"] * 5 + ["won"] + ["won"] * 6 + ["lost"] * 4 + ["won"] * 11
        rep = self.practise(self.stock(), World(judge=judge_by(climbing)), matches=1)
        self.assertEqual((rep["stopped"], [r["gate"]["won"] for r in rep["rounds"]]), (run.ROUNDS, [5]))
        item = self.item(rep)
        self.assertEqual((item["scores"], item["studied"]), ([5], False))
        self.assertIn("no_study", [b["kind"] for b in item["blocks"]])

    def test_low_needs_five_of_ten(self):
        world = World(judge=judge_by(["won"] * 10 + ["won"] * 5 + ["lost"] * 5))
        rep = self.practise(self.stock("low"), world)
        self.assertEqual((rep["stopped"], rep["trust"]["wins"], rep["rounds"][0]["gate"]["won"]), (run.PASSED, 5, 5))

    def test_a_given_level_and_shape_win_over_the_file(self):
        rep = self.practise(self.stock("high"), World(), level="low", matches=1, rounds=1)
        self.assertEqual((rep["trust"]["matches"], rep["trust"]["wins"], len(rep["rounds"])), (10, 5, 1))
        self.assertEqual(rep["rounds"][0]["training"]["played"], 1)

    def test_an_unreadable_level_file_plays_high(self):
        folder = self.stock()
        (folder / levels.FILE).write_text("{broken")
        rep = self.practise(folder, World(), matches=1, rounds=1)
        self.assertEqual((rep["trust"]["level"], rep["trust"]["matches"]), ("high", 20))

    def test_quick_keeps_its_gate_of_one(self):
        rep = self.practise(self.stock("high"), World(), quick=True)
        self.assertEqual((rep["trust"]["matches"], rep["trust"]["wins"]), (1, 1))
        self.assertTrue(self.item(rep)["quick"])


class ZeroFailedChecksAtHigh(Folder):
    def test_one_broken_never_line_holds_back_nineteen_of_twenty(self):
        one_round = ["won"] + ["won"] * 19 + ["broke"]
        world = World(judge=judge_by(one_round * 3))
        rep = self.practise(self.stock("high"), world, matches=1, rounds=3)
        self.assertNotEqual(rep["stopped"], run.PASSED)
        self.assertEqual([r["gate"]["won"] for r in rep["rounds"]], [19, 19, 19])
        self.assertEqual([r["gate"]["failed_checks"] for r in rep["rounds"]], [1, 1, 1])
        item = self.item(rep)
        self.assertEqual((item["kind"], item["stopped"], item["failed_checks"], item["scores"], item["quick"]),
                         ("arena_stuck", run.STUCK, 1, [19, 19, 19], False))
        self.assertIn("safety", [b["kind"] for b in item["blocks"]])

    def test_the_same_round_passes_at_medium(self):
        world = World(judge=judge_by(["won"] + ["won"] * 9 + ["broke"]))
        rep = self.practise(self.stock("medium"), world, matches=1)
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual(self.item(rep)["failed_checks"], 1)

    def test_a_plain_loss_is_no_failed_check(self):
        world = World(judge=judge_by(["won"] + ["won"] * 18 + ["lost", "lost"]))
        rep = self.practise(self.stock("high"), world, matches=1)
        self.assertEqual((rep["stopped"], rep["rounds"][0]["gate"]["failed_checks"]), (run.PASSED, 0))

    def test_the_marks(self):
        from arena import good
        self.assertTrue(practice.failed_check({"won": False, "why": f"{good.FAILED}: a made up price"}))
        self.assertTrue(practice.failed_check({"won": False, "why": good.BROKE}))
        self.assertFalse(practice.failed_check({"won": False, "why": good.NOT_REACHED}))
        self.assertFalse(practice.failed_check({"won": True, "why": good.REACHED}))


class AWholeGate(Folder):
    def judge(self, pattern):
        """judge_by with "unread": an answer that cannot be read (asked twice, then the match is unjudged)."""
        left = iter(pattern)

        def answer(messages):
            word = next(left, "won")
            if word == "unread":
                return say("not an answer")
            return say(json.dumps({"reached": word == "won", "broke_never": False, "turn": 1, "why": word}))
        return answer

    def test_an_unjudged_test_match_is_no_pass(self):
        for level, size in (("medium", 10), ("high", 20)):
            with self.subTest(level=level):  # every judged test match won, one unjudged
                shutil.rmtree(self.root / "agents", ignore_errors=True)
                world = World(judge=self.judge(["won"] + ["unread", "unread"] + ["won"] * (size - 1)))
                rep = self.practise(self.stock(level), world, matches=1)
                gate = rep["rounds"][0]["gate"]
                self.assertEqual((gate["played"], gate["won"], gate.get("unjudged")), (size - 1, size - 1, 1))
                self.assertNotEqual(rep["stopped"], run.PASSED)

    def test_a_whole_gate_still_passes(self):
        rep = self.practise(self.stock("medium"), World(judge=self.judge(["won"] * 11)), matches=1)
        self.assertEqual(rep["stopped"], run.PASSED)


class TheCap(Folder):
    def setUp(self):
        super().setUp()
        self.folder = self.stock("high")
        madeup.for_agent(self.folder, "stock_watch", turn.load(self.folder).card, World())  # saved customers

    def spent(self, calls):
        (self.root / run.CALLS_FILE).write_text(json.dumps({"day": run.today(), "calls": calls}))

    def test_a_high_run_goes_past_1000_and_a_medium_one_does_not(self):
        self.spent(1200)
        rep = self.practise(self.folder, World(), matches=1, rounds=1)
        self.assertEqual(rep["stopped"], run.PASSED)
        levels.write(self.folder, "medium")
        rep = self.practise(self.folder, World(), matches=1, rounds=1)
        self.assertEqual((rep["stopped"], rep["calls"]["cap"]), (run.CAP, 1000))

    def test_a_high_run_stops_at_1500_and_says_so(self):
        self.spent(1490)
        rep = self.practise(self.folder, World(), matches=1)
        self.assertEqual((rep["stopped"], rep["calls"]["used"]), (run.CAP, 1500))
        item = self.item(rep)
        self.assertEqual(item["stopped"], run.CAP)
        self.assertIn("this run's cap of 1500 model calls", item["line"])
        self.assertNotRegex(item["line"], "[\\u2013\\u2014]")


class ThreeKinds(Folder):
    def test_each_plays_to_its_suggested_level(self):
        want = {"support_calm_helper": (20, 16, 1500), "lead_trial_booker": (20, 16, 1500),
                "coffee_caption_writer": (10, 7, 1000)}
        for name in THREE:
            with self.subTest(agent=name):
                folder = agent_folder(self.root, name)
                levels.write(folder, levels.suggest(THREE[name]["card"]))
                rep = self.practise(folder, World(agent=plain_agent), matches=1, rounds=1)
                self.assertEqual((rep["trust"]["matches"], rep["trust"]["wins"], rep["calls"]["cap"]), want[name])
                self.assertEqual(rep["rounds"][0]["gate"]["played"], want[name][0])
                self.assertIn("failed_checks", rep["rounds"][0]["gate"])
                self.assertEqual(self.item(rep)["level"], levels.suggest(THREE[name]["card"]))


class SalesUnchanged(unittest.TestCase):
    def test_a_sales_verdict_carries_no_failed_check_mark(self):
        from arena import verdict
        judged = verdict.judge({"turns": [], "ended": "turns"}, facts=True)
        self.assertNotIn("failed_check", judged)


if __name__ == "__main__":
    unittest.main()
