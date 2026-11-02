"""A built agent's lost practice match becomes a case its night study reads (arena/learn_built.py,
the live cases work, map item A9). The risk first: such a case never counts in a trial, a fast note
or the agent being live. Made-up agents and lines only; no model, no network."""
import calendar
import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from arena import learn_built
from engine.fast import FastNotes
from engine.lessons import TRYING, Lessons
from engine.log import Log, is_history
from engine.study import BAD, GOOD, Study, settle
from engine.trial import Trials
from kit import turn
from kit.db import Db
from reflection import PLUG as SALES
from tests import plugs
from tests import study_fakes as fk

DAY = 86400.0
NOW = 1_800_000_000.0
STOCK = json.loads((Path(__file__).resolve().parent / "agents" / "stock_watch" / "plug.json").read_text())
# Build always names a bad result and no timer settles a case (DECISIONS item 66), so the stock
# agent here closes a lost chat the way Build would
STOCK["results"]["chat_closed"] = {"speed": "fast", "about": "The chat closed with no stock answer."}
STOCK["decides"]["bad"] = ["chat_closed"]


def low(text, high_about, low_about):
    return "low"


def ticket_plug():
    """A made-up support ticket agent: a bad result that comes on its own, sources named by row."""
    d = copy.deepcopy(STOCK)
    d.update(agent="tickets", case="One support ticket.", stages=["new", "resolved"],
             actions={"reply": "One answer on the ticket.", "tag": "Tag the ticket, for example needs the team."},
             source={"about": "The person who opened the ticket.", "known_by": "row"})
    d["results"]["tagged"] = {"speed": "fast", "shows_in_days": [0, 0], "after": "tag", "about": "The tag was set."}
    d["results"]["reopened"] = {"speed": "slow", "shows_in_days": [1, 3], "about": "The person opened it again."}
    d["decides"] = {"good": "answered", "bad": ["reopened"]}
    return d


def lost(turns, why="the good result was not reached: no stock answer"):
    m = {"card": "made-up-01", "worry": "a late answer", "made_up": True, "turns": turns}
    return m, {"won": False, "why": why, "quote": {"turn": len(turns), "who": "agent", "text": "x"}}


TWO_TURNS = [
    {"n": 1, "customer": "Is the blue mug in stock?", "replies": ["Let me check."], "outcome": "replied",
     "tools": ["store"], "actions": [], "failed": []},
    {"n": 2, "customer": "So?", "replies": ["It may come back soon."], "outcome": "replied", "tools": [],
     "actions": [], "failed": []}]


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(STOCK, self)
        self.lessons = Lessons(self.db, self.plug, judge=low)
        self.lid = self.lessons.propose("Say in stock or out of stock in the first line.", ["all"], sources=[],
                                        now=NOW)
        self.assertEqual(self.lessons.get(self.lid)["state"], TRYING)

    def tmp_folder(self):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)

    @staticmethod
    def saved(mid, won, agent="stock_watch"):
        m, judged = lost(TWO_TURNS)
        m.update(id=mid, agent=agent, won=won, why="a clear answer" if won else judged["why"], quote=judged["quote"])
        return m

    @staticmethod
    def save(folder, matches, extra=()):
        lines = [json.dumps(m) for m in matches] + list(extra)
        (folder / "arena-matches.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


class NeverCountsLive(Base):
    """The riskiest part: practice cases are marked arena and history, so nothing live counts them."""

    def practice(self, n, at):
        for i in range(n):
            m, judged = lost(TWO_TURNS)
            learn_built.to_case(self.db, self.plug, m, judged, f"run1-r1-t{i:02d}", now=at)

    def counted(self, at):
        rep = Trials(self.db, self.plug, lessons=self.lessons).check(at)
        entry = next(t for t in rep["trials"] if t["lesson_id"] == self.lid)
        return entry["with"]["cases"], entry["without"]["cases"]

    def test_practice_cases_are_left_out_of_a_trial(self):
        self.practice(6, NOW + 2 * DAY)
        rows = Log(self.db, self.plug).window(NOW, NOW + 3 * DAY)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(is_history(r) and r["detail"]["arena"] is True for case in rows.values() for r in case))
        self.assertEqual(self.counted(NOW + 3 * DAY), (0, 0))

    def test_a_live_case_beside_them_still_counts(self):
        self.practice(3, NOW + 2 * DAY)
        log = Log(self.db, self.plug)
        log.act("chat-1", "reply", result="replied", lessons=[self.lid], stage="asking", at=NOW + DAY)
        log.act("chat-2", "reply", result="replied", stage="asking", at=NOW + DAY)
        self.assertEqual(self.counted(NOW + 3 * DAY), (1, 1))

    def test_practice_wins_written_by_the_night_are_left_out_too(self):
        folder = self.tmp_folder()
        self.save(folder, [self.saved("20270115T080000-r1-t01", True), self.saved("20270115T080000-r1-t02", False)])
        got = learn_built.from_folder(self.db, self.plug, folder, until=NOW + 30 * DAY)
        self.assertEqual(got, {"written": 2, "won": 1, "lost": 1})
        self.assertEqual(self.counted(NOW + 30 * DAY), (0, 0))


    def test_no_fast_note_for_a_practice_case(self):
        self.practice(2, NOW + DAY)
        notes = FastNotes(self.db, self.plug, writer=lambda *a, **k: self.fail("no note is written"))
        self.assertEqual(notes.sweep(now=NOW + 2 * DAY), [])

    def test_the_agent_is_not_live_on_practice_alone(self):
        self.practice(2, NOW + DAY)
        with self.db.tx() as c:
            live = c.execute("SELECT DISTINCT agent FROM trace WHERE (CASE WHEN json_valid(detail) THEN "
                             "json_extract(detail, '$.history') END) IS NOT 1").fetchall()
        self.assertEqual(live, [])  # the Morning page's _live query finds no live agent


class FromFolder(Base):
    """The night's way in: every training match saved in the agent's folder, won and lost."""

    def test_wins_close_good_losses_not_good_gate_and_other_matches_left_out(self):
        folder = self.tmp_folder()
        at = calendar.timegm((2027, 1, 15, 8, 0, 0))
        self.save(folder, [self.saved("20270115T080000-r1-t01", True), self.saved("20270115T080000-r1-t02", False),
                           self.saved("20270115T080000-r1-g01", True), self.saved("20270115T080000-r1-t03", True, "other"),
                           self.saved("20990101T000000-r1-t01", True), self.saved("not-a-match-id", True)],
                  extra=["not json", "[1, 2]"])
        got = learn_built.from_folder(self.db, self.plug, folder, until=at + DAY)
        self.assertEqual(got, {"written": 2, "won": 1, "lost": 1})
        log = Log(self.db, self.plug)
        won = log.case("arena-stock_watch-20270115T080000-r1-t01")
        self.assertEqual(won[-1]["result"], "answered")
        self.assertEqual(settle(self.plug, won, at + DAY)[:2], (GOOD, "answered"))
        lost_rows = log.case("arena-stock_watch-20270115T080000-r1-t02")
        self.assertEqual(settle(self.plug, lost_rows, at + DAY)[:2], (BAD, "chat_closed"))
        self.assertTrue(all(r["at"] < at + 60 for r in won + lost_rows))
        self.assertEqual(log.case("arena-stock_watch-20270115T080000-r1-g01"), [])
        again = learn_built.from_folder(self.db, self.plug, folder, until=at + DAY)
        self.assertEqual(again, {"written": 0, "won": 0, "lost": 0})  # written once

    def test_no_file_a_linked_file_or_a_big_one_writes_nothing(self):
        folder = self.tmp_folder()
        none = {"written": 0, "won": 0, "lost": 0}
        self.assertEqual(learn_built.from_folder(self.db, self.plug, folder), none)
        real = self.tmp_folder()
        self.save(real, [self.saved("20270115T080000-r1-t01", True)])
        (folder / "arena-matches.jsonl").symlink_to(real / "arena-matches.jsonl")
        self.assertEqual(learn_built.from_folder(self.db, self.plug, folder), none)
        with mock.patch.object(learn_built, "MAX_MATCHES_BYTES", 10):
            big = learn_built.from_folder(self.db, self.plug, real)
        self.assertEqual({k: big[k] for k in none}, none)
        self.assertIn("no practice was read", big["skipped"])  # review merge r1 finding 8


class ACase(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def test_a_lost_chat_closes_on_the_bad_result_and_the_night_reads_it(self):
        plug = plugs.load(STOCK, self)
        m, judged = lost(TWO_TURNS)
        case = learn_built.to_case(self.db, plug, m, judged, "run1-r1-t01", now=NOW)
        self.assertEqual(case, "arena-stock_watch-run1-r1-t01")
        rows = Log(self.db, plug).case(case)
        self.assertEqual([(r["action"], r["result"], r["stage"]) for r in rows],
                         [("reply", "replied", "asking"), ("reply", "replied", "asking"), (None, "chat_closed", "asking")])
        self.assertEqual(rows[0]["detail"]["customer"], "Is the blue mug in stock?")
        self.assertEqual(rows[0]["detail"]["tools"], ["store"])
        self.assertEqual(rows[1]["detail"]["verdict"], judged["why"])
        self.assertNotIn("verdict", rows[0]["detail"])
        self.assertEqual(settle(plug, rows, NOW)[:2], (BAD, "chat_closed"))
        rep = Study(self.db, plug, proposer=fk.Proposer(), tagger=fk.Tagger(),
                    lessons=Lessons(self.db, plug, judge=low)).run(NOW - 2 * DAY, NOW, now=NOW)
        self.assertEqual((rep["read"]["cases"], rep["decided"]["bad"]), (1, 1))

    def test_a_ticket_closes_with_its_bad_result_its_actions_and_its_source(self):
        plug = plugs.load(ticket_plug(), self)
        turns = [{"n": 1, "customer": "My order came broken.", "replies": ["Sorry, a new one is on its way."],
                  "outcome": "replied", "tools": [], "actions": ["reply", "tag", "close"], "failed": []}]
        m, judged = lost(turns)
        case = learn_built.to_case(self.db, plug, m, judged, "run2-r1-t01", now=NOW)
        rows = Log(self.db, plug).case(case)
        self.assertEqual([(r["action"], r["result"]) for r in rows],
                         [("reply", None), ("tag", None), (None, "reopened")])  # replied does not end tag
        self.assertEqual({r["source"] for r in rows}, {"arena-made-up-01"})
        self.assertEqual({r["stage"] for r in rows}, {"new"})
        self.assertEqual(rows[0]["detail"]["actions"], ["reply", "tag", "close"])
        self.assertEqual(rows[1]["detail"]["verdict"], judged["why"])
        self.assertTrue(all(is_history(r) for r in rows))
        self.assertLess(rows[-1]["at"], NOW)
        self.assertEqual(settle(plug, rows, NOW)[:2], (BAD, "reopened"))

    def test_a_bad_result_that_ends_an_action_closes_on_that_action(self):
        """Review merge r1 finding 6: the bad result has after set, so the closing row is its action."""
        d = ticket_plug()
        d["results"]["reopened"].update(after="tag", speed="fast", shows_in_days=[0, 0])
        plug = plugs.load(d, self)
        m, judged = lost(TWO_TURNS)
        rows = Log(self.db, plug).case(learn_built.to_case(self.db, plug, m, judged, "act-1", now=NOW))
        self.assertEqual((rows[-1]["action"], rows[-1]["result"]), ("tag", "reopened"))
        self.assertEqual(settle(plug, rows, NOW)[:2], (BAD, "reopened"))

    def test_an_agent_first_case_with_no_answer(self):
        plug = plugs.load(ticket_plug(), self)
        turns = [{"n": 1, "customer": None, "replies": ["Hi, still thinking about the desk?"], "outcome": "replied",
                  "tools": [], "actions": [], "failed": []}]
        m, judged = lost(turns, why="the good result was not reached: the lead never answered")
        rows = Log(self.db, plug).case(learn_built.to_case(self.db, plug, m, judged, "lead-1", now=NOW))
        self.assertEqual(rows[0]["detail"]["customer"], None)
        self.assertEqual((rows[0]["action"], rows[0]["result"]), ("reply", "replied"))

    def test_a_turn_outcome_that_is_a_deciding_result_never_decides(self):
        d = copy.deepcopy(STOCK)
        d["decides"] = {"good": "replied", "bad": ["chat_closed"]}  # a plug the model wrote with a fast good result
        plug = plugs.load(d, self)
        m, judged = lost(TWO_TURNS)
        rows = Log(self.db, plug).case(learn_built.to_case(self.db, plug, m, judged, "d1", now=NOW))
        self.assertEqual([r["result"] for r in rows], [None, None, "chat_closed"])
        self.assertEqual(settle(plug, rows, NOW)[:2], (BAD, "chat_closed"))

    def test_a_plug_with_no_reply_action_takes_its_first(self):
        d = ticket_plug()
        d["actions"] = {"post": "Write one post."}
        d["results"] = {k: v for k, v in d["results"].items() if v.get("after") in (None, "post")}
        d["results"]["posted"] = {"speed": "fast", "shows_in_days": [0, 0], "after": "post"}
        d["harm"] = {"results": ["posted"]}
        plug = plugs.load(d, self)
        m, judged = lost([{"n": 1, "customer": "A brief.", "replies": ["A post."], "outcome": "replied"}])
        rows = Log(self.db, plug).case(learn_built.to_case(self.db, plug, m, judged, "p1", now=NOW))
        self.assertEqual([(r["action"], r["result"]) for r in rows], [("post", None), (None, "reopened")])

    def test_refusals_and_a_second_write(self):
        plug = plugs.load(STOCK, self)
        m, judged = lost(TWO_TURNS)
        with self.assertRaisesRegex(ValueError, "only a lost match"):
            learn_built.to_case(self.db, plug, m, {"won": True}, "x", now=NOW)
        with self.assertRaisesRegex(ValueError, "arena/learn.py"):
            learn_built.to_case(self.db, SALES, m, judged, "x", now=NOW)
        a = learn_built.to_case(self.db, plug, m, judged, "same", now=NOW)
        b = learn_built.learner(self.db, plug)(m, judged, "same")
        self.assertEqual(a, b)
        self.assertEqual(len(Log(self.db, plug).case(a)), 3)

    def test_a_match_with_no_turns_still_carries_its_verdict(self):
        plug = plugs.load(STOCK, self)
        rows = Log(self.db, plug).case(learn_built.to_case(self.db, plug, *lost([]), "empty", now=NOW))
        self.assertEqual(len(rows), 2)  # the one row and the closing bad result
        self.assertEqual(rows[0]["detail"]["verdict"], "the good result was not reached: no stock answer")


class PracticeThenNight(unittest.TestCase):
    """End to end: a built agent practises (arena/practice.py on fake models), then its night writes
    the training matches as cases and its study reads both sides."""

    def test_the_night_reads_its_practice(self):
        import time
        from reflection import night
        from tests import test_arena_practice as tp
        world = iter([True, False, True, False, True, False, True, False])

        def judge(messages):
            return tp.say(json.dumps({"reached": next(world, False), "broke_never": False, "turn": 1,
                                      "why": "a clear answer"}))

        base = tp.Base("run")
        base.setUp()
        self.addCleanup(base.doCleanups)
        plug = json.loads((base.folder / "plug.json").read_text())  # a bad result, as Build always names
        plug["results"]["chat_closed"] = STOCK["results"]["chat_closed"]
        plug["decides"]["bad"] = ["chat_closed"]
        (base.folder / "plug.json").write_text(json.dumps(plug))
        code, rep = base.main("--matches", "4", "--json", world=tp.World(judge=judge))
        self.assertIn(code, (0, 1))
        trained = [m for m in base.matches() if "-t" in m["id"]]
        self.assertEqual(len(trained), 4)
        agent = turn.load(base.folder)
        db = Db(":memory:")
        self.addCleanup(db.close)
        self.assertEqual(night.built_folder(agent.plug, base.folder / "plug.json"), base.folder)
        proposer = fk.Proposer()
        got = night.night(db, agent.plug, until=time.time() + 120, others=[], judge=low, proposer=proposer,
                          tagger=fk.Tagger(), practice=base.folder)
        won = sum(m["won"] for m in trained)
        self.assertEqual(got["practice_cases"], {"written": 4, "won": won, "lost": 4 - won})
        self.assertEqual((got["decided"]["good"], got["decided"]["bad"]), (won, 4 - won))
        self.assertEqual(len(proposer.calls), 1)  # both sides settled, so the study looked for a pattern
        self.assertIn("practice matches written as cases: 4", night.text(got, agent.plug))
        self.assertEqual(got["trials"]["trials"], [])

    def test_the_sales_plug_and_a_folder_that_is_not_the_agent_get_none(self):
        from reflection import night
        self.assertIsNone(night.built_folder(SALES, Path(__file__).resolve().parent.parent / "sales" / "plug.json"))
        plug = plugs.load(ticket_plug(), self)
        self.assertIsNone(night.built_folder(plug, Path(__file__).resolve().parent / "agents" / "stock_watch" / "plug.json"))


if __name__ == "__main__":
    unittest.main()
