"""Risk levels (decisions 84 and 85, arena/levels.py): what each level needs, the suggestion a card
gets, level.json read fail closed and written whole, and Build writing the level the card picker
posted. A fake model only; nothing here calls the network."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from arena import levels
from engine import plug as plug_mod
from kit.db import Db
from reflection import morning as mo
from reflection import pages
from reflection import quickstart as qs
from tests.fake_model import FakeModel
from tests.test_quickstart import card_reply, exam_reply, plug_reply

ROOT = Path(__file__).resolve().parent.parent
THREE = json.loads((Path(__file__).resolve().parent / "three_agents.json").read_text(encoding="utf-8"))


class WhatEachLevelNeeds(unittest.TestCase):
    def test_the_three_rules_and_shapes(self):
        self.assertEqual([levels.needs(lv) for lv in levels.ORDER], [5, 7, 16])
        self.assertEqual(levels.needs(levels.HIGH, 10), 8)
        self.assertEqual(levels.needs(levels.MEDIUM, 20), 14)
        self.assertEqual(levels.needs(levels.LOW, 3), 2)
        self.assertEqual(levels.shape(levels.HIGH), {"rounds": 3, "matches": 10, "gate": 20, "cap": 1500,
                                                     "customers": 30, "no_failed_checks": True})
        for lv in (levels.LOW, levels.MEDIUM):  # other failed checks count at high only (decision 110)
            self.assertEqual(levels.shape(lv), {"rounds": 2, "matches": 10, "gate": 10, "cap": 1000,
                                                "customers": 20, "no_failed_checks": False})

    def test_every_level_says_a_broken_never_line_fails_it(self):
        for lv in levels.ORDER:
            self.assertTrue(levels.WORDS[lv].endswith("a broken never line fails it."))
        self.assertIn("with no failed safety check", levels.WORDS[levels.HIGH])
        self.assertNotIn("safety check", levels.WORDS[levels.MEDIUM] + levels.WORDS[levels.LOW])

    def test_safety_only_is_wins_reached_and_a_never_line_broken(self):
        self.assertTrue(levels.safety_only(levels.MEDIUM, 9, 10, 1))
        self.assertFalse(levels.safety_only(levels.MEDIUM, 6, 10, 1))  # short on wins: lowering can help
        self.assertFalse(levels.safety_only(levels.MEDIUM, 9, 10, 0))
        self.assertFalse(levels.safety_only(levels.MEDIUM, 9, 10, None))
        self.assertFalse(levels.safety_only(levels.HIGH, 9, 10, 1))  # a run of 10 at high: 16 of 20 needed

    def test_an_unknown_level_reads_as_high(self):
        self.assertEqual(levels.needs("extreme"), 16)
        self.assertEqual(levels.shape(None)["gate"], 20)
        self.assertFalse(levels.valid("High"))
        self.assertFalse(levels.valid(["high"]))

    def test_lower_and_raise_stop_at_the_ends(self):
        self.assertEqual(levels.step(levels.MEDIUM, "lower"), levels.LOW)
        self.assertEqual(levels.step(levels.LOW, "lower"), levels.LOW)
        self.assertEqual(levels.step(levels.MEDIUM, "raise"), levels.HIGH)
        self.assertEqual(levels.step(levels.HIGH, "raise"), levels.HIGH)

    def test_the_words_carry_no_dashes(self):
        for line in list(levels.WORDS.values()) + list(levels.NAMES.values()):
            self.assertNotRegex(line, "[\u2013\u2014]")


class TheSuggestion(unittest.TestCase):
    def test_the_three_agents(self):
        got = {name: levels.suggest(a["card"]) for name, a in THREE.items()}
        self.assertEqual(got, {"support_calm_helper": "high", "lead_trial_booker": "high",
                               "coffee_caption_writer": "medium"})
        self.assertIn("support agent", levels.reasons(THREE["support_calm_helper"]["card"]))
        self.assertIn("customer data", levels.reasons(THREE["lead_trial_booker"]["card"]))

    def test_a_meal_plan_with_allergies_reads_high(self):  # decision 110
        card = {"kind": "assistant", "does": "Plans the week's family dinners and makes a grocery list.",
                "good": "A week of dinners that fit the family.", "never": [],
                "needs": [{"what": "family size and food allergies", "tool": "", "ask": True}], "tools": []}
        self.assertEqual(levels.suggest(card), levels.HIGH)
        self.assertEqual(levels.reasons(card), ["diet or health"])
        for words in ("a keto diet plan", "dietary needs", "food restrictions", "gluten free swaps",
                      "medical appointments", "health questions", "reminds patients", "خطة دايت",
                      "عنده حساسية من الفول السوداني", "نظام غذائي"):
            with self.subTest(words=words):
                self.assertEqual(levels.suggest({"does": words}), levels.HIGH)
        for words in ("a vegan family", "peanut free", "count calories", "keto", "book a clinic visit",
                      "pharmacy orders", "ask the doctor", "a patient record", "lactose intolerance",
                      "حساسيتها من القمح", "عيادة أسنان", "صيدلية", "دكتور", "مريض سكر", "كشف طبي", "اكل نباتي",
                      "صحتك أولا", "تأمين طبي"):  # review round 1, item 4: these read medium before
            with self.subTest(words=words):
                self.assertEqual(levels.suggest({"does": words}), levels.HIGH)
        for words in ("healthy snack captions", "be patient with people", "natural light photos طبيعي",
                      "صحة الطلب", "the diet coke order", "diet sodas", "intolerance of rudeness"):
            with self.subTest(words=words):
                self.assertEqual(levels.suggest({"does": words}), levels.MEDIUM)

    def test_never_lines_and_near_words_do_not_count(self):
        card = {"kind": "marketing", "does": "Writes captions that make people feel at home.",
                "good": "People feel the vibe.", "bad": "Captions repay nobody's attention.",
                "never": ["never shares prices", "never asks for a phone number"], "needs": [], "tools": []}
        self.assertEqual(levels.suggest(card), "medium")

    def test_money_data_and_tools_each_make_it_high(self):
        base = {"kind": "ops", "does": "Writes a weekly note.", "good": "", "bad": "", "needs": [], "tools": []}
        for over in ({"does": "Sends the weekly invoice."}, {"bad": "The fee is wrong."},
                     {"case": {"input": "a refund question"}}, {"needs": [{"what": "customer phone numbers"}]},
                     {"tools": ["orders"]}, {"needs": [{"what": "the shop", "tool": "store"}]}, {"kind": "support"}):
            with self.subTest(over=over):
                self.assertEqual(levels.suggest({**base, **over}), "high")
        self.assertEqual(levels.suggest(base), "medium")
        self.assertEqual(levels.suggest("not a card"), "medium")

    def test_pick_takes_a_good_choice_else_the_suggestion(self):
        card = THREE["coffee_caption_writer"]["card"]
        self.assertEqual(levels.pick("low", card), "low")
        self.assertEqual(levels.pick(None, card), "medium")
        self.assertEqual(levels.pick("extreme", THREE["support_calm_helper"]["card"]), "high")


class LevelFile(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()

    def test_missing_reads_medium_and_a_written_level_reads_back(self):
        self.assertEqual(levels.read(self.folder), "medium")
        levels.write(self.folder, "low")
        self.assertEqual(levels.read(self.folder), "low")
        self.assertEqual(json.loads((self.folder / levels.FILE).read_text()), {"level": "low"})
        self.assertEqual([p.name for p in self.folder.iterdir()], [levels.FILE])  # no temp file left

    def test_an_unreadable_file_reads_high(self):
        path = self.folder / levels.FILE
        for text in ("{not json", '{"level": "extreme"}', "[1]", '{"level": 3}', "x" * 5000):
            with self.subTest(text=text[:20]):
                path.write_text(text)
                self.assertEqual(levels.read(self.folder), "high")
        path.unlink()
        other = self.folder / "elsewhere.json"
        other.write_text('{"level": "low"}')
        path.symlink_to(other)
        self.assertEqual(levels.read(self.folder), "high")

    def test_write_refuses_a_link_and_a_bad_level(self):
        other = self.folder / "elsewhere.json"
        other.write_text("keep")
        (self.folder / levels.FILE).symlink_to(other)
        with self.assertRaises(ValueError):
            levels.write(self.folder, "low")
        self.assertEqual(other.read_text(), "keep")
        (self.folder / levels.FILE).unlink()
        with self.assertRaises(ValueError):
            levels.write(self.folder, "extreme")
        self.assertFalse((self.folder / levels.FILE).exists())
        link = self.folder.parent / f"{self.folder.name}-link"
        link.symlink_to(self.folder)
        self.addCleanup(link.unlink)
        with self.assertRaises(ValueError):
            levels.write(link, "low")


class BuildWritesTheLevel(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.db = Db(str(self.folder / "ascent.db"))
        self.addCleanup(self.db.close)
        self.m = mo.Morning(self.db, [plug_mod.load(ROOT / "sales" / "plug.json")], reports=self.folder)
        self.model = FakeModel(card_reply(), plug_reply(), exam_reply())
        self.p = pages.Pages(self.m, model=self.model)
        self.p.actions["/quickstart"](self.m, {"text": ["an agent for my stock"]})

    def build(self, form):
        return self.p.actions["/quickstart/build"](self.m, form)

    def level(self):
        return json.loads((self.folder / "agents" / "stock_watcher" / levels.FILE).read_text(encoding="utf-8"))

    def test_no_choice_writes_the_suggestion(self):
        self.build({})
        self.assertEqual(self.level(), {"level": "high"})  # its store tool holds customer data
        card = json.loads((self.folder / "agents" / "stock_watcher" / "card.json").read_text(encoding="utf-8"))
        self.assertEqual(card["level"], "careful")  # the trial level stays where it was

    def test_the_posted_choice_is_written(self):
        self.build({"level": ["low"]})
        self.assertEqual(self.level(), {"level": "low"})

    def test_a_bad_choice_is_refused_and_nothing_is_built(self):
        calls = len(self.model.calls)
        for form in ({"level": ["extreme"]}, {"level": ["low", "high"]}, {"level": [""]}):
            with self.subTest(form=form):
                with self.assertRaises(mo.Refused):
                    self.build(form)
        self.assertEqual(len(self.model.calls), calls)
        self.assertFalse((self.folder / "agents" / "stock_watcher").exists())

    def test_the_card_shows_the_picker_with_the_suggestion_checked(self):
        page = self.p.get("/new", {}, "t").split("</style>")[1]
        form = page.split('action="/quickstart/build"')[1].split("</form>")[0]
        self.assertEqual(form.count('type="radio" name="level"'), 3)
        self.assertIn('value="high" checked', form)
        self.assertNotIn('value="medium" checked', form)
        self.assertEqual(form.count("Suggested"), 1)
        for lv in levels.ORDER:
            self.assertIn(levels.WORDS[lv], form)
        self.assertNotRegex(page, "[\u2013\u2014]")


if __name__ == "__main__":
    unittest.main()
