"""The two tab page (reflection/pages.py): Today, Agents, an agent's page, New agent, the answers
it adds to the morning page (Modify through the exam, a correction) and the demo day switch.
No model call: the examiner is a fake."""
import unittest
from pathlib import Path

from engine import exam as exam_mod
from engine import plug as plug_mod
from engine import risk
from engine.lessons import IDEA, PULLED, TRYING, WAITING
from kit.db import Db
from reflection import morning as mo
from reflection import pages

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0
LINE = "Ask which size they wear in Adidas before naming ours."


def high(text, high_about, low_about):
    return risk.HIGH


def examiner(passed, calls):
    def run(text, tags):
        calls.append(text)
        row = exam_mod.Row(1, "s1", "guard", passed, "" if passed else "no_shop", "" if passed else "why")
        return exam_mod.Result(passed, [row], calls=1)
    return run


class TwoTabs(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plugs = [plug_mod.load(ROOT / "sales" / "plug.json"), plug_mod.load(ROOT / "assistant" / "plug.json")]
        self.m = mo.Morning(self.db, self.plugs, judge=high)
        self.p = pages.Pages(self.m)

    def get(self, path, query=None, token="t"):
        return self.p.get(path, query or {}, token)

    def waiting(self, text=LINE):
        return self.m.lessons["sales"].propose(text, ["asking"], sources=[], now=NOW)

    def test_today_empty_has_no_count_and_two_tabs(self):
        page = self.get("/")
        self.assertIn("Nothing needs you today", page)
        for gone in (">Lessons<", ">Ideas<", ">Facts<", "—", "–"):
            self.assertNotIn(gone, page)
        self.assertIn(">Today</a>", page)
        self.assertIn(">Agents</a>", page)

    def test_today_card_with_modify_and_one_yes(self):
        lid = self.waiting()
        page = self.get("/")
        self.assertIn(LINE, page)
        self.assertIn('action="/modify"', page)
        self.assertEqual(page.count('class="yes"'), 1)
        self.assertNotIn("Nothing needs you today", page)
        self.assertNotIn(f"Lesson {lid}", page)  # no raw ids in words

    def test_static_copy_has_no_buttons(self):
        self.waiting()
        self.assertNotIn("<form", self.get("/", token=None).split('class="cards"')[1].split("Last night")[0])

    def test_modify_runs_the_exam_again(self):
        calls = []
        self.m.exams = {"sales": examiner(False, calls)}
        lid = self.waiting()
        said = self.m.modify(lid, LINE + " Never on the new drop.", "")
        self.assertEqual(len(calls), 1)
        self.assertIn("waits for a yes", said)
        self.assertEqual(self.m.lessons["sales"].get(lid)["state"], PULLED)
        new = [les for les in self.m.lessons["sales"].mine() if les["state"] == WAITING]
        self.assertEqual([les["text"] for les in new], [LINE + " Never on the new drop."])

    def test_correction_starts_now_and_is_an_idea_line(self):
        calls = []
        self.m.exams = {"sales": examiner(True, calls)}
        self.m.correct("sales", "When someone asks for a photo, send the product link first.")
        les = self.m.lessons["sales"].mine()[-1]
        self.assertEqual((les["kind"], les["state"]), (IDEA, TRYING))
        self.assertIn(pages.CORRECTED, les["source"])
        self.assertEqual(len(calls), 1)
        page = self.get("/agents/sales")
        self.assertIn("Hotfix", page)
        self.assertIn('action="/correct"', page)

    def test_agents_list_and_unknown_agent(self):
        page = self.get("/agents")
        self.assertIn("Sales agent", page)
        self.assertIn("Personal assistant", page)
        self.assertIn('href="/new"', page)
        self.assertIsNone(self.get("/agents/nobody"))
        self.assertIsNone(self.get("/elsewhere"))

    def test_new_agent_routes_or_says_not_yet(self):
        self.assertEqual(pages.route_ask("a sales agent for my boots store", self.m.plugs), "sales")
        self.assertEqual(pages.route_ask("a personal assistant for my inbox", self.m.plugs), "assistant")
        self.assertIsNone(pages.route_ask("a lawyer that drafts contracts", self.m.plugs))
        self.assertIn("Not yet", self.get("/new", {"ask": ["a lawyer that drafts contracts"]}))
        self.assertIn("/new/build?agent=sales", self.get("/new", {"ask": ["sell boots on WhatsApp"]}))
        build = self.get("/new/build", {"agent": ["sales"]})
        self.assertIn("Practice matches", build)
        self.assertNotIn(">won", build.split("</style>")[1].lower())

    def test_back_stays_on_the_page(self):
        for bad in ("https://evil.example/", "//evil.example/x", "/agents/../x", "/morning"):
            self.assertEqual(self.p.back(bad), "/")
        self.assertEqual(self.p.back("/agents/sales"), "/agents/sales")


class DemoDays(unittest.TestCase):
    def test_day_switch_marks_sample_data_and_picks_the_day(self):
        plugs = [plug_mod.load(ROOT / "sales" / "plug.json")]
        days = {}
        for d in (1, 2, 3):
            db = Db(":memory:")
            self.addCleanup(db.close)
            days[d] = mo.Morning(db, plugs, judge=high)
        days[2].lessons["sales"].propose(LINE, ["asking"], sources=[], now=NOW)
        p = pages.Pages(days=days)
        one, two = p.get("/", {"day": ["1"]}, "t"), p.get("/", {"day": ["2"]}, "t")
        self.assertIn("Sample data", one)
        self.assertIn("Day 3", one)
        self.assertNotIn(LINE, one)
        self.assertIn(LINE, two)
        self.assertIs(p.morning_for(p.back("/?day=2")), days[2])
        self.assertEqual(p.back("/agents?day=9"), "/agents?day=1")


if __name__ == "__main__":
    unittest.main()
