"""Handing over: the night study's second track. Some patterns in an agent's lost cases are not
for its own lessons but for another agent: the agent's plug names them (hands_over: the
receiving agent and its kinds of pattern, engine/plug.py). The engine holds no kind of its own,
so a new kind, or a new receiving agent, needs only a plug change.

Each night, with a spotter and a writer given (engine/study.py, Study(hand_over=...)):
1. Spot. The night's lost cases, each settled not good (a bad deciding result, none in its window,
   or left out for a cause outside the agent with no good result), up to TAGGED of them, a seeded
   sample when there are more, go to the spotter in blind views (keys, never a case id or a
   source; nothing after the deciding row). It answers each key with one declared kind or none.
   Anything else is no kind.
2. Count, in code. For each kind: the cases and the different sources it was spotted in. A kind
   counts only with at least MIN_SOURCES (3) different sources, the floor a lesson needs on each
   side (engine/study.py), so one source with many cases never sends a note alone.
3. One note per receiving agent a night, at most: its kind with the most sources, then the most
   cases, then the first the plug names. A kind under the floor, or beaten by another, sends
   nothing; the report names why.
4. Write. The writer is given what the night found, never a case: the agent's plug, the receiving
   agent (its plug's about line when its plug is given, else the hands_over about line), the kind
   and its line, and the counts. It writes one line from that intent; no text is fixed. The line
   then takes fast reflection's guard (engine/fast.py guard): one line of at most NOTE_LEN
   characters, no link, phone or handle, no number of any kind, no run of COPY_RUN words copied
   from the cases' own words and no word with a capital the cases hold (a name). The plug's high
   risk list is not used: the note goes to another agent, not to a case's source, and it must be
   free to name the topic. A writer that fails, gives nothing or is refused sends no note that
   night; the report says why. The counts and the case ids sit beside the line, added in code.
5. Hand over. The note is saved as a row of the handed_over table, which the receiving agent
   reads (received()), and named in the night's report. A row is never rewritten, and no two notes
   from one agent to one receiving agent have windows that overlap: a rerun of the same night, a
   second run a few minutes later (the runner sets until to the time it runs) or a night whose
   window takes in part of an earlier note's window writes none (the table refuses it).

The sort. Every line the study would write as a lesson (a pattern, an adapted lesson, an idea)
is asked first (sort()): a line that is one of the plug's kinds is not written; it is handed
over, never learned. So a kind the agent must never do itself (a plug may say so in the kind's
line) can never come back as a lesson through the night. Only an answer of "none" lets the line
be written as usual; a failing or unusable sort (no answer for the line, an answer that is not
an object, a kind the plug does not declare) holds the line for a person's yes instead
(engine/study.py).

Nothing here asks for a yes, starts a trial or writes a lesson.
"""
import json
import random

from engine.fast import guard
from engine.log import case_key
from engine.plug import Risk
from engine.study import BAD, LEFT_OUT, MIN_SOURCES, SHOWN, TAGGED, PartError, _view

NONE = "none"
NOTE = "note"                                    # a kind that sends tonight's note
FEW_SOURCES = "too few sources"                  # under the floor: no note
BEATEN = "another kind was stronger tonight"     # over the floor, but one note a night per receiving agent
NOT_SENT = "no note sent"                        # the writer failed, gave nothing or was refused
# The marks a note may never carry beyond the guard's own (a link, a phone, a handle, any number):
# none. The note goes to another agent, so it may name a topic the plug lists as high risk.
OPEN = Risk(high_about="", low_about="", words=(), patterns=(), tools=())

SCHEMA = """
CREATE TABLE IF NOT EXISTS handed_over (
  id INTEGER PRIMARY KEY,
  from_agent TEXT NOT NULL,
  to_agent TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  cases TEXT NOT NULL,
  sources INTEGER NOT NULL,
  since REAL NOT NULL,
  until REAL NOT NULL,
  written_at REAL NOT NULL,
  UNIQUE (from_agent, to_agent, until)
);
CREATE INDEX IF NOT EXISTS handed_over_to ON handed_over (to_agent, id);
CREATE TRIGGER IF NOT EXISTS handed_over_never_rewritten
BEFORE UPDATE ON handed_over
BEGIN SELECT RAISE(ABORT, 'a handed over note is never rewritten'); END;
CREATE TRIGGER IF NOT EXISTS handed_over_one_note_a_window
BEFORE INSERT ON handed_over
WHEN EXISTS (SELECT 1 FROM handed_over WHERE from_agent = NEW.from_agent AND to_agent = NEW.to_agent
             AND since < NEW.until - 3600 AND until > NEW.since + 3600)
BEGIN SELECT RAISE(IGNORE); END;
"""
# Windows that share an hour or less count as apart: a night that starts a few seconds earlier than the
# one before still writes its note (the one-hour slack in the trigger above).


class Track:
    """One agent's handing over. spotter(plug, kinds, items): {item id: kind name or "none"};
    kinds is [{kind, to, about}], items are blind case views ({id, steps}) or lines ({id, lesson,
    pattern, situation}). writer(plug, receiver, found): the note as one line, or None;
    receiver is {agent, about}, found is {kind, about, cases, sources}. Either may raise (a
    PartError's words are kept, any other error by its type only). others: the plugs of the other
    agents, for the receiving agent's own about line."""

    def __init__(self, db, plug, *, spotter, writer, others=(), seed=0):
        self.db, self.plug = db, plug
        self.spotter, self.writer = spotter, writer
        self.others = {o.agent: o for o in others}
        self.seed = seed
        self.kinds = {kind: (h.agent, line) for h in plug.hands_over for kind, line in h.kinds.items()}
        self.db.script(SCHEMA)

    def _kinds(self):
        return [{"kind": k, "to": to, "about": line} for k, (to, line) in self.kinds.items()]

    def sort(self, cand):
        """(receiving agent, kind) when the line is one of the plug's kinds, None when the spotter
        answers it "none". Raises what the spotter raises, and PartError on any other answer (not
        an object, no answer for the line, or a kind the plug does not declare), so an unusable
        sort holds the line for a yes and is never read as "not a kind"."""
        if not self.kinds:
            return None
        item = {"id": "l1", "lesson": cand["lesson"], "pattern": cand.get("pattern") or "",
                "situation": cand.get("situation") or ""}
        got = self.spotter(self.plug, self._kinds(), [item])
        kind = got.get("l1") if isinstance(got, dict) else None
        if kind == NONE:
            return None
        if isinstance(kind, str) and kind in self.kinds:
            return self.kinds[kind][0], kind
        raise PartError("the spotter gave no usable answer for the line")

    def night(self, cases, texts, since, until, *, now, notes):
        """The night's handing over on the study's read cases: {kinds, notes}. kinds: one entry per
        declared kind {to, kind, cases, sources, verdict, why}; notes: the notes handed over, each
        {id, to, kind, text, cases, sources, case_ids, again}. again: a note whose window overlaps
        this one was handed over before (a rerun, or a run soon after), so no new row; the note
        shown is that earlier one."""
        out = {"kinds": [], "notes": []}
        if not self.kinds:
            return out
        good = self.plug.decides.good
        lost = [c for c in cases if c.status == BAD or (c.status == LEFT_OUT and c.deciding != good)]
        if not lost:
            return out
        if len(lost) > TAGGED:
            picked = set(random.Random(f"hand|{self.seed}|{self.plug.agent}").sample(range(len(lost)), TAGGED))
            lost = [c for n, c in enumerate(lost) if n in picked]
        by_key = {c.key: c for c in lost}
        try:
            tags = self.spotter(self.plug, self._kinds(), [_view(self.plug, c, texts, blind=True) for c in lost])
        except Exception as e:  # a failing spotter hands nothing over
            notes.append(f"{self.plug.agent}: the spotter failed ({_failed(e)}); nothing handed over")
            return out
        tags = tags if isinstance(tags, dict) else {}
        found = {}
        for key, c in by_key.items():
            kind = tags.get(key)
            if isinstance(kind, str) and kind in self.kinds:
                found.setdefault(kind, []).append(c)
        for h in self.plug.hands_over:
            entries = []
            for kind in h.kinds:
                got = found.get(kind, [])
                sources = {c.source for c in got if c.source is not None}
                entry = {"to": h.agent, "kind": kind, "cases": len(got), "sources": len(sources),
                         "verdict": NOTE if len(sources) >= MIN_SOURCES else FEW_SOURCES, "why": None}
                entries.append((entry, got))
            out["kinds"].extend(e for e, _ in entries)
            strong = [(e, got) for e, got in entries if e["verdict"] == NOTE]
            if not strong:
                continue
            best = max(strong, key=lambda p: (p[0]["sources"], p[0]["cases"], -list(h.kinds).index(p[0]["kind"])))
            for e, _ in strong:
                if e is not best[0]:
                    e["verdict"] = BEATEN
            note = self._note(h, best[0], best[1], since, until, now, notes)
            if note is not None:
                out["notes"].append(note)
        return out

    def _note(self, h, entry, got, since, until, now, notes):
        """Write, check and save the note for one kind; None when none is sent (entry["why"] says why)."""
        other = self.others.get(h.agent)
        receiver = {"agent": h.agent, "about": (other.about if other is not None and other.about else h.about)}
        found = {"kind": entry["kind"], "about": self.kinds[entry["kind"]][1], "cases": entry["cases"],
                 "sources": entry["sources"]}
        try:
            text = self.writer(self.plug, dict(receiver), dict(found))
        except Exception as e:  # a failing writer sends no note
            notes.append(f"{self.plug.agent}: the note writer failed ({_failed(e)}); no note to {h.agent}")
            entry["verdict"], entry["why"] = NOT_SENT, "the writer failed"
            return None
        if text is None:
            entry["verdict"], entry["why"] = NOT_SENT, "the writer saw nothing worth passing on"
            return None
        refused = guard(text, self.plug, theirs=[c.text for c in got], never=OPEN)
        if refused:
            entry["verdict"], entry["why"] = NOT_SENT, "the note was refused: " + "; ".join(refused)
            return None
        text = text.strip()
        ids = [case_key(c.id) for c in got]
        with self.db.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO handed_over (from_agent, to_agent, kind, text, cases, sources, "
                            "since, until, written_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (self.plug.agent, h.agent, entry["kind"], text, json.dumps(ids, ensure_ascii=False),
                             entry["sources"], float(since), float(until), float(now)))
            if cur.rowcount == 1:
                row = {"id": cur.lastrowid, "kind": entry["kind"], "text": text, "cases": ids,
                       "sources": entry["sources"]}
            else:
                row = _row(c.execute("SELECT * FROM handed_over WHERE from_agent = ? AND to_agent = ? AND since < ? "
                                     "AND until > ? ORDER BY id DESC LIMIT 1",
                                     (self.plug.agent, h.agent, float(until), float(since))).fetchone())
        return {"id": row["id"], "to": h.agent, "kind": row["kind"], "text": row["text"], "cases": len(row["cases"]),
                "sources": row["sources"], "case_ids": list(row["cases"]), "again": cur.rowcount != 1}


def received(db, agent, since=None):
    """The notes handed over to this agent, oldest first: [{id, from, kind, text, cases, case_ids,
    sources, since, until, written_at}]. since: only those written at or after it."""
    db.script(SCHEMA)
    with db.tx() as c:
        rows = c.execute("SELECT * FROM handed_over WHERE to_agent = ? AND written_at >= ? ORDER BY id",
                         (agent, float("-inf") if since is None else float(since))).fetchall()
    return [dict(_row(r), cases=len(json.loads(r["cases"])), case_ids=json.loads(r["cases"])) for r in rows]


def line(note, shown=SHOWN):
    """One note as one plain line: where it went, its text, its kind and counts, and the first case ids."""
    ids = list(note.get("case_ids") or [])
    more = f" and {len(ids) - shown} more" if len(ids) > shown else ""
    return (f'note to {note["to"]}: "{note["text"]}" ({note["kind"]}, {note["cases"]} cases from '
            f'{note["sources"]} sources: {", ".join(ids[:shown])}{more})')


def _row(r):
    d = dict(r)
    d["from"] = d.pop("from_agent")
    d["to"] = d.pop("to_agent")
    d["cases"] = json.loads(d["cases"]) if isinstance(d["cases"], str) else d["cases"]
    return d


def _failed(e):
    return f"{type(e).__name__}: {e}" if isinstance(e, PartError) else type(e).__name__

