"""Step 2: cases. Every action is saved under its case with the lesson ids it was given; a
later result attaches by case; the log is read by agent, case, action, result and time."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine.log import Log
from kit.db import Db
from reflection.results import Results
from tests import plugs

OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  chat_id TEXT NOT NULL,
  step INTEGER,
  stage TEXT,
  outcome TEXT NOT NULL,
  lessons TEXT,
  detail TEXT,
  at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS results_chat ON results (chat_id);
"""
OLD_ROWS = [  # (agent, chat_id, step, stage, outcome, lessons, detail, at), as the old record wrote them
    ("sales", "a1", 2, "asking", "check_failed", "[1, 2]", '{"reply": "x", "feedback": "y"}', 100.0),
    ("sales", "a1", 4, "asking", "replied", "[1, 2]", '{"tool_steps": 1}', 101.0),
    ("sales", "a1", None, "ordering", "order_drafted", "[]", '{"total": 1958}', 102.0),
    ("sales", "a1", None, "ordering", "order_created", "[]", '{"order": "#1001", "cod_risk": "low"}', 103.0),
    ("sales", "b2", None, "asking", "limited", "[]", '{"limit": "customer", "told": true}', 104.0),
    ("sales", "b2", 3, "asking", "model_error", "[3]", '{"in_a_row": 1}', 105.0),
    ("sales", "b2", 5, "asking", "turn_failed", "[]", '{"in_a_row": 2}', 106.0),
    ("sales", "b2", None, "asking", "no_safe_reply", "[3]", '{"by": "turn_failed", "in_a_row": 2}', 107.0),
    ("sales", "b2", 7, "asking", "person_replied", "[]", '{"note": "wamid.1"}', 108.0),
    ("sales", "b2", None, "asking", "check_failed", "[]", '{"reply": "z", "feedback": "w"}', 109.0),
    ("sales", "b2", 9, "asking", "replied", "[]", None, 110.0),
    ("sales", "c3", None, "asking", "no_safe_reply", "[]", '{"by": "send_check", "in_a_row": 3}', 111.0),
    ("sales", "a1", None, None, "delivered", "[]", None, 112.0),
    ("sales", "c3", None, None, "refused", None, None, 113.0),
]


def old_database(test, rows=OLD_ROWS):
    """A database file as it was before the engine, with the old results table and rows."""
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    path = Path(d.name) / "ascent.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.executemany("INSERT INTO results (agent, chat_id, step, stage, outcome, lessons, detail, at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return path


def tables(db):
    with db.tx() as c:
        return {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


class MadeUpAgentCases(unittest.TestCase):
    """The waterer runs through the log with no engine change: one bed is one case."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.log = Log(self.db, plugs.load(plugs.WATERER, self))

    def test_action_with_its_lessons_then_a_later_result_by_case(self):
        a = self.log.act("bed-3", "water", lessons=[7, 5, 7], result="soaked", stage="seedling", at=10)
        b = self.log.act("bed-3", "skip", lessons=[5], at=20)  # its result is not known yet
        c = self.log.result("bed-3", "wilted", cause="frost", detail={"note": "cold night"}, at=400000)
        self.log.act("bed-9", "water", result="soaked", at=30)
        rows = self.log.case("bed-3")
        self.assertEqual([r["id"] for r in rows], [a, b, c])
        self.assertEqual([(r["action"], r["result"], r["lessons"]) for r in rows],
                         [("water", "soaked", [5, 7]), ("skip", None, [5]), (None, "wilted", [])])
        self.assertEqual((rows[2]["cause"], rows[2]["detail"], rows[2]["case_id"]), ("frost", {"note": "cold night"}, "bed-3"))
        self.assertEqual({r["agent"] for r in rows}, {"waterer"})

    def test_query_by_case_action_result_and_time(self):
        self.log.act("bed-1", "water", result="soaked", at=100)
        self.log.act("bed-2", "water", result="soaked", at=200)
        self.log.act(3, "skip", result="skipped", at=300)  # a whole number is a case id too
        self.log.result("bed-1", "grew", at=900)
        self.assertEqual([r["case_id"] for r in self.log.query(result="soaked")], ["bed-1", "bed-2"])
        self.assertEqual([r["case_id"] for r in self.log.query(action="skip")], ["3"])
        self.assertEqual([r["case_id"] for r in self.log.case(3)], ["3"])
        self.assertEqual([r["at"] for r in self.log.query(since=200, until=900)], [200.0, 300.0])
        self.assertEqual([r["result"] for r in self.log.query(case="bed-1", since=500)], ["grew"])
        self.assertEqual(self.log.query(case="bed-404"), [])

    def test_refuses_what_its_plug_did_not_declare(self):
        bad = [
            lambda: self.log.act("bed-1", "reply"),                            # not its action
            lambda: self.log.act("bed-1", "water", result="replied"),          # not its result
            lambda: self.log.act("bed-1", "water", result="skipped"),          # skipped ends skip, not water
            lambda: self.log.act("bed-1", "water", result="grew"),             # a slow result comes on its own
            lambda: self.log.act("bed-1", "water", cause="frost"),             # a cause goes with a result
            lambda: self.log.result("bed-1", "soaked"),                        # soaked ends water: use act
            lambda: self.log.result("bed-1", "delivered"),                     # the Sales agent's, not its own
            lambda: self.log.result("bed-1", "wilted", cause="courier_late"),  # not its cause
            lambda: self.log.query(result="replied"),
            lambda: self.log.query(action="hand_off"),
        ]
        for i, f in enumerate(bad):
            with self.subTest(i=i), self.assertRaises(ValueError):
                f()
        for case in (None, "", "  ", True, 1.5, ["bed"]):
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.log.act(case, "water")
        for ids in (["1"], [True], [1.0]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.log.act("bed-1", "water", lessons=ids)
        self.assertEqual(self.log.query(), [])

    def test_the_database_refuses_a_row_with_no_action_and_no_result(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.tx() as c:
                c.execute("INSERT INTO trace (agent, case_id, at) VALUES ('waterer', 'bed-1', 1)")


class AgentsShareOneLog(unittest.TestCase):
    def test_each_agent_reads_its_own_rows_unless_it_names_another(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        front, waterer = Results(db), Log(db, plugs.load(plugs.WATERER, self))
        front.record("c1", "replied", lessons=[1])
        waterer.act("c1", "water", result="soaked")  # the same case id, another agent
        self.assertEqual([r["outcome"] for r in front.for_chat("c1")], ["replied"])
        self.assertEqual([r["result"] for r in waterer.case("c1")], ["soaked"])
        self.assertEqual([r["result"] for r in waterer.query(agent="sales")], ["replied"])
        self.assertEqual(waterer.query(agent="nobody"), [])


class SalesCases(unittest.TestCase):
    """The Sales agent's case is its chat."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.results = Results(self.db)

    def test_each_turn_outcome_is_saved_with_its_action_and_lessons(self):
        self.results.record("c1", "check_failed", stage="asking", lessons={2, 1}, detail={"feedback": "x"})
        self.results.record("c1", "replied", step=4, stage="asking", lessons={2, 1})
        self.results.record("c1", "order_created", stage="ordering", detail={"order": "#1001"})
        self.results.record("c1", "no_safe_reply", stage="ordering", lessons=[2], detail={"by": "send_check"})
        rows = self.results.query(case="c1")
        self.assertEqual([(r["action"], r["result"], r["lessons"]) for r in rows],
                         [("reply", "check_failed", [1, 2]), ("reply", "replied", [1, 2]),
                          ("order", "order_created", []), ("reply", "no_safe_reply", [2])])

    def test_a_later_result_attaches_by_chat(self):
        self.results.record("c1", "replied", step=4, stage="asking", lessons=[1])
        self.results.record("c1", "delivered", detail={"bosta": "x"})
        self.results.record("c2", "refused")
        later = self.results.for_chat("c1")[-1]
        self.assertEqual((later["outcome"], later["action"], later["chat_id"], later["lessons"]),
                         ("delivered", None, "c1", []))
        self.assertEqual([r["case_id"] for r in self.results.query(result="delivered")], ["c1"])
        self.assertEqual([r["case_id"] for r in self.results.query(result="refused")], ["c2"])

    def test_refuses_lessons_on_a_result_that_comes_on_its_own_and_another_agent(self):
        with self.assertRaises(ValueError):
            self.results.record("c1", "person_replied", lessons=[1])
        with self.assertRaises(ValueError):
            self.results.record("c1", "replied", agent="marketing")
        self.assertEqual(self.results.for_chat("c1"), [])


class MoveOldRows(unittest.TestCase):
    """Rows of the old results table move into the engine's log without loss."""

    def test_every_row_moves_with_the_same_id_and_values(self):
        path = old_database(self)
        db = Db(path)
        self.addCleanup(db.close)
        results = Results(db)
        self.assertNotIn("results", tables(db))
        moved = {r["id"]: r for chat in ("a1", "b2", "c3") for r in results.for_chat(chat)}
        self.assertEqual(sorted(moved), list(range(1, len(OLD_ROWS) + 1)))
        for i, (agent, chat_id, step, stage, outcome, lessons, detail, at) in enumerate(OLD_ROWS, start=1):
            r = moved[i]
            self.assertEqual((r["agent"], r["chat_id"], r["step"], r["stage"], r["outcome"], r["at"]),
                             (agent, chat_id, step, stage, outcome, at), i)
            self.assertEqual(r["lessons"], json.loads(lessons) if lessons else [], i)
            self.assertEqual(r["detail"], json.loads(detail) if detail else None, i)
            self.assertEqual(r["action"], results.plug.result(outcome).after, i)

    def test_it_moves_once_and_new_rows_follow(self):
        path = old_database(self)
        db = Db(path)
        Results(db)
        db.close()
        db = Db(path)  # the next start finds nothing to move
        self.addCleanup(db.close)
        results = Results(db)
        self.assertEqual(len(results.query()), len(OLD_ROWS))
        rid = results.record("a1", "replied", lessons=[9])
        self.assertGreater(rid, len(OLD_ROWS))

    def test_a_row_it_cannot_place_stops_the_move_and_loses_nothing(self):
        for bad in (("sales", "z9", None, None, "made_up", "[]", None, 1.0),
                    ("marketing", "z9", None, None, "replied", "[]", None, 1.0)):
            with self.subTest(bad=bad):
                path = old_database(self, OLD_ROWS + [bad])
                db = Db(path)
                self.addCleanup(db.close)
                with self.assertRaises(ValueError):
                    Results(db)
                self.assertIn("results", tables(db))
                with db.tx() as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM results").fetchone()[0], len(OLD_ROWS) + 1)
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM trace").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
