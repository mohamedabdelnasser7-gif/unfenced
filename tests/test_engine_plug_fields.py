"""Task t261029d part 4: three more plug fields. source: what one source of a case is and
how the log knows it, with a source column in the log. harm: the fast results that count
as harm for the trial stop rule. decides: the slow results that settle a trial, and which
one is good. A plug missing one is refused with a plain message."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import plug
from engine.log import Log
from kit.db import Db
from reflection import PLUG
from reflection.results import Results
from tests import plugs
from tests import test_engine_cases as cases

ROW_PLUG = plugs.changed(plugs.WATERER, source={"about": "The gardener who asked for the round.", "known_by": "row"})

OLD_TRACE = """
CREATE TABLE trace (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  case_id TEXT NOT NULL,
  action TEXT,
  result TEXT,
  cause TEXT,
  lessons TEXT NOT NULL DEFAULT '[]',
  stage TEXT,
  step INTEGER,
  detail TEXT,
  at REAL NOT NULL,
  CHECK (action IS NOT NULL OR result IS NOT NULL),
  CHECK (cause IS NULL OR result IS NOT NULL)
);
CREATE INDEX trace_case ON trace (agent, case_id);
"""


def columns(db, table):
    with db.tx() as c:
        return {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}


def indexes(db):
    with db.tx() as c:
        return {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}


class SalesFields(unittest.TestCase):
    def test_source_is_the_person_writing_in_named_by_the_case(self):
        self.assertEqual(PLUG.source.known_by, plug.CASE)
        self.assertIn("person writing in", PLUG.source.about.lower())

    def test_harm_is_no_safe_reply_and_says_complaints_have_no_result_yet(self):
        self.assertEqual(PLUG.harm.results, ("no_safe_reply",))
        self.assertIn("complaint", PLUG.harm.about.lower())
        self.assertIn("no result", PLUG.harm.about.lower())

    def test_an_order_is_good_and_going_quiet_is_not(self):
        # no bad result: a chat with no order a day after the agent last acted settles not good
        self.assertEqual((PLUG.decides.good, PLUG.decides.bad), ("order_created", ()))
        self.assertEqual(PLUG.results["order_created"].shows_in_days, (0.0, 1.0))

    def test_bosta_results_are_recorded_but_never_decide(self):
        self.assertEqual({PLUG.results[r].speed for r in ("delivered", "refused")}, {"slow"})
        self.assertNotIn("delivered", (PLUG.decides.good, *PLUG.decides.bad))
        self.assertNotIn("refused", (PLUG.decides.good, *PLUG.decides.bad))

    def test_every_row_carries_the_chat_as_its_source(self):
        r = Results(Db(":memory:"))
        self.addCleanup(r.db.close)
        r.record("c1", "replied", lessons=[1])
        r.record("c1", "person_replied")
        r.record("c1", "delivered")
        self.assertEqual([row["source"] for row in r.for_chat("c1")], ["c1", "c1", "c1"])
        self.assertEqual(len(r.query(source="c1")), 3)


class MadeUpAgentFields(unittest.TestCase):
    def test_each_made_up_agent_declares_them(self):
        w = plugs.load(plugs.WATERER, self)
        self.assertEqual((w.source.known_by, w.harm.results, w.decides.good, w.decides.bad),
                         (plug.CASE, ("ran_off",), "grew", ("wilted",)))
        for data in (plugs.FAN, plugs.LEDGER):
            p = plugs.load(data, self)
            self.assertEqual(p.result(p.harm.results[0]).speed, plug.FAST)
            self.assertEqual(p.result(p.decides.good).speed, plug.SLOW)

    def test_they_cannot_be_changed_after_loading(self):
        w = plugs.load(plugs.WATERER, self)
        for obj, attr in ((w, "harm"), (w.harm, "results"), (w.decides, "good"), (w.source, "known_by")):
            with self.subTest(attr=attr), self.assertRaises(AttributeError):
                setattr(obj, attr, None)
        self.assertIsInstance(w.harm.results, tuple)
        self.assertIsInstance(w.decides.bad, tuple)


class Refusals(unittest.TestCase):
    def bad(self, data, *words):
        with self.assertRaises(ValueError) as cm:
            plug.from_dict(data)
        for w in words:
            self.assertIn(w, str(cm.exception))

    def changed(self, key, value):
        return plugs.changed(plugs.WATERER, **{key: value})

    def test_a_plug_missing_one_is_refused_in_plain_words(self):
        for key, hint in (("source", "how the log knows it"), ("harm", "count as harm"),
                          ("decides", "settle a trial")):
            with self.subTest(key=key):
                data = copy.deepcopy(plugs.WATERER)
                del data[key]
                self.bad(data, f"missing {key!r}", hint)

    def test_source(self):
        self.bad(self.changed("source", "the bed"), "source: an object")
        self.bad(self.changed("source", {"known_by": "case"}), "source: missing 'about'")
        self.bad(self.changed("source", {"about": "The bed."}), "source: missing 'known_by'")
        for known_by in ("chat", "CASE", "", None, 1):
            with self.subTest(known_by=known_by):
                self.bad(self.changed("source", {"about": "The bed.", "known_by": known_by}), "known_by is case")
        self.bad(self.changed("source", {"about": "The bed.", "known_by": "case", "key": "x"}), "unknown key 'key'")
        self.bad(self.changed("source", {"about": "two\nlines", "known_by": "case"}), "one line")

    def test_harm(self):
        self.bad(self.changed("harm", ["ran_off"]), "harm: an object")
        self.bad(self.changed("harm", {"about": "x"}), "harm: missing 'results'")
        self.bad(self.changed("harm", {"results": []}), "at least one")
        self.bad(self.changed("harm", {"results": "ran_off"}), "a list")
        for name in ("nope", "handed_off", 7, None, ["ran_off"]):
            with self.subTest(name=name):
                self.bad(self.changed("harm", {"results": [name]}), "not a declared result")
        self.bad(self.changed("harm", {"results": ["wilted"]}), "'wilted' is a slow result")
        self.bad(self.changed("harm", {"results": ["ran_off", "ran_off"]}), "named twice")
        self.bad(self.changed("harm", {"results": ["ran_off"], "colour": "red"}), "unknown key 'colour'")
        self.bad(self.changed("harm", {"results": ["ran_off"], "about": ""}), "one line")

    def test_decides(self):
        self.bad(self.changed("decides", ["grew"]), "decides: an object")
        self.bad(self.changed("decides", {"bad": []}), "decides: missing 'good'")
        self.bad(self.changed("decides", {"good": "grew"}), "decides: missing 'bad'")
        for good in ("nope", "delivered", None, ["grew"]):
            with self.subTest(good=good):
                self.bad(self.changed("decides", {"good": good, "bad": []}), "not a declared result")
        self.bad(self.changed("decides", {"good": "grew", "bad": ["nope"]}), "not a declared result")
        self.bad(self.changed("decides", {"good": "grew", "bad": "wilted"}), "a list")
        self.bad(self.changed("decides", {"good": "grew", "bad": ["grew"]}), "named twice")
        self.bad(self.changed("decides", {"good": "grew", "bad": ["wilted", "wilted"]}), "named twice")
        self.bad(self.changed("decides", {"good": "grew", "bad": [], "about": "x"}), "unknown key 'about'")

    def test_bad_can_be_empty(self):
        p = plug.from_dict(self.changed("decides", {"good": "grew", "bad": []}))
        self.assertEqual(p.decides.bad, ())

    def test_a_fast_result_can_decide(self):
        # the Sales agent decides on order_created, a fast result, against going quiet
        p = plug.from_dict(self.changed("decides", {"good": "soaked", "bad": ["grew"]}))
        self.assertEqual((p.decides.good, p.decides.bad), ("soaked", ("grew",)))

    def test_a_plug_file_is_refused_the_same_way(self):
        data = copy.deepcopy(plugs.WATERER)
        del data["harm"]
        with self.assertRaises(ValueError) as cm:
            plugs.load(data, self)
        self.assertIn("missing 'harm'", str(cm.exception))


class CaseNamesTheSource(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.log = Log(self.db, plugs.load(plugs.WATERER, self))

    def test_every_row_takes_its_case_id(self):
        self.log.act("bed-1", "water", result="ran_off", at=1)
        self.log.act("bed-1", "skip", source="bed-1", at=2)  # the same name is allowed
        self.log.result("bed-1", "grew", at=3)
        self.log.act(3, "water", at=4)
        self.assertEqual([r["source"] for r in self.log.query()], ["bed-1", "bed-1", "bed-1", "3"])
        self.assertEqual([r["at"] for r in self.log.query(source="bed-1")], [1.0, 2.0, 3.0])
        self.assertEqual([r["case_id"] for r in self.log.query(source=3)], ["3"])

    def test_another_source_is_refused(self):
        with self.assertRaises(ValueError):
            self.log.act("bed-1", "water", source="bed-2")
        with self.assertRaises(ValueError):
            self.log.result("bed-1", "grew", source="someone")
        self.assertEqual(self.log.query(), [])


class EachRowNamesTheSource(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.log = Log(self.db, plugs.load(ROW_PLUG, self))

    def test_an_action_needs_its_source(self):
        with self.assertRaises(ValueError) as cm:
            self.log.act("bed-1", "water")
        self.assertIn("source", str(cm.exception))
        self.assertEqual(self.log.query(), [])
        self.log.act("bed-1", "water", source="sara", at=1)
        self.log.act("bed-1", "skip", source=42, at=2)
        self.assertEqual([r["source"] for r in self.log.query()], ["sara", "42"])

    def test_a_result_on_its_own_takes_the_source_its_case_has(self):
        self.log.act("bed-1", "water", source="sara", at=1)
        self.log.act("bed-1", "water", source="omar", at=2)
        self.log.act("bed-2", "water", source="sara", at=3)
        self.log.result("bed-1", "grew", at=4)
        self.log.result("bed-9", "wilted", at=5)               # no rows yet: no source, never lost
        self.log.result("bed-9", "grew", source="nour", at=6)
        rows = self.log.query()
        self.assertEqual([r["source"] for r in rows], ["sara", "omar", "sara", "omar", None, "nour"])
        self.assertEqual([r["at"] for r in self.log.query(source="sara")], [1.0, 3.0])

    def test_a_source_is_text_or_a_whole_number(self):
        for bad in ("", "  ", True, 1.5, ["sara"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.log.act("bed-1", "water", source=bad)
            with self.subTest(bad=bad, query=True), self.assertRaises(ValueError):
                self.log.query(source=bad)
        self.assertEqual(self.log.query(), [])


class OldLogs(unittest.TestCase):
    def test_a_log_made_before_sources_gets_the_column_and_case_sources(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name) / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript(OLD_TRACE)
        conn.executemany("INSERT INTO trace (agent, case_id, action, result, at) VALUES (?, ?, ?, ?, ?)",
                         [("waterer", "bed-1", "water", "soaked", 1), ("waterer", "bed-2", None, "grew", 2),
                          ("fan", "house-1", "spin", "spun", 3)])
        conn.commit()
        conn.close()
        db = Db(path)
        self.addCleanup(db.close)
        waterer = Log(db, plugs.load(plugs.WATERER, self))
        self.assertIn("source", columns(db, "trace"))
        self.assertIn("trace_source", indexes(db))
        self.assertEqual([r["source"] for r in waterer.query()], ["bed-1", "bed-2"])
        self.assertEqual([r["source"] for r in waterer.query(agent="fan")], [None])  # not its rows
        fan = Log(db, plugs.load(plugs.FAN, self))
        self.assertEqual([r["source"] for r in fan.query()], ["house-1"])
        Log(db, plugs.load(plugs.WATERER, self))  # a second start changes nothing
        self.assertEqual([r["source"] for r in waterer.query()], ["bed-1", "bed-2"])

    def test_a_row_plug_leaves_old_rows_without_a_source(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        with db.tx() as c:
            c.executescript(OLD_TRACE)
            c.execute("INSERT INTO trace (agent, case_id, action, at) VALUES ('waterer', 'bed-1', 'water', 1)")
        log = Log(db, plugs.load(ROW_PLUG, self))
        self.assertEqual([r["source"] for r in log.query()], [None])

    def test_rows_moved_from_the_old_results_table_carry_their_chat(self):
        db = Db(cases.old_database(self))
        self.addCleanup(db.close)
        results = Results(db)
        rows = results.query()
        self.assertEqual(len(rows), len(cases.OLD_ROWS))
        self.assertEqual([r["source"] for r in rows], [r["case_id"] for r in rows])


if __name__ == "__main__":
    unittest.main()
