"""Review simplify round 3, the sweep: tests for Try again paths the mutation sweep showed had none
(arena/retry.py retry, reflection/morning.py Morning.try_again and read_arena, reflection/pages.py
build and try_again). A try stops at the day's call cap or at a model that does not answer, and the
cards after it are not played; a double press before the thread runs is refused; a new try clears
the last one's failure note; a thread that cannot start leaves no try running; fact checks off on
the run are off in the try; and the screen says when a try stopped or failed, with a card it never
played shown as it was. Fake models only, no network; the cards are made here."""
import json
import unittest
from unittest import mock

from arena import retry, rounds, run
from kit.model import ModelError
from reflection import morning as mo
from reflection import pages
from reflection.lessons import Lessons as SalesLessons
from tests import test_try_again as tta
from tests.test_arena_run import Customer

CARDS = ["persona-02", "persona-03"]


class Silent:
    """An agent model that never answers."""

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        raise ModelError("the route is busy")


class Stops(tta.Base):
    """arena/retry.py: a stop ends the try at that card; the cards after it are not played."""

    def retry(self, agent_model, cap=run.DEFAULT_CAP):
        rep = self.stuck()
        return retry.retry(agent="sales", run=rep["run"], cards=CARDS, state=self.dir, reports=self.dir,
                           pool=rounds.Pool(SalesLessons(self.db)), agent_model=agent_model,
                           customer_model=Customer(("price", "fit")), cap=cap, now=lambda: tta.NOW + 60)

    def calls(self):
        return json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]

    def test_the_day_cap_stops_the_try_and_the_rest_are_not_played(self):
        rep = self.stuck()
        cap = self.calls() + 1  # the agent's first line is the last call the day has room for
        item = retry.retry(agent="sales", run=rep["run"], cards=CARDS, state=self.dir, reports=self.dir,
                           pool=rounds.Pool(SalesLessons(self.db)), agent_model=tta.Agent(),
                           customer_model=Customer(("price", "fit")), cap=cap, now=lambda: tta.NOW + 60)
        self.assertEqual(item["stopped"], run.CAP)
        self.assertEqual([(r["card"], r["result"], r["why"]) for r in item["results"]],
                         [("persona-02", retry.NOT_PLAYED, "the try stopped here"),
                          ("persona-03", retry.NOT_PLAYED, "the try stopped before it")])
        self.assertEqual(self.calls(), cap)
        self.assertNotIn("error", item)
        saved = json.loads((self.dir / item["file"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["stopped"], run.CAP)

    def test_a_model_that_does_not_answer_stops_the_try_with_its_error(self):
        item = self.retry(Silent())
        self.assertEqual(item["stopped"], run.MODEL_ERROR)
        self.assertTrue(item["error"])
        self.assertEqual([(r["card"], r["result"], r["why"]) for r in item["results"]],
                         [("persona-02", retry.NOT_PLAYED, "the try stopped here"),
                          ("persona-03", retry.NOT_PLAYED, "the try stopped before it")])
        self.assertTrue(item["line"].startswith("Try again played 0 of the 2 lost matches"))


class Presses(tta.Base):
    """reflection/morning.py Morning.try_again: the running mark, the failure note and the thread start."""

    def test_a_second_press_before_the_thread_runs_is_refused(self):
        self.stuck()
        held = []
        self.m.retry_start = lambda work, name: held.append(work)  # the thread has not run yet
        self.assertEqual(self.m.try_again("sales"), retry.STARTED)
        self.assertTrue(self.m.trying("sales"))
        with self.assertRaises(mo.Refused) as e:
            self.m.try_again("sales")
        self.assertIn("running for this agent already", str(e.exception))
        self.assertEqual(len(held), 1)
        held[0]()
        self.assertFalse(self.m.trying("sales"))
        self.assertEqual(len(list(self.dir.glob("arena-sales-retry-*.json"))), 1)

    def test_a_new_try_clears_the_last_ones_failure_note(self):
        self.stuck()
        models = self.m.retry_models

        def broken():
            raise RuntimeError("the route is busy")
        self.m.retry_models = broken
        self.m.try_again("sales")
        self.assertIn("the route is busy", self.m.try_note("sales"))
        self.m.retry_models = models
        self.m.try_again("sales")
        self.assertIsNone(self.m.try_note("sales"))

    def test_a_thread_that_cannot_start_leaves_no_try_running(self):
        self.stuck()
        start = self.m.retry_start

        def cannot(work, name):
            raise RuntimeError("can't start new thread")
        self.m.retry_start = cannot
        with self.assertRaises(RuntimeError):
            self.m.try_again("sales")
        self.assertFalse(self.m.trying("sales"))
        self.m.retry_start = start
        self.assertEqual(self.m.try_again("sales"), retry.STARTED)  # not refused as running


class FactChecks(tta.Base):
    """A run with fact checks off: read_arena says so and the try is judged the same way."""

    def facts_off(self):
        path = self.dir / self.stuck()["stuck"]["file"]
        item = json.loads(path.read_text(encoding="utf-8"))
        item["fact_checks"] = False
        path.write_text(json.dumps(item), encoding="utf-8")

    def test_read_arena_carries_fact_checks_off(self):
        self.stuck()
        self.assertIs(self.item()["facts"], True)
        self.facts_off()
        self.assertIs(self.item()["facts"], False)

    def test_fact_checks_off_carry_into_the_try(self):
        self.facts_off()
        real, got = retry.retry, []

        def spy(**kw):
            got.append(kw["facts"])
            return real(**kw)
        with mock.patch.object(retry, "retry", spy):
            self.m.try_again("sales")
        self.assertEqual(got, [False])


class Screen(tta.Base):
    """reflection/pages.py: the stopped line, the failure note, and a card the try never played."""

    def page(self):
        return pages.Pages(self.m).get("/new/build", {"agent": ["sales"]}, "t")

    def stopped_try(self):
        rep = self.stuck()
        item = {"agent": "sales", "kind": retry.KIND, "at": tta.NOW + 60, "run": "retry-x", "retried": rep["run"],
                "stopped": run.CAP, "line": "made up for the test",
                "results": [{"card": "persona-02", "result": retry.NOT_PLAYED, "why": "the try stopped here"},
                            {"card": "persona-03", "result": retry.STILL_LOST, "why": "the customer left again",
                             "quote": {"turn": 1, "who": "agent", "text": "Hi there"}}]}
        (self.dir / "arena-sales-retry-x.json").write_text(json.dumps(item), encoding="utf-8")

    def test_a_card_the_try_never_played_shows_as_it_was(self):
        self.stopped_try()
        tiles = self.page().split('class="tiles"')[1].split("</section>")[0]
        self.assertNotIn("the try stopped here", tiles)
        self.assertIn('<span class="res">Lost</span>', tiles)
        self.assertIn('<span class="res">Still lost</span>', tiles)
        self.assertEqual(tiles.count("<article"), 2)

    def test_a_try_that_stopped_says_so(self):
        self.stopped_try()
        self.assertIn("The last try stopped before it played every match", self.page())

    def test_a_try_that_failed_shows_its_note(self):
        self.stuck()

        def broken():
            raise RuntimeError("the route is busy")
        self.m.retry_models = broken
        self.m.try_again("sales")
        page = self.page()
        self.assertIn("The last try could not run (the route is busy).", page)
        self.assertNotIn("The last try stopped before", page)


if __name__ == "__main__":
    unittest.main()
