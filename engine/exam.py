"""The exam: a fixed set of situations, each with checks in code on what the agent did.

Agent neutral. A plug names its exam (plug key "exam": the situations file and the check
names); a plug with no exam has none, and nothing here runs for it. The agent's own code gives
two things:
  answer(situation, lesson) -> did: a dict of what the agent did, its own keys, plus
      "calls" (model calls made); lesson is the new lesson's text, or None for the kept ones only.
  checks: {name: check(situation, did) -> "" when it passes, else why, one plain line}.
Every check the plug names runs on every situation; a check reads the situation's "expect"
dict to know what applies there. An answer or a check that raises fails that situation, so a
broken exam never passes a lesson.

A situation: {"id": 1..N, "name": a short unique name, "part": the half it belongs to,
"title": one line, "stage": one of the plug's stages, "turns": [dicts, the agent's code reads
them], "expect": {...}}. Ids run 1..N with no gap, so "situation 7" names one situation.

lesson_exams keeps the exam each new lesson took before its trial (engine/lessons.py): one row a
lesson, never changed and never deleted.

The gate's counts (new, 2026-10-31; DECISIONS items 27 and 28). Beside pass or fail, a gate
result can carry pairs: one Pair a case it tested, whether the agent got it right without the
new lesson (before) and with it (after). An exam situation pairs the exam run with the kept
lessons only against the run with the new lesson added; an Arena rerun pairs the past win (right
before, by being a win) against the rerun. From the pairs: fixed = wrong before, right after;
broke = right before, wrong after. A case whose answer raised on either side (a model error, not
the agent's choice) or that could not run is no pair. The counts are reported and saved with the
lesson's exam row; they decide nothing: the pass or fail rule is the one above, so a lesson that
breaks any case the gate requires to hold still fails. Since a pass needs every situation right,
a lesson that passed has no broke from the exam itself.

mcnemar(fixed, broke) is McNemar's exact check, in plain words: it looks only at the cases that
changed and asks how often a lesson that changed nothing would split them this unevenly between
fixed and broken by chance alone (a fair coin per case), so a small p-value (under 0.05) means
the gap is likely real and a large one means it could be chance. With no case changed it makes
no claim (None).

Rows saved before the counts existed, and a lesson whose gate made no pairs, keep the count
columns empty (NULL): "not counted", never zero. ensure() adds the columns to an older database.

The pass rule (new, 2026-11-02; DECISIONS item 75, amends 27). A check is either safety (it blocks)
or style (it is reported in the rows and the counts, never blocking). The plug's exam key names its
safety checks ("safety"); with none, the agent's own binding gives its default list (safety_of), and
every other check is style. Each
row keeps every check that failed on it (Row.fails), not only the first, so a style fail never hides a
safety one. With the run on the kept lessons only beside it (before), a lesson passes when every
situation was answered with the new line, no safety check fails on a situation where it passed
before, and it fixed at least as many situations as it broke (the counts above, over every check).
With no run before (the gate that stops at the first fail), a lesson passes when no safety check
fails at all. Always blocking, whatever the plug says: an answer that raised with the new line, an
exam that could not run, a check name with no check, and the built agents' good result reached
before and not with the line (ALWAYS). judge() applies the rule; Result.blocked names the row that
held the lesson, so its card shows the safety check, never a style one.

A failed gate is kept with the lesson too (new, 2026-10-31; DECISIONS item 50): beside the first
fail, the fails column keeps every failed row of the result (at most MAX_FAILS, first fail first:
the situation or rerun, its name, the check and why), so the night study can tell the
proposer what a failed line broke (engine/study.py). A row that passed, or one saved before the
column, keeps it empty; fails_of() then reads the first fail alone.
"""
import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

TABLE = """
CREATE TABLE IF NOT EXISTS lesson_exams (
  lesson_id INTEGER PRIMARY KEY REFERENCES lessons (id),
  agent TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
  situation INTEGER,
  check_name TEXT,
  why TEXT,
  calls INTEGER NOT NULL DEFAULT 0,
  parts TEXT NOT NULL DEFAULT '{}',
  at REAL NOT NULL
);
CREATE TRIGGER IF NOT EXISTS lesson_exams_never_changed BEFORE UPDATE ON lesson_exams
BEGIN SELECT RAISE(ABORT, 'an exam row is never changed'); END;
CREATE TRIGGER IF NOT EXISTS lesson_exams_never_deleted BEFORE DELETE ON lesson_exams
BEGIN SELECT RAISE(ABORT, 'an exam row is never deleted'); END;
"""
# The gate's counts, added by ensure() (a database from before them gets them empty): fixed and
# broke (cases), p_value (mcnemar, NULL when no case changed) and effect (JSON: the fixed and broken
# case names and the pairs that did not change). All NULL on a row with no counts.
COUNT_COLUMNS = (("fixed", "INTEGER"), ("broke", "INTEGER"), ("p_value", "REAL"), ("effect", "TEXT"))
# The failed rows of a gate that failed, added by ensure() like the counts: JSON, a list of
# {situation, name, part, check, why}. NULL on a row that passed and on rows from before it.
FAIL_COLUMNS = (("fails", "TEXT"),)
MAX_FAILS = 10  # failed rows kept on one exam row
NOT_RUN = "error"  # the check name saved when the exam itself could not run
ANSWER = "answer"  # the check name of a situation whose answer raised (engine sit)
RERUN = "arena_rerun"  # the check name of the eval gate's Arena rerun of past wins (arena/gate.py)
ROUND = "practice_round"  # the check name of a correction's practice round (arena/gate.py CorrectionRound)
LIKELY = 0.05  # a p-value under this reads "likely real"
NO_CHECK = "no such check"  # the why of a check name the agent's code has no check for
COUNTS = "fixed_vs_broke"  # the check name of a lesson that broke more situations than it fixed
GOOD = "good_model_judged"  # the built agents' good result, reached before and not with the line (reflection/turn_exam.py)
ALWAYS = (ANSWER, NOT_RUN, GOOD)  # block whatever the plug's list says


@dataclass(frozen=True)
class Row:
    situation: int
    name: str
    part: str
    passed: bool
    check: str = ""
    why: str = ""
    fails: tuple = ()  # ((check, why), ...): every check that failed here, the first one first


@dataclass(frozen=True)
class Pair:
    """One case the gate tested: right without the new lesson (before), right with it (after)."""
    case: str
    before: bool
    after: bool


@dataclass
class Result:
    passed: bool
    rows: list = field(default_factory=list)
    calls: int = 0
    pairs: list = field(default_factory=list)  # [Pair], the gate's counts; empty when not counted
    blocked: Row | None = None  # the row that held the lesson (judge()); None: the first failed row

    @property
    def first(self):
        """The row that held the lesson when one is named, else the first failed Row, or None."""
        if self.blocked is not None:
            return self.blocked
        return next((r for r in self.rows if not r.passed), None)

    def parts(self):
        """{part: [passed, total]}, each part where it first shows up."""
        out = {}
        for r in self.rows:
            out.setdefault(r.part, [0, 0])
            out[r.part][1] += 1
            out[r.part][0] += r.passed
        return out

    def line(self):
        """The line a held lesson shows: "failed the exam: situation N, check X"; "" when passed."""
        return fail_line(self.first) if not self.passed else ""


def fail_line(row):
    if row is None or row.situation is None:
        return "failed the exam: it could not run"
    if row.check == RERUN:  # its number counts the past wins rerun, not the exam's situations
        return f"failed the Arena rerun of past wins, at rerun {row.situation}"
    if row.check == ROUND:  # its number counts the practice round's matches
        return f"failed the practice round, at match {row.situation}"
    return f"failed the exam: situation {row.situation}, check {row.check}"


def could_not_run(why):
    """The Result of an exam that raised: failed, so the lesson is held (fail closed)."""
    return Result(passed=False, rows=[Row(None, "", "", False, NOT_RUN, _one_line(why))])


def load(path, stages):
    """Read and check a situations file. ValueError names the first thing wrong."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as e:
        raise ValueError(f"exam situations {Path(path).name}: {e}") from None
    sits = data.get("situations") if isinstance(data, dict) else None
    if not isinstance(sits, list) or not sits:
        raise ValueError("exam situations: a JSON object with a non-empty list \"situations\"")
    names = set()
    for i, s in enumerate(sits, 1):
        if not isinstance(s, dict):
            raise ValueError(f"exam situation {i}: an object")
        if s.get("id") != i:
            raise ValueError(f"exam situation {i}: ids run 1 to N with no gap, found {s.get('id')!r}")
        for key in ("name", "part", "title"):
            v = s.get(key)
            if not isinstance(v, str) or not v.strip() or "\n" in v:
                raise ValueError(f"exam situation {i}: {key} is one line of text")
        if s["name"] in names:
            raise ValueError(f"exam situation {i}: the name {s['name']!r} is used twice")
        names.add(s["name"])
        if s.get("stage") not in stages:
            raise ValueError(f"exam situation {i}: stage {s.get('stage')!r} is not a stage of the plug")
        turns = s.get("turns")
        if not isinstance(turns, list) or not turns or not all(isinstance(t, dict) for t in turns):
            raise ValueError(f"exam situation {i}: turns is a non-empty list of objects")
        if not isinstance(s.get("expect"), dict):
            raise ValueError(f"exam situation {i}: expect is an object")
    return sits


def sit(situations, answer, checks, names, lesson=None, *, stop_at_first=False, safety=None):
    """Run every situation once: answer it, then run each named check on what it did (every one, so
    Row.fails names them all). A name with no check fails every situation. safety: the checks that
    block (the pass rule above, with no run before); None: every check blocks. stop_at_first: stop at
    the first situation that blocks (the gate before a trial). Returns a Result; calls sums each
    did["calls"]."""
    rows, calls = [], 0
    for s in situations:
        try:
            did = answer(s, lesson)
            calls += int(did.get("calls") or 0)
        except Exception as e:
            rows.append(Row(s["id"], s["name"], s["part"], False, ANSWER, _one_line(f"the answer raised: {e}")))
        else:
            rows.append(_checked(s, did, checks, names))
        if stop_at_first and blocks(rows[-1], safety):
            break
    if safety is None:
        return Result(passed=all(r.passed for r in rows) and len(rows) == len(situations), rows=rows, calls=calls)
    return judge(rows, None, len(situations), safety, calls=calls)


def _checked(s, did, checks, names):
    fails = []
    for name in names:
        fn = checks.get(name)
        if fn is None:
            fails.append((name, NO_CHECK))
            continue
        try:
            why = fn(s, did)
        except Exception as e:
            why = f"the check raised: {e}"
        if why:
            fails.append((name, _one_line(why)))
    if not fails:
        return Row(s["id"], s["name"], s["part"], True)
    return Row(s["id"], s["name"], s["part"], False, fails[0][0], fails[0][1], tuple(fails))


def safety_of(plug, default):
    """The checks that block a lesson for this plug: its exam key's "safety", else default (the agent's
    own binding's list)."""
    got = getattr(getattr(plug, "exam", None), "safety", None)
    return tuple(default) if got is None else tuple(got)


def _row_fails(row):
    """((check, why), ...) of a row: its fails, or its one check on a row made before fails existed."""
    if row.passed:
        return ()
    return tuple(row.fails) or ((row.check, row.why),)


def _blocking(row, safety):
    """The fails on row that block under safety (None: every fail blocks)."""
    return [(c, w) for c, w in _row_fails(row) if safety is None or c in safety or c in ALWAYS or w == NO_CHECK]


def blocks(row, safety):
    return bool(_blocking(row, safety))


def judge(after, before, total, safety, *, calls=0, pairs=None):
    """The pass rule (see the module's note) on the rows of a run with the new line (after), beside
    the rows of the run on the kept lessons only (before; None when there is none). total: the
    situations the exam has. Returns a Result with the after rows, blocked naming the row that held
    the lesson (its check the blocking one), and pairs (pair_rows when before is given, unless given)."""
    after = list(after)
    if pairs is None:
        pairs = pair_rows(before, after) if before is not None else []
    before_by = {} if before is None else {r.situation: r for r in before if r.situation is not None}
    held = None
    for r in after:
        old = before_by.get(r.situation)
        had = set() if old is None or old.check in (ANSWER, NOT_RUN) else {c for c, _ in _row_fails(old)}
        for c, w in _blocking(r, safety):
            if c in ALWAYS or w == NO_CHECK or c not in had:
                held = Row(r.situation, r.name, r.part, False, c, w, r.fails)
                break
        if held is not None:
            break
    if held is None and len(after) != total:
        held = next((r for r in after if not r.passed), None) or Row(None, "", "", False, NOT_RUN,
                                                                     "not every situation was run")
    if held is None and before is not None:
        eff = effect(pairs)
        if eff is not None and eff["fixed"] < eff["broke"]:
            name = eff["broke_cases"][0]
            r = next((x for x in after if f"situation {x.situation}" == name), None)
            why = f"it broke {eff['broke']} situations and fixed {eff['fixed']}"
            held = Row(r.situation if r else None, r.name if r else "", r.part if r else "", False, COUNTS, why)
    return Result(passed=held is None, rows=after, calls=calls, pairs=list(pairs), blocked=held)


def ensure(db):
    """The lesson_exams table, and the count columns on a table made before them (empty on its old
    rows). Safe to run again, and when another connection added a column first."""
    db.script(TABLE)
    with db.tx() as c:
        have = {r[1] for r in c.execute("PRAGMA table_info(lesson_exams)")}
        for col, kind in COUNT_COLUMNS + FAIL_COLUMNS:
            if col in have:
                continue
            try:
                c.execute(f"ALTER TABLE lesson_exams ADD COLUMN {col} {kind}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e):
                    raise


def save(c, agent, lesson_id, result, now=None):
    """Write the exam a lesson took, with the gate's counts when it has pairs and its failed rows
    when it failed, in the caller's transaction."""
    first = None if result.passed else result.first  # a passed lesson's style fails name no held line
    eff = effect(getattr(result, "pairs", None) or [])
    counts = (None, None, None, None) if eff is None else (
        eff["fixed"], eff["broke"], eff["p"], json.dumps({k: eff[k] for k in ("fixed_cases", "broke_cases", "both_right",
                                                                              "both_wrong")}, ensure_ascii=False))
    fails = None
    if not result.passed:
        failed = [r for r in result.rows if not r.passed]
        if first is not None:  # the row that held it first, with its blocking check
            failed = [first] + [r for r in failed if r.situation != first.situation or first.situation is None
                                and r is not first]
        fails = json.dumps([{"situation": r.situation, "name": r.name, "part": r.part, "check": r.check,
                             "why": _one_line(r.why)} for r in failed][:MAX_FAILS], ensure_ascii=False)
    c.execute("INSERT INTO lesson_exams (lesson_id, agent, passed, situation, check_name, why, calls, parts, at, "
              "fixed, broke, p_value, effect, fails) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (lesson_id, agent, int(result.passed), first.situation if first else None,
               first.check if first else None,
               None if first is None or first.why is None else _one_line(first.why),  # one line, capped (red team item 5)
               int(result.calls),
               json.dumps(result.parts(), ensure_ascii=False), time.time() if now is None else now, *counts, fails))


def of(c, agent, lesson_id):
    """The exam row of one lesson as a dict, or None."""
    r = c.execute("SELECT * FROM lesson_exams WHERE lesson_id = ? AND agent = ?", (lesson_id, agent)).fetchone()
    return None if r is None else dict(r)


def fails_of(row):
    """The failed rows kept on a saved exam row (a dict from of()), each {situation, name, part,
    check, why}; the first fail alone when the row has no fails column filled (saved before it),
    [] when it passed or there is none."""
    if not row or row["passed"]:
        return []
    try:
        kept = json.loads(row.get("fails") or "null")
    except ValueError:
        kept = None
    if isinstance(kept, list) and kept:
        return [k for k in kept if isinstance(k, dict)]
    return [{"situation": row.get("situation"), "name": "", "part": "", "check": row.get("check_name") or "",
             "why": row.get("why") or ""}]


def broke_cases(row):
    """The cases a saved exam row's gate broke (right before the lesson, wrong with it), by name;
    [] when not counted."""
    if not row or not row.get("effect"):
        return []
    try:
        eff = json.loads(row["effect"])
    except ValueError:
        return []
    got = eff.get("broke_cases") if isinstance(eff, dict) else None
    return [str(x) for x in got] if isinstance(got, list) else []


def pair_rows(before, after):
    """The exam's pairs from two exam runs (sit()'s rows, no gate rows): each situation in both
    (by situation id), right without the new lesson (before) and with it (after). A situation whose
    answer raised, or that could not run, on either side is left out."""
    def usable(rows):
        return {r.situation: r for r in rows if r.situation is not None and r.check not in (ANSWER, NOT_RUN)}
    b, a = usable(before), usable(after)
    return [Pair(f"situation {n}", b[n].passed, a[n].passed) for n in sorted(set(b) & set(a))]


def effect(pairs):
    """The counts of a list of Pairs: {fixed, broke, both_right, both_wrong, p, fixed_cases,
    broke_cases}; None for no pairs (not counted)."""
    pairs = list(pairs or [])
    if not pairs:
        return None
    fixed = [p.case for p in pairs if not p.before and p.after]
    broke = [p.case for p in pairs if p.before and not p.after]
    return {"fixed": len(fixed), "broke": len(broke), "p": mcnemar(len(fixed), len(broke)),
            "both_right": sum(p.before and p.after for p in pairs),
            "both_wrong": sum(not p.before and not p.after for p in pairs),
            "fixed_cases": fixed, "broke_cases": broke}


def mcnemar(fixed, broke):
    """McNemar's exact check on the cases that changed (see the module's note): the two-sided
    binomial p-value of `fixed` against `broke` at even odds, min(1, 2 x P(X <= the smaller)),
    X ~ Binomial(fixed + broke, 1/2). None when no case changed: no claim either way."""
    for v in (fixed, broke):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("fixed and broke are counts: whole numbers, 0 or more")
    n = fixed + broke
    if n == 0:
        return None
    tail = sum(math.comb(n, k) for k in range(min(fixed, broke) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def chance_words(fixed, broke, p):
    """The p-value in plain words: likely a real gain, likely real harm, could be chance, or
    nothing changed (no claim)."""
    if p is None:
        return "nothing changed either way"
    if p < LIKELY:
        return "likely a real gain" if fixed > broke else "likely real harm"
    return "could be chance"


def p_text(p):
    """A p-value for a report line: three places at most, "under 0.001" below that."""
    if p is None:
        return "none"
    if p < 0.001:
        return "under 0.001"
    return f"{p:.3f}".rstrip("0").rstrip(".") or "0"


def effect_of(row):
    """The gate's counts on a saved exam row (a dict from of()): {fixed, broke, p, words}, or None
    when the row has none (no row, saved before the counts, or a gate with no pairs)."""
    if not row or row.get("fixed") is None or row.get("broke") is None:
        return None
    fixed, broke = int(row["fixed"]), int(row["broke"])
    p = row.get("p_value")
    p = None if p is None else float(p)
    return {"fixed": fixed, "broke": broke, "p": p, "words": chance_words(fixed, broke, p)}


def effect_line(eff):
    """The counts in one report line: "gate counts: fixed 3, broke 0, McNemar p 0.25 (could be chance)"."""
    if eff["p"] is None:
        return f'gate counts: fixed {eff["fixed"]}, broke {eff["broke"]} ({eff["words"]})'
    return f'gate counts: fixed {eff["fixed"]}, broke {eff["broke"]}, McNemar p {p_text(eff["p"])} ({eff["words"]})'


def held_line(row):
    """The line for a lesson held by its exam row (a dict from of()), or "" when it passed or has none."""
    if not row or row["passed"]:
        return ""
    return fail_line(Row(row["situation"], "", "", False, row["check_name"] or ""))


def _one_line(text):
    return " ".join(str(text).split())[:300]
