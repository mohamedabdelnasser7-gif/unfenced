"""Task t261029n: nightly snapshots of an agent's lessons, and a rollback to one night
(reflection/snapshots.py). One snapshot a night, the same night taken twice writes nothing, the
diff is right, the rollback plan changes nothing without --yes, --yes restores the lessons
given that night through Lessons.pull only, in one transaction, and names what cannot come
back; lesson rows are never rewritten and snapshot rows never change. Made-up plugs and
temporary databases only."""
import contextlib
import io
import json
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import plug as plug_mod
from engine import risk
from engine.lessons import KEPT, PULLED, TRYING, WAITING, Lessons
from engine.trial import Trials
from kit.db import Db
from reflection import morning
from reflection import night
from reflection import snapshots as snap_mod
from tests import plugs
from tests import study_fakes as fk
from tests.test_night import Setup as NightSetup
from tests.kept import kept_lesson

ROOT = Path(snap_mod.__file__).resolve().parent.parent
DAY = 86400.0
T1 = 1_800_000_000.0           # the first night
T2 = T1 + DAY                  # the next night
T3 = T2 + 3600                 # the rollback
N1, N2 = snap_mod.night_of(T1), snap_mod.night_of(T2)
OWNER = "the user"


def always_low(text, high_about, low_about):
    return risk.LOW


class Base(unittest.TestCase):
    """The waterer's plug as a file and a database file in one temporary folder."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.plug_path = self.dir / "waterer" / "plug.json"  # a repo's layout, so --plug waterer finds it
        self.plug_path.parent.mkdir()
        self.plug_path.write_text(json.dumps(plugs.WATERER), encoding="utf-8")
        self.plug = plug_mod.load(self.plug_path)
        self.db_path = self.dir / "agent.db"
        self.db = Db(self.db_path)
        self.addCleanup(self.db.close)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)

    def build(self):
        """Night 1: A and E kept, B on trial, C waits its turn behind B, D waits for a yes.
        Then: E stopped, B kept by its trial, F a person's line, D said yes to and on trial,
        G waits for a yes, H waits its turn behind C. Night 2. Returns the ids."""
        L = self.lessons
        ids = {"A": kept_lesson(L, "Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=T1 - 7200),
               "E": kept_lesson(L, "Visit the north bed first.", ["seedling"], yes_by=OWNER, now=T1 - 7200),
               "B": L.propose("Check the seedling beds after the shade moves.", ["seedling"], sources=[], now=T1 - 3600),
               "C": L.propose("Visit the seedling beds after the grown beds.", ["seedling"], sources=[], now=T1 - 3500),
               "D": L.propose("Wait a day between rounds on the grown beds.", ["grown"], sources=[], trial=False,
                              now=T1 - 3400)}
        self.assertEqual(L.waits_for(ids["C"], T1), [ids["B"]])
        self.first = snap_mod.take(self.db, "waterer", T1)
        self.assertTrue(L.pull(ids["E"], "stopped by the owner: too slow", now=T1 + 3600))
        self.assertTrue(L.keep(ids["B"]))
        ids["F"] = kept_lesson(L, "Visit the grown beds last.", ["grown"], yes_by=OWNER, now=T1 + 3600)
        self.assertTrue(L.approve(ids["D"], OWNER, now=T1 + 3700))
        ids["G"] = L.propose("Leave the seedling beds for the end of the round.", ["seedling"], sources=[], trial=False,
                             now=T1 + 3800)
        ids["H"] = L.propose("Water the seedling beds before the sun is high.", ["seedling"], sources=[], now=T1 + 3900)
        self.assertEqual(L.get(ids["D"])["state"], TRYING)
        self.assertEqual(L.waits_for(ids["H"], T2), [ids["C"]])
        self.second = snap_mod.take(self.db, "waterer", T2)
        return ids

    def live(self, at=T3):
        return {les["id"] for les in self.lessons.live(now=at)}

    def tables(self):
        """Every row of the lessons, trials and snapshot tables, read on a fresh connection."""
        c = sqlite3.connect(self.db_path)
        try:
            return {t: c.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()
                    for t in ("lessons", "trials", "lesson_clashes", "lesson_snapshots")}
        finally:
            c.close()

    def rollback(self, *extra, plug=None, to=N1, now=T3):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = snap_mod.main(["rollback", "--plug", str(plug or self.plug_path), "--to", to,
                                  "--db", str(self.db_path), *extra], now=now, root=self.dir)
        return code, out.getvalue(), err.getvalue()

    def paste(self, preview, now=T3, *, bring_back=False):
        """Run the command a preview printed, as pasted: the one with --bring-back, or the one without."""
        line, = [ln.strip() for ln in preview.splitlines() if " --yes " in ln and (" --bring-back " in ln) == bring_back]
        argv = shlex.split(line)
        self.assertEqual(argv[:3], ["python3", "-I", "reflection/snapshots.py"])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = snap_mod.main(argv[3:], now=now, root=self.dir)
        return code, out.getvalue(), err.getvalue()

    def code(self, snap, at=T3):
        """The plan's code now, as a preview prints it."""
        with self.db.tx() as c:
            return snap_mod.plan_code(snap, snap_mod.plan(c, "waterer", snap, at))


class Taking(Base):
    def test_a_snapshot_lists_every_lesson_with_its_state_trial_and_score(self):
        ids = self.build()
        got = {e["id"]: (e["state"], e["trial"], e["live"]) for e in self.first["lessons"]}
        self.assertEqual(got, {ids["A"]: (KEPT, None, True), ids["E"]: (KEPT, None, True),
                               ids["B"]: (TRYING, snap_mod.ON_TRIAL, True), ids["C"]: (WAITING, snap_mod.WAITS_TURN, False),
                               ids["D"]: (WAITING, None, False)})
        self.assertTrue(all(e["score"] == 0.0 for e in self.first["lessons"]))
        self.assertEqual((self.first["night"], self.first["kind"], self.first["written"]), (N1, "night", True))
        self.assertEqual(len(self.first["hash"]), 64)

    def test_the_same_night_twice_writes_nothing(self):
        kept_lesson(self.lessons, "Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=T1 - 60)
        one = snap_mod.take(self.db, "waterer", T1)
        two = snap_mod.take(self.db, "waterer", T1 + 60)
        self.assertEqual((two["id"], two["written"]), (one["id"], False))
        self.assertEqual(len(self.tables()["lesson_snapshots"]), 1)

    def test_a_changed_set_the_same_night_is_its_newer_copy(self):
        one = snap_mod.take(self.db, "waterer", T1)
        lid = kept_lesson(self.lessons, "Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=T1 + 60)
        two = snap_mod.take(self.db, "waterer", T1 + 120)
        self.assertNotEqual(one["id"], two["id"])
        self.assertEqual([e["id"] for e in snap_mod.of_night(self.db, "waterer", N1)["lessons"]], [lid])

    def test_the_diff_names_what_changed(self):
        ids = self.build()
        d = snap_mod.diff(self.first["lessons"], self.second["lessons"])
        self.assertEqual(d, {"added": [(ids["F"], KEPT), (ids["G"], WAITING), (ids["H"], WAITING)],
                             "on_trial": [ids["D"]], "kept": [ids["B"]], "pulled": [ids["E"]], "waiting": [ids["C"]]})
        self.assertEqual(snap_mod.diff_text(d, N1),
                         f"since the night of {N1}: added 3 (lesson {ids['F']} kept, lesson {ids['G']} waiting, "
                         f"lesson {ids['H']} waiting); on trial 1 (lesson {ids['D']}); kept 1 (lesson {ids['B']}); "
                         f"pulled 1 (lesson {ids['E']}); still waiting 1 (lesson {ids['C']})")
        self.assertEqual(snap_mod.diff_text(snap_mod.diff(self.second["lessons"], self.second["lessons"]), N2),
                         f"since the night of {N2}: still waiting 3 (lesson {ids['C']}, {ids['G']}, {ids['H']})")
        self.assertEqual(snap_mod.diff_text(None, None), "first snapshot of this agent")

    def test_a_paused_trial_and_a_decided_one_show_as_such(self):
        L = self.lessons
        b = L.propose("Check the seedling beds after the shade moves.", ["seedling"], sources=[], now=T1 - 3600)
        p = L.propose("Water the seedling beds before the sun is high.", ["grown"], sources=[], now=T1 - 3500)
        trials = Trials(self.db, self.plug, lessons=L)
        with self.db.tx() as c:  # b kept by its verdict, p paused by the stop rule, each with its mark
            self.assertTrue(L.keep(b, c=c))
            trials._mark(c, b, "verdict", value=0.97, detail={}, now=T1 - 60)
            self.assertTrue(L.pause(p, T1 - 60, c=c))
            trials._mark(c, p, "paused", value=2.0, detail={}, now=T1 - 60)
        got = {e["id"]: (e["state"], e["trial"], e["live"]) for e in snap_mod.take(self.db, "waterer", T1)["lessons"]}
        self.assertEqual(got, {b: (KEPT, snap_mod.DECIDED, True), p: (TRYING, snap_mod.PAUSED, False)})

    def test_a_trial_that_ends_the_same_night_makes_a_newer_copy_and_the_newest_copy_is_compared(self):
        lid = self.lessons.propose("Check the seedling beds after the shade moves.", ["seedling"], sources=[],
                                   now=T1 - 3600)
        ends = self.lessons.get(lid)["ends_at"]
        self.assertEqual(snap_mod.night_of(ends - 10), snap_mod.night_of(ends))
        one = snap_mod.take(self.db, "waterer", ends - 10)
        two = snap_mod.take(self.db, "waterer", ends)  # same state, its trial ended: a changed set
        self.assertEqual(self.live(ends), set())  # at its end the engine no longer gives it, nor does the snapshot
        self.assertTrue(two["written"])
        self.assertEqual([(e["trial"], e["live"]) for e in two["lessons"]], [(snap_mod.ENDED, False)])
        three = snap_mod.take(self.db, "waterer", ends - 5)  # the first copy's set, but not the newest copy's
        self.assertEqual((three["hash"], three["written"]), (one["hash"], True))
        self.assertEqual(snap_mod.of_night(self.db, "waterer", one["night"])["id"], three["id"])

    def test_snapshot_rows_are_never_changed_deleted_or_replaced(self):
        self.build()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never changed"), self.db.tx() as c:
            c.execute("UPDATE lesson_snapshots SET hash = 'x' WHERE id = ?", (self.first["id"],))
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never deleted"), self.db.tx() as c:
            c.execute("DELETE FROM lesson_snapshots WHERE id = ?", (self.first["id"],))
        with self.assertRaisesRegex(sqlite3.DatabaseError, "never replaced"), self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO lesson_snapshots (id, agent, kind, night, at, lessons, hash) "
                      "VALUES (?, 'waterer', 'night', ?, 0, '[]', 'x')", (self.first["id"], N1))


class TheNight(Base):
    def night(self, until):
        return night.night(self.db, self.plug, until=until, days=1, proposer=fk.Proposer(), tagger=fk.Tagger(),
                           fit=fk.Fit(), adapter=fk.Adapter(), others=[], judge=always_low)

    def test_each_night_takes_one_snapshot_after_the_study(self):
        lid = self.lessons.propose("Check the seedling beds after the shade moves.", ["seedling"], sources=[],
                                   now=T1 - 3600)
        rep = self.night(T1)
        snap = rep["snapshot"]
        self.assertEqual((snap["night"], snap["lessons"], snap["live"], snap["written"], snap["since"]), (N1, 1, 1, True, None))
        self.assertEqual(self.night(T1)["snapshot"]["written"], False)  # the same night again
        rows = self.tables()["lesson_snapshots"]
        self.assertEqual(len(rows), 1)
        text = night.text(self.night(T2), self.plug)
        self.assertEqual(len(self.tables()["lesson_snapshots"]), 2)
        self.assertIn(f"  snapshot of the night of {N2}: 1 lesson, 1 given, hash ", text)
        self.assertIn(f"; to roll back to it: python3 -I reflection/snapshots.py rollback --plug=waterer --to {N2}\n", text)
        self.assertIn(f"\n  since the night of {N1}: no change", text)
        self.assertEqual(self.lessons.get(lid)["state"], TRYING)


class TheNightRunner(NightSetup):
    def test_the_report_names_the_plug_and_database_it_ran_with_and_the_command_runs(self):
        self.env()
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        rep = json.loads(next(self.dir.glob("night-waterer-*.json")).read_text(encoding="utf-8"))
        cmd = snap_mod.command(self.plug_path, rep["snapshot"]["night"], self.db_path)
        self.assertIn(f"to roll back to it: {cmd}\n", out)
        self.assertEqual(shlex.split(cmd)[:3], ["python3", "-I", "reflection/snapshots.py"])
        r = subprocess.run([sys.executable, *shlex.split(cmd)[1:]], cwd=ROOT, capture_output=True, text=True,
                           timeout=60)  # the command as printed, from the repo, under -I
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"Rollback of waterer to the night of {rep['snapshot']['night']}", r.stdout)

    def test_the_default_database_is_not_named(self):
        self.env()
        with mock.patch.object(night, "DEFAULT_PATH", self.db_path):
            code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        rep = json.loads(next(self.dir.glob("night-waterer-*.json")).read_text(encoding="utf-8"))
        self.assertNotIn("db", rep["snapshot"])
        self.assertIn(f"to roll back to it: {snap_mod.command(self.plug_path, rep['snapshot']['night'])}\n", out)


class Rollback(Base):
    def test_without_yes_it_shows_the_plan_and_changes_nothing(self):
        ids = self.build()
        before = self.tables()
        code, out, err = self.rollback()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.tables(), before)
        for line in (f'  stays: lesson {ids["A"]} "Water the grown beds at dusk.": given that night and now',
                     f'  bring back: lesson {ids["E"]} "Visit the north bed first.": pulled since (stopped by '
                     "the owner: too slow); with --bring-back it comes back as a new lesson on trial or waiting its turn, and this "
                     "one stays pulled",
                     f'  stays: lesson {ids["B"]} "Check the seedling beds after the shade moves.": given that night '
                     "and now; kept since, it stays kept and does not go back on trial",
                     f'  pull: lesson {ids["D"]} "Wait a day between rounds on the grown beds.": it waited for a yes '
                     "that night",
                     f'  pull: lesson {ids["F"]} "Visit the grown beds last.": added after that night',
                     f'  left waiting: lesson {ids["G"]} "Leave the seedling beds for the end of the round.": added '
                     "after that night; it waits for a yes and changes nothing until a person answers",
                     f'  pull: lesson {ids["H"]} "Water the seedling beds before the sun is high.": added after that '
                     "night; it waits its turn now and would start by itself"):
            self.assertIn(line + "\n", out)
        self.assertNotIn(f"lesson {ids['C']} ", out)  # it waited its turn that night and still does
        self.assertIn("Nothing changed.", out)
        self.assertIn(f"\n  python3 -I reflection/snapshots.py rollback --plug={shlex.quote(str(self.plug_path))} --to {N1} "
                      f"--db={shlex.quote(str(self.db_path))} --yes {self.code(self.first)}\n", out)
        self.assertIn("To bring back the lessons marked bring back as well, each as a new lesson on trial or waiting its turn, run this "
                      f"instead:\n  python3 -I reflection/snapshots.py rollback --plug={shlex.quote(str(self.plug_path))} "
                      f"--to {N1} --db={shlex.quote(str(self.db_path))} --bring-back --yes {self.code(self.first)}\n", out)
        with mock.patch.object(snap_mod, "DEFAULT_PATH", self.db_path):  # the default database is not named
            self.assertIn(f" --to {N1} --yes {self.code(self.first)}\n", self.rollback()[1])

    def test_with_yes_it_restores_the_lessons_given_that_night_except_what_cannot_come_back(self):
        ids = self.build()
        self.assertEqual(self.live(), {ids[k] for k in "ABDF"})
        preview = self.rollback("--by", "Mohamed")[1]
        self.assertIn(f" --by=Mohamed --yes {self.code(self.first)}\n", preview)
        code, out, err = self.paste(preview)
        self.assertEqual((code, err), (0, ""))
        then = {e["id"] for e in self.first["lessons"] if e["live"]}
        self.assertEqual(then, {ids["A"], ids["E"], ids["B"]})
        self.assertEqual(self.live(), then - {ids["E"]})
        for k in "DFH":
            les = self.lessons.get(ids[k])
            self.assertEqual((les["state"], les["pulled_why"], les["pulled_at"]),
                             (PULLED, f"rolled back by Mohamed to the night of {N1}", T3))
        self.assertEqual(self.lessons.get(ids["G"])["state"], WAITING)
        self.assertEqual(self.lessons.waits_for(ids["C"], T3), [])
        rb, = snap_mod.rollbacks(self.db, "waterer")
        self.assertEqual((rb["kind"], rb["night"], rb["by"], rb["at"]), ("rollback", N1, "Mohamed", T3))
        self.assertEqual(rb["detail"], {"to": self.first["id"], "pulled": [ids["D"], ids["F"], ids["H"]],
                                        "brought_back": [], "offered_back": [ids["E"]], "cannot_come_back": [],
                                        "left_waiting": [ids["G"]]})
        self.assertEqual({e["id"] for e in rb["lessons"] if e["live"]}, then - {ids["E"]})
        self.assertIn(f"Done, signed by Mohamed: pulled lesson {ids['D']}, {ids['F']}, {ids['H']}. Recorded as "
                      f"snapshot {rb['id']} (rollback). Not brought back: lesson {ids['E']}; to bring it back, run the "
                      "plan again and add --bring-back.\n", out)
        self.assertEqual(self.lessons.get(ids["E"])["state"], PULLED)  # no --bring-back: it stays out
        self.assertEqual(snap_mod.latest(self.db, "waterer")["id"], self.second["id"])  # a rollback is not a night

    def test_lesson_rows_are_never_rewritten_and_snapshots_stay(self):
        ids = self.build()
        before = self.tables()
        self.assertEqual(self.paste(self.rollback()[1])[0], 0)
        after = self.tables()
        names = self._columns("lessons")
        moved = {"state", "pulled_at", "pulled_why"}
        pulled = {ids["D"], ids["F"], ids["H"]}
        self.assertEqual(len(after["lessons"]), len(before["lessons"]))
        for old, new in zip(before["lessons"], after["lessons"]):
            row_old, row_new = dict(zip(names, old)), dict(zip(names, new))
            if row_old["id"] in pulled:
                row_old = {k: v for k, v in row_old.items() if k not in moved}
                row_new = {k: v for k, v in row_new.items() if k not in moved}
            self.assertEqual(row_new, row_old)
        self.assertEqual(after["lesson_snapshots"][:2], before["lesson_snapshots"])
        self.assertEqual(len(after["lesson_snapshots"]), 3)

    def _columns(self, table):
        c = sqlite3.connect(self.db_path)
        try:
            return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
        finally:
            c.close()

    def test_a_second_rollback_with_nothing_to_pull_writes_nothing(self):
        ids = self.build()
        first = self.rollback()[1]
        self.assertEqual(self.paste(first)[0], 0)
        before = self.tables()
        code, out, _ = self.rollback()
        self.assertEqual(code, 0)
        self.assertIn("  nothing to pull: the lessons given now were all given that night\n", out)
        commands = [ln for ln in out.splitlines() if " --yes " in ln]  # nothing to pull: only the Bring back command
        self.assertEqual(len(commands), 1)
        self.assertIn(" --bring-back --yes ", commands[0])
        code, out, _ = self.rollback("--yes", self.code(self.first))
        self.assertEqual(code, 0)
        self.assertIn("  nothing to pull: the lessons given now were all given that night\n", out)
        self.assertTrue(out.endswith(f"\nNothing changed. Not brought back: lesson {ids['E']}; to bring it back, run the plan "
                                     "again and add --bring-back.\n"))
        code, out, err = self.paste(first)  # the first command again: its plan is gone
        self.assertEqual((code, out), (2, ""))
        self.assertIn("Not run: the plan changed; run it again without --yes.", err)
        self.assertEqual(self.tables(), before)

    def test_a_lesson_changed_meanwhile_undoes_the_whole_rollback(self):
        ids = self.build()

        class Flaky(Lessons):
            def pull(self, lesson_id, why="", **kw):
                if lesson_id == ids["H"]:
                    return False
                return super().pull(lesson_id, why, **kw)

        before = self.tables()
        with self.assertRaisesRegex(snap_mod.Refused, f"lesson {ids['H']} changed meanwhile"):
            snap_mod.rollback(self.db, Flaky(self.db, self.plug, judge=always_low), self.first, OWNER, T3,
                              code=self.code(self.first))
        self.assertEqual(self.tables(), before)
        self.assertIn(ids["D"], self.live())

    def test_a_snapshot_of_another_agent_is_refused(self):
        self.build()
        fan = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        with self.assertRaisesRegex(snap_mod.Refused, f"snapshot {self.first['id']} is not a night of fan"):
            snap_mod.rollback(self.db, fan, self.first, OWNER, T3, code=self.code(self.first))

    def test_a_rollback_row_is_not_a_night_to_roll_back_to(self):
        self.build()
        self.assertEqual(self.paste(self.rollback()[1])[0], 0)
        rb, = snap_mod.rollbacks(self.db, "waterer")
        before = self.tables()
        with self.assertRaisesRegex(snap_mod.Refused, f"snapshot {rb['id']} is not a night of waterer"):
            snap_mod.rollback(self.db, self.lessons, rb, OWNER, T3, code=self.code(rb))
        self.assertEqual(self.tables(), before)

    def test_a_plan_that_changed_after_the_preview_is_refused(self):
        ids = self.build()
        code, out, _ = self.rollback()
        self.assertIn(f'  left waiting: lesson {ids["G"]} ', out)
        self.assertTrue(self.lessons.approve(ids["G"], "Ziad", now=T3 - 60))  # a yes on the morning page meanwhile
        g = self.lessons.get(ids["G"])["state"]
        before = self.tables()
        code, got, err = self.paste(out)
        self.assertEqual((code, got), (2, ""))
        self.assertIn("Not run: the plan changed; run it again without --yes.", err)
        self.assertEqual(self.tables(), before)
        self.assertNotEqual(g, PULLED)
        again = self.rollback()[1]  # the new plan pulls it too, under a new code
        self.assertIn(f'  pull: lesson {ids["G"]} ', again)
        self.assertNotEqual(again.splitlines()[-1], out.splitlines()[-1])
        self.assertEqual(self.paste(again)[0], 0)
        self.assertEqual(self.lessons.get(ids["G"])["state"], PULLED)
        steps = [{"id": ids["D"], "line": "x", "do": snap_mod.PULL}]  # the code names the snapshot too, not only the pulls
        self.assertNotEqual(snap_mod.plan_code(self.first, steps), snap_mod.plan_code(self.second, steps))

    def test_a_trial_given_that_night_and_paused_or_ended_by_now_cannot_come_back(self):
        L = self.lessons
        b = L.propose("Check the seedling beds after the shade moves.", ["seedling"], sources=[], now=T1 - 3600)
        p = L.propose("Water the seedling beds before the sun is high.", ["grown"], sources=[], now=T1 - 3500)
        first = snap_mod.take(self.db, "waterer", T1)
        with self.db.tx() as c:
            self.assertTrue(L.pause(p, T1 + 3600, c=c))
            Trials(self.db, self.plug, lessons=L)._mark(c, p, "paused", value=2.0, detail={}, now=T1 + 3600)
        later = L.get(b)["ends_at"] + 60  # the plan is read at the rollback, not at the night
        steps, rid = snap_mod.rollback(self.db, L, first, OWNER, later, code=self.code(first, later))
        self.assertIsNone(rid)
        self.assertEqual([(s["id"], s["do"], s["why"]) for s in steps],
                         [(b, snap_mod.CANNOT, "its trial ended since and waits for its verdict; a trial never starts "
                                               "again"),
                          (p, snap_mod.CANNOT, "its trial was paused since; it waits for a person to keep it or pull it")])

    def test_a_lesson_given_that_night_but_not_in_this_database_is_named(self):
        self.build()
        gone = {"id": 999, "state": KEPT, "trial": None, "score": 0.0, "live": True}
        snap = dict(self.first, lessons=self.first["lessons"] + [dict(gone, id=998, state=WAITING, live=False), gone])
        with self.db.tx() as c:
            steps = snap_mod.plan(c, "waterer", snap, T3)
        self.assertEqual(steps[-1], {"id": 999, "line": "", "do": snap_mod.CANNOT, "why": "not in this database"})
        self.assertNotIn(998, [s["id"] for s in steps])
        self.assertIn("\n  cannot come back: lesson 999: not in this database", snap_mod.plan_text("waterer", snap, steps))

    def test_yes_without_the_plans_code_is_refused(self):
        self.build()
        before = self.tables()
        for extra, words in ((("--yes",), "--yes takes the code the plan printed; run it again without --yes to see it"),
                             (("--yes", "--by", "Mohamed"), "--yes takes the code the plan printed"),
                             (("--yes", "0" * 12), "the plan changed; run it again without --yes")):
            with self.subTest(extra=extra):
                code, out, err = self.rollback(*extra)
                self.assertEqual((code, out), (2, ""))
                self.assertIn(f"Not run: {words}", err)
        self.assertEqual(self.tables(), before)

    def test_a_trial_started_after_that_night_and_paused_or_ended_since_is_pulled(self):
        L = self.lessons
        a = kept_lesson(L, "Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=T1 - 7200)
        first = snap_mod.take(self.db, "waterer", T1)
        x = L.propose("Check the seedling beds after the shade moves.", ["seedling"], sources=[], now=T1 + 3600)
        y = L.propose("Water the seedling beds before the sun is high.", ["grown"], sources=[], now=T1 + 3700)
        with self.db.tx() as c:  # y paused as the stop rule does; x's trial simply ends
            self.assertTrue(L.pause(y, T1 + 7200, c=c))
            Trials(self.db, self.plug, lessons=L)._mark(c, y, "paused", value=2.0, detail={}, now=T1 + 7200)
        later = L.get(x)["ends_at"] + 60
        now = {e["id"]: (e["state"], e["trial"], e["live"]) for e in snap_mod._set(self.db.conn, "waterer", later)}
        self.assertEqual(now, {a: (KEPT, None, True), x: (TRYING, snap_mod.ENDED, False),
                               y: (TRYING, snap_mod.PAUSED, False)})
        code, out, _ = self.rollback(now=later)
        for line in (f'  pull: lesson {x} "Check the seedling beds after the shade moves.": added after that night; '
                     "its trial started since and has ended, so it could still be kept",
                     f'  pull: lesson {y} "Water the seedling beds before the sun is high.": added after that night; '
                     "its trial started since and was paused, so it could still be kept"):
            self.assertIn(line + "\n", out)
        self.assertEqual(self.paste(out, now=later)[0], 0)
        self.assertEqual({L.get(i)["state"] for i in (x, y)}, {PULLED})
        self.assertFalse(L.keep(x))  # neither its verdict nor a person can give it again
        self.assertEqual(self.live(later), {a})
        rb, = snap_mod.rollbacks(self.db, "waterer")
        self.assertEqual((rb["detail"]["to"], rb["detail"]["pulled"]), (first["id"], [x, y]))

    def test_a_lesson_that_waited_that_night_and_whose_trial_ended_since_is_pulled(self):
        ids = self.build()  # D waited for a yes on night 1; C waited its turn behind B
        L = self.lessons
        L.start_turns(now=T2 + 60)
        self.assertEqual(L.get(ids["C"])["state"], TRYING)
        later = max(L.get(ids[k])["ends_at"] for k in "CD") + 60
        code, out, _ = self.rollback(now=later)
        for line in (f'  pull: lesson {ids["C"]} "Visit the seedling beds after the grown beds.": it waited its turn '
                     "that night; a lesson never goes back to waiting; its trial started since and has ended, so it "
                     "could still be kept",
                     f'  pull: lesson {ids["D"]} "Wait a day between rounds on the grown beds.": it waited for a yes '
                     "that night; its trial started since and has ended, so it could still be kept"):
            self.assertIn(line + "\n", out)

    def test_the_printed_command_runs_with_a_signer_that_starts_with_a_dash(self):
        ids = self.build()
        preview = self.rollback("--by=-Ziad M")[1]
        self.assertIn(f" --by='-Ziad M' --yes {self.code(self.first)}\n", preview)
        code, out, err = self.paste(preview)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Done, signed by -Ziad M: pulled lesson", out)
        self.assertEqual(self.lessons.get(ids["F"])["state"], PULLED)

    def test_the_code_names_the_lines_and_the_snapshot_not_only_the_ids(self):
        self.build()
        steps = [{"id": 5, "line": "a", "do": snap_mod.PULL}]
        code = snap_mod.plan_code(self.first, steps)
        self.assertNotEqual(code, snap_mod.plan_code(self.first, [dict(steps[0], line="b")]))
        for key, value in (("agent", "other"), ("night", "2027-01-01"), ("hash", "0" * 64)):
            self.assertNotEqual(code, snap_mod.plan_code(dict(self.first, **{key: value}), steps), key)


class OneWriter(Base):
    """take() and rollback() read the lessons under the write lock: no one writes between the
    read and the write."""

    def locked(self):
        """True when a second connection cannot start writing now."""
        other = sqlite3.connect(self.db_path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            return False
        except sqlite3.OperationalError as e:
            self.assertIn("locked", str(e))
            return True
        finally:
            other.close()

    def spy(self, name, seen):
        real = getattr(snap_mod, name)

        def wrapped(*a, **kw):
            seen.append(self.locked())
            return real(*a, **kw)
        return mock.patch.object(snap_mod, name, wrapped)

    def test_take_reads_the_lessons_under_the_write_lock(self):
        kept_lesson(self.lessons, "Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=T1 - 60)
        seen = []
        with self.spy("_set", seen):
            self.assertTrue(snap_mod.take(self.db, "waterer", T1)["written"])
        self.assertEqual(seen, [True])

    def test_rollback_reads_its_plan_under_the_write_lock(self):
        self.build()
        code, seen = self.code(self.first), []
        with self.spy("plan", seen):
            self.assertIsNotNone(snap_mod.rollback(self.db, self.lessons, self.first, OWNER, T3, code=code)[1])
        self.assertEqual(seen, [True])
        self.assertFalse(self.locked())  # and lets go of it after


class Refuses(Base):
    def assert_refused(self, words, *extra, **kw):
        self.build()
        before = self.tables()
        code, out, err = self.rollback("--yes", self.code(self.first), *extra, **kw)
        self.assertEqual((code, out), (2, ""))
        self.assertIn(words, err)
        self.assertEqual(self.tables(), before)

    def test_an_unknown_plug(self):
        self.assert_refused("no plug 'gardener': neither a plug file nor an agent in this repo", plug="gardener")

    def test_a_plug_named_by_its_agent_in_the_repo_is_found(self):
        self.build()
        code, out, _ = self.rollback(plug="waterer")
        self.assertEqual(code, 0)
        self.assertIn("Rollback of waterer", out)

    def test_another_agent_with_no_snapshot(self):
        fan = self.dir / "fan.json"
        fan.write_text(json.dumps(plugs.FAN), encoding="utf-8")
        self.assert_refused("no snapshot of fan on the night of", plug=fan)

    def test_an_unknown_night(self):
        self.assert_refused(f"no snapshot of waterer on the night of 2020-01-01; nights with one: {N2}, {N1}",
                            to="2020-01-01")

    def test_a_night_that_is_not_a_date(self):
        for bad in ("yesterday", "2026-02-30", "20261028", f"{N1} "):
            with self.subTest(night=bad):
                code, _, err = self.rollback(to=bad)
                self.assertEqual(code, 2)
                self.assertIn("is not a night", err)

    def test_a_signature_that_is_not_one_line(self):
        self.build()
        before = self.tables()
        for bad in ("Mo\nhamed", "Mo\rhamed", "  "):
            with self.subTest(by=bad):
                code, out, err = self.rollback("--yes", self.code(self.first), "--by", bad)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("--by is one line of text", err)
        self.assertEqual(self.tables(), before)

    def test_a_snapshot_that_no_longer_matches_its_hash(self):
        self.build()
        c = sqlite3.connect(self.db_path)
        c.execute("DROP TRIGGER lesson_snapshots_never_changed")
        c.execute("UPDATE lesson_snapshots SET lessons = '[]' WHERE id = ?", (self.first["id"],))
        c.commit()
        c.close()
        before = self.tables()
        code, _, err = self.rollback("--yes", "0" * 12)
        self.assertEqual(code, 2)
        self.assertIn(f"snapshot {self.first['id']} no longer matches its hash", err)
        self.assertEqual(self.tables(), before)

    def test_no_database(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = snap_mod.main(["rollback", "--plug", str(self.plug_path), "--to", N1, "--db",
                                  str(self.dir / "none.db")], now=T3, root=self.dir)
        self.assertEqual(code, 2)
        self.assertIn("no database at", err.getvalue())
        self.assertFalse((self.dir / "none.db").exists())


class TheMorningPage(Base):
    def test_each_agent_names_its_latest_snapshot_and_how_to_roll_back(self):
        self.build()
        page = morning.Morning(self.db, [self.plug])
        a, = page.view(now=T3)["agents"]
        self.assertEqual(a["snapshot"]["night"], N2)
        html = morning.render(page.view(now=T3))
        self.assertIn(f'<p class="meta">Latest snapshot: the night of {N2}, 8 lessons, 4 given (hash '
                      f'{self.second["hash"][:12]}). To roll back to it: <code>python3 -I reflection/snapshots.py '
                      f"rollback --plug=waterer --to {N2}</code></p>", html)
        other = morning.Morning(self.db, [], db_file="/tmp/a b.db").view(now=T3)["agents"][0]["snapshot"]
        self.assertIsNone(other["command"])  # no plug in the repo: no command
        self.assertEqual(morning.Morning(self.db, [self.plug], db_file="/x/a b.db").view(now=T3)["agents"][0]
                         ["snapshot"]["command"], f"python3 -I reflection/snapshots.py rollback --plug=waterer --to {N2} "
                                                  "--db='/x/a b.db'")

    def test_the_page_names_the_database_only_when_it_is_not_the_default(self):
        self.build()
        page = self.dir / "page.html"
        for default, tail in ((self.db_path, ""), (self.dir / "other.db", f" --db={shlex.quote(str(self.db_path))}")):
            with self.subTest(default=default), mock.patch.object(morning, "DEFAULT_PATH", default), \
                    mock.patch.object(morning, "repo_plugs", return_value=[self.plug]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(morning.main(["--db", str(self.db_path), "--html", str(page)]), 0)
                self.assertIn(f"<code>python3 -I reflection/snapshots.py rollback --plug=waterer --to {N2}{tail}</code>",
                              page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
