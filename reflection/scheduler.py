"""The night scheduler: each agent's night study (reflection/night.py) once a night, by itself.

Where it runs. It starts with the WhatsApp channel's server (channels/whatsapp.py main), as one
more thread next to its quiet tick. That is the one process that runs all the time (Meta must
always reach it); the morning page is started by a person and stopped with Ctrl+C, and the
delivery webhook is optional, so neither is a home a night can count on. When the scheduler
cannot start, the server still answers customers and the log says why.

When. NIGHT_HOUR (a whole hour, 0 to 23, default 3) in NIGHT_TZ (default Africa/Cairo).
NIGHT_HOUR=off turns it off; a value it cannot read is the default, said in the log. A night is
named by its date in NIGHT_TZ: from NIGHT_HOUR on a date, that date's night is due. Every TICK
seconds it looks: each agent whose due night has no record yet runs it now. So a service that was
down at that hour runs the night once when it is back, and older missed nights are not made up.

Once per night per agent, in the database. Before an agent's night starts, a row (agent, night)
goes into night_runs in one statement that adds it only when none is there: a restart, a second
process or a second tick never runs that night again, even after a crash part way. The row ends
done, failed with why (the night's exit code, timeout, or the error's type), or, when a run that started
never ended (a crash), stopped once it is older than STALE.

One lock. A second service on the same database never runs nights at the same time: the night_lock
row is taken in one statement only when it is free, already this process's, or older than STALE,
refreshed before each agent and let go after. A crash leaves it behind, and after STALE the next
tick takes it over, so it is never stuck. STALE is longer than a night should ever take.

One agent's failure is its own. Each agent's night runs on its own: a refusal (a missing key, a
missing database) or an error is recorded for that agent and the next one runs; nothing here ever
stops the service.

Its own process. Each night runs as the manual command in a child process (run_night), from the
repo root, so what a night changes for itself (the exam's demo store, its env, logging and the
store's cache) never reaches the server's live turns. The child has LIMIT seconds, under STALE, held
on both sides. The scheduler kills one still running then and records it failed, "timeout", so a
stuck call never holds the scheduler's thread and no second runner takes over a night that still
runs. The child, given the limit on its command line (--limit), ends itself at that limit and as
soon as the pipe from the server closes (guard), so a server that stops mid night, however it
stops, never leaves a night running with no limit. Its printed lines go to NIGHTS_LOG next to the
database.

The night itself asks the courier's API first (reflection/night.py courier_check), so the results
it brings count that night.

The agents. Every plug in the repo (<folder>/plug.json) and every agent Quick start built next to
the database (kit/turn.py built), by name, one run each, in that order.

The manual night command (python3 -m reflection.night) is the same command: run by hand it records
nothing here, so a manual run never stops the scheduled one.
"""
import logging
import math
import os
import re
import signal
import stat
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("scheduler")

ROOT = Path(__file__).resolve().parent.parent
HOUR_ENV, TZ_ENV = "NIGHT_HOUR", "NIGHT_TZ"
HOUR_DEFAULT, TZ_DEFAULT = 3, "Africa/Cairo"
OFF = "off"
TICK = 60.0                  # seconds between looks
STALE = 6 * 3600.0           # seconds: a lock or a started run this old is a crash's
LIMIT = 5 * 3600.0           # seconds a night's child process may run before it is killed
NIGHTS_LOG = "nights.log"    # next to the database: what each night's child printed
NIGHTS_LOG_MAX = 5 * 1024 * 1024  # bytes; past it the log starts again, the last one kept as nights.log.1
TIMEOUT = "timeout"
RUNNING, DONE, FAILED, STOPPED = "running", "done", "failed", "stopped"
HOUR_FORM = re.compile(r"[0-9]{1,2}")
FROM_ENV = object()            # Scheduler(when=...) left out: read NIGHT_HOUR and NIGHT_TZ

SCHEMA = """
CREATE TABLE IF NOT EXISTS night_runs (
    agent TEXT NOT NULL,
    night TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    why TEXT,
    PRIMARY KEY (agent, night)
);
CREATE TABLE IF NOT EXISTS night_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    holder TEXT NOT NULL,
    at REAL NOT NULL
);
"""


def settings(get=None):
    """(hour, zone) from NIGHT_HOUR and NIGHT_TZ, or None when NIGHT_HOUR is off. A value that
    cannot be read is the default, and the log says which."""
    if get is None:
        from kit import env
        get = env.get
    raw_hour, raw_tz = (get(HOUR_ENV) or "").strip(), (get(TZ_ENV) or "").strip()
    if raw_hour.lower() == OFF:
        return None
    hour = HOUR_DEFAULT
    if raw_hour:
        if HOUR_FORM.fullmatch(raw_hour) and 0 <= int(raw_hour) <= 23:
            hour = int(raw_hour)
        else:
            log.warning("%s is not a whole hour from 0 to 23; the night runs at %d", HOUR_ENV, HOUR_DEFAULT)
    zone = ZoneInfo(TZ_DEFAULT)
    if raw_tz:
        try:
            zone = ZoneInfo(raw_tz)
        except Exception:  # not found (a KeyError), a bad key (ValueError), a folder (OSError)
            log.warning("%s is not a time zone this computer knows; the night runs in %s", TZ_ENV, TZ_DEFAULT)
    return hour, zone


def due_night(now, hour, zone):
    """The night due at now: its date in zone, the day before before hour."""
    local = datetime.fromtimestamp(now, zone)
    day = local.date() if local.hour >= hour else local.date() - timedelta(days=1)
    return day.isoformat()


def agents(db_path, root=ROOT):
    """[(agent name, plug path)]: the repo's plugs, then each agent Quick start built next to the
    database; a name already listed is left out."""
    from engine import plug as plug_mod
    out, seen = [], set()
    for path in sorted(Path(root).glob("*/plug.json")):
        try:
            name = plug_mod.load(path).agent
        except Exception as e:  # one plug that does not load never stops the others
            log.warning("plug %s left out of the night: %s", path.parent.name, type(e).__name__)
            continue
        if name not in seen:
            out.append((name, path))
            seen.add(name)
    if db_path is not None and str(db_path) != ":memory:":
        from kit import turn
        try:
            built = turn.built(Path(db_path).resolve().parent)
        except Exception as e:  # the repo's agents still run
            log.warning("built agents left out of the night: %s", type(e).__name__)
            built = []
        for agent in built:
            if agent.name not in seen:
                out.append((agent.name, agent.folder / "plug.json"))
                seen.add(agent.name)
    return out


class TimedOut(Exception):
    """A night's child process ran past its limit and was killed."""


def run_night(plug_path, db_path, now, *, limit=LIMIT, module="reflection.night"):
    """One agent's night, the manual command (reflection/night.py main) in a child process from the
    repo root, given limit (--limit) and a pipe from this process on its stdin, which nothing writes
    to: the child ends itself at limit or when the pipe closes (guard). Its exit code; TimedOut when
    it ran past limit seconds, killed here or by its own alarm. module: the command to run (the
    tests give a small stand in)."""
    cmd = [sys.executable, "-m", module, "--plug", str(plug_path), "--db", str(db_path), "--until", repr(float(now)),
           "--limit", repr(float(limit))]
    with _output(db_path) as out:
        child = subprocess.Popen(cmd, cwd=str(ROOT), stdin=subprocess.PIPE, stdout=out, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            code = child.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            _kill(child)
            raise TimedOut(f"past {limit:g} seconds") from None
        except BaseException:  # the server is stopping: no night outlives it
            _kill(child)
            raise
        finally:
            child.stdin.close()
    if code == -signal.SIGALRM:  # the child's own limit came first
        raise TimedOut(f"past {limit:g} seconds, ended by its own limit")
    return code


def guard(limit, fd=0):
    """The child's own end, called first by a night the scheduler started (reflection/night.py
    --limit): SIGALRM at limit seconds, rounded up, whose default action ends the process wherever
    it is; and a watcher thread on the pipe from the server (stdin's descriptor, read raw, so the
    thread never holds a lock the interpreter needs at exit), which ends the child once the pipe
    closes. The server never writes to it, so it closes only when the server's end does: the server
    stopped, however it stopped. Only a pipe is watched: a night run by hand with --limit and stdin
    from a file or /dev/null keeps the alarm alone. Call it from the main thread."""
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(max(1, math.ceil(float(limit))))
    try:
        piped = stat.S_ISFIFO(os.fstat(fd).st_mode)
    except OSError:
        piped = False
    if piped:
        threading.Thread(target=_watch, args=(fd,), daemon=True, name="server-pipe").start()


def _watch(fd):
    """Read the pipe until it closes, then end this process and its group when it leads one (the
    scheduler starts the child in its own session)."""
    try:
        while os.read(fd, 4096):
            pass
    except OSError:  # a descriptor that cannot be read: no server to wait on
        pass
    pid = os.getpid()
    if os.getpgrp() == pid:
        os.killpg(pid, signal.SIGKILL)
    os.kill(pid, signal.SIGKILL)


def _output(db_path):
    """Where a night's child prints: NIGHTS_LOG next to the database, added to, readable by this
    user only (it names cases); past NIGHTS_LOG_MAX it moves to nights.log.1 and starts again;
    nowhere when that cannot be opened or is a link."""
    path = Path(db_path).resolve().parent / NIGHTS_LOG
    try:
        if path.is_file() and path.stat().st_size > NIGHTS_LOG_MAX:
            os.replace(path, path.with_name(NIGHTS_LOG + ".1"))
        return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600), "ab")
    except OSError:
        return open(os.devnull, "wb")


def _kill(child):
    """The child and anything it started, killed and waited for."""
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except OSError:  # already gone
        pass
    child.kill()
    child.wait()


class Scheduler:
    """The nights for one database. when: (hour, zone), None for off, read from the env when
    left out. run(plug path, db path, now) -> exit code runs one night; clock() -> now; find() ->
    [(agent, plug path)]. The tests give them, so nothing sleeps and no night really runs."""

    def __init__(self, db, db_path, *, when=FROM_ENV, run=None, clock=time.time, find=None, stale=STALE, holder=None):
        self.db, self.db_path = db, db_path
        self.when = settings() if when is FROM_ENV else when  # None: off
        self.run = run or run_night
        self.clock = clock
        self.find = find or (lambda: agents(db_path))
        self.stale = float(stale)
        self.holder = holder or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.db.script(SCHEMA)

    def once(self):
        """One look: run each agent's due night that has no record yet. Returns {night, ran:
        {agent: state}, locked}; never raises for one agent's failure."""
        if self.when is None:
            return {"night": None, "ran": {}, "locked": False}
        now = self.clock()
        night = due_night(now, *self.when)
        self._stop_stale(now)
        todo = [(a, p) for a, p in self.find() if not self._had(a, night)]
        rep = {"night": night, "ran": {}, "locked": False}
        if not todo:
            return rep
        if not self._lock(now):
            rep["locked"] = True
            return rep
        try:
            for agent, path in todo:
                if not self._lock(self.clock()) or not self._claim(agent, night, self.clock()):
                    continue
                try:
                    code = self.run(path, self.db_path, self.clock())
                    state, why = (DONE, None) if code == 0 else (FAILED, f"exit {code}")
                except TimedOut:
                    state, why = FAILED, TIMEOUT
                    log.error("the night of %s ran past its limit and was killed", agent)
                except (Exception, SystemExit) as e:  # SystemExit: an argparse refusal ends no thread
                    state, why = FAILED, type(e).__name__
                    log.exception("the night of %s failed", agent)
                self._end(agent, night, state, why)
                rep["ran"][agent] = state
                log.info("night %s of %s: %s%s", night, agent, state, f" ({why})" if why else "")
        finally:
            self._unlock()
        return rep

    def loop(self, stop, every=TICK):
        """once() now, then every `every` seconds until stop (a threading.Event) is set. A look
        that fails is logged and the next one tries again."""
        while True:
            try:
                self.once()
            except Exception:
                log.exception("the night scheduler's look failed")
            if stop.wait(every):
                return

    def runs(self, night=None):
        """The records, oldest first: [{agent, night, state, started_at, ended_at, why}]."""
        with self.db.tx() as c:
            q = "SELECT * FROM night_runs" + (" WHERE night = ?" if night else "") + " ORDER BY started_at, agent"
            return [dict(r) for r in c.execute(q, (night,) if night else ())]

    # ---- the records and the lock, each one SQL statement --------------------------------

    def _had(self, agent, night):
        with self.db.tx() as c:
            return c.execute("SELECT 1 FROM night_runs WHERE agent = ? AND night = ?", (agent, night)).fetchone() is not None

    def _claim(self, agent, night, now):
        with self.db.tx() as c:
            return c.execute("INSERT OR IGNORE INTO night_runs (agent, night, state, started_at) VALUES (?, ?, ?, ?)",
                             (agent, night, RUNNING, now)).rowcount == 1

    def _end(self, agent, night, state, why):
        with self.db.tx() as c:
            c.execute("UPDATE night_runs SET state = ?, ended_at = ?, why = ? WHERE agent = ? AND night = ? AND state = ?",
                      (state, self.clock(), why, agent, night, RUNNING))

    def _stop_stale(self, now):
        with self.db.tx() as c:
            c.execute("UPDATE night_runs SET state = ?, why = ? WHERE state = ? AND started_at <= ?",
                      (STOPPED, "started and never ended", RUNNING, now - self.stale))

    def _lock(self, now):
        """Take or refresh the lock: free, this process's, or older than stale. True when held."""
        with self.db.tx() as c:
            return c.execute(
                "INSERT INTO night_lock (id, holder, at) VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "holder = excluded.holder, at = excluded.at WHERE night_lock.holder = excluded.holder OR night_lock.at <= ?",
                (self.holder, now, now - self.stale)).rowcount == 1

    def _unlock(self):
        with self.db.tx() as c:
            c.execute("DELETE FROM night_lock WHERE id = 1 AND holder = ?", (self.holder,))

    def _take_over(self, old, now):
        """Take the lock from old, the holder it was seen with (a Run reflection whose process is gone,
        reflection/reflect_now.py gone). True when it was still old's and is now this one's."""
        with self.db.tx() as c:
            return c.execute("UPDATE night_lock SET holder = ?, at = ? WHERE id = 1 AND holder = ?",
                             (self.holder, now, old)).rowcount == 1


def live_holder(db, now, stale=STALE):
    """Who holds the night lock on db now: its holder, or None when the lock is free, older than stale (the
    next taker takes it over) or never made."""
    with db.tx() as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'night_lock'").fetchone() is None:
            return None
        row = c.execute("SELECT holder FROM night_lock WHERE id = 1 AND at > ?", (now - float(stale),)).fetchone()
    return None if row is None else row[0]


def start(db, db_path, stop=None):
    """The scheduler's thread for a running service, started; None when NIGHT_HOUR is off or it
    could not start (the log says why). The service goes on either way."""
    try:
        sched = Scheduler(db, db_path)
    except Exception:
        log.exception("the night scheduler is off: it could not be set up")
        return None
    if sched.when is None:
        log.info("the night scheduler is off (%s=%s)", HOUR_ENV, OFF)
        return None
    thread = threading.Thread(target=sched.loop, args=(stop or threading.Event(),), daemon=True, name="nights")
    thread.start()
    log.info("the night scheduler runs each agent's night at %02d:00 %s", sched.when[0], sched.when[1].key)
    return thread
