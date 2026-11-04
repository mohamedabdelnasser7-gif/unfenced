"""Part E of the losses work: the quick notes inside an Arena run. The printed run summary shows, each
round, how many notes were written, how many the guard stopped and on which marks, and in how many
matches they were handed; every agent the Arena runs gets them (a built agent through arena/practice.py,
with the same RunNotes and guard, still only with a database and the study between rounds); and a
spelled number word in an ordinary sentence ("Try one short question first") no longer trips the number
rule, while digits, money, links, names, amounts and stock counts are still stopped. Made-up text and
fake models only, no network."""
import json
import unittest
from unittest import mock

from arena import notes as notes_mod, practice, run
from engine import fast as engine_fast
from kit import turn
from reflection import PLUG
from reflection import fast as fast_mod
from tests.fake_model import say
from tests.test_levels_study import Base as StudyBase, Climb

ZW = chr(0x200B)  # a zero width space


def guard(text, plug=PLUG, never=None, theirs=()):
    return engine_fast.guard(text, plug, list(theirs), never=fast_mod.NEVER if never is None else never, known=())


class PlainNumberWords(unittest.TestCase):
    def test_a_number_word_in_an_ordinary_sentence_passes(self):
        for text in ("Try one short question first.", "Ask one question at a time and wait.",
                     "Keep it to one clear question, then wait.", "Lead with the boot they asked about, then show two choices.",
                     "Keep it to one or two short lines.", "Ask one question about the size."):
            with self.subTest(text=text):
                self.assertEqual(guard(text), [])

    def test_amounts_counts_and_stock_still_fail(self):
        for text in ("Say only two pairs are left.", "Say two of them are left.", "Say two in stock.",
                     "Tell them it costs twenty.", "Say the boots are twenty.", "Offer it for ten.",
                     "Say it is twenty percent less.", "Tell them it costs fifteen hundred.",
                     "Say twenty five is fair.", "Mention it comes in three days.", "Say only one is left.",
                     "Say t w o pairs left.", "Say two" + ZW + " pairs left.", "Ask if they want one or two pairs."):
            with self.subTest(text=text):
                self.assertTrue(any(f.startswith(("number:", "amount:", "policy:")) for f in guard(text)), guard(text))

    def test_digits_money_links_and_names_still_fail(self):
        for text, line in (("Try 1 short question first.", "number: /[0-9]/"), ("Say it is $ less.", "number: /"),
                           ("Explain the value in pounds.", "amount: pound"), ("Send them to boots.com.", "core: link"),
                           ("Ask Mona one short question.", "names a word")):
            with self.subTest(text=text):
                found = guard(text, theirs=["I am Mona and I want boots"])
                self.assertTrue(any(f.startswith(line) for f in found), (text, found))

    def test_other_number_marks_and_scripts_never_pass_here(self):
        for text in ("Ask about half the options first.", "Double the questions about the size.",
                     "Say خمسين is fair.", "Mention wahed choice first."):
            with self.subTest(text=text):
                self.assertTrue(guard(text), text)

    def test_a_built_agents_plug_gets_the_same_rule(self):
        from tests.test_arena_practice import FIXTURE
        agent = turn.load(FIXTURE)
        never = fast_mod.never_for(agent.plug.risk)
        self.assertEqual(guard("Try one short question first.", agent.plug, never), [])
        self.assertTrue(guard("Say only two pairs are left.", agent.plug, never))
        self.assertTrue(guard("Try 1 short question first.", agent.plug, never))


class Summary(unittest.TestCase):
    def test_written_stopped_by_mark_and_handed(self):
        rows = [{"match": "a", "note": "Ask first.", "answer": None, "why": None},
                {"match": "b", "note": None, "answer": None, "why": "stopped: number: one; policy: stock"},
                {"match": "c", "note": None, "answer": None, "why": "stopped: policy: stock"},
                {"match": "d", "note": None, "answer": None,
                 "why": "stopped: names a word from the source's own words: mona; copies 3 or more words in a row"},
                {"match": "e", "note": None, "answer": None, "why": engine_fast.NOTHING},
                {"match": "f", "note": None, "answer": None, "why": "the writer failed: TimeoutError"},
                {"match": "a", "note": None, "answer": None, "why": "dropped after the Reflection on round 1"}]
        line = notes_mod.summary(rows, 4)
        self.assertEqual(line, "quick notes: 1 written, 3 stopped by the guard (policy: stock 2, a name 1, number: one 1, "
                               f"their words 1), 1 none: the writer failed, 1 none: {engine_fast.NOTHING}; handed in 4 matches")
        self.assertNotIn("mona", line)

    def test_no_line_with_no_notes(self):
        self.assertEqual(notes_mod.summary([], 0), "")
        self.assertEqual(notes_mod.summary([{"match": "a", "note": None, "answer": None, "why": "dropped: over"}]), "")

    def test_the_printed_summary_shows_each_rounds_line(self):
        rep = {"run": "r", "agent": "sales", "stopped": "rounds", "fact_checks": True,
               "trust": {"wins": 7, "matches": 10}, "training_cards": ["a"], "held_out_cards": ["b"],
               "calls": {"day": "2026-11-04", "used": 1, "cap": 10},
               "rounds": [{"round": 1, "training": {"won": 0, "played": 3, "cases": [], "notes_handed": 2, "notes": [
                   {"match": "m", "note": "Ask first.", "answer": None, "why": None},
                   {"match": "n", "note": None, "answer": None, "why": "stopped: number: one"}]},
                   "gate": {"won": 0, "played": 1, "lost": []}}]}
        self.assertIn("    quick notes: 1 written, 1 stopped by the guard (number: one 1); handed in 2 matches",
                      run.text(rep))


NOTE = "Ask what they need first, then answer in a short line."


class NoteWriter:
    """The quick note's writer model for a built agent's run: answers with NOTE as fast reflection's JSON."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        assert messages[0]["content"].startswith("You are Reflection")
        return say(json.dumps({"note": NOTE}))


class Seen(Climb):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.with_note = 0

    def answer(self, messages, tools):
        self.with_note += NOTE in messages[0]["content"]
        return super().answer(messages, tools)


class BuiltAgentRun(StudyBase):
    def run_notes(self, notes=True):
        folder = self.stock()
        world = Seen((folder / "instructions.md").read_text(encoding="utf-8"), [[]])
        from tests.test_arena_rounds import Exams
        from kit.db import Db
        db = Db(str(self.root / "ascent.db"))
        self.addCleanup(db.close)
        self.writer = NoteWriter()
        study = {"study": world, "open": world, "exam": world, "examiner": Exams(())}
        if notes:
            study["notes"] = self.writer
        given = dict(study)
        real, self.handed = practice.play, []

        def play(agent, card, **kw):
            self.handed.append((str(kw.get("seed")), kw.get("fast")))
            return real(agent, card, **kw)
        # groups of 3, so a later group plays with the notes of the one before (at the default 10 a round of 10
        # practice matches is one group and its notes reach no match of it)
        with mock.patch.object(practice, "play", play), mock.patch.object(run, "PARALLEL", 3):
            rep = practice.practise(folder, agent_model=world, customer_model=world, judge_model=world, study=study,
                                    db=db)
        self.assertEqual(study, given)  # the caller's models are left as given
        return rep, world

    def test_a_built_agent_gets_quick_notes_in_training_only(self):
        rep, world = self.run_notes()
        first = rep["rounds"][0]["training"]
        self.assertTrue(first["notes"] and first["notes"][0]["note"] == NOTE, first.get("notes"))
        self.assertGreater(self.writer.calls, 0)
        training = [f for seed, f in self.handed if "-t" in seed]
        gate = [f for seed, f in self.handed if "-g" in seed]
        self.assertTrue(gate and training)
        self.assertEqual(gate, [None] * len(gate))  # the gate plays as the live agent does, without notes
        self.assertTrue(all(isinstance(f, notes_mod.RunNotes) for f in training))
        self.assertGreater(world.with_note, 0)  # the note reached the built agent's prompt
        self.assertGreater(first.get("notes_handed", 0), 0)
        self.assertIn("quick notes: ", practice.text(rep))

    def test_no_notes_model_means_no_notes(self):
        rep, world = self.run_notes(notes=False)
        self.assertNotIn("notes", rep["rounds"][0]["training"])
        self.assertTrue(all(f is None for _, f in self.handed))
        self.assertEqual(world.with_note, 0)


if __name__ == "__main__":
    unittest.main()
