"""A clear mistake teaches from one case (DECISIONS item 111; engine/study.py step 4). A lost Arena or
practice case whose verdict is a broken never line or a failed fact check makes a lesson on its own,
with no floor of cases or sources and no gap test; the lesson still goes through the risk check, the
exam and the gate. A plain loss alone makes none, and a softer pattern keeps the 75% chance with 5
cases from 3 sources on each side. The night and Run reflection (reflection/night.py) and the Arena
between rounds (arena/rounds.py) take the same path. Fake model parts only, no network."""
import json
import unittest
from unittest import mock

from arena import good, learn, learn_built, verdict
from engine import risk, study
from engine.lessons import Lessons
from engine.log import Log
from engine.study import Study
from kit.db import Db
from reflection import PLUG as SALES
from reflection import night
from reflection.lessons import Lessons as SalesLessons
from tests import plugs
from tests import study_fakes as fk
from tests import test_arena_rounds as ar
from tests.fake_model import say

AT = fk.UNTIL - fk.DAY
NEVER_LINE = "Never water a bed again in the same round."
FACT_LINE = "Quote only what the store tool gives for each item."
MISTAKE = {"pattern": "The agent did the one thing it must never do.", "helps": False,
           "lesson": NEVER_LINE, "situation": "Any bed.", "stages": ["all"]}


def always_low(text, high_about, low_about):
    return risk.LOW


def match(customer, reply, failed=None):
    turn = {"n": 1, "customer": customer, "replies": [reply], "outcome": "replied"}
    if failed:
        turn["failed"] = failed
    return {"turns": [turn], "card": "persona-01", "worry": "price"}


class Constants(unittest.TestCase):
    def test_the_verdict_starts_are_the_arenas_own(self):
        self.assertEqual(study.BROKE_NEVER, good.BROKE)
        self.assertEqual(study.FAILED_SEND, good.FAILED)
        self.assertEqual(study.FAILED_FACT, verdict.FAILED)

    def test_softer_patterns_keep_the_old_bar(self):
        self.assertEqual((study.CHANCE, study.MIN_CASES, study.MIN_SOURCES), (0.75, 5, 3))

    def test_a_study_asks_about_three_clear_mistakes_at_most(self):
        self.assertEqual(study.MISTAKES_A_RUN, 3)


class Built(unittest.TestCase):
    """A built agent (the made-up waterer) with its practice losses written by arena/learn_built.py."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)

    def lose(self, why, mid="m1", failed=None, customer="Water bed one."):
        learn_built.to_case(self.db, self.plug, match(customer, "Watered it twice.", failed),
                            {"won": False, "why": why, "quote": {"turn": 1, "who": "agent", "text": ""}}, mid, now=AT)
        return learn_built.case_id(self.plug.agent, mid)

    def run_night(self, *candidates):
        self.proposer = fk.Proposer(*candidates)
        return Study(self.db, self.plug, proposer=self.proposer, tagger=fk.Tagger(),
                     lessons=self.lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW)

    def test_one_never_line_loss_alone_makes_a_lesson(self):
        case = self.lose(f"{good.BROKE}: it watered the bed twice")
        rep = self.run_night(MISTAKE)
        self.assertEqual(rep["decided"], {"good": 0, "bad": 1})  # one case, nothing to compare
        self.assertEqual(rep["candidates"], [])
        (got,) = rep["mistakes"]
        self.assertEqual((got["case_id"], got["kind"], got["verdict"]), (case, "a broken never line", study.LESSON))
        (les,) = self.lessons.mine()
        self.assertEqual(les["text"], NEVER_LINE)
        self.assertIn("from one clear mistake: a broken never line", les["source"])
        self.assertEqual(got["lesson_id"], les["id"])
        (call,) = self.proposer.calls
        self.assertEqual([v["mistake"] for v in call["sample"]], ["a broken never line"])  # that one case only

    def test_one_failed_send_check_alone_makes_a_lesson(self):
        failed = [{"check": "amount", "why": "an amount no tool gave"}]
        self.lose(f"{good.FAILED}: an amount no tool gave", failed=failed)
        rep = self.run_night(MISTAKE)
        self.assertEqual([(m["kind"], m["verdict"]) for m in rep["mistakes"]], [("a failed fact check", study.LESSON)])
        self.assertIn("from one clear mistake: a failed fact check", self.lessons.mine()[0]["source"])

    def test_one_plain_loss_alone_makes_none(self):
        self.lose(f"{good.NOT_REACHED}: it only asked questions")
        rep = self.run_night(MISTAKE)
        self.assertEqual(rep["mistakes"], [])
        self.assertEqual(self.proposer.calls, [])  # no good case either, so no pattern search
        self.assertEqual(self.lessons.mine(), [])

    def test_the_same_verdict_twice_asks_once(self):
        self.lose(f"{good.BROKE}: it watered the bed twice", mid="m1")
        self.lose(f"{good.BROKE}: it watered the bed twice", mid="m2")
        rep = self.run_night(MISTAKE)
        self.assertEqual([m["verdict"] for m in rep["mistakes"]], [study.LESSON, study.SAME_MISTAKE])
        self.assertEqual(len(self.proposer.calls), 1)

    def test_a_lesson_copying_the_case_goes_high_and_waits(self):
        said = "Please water the left bed by the old fence today."
        self.lose(f"{good.BROKE}: it watered the bed twice", customer=said)
        copy = dict(MISTAKE, lesson="Water the left bed by the old fence before noon.")
        rep = self.run_night(copy)
        self.assertEqual([m["verdict"] for m in rep["mistakes"]], [study.LESSON])
        (card,) = rep["cards"]
        self.assertEqual((card["risk"], card["state"]), ("high", "waiting"))
        self.assertIn("core: copied from source", card["risk_why"])

    def test_a_high_risk_mistake_lesson_waits_for_a_yes(self):
        self.lessons = Lessons(self.db, self.plug, judge=lambda text, high_about, low_about: risk.HIGH)
        self.lose(f"{good.BROKE}: it watered the bed twice")
        rep = self.run_night(MISTAKE)
        self.assertEqual([m["verdict"] for m in rep["mistakes"]], [study.LESSON])
        (card,) = rep["cards"]
        self.assertEqual((card["risk"], card["state"]), ("high", "waiting"))
        self.assertNotIn("core: copied from source", card["risk_why"])
        (les,) = self.lessons.mine()
        self.assertEqual(les["state"], "waiting")

    def test_many_send_check_losses_make_one_lesson(self):
        for n in range(4):
            why = f"an amount no tool gave: {n + 1},000 EGP"
            self.lose(f"{good.FAILED}: {why}", mid=f"m{n}", failed=[{"check": "send_check", "why": why}])
        rep = self.run_night(MISTAKE)
        self.assertEqual([m["verdict"] for m in rep["mistakes"]], [study.LESSON] + [study.SAME_MISTAKE] * 3)
        self.assertEqual(len(self.proposer.calls), 1)

    def test_two_different_send_check_problems_are_asked_twice(self):
        for n, why in enumerate(("an amount no tool gave: 1,000 EGP", "a dash in the reply")):
            self.lose(f"{good.FAILED}: {why}", mid=f"s{n}", failed=[{"check": "send_check", "why": why}])
        self.run_night(MISTAKE)
        self.assertEqual(len(self.proposer.calls), 2)

    def test_two_different_never_lines_are_asked_twice_and_the_second_knows_the_first(self):
        self.lose(f"{good.BROKE}: it watered the bed twice", mid="n1")
        self.lose(f"{good.BROKE}: it watered in the noon sun", mid="n2")
        self.run_night(MISTAKE)
        self.assertEqual(len(self.proposer.calls), 2)
        self.assertNotIn(NEVER_LINE, self.proposer.calls[0]["known"])
        self.assertIn(NEVER_LINE, self.proposer.calls[1]["known"])

    def test_only_the_first_lesson_of_the_answer_is_written(self):
        self.lose(f"{good.BROKE}: it watered the bed twice")
        rep = self.run_night(MISTAKE, fk.EARLY)
        self.assertEqual([les["text"] for les in self.lessons.mine()], [NEVER_LINE])
        self.assertIn({"agent": "waterer", "candidate": fk.EARLY["pattern"], "why": study.ONE_A_CASE}, rep["dropped"])

    def test_a_verdict_on_a_row_the_arena_did_not_write_is_no_mistake(self):
        log = Log(self.db, self.plug)
        log.act("live1", "water", result="soaked", detail={"verdict": f"{good.BROKE}: planted"}, at=AT)
        log.result("live1", "wilted", at=AT + 60)
        rep = self.run_night(MISTAKE)
        self.assertEqual(rep["mistakes"], [])
        self.assertEqual(self.lessons.mine(), [])

    def test_a_soft_pattern_with_one_case_on_each_side_makes_none(self):
        log = Log(self.db, self.plug)
        fk.case(log, "b1", "water", "soaked", "grew", stage="seedling", early=True)
        fk.case(log, "b2", "water", "soaked", "wilted", stage="seedling", early=False)
        rep = self.run_night(fk.EARLY)
        (cand,) = rep["candidates"]
        self.assertEqual((cand["with"]["cases"], cand["without"]["cases"]), (1, 1))
        self.assertEqual(cand["verdict"], study.FEW_CASES)
        self.assertEqual(rep["mistakes"], [])
        self.assertEqual(self.lessons.mine(), [])

    def test_a_stop_before_the_write_queues_it_as_a_mistake(self):
        case = self.lose(f"{good.BROKE}: it watered the bed twice")
        said = iter([False, True])  # go on past the proposer, then stop before the write
        rep = Study(self.db, self.plug, proposer=fk.Proposer(MISTAKE), tagger=fk.Tagger(),
                    lessons=self.lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW, stop=lambda: next(said, True))
        (q,) = rep["queued"]
        self.assertEqual((q["lesson"], q["part"]), (NEVER_LINE, "mistake"))
        self.assertTrue(rep["mistakes"][0]["verdict"].startswith(study.QUEUED))
        self.assertEqual(self.lessons.mine(), [])
        rep = Study(self.db, self.plug, proposer=fk.Proposer(), tagger=fk.Tagger(),
                    lessons=self.lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW, take_queue=True)
        (taken,) = rep["from_queue"]
        self.assertEqual((taken["part"], taken["cases_with"]), ("mistake", [case]))
        self.assertEqual([les["text"] for les in self.lessons.mine()], [NEVER_LINE])

    def test_the_proposer_is_told_what_a_mistake_case_is(self):
        from reflection import study as parts
        self.assertIn('When a case has "mistake", it is the only case given', parts.PROPOSE)

    def test_the_night_and_run_reflection_take_the_same_path(self):
        case = self.lose(f"{good.BROKE}: it watered the bed twice")
        rep = night.night(self.db, self.plug, days=30, until=fk.UNTIL, others=[], judge=always_low,
                          proposer=fk.Proposer(MISTAKE), tagger=fk.Tagger())
        self.assertEqual([m["verdict"] for m in rep["mistakes"]], [study.LESSON])
        (linked,) = rep["links"]["lessons"]
        self.assertEqual(linked["cases"], [case])  # the lesson links back to its one case
        self.assertIn("clear mistakes 1", night.text(rep, self.plug))


class SalesFactCheck(unittest.TestCase):
    """The Sales agent's Arena losses, written by arena/learn.py."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def lose(self, why, failed=None, mid="x1"):
        learn.to_case(self.db, match("How much is it?", "It is a price the store never set.", failed),
                      {"won": False, "why": why, "quote": {"turn": 1, "who": "agent", "text": ""}}, mid, now=AT)

    def run_night(self, candidate):
        lessons = SalesLessons(self.db, judge=always_low)
        self.proposer = fk.Proposer(candidate)
        rep = Study(self.db, SALES, proposer=self.proposer, tagger=fk.Tagger(),
                    lessons=lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        return rep, lessons

    def test_many_losses_on_one_check_make_one_lesson(self):
        for n in range(25):  # each line names its own amount, the check is the same
            why = f"{n + 1},000 EGP is not a store price, fee or tool amount"
            self.lose(f"{verdict.FAILED}: price: {why}", failed=[{"check": "price", "why": why}], mid=f"x{n}")
        rep, lessons = self.run_night(dict(MISTAKE, lesson=FACT_LINE, stages=["all"]))
        verdicts = [m["verdict"] for m in rep["mistakes"]]
        self.assertEqual((len(verdicts), verdicts.count(study.LESSON), verdicts.count(study.SAME_MISTAKE)), (25, 1, 24))
        self.assertEqual(len(self.proposer.calls), 1)
        self.assertEqual([les["text"] for les in lessons.mine()], [FACT_LINE])

    def test_past_the_cap_the_rest_are_not_asked(self):
        checks = {"price": "9,000 EGP is not a store price", "size": "size 50 is not a size of the boot",
                  "stock": "the boot is out, the reply says available", "delivery": "90 EGP is not the delivery fee",
                  "order": "the reply says the order is placed, but no tool placed one"}
        for n, (check, why) in enumerate(checks.items()):
            self.lose(f"{verdict.FAILED}: {check}: {why}", failed=[{"check": check, "why": why}], mid=f"x{n}")
        rep, lessons = self.run_night(dict(MISTAKE, lesson=FACT_LINE, stages=["all"]))
        verdicts = [m["verdict"] for m in rep["mistakes"]]
        self.assertEqual(len(verdicts), 5)
        self.assertEqual(verdicts.count(study.NOT_ASKED_CAP), 2)
        self.assertEqual(verdicts[-2:], [study.NOT_ASKED_CAP] * 2)  # the first three are asked
        self.assertEqual(len(self.proposer.calls), study.MISTAKES_A_RUN)
        self.assertEqual(len({m["case_id"] for m in rep["mistakes"]}), 5)  # every case named, none dropped

    def test_one_failed_fact_check_alone_makes_a_lesson(self):
        self.lose(f"{verdict.FAILED}: price: a price the store never set",
                  failed=[{"check": "price", "why": "a price the store never set"}])
        rep, lessons = self.run_night(dict(MISTAKE, lesson=FACT_LINE, stages=["all"]))
        self.assertEqual([(m["kind"], m["verdict"]) for m in rep["mistakes"]], [("a failed fact check", study.LESSON)])
        (les,) = lessons.mine()
        self.assertEqual(les["text"], FACT_LINE)
        self.assertIn("from one clear mistake: a failed fact check", les["source"])

    def test_one_plain_loss_alone_makes_none(self):
        self.lose(verdict.LEFT)
        rep, lessons = self.run_night(dict(MISTAKE, lesson=FACT_LINE, stages=["all"]))
        self.assertEqual(rep["mistakes"], [])
        self.assertEqual(lessons.mine(), [])


class WrongPrice(ar.Agent):
    """The rounds test's agent, always quoting a price the store never set, so every match it plays fails
    the price fact check."""

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.systems.append(messages[0]["content"])
        self.price = "The Mercurial Vapor 17 Elite is 11,000 EGP."
        return ar.Seller.chat(self, messages, tools, effort, max_tokens, whole)


class MistakeNight(ar.Night):
    """The rounds test's night model; the proposer, given one case marked with a mistake, gives FACT_LINE."""

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if messages[0]["content"].startswith("You study the past cases") and '"mistake"' in messages[1]["content"]:
            self.calls += 1
            return say(json.dumps([{"pattern": "The reply gave a price the store never set.", "helps": False,
                                    "lesson": FACT_LINE, "situation": "Any price question.", "stages": ["all"]}]))
        return super().chat(messages, tools, effort, max_tokens, whole)


class ArenaRounds(ar.Base):
    def test_the_arena_between_rounds_takes_the_same_path(self):
        db = self.db()
        with mock.patch.object(ar, "Agent", WrongPrice), mock.patch.object(ar, "Night", MistakeNight):
            code, rep = self.cli(db, [])
        got = rep["rounds"][0]["reflection"]
        self.assertGreaterEqual(got["proposed"], 1)
        self.assertIn(FACT_LINE, self.exams.seen)  # it took the gate like any lesson
        by_text, _ = self.arena_lessons(db)
        self.assertIn("from one clear mistake: a failed fact check", by_text[FACT_LINE]["source"])


if __name__ == "__main__":
    unittest.main()
