"""The free text fields the tag model writes back (arena/tag.py, 2026-10-30): at most 8 words,
cleaned again with the run's cleaner for that chat, so a name the model copies in is masked as
it was in the chat, then cut. Made-up names and a fake model only, never a real call."""
import json
import unittest

from arena import tag as tag_mod
from arena.clean import Cleaner
from tests import fake_recipe

NAMES = ("Zorvex Tamblin",)  # a made-up name on no name list


class Echo:
    """A fake model that writes a chat's name into both free text fields."""
    label = "echo"

    def __init__(self, want, trigger):
        self.want, self.trigger = want, trigger

    def chat(self, messages, **kw):
        worry = sorted(fake_recipe.load().worries)[0]
        return {"role": "assistant", "content": json.dumps(
            {"want": self.want, "worry": worry, "buy_trigger": self.trigger, "patience": 2, "no_budget": False})}


class Fields(unittest.TestCase):
    def test_at_most_eight_words(self):
        words = "one two three four five six seven eight nine ten eleven twelve"
        self.assertEqual(tag_mod._field(words, lambda t: t), "one two three four five six seven eight")
        self.assertEqual(tag_mod._field("a  b\n c", lambda t: t), "a b c")
        self.assertEqual(len(tag_mod._field(" ".join(["w" * 40] * 8), lambda t: t)), tag_mod.MAX_FIELD)

    def test_cleaned_before_the_cut(self):
        cleaner = Cleaner(set(NAMES)).chat(NAMES)
        got = tag_mod._field("x" * 114 + " Zorvex Tamblin", cleaner)
        self.assertNotIn("Zorv", got)
        self.assertLessEqual(len(got), tag_mod.MAX_FIELD)

    def test_a_name_written_back_is_masked_with_the_chats_cleaner(self):
        tagger = tag_mod.Tagger(model=Echo("Zorvex wants size 43 boots", "Tamblin got free shipping"), cap=5,
                                recipe=fake_recipe.load())
        tags = tagger([{"from": "customer", "text": "[name] here"}], "lost", cleaner=Cleaner(set(NAMES)).chat(NAMES))
        self.assertNotIn("Zorvex", tags["want"])
        self.assertNotIn("Tamblin", tags["buy_trigger"])
        self.assertIn("size 43", tags["want"])

    def test_with_no_cleaner_given_the_plain_cleaner_runs(self):
        tagger = tag_mod.Tagger(model=Echo("call me on 01001234567", "x@example.com"), cap=5,
                                recipe=fake_recipe.load())
        tags = tagger([{"from": "customer", "text": "hi"}], "won")
        self.assertNotIn("01001234567", tags["want"])
        self.assertNotIn("example.com", tags["buy_trigger"])


if __name__ == "__main__":
    unittest.main()
