"""Reviewer losses round 1, item 6 gap: arena/run.py quick_notes for a built agent takes the never marks
from its own plug's high list (reflection/fast.py never_for) and the demo store's words only when it
has the store tool; the Sales agent keeps NEVER and the store's words. Fake models only."""
import tempfile
import types
import unittest
from pathlib import Path

from arena import match as match_mod, run
from engine import fast as engine_fast
from kit import turn
from reflection import PLUG
from reflection import fast as fast_mod
from tests.fake_model import clean_env
from tests.test_any_agent_r2 import old_folder
from tests.test_losses_notes import NoteWriter


class QuickNotes(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.calls = run.Calls(self.root / run.CALLS_FILE, 50)

    def built(self, name):
        return turn.load(old_folder(self.root, name))

    def notes(self, plug, agent=None):
        return run.quick_notes(plug, self.calls, NoteWriter(), agent=agent)

    def test_a_built_agent_gets_its_own_never_marks(self):
        for name in ("support_calm_helper", "lead_trial_booker", "coffee_caption_writer"):
            with self.subTest(agent=name):
                agent = self.built(name)
                notes = self.notes(agent.plug, agent)
                self.assertEqual(notes.never, fast_mod.never_for(agent.plug.risk))
                self.assertNotEqual(notes.never, fast_mod.NEVER)

    def test_a_word_only_on_the_built_agents_high_list_stops_its_note(self):
        agent = self.built("coffee_caption_writer")
        self.assertNotIn("giveaway", {w.casefold() for _, w in fast_mod.NEVER.words})
        self.assertIn("giveaway", {w.casefold() for _, w in agent.plug.risk.words})
        notes = self.notes(agent.plug, agent)
        text = "Mention the giveaway gently."
        self.assertTrue(engine_fast.guard(text, agent.plug, [], never=notes.never, known=notes._known()))
        self.assertEqual(engine_fast.guard(text, agent.plug, [], never=fast_mod.NEVER, known=()), [])

    def test_no_store_tool_no_store_words(self):
        for name in ("support_calm_helper", "lead_trial_booker", "coffee_caption_writer"):
            with self.subTest(agent=name):
                agent = self.built(name)
                self.assertNotIn("store", agent.tools)
                notes = self.notes(agent.plug, agent)
                self.assertIsNone(notes.known)
                self.assertEqual(notes._known(), ())

    def test_a_built_agent_with_the_store_tool_gets_the_store_words(self):
        agent = self.built("support_calm_helper")
        with_store = types.SimpleNamespace(plug=agent.plug, tools=tuple(agent.tools) + ("store",))
        notes = self.notes(agent.plug, with_store)
        self.assertEqual(notes.never, fast_mod.never_for(agent.plug.risk))
        with match_mod.demo_store():
            want = fast_mod.known()
        got = notes._known()
        self.assertTrue(got)
        self.assertEqual(set(got), set(want))

    def test_the_sales_agent_keeps_never_and_the_store_words(self):
        notes = self.notes(PLUG)
        self.assertIs(notes.never, fast_mod.NEVER)
        with match_mod.demo_store():
            want = fast_mod.known()
        self.assertEqual(set(notes._known()), set(want))

    def test_the_writer_calls_count_on_the_run_cap(self):
        agent = self.built("coffee_caption_writer")
        notes = self.notes(agent.plug, agent)  # fast reflection's writer, on the run's counted model
        self.assertIsInstance(notes.writer, fast_mod.Writer)
        self.assertEqual(type(notes.writer.model).__name__, "Counted")


if __name__ == "__main__":
    unittest.main()
