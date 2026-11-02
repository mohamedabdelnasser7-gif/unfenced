"""Practice customers that behave like the owner's real customers (arena/madeup.py blend; DECISIONS
items 51 and 59). Only the made-up demo cards (demo/personas/cards) stand in for an owner's cleaned
real cards; nothing here reads arena/real. Fake models only."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path

from arena import madeup, practice, run
from kit import turn
from reflection import quickstart as qs
from tests.fake_model import FakeModel, clean_env, say
from tests.test_arena_practice import FIXTURE, PEOPLE, World
from tests.test_quickstart import card_reply, exam_reply, plug_reply

DEMO = Path(run.DEMO_CARDS)
OWNER = "acme"
BLEND_PEOPLE = [{k: v for k, v in p.items() if k not in ("language", "length")} for p in PEOPLE] + [
    {"want": ["to check one item"], "worry": "it is a waste of time", "settles_it": ["one short answer"],
     "opening": "one item", "examples": ["Quick one, is it there?"]},
    {"want": ["only to look around"], "worry": "nothing in mind", "settles_it": ["nothing today"],
     "opening": "a look around", "examples": ["Just looking"], "why_not": "only looking today"},
]


class BlendWorld(World):
    """World with the blend's call answered too; every blend ask is kept."""

    def __init__(self, people=None, **kw):
        super().__init__(**kw)
        self.blend_people = BLEND_PEOPLE if people is None else people
        self.blend_asks = []

    def chat(self, messages, tools=None, **kw):
        if messages[0]["content"] == madeup.BLEND_SYSTEM:
            self.calls["cards"] += 1
            self.blend_asks.append(messages[1]["content"])
            return say(json.dumps({"customers": self.blend_people}))
        return super().chat(messages, tools, **kw)


def demo_cards():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DEMO.glob("persona-*.json"))}


def lines_of(cards):
    """Every want, settles-it and example line of the real cards: none may reach the model or a new card."""
    return {x for c in cards.values() for k in ("want", "buy_trigger", "examples") for x in c[k]}


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()                 # beside the database
        self.agents = self.root / "agents"
        self.folder = self.agents / "stock_watch"
        shutil.copytree(FIXTURE, self.folder)
        self.card = turn.load(self.folder).card

    def own(self, plug_owner=OWNER, marker=OWNER, cards=None):
        """owner.json in agents/ naming marker, the plug naming plug_owner, and the real cards in real-cards/."""
        if marker is not None:
            (self.agents / "owner.json").write_text(json.dumps({"owner": marker}), encoding="utf-8")
        raw = json.loads((self.folder / "plug.json").read_text(encoding="utf-8"))
        if plug_owner is not None:
            raw["owner"] = plug_owner
        (self.folder / "plug.json").write_text(json.dumps(raw), encoding="utf-8")
        real = self.agents / madeup.REAL_FOLDER
        real.mkdir(exist_ok=True)
        for cid, c in (demo_cards() if cards is None else cards).items():
            (real / f"{cid}.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        return real

    def main(self, world, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = practice.main(["--agent", str(self.folder), "--quick", *argv], agent_model=world,
                                 customer_model=world, judge_model=world)
        self.assertEqual(code, 0, err.getvalue())
        return out.getvalue()


class OwnerScope(Base):
    def test_the_owners_real_cards_are_read_when_the_plug_names_the_owner(self):
        self.own()
        got = madeup.owner_cards(self.folder)
        self.assertEqual([b["id"] for b in got], sorted(demo_cards()))

    def test_another_owner_or_no_marker_or_no_plug_owner_reads_none(self):
        for plug_owner, marker in (("other", OWNER), (OWNER, None), (None, OWNER)):
            with self.subTest(plug_owner=plug_owner, marker=marker):
                self.setUp()
                self.own(plug_owner=plug_owner, marker=marker)
                self.assertIsNone(madeup.owner_cards(self.folder))

    def test_a_linked_folder_a_linked_card_and_too_few_or_none_winnable_read_none(self):
        cards = demo_cards()
        real = self.own(cards={k: cards[k] for k in ("persona-01", "persona-07")})
        os.unlink(real / "persona-01.json")
        os.symlink(DEMO / "persona-01.json", real / "persona-01.json")
        self.assertIsNone(madeup.owner_cards(self.folder))  # the link is skipped: one card left
        self.setUp()
        self.own(cards={k: cards[k] for k in ("persona-07", "persona-08")})  # both unwinnable
        self.assertIsNone(madeup.owner_cards(self.folder))
        self.setUp()
        real = self.own(cards={})
        shutil.rmtree(real)
        os.symlink(DEMO, real)
        self.assertIsNone(madeup.owner_cards(self.folder))

    def test_only_behaviour_fields_are_read_and_odd_ones_are_skipped(self):
        cards = demo_cards()
        cards["persona-02"] = dict(cards["persona-02"], worry="Ahmed said the box came open, call 0100")
        cards["persona-03"] = dict(cards["persona-03"], style="loud")
        cards["persona-04"] = dict(cards["persona-04"], patience={"median": 1, "most": 2.5})
        self.own(cards=cards)
        got = {b["id"]: b for b in madeup.owner_cards(self.folder)}
        self.assertNotIn("persona-03", got)
        self.assertNotIn("persona-04", got)
        self.assertEqual(got["persona-02"]["worry"], madeup.OTHER)
        self.assertEqual(got["persona-08"]["why"], "no budget")
        for b in got.values():
            self.assertEqual(set(b), {"id", "worry", "unwinnable", "why", "patience", "length", "language",
                                      "voice_notes", "opening", "weight", "share"})
            self.assertEqual(set(b["opening"]), set(madeup.BEHAVIOUR_OPENINGS))


class Blend(Base):
    def blend(self, world=None):
        self.own()
        world = world or BlendWorld()
        profiles = madeup.owner_cards(self.folder)
        cards, written = madeup.for_agent(self.folder, "stock_watch", self.card, world, profiles)
        return world, profiles, cards, written

    def test_the_model_gets_behaviour_labels_and_the_agents_card_and_no_real_line(self):
        world, _, _, _ = self.blend()
        self.assertEqual(len(world.blend_asks), 1)
        ask = world.blend_asks[0]
        for line in lines_of(demo_cards()):
            self.assertNotIn(line, ask)
            self.assertNotIn(json.dumps(line, ensure_ascii=False)[1:-1], ask)
        sent = json.loads(ask)
        self.assertEqual(sent["agent_card"]["does"], self.card["does"])
        self.assertEqual(set(sent["people"][0]), {"worry_kind", "patience", "language", "length",
                                                  "can_reach_good_result"})
        self.assertEqual([p["worry_kind"] for p in sent["people"]],
                         [c["worry"] for c in demo_cards().values()])
        self.assertEqual(sent["people"][7]["why_not_kind"], "no budget")
        self.assertEqual(sent["people"][0]["language"], "arabic")

    def test_cards_copy_behaviour_only_and_are_marked(self):
        _, _, cards, written = self.blend()
        self.assertTrue(written)
        real = list(demo_cards().values())
        self.assertEqual(len(cards), len(real))
        lines = lines_of(demo_cards())
        for c, r, said in zip(cards, real, BLEND_PEOPLE):
            self.assertIs(c["made_up"], True)
            self.assertEqual(c["behaviour_from"], [r["id"]])
            self.assertEqual((c["unwinnable"], c["arena_weight"], c["share"]), (r["unwinnable"], r["arena_weight"],
                                                                                r["share"]))
            self.assertEqual(c["patience"], {"median": float(r["patience"]["median"]), "most": r["patience"]["most"]})
            self.assertEqual(c["style"]["length"], r["style"]["length"])
            self.assertEqual(c["style"]["language"], r["style"]["language"])
            self.assertEqual(c["style"]["voice_notes"], r["style"]["voice_notes"])
            self.assertEqual((c["chats"], c["won"], c["lost"]), (0, 0, 0))
            self.assertFalse(set(c["want"] + c["buy_trigger"] + c["examples"]) & lines)
            self.assertAlmostEqual(sum(c["style"]["opening"].values()), 1.0, places=2)
            self.assertLessEqual(set(c["style"]["opening"]), {*madeup.BEHAVIOUR_OPENINGS, said["opening"]})
        self.assertEqual(cards[0]["want"], BLEND_PEOPLE[0]["want"])
        self.assertEqual(cards[6]["why_unwinnable"], "just browsing")  # no why from the model: the kind label
        self.assertEqual(cards[7]["why_unwinnable"], "only looking today")
        self.assertIsNone(cards[5]["why_unwinnable"])  # can reach it: a why the model wrote is dropped

    def test_the_same_real_cards_play_again_and_a_changed_one_writes_new_customers(self):
        world, _, _, _ = self.blend()
        profiles = madeup.owner_cards(self.folder)
        _, written = madeup.for_agent(self.folder, "stock_watch", self.card, world, profiles)
        self.assertFalse(written)
        c = demo_cards()["persona-01"]
        c["patience"] = {"median": 3, "most": 3}
        (self.agents / madeup.REAL_FOLDER / "persona-01.json").write_text(json.dumps(c), encoding="utf-8")
        _, written = madeup.for_agent(self.folder, "stock_watch", self.card, world, madeup.owner_cards(self.folder))
        self.assertTrue(written)
        self.assertEqual(world.calls["cards"], 2)

    def test_saved_made_up_customers_are_not_taken_for_a_blend(self):
        world = BlendWorld()
        madeup.for_agent(self.folder, "stock_watch", self.card, world)
        self.own()
        _, written = madeup.for_agent(self.folder, "stock_watch", self.card, world, madeup.owner_cards(self.folder))
        self.assertTrue(written)

    def test_an_unreadable_or_thin_answer_is_a_model_fault(self):
        for people in ([], [{"want": [], "worry": ""}] * 8, [BLEND_PEOPLE[7]] + [{}] * 7):
            with self.subTest(people=len(people)):
                self.setUp()
                with self.assertRaises(madeup.Unreadable):
                    self.blend(BlendWorld(people=people))


class PracticeDefault(Base):
    def test_practice_blends_when_owner_cards_exist_and_says_so(self):
        self.own()
        world = BlendWorld()
        rep = json.loads(self.main(world, "--json"))
        self.assertEqual((rep["made_up"], rep["behaviour_from"]), (True, 8))
        self.assertEqual(len(world.blend_asks), 1)
        text = self.main(world)
        self.assertIn("behaving like 8 of the owner's real customers", text)

    def test_practice_makes_them_up_with_no_owner_cards(self):
        self.own(plug_owner="other")
        world = BlendWorld()
        rep = json.loads(self.main(world, "--json"))
        self.assertEqual((rep["made_up"], rep["behaviour_from"]), (True, 0))
        self.assertEqual(world.blend_asks, [])
        self.assertEqual(world.calls["cards"], 1)


class BuildNamesTheOwner(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def build(self):
        page = types.SimpleNamespace(reports=self.root, plugs={})
        quick = qs.QuickStart(FakeModel(card_reply(), plug_reply(), exam_reply()))
        quick.say(page, "an agent that tells my customers what is in stock")
        quick.build(page)
        return self.root / qs.AGENTS / "stock_watcher"

    def test_owner_json_beside_the_agents_names_the_plugs_owner(self):
        (self.root / qs.AGENTS).mkdir()
        (self.root / qs.AGENTS / "owner.json").write_text(json.dumps({"owner": OWNER}), encoding="utf-8")
        folder = self.build()
        self.assertEqual(turn.load(folder).plug.owner, OWNER)

    def test_no_owner_json_or_an_odd_one_names_none(self):
        self.assertEqual(turn.load(self.build()).plug.owner, "")
        self.setUp()
        (self.root / qs.AGENTS).mkdir()
        (self.root / qs.AGENTS / "owner.json").write_text(json.dumps({"owner": "Not A Name!"}), encoding="utf-8")
        self.assertEqual(turn.load(self.build()).plug.owner, "")


if __name__ == "__main__":
    unittest.main()
