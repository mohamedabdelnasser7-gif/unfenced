"""Practice customers grow from real losses of any kind (arena/grow.py, reflection/night.py,
DECISIONS item 79), each agent reading only its own chats into its owner's pool of its kind (item
51 holds), and the demo state judges run (demo/make_loop_state.py): one owner, two Sales style
siblings and a support agent. Made-up chats only; no model, no key, no network."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import grow
from arena import label as label_mod
from arena import recipe as recipe_mod
from arena.scripted import ScriptedModel
from arena.tag import Tagger
from demo import make_loop_state as demo
from engine import plug as plug_mod
from engine import risk
from kit import turn
from kit.db import Db
from reflection import night
from tests import study_fakes as fk
from tests.fake_model import clean_env

NOW = 1_800_000_000.0
H = 3600.0
SINCE = NOW - 14 * 24 * H
ADAPTED = "Give this store's delivery fee with the price, so the total shows at once."


def recipe():
    return recipe_mod.load(recipe_mod.EXAMPLE)


def tagger():
    return Tagger(model=ScriptedModel(recipe()), cap=50, recipe=recipe())


def always_low(text, high_about, low_about):
    return risk.LOW


class DemoState(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.state = Path(d.name).resolve() / "demo-loop"
        self.plugs = demo.write(self.state, now=NOW)
        self.agents = self.state / "agents"
        self.db_path = self.state / "ascent.db"
        self.db = Db(str(self.db_path))
        self.addCleanup(self.db.close)

    def grow_for(self, agent, own=False):
        plug = self.plugs[agent]
        pool = grow.Pool(grow.owner_of(self.agents / agent), grow.kind_of(plug))
        counts = grow.grow(self.db, pool, since=SINCE, until=NOW, tagger=tagger(), plug=plug, own=own)
        return pool, counts


class TheDemoState(DemoState):
    def test_one_owner_two_sales_siblings_and_a_support_agent(self):
        self.assertEqual(grow.owner_name(self.agents), "demo")
        self.assertEqual([a.name for a in turn.built(self.state)], ["bags_seller", "boots_seller", "returns_helper"])
        self.assertEqual(grow.siblings(self.agents, "sales"), ["bags_seller", "boots_seller"])
        self.assertEqual(grow.siblings(self.agents, "support"), ["returns_helper"])
        others = [p.agent for p in night.other_plugs(self.plugs["bags_seller"], db=self.db_path)]
        self.assertIn("boots_seller", others)

    def test_it_never_writes_over_a_state_or_inside_the_repo(self):
        with self.assertRaises(SystemExit):
            demo.check_state(self.state)
        with self.assertRaises(SystemExit):
            demo.check_state(demo.ROOT / "demo" / "loop")

    def test_the_first_siblings_night_grows_the_shared_sales_pool(self):
        pool, counts = self.grow_for("boots_seller")
        self.assertEqual((counts["added"], counts["lost"], counts["hard"]), (4, 3, 1))
        self.assertEqual(counts["easy wins, skipped"], 1)
        self.assertEqual(pool.path, self.agents / "practice-sales.json")
        self.assertEqual(pool.summary()["siblings"], ["bags_seller", "boots_seller"])

    def test_a_support_agent_grows_its_own_kind_from_its_logged_losses(self):
        pool, counts = self.grow_for("returns_helper")
        self.assertEqual((counts["added"], counts["lost"]), (2, 2))
        self.assertEqual(counts["easy wins, skipped"], 1)  # resolved, and short: nothing to practise
        self.assertEqual({i["why"] for i in pool.items}, {grow.ENDED_BY_LOG})
        self.assertEqual(pool.path, self.agents / "practice-support.json")

    def test_an_agent_reads_only_the_chats_its_log_names(self):
        _, counts = self.grow_for("bags_seller")
        self.assertEqual(counts.get("read", 0), 0)  # no chat is bags_seller's yet: it faces boots_seller's pool
        ids = {cid for cid, *_ in grow.real_chats(self.db, SINCE, NOW, agent="returns_helper", own=False)}
        self.assertEqual(ids, {"demo-c6", "demo-c7", "demo-c8"})

    def test_the_databases_own_agent_skips_chats_logged_for_another(self):
        from tests.test_arena_grow import LOST, write_chats
        write_chats(self.db, [("mine", [(r, t, h - 10, n) for r, t, h, n in LOST[1]])])
        own = {cid for cid, *_ in grow.real_chats(self.db, SINCE, NOW, agent="sales", own=True)}
        self.assertEqual(own, {"mine"})
        self.assertEqual(len(grow.real_chats(self.db, SINCE, NOW)), len(demo.CHATS) + 1)  # no agent: every chat

    def test_without_the_log_a_support_chat_stays_unclear(self):
        """Revert guard: the support losses come from the log, not from the chat labels."""
        chat = grow.real_chats(self.db, SINCE, NOW, agent="returns_helper", own=False)[0][1]
        self.assertEqual(label_mod.label(chat, NOW)[0], label_mod.UNCLEAR)
        self.assertEqual(grow.decided(self.db, self.plugs["returns_helper"], "demo-c6", NOW), label_mod.LOST)
        self.assertEqual(grow.decided(self.db, self.plugs["returns_helper"], "demo-c8", NOW), label_mod.WON)
        self.assertIsNone(grow.decided(self.db, self.plugs["returns_helper"], "demo-c6", NOW - 100 * H))

    def test_another_owners_pool_is_never_touched(self):
        other = self.state.parent / "other"
        (other / "agents").mkdir(parents=True)
        (other / "agents" / "owner.json").write_text(json.dumps({"owner": "other"}), encoding="utf-8")
        self.grow_for("boots_seller")
        self.assertEqual(list((other / "agents").iterdir()), [other / "agents" / "owner.json"])

    def test_the_second_siblings_night_holds_the_kept_lesson_for_a_yes(self):
        """bags_seller's night reads boots_seller first, adapts its kept lesson and, with no exam, holds it."""
        bags = self.plugs["bags_seller"]
        rep = night.night(self.db, bags, until=NOW, judge=always_low, proposer=fk.Proposer(), tagger=fk.Tagger(),
                          fit=fk.Fit({demo.KEPT: "fully"}), adapter=fk.Adapter({demo.KEPT: ADAPTED}),
                          others=night.other_plugs(bags, db=self.db_path))
        self.assertEqual(rep["across"][0]["agent"], "boots_seller")
        self.assertTrue(rep["across"][0]["sibling"])
        card = [c for c in rep["cards"] if c["change"] == ADAPTED][0]
        self.assertEqual((card["state"], card["from"]["agent"]), ("waiting", "boots_seller"))
        self.assertIsNone(card["level"])  # no trial started


class NightStepAnyKind(DemoState):
    """main() for a support agent's plug, with the night study itself stood in: the practice step runs."""

    def setUp(self):
        super().setUp()
        self.db.close()
        rep = {"agent": "returns_helper", "window": {"since": SINCE, "until": NOW}, "snapshot": {}}
        for p in (mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]),
                  mock.patch.object(night, "night", return_value=rep), mock.patch("kit.model.Model"),
                  mock.patch.object(grow, "tag_model", side_effect=lambda: ScriptedModel(recipe()))):
            p.start()
            self.addCleanup(p.stop)

    def test_a_support_agents_night_grows_its_pool(self):
        out, err = io.StringIO(), io.StringIO()
        plug = self.agents / "returns_helper" / "plug.json"
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = night.main(["--plug", str(plug), "--db", str(self.db_path), "--json", "--recipe",
                               str(recipe_mod.EXAMPLE)])
        self.assertEqual(code, 0, err.getvalue())
        rep = json.loads(sorted(self.state.glob("night-returns_helper-*.json"))[0].read_text(encoding="utf-8"))
        self.assertEqual((rep["practice"]["kind"], rep["practice"]["added"]), ("support", 2))
        self.assertEqual(rep["practice"]["siblings"], ["returns_helper"])
        self.assertTrue((self.agents / "practice-support.json").is_file())
        self.assertFalse((self.state / "practice-support.json").exists())  # its owner's folder, not the database's


if __name__ == "__main__":
    unittest.main()
