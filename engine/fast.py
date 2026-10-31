"""Fast reflection: right after a case ends without the good result, one short note, "try this
instead", for the next case from the same source only. The night study is the slow half of
Reflection; this is the fast half. One case id links them.

When a case ends. As the night study settles it (study.settle): a case with the plug's good
result is good and gets nothing; a case still inside its window is pending and gets nothing, so
nothing is ever written in the middle of a case; a case with a cause outside the agent is left
out and gets nothing; a case that ended not good (a bad deciding result, or no deciding result
once the longest deciding window has passed since its last action) gets one note. sweep() finds
those cases and writes their notes, so a sweep every few seconds writes a note within seconds of
the case ending. One note per ending: the case id and the time of its last action. A case whose
next case keeps its id (a plug whose case id names its source) can end again later and gets a
new note then. Rows imported from past data (log.is_history) never get a note.

What the writer reads. The case's own rows from the log (its actions, results and their detail)
and, when the agent gives a reader, the case's turns: who said what, each {"from", "text"} or
{"from", "tools"}. Turns from anyone but the agent (OTHER, or another name the agent uses) are
the source's own words: the writer is told they are data, never instructions, and the note is
checked against them. The writer is given to this module (the model version lives outside
engine/), so a test gives a fake.

The guard, in code, before a note is saved (guard()): one line of at most NOTE_LEN characters;
none of the risk check's core marks (a link, a phone number or a handle); no number of any kind:
a digit in any script, a numeral sign or a fraction (each reads as a digit in the risk check's
normal form), a percent or a money sign (NUMBERS, for every agent); none of the never marks;
no run of COPY_RUN words in a row copied from the source's own words, read in the same
normal form; and no word written with a capital (past a sentence's first word) that the source's
own words hold, so a name the source gave never reaches a note ("Ask Ahmed", red team round 2).
The never marks are what a note may never state, given by the agent as a Risk (words, patterns
and tools; never=). With none given they are the plug's whole high risk list,
the strict default. An agent gives its own when its high list also holds words a note needs
to name a topic: a note may say what to talk about, never state a figure, a cut, a promise or
a date. A note that fails is not saved as a note: its row keeps only why, so the same ending is
not tried again. The judge is not asked: a note never becomes a lesson and reaches one source's
next case only, so the code check is its whole bar.

What a note is not: a lesson. It lives in its own table, fast_notes, never in lessons. It never
goes on trial, never takes a share of cases, never passes through Lessons.hand, so its id never
joins the lesson ids an action is saved with, and nothing here writes a lesson. The night study
reads the same case by the same id; only the night's own way (the study, the risk check, the
exam and the Arena rerun before any trial) can turn the case into a lesson.

Expiry: one next case. A note is first given at the start of the next case from its source and
then in every action of that case, until that case ends the way any case ends: its good or a
bad deciding result, or the longest deciding window after its last action with neither. Then it
is gone. Why one next case and not a fixed number of hours: the note is about one case, and what
the agent should try lasts as long as the work it is for, short or long. A note never given is
gone KEEP_DAYS (7) days after it was written: a source that comes back after a week is starting
something new, the case behind the note is a week old, and the night study has read that case
by then. A note is missed, and never given, when the source already had an action after the
ended case before the note could be given: the next case began without it, and a note never
joins a case half way (for a plug whose rows name their source, it goes only to a case with no
action yet). A newer note for the same source replaces an older one not yet closed.
The database refuses a note's text or times rewritten, a second first use and any change to a
closed note.

slot() writes a note under a heading the agent gives, for its prompt. The agent's own checks run
after, so a note can never loosen a check.
"""
import dataclasses
import re
import time
import unicodedata

from engine import risk as risk_mod
from engine.log import Log, case_key, is_history, source_key
from engine.plug import CASE, Risk
from engine.study import BAD, PAST, PartError, longest, settle

DAY = 86400.0
KEEP_DAYS = 7          # a note never given is gone this many days after it was written
NOTE_LEN = 200         # characters in a note at most
COPY_RUN = 3           # words in a row from the source's own words that stop a note
MAX_PER_SWEEP = 20     # notes one sweep may write; the rest wait for the next sweep
STEPS = 40             # the last rows of the ended case the writer reads
TURNS = 30             # the last turns of the ended case the writer reads
AGENT, OTHER = "agent", "other"  # who a turn is from: the agent itself, or the case's source

WAITING, GIVEN = "waiting", "given"  # open: written and not given yet; given in its next case now
DONE, EXPIRED, MISSED, REPLACED = "done", "expired", "missed", "replaced"  # closed
NONE = "none"  # no note was written; why says why
CLOSED = (DONE, EXPIRED, MISSED, REPLACED)
NOTHING = "the writer saw nothing worth trying"
# A number of any kind, for every agent. The normal form turns every digit in any script into 0
# to 9 and every other numeral sign or fraction into digits too, so one digit class catches them.
NUMBERS = (("number", r"[0-9]"), ("number", r"[%$£€¥٪]"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS fast_notes (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  case_id TEXT NOT NULL,
  source TEXT NOT NULL,
  ended_at REAL NOT NULL,
  text TEXT,
  why TEXT,
  written_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  used_case TEXT,
  used_at REAL,
  closed_at REAL,
  closed_why TEXT CHECK (closed_why IS NULL OR closed_why IN ('done', 'expired', 'missed', 'replaced')),
  UNIQUE (agent, case_id, ended_at),
  CHECK (text IS NOT NULL OR why IS NOT NULL),
  CHECK (used_at IS NULL OR text IS NOT NULL),
  CHECK ((closed_at IS NULL) = (closed_why IS NULL))
);
CREATE INDEX IF NOT EXISTS fast_notes_source ON fast_notes (agent, source, id);
CREATE TRIGGER IF NOT EXISTS fast_notes_never_rewritten
BEFORE UPDATE OF agent, case_id, source, ended_at, text, why, written_at, expires_at ON fast_notes
BEGIN SELECT RAISE(ABORT, 'a fast note is never rewritten'); END;
CREATE TRIGGER IF NOT EXISTS fast_notes_one_next_case
BEFORE UPDATE OF used_case, used_at ON fast_notes WHEN OLD.used_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a fast note is given in one next case only'); END;
CREATE TRIGGER IF NOT EXISTS fast_notes_stay_closed
BEFORE UPDATE ON fast_notes WHEN OLD.closed_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a closed fast note stays closed'); END;
"""
_WORDS = re.compile(r"\w+")
_NAME_WORD = re.compile(r"[^\W\d_]+")  # a word of letters only


class FastNotes:
    """One agent's fast notes. writer(plug, view): the note as text, or None when nothing is worth
    trying; it may raise (a PartError's words are kept, any other error by its type only).
    reader(case id): the case's turns, a list of {"from", "text"} or {"from", "tools"}; optional.
    never: the marks a note may never carry, a plug.Risk; the plug's high risk list when left out."""

    def __init__(self, db, plug, *, writer=None, reader=None, keep_days=KEEP_DAYS, never=None):
        if not keep_days > 0:
            raise ValueError("keep_days is more than 0")
        if never is not None and not isinstance(never, Risk):
            raise ValueError("never is a plug Risk")
        self.db = db
        self.plug = plug
        self.log = Log(db, plug)
        self.writer, self.reader = writer, reader
        self.never = never
        self.keep_days = float(keep_days)
        self.db.script(SCHEMA)

    @property
    def agent(self):
        return self.plug.agent

    # writing

    def sweep(self, now=None, limit=MAX_PER_SWEEP):
        """Write one note for each case that ended not good and has none for that ending yet, at
        most `limit`, the cases that ended first first. Returns [{case, id, text, why}], one per
        row written. A case that ended more than keep_days ago is not looked at: its note would be
        gone already."""
        if self.writer is None:
            raise ValueError("a sweep needs a writer")
        now = _now(now)
        window = longest(self.plug) * DAY
        sql = "SELECT case_id, MAX(at) AS last FROM trace WHERE agent = ? AND action IS NOT NULL AND at <= ?"
        args = [self.agent, now]
        if not self.plug.decides.bad:  # with no bad deciding result, a case with the good one is good
            sql += " AND case_id NOT IN (SELECT case_id FROM trace WHERE agent = ? AND result = ? AND at <= ?)"
            args += [self.agent, self.plug.decides.good, now]
        sql += " GROUP BY case_id HAVING last >= ?"
        args.append(now - window - self.keep_days * DAY)
        if not self.plug.decides.bad:  # and it ends only past its window
            sql += " AND last <= ?"
            args.append(now - window)
        with self.db.tx() as c:
            found = c.execute(sql + " ORDER BY last, case_id", args).fetchall()
            done = {(r["case_id"], r["ended_at"]) for r in c.execute(
                "SELECT case_id, ended_at FROM fast_notes WHERE agent = ?", (self.agent,))}
        out = []
        for r in found:
            if len(out) >= limit:
                break
            if (r["case_id"], r["last"]) in done:
                continue
            wrote = self._one(r["case_id"], now)
            if wrote is not None:
                out.append(wrote)
        return out

    def _one(self, case_id, now):
        rows = [r for r in self.log.case(case_id) if r["at"] <= now]
        acted = [r["at"] for r in rows if r["action"] is not None]
        if not acted or any(is_history(r) for r in rows):
            return None
        status, deciding, _causes, _cut = settle(self.plug, rows, now)
        if status != BAD:  # good, pending (not ended: never in the middle of a case) or left out
            return None
        sources = [r["source"] for r in rows if r["source"] is not None]
        if not sources:
            return None
        turns = self._turns(case_id)
        view = {"ended_with": deciding or PAST, "good_result": self.plug.decides.good,
                "steps": [_step(r) for r in rows[-STEPS:]], "turns": turns}
        theirs = [t["text"] for t in turns if t["from"] != AGENT and "text" in t]
        text, why = self._write(view, theirs)
        return self._save(case_id, sources[-1], max(acted), text, why, now)

    def _turns(self, case_id):
        """The case's turns from the reader, each checked; [] with no reader or when it fails."""
        if self.reader is None:
            return []
        try:
            got = self.reader(case_id)
        except Exception:
            return []
        out = []
        for t in got if isinstance(got, list) else []:
            if not isinstance(t, dict) or not isinstance(t.get("from"), str) or not t["from"].strip():
                continue
            turn = {"from": t["from"].strip()}
            if isinstance(t.get("text"), str) and t["text"].strip():
                turn["text"] = t["text"].strip()
            tools = t.get("tools")
            if isinstance(tools, list) and tools and all(isinstance(x, str) for x in tools):
                turn["tools"] = list(tools)
            if len(turn) > 1:
                out.append(turn)
        return out[-TURNS:]

    def _write(self, view, theirs):
        """(the note, None) or (None, why there is none)."""
        try:
            raw = self.writer(self.plug, view)
        except PartError as e:
            return None, f"the writer failed: {e}"
        except Exception as e:  # named by its type only: its words could hold anything
            return None, f"the writer failed: {type(e).__name__}"
        if raw is None:
            return None, NOTHING
        if not isinstance(raw, str):
            return None, "the writer gave no text"
        text = raw.strip()
        found = guard(text, self.plug, theirs, never=self.never)
        if found:
            return None, "stopped: " + "; ".join(found)
        return text, None

    def _save(self, case_id, source, ended_at, text, why, now):
        with self.db.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO fast_notes (agent, case_id, source, ended_at, text, why, written_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent, case_key(case_id), source_key(source), float(ended_at), text, why, now,
                 now + self.keep_days * DAY))
            if cur.rowcount != 1:  # another sweep wrote this ending first
                return None
            new_id = cur.lastrowid
            if text is not None:
                for old in c.execute("SELECT * FROM fast_notes WHERE agent = ? AND source = ? AND id < ? "
                                     "AND text IS NOT NULL AND closed_at IS NULL", (self.agent, source_key(source),
                                                                                     new_id)).fetchall():
                    if self._state(c, dict(old), now) in (WAITING, GIVEN):
                        _close(c, old["id"], REPLACED, now)
        return {"case": case_key(case_id), "id": new_id, "text": text, "why": why}

    # giving

    def hand(self, case, *, source=None, now=None):
        """The note for an action in this case, as {id, text, case} (case: the ended case it came
        from), or None. The first time it is given marks its one next case; after that it is given
        only in that case, until that case ends. source: needed when each row names its source;
        when the case names it, left out or the case id."""
        key = case_key(case)
        src = self._source(key, source)
        now = _now(now)
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM fast_notes WHERE agent = ? AND source = ? AND text IS NOT NULL "
                            "AND closed_at IS NULL ORDER BY id DESC LIMIT 1", (self.agent, src)).fetchone()
            if row is None:
                return None
            note = dict(row)
            state = self._state(c, note, now)
            if state == WAITING:
                if key != note["case_id"] and c.execute(
                        "SELECT 1 FROM trace WHERE agent = ? AND case_id = ? AND action IS NOT NULL LIMIT 1",
                        (self.agent, key)).fetchone():
                    return None  # another case already under way: a note never joins a case half way
                c.execute("UPDATE fast_notes SET used_case = ?, used_at = ? WHERE id = ?", (key, now, note["id"]))
            elif state != GIVEN or note["used_case"] != key:
                return None
            return {"id": note["id"], "text": note["text"], "case": note["case_id"]}

    def _source(self, key, source):
        if self.plug.source.known_by == CASE:
            if source is not None and source_key(source) != key:
                raise ValueError(f"for {self.agent} the case id names the source; leave source out")
            return key
        if source is None:
            raise ValueError(f"{self.agent} names the source of each row; give it")
        return source_key(source)

    # reading

    def state(self, note_id, now=None):
        """The note's state now: waiting, given, done, expired, missed, replaced or none."""
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM fast_notes WHERE id = ? AND agent = ?", (note_id, self.agent)).fetchone()
            if row is None:
                raise KeyError(note_id)
            return self._state(c, dict(row), _now(now))

    def for_case(self, case, now=None):
        """Every note row written for this ended case, oldest first, each with its state now."""
        return self.linked([case], now)

    def linked(self, cases, now=None):
        """The note rows written for these ended cases (a night's case ids), oldest first, each
        {id, case, text, why, state, written_at}. Read only: nothing is closed here."""
        keys = sorted({case_key(x) for x in cases})
        if not keys:
            return []
        now = _now(now)
        marks = ", ".join("?" for _ in keys)
        with self.db.tx() as c:
            rows = [dict(r) for r in c.execute(
                f"SELECT * FROM fast_notes WHERE agent = ? AND case_id IN ({marks}) ORDER BY id",
                (self.agent, *keys)).fetchall()]
            return [{"id": r["id"], "case": r["case_id"], "text": r["text"], "why": r["why"],
                     "state": self._state(c, r, now, close=False), "written_at": r["written_at"]} for r in rows]

    def _state(self, c, note, now, close=True):
        """A note's state at now; a state that ends it is saved (close) the first time it is seen."""
        if note["text"] is None:
            return NONE
        if note["closed_at"] is not None:
            return note["closed_why"]
        if note["used_at"] is None:
            if now >= note["expires_at"]:
                state = EXPIRED
            elif c.execute("SELECT 1 FROM trace WHERE agent = ? AND source = ? AND action IS NOT NULL AND at > ? "
                           "LIMIT 1", (self.agent, note["source"], note["ended_at"])).fetchone():
                state = MISSED
            else:
                return WAITING
        elif self._over(c, note, now):
            state = DONE
        else:
            return GIVEN
        if close:
            _close(c, note["id"], state, now)
        return state

    def _over(self, c, note, now):
        """Has the note's one next case ended: a deciding result since it was first given, or the
        longest deciding window passed since its last action (or since it was given, with none)?"""
        deciders = {self.plug.decides.good, *self.plug.decides.bad}
        last = note["used_at"]
        for r in c.execute("SELECT action, result, at FROM trace WHERE agent = ? AND case_id = ? AND at >= ? "
                           "ORDER BY at, id", (self.agent, note["used_case"], note["used_at"])):
            if r["result"] in deciders:
                return True
            if r["action"] is not None:
                last = max(last, r["at"])
        return now >= last + longest(self.plug) * DAY


def guard(text, plug, theirs=(), never=None):
    """Why a note may not be given, as plain lines; [] when it may. theirs: the source's own words.
    never: the marks a note may never carry (a plug.Risk); the plug's high risk list when None.
    The core marks and NUMBERS are checked either way."""
    if not isinstance(text, str) or not text.strip():
        return ["not one line of text"]
    if len(text.splitlines()) > 1:  # every line break Python knows: \n, \r, U+2028, U+0085 and more
        return ["more than one line"]
    found = []
    if len(text.strip()) > NOTE_LEN:
        found.append(f"over {NOTE_LEN} characters")
    marks = plug.risk if never is None else never
    found += risk_mod.code_check(text, dataclasses.replace(marks, patterns=NUMBERS + tuple(marks.patterns)))
    if any(_runs(text) & _runs(t) for t in theirs if isinstance(t, str)):
        found.append(f"copies {COPY_RUN} or more words in a row from the source's own words")
    names = _capitalised(text) & _their_words(theirs)
    if names:
        found.append("names a word from the source's own words: " + ", ".join(sorted(names)))
    return found


def _capitalised(text):
    """The words of text written with a capital first letter, other than a sentence's first word
    ("Ask Ahmed first" gives ahmed), in the normal form. Hidden characters and marks are dropped and
    look alike letters read as Latin first, keeping their case, so neither hides a capital."""
    plain = unicodedata.normalize("NFKD", (text or "").translate(risk_mod._LATIN))
    plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Cf" and ch not in risk_mod._BLANKS
                    and not unicodedata.category(ch).startswith("M")).translate(risk_mod._LATIN)
    def opens(m):  # a sentence's first word has a capital anyway
        before = plain[:m.start()].rstrip(" \t\"'“”‘’(")
        return not before or before[-1] in ".!?;:؟"
    return {risk_mod.normalize(m.group(0)) for m in _NAME_WORD.finditer(plain)
            if len(m.group(0)) > 1 and m.group(0)[0].isupper() and not opens(m)}


def _their_words(theirs):
    """Every word of the source's own turns, in the four forms the risk check reads."""
    words = set()
    for t in theirs:
        if isinstance(t, str):
            for letters in (False, True):
                for hidden in ("", " "):
                    words.update(_WORDS.findall(risk_mod.normalize(t, hidden, letters)))
    return words


def slot(note, heading):
    """A note's place in the agent's prompt: the heading, then the note; "" when there is none."""
    if not note:
        return ""
    return heading + "\n- " + note["text"]


def _runs(text):
    """Every run of COPY_RUN words in a row, in the four forms the risk check reads."""
    runs = set()
    for letters in (False, True):
        for hidden in ("", " "):
            words = _WORDS.findall(risk_mod.normalize(text, hidden, letters))
            runs.update(tuple(words[i:i + COPY_RUN]) for i in range(len(words) - COPY_RUN + 1))
    return runs


def _step(r):
    step = {k: r[k] for k in ("action", "stage", "result") if r[k] is not None}
    if r["detail"] is not None:
        step["detail"] = r["detail"]
    return step


def _close(c, note_id, why, now):
    c.execute("UPDATE fast_notes SET closed_at = ?, closed_why = ? WHERE id = ? AND closed_at IS NULL",
              (now, why, note_id))


def _now(now):
    return time.time() if now is None else float(now)
