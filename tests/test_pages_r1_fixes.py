"""Round 1 review fixes on the two tab page (reflection/pages.py, reflection/morning.py): Modify and
Edit never start a high risk line with no yes, the night line says what the exam said, a sample day's
answers carry that day's clock, Roll back shows its plan first, a bad address or form gets a 400, the
cheap refusals come before the exam, the old A3 answers are not served on the two tab server, and
Last night says at most two lines per agent. No model call: the examiners are fakes."""
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from engine import exam as exam_mod
from engine import plug as plug_mod
from engine import risk
from engine.lessons import MAX_LEN, PULLED, TRYING, WAITING
from kit.db import Db
from reflection import morning as mo
from reflection import pages
from reflection import snapshots
from sim import three_days

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0
HIGH = "When someone asks about the price, say the total is 1450 EGP with delivery."
LOW = "Ask which colour they like before you send the summary."
SIZE = "Ask which size they wear before naming ours."


def examiner(passed, calls):
    def run(text, tags):
        calls.append(text)
        row = exam_mod.Row(1, "s1", "guard", passed, "" if passed else "no_shop", "" if passed else "why")
        return exam_mod.Result(passed, [row], calls=1)
    return run


def low(text, high_about, low_about):
    return risk.LOW


def raises(text, tags):
    raise RuntimeError("model down")


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plugs = [plug_mod.load(ROOT / "sales" / "plug.json"), plug_mod.load(ROOT / "assistant" / "plug.json")]
        self.m = mo.Morning(self.db, self.plugs)
        self.L = self.m.lessons["sales"]

    def card_ids(self, now=None):
        return [c["id"] for c in self.m.view(now=now)["cards"]]


class ModifyHoldsHighRisk(Base):
    """Review finding 1 and red team finding 1: Modify is never the yes on a high risk line."""

    def test_modify_on_a_held_correction_waits_for_a_yes_again(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        m = mo.Morning(db, self.plugs, exams={"sales": examiner(True, [])})
        L = m.lessons["sales"]
        m.correct("sales", HIGH, now=NOW)
        held = L.mine()[-1]
        self.assertEqual(held["state"], WAITING)
        self.assertTrue(L.wants_yes(held["id"]))  # a high risk correction (Lessons.correct, WANTS_YES)
        said = m.modify(held["id"], HIGH, "Be kind.", now=NOW + 10)
        new = L.mine()[-1]
        self.assertEqual((new["text"], new["state"], new["risk"], new["yes_at"]),
                         (HIGH + " Be kind.", WAITING, "high", None))
        self.assertIsNone(L.trial(new["id"]))
        self.assertEqual(L.get(held["id"])["state"], PULLED)
        self.assertIn("It is high risk, so it waits for your yes on its card.", said)
        self.assertIn(new["id"], [c["id"] for c in m.view(now=NOW + 20)["cards"]])
        m.yes(new["id"], "", now=NOW + 30)  # the yes on its card starts it
        self.assertEqual(L.get(new["id"])["state"], TRYING)

    def test_a_high_risk_note_on_a_reflection_card_waits_for_a_yes(self):
        lid = self.L.propose(SIZE, ["asking"], sources=[], now=NOW)
        self.m.modify(lid, SIZE, "Offer 20% off to anyone who asks the price.", now=NOW + 10)
        new = self.L.mine()[-1]
        self.assertEqual((new["state"], new["risk"], new["yes_at"]), (WAITING, "high", None))
        self.assertIn(new["id"], self.card_ids(NOW + 20))

    def test_edit_of_a_live_lesson_into_high_risk_words_waits_for_a_yes(self):
        self.m = mo.Morning(self.db, self.plugs, judge=low, exams={"sales": examiner(True, [])})
        self.L = self.m.lessons["sales"]
        self.m.correct("sales", LOW, now=NOW)
        live = self.L.mine()[-1]
        self.assertEqual(live["state"], TRYING)
        said = self.m.edit(live["id"], HIGH, now=NOW + 10)
        new = self.L.mine()[-1]
        self.assertEqual((new["state"], new["yes_at"]), (WAITING, None))
        self.assertIn("waits for your yes on its card", said)

    def test_a_low_risk_modify_still_starts_with_no_yes(self):
        lid = self.L.propose(SIZE, ["asking"], sources=[], now=NOW)
        said = self.m.modify(lid, "Ask which size they wear in Adidas before naming ours.", "", now=NOW + 10)
        self.assertEqual(self.L.mine()[-1]["state"], TRYING)
        self.assertIn("It is on trial.", said)


class ModifyRefusesBeforeTheExam(Base):
    """Review finding 7: a line Modify refuses anyway takes no exam."""

    def test_same_words_and_too_long_take_no_exam(self):
        calls = []
        self.m.exams = {"sales": examiner(True, calls)}
        lid = self.L.propose(SIZE, ["asking"], sources=[], now=NOW)
        with self.assertRaises(mo.Refused):
            self.m.modify(lid, SIZE, "", now=NOW + 10)
        with self.assertRaises(mo.Refused) as e:
            self.m.modify(lid, "a" * (MAX_LEN - 5), "b" * 10, now=NOW + 10)
        self.assertIn("together", str(e.exception))
        self.assertEqual(calls, [])
        self.assertEqual(self.L.get(lid)["state"], WAITING)


class NightLineSaysWhatTheExamSaid(Base):
    """Review finding 2: "passed the exam" only when it passed."""

    def night(self, exam, line):
        if exam is not None:
            self.m.exams = {"sales": exam}
        self.m.correct("sales", line)
        return pages.Pages(self.m).get("/", {}, "t").split('aria-label="Last night"')[1]

    def test_passed(self):
        self.assertIn("Your correction passed the exam and waits for your yes.", self.night(examiner(True, []), HIGH))

    def test_failed(self):
        night = self.night(examiner(False, []), LOW)
        self.assertIn("Your correction did not pass the exam and waits for your yes.", night)
        self.assertNotIn("passed the exam", night)

    def test_could_not_run(self):
        night = self.night(raises, LOW)
        self.assertIn("The exam could not run on your correction, so it waits for your yes.", night)
        self.assertNotIn("passed the exam", night)

    def test_no_exam_no_correction(self):
        """Review finding 3: a correction is a hotfix and never starts untested (Lessons.correct), so with
        no exam on the page it is refused and Last night has nothing to say about it."""
        with self.assertRaises(mo.Refused):
            self.night(None, HIGH)
        self.assertEqual(self.L.mine(), [])
        self.assertEqual(pages.EXAM_SAID[None], "Your correction waits for your yes.")  # a row from before


class LastNightTwoLines(unittest.TestCase):
    """Review finding 9: at most two lines per agent, the most important first."""

    def test_two_lines_most_important_first(self):
        now = NOW
        a = {"agent": "sales", "live": [], "new": [{"id": 9, "origin": "agent"}],
             "waiting": [{"id": 1, "source": f"a correction the user {pages.CORRECTED}", "card": True,
                          "added_at": now, "exam_result": None}],
             "pulled": [{"id": 2, "pulled_at": now, "pulled_why": "no from the user"}],
             "night": {"until": now, "chats": 5, "hotfix": 2, "trials": []},
             "arena": {"at": now}, "mode_card": {"at": now}}
        self.assertEqual(pages.night_lines(a, now, answered=3),
                         ["Your correction waits for your yes.", "A lesson was pulled."])
        a["waiting"], a["pulled"] = [], []
        self.assertEqual(pages.night_lines(a, now), ["Reflection read 5 chats and wrote a new lesson.",
                                                     "It found a new mode for you and tried it on your past days in "
                                                     "the Arena."])


class RollBackShowsItsPlan(Base):
    """Review finding 5: Roll back shows what it will do first, refuses a stale plan in plain words."""

    def setUp(self):
        super().setUp()
        self.p = pages.Pages(self.m)
        t = time.time() - 600  # the page reads the real clock here
        self.m.exams = {"sales": examiner(True, [])}
        self.m.correct("sales", LOW, now=t)
        snapshots.take(self.db, "sales", t + 100)
        self.lid = self.L.propose(SIZE, ["asking"], sources=[], now=t + 300)
        self.m.yes(self.lid, "", now=t + 310)

    def test_the_agent_page_links_to_the_plan(self):
        page = self.p.get("/agents/sales", {}, "t")
        self.assertIn('href="/agents/sales/rollback">', page)
        self.assertNotIn('action="/rollback"', page)

    def test_the_plan_names_each_change_then_rolls_back(self):
        page = self.p.get("/agents/sales/rollback", {}, "t")
        self.assertIn("<h1>Roll back</h1>", page)
        self.assertIn(SIZE, page)
        self.assertIn(">Pulled<", page)
        self.assertIn('action="/rollback"', page)
        self.assertIn('name="back" value="/agents/sales"', page)
        code = page.split('name="code" value="')[1].split('"')[0]
        said = mo.ACTIONS["/rollback"](self.m, {"agent": ["sales"], "code": [code]})
        self.assertIn("Rolled back to the night of", said)
        self.assertEqual(self.L.get(self.lid)["state"], PULLED)
        after = self.p.get("/agents/sales/rollback", {}, "t")
        self.assertIn("Nothing to roll back", after)
        self.assertNotIn('action="/rollback"', after)

    def test_a_stale_plan_is_refused_in_plain_words(self):
        page = self.p.get("/agents/sales/rollback", {}, "t")
        code = page.split('name="code" value="')[1].split('"')[0]
        other = self.L.propose("Ask which city before you name the delivery days.", ["asking"], sources=[])
        self.m.yes(other, "")
        states = [les["state"] for les in self.L.mine()]
        with self.assertRaises(mo.Refused) as e:
            mo.ACTIONS["/rollback"](self.m, {"agent": ["sales"], "code": [code]})
        self.assertEqual(str(e.exception), mo.STALE_PLAN)
        self.assertNotIn("--yes", str(e.exception))
        self.assertEqual([les["state"] for les in self.L.mine()], states)  # nothing pulled

    def test_no_plan_page_for_an_unknown_agent_or_no_snapshot(self):
        self.assertIsNone(self.p.get("/agents/nobody/rollback", {}, "t"))
        self.assertIsNone(self.p.get("/agents/assistant/rollback", {}, "t"))


class BoxCopy(Base):
    """Review finding 3: the box says a correction starts at once as a hotfix, now that it does."""

    def test_the_box_says_what_a_correction_does(self):
        page = pages.Pages(self.m).get("/agents/sales", {}, "t")
        self.assertIn(pages.h(pages.SAY_NOTE), page)
        for said in ("short exam", "at once as a hotfix in half the cases", "high risk", "your yes on Today"):
            self.assertIn(said, pages.SAY_NOTE)


class TwoTabServer(unittest.TestCase):
    """Review findings 4, 6 and 8 on the demo server with a Live tab (temp databases only)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        three_days.build(root / "days")
        live_path = root / "live" / "ascent.db"
        live_path.parent.mkdir()
        cls.live_db = Db(str(live_path))
        live = mo.live_morning(cls.live_db, str(live_path), mo.repo_plugs(), root / "live" / "assistant")
        live.exams = {"sales": examiner(True, [])}  # main() gives the live page its exam (page_exams)
        cls.pages, cls.dbs = mo.demo_pages(root / "days", root / "served", live=live)
        cls.server = mo.make_server(cls.pages.morning, port=0, pages=cls.pages)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)
        for db in cls.dbs:
            db.close()
        cls.live_db.close()
        cls.tmp.cleanup()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def fetch(self, path):
        with urllib.request.urlopen(self.url(path), timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def post(self, path, fields):
        token = self.fetch("/agents/sales?day=1")[1].split('name="token" value="')[1].split('"')[0]
        body = urllib.parse.urlencode([("token", token)] + list(fields)).encode()
        req = urllib.request.Request(self.url(path), data=body, method="POST", headers={
            "Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def code(self, call):
        with self.assertRaises(urllib.error.HTTPError) as e:
            call()
        e.exception.close()
        return e.exception.code

    def test_a_sample_day_answer_is_dated_that_day_and_live_keeps_the_real_clock(self):
        self.post("/correct", [("back", "/agents/sales?day=1"), ("agent", "sales"), ("line", LOW)])
        row = [les for les in self.pages.days[1].lessons["sales"].mine() if les["text"] == LOW][-1]
        self.assertEqual(row["added_at"], self.pages.at[1])
        before = time.time()
        self.post("/correct", [("back", "/agents/sales?day=live"), ("agent", "sales"), ("line", LOW)])
        row = [les for les in self.pages.live.lessons["sales"].mine() if les["text"] == LOW][-1]
        self.assertGreaterEqual(row["added_at"], before)

    def test_too_many_query_fields_is_a_400(self):
        self.assertEqual(self.code(lambda: self.fetch("/?" + "&".join(f"a{i}=1" for i in range(9)))), 400)
        self.assertEqual(self.fetch("/?day=1")[0], 200)

    def test_two_back_fields_is_a_400(self):
        fields = [("back", "/"), ("back", "/agents"), ("agent", "sales"), ("line", SIZE)]
        self.assertEqual(self.code(lambda: self.post("/correct", fields)), 400)
        self.assertNotIn(SIZE, [les["text"] for les in self.pages.days[1].lessons["sales"].mine()])

    def test_the_old_a3_answers_are_not_served(self):
        lid = self.pages.days[1].lessons["sales"].mine()[0]["id"]
        self.assertEqual(self.code(lambda: self.post("/idea", [("back", "/?day=1"), ("agent", "sales"),
                                                               ("line", SIZE), ("stage", "all")])), 404)
        self.assertEqual(self.code(lambda: self.post("/edit", [("back", "/?day=1"), ("lesson", str(lid)),
                                                               ("line", SIZE)])), 404)
        self.assertNotIn(SIZE, [les["text"] for les in self.pages.days[1].lessons["sales"].mine()])
        self.assertNotIn("/idea", mo.TWO_TAB_ACTIONS)
        self.assertIn("/idea", mo.ACTIONS)  # the A3 page keeps its own


if __name__ == "__main__":
    unittest.main()


class LiveJudge(unittest.TestCase):
    """The live page rates a correction with the live agent's judge, not the never-sure stub, so a low
    risk correction that passes its exam starts at once (DECISIONS 56)."""

    def test_the_live_page_uses_the_real_judge(self):
        import tempfile
        from pathlib import Path
        from kit.db import Db
        from reflection import morning as mo
        from reflection.judge import Judge
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "live.db"
            db = Db(str(path))
            try:
                live = mo.live_morning(db, str(path), mo.repo_plugs(), Path(d) / "assistant")
                self.assertTrue(live.lessons)
                for lessons in live.lessons.values():
                    self.assertIsInstance(lessons.judge, Judge)
            finally:
                db.close()


class JudgeOutsideTheLock(unittest.TestCase):
    """Stack review round 1, item 1: the live page's judge is a model call, so it runs before the answer
    takes the write lock, for a correction, Modify, Edit and an idea. While it runs the live agent's
    process can still write to the same database."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = str(Path(d.name) / "ascent.db")
        self.db = Db(self.path)
        self.addCleanup(self.db.close)
        self.seen = []

    def judge(self, text, high_about, low_about):
        import sqlite3
        other = sqlite3.connect(self.path, timeout=0.2)  # the live agent writing a message meanwhile
        try:
            other.execute("CREATE TABLE IF NOT EXISTS ping (x)")
            other.execute("INSERT INTO ping VALUES (1)")
            other.commit()
            wrote = True
        except sqlite3.OperationalError:
            wrote = False
        finally:
            other.close()
        self.seen.append((text, self.db.conn.in_transaction, wrote))
        return risk.LOW

    def test_the_judge_never_runs_inside_the_answers_transaction(self):
        plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        m = mo.Morning(self.db, plugs, judge=self.judge, exams={"sales": examiner(True, [])})
        L = m.lessons["sales"]
        m.correct("sales", LOW, now=NOW)
        live = L.mine()[-1]
        self.assertEqual(live["state"], TRYING)
        m.idea("sales", SIZE, "all", now=NOW + 10)
        m.edit(live["id"], "Ask which colour they like before you write the summary.", now=NOW + 20)
        trying = [les for les in L.mine() if les["state"] == TRYING][0]
        m.modify(trying["id"], "Ask which brand they wear before naming ours.", "", now=NOW + 30)
        rated = [t for t, _, _ in self.seen]
        for line in (LOW, SIZE, "Ask which brand they wear before naming ours.",
                     "Ask which colour they like before you write the summary."):
            self.assertIn(line, rated)
        self.assertEqual([(t, tx, wrote) for t, tx, wrote in self.seen if tx or not wrote], [])

    def test_a_line_changed_after_its_rating_is_refused(self):
        plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        m = mo.Morning(self.db, plugs, judge=low)
        L = m.lessons["sales"]
        rated = L.rate(LOW)
        with self.assertRaisesRegex(ValueError, "changed after its risk was rated"):
            L.add(SIZE, ["all"], "typed", yes_by="mona", rated=rated, now=NOW)
        self.assertEqual(L.mine(), [])


class JudgeHighHolds(Base):
    """Stack review round 1, item 6 (engine/lessons.py marked_high): a judge that says high outright holds a
    person's edited line for a yes, though the code check found no mark."""

    def test_judge_high_holds_an_edit(self):
        said = {"v": risk.LOW}
        m = mo.Morning(self.db, self.plugs, judge=lambda t, h, lo: said["v"], exams={"sales": examiner(True, [])})
        L = m.lessons["sales"]
        m.correct("sales", LOW, now=NOW)
        live = L.mine()[-1]
        self.assertEqual(live["state"], TRYING)
        said["v"] = risk.HIGH
        m.edit(live["id"], SIZE, now=NOW + 10)
        new = L.mine()[-1]
        self.assertEqual((new["text"], new["risk"], new["state"], new["yes_at"]), (SIZE, "high", WAITING, None))
        self.assertIn(new["id"], self.card_ids_of(m, NOW + 20))

    @staticmethod
    def card_ids_of(m, now):
        return [c["id"] for c in m.view(now=now)["cards"]]


class DemoReadsEnv(unittest.TestCase):
    """Stack review round 1, item 6 (morning.py _demo): the sample days read .env, so Quick start finds its key."""

    def test_demo_loads_env_first(self):
        from unittest import mock
        with mock.patch.object(mo.env, "load") as load, \
                mock.patch.object(mo, "demo_pages", side_effect=mo.Refused("stop here")):
            with mock.patch("sys.stderr"):
                self.assertEqual(mo._demo(ROOT / "sim"), 2)
        load.assert_called_once_with()
