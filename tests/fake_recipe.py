"""A made-up persona recipe for the tests (new, 2026-10-30). The real recipe is private and lives
outside this repo (DECISIONS item 17). This one only drives the scripted model on the made-up
chats from demo/make_arena_history.py: a stand-in prompt and at most 3 words a worry, each seen
in those chats, enough to give every made-up chat the worry the tests expect, and the name
printing held to at most 25% of the Arena's draws (DECISIONS item 33), as the demo cards are."""
import copy
import json
import tempfile
from pathlib import Path

from arena import recipe as recipe_mod

DATA = {
    "prompt": "Test stand-in for the private tag prompt. Name one worry of: {worries}. Answer with JSON: "
              "want, worry, buy_trigger, patience, no_budget.",
    "worries": [
        {"name": "size", "words": ["مقاس", "size", "ma2as"]},
        {"name": "price", "words": ["بكام", "discount", "expensive"]},
        {"name": "cash on delivery", "words": ["استلام", "دفع", "cash"]},
        {"name": "trust", "words": ["اصلي", "اصلية", "copy"]},
        {"name": "delivery time", "words": ["امتى", "how long", "hywsal"]},
        {"name": "just browsing", "words": ["بتفرج", "just looking", "بس بسال"]},
        {"name": "other", "words": []},
    ],
    "unwinnable": ["just browsing"],
    "fallback": "other",
    "capped_wants": [{"name": "name printing", "words": ["طباعة", "print", "printing", "dtf"], "most": 0.25}],
}


def data():
    """A fresh copy of the test recipe, to change in a test."""
    return copy.deepcopy(DATA)


def write(folder, doc=None):
    """The test recipe (or doc) as a file in folder; returns its path."""
    path = Path(folder) / "recipe-test.json"
    path.write_text(json.dumps(DATA if doc is None else doc, ensure_ascii=False), encoding="utf-8")
    return path


def load():
    """The test recipe read by recipe.load from a file in a temp folder, the way a run reads its own."""
    with tempfile.TemporaryDirectory() as tmp:
        return recipe_mod.load(write(tmp))
