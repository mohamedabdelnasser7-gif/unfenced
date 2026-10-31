"""Checks in the Arena tagger, cards and recipe (2026-10-30) that no other test caught when they
were switched off (mutation run, round 4): the failed-call count resets on an answer, a worry
or patience out of range gives no tag, a tool call is no answer, no unwinnable chat gives no
unwinnable weight, and a recipe file that is a link, too big or lists an unknown worry is
refused."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from kit import model as model_mod
from arena import cards as cards_mod
from arena import clean as cl
from arena import recipe as recipe_mod
from arena import tag as tag_mod
from tests import fake_recipe

TURNS = [{"from": "customer", "text": "بكام"}, {"from": "store", "text": "1450 جنيه"}]


def answer(recipe, **change):
    got = {"want": "boots", "worry": recipe.worries[0], "buy_trigger": "the price", "patience": 2, "no_budget": False}
    got.update(change)
    return json.dumps(got)


class Script:
    """Answers in order: an Exception raises it, a dict is returned as the reply."""
    label = "script"

    def __init__(self, steps):
        self.steps = list(steps)

    def chat(self, messages, **kw):
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class Tagger(unittest.TestCase):
    def setUp(self):
        self.recipe = fake_recipe.load()
        self.good = {"role": "assistant", "content": answer(self.recipe)}

    def test_an_answer_resets_the_failed_calls_in_a_row(self):
        fail = model_mod.ModelError("Baseten answered 500 Internal Server Error")
        tagger = tag_mod.Tagger(model=Script([fail, fail, self.good, fail, fail]), recipe=self.recipe)
        got = [tagger(TURNS, "lost") for _ in range(5)]
        self.assertIsNotNone(got[2])
        self.assertIsNone(tagger.stopped)
        self.assertTrue(tagger.can_ask())
        self.assertEqual((tagger.calls, tagger.failed, tagger.in_a_row), (5, 4, 2))

    def test_a_tool_call_is_no_answer(self):
        reply = {**self.good, "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}
        tagger = tag_mod.Tagger(model=Script([reply]), recipe=self.recipe)
        self.assertIsNone(tagger(TURNS, "lost"))
        self.assertEqual((tagger.refused, tagger.failed), (1, 0))

    def test_a_worry_or_patience_out_of_range_gives_no_tag(self):
        c, worries = cl.Cleaner().chat(), self.recipe.worries
        self.assertIsNotNone(tag_mod.read_tags(answer(self.recipe), c, worries))
        self.assertIsNotNone(tag_mod.read_tags(answer(self.recipe, patience=tag_mod.MAX_PATIENCE), c, worries))
        self.assertIsNotNone(tag_mod.read_tags(answer(self.recipe, patience=0), c, worries))
        for change in ({"worry": "weather"}, {"worry": ""}, {"patience": tag_mod.MAX_PATIENCE + 1}, {"patience": -1}):
            with self.subTest(change=change):
                self.assertIsNone(tag_mod.read_tags(answer(self.recipe, **change), c, worries))


class Weights(unittest.TestCase):
    def test_no_unwinnable_chat_gives_no_unwinnable_weight(self):
        recipe = fake_recipe.load()
        worry = next(w for w in recipe.worries if w not in recipe.unwinnable)
        style = {"length": "short", "language": {k: 0.0 for k in cards_mod.LANGUAGES}, "voice_notes": 0.0,
                 "opening": "price"}
        items = [{"label": "won", "style": style, "turns": TURNS,
                  "tags": {"want": "boots", "worry": worry, "buy_trigger": "the price", "patience": 1,
                           "no_budget": False}} for _ in range(2)]
        cards, info = cards_mod.build(items, recipe)
        self.assertEqual(info["unwinnable_chats"], 0)
        self.assertEqual(info["unwinnable_share_used"], 0.0)
        self.assertEqual([c["arena_weight"] for c in cards], [1.0])


class RecipeFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.data = fake_recipe.data()

    def test_a_link_is_refused(self):
        link = os.path.join(self.tmp, "recipe.json")
        os.symlink(fake_recipe.write(self.tmp), link)
        with self.assertRaises(recipe_mod.hist.Refused) as e:
            recipe_mod.load(link)
        self.assertIn("a link", str(e.exception))

    def test_a_file_over_the_cap_is_refused_by_its_size(self):
        big = os.path.join(self.tmp, "recipe.json")
        with open(big, "w", encoding="utf-8") as f:
            f.write(json.dumps({**self.data, "pad": "x" * recipe_mod.MAX_BYTES}))
        with self.assertRaises(recipe_mod.hist.Refused) as e:
            recipe_mod.load(big)
        self.assertEqual(str(e.exception), f"the recipe: not a plain file of at most {recipe_mod.MAX_BYTES // 1024} KB")

    def test_a_recipe_inside_the_repo_is_refused_but_the_example(self):
        """Review round 1, finding 5: a private recipe at the old demo path (or anywhere in the repo,
        any case) is refused before it is read; only the example loads from inside the repo."""
        root = Path(recipe_mod.__file__).resolve().parent.parent
        old = root / "demo" / "personas" / "recipe.json"
        self.assertFalse(old.exists())
        fake_recipe.write(self.tmp)
        old.write_bytes((Path(self.tmp) / "recipe-test.json").read_bytes())
        self.addCleanup(old.unlink)
        for given in (old, Path(str(old).swapcase()), root / "arena" / "no-such-recipe.json"):
            with self.assertRaises(recipe_mod.hist.Refused) as e:
                recipe_mod.load(given)
            self.assertIn("the recipe: the file sits inside the repo", str(e.exception))
        self.assertTrue(recipe_mod.load(recipe_mod.EXAMPLE).example)
        self.assertTrue(recipe_mod.load(Path(str(recipe_mod.EXAMPLE).swapcase())).example)  # a Mac ignores case
        self.assertFalse(recipe_mod.load(Path(self.tmp) / "recipe-test.json").example)

    def test_unwinnable_lists_worry_names_only(self):
        self.assertTrue(recipe_mod.Recipe({**self.data}).worries)
        with self.assertRaises(recipe_mod.hist.Refused) as e:
            recipe_mod.Recipe({**self.data, "unwinnable": [self.data["worries"][0]["name"], "nothing"]})
        self.assertIn("unwinnable lists worry names only", str(e.exception))


if __name__ == "__main__":
    unittest.main()
