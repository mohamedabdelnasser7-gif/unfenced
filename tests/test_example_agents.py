"""The example agents a fresh clone shows on Agents (reflection/examples.py, examples/agents/): copied once into
the page's agents folder by python3 -m unfenced, never over the user's own agent, and then an agent like any
Quick start built. Fake models only, nothing served, no real data."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import levels, madeup
from engine import plug as plug_mod
from kit import sample, turn
from reflection import examples, morning as mo, pages, quickstart as qs, turn_exam
from tests.fake_model import clean_env
from tests.test_arena_practice import World

AGENT = "family_dinner_planner"
SHIPPED = examples.SOURCE / AGENT


def start(db):
    """python3 -m unfenced on db as its default database, the page itself not started: what it printed."""
    import unfenced.__main__ as entry
    with mock.patch.object(entry, "DEFAULT_PATH", db), mock.patch.object(mo, "main", return_value=0), \
            mock.patch("builtins.print") as said:
        assert entry.main([]) == 0
    return [c.args[0] for c in said.call_args_list]


def tree(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


class Install(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.db = Path(d.name).resolve() / "data" / "ascent.db"
        self.agents = self.db.parent / "agents"

    def test_a_fresh_start_installs_the_example_once_as_shipped(self):
        said = start(self.db)
        self.assertTrue(self.db.is_file())
        self.assertEqual(tree(self.agents / AGENT), tree(SHIPPED))
        self.assertIn(f"Added the example agent {AGENT} to Agents. Like every agent, it starts with zero lessons.",
                      said)
        self.assertEqual(json.loads((self.agents / examples.MARK).read_text())["copied"], [AGENT])
        self.assertEqual([a.name for a in turn.built(self.db.parent)], [AGENT])  # the mark is no agent

    def test_a_second_start_neither_duplicates_nor_overwrites(self):
        start(self.db)
        mine = self.agents / AGENT / "instructions.md"
        mine.write_text("The user's own words now.\n", encoding="utf-8")
        said = start(self.db)
        self.assertEqual(mine.read_text(encoding="utf-8"), "The user's own words now.\n")
        self.assertFalse([s for s in said if "example agent" in s])
        self.assertEqual(sorted(p.name for p in self.agents.iterdir()), [examples.MARK, AGENT])

    def test_an_example_the_user_removed_stays_removed(self):
        start(self.db)
        shutil.rmtree(self.agents / AGENT)
        start(self.db)
        self.assertFalse((self.agents / AGENT).exists())

    def test_the_users_own_agent_of_that_name_is_untouched(self):
        own = self.agents / AGENT
        own.mkdir(parents=True)
        (own / "notes.txt").write_text("mine", encoding="utf-8")
        said = start(self.db)
        self.assertEqual(tree(own), {"notes.txt": b"mine"})
        self.assertFalse([s for s in said if "example agent" in s])
        self.assertFalse((self.agents / examples.MARK).exists())

    def test_a_name_an_agent_on_the_page_has_is_never_taken(self):
        self.agents.mkdir(parents=True)
        self.assertEqual(examples.install(self.db, {AGENT}), [])
        self.assertEqual(examples.install(self.db, {"sales"}), [AGENT])
        with tempfile.TemporaryDirectory() as d:  # the built-in name, even when no plug is on the page
            src = Path(d) / "sales"
            shutil.copytree(SHIPPED, src)
            self.assertEqual(examples.install(self.db, (), source=d), [])
        self.assertFalse((self.agents / "sales").exists())

    def test_an_unreadable_mark_or_a_linked_agents_folder_copies_nothing(self):
        self.agents.mkdir(parents=True)
        (self.agents / examples.MARK).write_text("not json", encoding="utf-8")
        with self.assertLogs(examples.log, "WARNING"):
            self.assertEqual(examples.install(self.db), [])
        self.assertFalse((self.agents / AGENT).exists())
        with tempfile.TemporaryDirectory() as d:
            db = Path(d).resolve() / "x" / "ascent.db"
            db.parent.mkdir()
            (db.parent / "agents").symlink_to(d)
            with self.assertLogs(examples.log, "WARNING"):
                self.assertEqual(examples.install(db), [])

    def test_a_named_database_gets_no_example(self):
        import unfenced.__main__ as entry
        with mock.patch.object(entry, "DEFAULT_PATH", self.db), mock.patch.object(mo, "main", return_value=0), \
                mock.patch("builtins.print"):
            entry.main(["--db", "other.db"])
        self.assertFalse(self.agents.exists())


class Shipped(unittest.TestCase):
    """The shipped folder is an agent Quick start would build today, with no lessons and no saved run."""

    def test_only_build_files_and_nothing_from_a_run(self):
        names = set(tree(SHIPPED))
        cards = {n for n in names if n.startswith(madeup.FOLDER + "/")}
        self.assertEqual(names - cards, set(qs.FILES) | {sample.FILE})
        self.assertTrue(cards and all(madeup.CARD_FILE.fullmatch(n.split("/")[1]) for n in cards))

    def test_the_plug_passes_the_plug_check_and_loads(self):
        plug = json.loads((SHIPPED / "plug.json").read_text(encoding="utf-8"))
        self.assertIsNone(qs.check_plug(plug))
        self.assertEqual(plug_mod.from_dict(plug).agent, AGENT)
        self.assertEqual(plug["exam"], turn_exam.plug_exam())
        self.assertEqual(plug["trial"], qs.STRICT_TRIAL)
        agent = turn.load(SHIPPED)
        self.assertEqual(agent.card["name"], "Family Dinner Planner")
        raw = (SHIPPED / "instructions.md").read_text(encoding="utf-8").strip()
        self.assertEqual(agent.instructions, raw)  # nothing left for the load time fixes to change
        self.assertTrue(raw.endswith(qs.scope_line(agent.card)))

    def test_its_level_is_the_one_quick_start_sets_from_the_card(self):
        card = json.loads((SHIPPED / "card.json").read_text(encoding="utf-8"))
        self.assertEqual(levels.read(SHIPPED), levels.pick(None, card))

    def test_its_exam_and_practice_customers_are_from_this_card_and_made_up(self):
        card = json.loads((SHIPPED / "card.json").read_text(encoding="utf-8"))
        exam = json.loads((SHIPPED / "exam.json").read_text(encoding="utf-8"))
        seen = {k: card[k] for k in ("name", "does", "good", "never", "case")}  # what Build writes it from
        self.assertEqual(exam["from_card"], turn_exam.fingerprint(seen))
        self.assertTrue(all(len(t["customer"]) < turn_exam.MAX_LINE for s in exam["situations"] for t in s["turns"]))
        agent = turn.load(SHIPPED)
        cards = madeup.read(SHIPPED / madeup.FOLDER, AGENT, agent.card)
        self.assertEqual(len(cards), 6)
        self.assertTrue(all(c["made_up"] is True and c["chats"] == 0 for c in cards))

    def test_its_sample_data_is_all_made_up_and_labelled(self):
        data = sample.read(SHIPPED)
        self.assertTrue(data["rows"] and all(r["by"] == sample.MADE_UP for r in data["rows"]))
        self.assertEqual(sample.words(data), "Sample data made for this agent: family dinner profiles, 12 made up.")


class OnThePage(unittest.TestCase):
    """Installed, it is on Agents and Run the Arena takes it, as an agent made in Quick start."""

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name).resolve()
        from kit.db import Db
        self.db = Db(str(self.dir / "ascent.db"))
        self.addCleanup(self.db.close)
        self.assertEqual(examples.install(self.dir / "ascent.db", {"sales"}), [AGENT])
        self.m = mo.Morning(self.db, [plug_mod.load(mo.ROOT / "sales" / "plug.json")], reports=self.dir,
                            db_path=self.dir / "ascent.db")
        self.assertEqual(self.m.add_built(), [AGENT])
        self.world = World()
        self.m.arena_models = lambda: (self.world, self.world, self.world)
        self.m.arena_shape = {"matches": 1, "rounds": 1}
        self.starts = []
        self.m.arena_start = lambda work, name: self.starts.append((work, name))
        self.p = pages.Pages(self.m)

    def test_the_agents_page_lists_it_and_its_overview_labels_the_sample_data(self):
        listed = self.p.get("/agents", {}, "t")
        self.assertIn(f'href="/agents/{AGENT}"', listed)
        self.assertIn("Family dinner planner", listed)  # its name on the list, as any built agent's
        page = self.p.get(f"/agents/{AGENT}", {}, "t")
        self.assertIn("Sample data made for this agent: family dinner profiles, 12 made up.", page)
        self.assertIn(f'action="{pages.ARENA_PATH}"', page)

    def test_run_the_arena_accepts_it_and_plays_on_fake_models(self):
        before = tree(SHIPPED)
        self.assertEqual(self.m.run_arena(AGENT, full=True), mo.ARENA_STARTED)
        self.assertEqual([n for _, n in self.starts], [f"arena-{AGENT}"])
        self.starts[0][0]()  # the thread's work, here
        self.assertFalse(self.m.arena_running(AGENT))
        self.assertIn(AGENT, self.m.read_arena()[0])
        self.assertGreater(self.world.calls["judge"], 0)
        self.assertTrue(list((self.dir / "agents" / AGENT).glob("arena-*")))  # the run's files are the copy's
        self.assertEqual(tree(SHIPPED), before)  # the repo's folder is never written


if __name__ == "__main__":
    unittest.main()
