"""The night scheduler (reflection/scheduler.py): each agent's night once a night, by itself.
A fake clock and a fake night run: nothing sleeps, no night really runs, no server starts."""
import os
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from kit.db import Db
from reflection import scheduler as sc

CAIRO = ZoneInfo("Africa/Cairo")
WHEN = (3, CAIRO)
AGENTS = [("alpha", Path("alpha/plug.json")), ("beta", Path("beta/plug.json")), ("gamma", Path("gamma/plug.json"))]
HOUR = 3600.0


def at(y, m, d, h=0, mi=0, zone=CAIRO):
    return datetime(y, m, d, h, mi, tzinfo=zone).timestamp()


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Runs:
    """The fake night: records (agent folder, db path, now); answers by agent."""

    def __init__(self, answers=None):
        self.calls, self.answers = [], answers or {}

    def __call__(self, path, db_path, now):
        agent = Path(path).parent.name
        self.calls.append((agent, db_path, now))
        answer = self.answers.get(agent, 0)
        if callable(answer):
            return answer()
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def agents(self):
        return [a for a, _, _ in self.calls]


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.clock = Clock(at(2026, 11, 10, 3, 0))

    def make(self, runs=None, find=None, holder="here", when=WHEN, **kw):
        return sc.Scheduler(self.db, "/fake/ascent.db", when=when, run=runs or Runs(), clock=self.clock,
                            find=find or (lambda: list(AGENTS)), holder=holder, **kw)

    def lock_row(self):
        with self.db.tx() as c:
            r = c.execute("SELECT holder, at FROM night_lock").fetchone()
            return None if r is None else (r["holder"], r["at"])

    def states(self, s, night=None):
        return {r["agent"]: r["state"] for r in s.runs(night)}


class Settings(unittest.TestCase):
    def read(self, hour="", tz=""):
        return sc.settings({sc.HOUR_ENV: hour, sc.TZ_ENV: tz}.get)

    def test_defaults(self):
        hour, zone = self.read()
        self.assertEqual((hour, zone.key), (3, "Africa/Cairo"))

    def test_given(self):
        hour, zone = self.read("22", "Europe/London")
        self.assertEqual((hour, zone.key), (22, "Europe/London"))
        self.assertEqual(self.read("0")[0], 0)
        self.assertEqual(self.read(" 07 ")[0], 7)

    def test_off(self):
        for raw in ("off", "OFF", " Off "):
            self.assertIsNone(self.read(raw), raw)

    def test_bad_hour_is_the_default_and_said(self):
        for raw in ("24", "-1", "3.5", "three", "²", "٣", "100", "3pm"):
            with self.assertLogs("scheduler", "WARNING") as logs:
                hour, zone = self.read(raw)
            self.assertEqual(hour, sc.HOUR_DEFAULT, raw)
            self.assertIn(sc.HOUR_ENV, logs.output[0])

    def test_bad_zone_is_the_default_and_said(self):
        for raw in ("Not/AZone", "../etc/passwd", "America", "Africa/Cairo\x00", "/etc/localtime"):
            with self.assertLogs("scheduler", "WARNING") as logs:
                hour, zone = self.read("4", raw)
            self.assertEqual((hour, zone.key), (4, "Africa/Cairo"), raw)
            self.assertIn(sc.TZ_ENV, logs.output[0])

    def test_reads_the_env_when_not_given(self):
        with mock.patch.dict(os.environ, {sc.HOUR_ENV: "5", sc.TZ_ENV: "Asia/Dubai"}):
            hour, zone = sc.settings()
        self.assertEqual((hour, zone.key), (5, "Asia/Dubai"))
        with mock.patch.dict(os.environ, {sc.HOUR_ENV: "off"}):
            self.assertIsNone(sc.settings())


class DueNight(unittest.TestCase):
    def test_before_and_from_the_hour(self):
        self.assertEqual(sc.due_night(at(2026, 11, 10, 2, 59), *WHEN), "2026-11-09")
        self.assertEqual(sc.due_night(at(2026, 11, 10, 3, 0), *WHEN), "2026-11-10")
        self.assertEqual(sc.due_night(at(2026, 11, 10, 23, 59), *WHEN), "2026-11-10")
        self.assertEqual(sc.due_night(at(2026, 7, 1, 2, 59), *WHEN), "2026-06-30")  # summer time
        self.assertEqual(sc.due_night(at(2026, 7, 1, 3, 0), *WHEN), "2026-07-01")

    def test_across_the_clock_changes_no_night_is_skipped_or_doubled(self):
        for hour in (0, 1, 3, 23):
            for start in (datetime(2026, 4, 20, tzinfo=ZoneInfo("UTC")), datetime(2026, 10, 25, tzinfo=ZoneInfo("UTC"))):
                t0 = start.timestamp()
                nights = [sc.due_night(t0 + i * 600, hour, CAIRO) for i in range(12 * 24 * 6)]  # every 10 minutes, 12 days
                seen = list(dict.fromkeys(nights))
                days = [datetime.fromisoformat(n).date() for n in seen]
                self.assertEqual(days, [days[0] + timedelta(days=i) for i in range(len(days))], (hour, start))
                self.assertEqual(nights, sorted(nights))


class OncePerNight(Base):
    def test_each_agent_once_then_nothing_until_the_next_night(self):
        runs = Runs()
        s = self.make(runs)
        rep = s.once()
        self.assertEqual(rep["night"], "2026-11-10")
        self.assertEqual(rep["ran"], {"alpha": sc.DONE, "beta": sc.DONE, "gamma": sc.DONE})
        self.assertEqual(runs.agents(), ["alpha", "beta", "gamma"])
        self.assertEqual({c[1] for c in runs.calls}, {"/fake/ascent.db"})
        self.assertEqual({c[2] for c in runs.calls}, {self.clock.t})
        for minutes in (1, 60, 20 * 60):
            self.clock.t = at(2026, 11, 10, 3, 0) + minutes * 60
            self.assertEqual(s.once()["ran"], {})
        self.clock.t = at(2026, 11, 11, 2, 59)
        self.assertEqual(s.once()["ran"], {})
        self.clock.t = at(2026, 11, 11, 3, 0)
        self.assertEqual(s.once()["night"], "2026-11-11")
        self.assertEqual(runs.agents(), ["alpha", "beta", "gamma"] * 2)
        rows = s.runs()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["state"] == sc.DONE and r["ended_at"] is not None and r["why"] is None for r in rows))

    def test_a_restart_does_not_run_the_night_again(self):
        self.make(Runs(), holder="first").once()
        again = Runs()
        self.clock.t += 5 * 60
        rep = self.make(again, holder="second").once()
        self.assertEqual((rep["ran"], again.calls), ({}, []))

    def test_an_agent_added_later_runs_that_night_alone(self):
        found = list(AGENTS[:2])
        runs = Runs()
        s = self.make(runs, find=lambda: list(found))
        s.once()
        found.append(AGENTS[2])
        self.clock.t += HOUR
        self.assertEqual(s.once()["ran"], {"gamma": sc.DONE})
        self.assertEqual(runs.agents(), ["alpha", "beta", "gamma"])

    def test_no_agents_takes_no_lock(self):
        rep = self.make(find=lambda: []).once()
        self.assertEqual((rep["ran"], rep["locked"], self.lock_row()), ({}, False, None))


class MissedNights(Base):
    def test_a_service_down_at_the_hour_runs_the_night_once_when_back(self):
        runs = Runs()
        s = self.make(runs)
        self.clock.t = at(2026, 11, 10, 3, 0)
        s.once()
        self.clock.t = at(2026, 11, 13, 10, 30)  # down for the nights of the 11th and 12th
        rep = self.make(runs, holder="back").once()
        self.assertEqual(rep["night"], "2026-11-13")
        self.assertEqual(len(rep["ran"]), 3)
        self.assertEqual(sorted({r["night"] for r in s.runs()}), ["2026-11-10", "2026-11-13"])
        self.clock.t = at(2026, 11, 14, 2, 0)
        self.assertEqual(s.once()["ran"], {})

    def test_started_before_the_hour_runs_the_night_before(self):
        self.clock.t = at(2026, 11, 10, 1, 0)
        rep = self.make().once()
        self.assertEqual(rep["night"], "2026-11-09")
        self.assertEqual(len(rep["ran"]), 3)


class Failures(Base):
    def test_one_agents_failure_never_stops_the_others(self):
        runs = Runs({"alpha": ValueError("boom"), "beta": 2})
        with self.assertLogs("scheduler", "INFO"):
            rep = self.make(runs).once()
        self.assertEqual(runs.agents(), ["alpha", "beta", "gamma"])
        self.assertEqual(rep["ran"], {"alpha": sc.FAILED, "beta": sc.FAILED, "gamma": sc.DONE})
        why = {r["agent"]: r["why"] for r in self.make(runs).runs()}
        self.assertEqual(why, {"alpha": "ValueError", "beta": "exit 2", "gamma": None})
        self.assertIsNone(self.lock_row())

    def test_a_refusal_that_exits_is_a_failure_not_a_dead_thread(self):
        runs = Runs({"alpha": SystemExit(2)})
        with self.assertLogs("scheduler", "ERROR"):
            rep = self.make(runs).once()
        self.assertEqual(rep["ran"]["alpha"], sc.FAILED)
        self.assertEqual(rep["ran"]["beta"], sc.DONE)

    def test_a_failed_night_is_not_tried_again_that_night(self):
        runs = Runs({"beta": 1})
        s = self.make(runs)
        s.once()
        self.clock.t += HOUR
        self.assertEqual(s.once()["ran"], {})
        self.assertEqual(runs.agents().count("beta"), 1)


class CrashedRun(Base):
    def crash(self, holder="gone"):
        """A run that started and never ended: its row says running and its lock stays."""
        s = self.make(holder=holder)
        self.assertTrue(s._lock(self.clock.t))
        self.assertTrue(s._claim("alpha", "2026-11-10", self.clock.t))
        return s

    def test_left_behind_it_is_not_run_again_and_ends_stopped_after_stale(self):
        self.crash()
        runs = Runs()
        self.clock.t += HOUR
        s = self.make(runs)
        self.assertTrue(s.once()["locked"])  # the crashed process's lock still holds
        self.assertEqual(runs.calls, [])
        self.assertEqual(self.states(s)["alpha"], sc.RUNNING)
        self.clock.t = at(2026, 11, 10, 3, 0) + sc.STALE
        rep = s.once()
        self.assertFalse(rep["locked"])
        self.assertEqual(runs.agents(), ["beta", "gamma"])
        row = [r for r in s.runs() if r["agent"] == "alpha"][0]
        self.assertEqual((row["state"], row["why"]), (sc.STOPPED, "started and never ended"))
        self.assertIsNone(self.lock_row())

    def test_a_late_end_never_overwrites_stopped(self):
        s = self.crash(holder="slow")
        self.clock.t += sc.STALE + 1
        s._stop_stale(self.clock.t)
        s._end("alpha", "2026-11-10", sc.DONE, None)
        self.assertEqual(self.states(s)["alpha"], sc.STOPPED)


class Lock(Base):
    def take(self, holder, when):
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO night_lock (id, holder, at) VALUES (1, ?, ?)", (holder, when))

    def test_held_by_another_nothing_runs_and_nothing_is_claimed(self):
        s = self.make()
        self.take("other", self.clock.t - 60)
        runs = Runs()
        s.run = runs
        rep = s.once()
        self.assertTrue(rep["locked"])
        self.assertEqual((runs.calls, s.runs()), ([], []))
        self.assertEqual(self.lock_row(), ("other", self.clock.t - 60))

    def test_a_stale_lock_is_taken_over(self):
        s = self.make()
        self.take("other", self.clock.t - sc.STALE)
        rep = s.once()
        self.assertFalse(rep["locked"])
        self.assertEqual(len(rep["ran"]), 3)
        self.assertIsNone(self.lock_row())

    def test_a_lock_just_younger_than_stale_holds(self):
        s = self.make()
        self.take("other", self.clock.t - sc.STALE + 1)
        self.assertTrue(s.once()["locked"])

    def test_held_while_each_night_runs_refreshed_and_let_go_after(self):
        seen = []
        s = self.make()

        def look():
            seen.append(self.lock_row())
            self.clock.t += 600
            return 0
        s.run = Runs({a: look for a, _ in AGENTS})
        start = self.clock.t
        s.once()
        self.assertEqual(seen, [("here", start), ("here", start + 600), ("here", start + 1200)])
        self.assertIsNone(self.lock_row())

    def test_a_shorter_stale_is_kept(self):
        s = self.make(stale=60)
        self.take("other", self.clock.t - 61)
        self.assertFalse(s.once()["locked"])

    def test_lock_lost_mid_night_stops_the_rest_and_leaves_the_new_holder(self):
        s = self.make()

        def taken_over():
            self.take("other", self.clock.t)
            return 0
        runs = Runs({"alpha": taken_over})
        s.run = runs
        rep = s.once()
        self.assertEqual(runs.agents(), ["alpha"])
        self.assertEqual(rep["ran"], {"alpha": sc.DONE})
        self.assertEqual(self.lock_row(), ("other", self.clock.t))
        self.assertEqual(set(self.states(s)), {"alpha"})

    def test_own_lock_left_by_this_process_is_taken_again(self):
        s = self.make()
        self.take("here", self.clock.t - 10)
        self.assertFalse(s.once()["locked"])


class Off(Base):
    def test_off_runs_nothing(self):
        runs = Runs()
        s = self.make(runs, when=None)
        self.assertEqual(s.once(), {"night": None, "ran": {}, "locked": False})
        self.assertEqual(runs.calls, [])

    def test_start_off_starts_no_thread(self):
        with mock.patch.dict(os.environ, {sc.HOUR_ENV: "off"}), \
                mock.patch.object(sc.threading, "Thread") as thread, self.assertLogs("scheduler", "INFO"):
            self.assertIsNone(sc.start(self.db, ":memory:"))
        thread.assert_not_called()

    def test_start_that_cannot_set_up_returns_none(self):
        with mock.patch.object(sc, "Scheduler", side_effect=RuntimeError("no")), self.assertLogs("scheduler", "ERROR"):
            self.assertIsNone(sc.start(self.db, ":memory:"))

    def test_start_runs_the_loop_on_a_daemon_thread(self):
        got = []
        stop = threading.Event()
        with mock.patch.dict(os.environ, {sc.HOUR_ENV: "4", sc.TZ_ENV: "Asia/Dubai"}), \
                mock.patch.object(sc.Scheduler, "loop", lambda self, st: got.append((self.when[0], self.when[1].key, st))):
            thread = sc.start(self.db, ":memory:", stop=stop)
            thread.join(5)
        self.assertTrue(thread.daemon)
        self.assertFalse(thread.is_alive())
        self.assertEqual(got, [(4, "Asia/Dubai", stop)])


class Loop(Base):
    class Stop:
        """wait() answers from a list: False goes on, True stops. It never sleeps."""

        def __init__(self, answers):
            self.answers, self.waits = list(answers), []

        def wait(self, every):
            self.waits.append(every)
            return self.answers.pop(0)

    def test_stop_already_set_runs_once_and_returns(self):
        runs = Runs()
        s = self.make(runs)
        stop = threading.Event()
        stop.set()
        s.loop(stop, every=3600)
        self.assertEqual(runs.agents(), ["alpha", "beta", "gamma"])

    def test_ticks_until_stopped(self):
        s = self.make()
        looks = []
        s.once = lambda: looks.append(1)
        stop = self.Stop([False, False, True])
        s.loop(stop, every=7)
        self.assertEqual((len(looks), stop.waits), (3, [7, 7, 7]))

    def test_a_look_that_fails_is_logged_and_the_next_one_tries(self):
        s = self.make()
        calls = []

        def once():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("db gone")
        s.once = once
        with self.assertLogs("scheduler", "ERROR"):
            s.loop(self.Stop([False, True]), every=1)
        self.assertEqual(len(calls), 2)

    def test_default_tick(self):
        s = self.make()
        s.once = lambda: None
        stop = self.Stop([True])
        s.loop(stop)
        self.assertEqual(stop.waits, [sc.TICK])


class Agents(unittest.TestCase):
    def test_the_repo_plugs_by_name(self):
        names = [a for a, _ in sc.agents(":memory:")]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 3)
        for _, path in sc.agents(":memory:"):
            self.assertEqual(path.name, "plug.json")
            self.assertTrue(path.is_file())

    def test_a_plug_that_does_not_load_is_left_out(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken").mkdir()
            (Path(tmp) / "broken" / "plug.json").write_text("{not json", encoding="utf-8")
            good = sc.ROOT / "sales" / "plug.json"
            (Path(tmp) / "good").mkdir()
            (Path(tmp) / "good" / "plug.json").write_text(good.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertLogs("scheduler", "WARNING"):
                out = sc.agents(None, root=tmp)
        self.assertEqual([p.parent.name for _, p in out], ["good"])

    def test_built_agents_after_the_repo_ones_and_no_name_twice(self):
        repo = sc.agents(":memory:")
        first = repo[0][0]
        built = [mock.Mock(folder=Path("/x/agents/new_one")), mock.Mock(folder=Path("/x/agents/dup"))]
        built[0].name, built[1].name = "new_one", first
        with mock.patch("kit.turn.built", return_value=built) as b:
            out = sc.agents("/x/ascent.db")
        b.assert_called_once()
        self.assertEqual(out, repo + [("new_one", Path("/x/agents/new_one/plug.json"))])

    def test_built_agents_that_break_leave_the_repo_ones(self):
        with mock.patch("kit.turn.built", side_effect=OSError("gone")), self.assertLogs("scheduler", "WARNING"):
            out = sc.agents("/x/ascent.db")
        self.assertEqual(out, sc.agents(":memory:"))

    def test_run_night_is_the_manual_command(self):
        with mock.patch("reflection.night.main", return_value=0) as main:
            self.assertEqual(sc.run_night(Path("a/plug.json"), "/d/ascent.db", 123.0), 0)
        main.assert_called_once_with(["--plug", "a/plug.json", "--db", "/d/ascent.db"], until=123.0)


class Channel(unittest.TestCase):
    """channels/whatsapp.py starts the scheduler and goes on whatever it does."""

    def test_start_nights_hands_over(self):
        from channels import whatsapp
        with mock.patch.object(sc, "start", return_value="thread") as start:
            self.assertEqual(whatsapp.start_nights("db", "path"), "thread")
        start.assert_called_once_with("db", "path")

    def test_start_nights_never_raises(self):
        from channels import whatsapp
        with mock.patch.object(sc, "start", side_effect=RuntimeError("no")), \
                self.assertLogs("channels.whatsapp", "ERROR"):
            self.assertIsNone(whatsapp.start_nights("db", "path"))

    def test_main_calls_it_after_the_workers(self):
        import inspect
        from channels import whatsapp
        src = inspect.getsource(whatsapp.main)
        self.assertIn("start_nights(db, DEFAULT_PATH)", src)
        self.assertLess(src.index("app.sweep_fast"), src.index("start_nights("))
        self.assertLess(src.index("start_nights("), src.index("serve_forever"))


if __name__ == "__main__":
    unittest.main()
