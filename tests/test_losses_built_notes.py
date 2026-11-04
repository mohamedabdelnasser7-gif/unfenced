"""Part G of the losses work (owner decision 103): a built agent with real customers gets fast notes too,
by the one path the Sales agent has. reflection/fast.py notes_for gives the engine's notes with fast
reflection's writer and guard for an agent whose plug names a bad deciding result, and none for one that
names none; kit/turn.py reads the note once a turn through sales/loop.py fast_note and puts it last in the
prompt under the same heading; a note that cannot be read never stops the reply; the channel's sweep runs
built agents' notes beside the Sales agent's. Made-up text and a fake model; no network."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def writer(plug, view):
    return NOTE


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

    def test_a_built_agent_gets_the_note_after_a_lost_case_and_loses_it_when_the_next_case_ends(self):
        agent = self.agent()
        db, chats, log = self.world(agent)
        notes = fast_mod.notes_for(db, agent, chats=chats, writer=writer)
        self.assertIsInstance(notes, fast_mod.AgentNotes)
        first = chats.open(turn.CHANNEL, "cust-1")
        log.act(first, "reply", result="replied", source="cust-1")
        log.result(first, ENDED, source="cust-1")
        wrote = notes.sweep()
        self.assertEqual([(w["text"], w["why"]) for w in wrote], [(NOTE, None)])
        nxt = chats.open(turn.CHANNEL, "cust-1")
        system = self.reply(agent, chats, nxt, notes)
        self.assertTrue(system.endswith(fast_mod.HEADING + "\n- " + NOTE), system[-200:])  # last, same heading
        self.assertIn(NOTE, self.reply(agent, chats, nxt, notes))  # in every turn of that next case
        self.assertNotIn(NOTE, self.reply(agent, chats, chats.open(turn.CHANNEL, "cust-2"), notes, who="cust-2"))
        log.act(nxt, "reply", result="replied", source="cust-1")
        log.result(nxt, "answered", source="cust-1")  # the next case ends: the note is gone
        self.assertNotIn(fast_mod.HEADING, self.reply(agent, chats, nxt, notes))

    def test_an_agent_with_no_bad_result_gets_none(self):
        agent = self.agent(bad=False)
        db, chats, _ = self.world(agent)
        self.assertIsNone(fast_mod.notes_for(db, agent, chats=chats, writer=writer))
        self.assertNotIn(fast_mod.HEADING, self.reply(agent, chats, chats.open(turn.CHANNEL, "cust-1"), None))

    def test_a_note_that_cannot_be_read_never_stops_the_reply(self):
        agent = self.agent()
        _, chats, _ = self.world(agent)

        class Broken:
            def for_prompt(self, case_id, now=None, source=None):
                raise RuntimeError("down")
        self.assertNotIn(fast_mod.HEADING, self.reply(agent, chats, chats.open(turn.CHANNEL, "cust-1"), Broken()))

    def test_notes_that_cannot_be_set_up_are_left_off(self):
        agent = self.agent()
        with mock.patch.object(fast_mod, "AgentNotes", side_effect=RuntimeError("no table")):
            self.assertIsNone(fast_mod.notes_for(None, agent))

    def test_the_guard_is_fast_reflections_over_the_agents_own_plug(self):
        agent = self.agent()
        db, chats, _ = self.world(agent)
        notes = fast_mod.notes_for(db, agent, chats=chats, writer=writer)
        self.assertEqual(notes.never, fast_mod.never_for(agent.plug.risk))
        self.assertIsNotNone(notes.known)  # it has the store tool: the store's words may be named


class ChannelSweep(unittest.TestCase):
    def test_built_agents_notes_are_swept_beside_the_sales_agents(self):
        class Notes:
            def __init__(self, got):
                self.got = got

            def sweep(self):
                if isinstance(self.got, Exception):
                    raise self.got
                return self.got
        app = wa.App.__new__(wa.App)
        app.fast, app.built_fast = Notes([{"case": "1"}]), [Notes(RuntimeError("down")), Notes([{"case": "2"}])]
        self.assertEqual(app.sweep_once(), [{"case": "1"}, {"case": "2"}])
        app.fast, app.built_fast = None, []
        self.assertEqual(app.sweep_once(), [])


if __name__ == "__main__":
    unittest.main()
