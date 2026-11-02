"""The Arena between rounds (new, 2026-10-31; DECISIONS items 4, 7, 8, 9a, 27 and 28): the round's
lost training matches go to the night study, every new lesson goes through the eval gate, and only
the lessons that pass are handed to the next round.

arena/run.py builds a Between when --db names the Sales agent's database and the run has more than
one round, on the Arena's own copy of that database (arena/run.py arena_copy). Its learn() writes
each lost training match as a case in the copy (arena/learn.py) and remembers it;
calling it with a round's number then:

1. Runs the night study (reflection/night.py LinkedStudy, the night's own Meta parts) on that
   round's lost matches only: every other case in the database is out of its window, and no other
   agent is read. All its cases ended not good, so the pattern search, which needs good and not
   good cases, finds nothing; the idea part (at most 3 ideas a study) is what writes lessons here.
   A lesson the gate failed after an earlier round goes back into this study with what it broke
   (engine/study.py, step 5; DECISIONS item 50), so the idea part writes a different try.
2. Puts every new lesson through the eval gate (arena/gate.py: the exam, then the rerun of past
   wins, with the fixed and broken counts and McNemar's p-value). Here the exam is scoped
   (DECISIONS item 75, reflection/exam.py Examiner scope): a lesson takes only the situations of its
   own stages, plus, for a rewrite, the situations its earlier tries failed, under EXAM_CAP model
   calls a lesson (arena/run.py --exam-cap); the night keeps the full exam. A lesson that would start its
   trial takes it as the night has it take it, before it starts. A lesson that does not take it
   there (high risk with no Accept high risk, a copy of a case's words, close to a pulled line or
   against a live one) takes it right after, and the result is saved on the lesson as its exam,
   so its card shows it; it still waits for a person's yes either way.
   A lesson the gate refused for what it broke goes straight back to the study with it (Mohamed
   2026-11-02, "Yes now"; DECISIONS item 50): Study.rewrite gives the idea part that line and its
   earlier tries, each with the situation and check it failed and its fixed and broken counts, and
   the one new line it writes takes the gate in the same round. At most REWRITES new tries a
   lesson, on the run's call cap; a try that still fails stays out like any refused lesson. A lesson
   whose exam could not run is not rewritten. No line is ever written by hand.
3. Hands on (Pool) only a lesson that passed and that the lessons' own rules let go ahead with no
   further yes: on trial or kept, or low risk and waiting its turn. A high risk lesson goes ahead
   only on a person's yes, or under Accept high risk as the engine already allows; a lesson that
   failed the gate is never handed, whatever its state.

4. Hands a lesson that passed the gate to the live agent's database (hand_live; DECISIONS item 46).
   arena/run.py gives Between the Arena's own copy of the database as db, and the live one as
   live: the cases, the study, the failed lessons and their exams stay in the copy, and only a
   lesson that passed is written to the live database, as the study writes one there: as waiting,
   with its risk, its lines and its exam row, then on trial at the live database's own level (or
   waiting its turn behind a live trial) when it went on trial or waited its turn in the copy. A
   high risk one starts there only under the live database's Accept high risk; else it waits for
   a person's yes. With no live, db is the agent's own database and nothing is copied. When the
   live database is busy or locked (sqlite3.Error), the lesson is not handed this run: the round
   notes "not handed, live busy" and the run and its report go on.

5. Hands a correction the user typed on the live page while the run goes on (live_hotfixes; Mohamed
   2026-11-02, "So hotfix should be in arena too then", and "It shouldn't make the same mistake in
   the same run"): before every match, Pool.refresh reads the live database, read only, for the
   agent's corrections that passed their exam and run there as a hotfix (on trial or kept), those
   already running when the run started too, and the Pool hands them first in every match after, and to the
   gate of each new lesson. A correction pulled since is no longer handed. Nothing the run makes
   (cases, lessons, exams, matches) is ever written to the live database by this step. A live
   database that is busy, locked or gone keeps the corrections read last.

Every model call of the study, the risk judge, the exam and the rerun is taken from the Arena's own
call count (arena/run.py Calls, arena-calls.json), so one cap holds the whole run. At the cap each
part fails closed: no candidates or ideas, the judge unsure (so high), the exam not run (so the
lesson is refused). Nothing from that study is handed on, and arena/run.py stops the run there.
"""
import sqlite3
import time
from pathlib import Path

from engine import exam as exam_mod
from engine import switches as switches_mod
from engine.lessons import HOTFIX_SOURCE, KEPT, MAX_PICK, PERSON, PULLED, TRYING, WAITING
from engine.plug import ALL
from engine.risk import LOW
from engine.study import read_days

DAY = 86400.0
LIVE_BUSY = "not handed, live busy"  # a passed lesson the live database could not take this run
EXAM_CAP = 60  # model calls one lesson's exam may take between rounds, the run on the kept lessons included (--exam-cap)
REWRITES = 2  # new tries a lesson the gate refused may take in the same round (Mohamed 2026-11-02, "Yes now")
CAP_NOTE = "the model call cap was reached during the night study; nothing it left unchecked is handed on"


def live_hotfixes(path, agent):
    """The agent's corrections in the live database at path that passed their exam, run there as a
    hotfix (on trial or kept), whenever they were added, oldest first, each as the Pool hands
    it: kept, its stages and fields as lists, and its id the live id made negative (live_id keeps the
    live one), so it never reads as a lesson of the Arena's copy. The database is opened read only.
    sqlite3.Error when it cannot be read (busy, locked, gone, or a database with no lessons yet)."""
    con = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=1)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT l.* FROM lessons l JOIN lesson_exams e ON e.lesson_id = l.id WHERE l.agent = ? AND l.source = ? "
            "AND l.origin = ? AND e.passed = 1 AND l.state IN (?, ?) ORDER BY l.id",
            (agent, HOTFIX_SOURCE, PERSON, TRYING, KEPT)).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        d.update(id=-int(d["id"]), live_id=int(d["id"]), state=KEPT,
                 stages=[t for t in (d.get("stages") or "").split(",") if t],
                 fields=[t for t in (d.get("fields") or "").split(",") if t])
        out.append(d)
    return out


class Pool:
    """The lessons the Arena hands (the reflection/exam.py _Lessons kept shape: live() and pick()):
    the corrections read from the live database (hotfixes, refreshed before every match), then the
    agent's kept lessons, then the lessons this run passed between rounds and handed on, each read
    again at every call, so one pulled since is not handed. A handed lesson reads as kept here
    because the Arena hands it in every match, as the exam hands a kept one. hotfixes: a callable
    giving the live corrections (live_hotfixes), or None."""

    def __init__(self, lessons, hotfixes=None):
        self.lessons, self.handed = lessons, []
        self.hotfixes, self.fixes, self.busy, self.seen = hotfixes, [], None, []

    def refresh(self):
        """Read the live corrections again (before every match). A live database that cannot be read
        keeps the ones read last and says why in busy."""
        if self.hotfixes is None:
            return self.fixes
        try:
            got = list(self.hotfixes())
        except sqlite3.Error as e:
            self.busy = f"{LIVE_BUSY} ({e})"
            return self.fixes
        self.busy = None
        mine = {les["text"] for les in self.lessons.live() if les["state"] == KEPT}
        mine |= {les["text"] for les in self._passed()}
        self.fixes = [les for les in got if les["text"] not in mine]
        for les in self.fixes:
            if les["live_id"] not in self.seen:
                self.seen.append(les["live_id"])
        return self.fixes

    def _fixes(self, stage=None):
        return [dict(les) for les in self.fixes if not stage or stage in les["stages"] or ALL in les["stages"]]

    def hand_on(self, lesson_id):
        if lesson_id not in self.handed:
            self.handed.append(lesson_id)

    def _passed(self, stage=None):
        out = []
        for lid in self.handed:
            les = self.lessons.get(lid)
            if les is None or les["state"] in (PULLED, KEPT):  # a kept one is among the kept already
                continue
            if stage and stage not in les["stages"] and ALL not in les["stages"]:
                continue
            out.append(dict(les, state=KEPT))
        return out

    def live(self, stage=None, now=None):
        return (self._fixes(stage) + [les for les in self.lessons.live(stage, now) if les["state"] == KEPT]
                + self._passed(stage))

    def pick(self, stage, text, limit=MAX_PICK, *, case=None, now=None, every_share=False):
        kept = [p for p in self.lessons.pick(stage, text, limit, now=now, every_share=True) if p["state"] == KEPT]
        return (self._fixes(stage) + kept + self._passed(stage))[:min(limit, MAX_PICK)]


def goes_ahead(les, trial, passed):
    """May a lesson that took the gate be handed to the next round? Only when it passed and its own
    rules let it go ahead with no further yes: on trial or kept, or low risk and waiting its turn."""
    if not passed or les is None:
        return False
    if les["state"] in (TRYING, KEPT):
        return True
    return les["state"] == WAITING and trial is not None and les["risk"] == LOW


LESSON_COLUMNS = ("agent", "text", "stages", "fields", "risk", "risk_why", "score", "source", "origin", "kind",
                  "added_at")


def _live_id(c, agent, words):
    """The live lesson of agent with these words (one not pulled first, then the newest), or None."""
    row = c.execute("SELECT id FROM lessons WHERE agent = ? AND text = ? ORDER BY state = 'pulled', id DESC LIMIT 1",
                    (agent, words)).fetchone()
    return None if row is None else row["id"]


def hand_live(arena_db, live, lesson_id, now=None):
    """Write one lesson that passed the gate in the Arena's copy (arena_db) to the live database:
    live is the live agent's Lessons (engine/lessons.py), on its own database. The lesson is written
    as waiting with its risk, risk lines, source, origin, kind and when it was added, its exam row
    beside it, and its clashes with lessons the live database holds (found there by agent and words,
    as is its source, since a copy id can name another lesson live). When it went on trial or waited
    its turn in the copy, it starts its trial in the live database now, at the live level, or waits
    its turn there behind a live trial (engine Lessons._try); a high risk one only while the live
    Accept high risk is on, else it waits for a person's yes. A lesson the copy pulled, or one that
    did not pass, is refused. Returns the lesson's id in the live database."""
    with arena_db.tx() as c:
        les = c.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        exam = c.execute("SELECT * FROM lesson_exams WHERE lesson_id = ?", (lesson_id,)).fetchone()
        tried = c.execute("SELECT 1 FROM trials WHERE lesson_id = ?", (lesson_id,)).fetchone() is not None
        # the clash targets and the source by agent and words: a copy id can name another lesson live
        clashes = [(r["agent"], r["text"]) for r in c.execute(
            "SELECT l.agent, l.text FROM lesson_clashes k JOIN lessons l ON l.id = k.live_id WHERE k.lesson_id = ?",
            (lesson_id,))]
        source = None
        if les is not None and les["source_lesson_id"] is not None:
            row = c.execute("SELECT agent, text FROM lessons WHERE id = ?", (les["source_lesson_id"],)).fetchone()
            source = None if row is None else (row["agent"], row["text"])
    if les is None or les["agent"] != live.agent or les["state"] == PULLED:
        raise ValueError(f"no lesson {lesson_id} of {live.agent} to hand to the live database")
    if exam is None or not exam["passed"]:
        raise ValueError(f"lesson {lesson_id} did not pass the eval gate")
    now = time.time() if now is None else float(now)
    with live.db.tx() as c:
        source_id = None  # its source in the live database, another agent's lesson with the same words
        if source is not None and source[0] != live.agent:
            source_id = _live_id(c, *source)
        cur = c.execute(f"INSERT INTO lessons ({', '.join(LESSON_COLUMNS)}, state, share, source_lesson_id) "
                        f"VALUES ({', '.join('?' * len(LESSON_COLUMNS))}, 'waiting', 1, ?)",
                        (*(les[k] for k in LESSON_COLUMNS), source_id))
        new_id = cur.lastrowid
        have = {r["name"] for r in c.execute("PRAGMA table_info(lesson_exams)")}
        cols = [k for k in exam.keys() if k in have and k != "lesson_id"]
        c.execute(f"INSERT INTO lesson_exams (lesson_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})",
                  (new_id, *(exam[k] for k in cols)))
        for agent, words in clashes:
            other = _live_id(c, agent, words)
            if other is not None and other != new_id:
                c.execute("INSERT OR IGNORE INTO lesson_clashes (lesson_id, live_id, agent, at) VALUES (?, ?, ?, ?)",
                          (new_id, other, live.agent, now))
        if tried:
            accept = None
            if les["risk"] != LOW:
                row = switches_mod.latest(c, live.agent, switches_mod.ACCEPT)
                accept = row if switches_mod.accept_on(row, now) else None
            if les["risk"] == LOW or accept is not None:
                live._try(c, new_id, [t for t in les["stages"].split(",") if t], now, accept=accept)
    return new_id


def real_examiner(plug, kept, model, cap=EXAM_CAP):
    """The Sales agent's exam with the gate's counts (reflection/exam.py, as night.sales_exam has it),
    scoped to the lesson's stages and source situations under cap model calls a lesson."""
    from reflection import exam as exam_mod_sales
    return exam_mod_sales.Examiner(plug, kept=kept, model=model, count=True, scope=True, cap=cap)


def full_examiner(plug, kept, model):
    """The Sales agent's full exam, every situation, as the night runs it: what a lesson that passed the
    scoped exam takes once more before hand_live writes it to the live database, so nothing reaches
    real customers on the scoped exam alone (DECISIONS item 75: the scoped exam is for the Arena)."""
    from reflection import exam as exam_mod_sales
    return exam_mod_sales.Examiner(plug, kept=kept, model=model, count=True)


class Between:
    """The night study and the eval gate between two Arena rounds. models: {"study": the proposer,
    tagger and idea part's model, "open": the fit check, adapter and risk judge's model, "exam": the
    exam's model}; each is taken from calls. agent_model and customer_model: the Arena's own, not yet
    counted (the gate counts them). examiner(plug, kept, model): the exam (real_examiner). db: the
    Arena's own copy of the agent's database; live: a callable giving the live agent's Lessons,
    called at the first lesson that passes, which hand_live writes it to (None: db is the agent's
    own database, and there is nothing to hand). full(plug, kept, model): the full exam a passed lesson
    takes before it is handed live (full_examiner); a lesson that fails it, or whose full exam cannot
    run, stays in the Arena and is not handed. None hands on the scoped pass (tests with a fake exam)."""

    def __init__(self, db, plug, *, calls, state, pool, agent_model, customer_model, models, examiner=real_examiner,
                 now=time.time, live=None, full=None):
        self.full = full
        self.db, self.plug, self.calls, self.state, self.pool = db, plug, calls, state, pool
        self.agent_model, self.customer_model = agent_model, customer_model
        self.models, self.examiner, self.now = dict(models), examiner, now
        self.pending = []
        self.live, self._live = live, None
        self.scoped = None  # the exam made for this round (its source names a rewrite's earlier fails)

    def learn(self, match, judged, match_id):
        """A lost training match as a case (arena/learn.py), kept for the study after its round."""
        from arena import learn as learn_mod
        case = learn_mod.to_case(self.db, match, judged, match_id)
        self.pending.append(case)
        return case

    def _exam(self, lessons):
        from arena import gate
        examiner = self.scoped = self.examiner(self.plug, self.pool, self.calls.model(self.models["exam"]))
        return gate.Fresh(examiner, self.pool, state=self.state, agent_model=self.agent_model,
                          customer_model=self.customer_model, calls=self.calls)

    def __call__(self, round_no):
        from reflection import judge as judge_mod
        from reflection import night
        from reflection import study as parts
        from reflection.lessons import Lessons
        ids, self.pending = self.pending, []
        out = {"after_round": round_no, "cases": len(ids), "proposed": 0, "passed": 0, "refused": 0,
               "waits_for_yes": 0, "handed": 0, "fixed": 0, "broke": 0, "calls": 0, "lessons": [], "notes": []}
        if self.pool.seen:  # corrections from the live page this run hands (Pool.refresh)
            out["hotfixes"] = list(self.pool.seen)
            out["notes"].append("corrections from the live page handed in this run: live lesson "
                                + ", ".join(map(str, self.pool.seen)))
        if self.pool.busy:
            out["notes"].append(f"corrections from the live page: {self.pool.busy}")
        if not ids:
            out["notes"].append("no lost training match this round, so nothing to study")
            return out
        before = self.calls.taken
        study_m, open_m = self.calls.model(self.models["study"]), self.calls.model(self.models["open"])
        lessons = Lessons(self.db, judge=judge_mod.Judge(model=open_m))
        examiner = lessons.examiner = night.Counted(self._exam(lessons))
        study = night.LinkedStudy(self.db, self.plug, proposer=parts.Proposer(model=study_m),
                                  tagger=parts.Tagger(model=study_m), fit=parts.FitCheck(model=open_m),
                                  adapter=parts.Adapter(model=open_m), lessons=lessons,
                                  others=night.other_plugs(self.plug, db=Path(self.state) / "ascent.db" if self.state else None),
                                  ideas=parts.Ideas(model=study_m))
        study.log = _Only(study.log, ids)
        until = float(self.now())
        rep = study.run(until - (read_days(self.plug) + 2) * DAY, until, now=until)
        out["notes"] += rep["notes"]
        for card in rep["cards"]:
            out["lessons"].append(self._gate(lessons, examiner, card["lesson_id"], until))
        self._rewrite(study, lessons, examiner, out, until)
        for one in out["lessons"]:
            if one.get("live"):
                out["notes"].append(f'lesson {one["lesson_id"]}: {one["live"]}')
            out["proposed"] += 1
            out["passed" if one["passed"] else "refused"] += 1
            out["waits_for_yes"] += one["waits_for_yes"]
            out["handed"] += one["handed"]
            if one["gate"]:
                out["fixed"] += one["gate"]["fixed"]
                out["broke"] += one["gate"]["broke"]
        if examiner.skipped:
            out["skipped"] = {why: len(n) for why, n in sorted(examiner.skipped.items())}
        out["calls"] = self.calls.taken - before
        if self.calls.reached:
            out["stopped"] = "cap"
            out["notes"].append(CAP_NOTE)
        return out

    def _rewrite(self, study, lessons, examiner, out, until):
        """Each lesson the gate refused for what it broke goes back to the study with it and is
        rewritten (Study.rewrite), and the new try takes the gate in this same round, at most
        REWRITES times a lesson, while the run's call cap holds. A rewrite that passes is handed on
        as any lesson that passes; one that still fails stays out, as does a lesson whose exam
        could not run. Each try is named in out["rewrites"] as {of, try, lesson_id, idea, passed,
        why}, and each rewritten lesson is in out["lessons"] with "rewrite_of"."""
        since = until - (read_days(self.plug) + 2) * DAY
        rewrites = []
        for first in list(out["lessons"]):
            if first["passed"] or not _broke_something(lessons.exam_of(first["lesson_id"])):
                continue
            chain = [first["lesson_id"]]
            for n in range(1, REWRITES + 1):
                if self.calls.reached:
                    break
                got = study.rewrite(chain, since, until, now=until)
                out["notes"] += got["notes"]
                one = {"of": first["lesson_id"], "try": n, "lesson_id": got["lesson_id"], "idea": got["idea"],
                       "passed": False, "why": got["why"]}
                rewrites.append(one)
                if got["lesson_id"] is None:
                    continue
                self._source(lessons, chain)
                try:
                    gated = self._gate(lessons, examiner, got["lesson_id"], until)
                finally:
                    self._source(lessons, ())
                gated["rewrite_of"] = first["lesson_id"]
                out["lessons"].append(gated)
                one["passed"], one["why"] = gated["passed"], gated["why"] or None
                if gated["passed"] or not _broke_something(lessons.exam_of(got["lesson_id"])):
                    break
                chain.append(got["lesson_id"])
        if rewrites:
            out["rewrites"] = rewrites

    def _source(self, lessons, chain):
        """Point a scoped exam at the situations the earlier tries in chain failed (none for ())."""
        if self.scoped is None or not hasattr(self.scoped, "source"):
            return
        ids = []
        for lid in chain:
            for f in exam_mod.fails_of(lessons.exam_of(lid)):
                n = f.get("situation")
                if isinstance(n, int) and not isinstance(n, bool) and n not in ids and \
                        f.get("check") not in (exam_mod.NOT_RUN, exam_mod.RERUN, exam_mod.ROUND):
                    ids.append(n)
        self.scoped.source = tuple(ids)

    def _gate(self, lessons, examiner, lesson_id, now):
        """One new lesson through the gate, when the study's own write did not take it there, and
        whether it is handed on."""
        les = lessons.get(lesson_id)
        row = lessons.exam_of(lesson_id)
        if row is None:  # no exam ran as it was written: it waits for a yes, and takes the gate now
            try:
                result = examiner(les["text"], les["stages"])
            except Exception as e:  # held, as the engine holds a lesson whose exam raises
                result = exam_mod.could_not_run(e)
            with self.db.tx() as c:
                exam_mod.save(c, self.plug.agent, lesson_id, result, now)
            row = lessons.exam_of(lesson_id)
        passed = bool(row and row["passed"])
        les = lessons.get(lesson_id)  # read again: the exam can change nothing, but a trial may have started
        handed = goes_ahead(les, lessons.trial(lesson_id), passed)
        if handed:
            self.pool.hand_on(lesson_id)
        out = {"lesson_id": lesson_id, "text": les["text"], "risk": les["risk"], "state": les["state"],
               "passed": passed, "handed": handed, "waits_for_yes": passed and not handed and les["state"] == WAITING,
               "why": exam_mod.held_line(row), "gate": exam_mod.effect_of(row)}
        if passed and self.live is not None and self.full is not None:  # the full exam before real customers
            try:
                full = self.full(self.plug, self.pool, self.calls.model(self.models["exam"]))(les["text"], les["stages"])
            except Exception as e:  # fail closed: a full exam that cannot run hands nothing
                full = exam_mod.could_not_run(e)
            out["full_exam"] = "passed" if full.passed else f"held: {full.line()}"
            if not full.passed:
                out["live_id"] = None
                out["live"] = f"{FULL_HELD} ({full.line()})"
                return out
        if passed and self.live is not None:  # only a lesson that passed reaches the live database
            try:
                if self._live is None:
                    self._live = self.live()
                out["live_id"] = hand_live(self.db, self._live, lesson_id, now)
            except sqlite3.Error as e:  # the live database busy or locked: the run and its report go on
                out["live_id"] = None
                out["live"] = f"{LIVE_BUSY} ({e})"
        return out


FULL_HELD = "passed the Arena's exam but not the full exam, so it stays in the Arena and is not handed live"


def _broke_something(row):
    """A failed exam row with at least one fail that is not the exam itself failing to run, so a
    rewrite has something to avoid."""
    return any(f.get("check") != exam_mod.NOT_RUN for f in exam_mod.fails_of(row))


class _Only:
    """The study's log, reading only the round's cases (Log.window and its agent's view)."""

    def __init__(self, log, ids):
        self.log, self.ids = log, set(ids)

    def window(self, since, until, *, agent=None, plug=None):
        return {k: v for k, v in self.log.window(since, until, agent=agent, plug=plug).items() if k in self.ids}

    def __getattr__(self, name):
        return getattr(self.log, name)


def line(one):
    """One round's Reflection in one plain line, for the report and the Morning page."""
    if not one.get("cases"):
        return f"after round {one['after_round']}: no lost training match, nothing studied"
    text = (f"after round {one['after_round']}: night study of {one['cases']} lost match"
            f"{'' if one['cases'] == 1 else 'es'}; lessons proposed {one['proposed']}, passed {one['passed']}, "
            f"refused {one['refused']}, handed to round {one['after_round'] + 1} {one['handed']}")
    if one.get("waits_for_yes"):
        text += f", waiting for a yes {one['waits_for_yes']}"
    text += f"; eval gate fixed {one['fixed']}, broke {one['broke']}"
    if one.get("rewrites"):  # the new tries of lessons the gate refused, in the same round
        tries = one["rewrites"]
        text += (f"; rewrites after a failed gate: {sum(1 for r in tries if r['lesson_id'] is not None)} written, "
                 f"{sum(1 for r in tries if r['passed'])} passed")
    text += f"; {one['calls']} model calls"
    if one.get("stopped") == "cap":
        text += "; stopped at the model call cap"
    return text
