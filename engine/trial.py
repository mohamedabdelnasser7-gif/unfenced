"""The trial: a lesson on trial is given in its share of cases until its end date (the same
case always gets the same answer, lessons.in_share), and each night check() compares it
with the old way over the same days, then keeps it, pulls it, pauses it, or ends it unclear.

1. The two sides. A case counts when it has an action at a stage the lesson fits ("all"
   fits every stage) between the trial's start (Lessons.trial) and its end date. With: the
   lesson was given in one of those actions. Without: it was not. Each case is read from
   its first counted action (on the with side, the first one given the lesson) up to now,
   so a result from before the lesson never settles it, and a result that came after the
   end date still counts. A row imported from a business's past data (log.is_history) is
   never counted, even when its time falls inside the trial: old data suggests, new results
   decide.
2. The stop rule, on fast results, while the trial is live. Harm: one of the plug's harm
   results in a case, from the first counted action on (on the with side, from the first
   one given the lesson), a result with a cause outside the agent left out. The trial
   pauses when at least STOP_CASES (3) cases with the lesson had harm and their harm rate
   is at least STOP_TIMES (2) times the rate of the cases without it; one bad case never
   pauses it, and with fewer than MIN_CASES (5) cases without it there is nothing to compare
   yet. A pause ends the trial now (Lessons.pause): the lesson is given in no new case and
   waits for a person to keep it or pull it; no number decides it after a pause.
3. A serious case. One case with the lesson and a result the plug names serious, with no
   cause outside the agent, pings the person: a ping mark, once for each such row (the
   database keeps one ping a row), after a pause too. A ping is on the first night's
   report that check() returns, and a reported mark says so; a night that fails before
   check() returns leaves the ping for the next night. Reported means returned by check():
   a runner that fails after that loses the ping. Nothing is sent from here.
4. The verdict, on the deciding results, once the end date has passed. A case is settled by its
   last deciding result, or past its window (study.settle); pending is never a loss and a
   settled case with a cause outside the agent is left out. While a counted case is still
   pending the verdict waits, at most the longest deciding window after the end date; then
   it decides on the settled cases. Kept when each side has at least MIN_CASES settled
   cases from MIN_SOURCES sources (the study's bar), the chance it is better
   (study.chance_better) is at least CHANCE, 75%, and its worst likely cost is at most the
   limit: the lesson's own when a person moved it before the start (set_limit), else the
   plug's trial worst_cost. All of it is fixed when the trial starts: the limit, and the
   plug's good and bad results with the days each takes to show, harm and serious results,
   copied into the trial (Lessons.trial); a plug changed later does not move a trial
   already running, nor stop it when it renames a result. Kept
   leaves the plug's holdback on the old way. Pulled otherwise, and
   the why says it plainly; when a person said yes to the lesson, or it was their own, the
   why says that it lost. Unclear when a side has too few settled cases or sources to tell
   (Mohamed's call 13A): an unclear mark, once for each end date; nothing else about the
   lesson changes, so with its end date passed it is given in no case and frees its stage,
   and no number decides it again until a person keeps it on trial longer (extend, a longer
   mark, the days it waited not counted) or drops it (a pull whose why starts DROPPED). The
   why says whose idea it was in each ending, plainly and first, with the counts: "Mona's
   idea lost: 9 of 20 good with it, 14 of 20 without." or "The agent's lesson won: ...";
   an idea (a lesson with no past cases behind it) is named an idea. A lesson that went on trial under Accept high
   risk had no person's yes, and its why says it started under Accept high risk and who
   switched it on, never that a person said yes.
5. Turns. After the night's pauses and verdicts, the lessons waiting their turn start on
   the stages that are free (Lessons.start_turns).

Every entry links back: the lesson id, its source and source lesson, the case ids on each
side with the row that settled each one, the action rows given the lesson, and the lessons
a "replace it?" card named with it. Pauses, pings, reported pings, limits, verdicts, unclear
ends and keep longer answers are kept as marks
that are never changed nor deleted, one verdict and one pause a lesson. A pause, a keep or
a pull is written in one transaction with its mark, and only when the lesson was still as
the night read it; when someone changed it meanwhile the night writes nothing for it and
says so. check() returns the night as plain data.
"""
import json
import time
from dataclasses import replace
from types import MappingProxyType

from engine.lessons import (ALL, FROM_STUDY, IDEA, PERSON, TRYING, WAITING, Lessons, meet,  # noqa: F401 (FROM_STUDY: its old home)
                            person_whose)
from engine.log import Log, is_history
from engine.plug import SLOW, Decides, Harm, Result
from engine.study import (BAD, CHANCE, GOOD, LEFT_OUT, MIN_CASES, MIN_SOURCES, PENDING, chance_better, longest,
                          settle)

DAY = 86400
STOP_TIMES = 2.0   # harm at about double the old way pauses a trial
STOP_CASES = 3     # cases with the lesson and harm, at least, before a pause
LONGER_DAYS = 90   # the most whole days a person may keep an unclear lesson on trial longer at once
KEPT, PULLED, PAUSED, ON_TRIAL, WAITS = "kept", "pulled", "paused", "on trial", "waiting for results"
UNCLEAR = "unclear"
CHANGED = "changed meanwhile"
CHANGED_WHY = "Someone changed it while the night ran, so the night wrote nothing for it."
DROPPED = "unclear, dropped by "  # the why of an unclear lesson a person dropped, before who
UNCLEAR_ASK = "It is given in no case now and waits for a person to keep it on trial longer or drop it."

def _whose(who):
    """A person's name as the owner of a line (lessons.person_whose)."""
    return person_whose(who)


KINDS = ("limit", "longer", "paused", "ping", "reported", "unclear", "verdict")
_MARKS = """
CREATE TABLE IF NOT EXISTS trial_marks (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  lesson_id INTEGER NOT NULL REFERENCES lessons (id),
  kind TEXT NOT NULL CHECK (kind IN ('limit', 'longer', 'paused', 'ping', 'reported', 'unclear', 'verdict')),
  case_id TEXT,
  row_id INTEGER,
  value REAL,
  by TEXT,
  detail TEXT,
  at REAL NOT NULL
);
"""
_GUARDS = """
CREATE INDEX IF NOT EXISTS trial_marks_lesson ON trial_marks (lesson_id, kind);
CREATE UNIQUE INDEX IF NOT EXISTS trial_marks_one_verdict ON trial_marks (lesson_id) WHERE kind = 'verdict';
CREATE UNIQUE INDEX IF NOT EXISTS trial_marks_one_pause ON trial_marks (lesson_id) WHERE kind = 'paused';
CREATE UNIQUE INDEX IF NOT EXISTS trial_marks_one_ping ON trial_marks (lesson_id, row_id) WHERE kind = 'ping';
CREATE UNIQUE INDEX IF NOT EXISTS trial_marks_one_reported ON trial_marks (lesson_id, row_id) WHERE kind = 'reported';
CREATE UNIQUE INDEX IF NOT EXISTS trial_marks_one_unclear ON trial_marks (lesson_id, value) WHERE kind = 'unclear';
CREATE TRIGGER IF NOT EXISTS trial_marks_never_changed BEFORE UPDATE ON trial_marks
BEGIN SELECT RAISE(ABORT, 'a trial mark is never changed'); END;
CREATE TRIGGER IF NOT EXISTS trial_marks_never_deleted BEFORE DELETE ON trial_marks
BEGIN SELECT RAISE(ABORT, 'a trial mark is never deleted'); END;
CREATE TRIGGER IF NOT EXISTS trial_marks_never_replaced BEFORE INSERT ON trial_marks
WHEN EXISTS (SELECT 1 FROM trial_marks WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'a trial mark is never replaced'); END;
CREATE TRIGGER IF NOT EXISTS trial_limits_before_the_start BEFORE INSERT ON trial_marks
WHEN NEW.kind = 'limit' AND NOT EXISTS (SELECT 1 FROM lessons WHERE id = NEW.lesson_id AND state = 'waiting')
BEGIN SELECT RAISE(ABORT, 'a limit is set before the trial starts'); END;
"""
SCHEMA = _MARKS + _GUARDS
_COLUMNS = "id, agent, lesson_id, kind, case_id, row_id, value, by, detail, at"
_COPIED = _COLUMNS.replace("kind", "CASE kind WHEN 'sent' THEN 'reported' ELSE kind END")  # 'sent' was its old name
_REBUILD = ("BEGIN IMMEDIATE;" + _MARKS.replace("IF NOT EXISTS trial_marks (", "trial_marks_new (", 1)
            + f"INSERT INTO trial_marks_new ({_COLUMNS}) SELECT {_COPIED} FROM trial_marks;\n"
            "DROP TABLE trial_marks;\nALTER TABLE trial_marks_new RENAME TO trial_marks;\n" + _GUARDS + "COMMIT;")


def ready(db):
    """The marks table, made or brought up to date. A table made before a kind of mark existed
    (its CHECK lacks one of KINDS) is rebuilt in one transaction: the same rows with the same
    ids, its indexes and its guards."""
    db.script(SCHEMA)
    with db.tx() as c:
        row = c.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'trial_marks'").fetchone()
        if all(f"'{k}'" in row["sql"] for k in KINDS):
            return
        c.executescript(_REBUILD)


def worst_cost(good_a, n_a, good_b, n_b):
    """The worst likely cost of keeping side a instead of side b: on average, the share of cases
    that lose the good result by keeping a, E[max(rate b - rate a, 0)], counting nothing where a
    does better. A plain average over every outcome, not an average over only the outcomes where
    a is worse. Each side is read as Beta(1 + good, 1 + not good) as in chance_better. Exact for
    whole counts."""
    mean_a, mean_b = (1 + good_a) / (2 + n_a), (1 + good_b) / (2 + n_b)
    loss = (mean_b * chance_better(good_b + 1, n_b + 1, good_a, n_a)
            - mean_a * chance_better(good_b, n_b, good_a + 1, n_a + 1))
    return max(0.0, loss)


class Trials:
    """One agent's trials: the nightly check, the stop rule, the verdict and the marks."""

    def __init__(self, db, plug, *, lessons=None):
        self.db = db
        self.plug = plug
        self.log = Log(db, plug)
        self.lessons = Lessons(db, plug) if lessons is None else lessons
        if self.lessons.agent != plug.agent:
            raise ValueError("a trial and its lessons belong to one agent")
        ready(self.db)

    def set_limit(self, lesson_id, worst, by, *, now=None):
        """A person moves the worst likely cost one lesson may have, before its trial starts: a
        share of cases from 0 to 1. True when the lesson waits, for a yes or its turn; once its
        trial starts its limit is fixed and the database refuses a new one."""
        worst = float(worst)
        if not 0 <= worst <= 1:
            raise ValueError("a worst likely cost is from 0 to 1")
        if not isinstance(by, str) or not by.strip() or "\n" in by:
            raise ValueError("by: one line of text")
        les = self.lessons.get(lesson_id)
        if les is None or les["state"] != WAITING:
            return False
        with self.db.tx() as c:
            return self._mark(c, lesson_id, "limit", value=worst, by=by.strip(), now=now)

    def limit(self, lesson_id):
        """{worst_cost, by}: the lesson's own limit, the last a person set before its trial
        started, else the plug's as copied when the trial started (the plug's now when it has
        not started, or started before that record)."""
        return self._limit(lesson_id, self._judged_by(self.lessons.trial(lesson_id)))

    def _limit(self, lesson_id, p):
        with self.db.tx() as c:
            row = c.execute("SELECT value, by FROM trial_marks WHERE lesson_id = ? AND agent = ? AND kind = 'limit' "
                            "ORDER BY id DESC LIMIT 1", (lesson_id, self.plug.agent)).fetchone()
        if row is None:
            return {"worst_cost": p.trial_worst_cost, "by": "plug"}
        return {"worst_cost": row["value"], "by": row["by"]}

    def _judged_by(self, trial):
        """The plug as the trial was fixed when it started: its limit, the results that settle a
        case and the days each takes to show, its harm and serious results; the plug as it is
        when nothing was copied, and the plug's windows for a trial from before they were."""
        if trial is None or trial["good"] is None:
            return self.plug
        results = dict(self.plug.results)
        for name, days in (trial["windows"] or {}).items():  # a result the plug no longer declares
            was = results.get(name)
            results[name] = (replace(was, shows_in_days=tuple(days)) if was is not None
                             else Result(name, SLOW, tuple(days), None, ""))
        return replace(self.plug, trial_worst_cost=trial["worst_cost"], results=MappingProxyType(results),
                       decides=Decides(trial["good"], tuple(trial["bad"])),
                       harm=Harm(tuple(trial["harm"]), self.plug.harm.about, tuple(trial["serious"])))

    def marks(self, lesson_id, kind=None):
        """The lesson's marks, oldest first, each with its detail read back."""
        sql, args = "SELECT * FROM trial_marks WHERE lesson_id = ? AND agent = ?", [lesson_id, self.plug.agent]
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        with self.db.tx() as c:
            rows = [dict(r) for r in c.execute(sql + " ORDER BY id", args)]
        for r in rows:
            r["detail"] = json.loads(r["detail"]) if r["detail"] else None
        return rows

    def check(self, now=None):
        """One night's check of every lesson on trial. Returns {agent, at, trials, pings, started}."""
        now = time.time() if now is None else float(now)
        rep = {"agent": self.plug.agent, "at": now, "trials": [], "pings": [], "started": []}
        for les in self.lessons.mine(TRYING):
            trial = self.lessons.trial(les["id"])
            if trial is None or trial["started_at"] is None or trial["started_at"] > now:
                continue
            p = self._judged_by(trial)
            entry = self._entry(p, les, trial["started_at"], now)
            self._pings(les, entry, now)
            paused = self.marks(les["id"], "paused")
            unclear = open_unclear(les, self.marks(les["id"], "unclear"))
            if paused:
                entry.update(status=PAUSED, paused_at=paused[0]["at"],
                             why="Paused by the stop rule; it waits for a person to keep it or pull it.")
            elif les["ends_at"] > now:
                self._stop(p, les, entry, now)
            elif unclear is not None:  # no number decides it again until a person answers
                entry.update(status=UNCLEAR, unclear_at=unclear["at"],
                             why=f"Its trial ended unclear, with too few results to tell. {UNCLEAR_ASK}")
            else:
                self._verdict(p, les, entry, now)
            rep["trials"].append(entry)
        rep["started"] = self.lessons.start_turns(now)
        rep["pings"] = self._report(now)  # last, so a night that fails before here leaves its pings for the next
        return rep

    def _entry(self, p, les, start, now):
        """The lesson's two sides over its trial days, as plain data with every link; p: the plug
        as the trial was fixed when it started."""
        end = min(les["ends_at"], now)
        gaps = _gaps(self.marks(les["id"], "longer"))  # the days it waited, unclear, for a person: not counted
        sides = {"with": [], "without": []}
        for case_id, rows in self.log.window(start, now).items():
            rows = [r for r in rows if not is_history(r)]  # old data suggests; only new results judge a trial
            counted = [i for i, r in enumerate(rows) if r["action"] is not None and start <= r["at"] < end
                       and (ALL in les["stages"] or r["stage"] in les["stages"])
                       and not any(a <= r["at"] < b for a, b in gaps)]
            if not counted:
                continue
            given = [i for i in counted if les["id"] in rows[i]["lessons"]]
            first = given[0] if given else counted[0]
            status, deciding, causes, cut = settle(p, rows[first:], now)
            after = [r for r in rows[first:] if not r["cause"]]
            sources = [r["source"] for r in rows if r["source"] is not None]
            sides["with" if given else "without"].append({
                "case": case_id, "source": sources[-1] if sources else None, "status": status, "result": deciding,
                "row": rows[first + cut]["id"] if cut is not None else None, "causes": causes,
                "given": [rows[i]["id"] for i in given],
                "harm": [{"row": r["id"], "result": r["result"]} for r in after if r["result"] in p.harm.results],
                "serious": [{"row": r["id"], "result": r["result"], "at": r["at"]} for r in after
                            if r["result"] in p.harm.serious]})
        links = self.lessons.clashes(les["id"])
        return {"lesson_id": les["id"], "line": les["text"], "stages": les["stages"], "status": ON_TRIAL,
                "started_at": start, "ends_at": les["ends_at"], "source": les["source"],
                "source_lesson_id": les["source_lesson_id"], "replaces": links["replaces"],
                "replaced_by": links["replaced_by"], "with": _side(sides["with"]), "without": _side(sides["without"]),
                "chance": None, "worst_cost": None, "limit": self._limit(les["id"], p), "harm": None, "person": None,
                "why": ""}

    def _pings(self, les, entry, now):
        """A ping mark for each serious row with the lesson not pinged before; the database keeps
        one ping mark a row. The mark is the ping until a night's report carries it (_report)."""
        for case in entry["with"]["list"]:
            for s in case["serious"]:
                ping = {"lesson_id": les["id"], "line": les["text"], "case": case["case"], "row": s["row"],
                        "result": s["result"], "at": s["at"],
                        "why": f'One case with this lesson had "{s["result"]}", a result the plug names serious.'}
                with self.db.tx() as c:
                    self._mark(c, les["id"], "ping", case_id=case["case"], row_id=s["row"], detail=ping, now=now,
                               once=True)

    def _report(self, now):
        """The night's pings: every ping mark of this agent with no reported mark, oldest first,
        each marked reported as check() returns it. Reported means returned by check(), not
        delivered: a runner that fails after that loses the ping. A night that fails before
        this leaves them for the next; the database keeps one reported mark a row, so two
        nights at once never report one row twice."""
        out = []
        with self.db.tx() as c:
            rows = c.execute("SELECT * FROM trial_marks p WHERE p.agent = ? AND p.kind = 'ping' AND NOT EXISTS "
                             "(SELECT 1 FROM trial_marks s WHERE s.agent = p.agent AND s.kind = 'reported' "
                             "AND s.lesson_id = p.lesson_id AND s.row_id = p.row_id) ORDER BY p.id",
                             (self.plug.agent,)).fetchall()
            for r in rows:
                if self._mark(c, r["lesson_id"], "reported", case_id=r["case_id"], row_id=r["row_id"], now=now,
                              once=True):
                    out.append(json.loads(r["detail"]))
        return out

    def _stop(self, p, les, entry, now):
        """The stop rule while the trial is live: pause at about double the harm of the old way."""
        w, wo = entry["with"], entry["without"]
        rate_w = w["harm"] / w["cases"] if w["cases"] else 0.0
        rate_wo = wo["harm"] / wo["cases"] if wo["cases"] else None
        times = None if not rate_wo else rate_w / rate_wo
        entry["harm"] = {"with": w["harm"], "without": wo["harm"], "rate_with": rate_w, "rate_without": rate_wo,
                         "times": times, "results": list(p.harm.results)}
        if w["harm"] < STOP_CASES or wo["cases"] < MIN_CASES or rate_w < STOP_TIMES * rate_wo:
            entry["why"] = (f'On trial until its end date. Harm with it in {w["harm"]} of {w["cases"]} cases, '
                            f'without it in {wo["harm"]} of {wo["cases"]}.')
            return
        why = (f'Paused early: harm with it in {w["harm"]} of {w["cases"]} cases, without it in '
               f'{wo["harm"]} of {wo["cases"]}, ' +
               (f"{times:.1f} times the old way" if times else "where the old way had none") +
               "; it waits for a person to keep it or pull it.")
        with self.db.tx() as c:  # the pause and its mark go in together, or neither
            done = self.lessons.pause(les["id"], now, c=c)
            if done:
                entry.update(status=PAUSED, why=why)
                self._mark(c, les["id"], "paused", value=times, detail=entry, now=now)
        if not done:
            entry.update(status=CHANGED, why=CHANGED_WHY)

    def _verdict(self, p, les, entry, now):
        """At the end: wait for pending results, then kept or pulled by the numbers alone, or
        unclear when a side has too few settled cases or sources to tell."""
        w, wo = entry["with"], entry["without"]
        if (w["pending"] or wo["pending"]) and now < les["ends_at"] + longest(p) * DAY:
            entry["status"] = WAITS
            entry["why"] = (f'Its trial ended; {w["pending"] + wo["pending"]} cases still wait for their result, '
                            "and a result that has not come is never a loss.")
            return
        g1, n1, g0, n0 = w["good"], w["settled"], wo["good"], wo["settled"]
        chance, cost, limit = chance_better(g1, n1, g0, n0), worst_cost(g1, n1, g0, n0), entry["limit"]["worst_cost"]
        entry.update(chance=chance, worst_cost=cost)
        good = p.decides.good
        counts = (f"The chance it is better is {round(chance * 100)}%, its worst likely cost about "
                  f"{_per100(cost)} in 100 cases "
                  f"(the limit is {_per100(limit)}).")
        unclear = True
        if min(n1, n0) < MIN_CASES:
            why = f"Too few settled cases to tell: a verdict needs {MIN_CASES} on each side."
        elif min(w["sources"], wo["sources"]) < MIN_SOURCES:
            why = f"Too few sources to tell: a verdict needs {MIN_SOURCES} on each side."
        else:
            unclear = False
            if chance < 0.5:
                why = "It did worse than the old way."
            elif chance < CHANCE:
                why = f"It was not clearly better: {round(CHANCE * 100)}% is needed."
            elif cost > limit:
                why = "Its worst likely cost is over the limit."
            else:
                why = None
        entry["person"] = self._person(les, lost=None if unclear else why is not None, counts=(g1, n1, g0, n0, good),
                                        chance=chance)
        said = entry["person"]["said"]
        if unclear:
            entry.update(status=UNCLEAR, why=f"Unclear. {said} {why} {UNCLEAR_ASK} {counts}")
        elif why is None:
            entry.update(status=KEPT, holdback=self.plug.trial_holdback,
                         why=(f"Kept. {said} {counts} {round(self.plug.trial_holdback * 100)}% of cases keep the old "
                              "way, so a lesson that does nothing is caught later."))
        else:
            entry.update(status=PULLED, why=f"Pulled. {said} {why} {counts}")
        with self.db.tx() as c:  # the verdict and its mark go in together, and only on a lesson still on trial
            if unclear:  # nothing about the lesson changes: its end date has passed, so it is given in no case
                done = self._mark_unclear(c, les, entry, now)
            elif why is None:
                done = self.lessons.keep(les["id"], holdback=self.plug.trial_holdback, c=c)
            else:
                done = self.lessons.pull(les["id"], entry["why"], now=now, on_trial=True, c=c)
            if done and not unclear:
                self._mark(c, les["id"], "verdict", value=chance, detail=entry, now=now)
        if not done:
            entry.pop("holdback", None)
            entry.update(status=CHANGED, why=CHANGED_WHY)

    def _mark_unclear(self, c, les, entry, now):
        """The unclear mark, its value the end date it judged, written only while the lesson is
        still on trial with that end date; the database keeps one for each end date. True when
        written."""
        cur = c.execute("INSERT INTO trial_marks (agent, lesson_id, kind, value, detail, at) "
                        "SELECT ?, ?, 'unclear', ?, ?, ? WHERE EXISTS (SELECT 1 FROM lessons WHERE id = ? AND agent = ? "
                        "AND state = 'trying' AND ends_at = ?) ON CONFLICT DO NOTHING",
                        (self.plug.agent, les["id"], les["ends_at"], json.dumps(entry, ensure_ascii=False), now,
                         les["id"], self.plug.agent, les["ends_at"]))
        return cur.rowcount == 1

    def _person(self, les, *, lost, counts, chance=None):
        """Whose idea the lesson was, a person's own line or the agent's, whether it won or lost
        with the counts behind that, and who said yes to it, said plainly first: "Mona's idea
        lost: 9 of 20 good with it, 14 of 20 without." An idea (a lesson with no past cases
        behind it) is named an idea, a pattern the study found a lesson. lost None: too few
        results to tell. counts: (good with, settled with, good without, settled without, the
        good result). chance: a pulled lesson that was ahead (a chance of 0.5 or more) did
        not win rather than lost. accept_high True: no person said yes; the agent's lesson went on trial
        under Accept high risk, by names who switched it on, and the line says that, never a yes."""
        own = les.get("origin") == PERSON
        who = les["yes_by"]
        trial = None if own or who is None else self.lessons.trial(les["id"])
        acc = None if trial is None else trial["accept_high"]
        kind = "idea" if les.get("kind") == IDEA else "lesson"
        owner = (person_whose(who) if own else "the agent's") + " " + kind
        g1, n1, g0, n0, good = counts
        numbers = f"{g1} of {n1} {good} with it, {g0} of {n0} without."
        said = (f"Too few results to tell if {owner} won: {numbers}" if lost is None
                else f"{_first_up(owner)} {_ending(lost, chance)}: {numbers}")
        if acc is not None:  # its yes column holds the switch's mark, not a person's yes
            who = acc["by"]
            said += f" It started under Accept high risk (switched on by {who}), with no person's yes."
        elif who is not None and not own:
            said += f" {_first_up(who)} said yes to it."
        return {"idea": PERSON if own else "agent", "kind": les.get("kind"), "by": who, "own": own, "lost": lost,
                "accept_high": acc is not None, "said": said}

    def unclear(self, lesson_id, now=None):
        """None when the lesson does not wait for a person after an unclear trial; else {lesson_id,
        ends_at: the end date that passed, mark: the unclear mark with the numbers the verdict
        read (its detail), ahead: the ids of the lessons on trial on its stages now; while there
        are any it is not kept on trial longer, since one trial runs on a stage at a time}."""
        now = time.time() if now is None else float(now)
        les = self.lessons.get(lesson_id)
        mark = open_unclear(les, self.marks(lesson_id, "unclear")) if les is not None else None
        if mark is None or les["ends_at"] > now:
            return None
        with self.db.tx() as c:
            ahead = _ahead(c, self.plug.agent, les, now)
        return {"lesson_id": les["id"], "ends_at": les["ends_at"], "mark": mark, "ahead": ahead}

    def longer(self, lesson_id, days, by, *, now=None):
        """A person keeps an unclear lesson on trial longer: given again in the same share of cases
        until `days` whole days from now (1 to LONGER_DAYS). The trial keeps its start, so the
        numbers so far still count; the days it waited for the person are not counted. A longer
        mark records who, when, the end date that passed and the new one. Returns the new end
        date, or None when the lesson does not wait after an unclear trial, or a lesson is on
        trial on its stages (unclear() names them)."""
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= LONGER_DAYS:
            raise ValueError(f"days: a whole number from 1 to {LONGER_DAYS}")
        by = _by(by)
        now = time.time() if now is None else float(now)
        with self.db.tx() as c:  # read and change under one write lock
            if not c.in_transaction:
                c.execute("BEGIN IMMEDIATE")
            les = _lesson_row(c, self.plug.agent, lesson_id)
            if les is None or not _is_unclear(c, les, now) or _ahead(c, self.plug.agent, les, now):
                return None
            ends_at = now + days * DAY
            if not self.lessons.extend(lesson_id, ends_at, was=les["ends_at"], now=now, c=c):
                return None
            self._mark(c, lesson_id, "longer", value=ends_at, by=by,
                       detail={"from": les["ends_at"], "to": ends_at, "days": days}, now=now)
        return ends_at

    def drop(self, lesson_id, by, *, now=None):
        """A person drops an unclear lesson: pulled, its why "unclear, dropped by <by>". True when
        it was waiting after an unclear trial."""
        by = _by(by)
        now = time.time() if now is None else float(now)
        with self.db.tx() as c:
            if not c.in_transaction:
                c.execute("BEGIN IMMEDIATE")
            les = _lesson_row(c, self.plug.agent, lesson_id)
            if les is None or not _is_unclear(c, les, now):
                return False
            return self.lessons.pull(lesson_id, DROPPED + by, now=now, on_trial=True, c=c)

    def _mark(self, c, lesson_id, kind, *, case_id=None, row_id=None, value=None, by=None, detail=None, now=None,
              once=False):
        """One mark in the caller's transaction. True when written; once: a mark the database
        already holds (one ping a row) is left as it is and False, else it is an error."""
        cur = c.execute("INSERT INTO trial_marks (agent, lesson_id, kind, case_id, row_id, value, by, detail, at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)" + (" ON CONFLICT DO NOTHING" if once else ""),
                        (self.plug.agent, lesson_id, kind, case_id, row_id, value, by,
                         None if detail is None else json.dumps(detail, ensure_ascii=False),
                         time.time() if now is None else float(now)))
        return cur.rowcount == 1


def _side(cases):
    """One side's numbers and its cases."""
    settled = [c for c in cases if c["status"] in (GOOD, BAD)]
    return {"cases": len(cases), "settled": len(settled), "good": sum(c["status"] == GOOD for c in settled),
            "pending": sum(c["status"] == PENDING for c in cases),
            "left_out": sum(c["status"] == LEFT_OUT for c in cases),
            "harm": sum(bool(c["harm"]) for c in cases),
            "sources": len({c["source"] for c in settled if c["source"] is not None}),
            "list": cases}


def open_unclear(les, marks):
    """The unclear mark a lesson waits on, or None: the lesson is on trial and an unclear mark
    judged its current end date (a longer trial moves the end date, so the mark is answered)."""
    if les is None or les["state"] != TRYING:
        return None
    return next((m for m in marks if m["kind"] == "unclear" and m["value"] == les["ends_at"]), None)


def _is_unclear(c, les, now):
    """In the caller's transaction: does the lesson wait for a person after an unclear trial?"""
    return (les["state"] == TRYING and les["ends_at"] <= now and c.execute(
        "SELECT 1 FROM trial_marks WHERE lesson_id = ? AND agent = ? AND kind = 'unclear' AND value = ?",
        (les["id"], les["agent"], les["ends_at"])).fetchone() is not None)


def _ahead(c, agent, les, now):
    """The ids of this agent's other lessons on trial on the lesson's stages now."""
    rows = c.execute("SELECT id, stages FROM lessons WHERE agent = ? AND state = 'trying' AND ends_at > ? AND id != ? "
                     "ORDER BY id", (agent, now, les["id"])).fetchall()
    return [r["id"] for r in rows if meet(les["stages"], [s for s in r["stages"].split(",") if s])]


def _lesson_row(c, agent, lesson_id):
    row = c.execute("SELECT * FROM lessons WHERE id = ? AND agent = ?", (lesson_id, agent)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["stages"] = [s for s in d["stages"].split(",") if s]
    return d


def _gaps(longer):
    """[(from, to)]: the days a lesson waited, unclear, before each longer trial."""
    return [(m["detail"]["from"], m["at"]) for m in longer if isinstance(m.get("detail"), dict)]


def _by(by):
    if not isinstance(by, str) or not by.strip() or "\n" in by or "\r" in by:
        raise ValueError("by: one line of text")
    return by.strip()


def _first_up(text):
    """A sentence's first letter in capitals, the rest as written."""
    return text[:1].upper() + text[1:]


def _per100(share):
    """A share of cases as a number in 100, one decimal when under 10."""
    n = share * 100
    return f"{n:.1f}".rstrip("0").rstrip(".") if n < 10 else str(round(n))


def _ending(lost, chance):
    """Won, lost, or did not win for a pulled lesson that was ahead but not sure enough."""
    if not lost:
        return "won"
    return "did not win" if chance is not None and chance >= 0.5 else "lost"
