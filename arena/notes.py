"""The quick note after each loss inside an Arena run (coordinator addition (1), with the rewrite
after a failed gate; Mohamed 2026-11-02, "It shouldn't make the same mistake in the same run").

After every lost training match of a run, the fast half of Reflection writes one short note, "try
this instead", as fast reflection writes one for a live chat (reflection/fast.py Writer, the same
prompt and model route), and the engine's guard (engine/fast.py guard) checks it in code before it
is held: one line, no number, no link or contact, none of the never marks, no run of words copied
from the practice customer and no name they gave. The note is handed in the agent's next matches of
that run, last in its prompt under HEADING (sales/loop.py reads it through for_prompt), until the
run's Reflection between rounds has studied the lost matches it came from: then it is dropped,
since the study either turned those cases into a lesson that took the gate or left them.

What it is not: a lesson. It lives in this object only, for this run; it is never written to a
database, the Arena's copy or the live one, never takes the gate, never goes on trial and never
reaches the live agent. A newer note replaces the one held, as a newer fast note for the same
source does. Every writer call is a model call taken from the run's own count (arena/run.py
Calls.model), so the run's cap holds it; at the cap, or when the writer fails or sees nothing
worth trying, there is no note and the run goes on.
"""
from engine import fast as engine_fast
from engine.study import PartError

HEADING = ("Try this instead (from Reflection, on a practice case this agent lost earlier in this run; "
           "for this run only, and everything above still comes first):")
LOST = "lost"  # what a lost match ended with, when the judge gave no why


def turns_of(match):
    """A practice match as the writer's turns: the customer's lines as "other", the agent's replies
    as "agent" and the tools it ran by name."""
    out = []
    for t in match.get("turns") or []:
        if isinstance(t.get("customer"), str) and t["customer"].strip():
            out.append({"from": engine_fast.OTHER, "text": t["customer"].strip()})
        tools = [x for x in t.get("tools") or [] if isinstance(x, str)]
        if tools:
            out.append({"from": engine_fast.AGENT, "tools": tools})
        for reply in t.get("replies") or []:
            if isinstance(reply, str) and reply.strip():
                out.append({"from": engine_fast.AGENT, "text": reply.strip()})
    return out[-engine_fast.TURNS:]


class RunNotes:
    """The run's quick notes, in memory. writer(plug, view): the note's text or None (reflection/fast.py
    Writer on a model the run counts). never: the marks a note may never carry (a plug Risk; the
    plug's high risk list when None). known: the agent's own words a note may name, a callable as
    engine FastNotes takes, or None."""

    def __init__(self, plug, writer, *, never=None, known=None, heading=HEADING):
        self.plug, self.writer, self.never, self.known, self.heading = plug, writer, never, known, heading
        self.note = None  # {"text", "match"}: the note held, or None
        self.log = []     # one row a lost match: {"match", "note", "why"}, and a row each time a note is dropped

    def after_loss(self, match, judged, match_id):
        """Write the note for one lost practice match and hold it when the guard lets it through.
        Returns its row: {"match", "note": the text or None, "why": why there is none or None}."""
        turns = turns_of(match)
        view = {"ended_with": (judged or {}).get("why") or LOST, "good_result": self.plug.decides.good,
                "steps": [], "turns": turns}
        theirs = [t["text"] for t in turns if t["from"] != engine_fast.AGENT and "text" in t]
        text, why = self._write(view, theirs)
        row = {"match": match_id, "note": text, "why": why}
        self.log.append(row)
        if text is not None:
            self.note = {"text": text, "match": match_id}
        return row

    def _write(self, view, theirs):
        """(the note, None) or (None, why there is none), as engine FastNotes writes one."""
        try:
            raw = self.writer(self.plug, view)
        except PartError as e:
            return None, f"the writer failed: {e}"
        except Exception as e:  # named by its type only: its words could hold anything
            return None, f"the writer failed: {type(e).__name__}"
        if raw is None:
            return None, engine_fast.NOTHING
        if not isinstance(raw, str):
            return None, "the writer gave no text"
        text = raw.strip()
        found = engine_fast.guard(text, self.plug, theirs, never=self.never, known=self._known())
        if found:
            return None, "stopped: " + "; ".join(found)
        return text, None

    def _known(self):
        if self.known is None:
            return ()
        try:
            got = self.known()
        except Exception:  # words that cannot be read let none through, never more
            return ()
        return tuple(got) if isinstance(got, (set, frozenset, list, tuple)) else ()

    def for_prompt(self, chat_id=None, now=None):
        """The note held, under the heading, for the end of the agent's prompt; "" with none. Every
        match of the run is the agent's next case, so the match's own chat id does not matter."""
        return engine_fast.slot(self.note, self.heading)

    def clear(self, round_no):
        """The run's Reflection has studied the lost matches of round_no: drop the note held. Returns
        the row that says so, or None when no note was held."""
        row = None
        if self.note is not None:
            row = {"match": self.note["match"], "note": None, "why": f"dropped after the Reflection on round {round_no}"}
            self.log.append(row)
        self.note = None
        return row
