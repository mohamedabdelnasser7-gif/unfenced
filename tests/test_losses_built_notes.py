"""Part G of the losses work: kit/turn.py reads a built agent's fast note once a turn through sales/loop.py
fast_note, the one path the Sales agent has, and puts it last in the prompt under fast reflection's heading;
a note that cannot be read, or is not text, never stops the reply. The Arena's quick notes are the only
notes a built agent gets today: no channel runs a built agent for real customers, so the built agent notes
and their channel sweep were taken out (reviewer losses round 1, finding 3). Made-up text and a fake model;
no network."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from arena import match as match_mod
from channels import whatsapp as wa
from engine.log import Log
from kit import turn
from kit.chats import Chats
from kit.db import Db
from reflection import fast as fast_mod
from tests.fake_model import clean_env, say
from tests.test_arena_practice import FIXTURE

NOTE = "Ask what they need first, then answer in a short line."
ENDED = "went_quiet"


class Model:
    """The built agent's model: keeps each system prompt, answers with a plain line."""

    def __init__(self):
        self.systems = []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.systems.append(messages[0]["content"])
        return say("Thanks for writing. Here is what happens next.")


class BuiltNotes(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def agent(self, bad=True):
        folder = self.root / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, folder, dirs_exist_ok=True)
        if bad:  # a plug with a bad deciding result, kept by source
            plug = json.loads((folder / "plug.json").read_text(encoding="utf-8"))
            plug["results"][ENDED] = {"speed": "fast", "shows_in_days": [0, 0], "about": "The customer went quiet."}
            plug["decides"]["bad"] = [ENDED]
            plug["source"]["known_by"] = "row"
            (folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
        return turn.load(folder)

    def world(self, agent):
        db = Db(str(self.root / "ascent.db"))
        self.addCleanup(db.close)
        return db, Chats(db), Log(db, agent.plug)

    def reply(self, agent, chats, chat_id, fast, who="cust-1"):
        model = Model()
        with match_mod.demo_store():
            out = turn.turn(agent, "Is it in stock?", chats=chats, chat_id=chat_id, model=model, send=lambda to, t: None,
                            customer_id=who, fast=fast)
        self.assertEqual(out.outcome, "replied")
        return model.systems[0]

    def test_the_note_goes_last_under_the_heading_in_every_turn(self):
        agent = self.agent()
        _, chats, _ = self.world(agent)

        class Notes:
            def for_prompt(self, case_id, now=None):
                return fast_mod.HEADING + "\n- " + NOTE
        chat = chats.open(turn.CHANNEL, "cust-1")
        system = self.reply(agent, chats, chat, Notes())
        self.assertTrue(system.endswith(fast_mod.HEADING + "\n- " + NOTE), system[-200:])  # last, same heading
        self.assertIn(NOTE, self.reply(agent, chats, chat, Notes()))
        self.assertNotIn(fast_mod.HEADING, self.reply(agent, chats, chat, None))

    def test_a_note_that_cannot_be_read_never_stops_the_reply(self):
        agent = self.agent()
        _, chats, _ = self.world(agent)

        class Broken:
            def for_prompt(self, case_id, now=None):
                raise RuntimeError("down")
        self.assertNotIn(fast_mod.HEADING, self.reply(agent, chats, chats.open(turn.CHANNEL, "cust-1"), Broken()))

    def test_a_note_that_is_not_text_is_left_out(self):
        agent = self.agent()
        _, chats, _ = self.world(agent)

        class Odd:
            def for_prompt(self, case_id, now=None):
                return [NOTE]
        self.assertNotIn(NOTE, self.reply(agent, chats, chats.open(turn.CHANNEL, "cust-1"), Odd()))


class FastNote(unittest.TestCase):
    def test_only_text_comes_back(self):
        from sales import loop

        class Notes:
            def __init__(self, got):
                self.got = got

            def for_prompt(self, chat_id):
                if isinstance(self.got, Exception):
                    raise self.got
                return self.got
        self.assertEqual(loop.fast_note(Notes("a note"), 1), "a note")
        for got in (None, ["a note"], 7, {"note": "a note"}, RuntimeError("down")):
            with self.subTest(got=got):
                self.assertEqual(loop.fast_note(Notes(got), 1), "")
        self.assertEqual(loop.fast_note(None, 1), "")

    def test_the_channel_has_no_built_agent_notes(self):
        self.assertFalse(hasattr(fast_mod, "AgentNotes") or hasattr(fast_mod, "notes_for"))
        self.assertNotIn("built_fast", wa.App.__init__.__code__.co_varnames)


if __name__ == "__main__":
    unittest.main()
