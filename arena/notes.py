"""The quick note after each loss inside an Arena run (coordinator addition (1), with the rewrite
after a failed gate; Mohamed 2026-11-02, "It shouldn't make the same mistake in the same run").

After every lost training match of a run, the fast half of Reflection writes one short note, "try
this instead", as fast reflection writes one for a live chat (reflection/fast.py Writer, the same
prompt and model route), and the engine's guard (engine/fast.py guard) checks it in code before it
is held: one line, no number, no link or contact, none of the never marks, no run of words copied
from the practice customer and no name they gave. The agent's own losing reply (its last reply in
the lost match) goes through the same guard and is held beside the note as the answer not to give
again; a reply the guard stops (a number, the customer's words or a name they gave) is left out,
so no customer words ever reach the prompt. Every note of the run is kept (DECISIONS 74, his words
2026-11-02: "it shouldn't repeat mistakes again in same run"), at most MAX_NOTES of them: past the
cap the oldest is dropped. All of them are handed in the agent's next matches of that run, last in
its prompt under HEADING (sales/loop.py reads them through for_prompt), until the run's Reflection
between rounds has studied the lost matches they came from: then they are dropped, since the study
either turned those cases into a lesson that took the gate or left them.

What it is not: a lesson. It lives in this object only, for this run; it is never written to a
database, the Arena's copy or the live one, never takes the gate, never goes on trial and never
reaches the live agent. Every writer call is a model call taken from the run's own count (arena/run.py
Calls.model), so the run's cap holds it; at the cap, or when the writer fails or sees nothing
worth trying, there is no note and the run goes on.
"""
from engine import fast as engine_fast
from engine.study import PartError

HEADING = ("These answers lost practice cases earlier in this run (from Reflection; for this run only, and "
           "everything above still comes first). Never give the same answer again; try something new:")
MAX_NOTES = 5  # the notes a run holds at most; past it the oldest is dropped
LOST_WITH = "The answer that lost: "
TRY = "Try instead: "
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
        self.held = []  # {"text", "answer", "match"} a lost match, oldest first, at most MAX_NOTES
        self.log = []   # one row a lost match: {"match", "note", "answer", "why"}, and a row each time a note is dropped

    def after_loss(self, match, judged, match_id):
        """Write the note for one lost practice match and hold it, with the agent's losing reply, when
        the guard lets them through. Returns its row: {"match", "note": the text or None, "answer": the
        losing reply held or None, "why": why there is no note or None}."""
        turns = turns_of(match)
        view = {"ended_with": (judged or {}).get("why") or LOST, "good_result": self.plug.decides.good,
                "steps": [], "turns": turns}
        theirs = [t["text"] for t in turns if t["from"] != engine_fast.AGENT and "text" in t]
        text, why = self._write(view, theirs)
        answer = self._answer(turns, theirs)
        row = {"match": match_id, "note": text, "answer": answer, "why": why}
        self.log.append(row)
        if text is not None or answer is not None:
            self.held.append({"text": text, "answer": answer, "match": match_id})
            while len(self.held) > MAX_NOTES:
                old = self.held.pop(0)
                self.log.append({"match": old["match"], "note": None, "answer": None,
                                 "why": f"dropped: over the {MAX_NOTES} notes a run holds"})
        return row

    def _answer(self, turns, theirs):
        """The agent's last reply in the lost match when the guard lets it through, else None."""
        said = [t["text"] for t in turns if t["from"] == engine_fast.AGENT and "text" in t]
        if not said:
            return None
        if engine_fast.guard(said[-1], self.plug, theirs, never=self.never, known=self._known()):
            return None
        return said[-1]

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
        """Every note held, oldest first, under the heading, for the end of the agent's prompt; ""
        with none. Every match of the run is the agent's next case, so the match's own chat id does
        not matter."""
        if not self.held:
            return ""
        return self.heading + "".join("\n- " + line(h) for h in self.held)

    def clear(self, round_no):
        """The run's Reflection has studied the lost matches of round_no: drop every note held (each
        came from a round the study has read, since every earlier step dropped its own). Returns one
        row a note dropped, oldest first; [] when none was held."""
        rows = [{"match": h["match"], "note": None, "answer": None,
                 "why": f"dropped after the Reflection on round {round_no}"} for h in self.held]
        self.log += rows
        self.held = []
        return rows


def line(held):
    """One held note as its line in the prompt: the answer that lost, then what to try instead."""
    parts = []
    if held.get("answer"):
        parts.append(f'{LOST_WITH}"{held["answer"]}".')
    if held.get("text"):
        parts.append((TRY if parts else "") + held["text"])
    return " ".join(parts)
