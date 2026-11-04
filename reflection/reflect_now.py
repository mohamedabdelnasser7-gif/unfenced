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
the exam's and the shared pool writer's. The Arena rerun inside the exam counts on the same file
(arena/gate.py Fresh, FreshTurn).

The run holds the night lock (reflection/scheduler.py night_lock), so it never runs while the
scheduled night runs on this database, and the scheduled night waits for it; Morning keeps one run
per agent and never beside a Run the Arena of the same agent.

Steps marks where it is for the page: reading lost chats until the proposer or the idea part first
asks its model, writing a lesson from then, the exam once a lesson takes it.
"""
import threading
import time
from pathlib import Path

READ, LESSON, EXAM = "read", "lesson", "exam"
STEPS = (READ, LESSON, EXAM)
PAGE_HOLDER = "page"  # how the night lock names a holder that is Run reflection (scheduler.py night_lock)


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
    (arena/run.py reflection_models; a test hands fakes), each taken from calls. folder: the folder of an
    agent Quick start built, else None. Returns (the report, the saved report's path)."""
    from kit.db import DEFAULT_PATH
    from reflection import judge as judge_mod
    from reflection import night
    from reflection import shared as shared_mod
    from reflection import study as parts
    study_m, open_m, exam_m = (calls.model(models[k]) for k in ("study", "open", "exam"))
    lesson_m = steps.marking(study_m, LESSON)
    make = night.agent_exam(plug, str(db_path), folder=folder, model=exam_m)
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
