"""Run reflection on an agent's page (DECISIONS items 92 and 93): that agent's night now, with the
real models on the real database, started from the page (Morning.run_reflection, pages.py
REFLECT_PATH) and run in the page's background thread, as Run the Arena is.

It is the night study of reflection/night.py night(), the same function the scheduled night and the
manual command run: the trial check, the practice matches of an agent Quick start built written as
cases, the study of the lost chats with the hotfix notes, a lesson written from them, the exam before
its trial (the full exam: night.agent_exam), the snapshot and the saved report (night-<agent>-<time>.json
next to the database, which the page reads). The courier check, the new mode step and the practice
customers grown from real chats stay on the scheduled night: they are not the learning step.

Every model call is taken from the day's call count next to the database (arena/run.py Calls,
CALLS_FILE), the same cap as Run the Arena, Try again and Try Sales: the study's, the risk judge's,
the exam's and the shared pool writer's. The Arena rerun inside the exam takes from the same Calls
(arena/gate.py Fresh, FreshTurn, given calls= and the models as they are), so each of its calls counts
once and lands in the run's count.

The run holds the night lock (reflection/scheduler.py night_lock), so it never runs while the
scheduled night or a night run by hand runs on this database, and they wait for it; Morning keeps one
run per agent and never beside a Run the Arena of the same agent. A page stopped mid run leaves its
holder (holder()); the next press takes it over once that process is gone (gone).

Steps marks where it is for the page: reading lost chats until the proposer or the idea part first
asks its model, writing a lesson from then, the exam once a lesson takes it.

The Sales agent practises on a copy of its database, <db>.arena (arena/run.py arena_copy), so the
chats it lost in the Arena are cases there, never in the live log (DECISIONS 46 and 96). While that copy
holds them, its Run reflection studies them there (run_arena): the study and the eval gate the Arena runs
between rounds (arena/rounds.py Between), on the night's study models, then the full exam, and only a
lesson that passes both is written to the live database (rounds.hand_live), so no live customer meets a
lesson that was not examined. With no Arena loss in the copy it runs the night on the live database, as
for any agent. The day's call count, the night lock and the steps are the same.
"""
import functools
import os
import secrets
import socket
import threading
import time
from pathlib import Path

READ, LESSON, EXAM = "read", "lesson", "exam"
STEPS = (READ, LESSON, EXAM)
PAGE_HOLDER = "page"  # how the night lock names a holder that is Run reflection (scheduler.py night_lock)


def holder(agent):
    """The night lock's holder for a Run reflection of agent: page:<agent>:<host>:<pid>:<token>. A page
    stopped mid run (Ctrl+C) leaves it behind; the host and pid let the next press see that its process
    is gone (gone) and take the lock over, not wait the lock's STALE hours."""
    return f"{PAGE_HOLDER}:{agent}:{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(4)}"


def _page_pid(held):
    """The pid in a Run reflection's holder (holder()) made on this machine, else None."""
    bits = held.split(":") if isinstance(held, str) else []
    if len(bits) != 5 or bits[0] != PAGE_HOLDER or bits[2] != socket.gethostname() or \
            not (bits[3].isascii() and bits[3].isdigit()):
        return None
    pid = int(bits[3])
    return pid if pid > 0 else None


def ours(held):
    """True when held is a Run reflection's holder of this very page process."""
    return _page_pid(held) == os.getpid()


def gone(held):
    """True when held is a Run reflection's holder (holder()) made on this machine whose process no longer
    runs: os.kill(pid, 0) raises ProcessLookupError. Any other holder (the scheduled night, a night run by
    hand, another machine's, a process that runs or one that cannot be asked) is False: it is waited for."""
    pid = _page_pid(held)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (OSError, OverflowError):  # PermissionError: it runs, as another user
        return False
    return False


class Steps:
    """Where a running reflection is: READ, then LESSON, then EXAM; it never steps back."""

    def __init__(self):
        self._at, self._lock = READ, threading.Lock()

    @property
    def at(self):
        with self._lock:
            return self._at

    def mark(self, step):
        with self._lock:
            if STEPS.index(step) > STEPS.index(self._at):
                self._at = step

    def marking(self, model, step):
        """model, marking step at each call (the proposer's and the idea part's: writing a lesson)."""
        steps = self

        class Marked:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                steps.mark(step)
                return model.chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)

            def __getattr__(self, name):  # the route and model id a part names in its label
                return getattr(model, name)
        return Marked()

    def exam(self, make):
        """make(lessons) -> examiner, marking EXAM each time a lesson takes it."""
        def made(lessons):
            examiner = make(lessons)

            def run(text, stages):
                self.mark(EXAM)
                return examiner(text, stages)
            return run
        return made


def lost_chats(db, plug, until=None, days=None):
    """The lost chats the night would read for plug: its cases in the night's window (night.default_days)
    that ended on a bad result, scope cases too (engine/study.py _own and _counts, as Study.run counts
    rep["decided"]["bad"])."""
    from engine import study as study_mod
    from engine.log import Log
    from reflection import night
    until = time.time() if until is None else float(until)
    days = night.default_days(plug) if days is None else float(days)
    every, _cases, _scoped = study_mod._own(plug, Log(db, plug).window(until - days * night.DAY, until), until)
    return study_mod._counts(plug, every)["decided"]["bad"]


def plug_path(agent, folder, db_path):
    """The plug file the rollback line names: the built agent's own, else the repo's (scheduler.agents)."""
    if folder is not None:
        return str(Path(folder) / "plug.json")
    from reflection import scheduler
    return next((str(p) for a, p in scheduler.agents(None) if a == agent), None)


def run(db, db_path, plug, *, folder, models, calls, steps, until=None):
    """One night of plug now, on db (its own connection) at db_path. models: {"study", "open", "exam"}
    (arena/run.py reflection_models; a test hands fakes), each call taken from calls. folder: the folder of an
    agent Quick start built, else None. Returns (the report, the saved report's path)."""
    from kit.db import DEFAULT_PATH
    from reflection import judge as judge_mod
    from reflection import night
    from reflection import shared as shared_mod
    from reflection import study as parts
    study_m, open_m = (calls.model(models[k]) for k in ("study", "open"))
    lesson_m = steps.marking(study_m, LESSON)
    # the exam's model as it is, with calls: the exam and its judges take each call from calls, and the Arena
    # rerun after it counts once on the same calls (night.agent_exam)
    make = night.agent_exam(plug, str(db_path), folder=folder, model=models["exam"], calls=calls)
    home = Path(folder) if folder is not None else Path(db_path).expanduser().resolve().parent  # as night.main
    try:  # an owner id or shared folder that cannot be read leaves the pool out, not the night
        link, left_out = shared_mod.Link.for_agent(plug, home, shared_mod.Writer(model=open_m),
                                                   shared_mod.root_for(str(db_path)), db=str(db_path)), None
    except (shared_mod.Refused, OSError) as e:
        link, left_out = None, shared_mod.left_out(e)
    until = time.time() if until is None else float(until)
    rep = night.night(db, plug, until=until, judge=judge_mod.Judge(model=open_m),
                      proposer=parts.Proposer(model=lesson_m), tagger=parts.Tagger(model=study_m),
                      fit=parts.FitCheck(model=open_m), adapter=parts.Adapter(model=open_m),
                      ideas=parts.Ideas(model=lesson_m), exam=None if make is None else steps.exam(make),
                      spotter=parts.Spotter(model=study_m), note_writer=parts.NoteWriter(model=study_m),
                      others=night.other_plugs(plug, db=str(db_path)), practice=folder, shared=link)
    if left_out:
        rep["notes"].append(left_out)
    rep["by"] = "Run reflection"  # started on the page, not by the scheduler
    rep["calls"] = calls.taken
    if calls.reached:
        rep["notes"].append("the day's model call cap was reached, so the rest did not run")
    where = plug_path(plug.agent, folder, db_path)
    if where:
        rep["snapshot"]["plug"] = where  # the rollback command names what this run was given
    if Path(db_path).resolve() != DEFAULT_PATH.resolve():
        rep["snapshot"]["db"] = str(db_path)
    return rep, night.save(rep, db_path)


def arena_path(db_path):
    """The Sales agent's Arena copy of the database at db_path (arena/run.py arena_copy): <db>.arena."""
    from arena import run as run_mod
    live = Path(db_path)
    return live.with_name(live.name + run_mod.ARENA_SUFFIX)


ARENA_CASES = ("SELECT case_id, MIN(at) FROM trace WHERE agent = ? AND json_extract(detail, '$.arena') = 1 "
               "GROUP BY case_id ORDER BY MIN(at), case_id")


def arena_losses(db_path, agent):
    """The chats agent lost in its newest Arena run, as cases in the Arena's copy (arena/learn.py to_case:
    only a lost match becomes one): [(case id, its first row's time)]; [] with no copy or none there. Read
    only: the copy is opened read only and never made here."""
    import sqlite3
    path = arena_path(db_path)
    if path.is_symlink() or not path.is_file():
        return []
    try:
        c = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            return [(r[0], float(r[1])) for r in c.execute(ARENA_CASES, (agent,))]
        finally:
            c.close()
    except sqlite3.Error:  # no log table yet, or a copy being made: nothing to study
        return []


def run_arena(db_path, plug, *, models, agent_model, customer_model, calls, steps, until=None):
    """Run reflection on the Sales agent's Arena losses (arena_losses): the study between rounds and its
    eval gate (arena/rounds.py Between) on the Arena's copy, read from the oldest of those losses, then the
    full exam before a lesson that passed is written to the live database at db_path. models: {"study",
    "open", "exam"} (arena/run.py reflection_models; a test adds "examiner" and "full", as arena/run.py main
    takes them); agent_model and customer_model: the Arena's, for the gate's rerun of past wins. Each call is
    taken from calls. Returns Between's counts with "cases", the losses read, and "cards", the live ids of
    the lessons written to the live database. Refused (ValueError) when the copy holds a lesson mined from
    history rows (DECISIONS item 20)."""
    from arena import rounds as rounds_mod, run as run_mod
    from kit.db import Db
    from reflection.lessons import Lessons as SalesLessons
    losses = arena_losses(db_path, plug.agent)
    models = dict(models)
    full = models.pop("full", None if "examiner" in models else rounds_mod.full_examiner)
    examiner = models.pop("examiner", functools.partial(rounds_mod.real_examiner, cap=rounds_mod.EXAM_CAP))
    marked = {"study": steps.marking(models["study"], LESSON), "open": models["open"], "exam": models["exam"]}

    def at_exam(make):  # each exam the gate makes marks EXAM when a lesson takes it
        if make is None:
            return None

        def made(p, kept, model):
            examine = make(p, kept, model)

            def run_it(text, stages):
                steps.mark(EXAM)
                return examine(text, stages)
            return run_it
        return made
    copy = Db(str(arena_path(db_path)))
    live = []
    try:
        mined = run_mod.history_lessons(copy)
        if mined:
            raise ValueError("the Arena's copy holds lessons mined from history rows; every agent starts from zero "
                             "(DECISIONS item 20)")
        pool = rounds_mod.Pool(SalesLessons(copy), hotfixes=lambda: rounds_mod.live_hotfixes(str(db_path), plug.agent))
        pool.refresh()  # the corrections sent on the live page, as before every Arena match

        def live_lessons():  # opened at the first lesson that passes the gate, not before
            live.append(Db(str(db_path)))
            return SalesLessons(live[0])
        until = time.time() if until is None else float(until)
        between = rounds_mod.Between(copy, plug, calls=calls, state=run_mod.state_dir(db_path), pool=pool,
                                     agent_model=agent_model, customer_model=customer_model, models=marked,
                                     examiner=at_exam(examiner), live=live_lessons, full=at_exam(full),
                                     now=lambda: until)
        between.pending = [case for case, _ in losses]
        if losses:
            between.since = min(at for _, at in losses) - 1.0
        out = between(0)
    finally:
        for d in [copy] + live:
            d.close()
    out["cases"] = len(losses)
    out["cards"] = [one["live_id"] for one in out["lessons"] if one.get("live_id") is not None]
    out["until"] = until
    return out
