"""The two tab page (reflection/pages.py): Today, Agents, an agent's page, New agent, the answers
it adds to the morning page (Modify through the exam, a correction) and the demo day switch.
No model call: the examiner is a fake."""
import unittest
from pathlib import Path

from engine import exam as exam_mod
from engine import plug as plug_mod
from engine import risk
from engine.lessons import HOTFIX_SHARE, HOTFIX_SOURCE, IDEA, PULLED, TRYING, WAITING
from kit.db import Db
from reflection import morning as mo
from reflection import pages

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_793_000_000.0
LINE = "Ask which size they wear in Adidas before naming ours."


def high(text, high_about, low_about):
    return risk.HIGH


def low(text, high_about, low_about):
    return risk.LOW


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

    def page(self, judge=risk.no_judge, passed=True, calls=None):
        """A page whose Sales agent has an exam, as main() gives it (page_exams)."""
        self.m = mo.Morning(self.db, self.plugs, judge=judge, exams={"sales": examiner(passed, [] if calls is None else calls)})
        self.p = pages.Pages(self.m)
        return self.m

    def test_correction_is_a_hotfix_on_half_the_chats_at_once(self):
        calls = []
        self.page(judge=low, calls=calls)
        first = self.m.lessons["sales"].add("Ask which colour they like first.", ["all"], "typed", yes_by="the user",
                                            now=NOW)  # a lesson on trial on every stage: a correction never waits behind it
        said = self.m.correct("sales", "When someone asks for a photo, send the product link first.", now=NOW + 1)
        L = self.m.lessons["sales"]
        les = L.mine()[-1]
        self.assertEqual((les["kind"], les["state"], les["share"]), (IDEA, TRYING, HOTFIX_SHARE))
        self.assertEqual(L.get(first)["state"], TRYING)
        self.assertEqual(L.trial(les["id"])["days"], float(L.plug.level(plug_mod.FAST_LEVEL).days))
        self.assertEqual(les["source"], HOTFIX_SOURCE)
        self.assertIn(pages.CORRECTED, les["source"])
        self.assertTrue(L.exam_of(les["id"])["passed"])
        self.assertEqual(len(calls), 1)  # the page's exam, run once, is the one Lessons.correct saves
        self.assertIn("runs now as a hotfix in half the cases", said)
        page = self.get("/agents/sales")
        self.assertIn("Hotfix", page)
        self.assertIn('action="/correct"', page)

    def test_correction_with_no_exam_is_refused_and_nothing_is_added(self):
        self.m = mo.Morning(self.db, self.plugs, judge=low)  # no exam for the Sales agent here
        with self.assertRaises(mo.Refused) as e:
            mo.TWO_TAB_ACTIONS["/correct"](self.m, {"agent": ["sales"], "line": [LINE]}, now=NOW)
        self.assertEqual(str(e.exception), mo.NO_EXAM)
        self.assertEqual(self.m.lessons["sales"].mine(), [])
        with self.assertRaises(mo.Refused):
            self.page(judge=low).correct("assistant", LINE, now=NOW)  # the assistant has no exam either
        self.assertEqual(self.m.lessons["assistant"].mine(), [])

    def test_a_failed_exam_holds_a_correction_for_a_yes(self):
        self.page(judge=low, passed=False)
        said = self.m.correct("sales", "When someone asks for a photo, send the side view.", now=NOW)
        L = self.m.lessons["sales"]
        les = L.mine()[-1]
        self.assertEqual(les["state"], WAITING)
        self.assertIn("waits for your yes on Today", said)
        self.assertIn(les["id"], [c["id"] for c in self.m.view(now=NOW + 1)["cards"]])
        self.m.yes(les["id"], "", now=NOW + 60)
        self.assertEqual((L.get(les["id"])["state"], L.get(les["id"])["share"]), (TRYING, HOTFIX_SHARE))

    def test_high_risk_correction_waits_for_a_yes_on_today(self):
        self.page(judge=low)
        line = "When someone asks about the price, say the total is 1450 EGP with delivery."
        said = self.m.correct("sales", line, now=NOW)
        self.assertIn("high risk, so it waits for your yes on Today", said)
        L = self.m.lessons["sales"]
        les = L.mine()[-1]
        self.assertEqual((les["origin"], les["state"], les["risk"], les["yes_by"]), ("person", WAITING, "high", mo.BY))
        self.assertTrue(L.wants_yes(les["id"]))  # engine.lessons WANTS_YES: its writer's name is not the yes
        page = self.get("/")
        self.assertIn(line, page)
        self.assertIn("Your correction", page)
        self.assertIn("It waits for your yes because it states an amount of money", page)
        for engine_words in ("on the number list", "names the tool", "code check"):
            self.assertNotIn(engine_words, page)
        self.assertIn("Waits for your yes on Today", self.get("/agents/sales"))
        self.assertNotIn("Hotfix", self.get("/agents/sales"))
        self.m.yes(les["id"], "", now=NOW + 60)
        self.assertEqual((L.get(les["id"])["state"], L.get(les["id"])["share"]), (TRYING, HOTFIX_SHARE))
        self.assertIn("Hotfix", self.get("/agents/sales"))

    def test_judge_that_says_high_holds_a_correction_too(self):
        self.page(judge=high)
        self.m.correct("sales", "When someone asks for a photo, send the side view.", now=NOW)
        les = self.m.lessons["sales"].mine()[-1]
        self.assertEqual(les["state"], WAITING)
        self.assertIn("the risk check marked it high", self.get("/"))

    def test_a_judge_that_is_not_sure_holds_a_correction_too(self):
        """Lessons.correct: any high risk waits for a yes, a judge that is only unsure included (fail closed)."""
        self.page()
        self.m.correct("sales", "When someone asks for a photo, send the side view.", now=NOW)
        self.assertEqual(self.m.lessons["sales"].mine()[-1]["state"], WAITING)

    def test_accept_high_risk_is_not_the_yes_on_a_correction(self):
        """A high risk correction waits for a yes on Today even under Accept high risk (Lessons.correct)."""
        self.page(judge=low)
        self.m.lessons["sales"].switches.set_accept_high(True, "the user", now=NOW)
        self.m.correct("sales", "When someone asks about the price, say the total is 1450 EGP.", now=NOW + 1)
        les = self.m.lessons["sales"].mine()[-1]
        self.assertEqual((les["origin"], les["state"]), ("person", WAITING))
        self.assertIn(les["id"], [c["id"] for c in self.m.view(now=NOW + 2)["cards"]])

    def test_plain_risk_reads_plainly(self):
        self.assertEqual(pages.plain_risk("tool: delivery"),
                         "It waits for your yes because it tells the agent how to use one of its tools.")
        self.assertEqual(pages.plain_risk("core: copied from source 3; core: copied from source 4"),
                         "It waits for your yes because it copies words from the chats it came from.")
        self.assertIn("the risk check marked it high", pages.plain_risk(""))
        self.assertNotIn("/", pages.plain_risk("number: /\\d+/; promise: refund; policy: rule"))

    def test_agents_list_and_unknown_agent(self):
        page = self.get("/agents")
        self.assertIn("Sales agent", page)
        self.assertIn("Personal assistant", page)
        self.assertIn('href="/new"', page)
        self.assertIsNone(self.get("/agents/nobody"))
        self.assertIsNone(self.get("/elsewhere"))

    def test_new_agent_is_the_quick_start_box(self):
        page = self.get("/new", {"ask": ["a lawyer that drafts contracts"]})  # any field; the chat is tests/test_quickstart.py
        self.assertIn('action="/quickstart"', page)
        self.assertNotIn("Not yet", page)
        self.assertIn("Brainstorm", page)
        build = self.get("/new/build", {"agent": ["sales"]})
        self.assertIn("Practice matches", build)
        self.assertNotIn(">won", build.split("</style>")[1].lower())

    def test_build_page_says_plainly_there_is_nothing_to_do(self):
        build = self.get("/new/build", {"agent": ["sales"]})
        self.assertIn("Nothing to do here while it practises.", build)
        self.assertNotIn("one note when it is ready", build)  # no such note is sent

    def test_name_taken_refusal_links_to_that_agent(self):
        said = "There is an agent called sales already. Give this one another name in the box."  # quickstart.py
        page = self.p.get("/new", {}, "t", said)
        self.assertIn(f'<p class="flash" role="status">{said} <a href="/agents/sales">Open ', page)
        gone = "There is an agent called stock_watch already. Give this one another name in the box."  # no such page
        page = self.p.get("/new", {}, "t", gone)
        self.assertIn(f'<p class="flash" role="status">{gone}</p>', page)
        other = "Not done: sales <b>x</b>"
        page = self.p.get("/agents", {}, "t", other)
        self.assertIn('<p class="flash" role="status">Not done: sales &lt;b&gt;x&lt;/b&gt;</p>', page)
        self.assertEqual(pages.flash_html(None, {"m": self.m, "q": ""}), "")

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
