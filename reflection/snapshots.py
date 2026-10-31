"""Snapshots: a copy of one agent's lessons at the end of each night, and a way back to one.

    python3 -I reflection/snapshots.py rollback --plug PLUG --to NIGHT [--db PATH] [--by NAME] [--bring-back] [--yes CODE]

(python3 -m reflection.snapshots works too; with -I, -m does not find the repo's packages, so
the file is run by its path, as sim/run.py is.)

At the end of each night (reflection/night.py, after the trial check and the study) take()
writes one snapshot of the agent: every lesson id with its state, its trial (waits its turn,
on trial, paused, ended, decided, or none), its score and whether it was given that night
(live), the night's date (UTC, as on the night report) and a hash of the set. Snapshots live
in one table in the database, kept like the trial marks: never changed, never deleted, never
replaced. Taking the same night again with the same set writes nothing; a night run again
the same day with a changed set adds a newer copy, and a night's snapshot is its newest copy.

diff() says what changed between two snapshots: lessons added, put on trial, kept, pulled,
and the ones still waiting. The night report carries it in plain words, since the last
night before.

rollback shows the plan first and changes nothing without --yes. The plan, for each lesson:
  pull              given now but not given that night; waiting its turn now (it would
                    start by itself) when it was not waiting its turn that night; or on a
                    trial that started since and was paused or has ended (a verdict or a
                    person could still keep it).
  stays             given that night and now.
  bring back        given that night and pulled since: with --bring-back it comes back
                    through Lessons.bring_back, as a new lesson on trial (or waiting
                    its turn), linked to the pulled one, which stays pulled.
  already back      given that night and pulled since, but its line is back already: a
                    lesson of its bring back family is not pulled (named).
  cannot come back  given that night but not now because its trial was paused or ended
                    since (a trial never starts again).
  left waiting      added since and waiting for a yes: it changes nothing until a person
                    answers, so it is left on the morning page.
A lesson brought back since from a line given that night stands for that line: it stays
when it is given now or waits its turn, and cannot come back when its trial was paused or
ended since; it is never pulled as "added after that night".
When it would pull or bring back, the plan ends with the command to do it: --yes and the
plan's code (12 characters of a sha256 of the snapshot, the lessons it would pull and the
lessons it offers to bring back, each with its line), and --bring-back too when it offers to
bring back. --yes reads the plan again under the write lock and refuses, changing nothing,
when its code differs: a plan that changed after it was shown (a yes or a Bring back on the
morning page, a night run between) is never acted on unseen. With --yes the pulls go
through Lessons.pull only, each why naming the rollback and who signed it; with
--bring-back too, each lesson offered comes back through Lessons.bring_back, signed by the
same person, after the pulls; and the rollback is written as its own snapshot row (kind
rollback: who, which snapshot, what it pulled, what it brought back and as which lesson,
what it offered and did not bring back, what could not come back), all in one transaction.
A lesson row is never rewritten nor deleted; a pull and a new lesson brought back are the
only changes, as on the morning page.

--plug is a plug file or the agent name of a plug in this repo (<folder>/plug.json). An
unknown plug, an agent with no snapshot, a night with no snapshot, or a snapshot that no
longer matches its hash is refused and nothing changes.
"""
import argparse
import datetime
import hashlib
import json
import re
import shlex
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I, as sim/run.py is
    sys.path.insert(0, str(ROOT))

from engine import plug as plug_mod  # noqa: E402
from engine.lessons import KEPT, PULLED, TRYING, WAITING, back_copy, back_family, returns_in  # noqa: E402
from engine.lessons import Lessons as EngineLessons  # noqa: E402
from kit.db import DEFAULT_PATH, Db  # noqa: E402

BY = "the user"   # who signs a rollback unless --by names someone
SHORT = 12         # hash characters shown
WAITS_TURN, ON_TRIAL, PAUSED, ENDED, DECIDED = "waits its turn", "on trial", "paused", "ended", "decided"
PULL, STAYS, CANNOT, LEFT = "pull", "stays", "cannot come back", "left waiting"
BACK, ALREADY = "bring back", "already back"
_NIGHT = re.compile(r"\d{4}-\d{2}-\d{2}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson_snapshots (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('night', 'rollback')),
  night TEXT NOT NULL CHECK (night GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  at REAL NOT NULL,
  lessons TEXT NOT NULL,
  hash TEXT NOT NULL,
  by TEXT,
  detail TEXT,
  CHECK ((kind = 'rollback') = (by IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS lesson_snapshots_night ON lesson_snapshots (agent, kind, night);
CREATE TRIGGER IF NOT EXISTS lesson_snapshots_never_changed BEFORE UPDATE ON lesson_snapshots
BEGIN SELECT RAISE(ABORT, 'a snapshot is never changed'); END;
CREATE TRIGGER IF NOT EXISTS lesson_snapshots_never_deleted BEFORE DELETE ON lesson_snapshots
BEGIN SELECT RAISE(ABORT, 'a snapshot is never deleted'); END;
CREATE TRIGGER IF NOT EXISTS lesson_snapshots_never_replaced BEFORE INSERT ON lesson_snapshots
WHEN EXISTS (SELECT 1 FROM lesson_snapshots WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'a snapshot is never replaced'); END;
"""
# lesson_snapshots: kind night, one agent's lessons at the end of a night (newest copy of a
# night wins); kind rollback, the lessons right after a rollback to `night`, signed `by`, its
# detail {to, pulled, brought_back: [{id, as}], offered_back, cannot_come_back, left_waiting}
# as JSON. lessons: a JSON list, one
# {id, state, trial, score, live} per lesson, oldest first; hash: sha256 of that list.


class Refused(Exception):
    """A rollback that cannot run as asked; the message says why, and nothing changed."""


def ready(db):
    db.script(SCHEMA)


def night_of(at):
    """The night's date, as the night report writes it (UTC)."""
    return time.strftime("%Y-%m-%d", time.gmtime(float(at)))


def take(db, agent, at):
    """The agent's snapshot at the end of the night at `at`. The newest copy of that night with
    the same hash is returned as it is (written False); otherwise a new copy is written."""
    ready(db)
    night = night_of(at)
    with db.tx() as c:
        if not c.in_transaction:  # read and write under one write lock: two runs never write twice
            c.execute("BEGIN IMMEDIATE")
        lessons = _set(c, agent, at)
        digest = _hash(lessons)
        row = c.execute("SELECT * FROM lesson_snapshots WHERE agent = ? AND kind = 'night' AND night = ? "
                        "ORDER BY id DESC LIMIT 1", (agent, night)).fetchone()
        if row is not None and row["hash"] == digest:
            return dict(_snap(row), written=False)
        cur = c.execute("INSERT INTO lesson_snapshots (agent, kind, night, at, lessons, hash) VALUES (?, 'night', ?, ?, ?, ?)",
                        (agent, night, float(at), _dump(lessons), digest))
        row = c.execute("SELECT * FROM lesson_snapshots WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(_snap(row), written=True)


def after_night(db, agent, at):
    """take(), as the night report carries it: {id, night, hash, lessons, live, written, since,
    changes, plug}; since is the last night before with a snapshot, changes the diff from it
    (None for the agent's first snapshot), plug the agent's name for the rollback command (the
    night runner puts its plug file there)."""
    snap = take(db, agent, at)
    prev = latest(db, agent, before=snap["night"])
    return {"id": snap["id"], "plug": agent, "night": snap["night"], "hash": snap["hash"], "lessons": len(snap["lessons"]),
            "live": sum(e["live"] for e in snap["lessons"]), "written": snap["written"],
            "since": None if prev is None else prev["night"],
            "changes": None if prev is None else diff(prev["lessons"], snap["lessons"])}


def latest(db, agent, *, before=None):
    """The agent's newest night snapshot (before that night, when given), or None."""
    sql, args = "SELECT * FROM lesson_snapshots WHERE agent = ? AND kind = 'night'", [agent]
    if before is not None:
        sql += " AND night < ?"
        args.append(before)
    with db.tx() as c:
        if not _has(c, "lesson_snapshots"):
            return None
        row = c.execute(sql + " ORDER BY night DESC, id DESC LIMIT 1", args).fetchone()
    return None if row is None else _snap(row)


def of_night(db, agent, night):
    """The night's snapshot (its newest copy), or None."""
    with db.tx() as c:
        if not _has(c, "lesson_snapshots"):
            return None
        row = c.execute("SELECT * FROM lesson_snapshots WHERE agent = ? AND kind = 'night' AND night = ? "
                        "ORDER BY id DESC LIMIT 1", (agent, night)).fetchone()
    return None if row is None else _snap(row)


def nights(db, agent):
    """The nights with a snapshot of the agent, newest first."""
    with db.tx() as c:
        if not _has(c, "lesson_snapshots"):
            return []
        return [r["night"] for r in c.execute("SELECT DISTINCT night FROM lesson_snapshots WHERE agent = ? AND "
                                               "kind = 'night' ORDER BY night DESC", (agent,))]


def rollbacks(db, agent):
    """The agent's rollbacks, oldest first, each with its detail read back."""
    with db.tx() as c:
        if not _has(c, "lesson_snapshots"):
            return []
        rows = c.execute("SELECT * FROM lesson_snapshots WHERE agent = ? AND kind = 'rollback' ORDER BY id",
                         (agent,)).fetchall()
    return [_snap(r) for r in rows]


def diff(a, b):
    """What changed from snapshot list a to snapshot list b: {added: [(id, state)], on_trial,
    kept, pulled: ids that moved there, waiting: ids waiting in both}."""
    old = {e["id"]: e for e in a}
    out = {"added": [], "on_trial": [], "kept": [], "pulled": [], "waiting": []}
    for e in b:
        was = old.get(e["id"])
        if was is None:
            out["added"].append((e["id"], e["state"]))
        elif e["state"] != was["state"]:
            key = {TRYING: "on_trial", KEPT: "kept", PULLED: "pulled"}.get(e["state"])
            if key:
                out[key].append(e["id"])
        elif e["state"] == WAITING:
            out["waiting"].append(e["id"])
    return out


def diff_text(changes, since):
    """The diff in plain words, for the night report."""
    if changes is None:
        return "first snapshot of this agent"
    words = {WAITING: "waiting", TRYING: "on trial", KEPT: "kept", PULLED: "pulled"}
    parts = []
    if changes["added"]:
        parts.append(f'added {len(changes["added"])} (' + ", ".join(f"lesson {i} {words[s]}" for i, s in changes["added"])
                     + ")")
    for key, name in (("on_trial", "on trial"), ("kept", "kept"), ("pulled", "pulled"), ("waiting", "still waiting")):
        if changes[key]:
            parts.append(f"{name} {len(changes[key])} (lesson " + ", ".join(str(i) for i in changes[key]) + ")")
    return f"since the night of {since}: " + ("; ".join(parts) if parts else "no change")


def size(n_lessons, n_live):
    """'3 lessons, 1 given', for the night report and the morning page."""
    return f"{n_lessons} lesson{'' if n_lessons == 1 else 's'}, {n_live} given"


def command(plug, night, db=None):
    """The rollback command for the night report and the morning page, ready to paste. Values go
    after an equals sign, so a value that starts with a dash still runs as printed."""
    out = f"python3 -I reflection/snapshots.py rollback --plug={shlex.quote(str(plug))} --to {night}"
    return out + (f" --db={shlex.quote(str(db))}" if db else "")


def plan(c, agent, snap, now):
    """What a rollback to `snap` would do now, read in the caller's transaction: one step a
    lesson that changes or is named, {id, line, do, why}, oldest first."""
    then = {e["id"]: e for e in snap["lessons"]}
    rows = {r["id"]: r for r in c.execute("SELECT id, text, state, pulled_why FROM lessons WHERE agent = ?", (agent,))}
    links = returns_in(c, agent)
    states = {i: r["state"] for i, r in rows.items()}
    steps = []
    for cur in _set(c, agent, now):
        e = then.get(cur["id"])
        live_then = bool(e and e["live"])
        turn_then = bool(e and e["trial"] == WAITS_TURN)
        stands_for = None if live_then or cur["state"] == PULLED else next(
            (i for i in sorted(back_family(links, cur["id"]) - {cur["id"]}) if then.get(i, {}).get("live")), None)
        if stands_for is not None:  # brought back since from a line given that night: it stands for that line
            where = f"brought back since; its line was given that night as lesson {stands_for}"
            if cur["live"] or cur["trial"] == WAITS_TURN:
                do, why = STAYS, where + ("" if cur["live"] else "; it waits its turn")
            else:
                do, why = CANNOT, f"{where}; {_gone(cur, None)}"
        elif cur["live"] and not live_then:
            do, why = PULL, _was(e, "not given that night") + (", kept since" if e and cur["state"] == KEPT else "")
        elif cur["trial"] == WAITS_TURN and not turn_then:
            do, why = PULL, _was(e, "") + "; it waits its turn now and would start by itself"
        elif cur["state"] == TRYING and not (e and e["state"] == TRYING):  # paused or ended, not given now
            do, why = PULL, _was(e, "") + "; its trial started since and " + \
                ("was paused" if cur["trial"] == PAUSED else "has ended") + ", so it could still be kept"
        elif live_then and cur["state"] == PULLED:
            gone = _pulled_since(rows[cur["id"]]["pulled_why"])
            copy = back_copy(links, states, cur["id"])
            if copy is not None:
                do, why = ALREADY, f"{gone}; its line is back already as lesson {copy}"
            else:
                do, why = BACK, (f"{gone}; with --bring-back it comes back as a new lesson on trial or waiting its turn, "
                                 "and this one stays pulled")
        elif live_then and not cur["live"]:
            do, why = CANNOT, _gone(cur, rows[cur["id"]]["pulled_why"])
        elif live_then:
            do, why = STAYS, ("given that night and now; kept since, it stays kept and does not go back on trial"
                              if e["state"] == TRYING and cur["state"] == KEPT else "given that night and now")
        elif e is None and cur["state"] == WAITING:
            do, why = LEFT, "added after that night; it waits for a yes and changes nothing until a person answers"
        else:
            continue
        steps.append({"id": cur["id"], "line": rows[cur["id"]]["text"], "do": do, "why": why.lstrip("; ")})
    for lid in sorted(set(then) - set(rows)):
        if then[lid]["live"]:
            steps.append({"id": lid, "line": "", "do": CANNOT, "why": "not in this database"})
    return steps


def plan_code(snap, steps):
    """The plan's short code: sha256 of the snapshot (id, agent, night, hash), each lesson it
    would pull and each lesson it offers to bring back, with its line, so ids that match in
    another database do not give the same code."""
    pulls = sorted([s["id"], s["line"]] for s in steps if s["do"] == PULL)
    backs = sorted([s["id"], s["line"]] for s in steps if s["do"] == BACK)
    key = [snap["id"], snap["agent"], snap["night"], snap["hash"], pulls, backs]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()[:SHORT]


def rollback(db, lessons, snap, by, now=None, *, code, bring_back=False):
    """Roll the agent back to `snap`, signed `by`, in one transaction: each pull through
    Lessons.pull, then, with bring_back, each lesson the plan offers to bring back through
    Lessons.bring_back (its step gets "as", the new lesson's id), and the rollback's own row.
    code: the plan_code() of the plan the person saw; the plan is read again under the write
    lock and refused when its code differs. Returns (steps, the rollback row's id, or None when
    there was nothing to pull or bring back and nothing was written). Refused, with nothing
    changed, when the plan or a lesson changed meanwhile."""
    now = time.time() if now is None else float(now)
    by = _line(by)
    agent = lessons.agent
    if snap["agent"] != agent or snap["kind"] != "night":
        raise Refused(f"snapshot {snap['id']} is not a night of {agent}")
    ready(db)
    with db.tx() as c:
        if not c.in_transaction:
            c.execute("BEGIN IMMEDIATE")
        steps = plan(c, agent, snap, now)
        if plan_code(snap, steps) != code:
            raise Refused("the plan changed; run it again without --yes")
        pulls = [s["id"] for s in steps if s["do"] == PULL]
        offered = [s for s in steps if s["do"] == BACK]
        backs = offered if bring_back else []
        if not pulls and not backs:
            return steps, None
        for lid in pulls:
            if not lessons.pull(lid, f"rolled back by {by} to the night of {snap['night']}", now=now, c=c):
                raise Refused(f"lesson {lid} changed meanwhile; nothing done")
        for s in backs:  # after the pulls, so a stage they free takes the lesson brought back at once
            try:
                s["as"] = lessons.bring_back(s["id"], by, now=now, c=c)
            except ValueError as e:
                raise Refused(f"lesson {s['id']} could not come back ({e}); nothing done") from None
        after = _set(c, agent, now)
        detail = {"to": snap["id"], "pulled": pulls, "brought_back": [{"id": s["id"], "as": s["as"]} for s in backs],
                  "offered_back": [s["id"] for s in offered if not bring_back],
                  "cannot_come_back": [{"id": s["id"], "why": s["why"]} for s in steps if s["do"] == CANNOT],
                  "left_waiting": [s["id"] for s in steps if s["do"] == LEFT]}
        cur = c.execute("INSERT INTO lesson_snapshots (agent, kind, night, at, lessons, hash, by, detail) "
                        "VALUES (?, 'rollback', ?, ?, ?, ?, ?, ?)",
                        (agent, snap["night"], now, _dump(after), _hash(after), by, json.dumps(detail)))
        return steps, cur.lastrowid


def plan_text(agent, snap, steps):
    """The plan as plain lines."""
    lines = [f'Rollback of {agent} to the night of {snap["night"]} (snapshot {snap["id"]}, hash {snap["hash"][:SHORT]}):']
    if not any(s["do"] == PULL for s in steps):
        lines.append("  nothing to pull: the lessons given now were all given that night")
    for s in steps:
        line = f' "{s["line"]}"' if s["line"] else ""
        lines.append(f'  {s["do"]}: lesson {s["id"]}{line}: {s["why"]}')
    return "\n".join(lines)


def find_plug(value, root=ROOT):
    """A plug file, or the agent name of a plug in the repo (<folder>/plug.json)."""
    path = Path(value)
    try:
        if path.is_file():
            return plug_mod.load(path)
        for p in sorted(Path(root).glob("*/plug.json")):
            plug = plug_mod.load(p)
            if plug.agent == value:
                return plug
    except (OSError, ValueError) as e:
        raise Refused(f"the plug could not be read ({e})") from None
    raise Refused(f"no plug {value!r}: neither a plug file nor an agent in this repo")


def main(argv=None, *, now=None, root=ROOT):
    """now: the clock when left out (tests give a fixed one). root: where agent names are found."""
    ap = argparse.ArgumentParser(description="Lesson snapshots: roll an agent's lessons back to a night.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("rollback", help="show the plan to roll back to a night; --yes does it")
    rb.add_argument("--plug", required=True, help="the agent's plug file, or its agent name in this repo")
    rb.add_argument("--to", required=True, metavar="NIGHT", help="the night, as on the night report: YYYY-MM-DD")
    rb.add_argument("--db", default=str(DEFAULT_PATH), help="the agent's database (default: data/ascent.db)")
    rb.add_argument("--by", default=BY, help=f"who signs the rollback (default: {BY})")
    rb.add_argument("--bring-back", action="store_true",
                    help="with --yes, also bring back the lessons the plan marks bring back, each as a new lesson")
    rb.add_argument("--yes", metavar="CODE", nargs="?", const="",
                    help="do it, with the plan's code as the plan printed it; without it nothing changes")
    args = ap.parse_args(argv)
    try:
        return _rollback(args, now, root)
    except Refused as e:
        print(f"Not run: {e}.", file=sys.stderr)
        return 2


def _rollback(args, now, root):
    if not _is_night(args.to):
        raise Refused(f"--to {args.to!r} is not a night; give it as on the night report, YYYY-MM-DD")
    by = _line(args.by)
    if args.yes == "":
        raise Refused("--yes takes the code the plan printed; run it again without --yes to see it")
    if not Path(args.db).is_file():
        raise Refused(f"no database at {args.db}")
    plug = find_plug(args.plug, root)
    db = Db(args.db)
    try:
        snap = of_night(db, plug.agent, args.to)
        if snap is None:
            have = nights(db, plug.agent)
            raise Refused(f"no snapshot of {plug.agent} on the night of {args.to}; " +
                          (f"nights with one: {', '.join(have[:10])}" if have else f"{plug.agent} has no snapshot yet"))
        if _hash(snap["lessons"]) != snap["hash"]:
            raise Refused(f"snapshot {snap['id']} no longer matches its hash")
        now = time.time() if now is None else float(now)
        if args.yes is None:
            with db.tx() as c:
                steps = plan(c, plug.agent, snap, now)
            print(plan_text(plug.agent, snap, steps))
            pulls, backs = (any(s["do"] == do for s in steps) for do in (PULL, BACK))
            if pulls or backs:
                other = Path(args.db).resolve() != DEFAULT_PATH.resolve()
                again = command(args.plug, args.to, args.db if other else None)
                again += f" --by={shlex.quote(by)}" if by != BY else ""
                code = plan_code(snap, steps)
                head = "Nothing changed. A pull is for good: a pulled lesson stays pulled."
                if pulls:
                    print(f"{head} To do it, run this (it is refused if the plan changes first):\n  {again} --yes {code}")
                if backs:
                    print(("To bring back the lessons marked bring back as well, each as a new lesson on trial or waiting its turn, "
                           "run this instead:" if pulls else
                           f"{head} To bring back the lessons marked bring back, each as a new lesson on trial or waiting its turn, "
                           "run this (it is refused if the plan changes first):")
                          + f"\n  {again} --bring-back --yes {code}")
            return 0
        steps, rid = rollback(db, EngineLessons(db, plug), snap, by, now, code=args.yes, bring_back=args.bring_back)
        print(plan_text(plug.agent, snap, steps))
        left = [str(s["id"]) for s in steps if s["do"] == BACK and "as" not in s]
        later = (f" Not brought back: lesson {', '.join(left)}; to bring it back, run the plan again and add "
                 "--bring-back.") if left else ""
        if rid is None:
            print("Nothing changed." + later)
        else:
            pulled = [str(s["id"]) for s in steps if s["do"] == PULL]
            back = [f"lesson {s['id']} as lesson {s['as']}" for s in steps if "as" in s]
            done = ([f"pulled lesson {', '.join(pulled)}"] if pulled else []) + \
                ([f"brought back {', '.join(back)}"] if back else [])
            print(f"Done, signed by {by}: {'; '.join(done)}. Recorded as snapshot {rid} (rollback).{later}")
        return 0
    finally:
        db.close()


# ---- reading the lessons ---------------------------------------------------------------------

def _set(c, agent, at):
    """The agent's lessons as a snapshot lists them at `at`, oldest first."""
    marks = {}
    if _has(c, "trial_marks"):
        for r in c.execute("SELECT lesson_id, kind FROM trial_marks WHERE agent = ? AND kind IN ('paused', 'verdict')",
                           (agent,)):
            marks.setdefault(r["lesson_id"], set()).add(r["kind"])
    out = []
    for r in c.execute("SELECT l.id, l.state, l.score, l.ends_at, t.lesson_id AS queued, t.started_at FROM lessons l "
                       "LEFT JOIN trials t ON t.lesson_id = l.id WHERE l.agent = ? ORDER BY l.id", (agent,)):
        mine = marks.get(r["id"], set())
        live = r["state"] == KEPT or (r["state"] == TRYING and r["ends_at"] is not None and r["ends_at"] > at)
        if r["state"] == WAITING:
            trial = WAITS_TURN if r["queued"] is not None and r["started_at"] is None else None
        elif r["state"] == TRYING:
            trial = PAUSED if "paused" in mine else ON_TRIAL if live else ENDED
        else:
            trial = DECIDED if "verdict" in mine else None
        out.append({"id": r["id"], "state": r["state"], "trial": trial, "score": float(r["score"]), "live": live})
    return out


def _was(e, live_word):
    """Where a lesson stood that night, in words, for a pull."""
    if e is None:
        return "added after that night"
    if e["trial"] == WAITS_TURN:
        return "it waited its turn that night; a lesson never goes back to waiting"
    if e["state"] == WAITING:
        return "it waited for a yes that night"
    if e["trial"] in (PAUSED, ENDED):
        return f"its trial was {e['trial']} that night"
    return live_word


def _pulled_since(pulled_why):
    return f"pulled since ({pulled_why})" if pulled_why else "pulled since"


def _gone(cur, pulled_why):
    """Why a lesson given that night and not pulled is not given now: its trial was paused or ended."""
    if cur["trial"] == PAUSED:
        return "its trial was paused since; it waits for a person to keep it or pull it"
    return "its trial ended since and waits for its verdict; a trial never starts again"


def _has(c, table):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def _snap(row):
    d = dict(row)
    d["lessons"] = json.loads(d["lessons"])
    d["detail"] = json.loads(d["detail"]) if d["detail"] else None
    return d


def _dump(lessons):
    return json.dumps(lessons, sort_keys=True, separators=(",", ":"))


def _hash(lessons):
    return hashlib.sha256(_dump(lessons).encode("utf-8")).hexdigest()


def _is_night(text):
    """A real date written YYYY-MM-DD."""
    try:
        return bool(_NIGHT.fullmatch(text)) and datetime.date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def _line(v):
    if not isinstance(v, str) or not v.strip() or "\n" in v or "\r" in v:
        raise Refused("--by is one line of text")
    return v.strip()


if __name__ == "__main__":
    sys.exit(main())
