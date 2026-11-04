"""Guards of the shared pool that had no test failing without them (review crossowner round 2,
item 4): an owner whose plug names another owner has no id (O02), an Arena state whose owner id
cannot be read gets no shared card rather than its own (K03), a built agent outside an agents/
folder reads no shared card (P04), and shared practice customers train at the average training
card's weight (P03) and only beside training cards (P07). E07 is in test_shared_pool. Fake files,
no key, no network."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from arena import grow, practice, run
from reflection import night, shared
from tests.test_arena_practice import FIXTURE

LOST_EN = "Asks about delivery time twice, then goes quiet when the store does not say when."


class Guards(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.base = Path(d.name)
        self.root = self.base / "shared"

    def built(self, parent, plug_owner="north", owner="north"):
        folder = self.base / parent / "stock_watch"
        shutil.copytree(FIXTURE, folder)
        plug = json.loads((folder / "plug.json").read_text(encoding="utf-8"))
        plug["owner"] = plug_owner
        (folder / "plug.json").write_text(json.dumps(plug), encoding="utf-8")
        (folder.parent / "owner.json").write_text(json.dumps({"owner": owner}), encoding="utf-8")
        return folder, night.plug_mod.load(folder / "plug.json")

    def seen_at_two(self, kind):
        pool = shared.Pool(kind, self.root)
        pool.add(shared.LOST, LOST_EN, "owner-id:" + "1" * 32, "chat:1")
        pool.add(shared.LOST, LOST_EN, "owner-id:" + "2" * 32, "chat:2")

    def test_o02_a_plug_naming_another_owner_has_no_owner_id(self):
        folder, _ = self.built("agents", plug_owner="south", owner="north")
        # the agent's own folder is then its state folder (grow.owner_of); one whose owner.json names
        # another owner than its plug still has no id
        (folder / "owner.json").write_text(json.dumps({"owner": "north"}), encoding="utf-8")
        self.assertEqual(shared.owner_id(folder), "")
        self.assertFalse((folder.parent / shared.OWNER_ID_FILE).exists())
        self.assertFalse((folder / shared.OWNER_ID_FILE).exists())
        same, _ = self.built("more", plug_owner="north", owner="north")
        self.assertTrue(shared.owner_id(same).startswith("owner-id:"))

    def test_k03_an_arena_state_whose_owner_id_cannot_be_read_gets_no_shared_card(self):
        folder, _ = self.built("agents")
        kind = grow.for_state(folder, shared_root=self.root).kind
        self.seen_at_two(kind)
        self.assertEqual(len(grow.for_state(folder, shared_root=self.root).shared), 1)  # a readable id: the card
        (folder.parent / shared.OWNER_ID_FILE).write_text("not an id", encoding="utf-8")
        self.assertEqual(grow.for_state(folder, shared_root=self.root).shared, [])

    def test_p04_a_built_agent_outside_an_agents_folder_reads_no_shared_card(self):
        inside, plug = self.built("agents")
        self.seen_at_two(grow.kind_of(plug))
        self.assertEqual(len(practice.shared_cards(inside, plug)), 1)
        outside, plug = self.built("other")  # its folder's parent's parent is the same base, beside the pool
        self.assertEqual(practice.shared_cards(outside, plug), [])

    def test_p03_shared_cards_train_at_the_average_training_weight(self):
        arena = SimpleNamespace(train=[{"id": "persona-01", "arena_weight": 2.0}, {"id": "persona-02", "arena_weight": 4.0}])
        n = practice.Practice._train_on(arena, [{"id": run.GROWN + "shared-a", "arena_weight": 1.0},
                                                {"id": "persona-09", "arena_weight": 1.0}])
        self.assertEqual(n, 1)  # only a grown card is a shared practice customer
        self.assertEqual([c["arena_weight"] for c in arena.train], [2.0, 4.0, 3.0])

    def test_p07_with_no_training_card_no_shared_card_is_added(self):
        arena = SimpleNamespace(train=[])
        self.assertEqual(practice.Practice._train_on(arena, [{"id": run.GROWN + "shared-a"}]), 0)
        self.assertEqual(arena.train, [])


if __name__ == "__main__":
    unittest.main()
