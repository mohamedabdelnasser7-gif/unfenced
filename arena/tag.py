"""Tags for the Arena personas (new, 2026-10-30): a Meta model reads one cleaned chat and says
what the customer wanted, what held them back, what made them buy (or would have), how many
dodged answers they took, and whether they had no budget. It asks through kit/model.py only,
on Muse Spark Open on Baseten (DECISIONS item 14: the Arena runs there), the way the parts in
reflection/study.py ask.

The instructions and the worry list come from the persona recipe (arena/recipe.py), not from
this file: the tuned one stays out of the public repo (DECISIONS item 17).

The chat goes in as data in its own message, never in the instructions, and only after
arena/clean.py has cleaned it. Every answer is read strictly (reflection/study.py read_json): a
worry outside the recipe's worries, a patience that is not a whole number from 0 to MAX_PATIENCE, a
no_budget that is not true or false, or a missing want or buy trigger gives no tag, and the
chat is skipped, never guessed. The free text that comes back is cut to MAX_WORDS words,
cleaned again with the run's cleaner for that chat (its names known) and cut to MAX_FIELD
characters.

Every call counts against a hard cap, MAX_CALLS a run unless a lower cap is given, a failed
call too. After MAX_FAILS failed calls in a row the run stops asking. Style (message length,
language mix, voice notes, how they open) is counted in code (arena/cards.py), not asked.
"""
import json

from kit import model as model_mod
from reflection.study import read_json
from arena import recipe as recipe_mod
from arena.clean import Cleaner

MAX_CALLS = 1000
MAX_FAILS = 3
MAX_FIELD = 120
MAX_WORDS = 8             # words kept of one free text field (want, buy trigger)
MAX_LINE = 400            # characters of one turn sent
MAX_CHAT = 8000           # characters of one chat sent: its start and its end when longer
MAX_PATIENCE = 20
# Reasoning tokens count against max_tokens, and a cut off answer is a failed call: at medium
# effort and 1500 tokens half the answers of a real build came back cut off and the run stopped
# after MAX_FAILS in a row. Low effort with 4000 tokens leaves room for the answer.
EFFORT = "low"
MAX_TOKENS = 4000
TIMEOUT = 90


class CapReached(Exception):
    """The run's call cap is used up."""


def turns_for_model(turns):
    """The turns as the model gets them: from, text cut to MAX_LINE, media; the chat's start and
    end only when it is longer than MAX_CHAT characters."""
    out = []
    for t in turns:
        item = {"from": t["from"]}
        if t.get("text"):
            item["text"] = t["text"][:MAX_LINE]
        if t.get("media"):
            item["media"] = t["media"]
        out.append(item)
    sizes = [len(i.get("text", "")) + 20 for i in out]
    if sum(sizes) <= MAX_CHAT:
        return out
    head, tail, used = [], [], 0
    for item, size in zip(out, sizes):
        if used + size > MAX_CHAT // 2:
            break
        head.append(item)
        used += size
    used = 0
    for item, size in zip(reversed(out[len(head):]), reversed(sizes[len(head):])):
        if used + size > MAX_CHAT // 2:
            break
        tail.append(item)
        used += size
    return head + [{"from": "note", "text": "some turns left out"}] + tail[::-1]


def read_tags(text, cleaner, worries):
    """The tags from the model's text, or None for anything that is not exactly right. worries:
    the recipe's worry names."""
    got = read_json(text)
    if not isinstance(got, dict):
        return None
    worry = got.get("worry")
    worry = worry.strip().casefold() if isinstance(worry, str) else None
    patience, no_budget = got.get("patience"), got.get("no_budget")
    if worry not in worries or isinstance(patience, bool) or not isinstance(patience, int) \
            or not 0 <= patience <= MAX_PATIENCE or not isinstance(no_budget, bool):
        return None
    want, trigger = _field(got.get("want"), cleaner), _field(got.get("buy_trigger"), cleaner)
    if want is None or trigger is None:
        return None
    return {"want": want, "worry": worry, "buy_trigger": trigger, "patience": patience, "no_budget": no_budget}


def _field(value, cleaner):
    """A free text field: at most MAX_WORDS words, cleaned, then cut to MAX_FIELD characters."""
    if not isinstance(value, str) or not value.strip():
        return None
    return cleaner(" ".join(value.split()[:MAX_WORDS]))[:MAX_FIELD]


class Tagger:
    """tagger(turns, ended, cleaner=None): the tags of one cleaned chat, or None (a failed call
    or an answer that is not exactly right). cleaner: the run's cleaner for this chat
    (arena/clean.py Cleaner.chat with the chat's names), so a name the model writes back into
    a free text field is masked as it was in the chat. Raises CapReached once the cap is used
    up or the run stopped."""

    def __init__(self, model=None, cap=MAX_CALLS, timeout=TIMEOUT, recipe=None):
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= MAX_CALLS:
            raise ValueError(f"the call cap is 1 to {MAX_CALLS}")
        self.recipe = recipe if recipe is not None else recipe_mod.load()
        self._model = model
        self.cap, self.timeout = cap, timeout
        self.calls = self.failed = self.refused = self.in_a_row = 0
        self.stopped = None     # why the run stopped asking, in plain words
        self.last_error = None  # kit/model.py's message: the host's status or a missing key, never text
        self._after = Cleaner().chat()

    @property
    def model(self):
        if self._model is None:
            self._model = model_mod.Model(timeout=self.timeout, route=model_mod.OPEN)
        return self._model

    @property
    def label(self):
        try:
            return getattr(self.model, "label", None) or f"{self.model.route.name} {self.model.model_id}"
        except model_mod.ModelError as e:
            return f"no model: {e}"

    def can_ask(self):
        return self.stopped is None and self.calls < self.cap

    def __call__(self, turns, ended, cleaner=None):
        if not self.can_ask():
            raise CapReached(self.stopped or "the call cap is used up")
        self.calls += 1
        data = {"ended": ended, "turns": turns_for_model(turns)}
        failed = None  # each raise sits outside its except block, so no error keeps the request
        try:
            out = self.model.chat([{"role": "system", "content": self.recipe.prompt},
                                   {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
                                  effort=EFFORT, max_tokens=MAX_TOKENS, whole=True)
        except model_mod.ModelError as e:  # its message never holds the key or the chat
            failed = str(e)
        except Exception as e:  # any other error or a timeout, named by its type only
            failed = f"the model call failed: {type(e).__name__}"
        if failed is not None:
            self.failed += 1
            self.in_a_row += 1
            self.last_error = failed
            if self.in_a_row >= MAX_FAILS:
                self.stopped = f"{MAX_FAILS} failed calls in a row"
            return None
        self.in_a_row = 0
        content = out.get("content") if isinstance(out, dict) and not out.get("tool_calls") else None
        tags = read_tags(content, cleaner if cleaner is not None else self._after, self.recipe.worries)
        self.refused += tags is None
        return tags
