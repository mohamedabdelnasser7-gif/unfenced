"""The Arena between rounds (new, 2026-10-31; DECISIONS items 4, 7, 8, 9a, 27 and 28): the round's
lost training matches go to the night study, every new lesson goes through the eval gate, and only
the lessons that pass are handed to the next round.

arena/run.py builds a Between when --db names the Sales agent's database and the run has more than
one round. Its learn() writes each lost training match as a case (arena/learn.py) and remembers it;
calling it with a round's number then:

1. Runs the night study (reflection/night.py LinkedStudy, the night's own Meta parts) on that
   round's lost matches only: every other case in the database is out of its window, and no other
   agent is read. All its cases ended not good, so the pattern search, which needs good and not
   good cases, finds nothing; the idea part (at most 3 ideas a study) is what writes lessons here.
2. Puts every new lesson through the eval gate (arena/gate.py: the exam, then the rerun of past
   wins, with the fixed and broken counts and McNemar's p-value). A lesson that would start its
   trial takes it as the night has it take it, before it starts. A lesson that does not take it
   there (high risk with no Accept high risk, a copy of a case's words, close to a pulled line or
   against a live one) takes it right after, and the result is saved on the lesson as its exam,
   so its card shows it; it still waits for a person's yes either way.
3. Hands on (Pool) only a lesson that passed and that the lessons' own rules let go ahead with no
   further yes: on trial or kept, or low risk and waiting its turn. A high risk lesson goes ahead
   only on a person's yes, or under Accept high risk as the engine already allows; a lesson that
   failed the gate is never handed, whatever its state.

Every model call of the study, the risk judge, the exam and the rerun is taken from the Arena's own
call count (arena/run.py Calls, arena-calls.json), so one cap holds the whole run. At the cap each
part fails closed: no candidates or ideas, the judge unsure (so high), the exam not run (so the
lesson is refused). Nothing from that study is handed on, and arena/run.py stops the run there.
"""
import time

from engine import exam as exam_mod
from engine.lessons import KEPT, MAX_PICK, PULLED, TRYING, WAITING
from engine.plug import ALL
from engine.risk import LOW
from engine.study import longest

DAY = 86400.0
CAP_NOTE = "the model call cap was reached during the night study; nothing it left unchecked is handed on"


class Pool:
    """The lessons the Arena hands (the reflection/exam.py _Lessons kept shape: live() and pick()):
    the agent's kept lessons, then the lessons this run passed between rounds and handed on, each
    read again at every call, so one pulled since is not handed. A handed lesson reads as kept here
    because the Arena hands it in every match, as the exam hands a kept one."""

    def __init__(self, lessons):
        self.lessons, self.handed = lessons, []

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
        return [les for les in self.lessons.live(stage, now) if les["state"] == KEPT] + self._passed(stage)

    def pick(self, stage, text, limit=MAX_PICK, *, case=None, now=None, every_share=False):
        kept = [p for p in self.lessons.pick(stage, text, limit, now=now, every_share=True) if p["state"] == KEPT]
        return (kept + self._passed(stage))[:min(limit, MAX_PICK)]


def goes_ahead(les, trial, passed):
    """May a lesson that took the gate be handed to the next round? Only when it passed and its own
    rules let it go ahead with no further yes: on trial or kept, or low risk and waiting its turn."""
    if not passed or les is None:
        return False
    if les["state"] in (TRYING, KEPT):
        return True
    return les["state"] == WAITING and trial is not None and les["risk"] == LOW


def real_examiner(plug, kept, model):
    """The Sales agent's exam with the gate's counts (reflection/exam.py, as night.sales_exam has it)."""
    from reflection import exam as exam_mod_sales
    return exam_mod_sales.Examiner(plug, kept=kept, model=model, count=True)


class Between:
    """The night study and the eval gate between two Arena rounds. models: {"study": the proposer,
    tagger and idea part's model, "open": the fit check, adapter and risk judge's model, "exam": the
    exam's model}; each is taken from calls. agent_model and customer_model: the Arena's own, not yet
    counted (the gate counts them). examiner(plug, kept, model): the exam (real_examiner)."""

    def __init__(self, db, plug, *, calls, state, pool, agent_model, customer_model, models, examiner=real_examiner,
                 now=time.time):
        self.db, self.plug, self.calls, self.state, self.pool = db, plug, calls, state, pool
        self.agent_model, self.customer_model = agent_model, customer_model
        self.models, self.examiner, self.now = dict(models), examiner, now
        self.pending = []

    def learn(self, match, judged, match_id):
        """A lost training match as a case (arena/learn.py), kept for the study after its round."""
        from arena import learn as learn_mod
        case = learn_mod.to_case(self.db, match, judged, match_id)
        self.pending.append(case)
        return case

    def _exam(self, lessons):
        from arena import gate
        examiner = self.examiner(self.plug, self.pool, self.calls.model(self.models["exam"]))
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
        if not ids:
            out["notes"].append("no lost training match this round, so nothing to study")
            return out
        before = self.calls.taken
        study_m, open_m = self.calls.model(self.models["study"]), self.calls.model(self.models["open"])
        lessons = Lessons(self.db, judge=judge_mod.Judge(model=open_m))
        examiner = lessons.examiner = night.Counted(self._exam(lessons))
        study = night.LinkedStudy(self.db, self.plug, proposer=parts.Proposer(model=study_m),
                                  tagger=parts.Tagger(model=study_m), fit=parts.FitCheck(model=open_m),
                                  adapter=parts.Adapter(model=open_m), others=(), lessons=lessons,
                                  ideas=parts.Ideas(model=study_m))
        study.log = _Only(study.log, ids)
        until = float(self.now())
        rep = study.run(until - (longest(self.plug) + 2) * DAY, until, now=until)
        out["notes"] += rep["notes"]
        for card in rep["cards"]:
            out["lessons"].append(self._gate(lessons, examiner, card["lesson_id"], until))
        for one in out["lessons"]:
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
        return {"lesson_id": lesson_id, "text": les["text"], "risk": les["risk"], "state": les["state"],
                "passed": passed, "handed": handed, "waits_for_yes": passed and not handed and les["state"] == WAITING,
                "why": exam_mod.held_line(row), "gate": exam_mod.effect_of(row)}


class _Only:
    """The study's log, reading only the round's cases (Log.window and its agent's view)."""

    def __init__(self, log, ids):
        self.log, self.ids = log, set(ids)

    def window(self, since, until, *, agent=None):
        return {k: v for k, v in self.log.window(since, until, agent=agent).items() if k in self.ids}

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
    text += f"; eval gate fixed {one['fixed']}, broke {one['broke']}; {one['calls']} model calls"
    if one.get("stopped") == "cap":
        text += "; stopped at the model call cap"
    return text
