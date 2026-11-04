"""The shared pool in the Arena (arena/grow.py, arena/run.py, reflection/shared.py; DECISIONS items 51, 83):
each lost chat a night adds, already cleaned, is given to the shared pool of its kind as one clean
pattern; a lost pattern seen at 2 or more owners becomes a fresh practice customer for any owner's
Arena that trains only and never takes the gate. One owner's real practice customers never reach
another owner: the fresh card holds the pattern and nothing of any chat. Made-up chats, the
scripted tagger and a fake writer; no key, no network."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import grow, run
from arena.scripted import ScriptedModel
from arena.tag import Tagger
from kit.db import Db
from reflection import night
from reflection import shared
from tests.fake_model import FakeModel, clean_env, say
from tests.test_arena_grow import (HARD, LOST, NAME, NOW, PHONE, SALES_PLUG, SINCE, recipe, write_chats, write_owner,
                                   write_plug)
from tests.test_arena_run import Agent, Customer, card
from tests import test_arena_practice as practice_tests
from arena import practice

LINE = "Asks about delivery time twice, then goes quiet when the store does not say when."
NEAR = "Asks about the delivery time twice, then goes quiet when the store does not say when."
LEAKY = "Customer Ahmed asks for a discount after the price and goes quiet."
# owner B's own lost chat: other words than owner A's, so a crossing would show
LOST_B = ("c-lost-b", [("user", "عندكم تيشيرت ازرق لارج؟ ابعتلي على التليفون", 80, None),
                       ("assistant", "التيشيرت ب 600 جنيه، اللارج متاح", 79.9, None)])
WORD_A, WORD_B = "السودا", "تيشيرت"  # a word only owner A's chat holds, and one only owner B's


def tmp(test):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def writer(*lines):
    model = FakeModel(*[say(json.dumps({"pattern": x})) for x in lines])
    return shared.Writer(model=model), model


def down(messages, tools):
    """A model step that fails, as a host that is down does."""
    raise RuntimeError("down")


def owner_at(test, name):
    """An owner's state folder with one sales agent under it: (owner folder, agent folder)."""
    owner = tmp(test)
    write_owner(owner, name)
    write_plug(owner / f"store_{name}", f"store_{name}", "sales", owner=name)
    return owner, owner / f"store_{name}"


def grow_at(owner, name, root, *lines, chats=(LOST,), give_lost=shared.GIVE_LOST, calls=None):
    """One night of an owner's agent on made-up chats, giving its lost chats to the shared pool:
    (the owner's pool, the counts, the writer's fake model)."""
    db = Db(":memory:")
    try:
        write_chats(db, chats)
        pool = grow.Pool(owner, "sales")
        w, model = writer(*lines)
        link = shared.Link("sales", shared.owner_id(owner / f"store_{name}"), w, root, give_lost=give_lost)
        tag = ScriptedModel(recipe()) if calls is None else calls.model(ScriptedModel(recipe()))
        counts = grow.grow(db, pool, since=SINCE, until=NOW, tagger=Tagger(model=tag, cap=50, recipe=recipe()),
                           calls=calls, shared=link)
    finally:
        db.close()
    pool.rebuild(recipe())
    pool.save()
    return pool, counts, model


def turn_texts(pool):
    return [t["text"] for i in pool.items for t in i["turns"] if isinstance(t.get("text"), str)]


class SharedPracticeCustomers(unittest.TestCase):
    def setUp(self):
        self.root = tmp(self) / "shared"
        self.a, _ = owner_at(self, "north")
        self.b, self.b_agent = owner_at(self, "south")
        self.c, self.c_agent = owner_at(self, "east")
        self.base = [card(1, "size"), card(2, "price")]

    def both(self):
        pa, ca, _ = grow_at(self.a, "north", self.root, LINE)
        pb, cb, _ = grow_at(self.b, "south", self.root, NEAR, chats=(LOST_B,))
        return pa, ca, pb, cb

    def test_a_lost_pattern_seen_at_two_owners_becomes_a_training_card_for_any_owner(self):
        _, ca, _, cb = self.both()
        self.assertEqual((ca["patterns given"], cb["patterns given"]), (1, 1))
        cards = shared.practice_cards("sales", self.root)
        self.assertEqual(len(cards), 1)
        got = cards[0]
        self.assertTrue(got["id"].startswith("grown-shared-"))
        self.assertEqual(got["shared"]["owners"], 2)
        pool = grow.for_state(self.c_agent, shared_root=self.root)  # a third owner plays it
        self.assertEqual([c["id"] for c in pool.shared], [got["id"]])
        self.assertEqual(pool.summary()["shared_cards"], 1)
        self.assertEqual(grow.for_state(self.b_agent, shared_root=self.root).shared, [])  # it gave it: not back
        self.assertEqual(shared.practice_cards("sales", self.root, but=shared.owner_id(self.b_agent)), [])
        pool = grow.for_state(self.c_agent, shared_root=self.root)
        for seed in range(6):
            _, held = run.split(self.base + pool.shared, seed=seed)
            held_ids = {c["id"] for c in held}
            self.assertNotIn(got["id"], held_ids)
            train, gate = grow.decks(self.base, pool, held_ids)
            self.assertIn(got["id"], [c["id"] for c in train])
            self.assertNotIn(got["id"], [c["id"] for c in gate])
        with self.assertRaises(run.Refused):
            run.split(self.base + pool.shared, [got["id"]])

    def test_with_no_shared_folder_given_no_shared_card_is_read(self):
        self.both()
        self.assertEqual(grow.for_state(self.c_agent).shared, [])
        self.assertEqual(shared.practice_cards("sales", None), [])

    def test_a_pattern_seen_at_one_owner_only_makes_no_card(self):
        two = (LOST, (LOST[0] + "-2", LOST[1]))
        _, counts, _ = grow_at(self.a, "north", self.root, LINE, NEAR, chats=two)
        self.assertEqual(counts["patterns given"], 2)
        self.assertEqual([len(p["owners"]) for p in shared.Pool("sales", self.root).patterns], [1])
        self.assertEqual(grow.for_state(self.b_agent, shared_root=self.root).shared, [])
        self.assertEqual(shared.practice_cards("sales", self.root), [])

    def test_one_owner_real_practice_customers_never_reach_another_owner(self):
        pa, _, pb, _ = self.both()
        a_texts, b_texts = turn_texts(pa), turn_texts(pb)
        self.assertTrue(any(WORD_A in t for t in a_texts) and any(WORD_B in t for t in b_texts))
        files = {"B's pool": (self.b / "practice-sales.json").read_text(encoding="utf-8"),
                 "the shared pool": (self.root / "patterns-sales.json").read_text(encoding="utf-8")}
        pool_b = grow.for_state(self.b_agent, shared_root=self.root)
        train, gate = grow.decks(self.base, pool_b, set())
        files["B's decks"] = json.dumps(train + gate, ensure_ascii=False)
        pool_c = grow.for_state(self.c_agent, shared_root=self.root)
        files["C's decks"] = json.dumps(sum(grow.decks(self.base, pool_c, set()), []), ensure_ascii=False)
        for where, text in files.items():
            for leak in (NAME, PHONE, WORD_A, *a_texts):
                self.assertNotIn(leak, text, where)
        self.assertNotIn(WORD_B, files["the shared pool"])
        self.assertNotIn(WORD_B, files["C's decks"])
        self.assertEqual(pool_c.items, [])  # C's own pool holds no chat of A or B
        # the fresh card from the shared pattern reaches C, holding the pattern only; B gave it, so not B
        fresh = pool_c.shared
        self.assertEqual(len(fresh), 1)
        self.assertIn("delivery time", fresh[0]["worry"])
        self.assertEqual((fresh[0]["want"], fresh[0]["examples"], fresh[0]["buy_trigger"]), ([], [], []))
        self.assertNotIn(fresh[0]["id"], files["B's decks"])
        self.assertIn(fresh[0]["id"], files["C's decks"])
        self.assertIn(fresh[0]["id"], files["C's decks"])
        with self.assertRaises(grow.Refused):  # an owner's pool still never opens another owner's file
            grow.Pool(self.b, "sales", path=self.a / "practice-sales.json")

    def test_the_writer_reads_the_cleaned_turns_only(self):
        _, _, model = grow_at(self.a, "north", self.root, LINE)
        sent = json.dumps(model.calls, ensure_ascii=False)
        self.assertEqual(len(model.calls), 1)
        self.assertNotIn(PHONE, sent)
        self.assertNotIn(NAME, sent)
        self.assertIn("[phone]", sent)

    def test_a_leaky_pattern_is_dropped_and_never_stored(self):
        _, counts, _ = grow_at(self.a, "north", self.root, LEAKY)
        self.assertEqual(counts["patterns dropped"], 1)
        self.assertNotIn("patterns given", counts)
        saved = (self.root / "patterns-sales.json").read_text(encoding="utf-8")
        self.assertNotIn("Ahmed", saved)
        self.assertEqual(shared.Pool("sales", self.root).patterns, [])

    def test_at_most_give_lost_chats_reach_the_writer_and_none_twice(self):
        two = (LOST, (LOST[0] + "-2", LOST[1]))
        _, counts, model = grow_at(self.a, "north", self.root, LINE, chats=two, give_lost=1)
        self.assertEqual((counts["patterns asked"], counts["lost"], len(model.calls)), (1, 2, 1))

    def test_a_writer_that_fails_is_asked_once_a_night(self):
        two = (LOST, (LOST[0] + "-2", LOST[1]))
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, two)
        model = FakeModel(down, say(json.dumps({"pattern": LINE})))
        link = shared.Link("sales", shared.owner_id(self.a / "store_north"), shared.Writer(model=model), self.root)
        counts = grow.grow(db, grow.Pool(self.a, "sales"), since=SINCE, until=NOW, shared=link,
                           tagger=Tagger(model=ScriptedModel(recipe()), cap=50, recipe=recipe()))
        self.assertEqual((counts["lost"], counts["patterns dropped"], len(model.calls)), (2, 1, 1))
        self.assertEqual(shared.Pool("sales", self.root).patterns, [])

    def test_a_hard_chat_that_was_won_is_not_given(self):
        _, counts, model = grow_at(self.a, "north", self.root, LINE, chats=(HARD,))
        self.assertEqual(counts["hard"], 1)
        self.assertEqual(model.calls, [])
        self.assertFalse(any(k.startswith("patterns") for k in counts), counts)

    def night_at(self, agent):
        """grow.night for an owner's agent on owner A's lost chat, the tagger and the writer stood in."""
        from arena import recipe as recipe_mod
        from engine import plug as plug_mod
        db = Db(str(agent / "ascent.db"))
        write_chats(db, [LOST])
        db.close()
        w = FakeModel(say(json.dumps({"pattern": LINE})))
        with mock.patch.object(grow, "tag_model", side_effect=[ScriptedModel(recipe()), w]):
            rep = grow.night(agent / "ascent.db", plug_mod.load(agent / "plug.json"), recipe_mod.EXAMPLE, SINCE, NOW,
                             folder=agent, own=True, shared_root=self.root)
        return rep, w, json.loads((agent / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"]

    def test_the_night_counts_no_shared_card_its_own_owner_gave(self):
        pool = shared.Pool("sales", self.root)
        pool.add(shared.LOST, LINE, shared.owner_id(self.b_agent), "chat:x")
        pool.add(shared.LOST, NEAR, "elsewhere", "chat:y")
        rep, _, _ = self.night_at(self.b_agent)
        self.assertFalse(rep.get("shared_cards"), rep)
        rep, _, _ = self.night_at(self.c_agent)
        self.assertEqual(rep.get("shared_cards"), 1, rep)

    def test_the_writer_counts_on_the_arena_call_cap(self):
        _, a_agent = owner_at(self, "west")
        rep, w, count = self.night_at(a_agent)
        self.assertEqual((rep.get("patterns given"), len(w.calls), count), (1, 1, 2))
        self.assertIn("1 lost chats given to the shared pool", grow.line(rep))
        with mock.patch.object(run, "DEFAULT_CAP", 1):
            rep, w, count = self.night_at(self.b_agent)
        self.assertEqual((rep.get("patterns dropped"), len(w.calls), count), (1, 0, 1))
        self.assertEqual(rep["stopped"], "the Arena's call cap")
        self.assertEqual([len(p["owners"]) for p in shared.Pool("sales", self.root).patterns], [1])

    def test_lesson_patterns_make_no_practice_customer(self):
        pool = shared.Pool("sales", self.root)
        pool.add(shared.LESSON, LINE, "north", "lesson:a:1")
        pool.add(shared.LESSON, NEAR, "south", "lesson:b:1")
        self.assertEqual(len(shared.Pool("sales", self.root).shared(shared.LESSON)), 1)
        self.assertEqual(shared.practice_cards("sales", self.root), [])
        self.assertEqual(grow.for_state(self.c_agent, shared_root=self.root).shared, [])

    def test_an_agent_that_names_no_owner_gives_nothing(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, [LOST])
        w, model = writer(LINE)
        counts = grow.grow(db, grow.Pool(self.a, "sales"), since=SINCE, until=NOW,
                           tagger=Tagger(model=ScriptedModel(recipe()), cap=50, recipe=recipe()),
                           shared=shared.Link("sales", "", w, self.root))
        self.assertEqual(counts["patterns skipped"], 1)
        self.assertEqual(model.calls, [])

    def test_the_night_line_names_the_shared_cards_and_the_patterns_given(self):
        rep = {"added": 1, "lost": 1, "grown_cards": 1, "items": 1, "siblings": [], "shared_cards": 3,
               "patterns given": 1}
        got = grow.line(rep)
        self.assertIn("3 more from patterns seen at 2 or more owners", got)
        self.assertIn("1 lost chats given to the shared pool as clean patterns", got)
        rep.pop("shared_cards"), rep.pop("patterns given")
        self.assertNotIn("shared pool", grow.line(rep))
        self.assertNotIn("owners", grow.line(rep))


class ArenaRun(unittest.TestCase):
    """arena/run.py main with a database reads the shared pool beside it."""

    def setUp(self):
        clean_env(self)
        self.c, self.agent = owner_at(self, "east")
        self.db_path = self.agent / "ascent.db"
        Db(str(self.db_path)).close()
        self.root = shared.root_for(self.db_path)
        a, _ = owner_at(self, "north")
        b, _ = owner_at(self, "south")
        grow_at(a, "north", self.root, LINE)
        grow_at(b, "south", self.root, NEAR, chats=(LOST_B,))
        self.cards = tmp(self) / "cards"
        self.cards.mkdir()
        for c in (card(1, "size"), card(2, "price")):
            (self.cards / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")

    def run_main(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.main(["--cards", str(self.cards), "--matches", "1", "--rounds", "1", "--db", str(self.db_path),
                             *extra], agent_model=Agent(), customer_model=Customer(buyers=("size", "price")))
        self.assertIn(code, (0, 1))
        return out.getvalue()

    def test_the_report_counts_the_shared_cards_and_the_text_names_them(self):
        rep = json.loads(self.run_main("--json"))
        self.assertEqual(rep["pool"]["shared_cards"], 1)
        self.assertFalse(any(i.startswith("grown-shared-") for i in rep["held_out_cards"]))
        self.assertIn("1 more from the shared pool of sales agents, patterns seen at 2 or more owners",
                      run.text(rep))

    def test_with_no_database_no_shared_pool_is_read(self):
        state = tmp(self)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            run.main(["--cards", str(self.cards), "--matches", "1", "--rounds", "1", "--state", str(state), "--json"],
                     agent_model=Agent(), customer_model=Customer(buyers=("size", "price")))
        rep = json.loads(out.getvalue())
        self.assertFalse(rep.get("pool", {}).get("shared_cards"))


class BuiltAgentPractice(practice_tests.Base):
    """A built agent practises through arena/practice.py: the shared lost patterns of its kind join its
    training draw only, never its gate."""

    def seed_pool(self, kind="stock_watch"):
        pool = shared.Pool(kind, self.root / shared.SHARED_DIR)
        pool.add(shared.LOST, LINE, "north", "chat:a")
        pool.add(shared.LOST, NEAR, "south", "chat:b")
        return shared.practice_cards(kind, self.root / shared.SHARED_DIR)[0]["id"]

    def test_shared_lost_patterns_train_a_built_agent_and_never_take_its_gate(self):
        cid = self.seed_pool()
        code, rep = self.main("--matches", "12", "--json")
        self.assertIn(code, (0, 1), self.err)
        self.assertEqual(rep["shared_cards"], 1)
        self.assertIn(cid, rep["training_cards"])
        self.assertNotIn(cid, rep["held_out_cards"])
        played = [m["id"] for m in self.matches() if m["persona"]["id"] == cid]
        self.assertTrue(played)  # it was drawn and played as a practice customer
        self.assertTrue(all("-t" in i and "-g" not in i for i in played), played)  # training matches only
        self.assertTrue(any("-g" in m["id"] for m in self.matches()))  # the gate did play, on other cards
        self.assertIn("1 more practice customers from the shared pool", practice.text(rep))

    def test_a_built_agent_never_practises_on_what_its_own_owner_gave(self):
        base = tmp(self)
        mine, other = base / "agents" / "store_north", base / "agents" / "store_east"
        for folder, name in ((mine, "north"), (other, "east")):
            write_plug(folder, folder.name, "sales", owner=name)
            write_owner(folder, name)
        pool = shared.Pool("sales", base / shared.SHARED_DIR)
        pool.add(shared.LOST, LINE, shared.owner_id(mine), "chat:a")
        pool.add(shared.LOST, NEAR, "south", "chat:b")
        load = grow.plug_mod.load
        self.assertEqual(practice.shared_cards(mine, load(mine / "plug.json")), [])
        self.assertEqual(len(practice.shared_cards(other, load(other / "plug.json"))), 1)
        (mine / shared.OWNER_ID_FILE).write_text("bad", encoding="utf-8")  # unreadable id: none, never its own
        self.assertEqual(practice.shared_cards(mine, load(mine / "plug.json")), [])

    def test_another_kind_or_no_agents_folder_reads_no_shared_card(self):
        self.seed_pool(kind="other_kind")
        _, rep = self.main("--matches", "2", "--json")
        self.assertEqual(rep["shared_cards"], 0)
        self.assertEqual(practice.shared_cards(self.root / "elsewhere" / "stock_watch", grow.plug_mod.load(
            self.folder / "plug.json")), [])


class NightWiring(unittest.TestCase):
    """reflection/night.py main hands the practice step the shared folder beside the database; the
    Sales agent names no owner, so it reads the pool and gives nothing."""

    def setUp(self):
        self.dir = tmp(self)
        self.db_path = self.dir / "ascent.db"
        db = Db(str(self.db_path))
        write_chats(db, [LOST])
        db.close()
        root = shared.root_for(self.db_path)
        a, _ = owner_at(self, "north")
        b, _ = owner_at(self, "south")
        grow_at(a, "north", root, LINE)
        grow_at(b, "south", root, NEAR, chats=(LOST_B,))
        rep = {"agent": "sales", "window": {"since": SINCE, "until": NOW}, "snapshot": {}}
        for p in (mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]),
                  mock.patch.object(night, "night", return_value=rep), mock.patch("kit.model.Model"),
                  mock.patch.object(grow, "tag_model", side_effect=lambda: ScriptedModel(recipe()))):
            p.start()
            self.addCleanup(p.stop)

    def test_the_night_reads_the_shared_cards_and_a_plug_with_no_owner_gives_nothing(self):
        from arena import recipe as recipe_mod
        before = (shared.root_for(self.db_path) / "patterns-sales.json").read_bytes()
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = night.main(["--plug", str(SALES_PLUG), "--db", str(self.db_path), "--json",
                               "--recipe", str(recipe_mod.EXAMPLE)])
        self.assertEqual(code, 0, err.getvalue())
        rep = json.loads(sorted(self.dir.glob("night-sales-*.json"))[0].read_text(encoding="utf-8"))["practice"]
        self.assertEqual(rep.get("shared_cards"), 1)
        self.assertEqual(rep.get("patterns skipped"), 1)
        self.assertNotIn("patterns given", rep)
        self.assertEqual((shared.root_for(self.db_path) / "patterns-sales.json").read_bytes(), before)

    def test_the_study_writer_counts_on_the_arena_day_cap(self):
        from reflection.study import PartError
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(night.main(["--plug", str(SALES_PLUG), "--db", str(self.db_path), "--json"]), 0)
        writer = night.night.call_args.kwargs["shared"].writer
        count = self.dir / run.CALLS_FILE
        count.write_text(json.dumps({"day": run.today(), "calls": run.DEFAULT_CAP - 1}), encoding="utf-8")
        writer(shared.LESSON, "sales", {"lesson": "x"})  # the mocked model answers; the call is counted
        self.assertEqual(json.loads(count.read_text(encoding="utf-8"))["calls"], run.DEFAULT_CAP)
        with self.assertRaises(PartError):
            writer(shared.LESSON, "sales", {"lesson": "x"})


if __name__ == "__main__":
    unittest.main()
