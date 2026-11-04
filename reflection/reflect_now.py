"""Run reflection on an agent's page (DECISIONS items 92, 93 and 102): that agent's night now, on its real
customer chats, with the real models on the real database, started from the page (Morning.run_reflection,
pages.py REFLECT_PATH) and run in the page's background thread, as Run the Arena is. And Train on the
Arena tab (DECISIONS 104, Morning.run_train): Reflection on every match the newest full Arena run lost.

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

Train studies the Arena's losses, never Run reflection (DECISIONS 102 and 104). The Sales agent practises
on a copy of its database, <db>.arena (arena/run.py arena_copy), so the matches it lost in the Arena are
cases there, never in the live log (DECISIONS 46 and 96): its lost training matches as it plays, its lost
gate matches once Train starts (add_arena_losses). Train studies them there (run_arena): the study and the
eval gate the Arena runs between rounds (arena/rounds.py Between), on the night's study models, then the
full exam, and only a lesson that passes both is written to the live database (rounds.hand_live), so no
live customer meets a lesson that was not examined. An agent made here: every lost match of the run as a
case in its own database (built_cases), then the study between rounds for it (arena/rounds.py
BuiltBetween: train_between, study_built). Train takes calls from the day's count too, and shows its steps
and lessons the same way; it holds no night lock, as Run the Arena holds none.
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
PASSED, FAILED, NOT_RUN, IN_EXAM = "passed", "failed", "not run", "in exam"  # a seen lesson's exam (Steps.seen)
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


def exam_word(result):
    """PASSED, FAILED or NOT_RUN for an exam result (engine/exam.py, reflection/exam.py: .passed and .first)."""
    from engine import exam as engine_exam
    first = getattr(result, "first", None)
    if getattr(first, "check", None) == engine_exam.NOT_RUN:
        return NOT_RUN
    return PASSED if getattr(result, "passed", False) else FAILED


class Steps:
    """Where a running reflection or Train is: READ, then LESSON, then EXAM; it never steps back. seen: each
    lesson as it takes its exam, then the exam's word, for the page's live view (DECISIONS 99 and 100), with
    the corrections sent while it runs (Morning.correct)."""

    def __init__(self, start=READ):
        self._at, self._lock = start, threading.Lock()
        self._seen = []

    @property
    def at(self):
        with self._lock:
            return self._at

    def mark(self, step):
        with self._lock:
            if STEPS.index(step) > STEPS.index(self._at):
                self._at = step

    @property
    def seen(self):
        """[{text, exam, kind}] in the order the lessons took their exam: exam IN_EXAM while it runs, then
        PASSED, FAILED or NOT_RUN; kind "lesson", or "correction" for one the owner sent while it ran. A
        lesson that takes a second exam (the full exam before live) shows that one's word."""
        with self._lock:
            return [dict(x) for x in self._seen]

    def begin(self, text, kind="lesson"):
        """A lesson starts its exam: its entry, IN_EXAM until end()."""
        with self._lock:
            for x in self._seen:
                if x["text"] == text and x["kind"] == kind:
                    x["exam"] = IN_EXAM
                    return x
            x = {"text": str(text), "exam": IN_EXAM, "kind": kind}
            self._seen.append(x)
            return x

    def end(self, entry, word):
        with self._lock:
            entry["exam"] = word

    def add(self, text, result, kind="correction"):
        """A lesson that took its exam elsewhere (a correction sent while it runs): shown with its word."""
        self.end(self.begin(text, kind), exam_word(result))

    def _watch(self, examine):
        """examine(text, stages), each call shown in seen with its result."""
        def run(text, stages):
            self.mark(EXAM)
            entry = self.begin(text)
            try:
                result = examine(text, stages)
            except Exception:
                self.end(entry, NOT_RUN)
                raise
            self.end(entry, exam_word(result))
            return result
        return run

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
        """make(lessons) -> examiner, marking EXAM each time a lesson takes it and showing it in seen."""
        def made(lessons):
            return self._watch(make(lessons))
        return made

    def gate_exam(self, make):
        """make(plug, kept, model) -> examiner (the Arena's exams, arena/rounds.py Between), marking EXAM and
        showing each lesson in seen as exam() does; None stays None."""
        if make is None:
            return None

        def made(p, kept, model):
            return self._watch(make(p, kept, model))
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


def run(db, db_path, plug, *, folder, models, calls, steps, until=None, stop=None):
    """One night of plug now, on db (its own connection) at db_path. models: {"study", "open", "exam"}
    (arena/run.py reflection_models; a test hands fakes), each call taken from calls. folder: the folder of an
    agent Quick start built, else None. stop: the page's Stop check (DECISIONS 98). It runs with no deadline, to
    the end: once Stop is pressed or the day's call cap is reached (night.day_cap_reached on the count calls
    takes from), no new lesson starts its exam and the rest are queued for tonight (engine/study_queue.py).
    Returns (the report, the saved report's path)."""
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
                      others=night.other_plugs(plug, db=str(db_path)), practice=folder, shared=link,
                      deadline=None, stop=stop, capped=night.day_cap_reached(Path(calls.path).parent))
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


def add_arena_losses(db_path, matches):
    """Before Train on the Sales agent (DECISIONS 104): each lost match in matches (the newest full run's, as
    its matches file saved them) that is no case in the Arena's copy yet, written there (arena/learn.py
    to_case): its gate matches, since only a lost training match becomes a case as it plays. Returns how many
    were written; 0 with no copy (a link or none is never written through)."""
    from arena import learn as learn_mod
    from kit.db import Db
    from reflection import PLUG as SALES
    path = arena_path(db_path)
    if path.is_symlink() or not path.is_file():
        return 0
    have = {case for case, _ in arena_losses(db_path, SALES.agent)}
    todo = [m for m in matches if not m.get("won") and learn_mod.case_id(m["id"]) not in have]
    if not todo:
        return 0
    copy = Db(str(path))
    try:
        for m in todo:
            learn_mod.to_case(copy, m, {"won": False, "why": m.get("why"), "quote": m.get("quote")}, m["id"])
    finally:
        copy.close()
    return len(todo)


def built_cases(db, plug, matches):
    """Before Train on an agent made here (DECISIONS 104): each lost match in matches (the newest full run's)
    as a case in db under plug (arena/learn_built.py to_case; one already written, as its training losses
    are while it plays, is left as it is), gate matches included. Returns their case ids, in order."""
    from arena import learn_built
    out = []
    for m in matches:
        if m.get("won"):
            continue
        out.append(learn_built.to_case(db, plug, m, {"won": False, "why": m.get("why"), "quote": m.get("quote")},
                                       m["id"]))
    return out


def run_arena(db_path, plug, *, models, agent_model, customer_model, calls, steps, until=None, stop=None):
    """Train on the Sales agent's Arena losses (arena_losses): the study between rounds and its
    eval gate (arena/rounds.py Between) on the Arena's copy, read from the oldest of those losses, then the
    full exam before a lesson that passed is written to the live database at db_path. models: {"study",
    "open", "exam"} (arena/run.py reflection_models; a test adds "examiner" and "full", as arena/run.py main
    takes them); agent_model and customer_model: the Arena's, for the gate's rerun of past wins. Each call is
    taken from calls. stop: Train's Stop check (Between.stop). Returns Between's counts with "cases", the losses
    read, and "cards", the live ids of the lessons written to the live database. Refused (ValueError) when the
    copy holds a lesson mined from history rows (DECISIONS item 20)."""
    from arena import rounds as rounds_mod, run as run_mod
    from kit.db import Db
    from reflection.lessons import Lessons as SalesLessons
    losses = arena_losses(db_path, plug.agent)
    models = dict(models)
    full = models.pop("full", None if "examiner" in models else rounds_mod.full_examiner)
    examiner = models.pop("examiner", functools.partial(rounds_mod.real_examiner, cap=rounds_mod.EXAM_CAP))
    marked = {"study": steps.marking(models["study"], LESSON), "open": models["open"], "exam": models["exam"]}
    at_exam = steps.gate_exam  # each exam the gate makes marks EXAM and shows the lesson when it takes it
    copy = Db(str(arena_path(db_path)))
    live = []
    try:
        mined = run_mod.history_lessons(copy)
        if mined:
            raise ValueError("the Arena's copy holds lessons mined from history rows; every agent starts from zero "
                             "(DECISIONS item 20)")
        pool = rounds_mod.Pool(SalesLessons(copy), hotfixes=lambda: rounds_mod.live_lessons(str(db_path), plug.agent))
        pool.refresh()  # the corrections sent on the live page and the live lessons on trial, as before every Arena match

        def live_lessons():  # opened at the first lesson that passes the gate, not before
            live.append(Db(str(db_path)))
            return SalesLessons(live[0])
        until = time.time() if until is None else float(until)
        between = rounds_mod.Between(copy, plug, calls=calls, state=run_mod.state_dir(db_path), pool=pool,
                                     agent_model=agent_model, customer_model=customer_model, models=marked,
                                     examiner=at_exam(examiner), live=live_lessons, full=at_exam(full),
                                     now=lambda: until)
        between.pending = [case for case, _ in losses]
        between.stop = stop
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


def study_built(db, db_path, between, *, steps, stop=None):
    """Train for an agent Quick start built (DECISIONS 104): the study between Arena rounds (arena/rounds.py
    BuiltBetween, made by train_between) on between.pending, the cases of the matches the newest full run
    lost (built_cases), as arena/practice.py runs it between two rounds. Returns its counts with "cases" and
    "cards", the ids of the lessons that passed, and "lost", the cases studied."""
    lost = len(between.pending)
    between.stop = stop
    out = between(1)
    out["lost"] = lost
    out["cards"] = [one["lesson_id"] for one in out["lessons"] if one.get("passed")]
    return out


def train_between(db, db_path, folder, *, models, agent_model, customer_model, judge_model, steps):
    """The BuiltBetween Train studies the newest full run's lost matches with (study_built, its pending set
    from built_cases): on db, the page's database, with the night's models (models: {"study", "open", "exam"}, a
    test's "examiner" too), its exam the built agent's own (arena/rounds.py turn_examiner) unless the test
    gives one, every lesson shown in steps.seen. Its calls are taken from the day's count beside the database
    (arena/practice.py reports_of), as the round's are."""
    from arena import practice, rounds as rounds_mod, run as run_mod
    from engine.lessons import Lessons as EngineLessons
    from kit import turn as turn_mod
    agent = turn_mod.load(folder)
    reports = practice.reports_of(Path(folder))
    calls = run_mod.Calls(reports / run_mod.CALLS_FILE, run_mod.DEFAULT_CAP)
    pool = rounds_mod.Pool(EngineLessons(db, agent.plug),  # it reads the live database at its first use
                           hotfixes=lambda: rounds_mod.live_lessons(str(db_path), agent.name))
    examiner = models.get("examiner") or rounds_mod.turn_examiner(agent, calls.model(judge_model))
    marked = {"study": steps.marking(models["study"], LESSON), "open": models["open"], "exam": models["exam"]}
    return rounds_mod.BuiltBetween(db, agent, reports=reports, judge_model=judge_model, calls=calls, pool=pool,
                                   agent_model=agent_model, customer_model=customer_model, models=marked,
                                   examiner=steps.gate_exam(examiner))
