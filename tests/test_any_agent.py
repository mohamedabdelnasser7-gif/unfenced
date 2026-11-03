"""Any agent, not only the stock one (2026-11-03): the judge's unreadable answer, sample data made at
Build and added by the user, the Run the Arena button and the card's wording. Fake models only, no
network, no real data."""
import json
import unittest

from arena import practice, run, tag
from tests.fake_model import say
from tests.test_arena_practice import Base, World

GOOD = json.dumps({"reached": True, "broke_never": False, "turn": 1, "why": "a clear answer"})


def judge_script(*answers):
    """A judge that gives each answer in turn, then GOOD."""
    left = list(answers)
    return lambda messages: say(left.pop(0) if left else GOOD)


class UnreadableJudge(Base):
    def test_the_rule_is_the_taggers_three_in_a_row(self):
        self.assertEqual(practice.UNREAD_IN_A_ROW, tag.MAX_FAILS)

    def test_one_unreadable_answer_is_asked_again_and_the_match_is_judged(self):
        world = World(judge=judge_script("I think it went well."))
        code, rep = self.main("--matches", "2", "--json", world=world)
        self.assertEqual((code, rep["stopped"]), (0, run.PASSED), self.err)
        self.assertNotIn("unjudged", rep["rounds"][0]["training"])
        self.assertEqual(rep["rounds"][0]["training"]["played"], 2)

    def test_a_match_read_twice_and_still_unreadable_is_unjudged_and_the_run_goes_on(self):
        world = World(judge=judge_script("no json", "still no json"))
        code, rep = self.main("--matches", "2", "--json", world=world)
        self.assertNotEqual(rep["stopped"], run.MODEL_ERROR)
        train = rep["rounds"][0]["training"]
        self.assertEqual((train["unjudged"], train["played"]), (1, 1))
        self.assertEqual(len(self.matches()), 1 + rep["rounds"][0]["gate"]["played"])
        self.assertTrue(all("won" in m for m in self.matches()))

    def test_three_unjudged_matches_in_a_row_stop_the_run(self):
        world = World(judge=lambda messages: say("never json"))
        code, rep = self.main("--matches", "4", "--json", world=world)
        self.assertEqual((code, rep["stopped"]), (1, run.MODEL_ERROR))
        self.assertIn("3 matches in a row", rep["error"])
        self.assertEqual(world.calls["judge"], 6)  # each match asked twice
        self.assertEqual(self.matches(), [])


if __name__ == "__main__":
    unittest.main()
