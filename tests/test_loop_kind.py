"""Build sets the agent's kind from the card (reflection/quickstart.py, DECISIONS item 79): the card
names the job, picked from the kinds already running here, the plug names that kind, and a second
agent of that kind under the same owner is a sibling (arena/grow.py siblings). A fake model only;
nothing here calls the network."""
import json
import tempfile
import unittest
from pathlib import Path

from arena import grow
from engine import plug as plug_mod
from kit.db import Db
from reflection import morning as mo
from reflection import pages
from reflection import quickstart as qs
from tests.fake_model import FakeModel, say
from tests.test_quickstart import ROOT, card_reply, exam_reply, plug_reply


def with_kind(reply, kind, name=None, key=None):
    """A card reply from tests/test_quickstart.py with the card's kind set, and its name and key."""
    d = json.loads(reply["content"])
    d["card"]["kind"] = kind
    if name is not None:
        d["card"]["name"], d["card"]["key"] = name, key
    return say(json.dumps(d))


class BuildSetsTheKind(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json")], reports=self.folder)

    def page(self, *script):
        self.model = FakeModel(*script)
        self.p = pages.Pages(self.m, model=self.model)

    def send(self, text):
        return self.p.actions["/quickstart"](self.m, {"text": [text]})

    def owner(self, name="demo"):
        agents = self.folder / "agents"
        agents.mkdir(exist_ok=True)
        (agents / "owner.json").write_text(json.dumps({"owner": name}), encoding="utf-8")
        return agents

    def build_one(self, kind, name, key):
        self.page(with_kind(card_reply(), kind, name, key), plug_reply(), exam_reply())
        self.send("a sales agent for my second store")
        self.p.actions["/quickstart/build"](self.m, {})
        self.p.actions["/quickstart/clear"](self.m, {})
        return plug_mod.load(self.folder / "agents" / key / "plug.json")

    def test_the_plug_and_the_card_name_the_kind_from_the_card(self):
        plug = self.build_one("sales", "Boots seller", "boots_seller")
        self.assertEqual(plug.kind, "sales")
        card = json.loads((self.folder / "agents" / "boots_seller" / "card.json").read_text(encoding="utf-8"))
        self.assertEqual(card["kind"], "sales")

    def test_a_second_agent_of_the_same_kind_is_a_sibling(self):
        agents = self.owner()
        self.build_one("sales", "Boots seller", "boots_seller")
        self.build_one("sales", "Bags seller", "bags_seller")
        self.build_one("support", "Returns helper", "returns_helper")
        self.assertEqual(grow.siblings(agents, "sales"), ["bags_seller", "boots_seller"])
        self.assertEqual(grow.siblings(agents, "support"), ["returns_helper"])

    def test_no_kind_or_a_bad_one_falls_back_to_the_agents_name(self):
        for bad in ("", "Sales Agent!", "1sales", "../sales", 7):
            with self.subTest(bad=bad):
                self.assertEqual(qs.kind_word(bad), "")
        self.assertEqual(qs.kind_word(" Order Taking "), "order_taking")
        plug = self.build_one("Sales Agent!", "Stock watcher", "stock_watcher")
        self.assertEqual(plug.kind, "stock_watcher")

    def test_the_card_prompt_names_the_kinds_already_running(self):
        self.build_one("sales", "Boots seller", "boots_seller")
        self.page(with_kind(card_reply(), "returns"))
        self.send("another agent")
        prompt = self.model.calls[0]["messages"][0]["content"]
        kinds = prompt.split("Kinds already running here: ", 1)[1].split(".", 1)[0]
        self.assertIn("sales", kinds.split(", "))
        self.assertIn("assistant", kinds.split(", "))
        self.assertIn('"kind": ""', prompt)

    def test_the_kind_is_read_back_to_the_model_on_a_change(self):
        self.page(with_kind(card_reply(), "sales"), with_kind(card_reply(), "sales"))
        self.send("a sales agent")
        self.send("make it shorter")
        back = json.loads(self.model.calls[1]["messages"][2]["content"])
        self.assertEqual(back["card"]["kind"], "sales")


if __name__ == "__main__":
    unittest.main()
