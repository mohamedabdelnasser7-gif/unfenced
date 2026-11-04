"""The Arena gate votes a past win lost on rerun (Arena run 20261104T143545, cause 6): played again with
the lesson to a majority of VOTES, then without it; held only when it lost with and won without."""
import json
import tempfile
import unittest
from pathlib import Path

from arena import gate, run
from engine import exam as engine_exam
from engine.exam import Pair
from tests.fake_model import Buyer, ByLesson, Seller, clean_env
from tests.test_arena_gate import LESSON, exam, past

WRONG = "The Mercurial Vapor 17 Elite is 11,000 EGP."  # a price the store never set: the match is lost


class Plays:
    """A Seller whose matches go by outcomes, one per match (True won, False lost), in order."""

    def __init__(self, *outcomes):
        self.outcomes, self.plays, self.calls = list(outcomes), 0, []
        self.seller = None

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if not any(m["role"] == "assistant" for m in messages):  # the first call of a match
            won = self.outcomes.pop(0)
            self.plays += 1
            self.seller = Seller() if won else Seller(WRONG)
        out = self.seller.chat(messages, tools, effort, max_tokens, whole)
        self.calls.append(self.seller.calls[-1])
        return out


class Vote(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def run_gate(self, with_line, without, cap=300):
        agent, customer = ByLesson(LESSON, with_line, without), Buyer()
        calls = run.Calls(self.dir / "calls.json", cap, day="2026-10-30")
        g = gate.Gate(exam(True), wins=[past()], agent_model=agent, customer_model=customer, calls=calls)
        return g(LESSON, ("all",)), agent, customer

    def saved(self):
        return json.loads((self.dir / "calls.json").read_text(encoding="utf-8"))["calls"]

    def test_a_loss_the_lesson_wins_back_by_majority_is_noise_and_passes(self):
        with_line, without = Plays(False, True, True), Plays()
        r, agent, customer = self.run_gate(with_line, without)
        self.assertTrue(r.passed, r.rows)
        row = r.rows[-1]
        self.assertEqual((row.part, row.passed, row.check), (gate.PART, True, ""))
        self.assertEqual(row.why, "lost once, then won 2 of 3 with the lesson: noise")
        self.assertEqual((with_line.plays, without.plays), (3, 0))
        self.assertEqual(r.pairs[-1], Pair("rerun m1", True, True))

    def test_a_win_lost_both_ways_holds_nothing(self):
        with_line, without = Plays(False, False), Plays(False, False)
        r, _, _ = self.run_gate(with_line, without)
        self.assertTrue(r.passed, r.rows)
        self.assertEqual(r.rows[-1].why, "lost once, then won 0 of 2 with the lesson, 0 of 2 without it: "
                                         "it is lost without the lesson too")
        self.assertEqual((with_line.plays, without.plays), (2, 2))
        self.assertEqual(r.pairs[-1], Pair("rerun m1", False, False))  # both wrong: no broke

    def test_a_loss_the_version_without_the_lesson_wins_holds_it_naming_both_votes(self):
        with_line, without = Plays(False, True, False), Plays(True, False, True)
        r, _, _ = self.run_gate(with_line, without)
        self.assertFalse(r.passed)
        self.assertEqual((r.first.part, r.first.check), (gate.PART, gate.CHECK))
        self.assertIn("was won, now lost", r.first.why)
        self.assertIn("11,000 EGP", r.first.why)
        self.assertTrue(r.first.why.endswith("; won 1 of 3 with the lesson, 2 of 3 without it"), r.first.why)
        self.assertEqual(r.line(), "failed the Arena rerun of past wins, at rerun 1")
        self.assertEqual(r.pairs[-1], Pair("rerun m1", True, False))
        self.assertEqual(engine_exam.effect(r.pairs)["broke_cases"], ["rerun m1"])

    def test_the_vote_plays_without_the_lesson_handed(self):
        with_line, without = Plays(False, False), Plays(True, True)
        r, agent, _ = self.run_gate(with_line, without)
        self.assertFalse(r.passed)
        plain = [c for c, h in zip(agent.calls, agent.handed) if not h]
        self.assertTrue(plain)
        self.assertTrue(all(LESSON not in c["messages"][0]["content"] for c in plain))
        self.assertEqual((with_line.plays, without.plays), (2, 2))

    def test_every_vote_play_counts_on_the_cap(self):
        with_line, without = Plays(False, True, False), Plays(True, False, True)
        r, agent, customer = self.run_gate(with_line, without)
        self.assertEqual((with_line.plays, without.plays), (3, 3))
        self.assertEqual(r.calls, 1 + len(agent.calls) + len(customer.calls))  # the exam's, then every play's
        self.assertEqual(self.saved(), len(agent.calls) + len(customer.calls))

    def test_a_cap_reached_in_the_vote_holds_the_lesson(self):
        with_line, without = Plays(False, False), Plays(False, False)
        _, agent, customer = self.run_gate(with_line, without)
        self.assertEqual((with_line.plays, without.plays), (2, 2))
        one, rest = divmod(len(agent.calls) + len(customer.calls), 4)  # four lost plays of the same length
        self.assertEqual(rest, 0)
        for with_line, without, cap, plays in (
                (Plays(False, True, True), Plays(), one + 1, (2, 0)),  # stops in the lesson's second play
                (Plays(False, False), Plays(True, True), 2 * one + 1, (2, 1))):  # and in the first without it
            with self.subTest(cap=cap):
                (self.dir / "calls.json").unlink()
                r, _, _ = self.run_gate(with_line, without, cap=cap)
                self.assertFalse(r.passed)
                self.assertEqual((r.first.part, r.first.check), (gate.PART, engine_exam.NOT_RUN))
                self.assertEqual(r.first.why, "the Arena call cap is reached")
                self.assertEqual(self.saved(), cap)
                self.assertEqual((with_line.plays, without.plays), plays)


if __name__ == "__main__":
    unittest.main()
