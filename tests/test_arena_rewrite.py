"""The rewrite after a failed gate inside an Arena run (arena/rounds.py Between._rewrite,
engine/study.py Study.rewrite; Mohamed 2026-11-02, "Yes now"; DECISIONS item 50): a lesson the
eval gate refused goes back to the run's Reflection with what it broke, is rewritten and takes
the gate again in the same round, at most twice a lesson, on the run's call cap; a rewrite that
still fails stays out. Fake models only, no network; the cards are made here."""
import json
import unittest
from pathlib import Path

from arena import run
from engine.lessons import TRYING, WAITING
from engine.study import FAILED_BEFORE
from tests.fake_model import say
from tests.test_arena_rounds import GOOD, IDEA_HEAD, JUDGE_HEAD, Base, Exams

BAD = "Keep each reply short and plain."
FIRST = "Ask which size they wear before anything else."
SECOND = "Greet the customer and thank them for writing."


class Ideas:
    """The night study's model: the idea part gives the next answer in answers (a list of lines a
    call, the last one again when they run out) and keeps the data it was given; the risk judge
    says low; anything else gets an empty list."""

    def __init__(self, answers, calls_file):
        self.answers, self.calls, self.idea_data = [list(a) for a in answers], 0, []
        self.calls_file, self.count_at_first = calls_file, None
        self.agent, self.agent_before = None, None  # the Arena's agent, and its calls before the first study

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        if self.count_at_first is None:
            self.count_at_first = json.loads(Path(self.calls_file).read_text(encoding="utf-8"))["calls"]
            self.agent_before = len(self.agent.systems)
        system = messages[0]["content"]
        if system.startswith(IDEA_HEAD):
            self.idea_data.append(json.loads(messages[1]["content"]))
            lines = self.answers[min(len(self.idea_data), len(self.answers)) - 1]
            return say(json.dumps([{"lesson": x, "situation": "Any chat.", "stages": ["all"]} for x in lines]))
        if system.startswith(JUDGE_HEAD):
            return say("low")
        return say("[]")


class Raises(Exams):
    """An exam that raises on the lines in broken, so the gate could not run."""

    def __init__(self, broken):
        super().__init__()
        self.broken = set(broken)

    def __call__(self, plug, kept, model):
        inner = super().__call__(plug, kept, model)

        def examine(text, tags):
            if text in self.broken:
                self.seen.append(text)
                raise RuntimeError("the exam broke")
            return inner(text, tags)
        return examine


class Rewrite(Base):
    def run_with(self, answers, *, refuse=(), cap=1000, exams=None, name="agent"):
        """One Arena run of 2 rounds where every match is lost, with the night's model swapped for
        Ideas(answers) and the exam for Exams(refuse) or exams."""
        db = self.db(name)
        self.ideas = Ideas(answers, run.state_dir(db) / run.CALLS_FILE)
        real_cli = run.main

        def main(argv, *, agent_model, customer_model, reflection):
            self.ideas.agent = agent_model
            reflection = dict(reflection, study=self.ideas, open=self.ideas)
            if exams is not None:
                reflection["examiner"] = exams
                self.exams = exams
            return real_cli(argv, agent_model=agent_model, customer_model=customer_model, reflection=reflection)

        run.main, saved = main, run.main
        try:
            code, rep = self.cli(db, [], refuse=refuse, cap=cap)
        finally:
            run.main = saved
        return db, code, rep

    def round_two(self):
        k = self.ideas.agent_before
        self.assertIsNotNone(k, "the night study never ran")
        return self.agent.systems[:k], self.agent.systems[k:]

    def ids(self, db):
        practised, _ = self.arena_lessons(db)
        return {text: les["id"] for text, les in practised.items()}

    def test_a_refused_lesson_is_rewritten_and_the_rewrite_that_passes_goes_on(self):
        db, code, rep = self.run_with([[BAD], [FIRST]], refuse=[BAD])
        got = rep["rounds"][0]["reflection"]
        ids = self.ids(db)
        self.assertEqual(got["rewrites"], [{"of": ids[BAD], "try": 1, "lesson_id": ids[FIRST], "idea": FIRST,
                                            "passed": True, "why": None}])
        self.assertEqual(self.exams.seen, [BAD, FIRST])  # the rewrite took the gate in the same round
        self.assertEqual((got["proposed"], got["passed"], got["refused"], got["handed"]), (2, 1, 1, 1))
        self.assertEqual([one.get("rewrite_of") for one in got["lessons"]], [None, ids[BAD]])
        failed = self.ideas.idea_data[1]["failed"]  # what it broke went back with the line
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["lesson"], BAD)
        self.assertEqual(failed[0]["fails"][0]["check"], "price")
        self.assertIn("situation 1", failed[0]["fails"][0]["case"])
        self.assertEqual((failed[0]["fixed"], failed[0]["broke"]), (0, 0))  # the counts went too
        _, after = self.round_two()
        self.assertTrue(after and all(FIRST in s for s in after))
        self.assertFalse(any(BAD in s for s in self.agent.systems))
        saved, _ = self.lessons(db)  # the live database gains only the rewrite that passed
        self.assertEqual(list(saved), [FIRST])
        self.assertEqual(saved[FIRST]["state"], TRYING)
        self.assertIn(f"a rewrite of lesson {ids[BAD]}, which failed the eval gate", saved[FIRST]["source"])
        self.assertIn("rewrites after a failed gate: 1 written, 1 passed", run.text(rep))

    def test_a_rewrite_that_fails_gets_a_second_try_with_both_failed_lines(self):
        db, code, rep = self.run_with([[BAD], [FIRST], [SECOND]], refuse=[BAD, FIRST])
        got = rep["rounds"][0]["reflection"]
        ids = self.ids(db)
        self.assertEqual([(r["try"], r["lesson_id"], r["passed"]) for r in got["rewrites"]],
                         [(1, ids[FIRST], False), (2, ids[SECOND], True)])
        self.assertEqual({r["of"] for r in got["rewrites"]}, {ids[BAD]})
        self.assertEqual(self.exams.seen, [BAD, FIRST, SECOND])
        second = self.ideas.idea_data[2]["failed"]
        self.assertEqual([f["lesson"] for f in second], [FIRST, BAD])  # the newest try first
        self.assertNotIn(FIRST, self.ideas.idea_data[2]["known"])
        saved, _ = self.lessons(db)
        self.assertEqual(list(saved), [SECOND])
        _, after = self.round_two()
        self.assertTrue(after and all(SECOND in s and FIRST not in s for s in after))

    def test_two_failed_rewrites_stay_out_and_a_third_never_runs(self):
        third = "End each reply with one short question."
        db, code, rep = self.run_with([[BAD], [FIRST], [SECOND], [third]], refuse=[BAD, FIRST, SECOND])
        got = rep["rounds"][0]["reflection"]
        self.assertEqual([r["passed"] for r in got["rewrites"]], [False, False])
        self.assertEqual(len(self.ideas.idea_data), 3)  # the first study and two rewrites, no third
        self.assertEqual(self.exams.seen, [BAD, FIRST, SECOND])
        self.assertEqual((got["proposed"], got["passed"], got["refused"], got["handed"]), (3, 0, 3, 0))
        practised, _ = self.arena_lessons(db)
        self.assertNotIn(third, practised)
        self.assertEqual({practised[x]["state"] for x in (BAD, FIRST, SECOND)}, {WAITING})
        saved, _ = self.lessons(db)
        self.assertEqual(saved, {})
        _, after = self.round_two()
        self.assertFalse(any(x in s for s in after for x in (BAD, FIRST, SECOND)))
        self.assertIn("rewrites after a failed gate: 2 written, 0 passed", run.text(rep))

    def test_the_failed_line_again_is_never_written_and_still_counts_as_a_try(self):
        db, code, rep = self.run_with([[BAD]], refuse=[BAD])
        got = rep["rounds"][0]["reflection"]
        self.assertEqual([(r["try"], r["lesson_id"], r["why"]) for r in got["rewrites"]],
                         [(1, None, FAILED_BEFORE), (2, None, FAILED_BEFORE)])
        self.assertEqual(self.exams.seen, [BAD])
        self.assertEqual(len(self.ideas.idea_data), 3)
        self.assertEqual(len(self.ids(db)), 1)

    def test_a_passed_lesson_and_one_whose_exam_could_not_run_are_not_rewritten(self):
        db, code, rep = self.run_with([[GOOD, BAD], [FIRST]], exams=Raises([BAD]))
        got = rep["rounds"][0]["reflection"]
        self.assertEqual((got["passed"], got["refused"]), (1, 1))
        self.assertNotIn("rewrites", got)
        self.assertEqual(len(self.ideas.idea_data), 1)

    def test_the_call_cap_stops_the_rewrites(self):
        self.run_with([[BAD], [FIRST]], refuse=[BAD], name="measure")
        at_first = self.ideas.count_at_first  # the Arena's count with the first idea call in it
        # room for the first study's idea call, its risk judge and its exam, and nothing more
        db, code, rep = self.run_with([[BAD], [FIRST]], refuse=[BAD], cap=at_first + 2)
        got = rep["rounds"][0]["reflection"]
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual(len(rep["rounds"]), 1)
        self.assertEqual(len(self.ideas.idea_data), 1)  # the rewrite's idea call was refused at the cap
        self.assertEqual([(r["try"], r["lesson_id"]) for r in got["rewrites"]], [(1, None)])  # no second try
        self.assertIn("CapReached", got["rewrites"][0]["why"])
        self.assertEqual(self.exams.seen, [BAD])
        self.assertEqual(got["stopped"], "cap")
        self.assertEqual(json.loads((run.state_dir(db) / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"],
                         at_first + 2)


if __name__ == "__main__":
    unittest.main()
