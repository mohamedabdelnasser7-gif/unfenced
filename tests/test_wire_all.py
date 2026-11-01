"""Every agent Quick start builds goes through every door the Sales agent has (DECISIONS item 59): the
pause switch, the night's cross-agent read and the Morning page. Fake models only; no network, no key."""
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import plug as plug_mod
from kit import switch, turn
from kit.chats import Chats
from kit.db import Db
from reflection import morning as mo
from reflection import night
from tests.fake_model import FakeModel, clean_env, say

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "agents" / "stock_watch"
SALES = plug_mod.load(REPO / "sales" / "plug.json")


class Folder(unittest.TestCase):
    """A database folder with one built agent in agents/stock_watch."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()
        self.folder = self.root / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        self.db_path = self.root / "ascent.db"


class PauseSwitch(Folder):
    def setUp(self):
        super().setUp()
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)
        self.chat_id = self.chats.open("whatsapp", "201000000000")
        self.agent = turn.load(self.folder)

    def one(self, model):
        sent = []
        out = turn.turn(self.agent, "Is it in stock?", chats=self.chats, chat_id=self.chat_id, model=model,
                        send=lambda to, text: sent.append(text), customer_id="201000000000")
        return out, sent

    def test_a_paused_agent_sends_nothing_and_calls_no_model(self):
        switch.pause("stock_watch", db=self.db, by="Mohamed")
        model = FakeModel()  # no script: any call fails the test
        out, sent = self.one(model)
        self.assertEqual((out.outcome, out.reply, sent, model.calls), (turn.PAUSED, None, [], []))
        steps = self.chats.steps(self.chat_id)
        self.assertEqual([(s["role"], s["content"]) for s in steps], [("user", "Is it in stock?")])  # still saved

    def test_after_resume_it_answers_again(self):
        switch.pause("stock_watch", db=self.db)
        self.one(FakeModel())
        switch.resume("stock_watch", db=self.db)
        out, sent = self.one(FakeModel(say("Yes, it is in stock.")))
        self.assertEqual((out.outcome, sent), ("replied", ["Yes, it is in stock."]))

    def test_another_agents_pause_does_not_stop_it(self):
        switch.pause("sales", db=self.db)
        out, sent = self.one(FakeModel(say("Yes, it is in stock.")))
        self.assertEqual(out.outcome, "replied")

    def test_honoured_says_yes_for_built_agents_only(self):
        self.assertTrue(switch.honoured("sales"))
        self.assertFalse(switch.honoured("stock_watch"))
        self.assertTrue(switch.honoured("stock_watch", {"stock_watch"}))

    def test_the_live_page_offers_pull_for_a_built_agent(self):
        db = Db(str(self.db_path))
        self.addCleanup(db.close)
        page = mo.live_morning(db, str(self.db_path), [SALES], self.root / "assistant")
        self.assertIn("stock_watch", page.plugs)
        self.assertEqual(page.built, frozenset({"stock_watch"}))
        self.assertTrue(page.pausable("stock_watch"))
        self.assertTrue(page.pausable("sales"))


class Built(Folder):
    def test_built_reads_each_agent_that_loads(self):
        (self.root / "agents" / ".half.ab12.tmp").mkdir()  # a Build still writing
        bad = self.root / "agents" / "broken"
        bad.mkdir()
        (bad / "plug.json").write_text("{}", encoding="utf-8")
        with self.assertLogs("kit.turn", "WARNING"):
            got = turn.built(self.root)
        self.assertEqual([a.name for a in got], ["stock_watch"])

    def test_built_reads_nothing_through_a_link(self):
        other = self.root / "elsewhere"
        (self.root / "agents").rename(other)
        (self.root / "agents").symlink_to(other)
        self.assertEqual(turn.built(self.root), [])

    def test_no_agents_folder_is_no_agents(self):
        shutil.rmtree(self.root / "agents")
        self.assertEqual(turn.built(self.root), [])


class NightReadsBuiltAgents(Folder):
    def test_other_plugs_takes_the_agents_beside_the_database(self):
        names = [p.agent for p in night.other_plugs(SALES, db=self.db_path)]
        self.assertIn("stock_watch", names)
        self.assertIn("marketing", names)
        self.assertNotIn("sales", names)

    def test_a_built_agent_reads_the_others_and_not_itself(self):
        mine = turn.load(self.folder).plug
        names = [p.agent for p in night.other_plugs(mine, db=self.db_path)]
        self.assertIn("sales", names)
        self.assertNotIn("stock_watch", names)

    def test_without_a_database_only_the_repo(self):
        self.assertNotIn("stock_watch", [p.agent for p in night.other_plugs(SALES)])
        self.assertNotIn("stock_watch", [p.agent for p in night.other_plugs(SALES, db=":memory:")])


if __name__ == "__main__":
    unittest.main()
