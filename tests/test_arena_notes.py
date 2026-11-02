"""The quick note after each loss inside an Arena run (arena/notes.py RunNotes, arena/run.py Arena
notes=): one guarded note written after each lost training match, with the agent's losing reply
when the guard lets it through, every note of the run held in memory (at most MAX_NOTES) for the
run's next matches, dropped once the step between rounds has run, every writer call on the run's
cap, nothing written to any database. Fake models only, no network; the cards are made here."""
import inspect
import json
import sqlite3
import unittest
from unittest import mock

from arena import match as match_mod, notes as notes_mod, run
from engine import fast as engine_fast
from engine.study import PartError
from reflection import PLUG
from reflection import fast as fast_mod
from tests.fake_model import say
from tests.test_arena_rounds import GOOD, Base

NOTE = "Ask what they want first, then suggest a fitting option."
LATER = "Keep the reply short and end with a question."
MATCH = {"turns": [{"n": 1, "customer": "How much is the Mercurial Vapor 17 Elite?", "replies": ["Let me check."],
                    "tools": ["search_products"]},
                   {"n": 2, "customer": "I am Mona and I need it soon", "replies": ["Noted."], "tools": []}]}


def writer(*answers):
    """A writer giving each answer in turn (a text, None, or an exception to raise), keeping each view."""
    seen, queue = [], list(answers)

    def write(plug, view):
        seen.append(view)
        got = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(got, Exception):
            raise got
        return got
    write.seen = seen
    return write


class Store(unittest.TestCase):
    def notes(self, *answers):
        return notes_mod.RunNotes(PLUG, writer(*answers), never=fast_mod.NEVER)

    def test_the_match_goes_to_the_writer_as_turns_and_a_clean_note_is_held(self):
        n = self.notes(NOTE)
        row = n.after_loss(MATCH, {"won": False, "why": "the customer left"}, "run-r1-t01")
        self.assertEqual(row, {"match": "run-r1-t01", "note": NOTE, "answer": "Noted.", "why": None})
        view = n.writer.seen[0]
        self.assertEqual(view["ended_with"], "the customer left")
        self.assertEqual(view["good_result"], PLUG.decides.good)
        self.assertEqual(view["turns"][:3], [
            {"from": engine_fast.OTHER, "text": "How much is the Mercurial Vapor 17 Elite?"},
            {"from": engine_fast.AGENT, "tools": ["search_products"]},
            {"from": engine_fast.AGENT, "text": "Let me check."}])
        self.assertEqual(n.for_prompt(7), notes_mod.HEADING + '\n- The answer that lost: "Noted.". Try instead: ' + NOTE)
        self.assertEqual(n.for_prompt(99), n.for_prompt(None))  # every match of the run is the next case

    def test_every_note_of_the_run_is_handed_and_clear_drops_them_all(self):
        n = self.notes(NOTE, LATER)
        n.after_loss(MATCH, {}, "m1")
        n.after_loss(MATCH, {}, "m2")
        prompt = n.for_prompt(1)
        self.assertTrue(prompt.startswith(notes_mod.HEADING + "\n- "), prompt)
        self.assertLess(prompt.index(NOTE), prompt.index(LATER))  # oldest first, the newer one kept beside it
        self.assertEqual(prompt.count("\n- "), 2)
        why = "dropped after the Reflection on round 1"
        self.assertEqual(n.clear(1), [{"match": "m1", "note": None, "answer": None, "why": why},
                                      {"match": "m2", "note": None, "answer": None, "why": why}])
        self.assertEqual(n.for_prompt(1), "")
        self.assertEqual(n.log[-1], {"match": "m2", "note": None, "answer": None, "why": why})
        self.assertEqual(n.clear(2), [])  # nothing held: nothing logged
        self.assertEqual(len(n.log), 4)

    def test_the_heading_says_never_the_same_answer_again(self):
        self.assertIn("lost practice cases earlier in this run", notes_mod.HEADING)
        self.assertIn("Never give the same answer again", notes_mod.HEADING)
        self.assertIn("try something new", notes_mod.HEADING)

    def test_past_the_cap_the_oldest_note_is_dropped(self):
        texts = [f"Try a new angle, the {w} way." for w in ("red", "blue", "green", "amber", "violet", "silver", "olive")]
        n = self.notes(*texts)
        for i in range(len(texts)):
            n.after_loss(MATCH, {}, f"m{i + 1}")
        prompt = n.for_prompt(1)
        self.assertEqual(notes_mod.MAX_NOTES, 5)
        self.assertEqual(prompt.count("\n- "), notes_mod.MAX_NOTES)
        self.assertNotIn(texts[0], prompt)
        self.assertNotIn(texts[1], prompt)
        self.assertTrue(all(t in prompt for t in texts[2:]))
        self.assertEqual([r["match"] for r in n.log if r["why"] and r["why"].startswith("dropped: over")], ["m1", "m2"])
        self.assertEqual([h["match"] for h in n.held], ["m3", "m4", "m5", "m6", "m7"])

    def test_the_losing_reply_is_held_only_when_the_guard_lets_it_through(self):
        def lost(reply, customer="Do you have it?"):
            return {"turns": [{"n": 1, "customer": customer, "replies": [reply], "tools": []}]}
        team = "I will check with the team and get back to you."
        n = self.notes(None)
        row = n.after_loss(lost(team), {}, "m1")
        self.assertEqual((row["note"], row["answer"]), (None, team))
        self.assertEqual(n.for_prompt(1), notes_mod.HEADING + '\n- The answer that lost: "' + team + '".')
        for bad, customer in (("It is 16,500 EGP.", "How much?"),  # a number
                              ("Sure Mona, it is on its way.", "I am Mona, where is it?"),  # a name they gave
                              ("I really need it before the match", "I really need it before the match")):  # their words
            n = self.notes(None)
            row = n.after_loss(lost(bad, customer), {}, "m1")
            self.assertIsNone(row["answer"], bad)
            self.assertEqual(n.for_prompt(1), "", bad)

    def test_the_guard_stops_a_number_a_copy_and_a_name_the_customer_gave(self):
        for bad in ("Offer 10 percent off.", "Say how much is the Mercurial for them.", "Ask Mona about the size."):
            n = self.notes(bad)
            row = n.after_loss(MATCH, {}, "m1")
            self.assertIsNone(row["note"], bad)
            self.assertTrue(row["why"].startswith("stopped: "), row["why"])
            self.assertNotIn(bad, n.for_prompt(1))

    def test_no_note_when_the_writer_sees_nothing_or_fails(self):
        cases = [(None, engine_fast.NOTHING), (PartError("the cap is reached"), "the writer failed: the cap is reached"),
                 (RuntimeError("secret words"), "the writer failed: RuntimeError"), (42, "the writer gave no text")]
        for answer, why in cases:
            n = self.notes(answer)
            row = n.after_loss(MATCH, {}, "m1")
            self.assertEqual((row["note"], row["why"]), (None, why))
            self.assertNotIn(notes_mod.TRY, n.for_prompt(1))  # only the losing reply is held

    def test_a_failure_keeps_the_note_already_held(self):
        n = self.notes(NOTE, None)
        n.after_loss(MATCH, {}, "m1")
        n.after_loss(MATCH, {}, "m2")
        self.assertIn(NOTE, n.for_prompt(1))


class NoteModel:
    """The quick note's writer model: answers with NOTE as fast reflection's JSON."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        assert messages[0]["content"].startswith("You are Reflection")
        return say(json.dumps({"note": NOTE}))


class InTheRun(Base):
    def run_with_notes(self, db, **kw):
        self.note_model = NoteModel()
        real = run.main

        def main(argv, *, agent_model, customer_model, reflection):
            return real(argv, agent_model=agent_model, customer_model=customer_model,
                        reflection=dict(reflection, notes=self.note_model))
        with mock.patch.object(run, "main", main), mock.patch.object(fast_mod, "known", lambda: frozenset()):
            return self.cli(db, [GOOD], **kw)

    def test_each_lost_training_match_gets_a_note_on_the_runs_cap_and_it_is_dropped_after_reflection(self):
        db = self.db()
        code, rep = self.run_with_notes(db)
        first, second = rep["rounds"]
        self.assertEqual([r["note"] for r in first["training"]["notes"]], [NOTE, NOTE, None, None])  # 2 lost
        self.assertEqual(first["training"]["notes"][2:],
                         [{"match": first["training"]["notes"][i]["match"], "note": None, "answer": None,
                           "why": "dropped after the Reflection on round 1"} for i in (0, 1)])  # both gone after the study
        self.assertEqual([r["note"] for r in second["training"]["notes"]], [NOTE, NOTE])  # no step after the last
        self.assertEqual(self.note_model.calls, 4)  # one a lost training match, both rounds; none for the gate
        saved = json.loads((run.state_dir(db) / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]
        self.assertEqual(saved, len(self.agent.calls) + self.customer.calls + self.night.calls
                         + self.exam_model.calls + self.note_model.calls)
        for path in (db, db.with_name(db.name + run.ARENA_SUFFIX)):  # never written to a database
            c = sqlite3.connect(path)
            self.addCleanup(c.close)
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'fast_notes'").fetchone())
            self.assertIsNone(c.execute("SELECT 1 FROM lessons WHERE text = ?", (NOTE,)).fetchone())

    def test_no_notes_model_means_no_notes(self):
        db = self.db()
        code, rep = self.cli(db, [GOOD])
        self.assertNotIn("notes", rep["rounds"][0]["training"])

    def test_the_cap_holds_the_writer(self):
        db = self.db()
        code, rep = self.run_with_notes(db, cap=3)  # the first match takes the cap before any loss is noted
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual(self.note_model.calls, 0)


class Handed(unittest.TestCase):
    def arena(self, notes):
        a = run.Arena.__new__(run.Arena)
        a.notes = notes
        return a

    def test_the_notes_go_to_play_once_play_takes_them(self):
        n = notes_mod.RunNotes(PLUG, writer(NOTE))

        def play(card, *, fast=None, **kw):
            return None
        with mock.patch.object(match_mod, "play", play):
            self.assertEqual(self.arena(n)._fast(), {"fast": n})
            self.assertEqual(self.arena(None)._fast(), {})

    @unittest.skipUnless("fast" in inspect.signature(match_mod.play).parameters,
                         "arena/match.py play takes no fast= yet (the merge line)")
    def test_the_note_reaches_the_agents_prompt(self):
        from tests.fake_model import Seller
        from tests.test_arena_rounds import card

        class Agent(Seller):
            def __init__(self):
                super().__init__()
                self.systems = []

            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                self.systems.append(messages[0]["content"])
                return super().chat(messages, tools, effort, max_tokens, whole)

        class Leaves:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                return say("How much is it?" if len(messages) == 2 else "[leave]")
        n = notes_mod.RunNotes(PLUG, writer(NOTE))
        n.after_loss(MATCH, {}, "m1")
        agent = Agent()
        match_mod.play(card(1, "price"), agent_model=agent, customer_model=Leaves(), fast=n)
        self.assertTrue(agent.systems and all(NOTE in s for s in agent.systems))


if __name__ == "__main__":
    unittest.main()
