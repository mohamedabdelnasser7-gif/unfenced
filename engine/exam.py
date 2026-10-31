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
"""
import json
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
NOT_RUN = "error"  # the check name saved when the exam itself could not run
RERUN = "arena_rerun"  # the check name of the eval gate's Arena rerun of past wins (arena/gate.py)


@dataclass(frozen=True)
class Row:
    situation: int
    name: str
    part: str
    passed: bool
    check: str = ""
    why: str = ""


@dataclass
class Result:
    passed: bool
    rows: list = field(default_factory=list)
    calls: int = 0

    @property
    def first(self):
        """The first failed Row, or None."""
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
    return f"failed the exam: situation {row.situation}, check {row.check}"


def could_not_run(why):
    """The Result of an exam that raised: failed, so the lesson is held (fail closed)."""
    return Result(passed=False, rows=[Row(None, "", "", False, NOT_RUN, _one_line(why))])


def load(path, stages):
    """Read and check a situations file. ValueError names the first thing wrong."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
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


def sit(situations, answer, checks, names, lesson=None, *, stop_at_first=False):
    """Run every situation once: answer it, then run each named check on what it did. A name with no
    check fails every situation. stop_at_first: stop at the first failed situation (the gate
    before a trial). Returns a Result; calls sums each did["calls"]."""
    rows, calls = [], 0
    for s in situations:
        try:
            did = answer(s, lesson)
            calls += int(did.get("calls") or 0)
        except Exception as e:
            rows.append(Row(s["id"], s["name"], s["part"], False, "answer", _one_line(f"the answer raised: {e}")))
        else:
            rows.append(_checked(s, did, checks, names))
        if stop_at_first and not rows[-1].passed:
            break
    return Result(passed=all(r.passed for r in rows) and len(rows) == len(situations), rows=rows, calls=calls)


def _checked(s, did, checks, names):
    for name in names:
        fn = checks.get(name)
        if fn is None:
            return Row(s["id"], s["name"], s["part"], False, name, "no such check")
        try:
            why = fn(s, did)
        except Exception as e:
            why = f"the check raised: {e}"
        if why:
            return Row(s["id"], s["name"], s["part"], False, name, _one_line(why))
    return Row(s["id"], s["name"], s["part"], True)


def save(c, agent, lesson_id, result, now=None):
    """Write the exam a lesson took, in the caller's transaction."""
    first = result.first
    c.execute("INSERT INTO lesson_exams (lesson_id, agent, passed, situation, check_name, why, calls, parts, at) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (lesson_id, agent, int(result.passed), first.situation if first else None,
               first.check if first else None, first.why if first else None, int(result.calls),
               json.dumps(result.parts(), ensure_ascii=False), time.time() if now is None else now))


def of(c, agent, lesson_id):
    """The exam row of one lesson as a dict, or None."""
    r = c.execute("SELECT * FROM lesson_exams WHERE lesson_id = ? AND agent = ?", (lesson_id, agent)).fetchone()
    return None if r is None else dict(r)


def held_line(row):
    """The line for a lesson held by its exam row (a dict from of()), or "" when it passed or has none."""
    if not row or row["passed"]:
        return ""
    return fail_line(Row(row["situation"], "", "", False, row["check_name"] or ""))


def _one_line(text):
    return " ".join(str(text).split())[:300]
