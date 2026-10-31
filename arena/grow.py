"""Practice customers grown from an agent's real chats (new, 2026-10-31; DECISIONS items 30, 32, 33,
47, 48, 51).

Both sides grow, the way the assistant's Arena grows from real days (assistant/arena.py). Each
night Reflection reads the Sales agent's new real chats (kit/chats.py, the agent's database) and
sends the Arena new practice cases beside its lessons (item 47):
  lost     quiet after the price (arena/label.py): kept.
  hard     won, but only after at least HARD_TURNS customer messages, a person stepping in or a
           failed send check: kept.
  easy     any other win: skipped, there is nothing in it to practise.
  unclear  skipped, never guessed (arena/label.py).
A customer keeps one chat per channel for good (kit/chats.py), so the pool keeps each chat's
progress by the last step it read, not by the chat: a later talk in the same chat is read from
the step after it. Only a settled talk moves the progress on: won, lost, or quiet with no price
given. Any other unclear talk (still open, a last message not answered yet, a voice note, a won
sign then a cancel) is left unmarked and read again, with whatever came after it, once the chat
has a new message. A talk still waiting (open, not answered, a voice note) and a settled one left
over (MAX_NEW, the tagger's cap, the Arena's call cap, a tagger answer that did not fit) are kept
as pending in the pool and read first the next night, whatever its window, up to MAX_TRIES
nights each and MAX_PENDING in all. The other chats read are the ones with a message since the
night's window opened, looking back label.QUIET_HOURS more, so a chat that went quiet just
before the window still counts. Imported history chats (channel history:...) and branches of a
chat (parent_id) are never read. A talk joins the pool once: the item keeps the chat and the
step it ended on, and the same talk is never added twice. When the progress list passes
MAX_READ chats the oldest are dropped and the pool keeps the time of the newest one dropped, so a
chat it no longer lists is read only after that time, never from its first step again. A pool
written before the progress list (df37745) lists the chats it read as seen; each is read only
after the time that file was written.

Each kept chat is cleaned (arena/clean.py: names, numbers and places out) before the tagger
(arena/tag.py) sees it and before anything is written; no second scan (item 40). The cleaner
knows what the customers gave for their orders: every name and name to print in the night's
draft_order calls is masked in any chat of the night, and in its own chat each word of it, the
address and the chat's number too, so a name typed bare with no cue word still goes. A chat with
no order keeps the words its cues showed as a name (arena/clean.py ChatCleaner.texts) and masks
them in all its turns, with a name-shaped word beside any [name]. Its tags and
cleaned turns join the pool, and the pool's cards are rebuilt through the card code
(arena/cards.py build), so the unwinnable share and the capped wants (item 33: name printing at
most 25%) hold for the grown cards as for the first ones. A grown card's id names its group
(grown-<worry>, grown-<worry>-no-budget), so it keeps its losses when the pool is rebuilt.

A practice customer that beats the agent comes back more often: the pool counts the losses in
training matches (arena/run.py) by the card's group (its worry and why it will not buy, the way
grown_id names grown cards), not by its id, and in training a card is drawn 1 + LOST_WEIGHT times
as often per loss, at most MAX_COUNTED_LOSSES counted, so one card never crowds out the rest
(decks). Grown cards train only and never take the gate; the gate's cards are
split off the base cards first and the split is saved in the pool (arena/run.py fixed_split).
The weights per loss, each side's share and the capped wants apply to the training draws after
that split; the gate draws at the weights before any loss, with the capped wants held on its own
draws. So on the training draws and on the gate draws each, printing stays at most 25% and the
unwinnable share holds.

Pools are per owner (item 51). The pool is practice-<kind>.json in the owner's state folder (in
data/, which git ignores, or outside the repo). An agent's own folder is the folder of its
database. Folders alone never say who the owner is: the owner's folder is the one above the
agent's only when that folder holds owner.json naming an owner ({"owner": name}) and the agent's
plug (<folder>/plug.json) names the same owner (engine/plug.py owner). Then several agents of one
owner each keep their own database and Arena files and share one owner folder. With no marker,
or a plug naming no owner or another, the agent's own folder is its owner's and its pool is its
own (the night says "this agent only"), so two owners' agents laid side by side under one folder
never share. A sibling is a plug of the same kind (engine/plug.py kind) naming the same owner in
a folder under the owner's: siblings share the pool, so a new agent of a kind the owner already
runs starts with zero lessons (item 20) and faces the practice customers its siblings' real work
grew. A pool path outside the owner's folder is refused, a link included, so nothing crosses to
another owner, even cleaned. A pool file naming another kind is refused, and so are values that
are not exactly the shape this file writes; the pool is written under a fresh name and moved into
place (arena/personas.py _write), never through a link, readable by its user only.

The tagger's calls count against the Arena's daily cap in the agent's own folder (arena/run.py
Calls), at most MAX_NEW chats a night. The step needs the persona recipe (arena/recipe.py,
private): with none it reads no chat and says so.
"""
import dataclasses
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from engine import plug as plug_mod
from reflection import history as hist
from arena import cards as cards_mod
from arena import label as label_mod
from arena import paths
from arena.clean import Cleaner

LOST_WEIGHT = 3
MAX_COUNTED_LOSSES = 5  # losses counted per card group at most (Mohamed 2026-10-31: the recommended 5)
HARD_TURNS = 6
MAX_NEW = 50
MAX_ITEMS = 500
MAX_READ = 20_000   # chats whose progress the pool keeps
MAX_PENDING = 2000  # chats read first the next night
MAX_TRIES = 7       # nights a pending chat is read before it is let go
MAX_PATTERN = 20_000  # a recipe's capped want of up to 200 words (arena/recipe.py) builds a long one
MAX_UNBOUNDED = 3  # a stored pattern with more *, + or {n,} is refused: a*a*a*...b backtracks for ever
MAX_NUMBER = 2 ** 53  # a number read from the pool file is at most this, so float() and math never overflow
DEFAULT_KIND = "sales"
KIND = plug_mod.AGENT_NAME  # one rule for a plug's kind and the pool's: a kind the plug takes, the pool takes
POOL_FILE = "practice-{kind}.json"
OWNER_FILE = "owner.json"
PERSON = "person"  # kit/chats.py PERSON: a team member's own reply


class Refused(ValueError):
    pass


# ---- owners, kinds and siblings

def kind_of(plug):
    """The plug's kind: its own when it names one, else its agent's name."""
    return getattr(plug, "kind", "") or plug.agent


def owner_name(folder):
    """The owner folder holds owner.json ({"owner": a name}); the name, or None when it holds none,
    a link, or a file that is not exactly that."""
    path = Path(folder) / OWNER_FILE
    if path.is_symlink() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("owner") if isinstance(data, dict) else None
    return name if isinstance(name, str) and KIND.fullmatch(name) else None


def _plug_at(folder):
    path = Path(folder) / "plug.json"
    try:
        return plug_mod.load(path) if path.is_file() else None
    except (OSError, ValueError):
        return None


def owner_of(folder):
    """The owner's state folder for an agent's folder (see the module lines): the folder above it
    when that folder's owner.json names the owner the agent's plug names, else its own folder."""
    folder = Path(folder).expanduser().resolve()
    plug = _plug_at(folder)
    marker = owner_name(folder.parent)
    return folder.parent if plug is not None and marker is not None and plug.owner == marker else folder


def kind_at(folder, default=DEFAULT_KIND):
    """The kind of the agent whose plug sits in folder, or default when none does."""
    path = Path(folder).expanduser().resolve() / "plug.json"
    return kind_of(plug_mod.load(path)) if path.is_file() else default


def siblings(owner, kind):
    """The agents of this kind that share the owner's folder, sorted: a plug in a folder under it
    (<folder>/plug.json) naming the owner its owner.json names. None when it names no owner (an
    agent's own folder)."""
    owner = Path(owner).expanduser().resolve()
    marker = owner_name(owner)
    if marker is None:
        return []
    out = []
    for path in sorted(owner.glob("*/plug.json")):
        plug = _plug_at(path.parent)
        if plug is not None and plug.owner == marker and kind_of(plug) == kind:
            out.append(plug.agent)
    return out


def check_owner(owner):
    owner = Path(owner).expanduser().resolve()
    if paths.inside_repo(owner) and not paths.within(owner, paths.DATA):
        raise Refused("the owner's state folder sits inside the repo outside data/")
    return owner


# ---- the pool

class Pool:
    """The practice customers one owner's real chats grew for one kind of agent, and how often each
    card beat the agent. path: for a test or a tool naming the file; refused outside the owner's folder."""

    def __init__(self, owner, kind, path=None):
        if not isinstance(kind, str) or not KIND.fullmatch(kind):
            raise Refused("a kind is lowercase letters, digits and _, starting with a letter")
        self.owner, self.kind = check_owner(owner), kind
        given = self.owner / POOL_FILE.format(kind=kind) if path is None else Path(path).expanduser()
        if not given.is_absolute():
            given = Path.cwd() / given
        if given.is_symlink():
            raise Refused("the pool file is a link")
        self.path = given.resolve()
        if self.path == self.owner or not paths.within(self.path, self.owner):
            raise Refused("the pool sits outside the owner's state folder; pools never cross owners")
        try:
            data, written = json.loads(self.path.read_text(encoding="utf-8")), self.path.stat().st_mtime
        except (OSError, ValueError):
            data, written = {}, None
        data = data if isinstance(data, dict) else {}
        if data.get("kind", kind) != kind:
            raise Refused("the pool file is for another kind of agent")
        self.items = [i for i in (data.get("items") or []) if _item_ok(i)][-MAX_ITEMS:]
        read = data.get("read") if isinstance(data.get("read"), dict) else {}
        self.read = {k: [v[0], float(v[1])] for k, v in read.items()
                     if isinstance(v, list) and len(v) == 2 and _count(v[0]) and _time(v[1])}
        # a pool from before the read list (df37745) names the chats it read in seen: each is read
        # only after the time the file was written (step 0: its step is not known), never again whole
        seen = data.get("seen") if isinstance(data.get("seen"), list) and _time(written) else []
        seen = [s for s in dict.fromkeys(s for s in seen if isinstance(s, str)) if s not in self.read]
        room = max(0, MAX_READ - len(self.read))
        self.read = {**{s: [0, float(written)] for s in seen[len(seen) - room:]}, **self.read}
        pending = data.get("pending") if isinstance(data.get("pending"), dict) else {}
        self.pending = {k: v for k, v in pending.items() if _count(v)}
        self.floor = float(data["floor"]) if _time(data.get("floor")) else None
        played = data.get("played") if isinstance(data.get("played"), dict) else {}
        self.played = {k: {"played": v["played"], "lost": v["lost"]} for k, v in played.items()
                       if isinstance(k, str) and GROUP.fullmatch(k) and isinstance(v, dict)
                       and _count(v.get("played")) and _count(v.get("lost"))}
        self.cards = [c for c in (data.get("cards") or []) if _card_ok(c)]
        capped = data.get("capped")  # None until the pool is first built from a recipe
        # one entry out of shape and the example recipe's caps hold instead (item 33), never none
        capped = [_capped_read(c) for c in capped] if isinstance(capped, list) else [None]
        self.capped = capped if all(c is not None for c in capped) else None
        self.split = data["split"] if _split_ok(data.get("split")) else None  # the gate's held ids (arena/run.py)
        self._keys = {i["read"] for i in self.items if "read" in i}
        self.changed = False

    def weight(self, card):
        """1 + LOST_WEIGHT per loss of the card's group in training, at most MAX_COUNTED_LOSSES counted."""
        return 1 + LOST_WEIGHT * min(int(self.played.get(group(card), {}).get("lost", 0)), MAX_COUNTED_LOSSES)

    def plays(self, card):
        """The training matches the card's group has played."""
        return int(self.played.get(group(card), {}).get("played", 0))

    def trained(self, card):
        """True when the card's group has played a training match: a new split holds it only to top
        up, and --held-out never names it (arena/run.py fixed_split)."""
        return self.plays(card) > 0

    def record(self, card, won):
        """A training match's result, counted for the card's group (group)."""
        row = self.played.setdefault(group(card), {"played": 0, "lost": 0})
        row["played"] += 1
        row["lost"] += 0 if won else 1
        self.changed = True

    def progress(self, chat_id):
        """(the last step read, its time) for a chat, or None when the pool lists no step of it. Step 0:
        a chat an old pool read (seen), read only after that time."""
        got = self.read.get(str(chat_id))
        return None if got is None else tuple(got)

    def mark(self, chat_id, step, at):
        """A settled talk: the chat is read up to step (at its time), and is no longer pending."""
        self.read.pop(str(chat_id), None)  # moved to the end: the newest read stays longest
        self.read[str(chat_id)] = [int(step), float(at)]
        self.pending.pop(str(chat_id), None)
        if len(self.read) > MAX_READ:
            dropped = list(self.read)[:len(self.read) - MAX_READ]
            self.floor = max([self.floor or 0.0] + [self.read[k][1] for k in dropped])
            for k in dropped:
                del self.read[k]
        self.changed = True

    def pend(self, chat_id, tried=True):
        """Read it first the next night. tried: this night read it and could not settle or add it,
        which counts towards MAX_TRIES; a talk only left over by a cap does not count."""
        k = str(chat_id)
        tries = self.pending.pop(k, 0) + bool(tried)
        if tries >= MAX_TRIES:
            self.changed = True
            return False
        self.pending[k] = tries
        while len(self.pending) > MAX_PENDING:
            del self.pending[next(iter(self.pending))]
        self.changed = True
        return True

    def unpend(self, chat_id):
        if self.pending.pop(str(chat_id), None) is not None:
            self.changed = True

    def add(self, item, chat_id, step, at):
        """A cleaned, tagged real talk joins the pool ({label, tags, style, turns}, as arena/cards.py
        takes), once: the same chat up to the same step never joins twice. True when it joined."""
        if not _item_ok(item):
            raise ValueError("a practice item has a label, tags, a style and turns")
        key = f"{chat_id}:{int(step)}"
        if key not in self._keys:
            self.items = (self.items + [{**item, "read": key}])[-MAX_ITEMS:]
            self._keys = {i["read"] for i in self.items if "read" in i} | {key}
        self.mark(chat_id, step, at)
        return True

    def rebuild(self, recipe):
        """The pool's cards from its items, through the card code; ids name each card's group."""
        built, _ = cards_mod.build([{**i, "grown": True} for i in self.items], recipe) if self.items else ([], None)
        for c in built:
            c["id"] = grown_id(c)
        self.cards = built
        words = getattr(recipe, "capped_words", {})  # the recipe's words: the file keeps these, not the pattern
        self.capped = [{"name": name, "words": list(words[name]), "pattern": rx.pattern, "most": most}
                       if name in words else {"name": name, "pattern": rx.pattern, "most": most}
                       for name, rx, most in getattr(recipe, "capped", ())]
        self.changed = True

    def save(self):
        """Written under a fresh name (0600, never through a link) and moved onto the pool file, the
        way the persona build writes (arena/personas.py _write); the owner folder is made or set 0700."""
        from arena.personas import _write
        os.makedirs(self.path.parent, mode=0o700, exist_ok=True)
        if not self.path.parent.is_symlink():
            os.chmod(self.path.parent, 0o700)  # an owner folder made earlier with a wider mode too
        _write(self.path, json.dumps({"kind": self.kind, "items": self.items, "read": self.read,
                                      "pending": self.pending, "floor": self.floor, "played": self.played,
                                      "cards": self.cards, "capped": _capped_file(self.capped), "split": self.split},
                                     ensure_ascii=False).encode("utf-8"))
        self.changed = False

    def summary(self):
        return {"kind": self.kind, "grown_cards": len(self.cards), "items": len(self.items),
                "siblings": siblings(self.owner, self.kind)}


def _count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


MAX_SPLIT = 1000  # base cards a saved split may name


def _split_ok(v):
    """{cards: the base card ids, sorted, seed, held: the ids held out of them}."""
    if not isinstance(v, dict) or not isinstance(v.get("seed"), int) or isinstance(v["seed"], bool):
        return False
    ids, held = v.get("cards"), v.get("held")
    return (isinstance(ids, list) and isinstance(held, list) and len(ids) <= MAX_SPLIT
            and all(isinstance(i, str) for i in ids) and ids == sorted(set(ids)) and set(held) <= set(ids)
            and all(isinstance(i, str) for i in held) and bool(held))


def _time(v):
    """An int or a float, not a bool, within MAX_NUMBER either way (NaN and inf fall outside)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and -MAX_NUMBER <= v <= MAX_NUMBER


def _item_ok(i):
    """{label, tags, style, turns} in the shapes arena/tag.py, cards.style_of and personas.turns_of
    give, so the card code (arena/cards.py build) never meets a value it cannot read."""
    return (isinstance(i, dict) and i.get("label") in (label_mod.WON, label_mod.LOST)
            and _tags_ok(i.get("tags")) and _style_ok(i.get("style")) and isinstance(i.get("turns"), list)
            and all(isinstance(t, dict) and isinstance(t.get("from"), str)
                    and isinstance(t.get("text", ""), str) for t in i["turns"]))


def _tags_ok(t):
    return (isinstance(t, dict) and all(isinstance(t.get(k), str) for k in ("worry", "want", "buy_trigger"))
            and _count(t.get("patience")) and isinstance(t.get("no_budget"), bool))


def _style_ok(s):
    return (isinstance(s, dict) and isinstance(s.get("length"), str) and isinstance(s.get("opening"), str)
            and _time(s.get("voice_notes")) and isinstance(s.get("language"), dict)
            and all(_time(s["language"].get(k)) for k in cards_mod.LANGUAGES))


def _card_ok(c):
    return (isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"].startswith("grown-")
            and _time(c.get("arena_weight")) and c["arena_weight"] >= 0
            and isinstance(c.get("chats"), int) and not isinstance(c["chats"], bool) and 1 <= c["chats"] <= MAX_NUMBER
            and isinstance(c.get("want"), list) and all(isinstance(w, str) for w in c["want"]))


def _capped_read(c):
    """One capped want from the pool file as {name, words, pattern, most}, or None when out of
    shape. Its words are checked as a recipe's are and the pattern is built again from them
    (arena/recipe.py _words), so no pattern is taken from the file. An older file holds only the
    pattern: kept when _capped_ok passes it."""
    if not isinstance(c, dict) or "words" not in c:
        return {k: c[k] for k in ("name", "pattern", "most")} if _capped_ok(c) else None
    from arena import recipe as recipe_mod
    words, most = c.get("words"), c.get("most")
    if not (isinstance(c.get("name"), str) and isinstance(most, (int, float)) and not isinstance(most, bool)
            and 0 < most < 1 and isinstance(words, list) and 0 < len(words) <= recipe_mod.MAX_WORDS
            and all(isinstance(w, str) and 0 < len(w) <= recipe_mod.MAX_WORD and w.isprintable() for w in words)):
        return None
    rx = recipe_mod._words(words)
    return {"name": c["name"], "words": list(words), "pattern": rx.pattern, "most": most} if rx else None


def _capped_file(capped):
    """The capped wants as the pool file keeps them: the words when known, never both."""
    if capped is None:
        return None
    return [{k: v for k, v in c.items() if k != "pattern"} if "words" in c else c for c in capped]


def _capped_ok(c):
    """An older pool file's capped want, {name, pattern, most}: no group repeated around a
    quantifier and at most MAX_UNBOUNDED unbounded quantifiers, so matching a want never hangs."""
    if not (isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("pattern"), str)
            and len(c["pattern"]) <= MAX_PATTERN and isinstance(c.get("most"), (int, float))
            and not isinstance(c["most"], bool) and 0 < c["most"] < 1) or _repeats_a_repeat(c["pattern"]) \
            or _unbounded(c["pattern"]) > MAX_UNBOUNDED:
        return False
    try:
        re.compile(c["pattern"], re.IGNORECASE)
    except (re.error, RecursionError, OverflowError):
        return False
    return True


def _repeats_a_repeat(pattern):
    """True when a group holding a quantifier or a | is itself repeated (*, + or {n,m} right after
    it): (\\w+\\s?)* or (a|a)*, the shapes that backtrack for ever on a want that almost matches.
    A recipe's capped words never build one (arena/recipe.py _words: a group is at most optional)."""
    stack, risky, i = [], False, 0  # stack: per open group, whether it holds a quantifier or a |
    while i < len(pattern):
        ch, closed = pattern[i], False
        if ch == "\\":
            i += 2
            risky = False
            continue
        if ch == "[":  # a class, skipped to its closing ]
            i += 1
            i += pattern.startswith("^", i)
            i += pattern.startswith("]", i)
            while i < len(pattern) and pattern[i] != "]":
                i += 2 if pattern[i] == "\\" else 1
            i += 1
            risky = False
            continue
        if ch in "*+{" and risky:
            return True
        if ch == "(":
            stack.append(False)
            i += pattern.startswith("?", i + 1)  # (?:, (?<! and the like: that ? is no quantifier
        elif ch == ")" and stack:
            closed = stack.pop()
            if stack and closed:
                stack[-1] = True
        elif ch in "*+?{|" and stack:
            stack[-1] = True
        risky = closed
        i += 1
    return False


OPEN_RANGE = re.compile(r"\{\d*,\}")  # {n,} and {,}: no top


def _unbounded(pattern):
    """How many *, + and {n,} the pattern holds outside a class and not escaped (a+? counts once)."""
    count, i = 0, 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":  # a class, skipped to its closing ]
            i += 1
            i += pattern.startswith("^", i)
            i += pattern.startswith("]", i)
            while i < len(pattern) and pattern[i] != "]":
                i += 2 if pattern[i] == "\\" else 1
            i += 1
            continue
        if ch in "*+" or ch == "{" and OPEN_RANGE.match(pattern, i):
            count += 1
        i += 1
    return count


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "other").casefold()).strip("-") or "other"


def grown_id(card):
    """grown-<worry>, with -no-budget for a card unwinnable for no budget: the same group, the same id."""
    return f"grown-{_slug(card.get('worry'))}" + ("-no-budget" if card.get("why_unwinnable") == "no budget" else "")


GROUP = re.compile(r"(?:base|grown):[a-z0-9-]{1,80}(?::[a-z0-9-]{1,80})?")


def group(card):
    """The card's group, the key its training results are counted under: base or grown, its worry
    and why it will not buy (base:price, grown:price:no-budget). A persona build numbers its cards
    again each time, so a card id (persona-NN) can name another group tomorrow; the group stays."""
    side = "grown" if str(card.get("id", "")).startswith("grown-") else "base"
    why = card.get("why_unwinnable")
    return f"{side}:{_slug(card.get('worry'))[:80]}" + (f":{_slug(why)[:80]}" if why else "")


def for_state(state, default_kind=DEFAULT_KIND):
    """The pool of the agent whose Arena files sit in state: its owner's, of its kind."""
    return Pool(owner_of(state), kind_at(state, default_kind))


# ---- the deck the Arena draws from

class _Caps:
    def __init__(self, capped):
        self.capped = tuple((c["name"], re.compile(c["pattern"], re.IGNORECASE), float(c["most"])) for c in capped)


def example_caps():
    """The example recipe's capped wants (item 33), for a pool that was never grown."""
    from arena import recipe as recipe_mod
    return [{"name": n, "pattern": rx.pattern, "most": m} for n, rx, m in recipe_mod.load(recipe_mod.EXAMPLE).capped]


def buys(card):
    return not card.get("unwinnable")


def decks(base, pool, held):
    """(training cards, gate cards) the Arena draws from, from the base cards, the pool's grown
    cards and held, the ids of the base cards held out for the gate (arena/run.py fixed_split).
    Every card starts at its weight with each part (base, grown) by its chats, and the unwinnable
    share is read off that whole deck. Grown cards train only, never the gate. Training cards:
    each weight times its losses (Pool.weight), then each side brought back to its share of the
    training draws and the capped wants held on them (arena/cards.py cap_wants). Gate cards: the
    held cards that can buy, at their weights before any loss, the capped wants held on the gate
    draws on their own. The caps are the owner's recipe's, saved in the pool when it was built, or
    the example recipe's (item 33) for a pool never built. Base cards built with the pool already
    in them (a "grown" count on each, arena/personas.py --state) take no grown card again. The
    base cards are never changed in place."""
    folded = any("grown" in c for c in base)
    grown = [] if folded else [dict(c) for c in pool.cards]
    out = [dict(c) for c in base] + grown
    for c in out:
        c.setdefault("unwinnable", False)
        c.setdefault("want", [])
    parts = ((out[:len(base)], sum(int(c.get("chats") or 1) for c in base)),
             (grown, sum(int(c.get("chats") or 1) for c in grown)))
    total = sum(n for _, n in parts) or 1
    for cards, n in parts:
        mass = sum(max(0.0, float(c["arena_weight"])) for c in cards)
        for c in cards:
            c["arena_weight"] = (max(0.0, float(c["arena_weight"])) / mass * n / total) if mass else 0.0
    sides = {u: sum(c["arena_weight"] for c in out if bool(c["unwinnable"]) == u) for u in (False, True)}
    caps = _Caps(pool.capped if pool.capped is not None else example_caps())
    train = [c for c in out if c["id"] not in held]
    for c in train:
        c["arena_weight"] *= pool.weight(c)
    _shares(train, sides)
    cards_mod.cap_wants(train, caps)
    _hold(train, caps)
    gate = [c for c in out if c["id"] in held and buys(c)]
    _shares(gate, {False: 1.0, True: 0.0})
    cards_mod.cap_wants(gate, caps)
    _hold(gate, caps)
    return train, gate


def _hold(cards, caps):
    """cap_wants rounds each weight to 3 places, so the weights can add up to a little under 1 and
    a capped want's share of the draws a little over its most (0.2503 for 0.25). This cuts that
    want's cards by just enough, so its share of the draws is at most its most."""
    for _, rx, most in caps.capped:
        mine = [c for c in cards if any(rx.search(w) for w in c["want"])]
        have = sum(c["arena_weight"] for c in mine)
        rest = sum(c["arena_weight"] for c in cards) - have
        if have <= 0 or rest <= 0 or have / (have + rest) <= most:
            continue
        cut = most * rest / (have * (1 - most))
        for c in mine:
            c["arena_weight"] = math.floor(c["arena_weight"] * cut * 1e6) / 1e6


def _shares(cards, sides):
    """Each side (winnable, unwinnable) of cards brought to its share of the draws; a side with no
    card here gives its share to the other, so the draws add up to 1."""
    mass = {u: sum(c["arena_weight"] for c in cards if bool(c["unwinnable"]) == u) for u in sides}
    have = {u: share for u, share in sides.items() if mass[u] > 0}
    whole = sum(have.values())
    for c in cards:
        u = bool(c["unwinnable"])
        c["arena_weight"] = round(c["arena_weight"] / mass[u] * have[u] / whole, 6) if u in have and whole else 0.0


# ---- the night: real chats into practice customers

LIVE = "parent_id IS NULL AND channel NOT LIKE 'history:%'"  # no branch, no imported history chat


def real_chats(db, since, until, pool=None):
    """[(chat id, reflection/history.py Chat, hard signs, (last step, its time))] for the pool's
    pending chats first, then the agent's other chats with a message in [since, until): the steps
    after the last one the pool read (pool.progress), before until; customer steps as the
    customer's, the agent's and a person's replies as the store's; tool calls and events left
    out, a failed send check and a person's reply counted. The last step is None when no new step
    came.
    What the customer gave for an order (the name, the name to print, the address and the phone in
    each draft_order call) and the chat's own number go on the Chat (names, address, phone,
    typed_phones), so the cleaner masks them wherever they are typed, with or without a cue."""
    with db.tx() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"chats", "steps"} <= tables:
            return []
        ids = {}
        for chat_id in list(pool.pending) if pool is not None else []:
            row = c.execute(f"SELECT id, customer_id FROM chats WHERE id = ? AND {LIVE}", (chat_id,)).fetchone()
            if row is not None:
                ids[row[0]] = row[1]
        for row in c.execute(f"SELECT id, customer_id FROM chats WHERE {LIVE} AND updated_at >= ? AND updated_at < ? "
                             "ORDER BY created_at", (since, until)):
            ids.setdefault(row[0], row[1])
        out = []
        for chat_id, customer in ids.items():
            got = pool.progress(chat_id) if pool is not None else None
            after = got[0] if got is not None else 0
            floor = pool.floor if got is None and pool is not None and pool.floor is not None else float("-inf")
            if got is not None and got[0] == 0:  # an old pool read it; its step is not known (Pool, seen)
                floor = got[1]
            rows = c.execute("SELECT n, role, content, tool_calls, name, media, at FROM steps WHERE chat_id = ? "
                             "AND at < ? ORDER BY n", (chat_id, until)).fetchall()
            msgs, signs, last = [], {"person": False, "check_failed": False}, None
            typed = {"names": set(), "phones": set(), "addresses": set()}
            for n, role, content, tool_calls, name, media, at in rows:
                if role == "assistant":
                    _typed(tool_calls, typed)  # from every talk of the chat: a name given once is masked in all
                if n <= after or float(at) <= floor:
                    continue
                last = (n, float(at))
                if role == "event":
                    signs["check_failed"] |= '"check_failed"' in (content or "")
                elif role == "user":
                    msgs.append(hist.Message(at=float(at), team=False, text=content or "", media=_media(media)))
                elif role == "assistant":
                    if (content or "").strip():
                        signs["person"] |= name == PERSON
                        msgs.append(hist.Message(at=float(at), team=True, text=content))
            phone = hist.phone_key(customer or "")
            chat = hist.Chat(source=hist.WHATSAPP, key=chat_id, place=0, messages=msgs, phone=phone,
                             names=typed["names"], typed_phones=(typed["phones"] | {phone}) - {""})
            chat.addresses = typed["addresses"]
            out.append((chat_id, chat, signs, last))
    return out


TYPED_NAMES = ("name",)          # draft_order arguments that hold a person's name
TYPED_PRINT = "print_name"       # on an item: the name to print, often the customer's or a friend's
MAX_TYPED = 300                  # draft_order's longest text field (the address)


def _typed(raw, typed):
    """Adds what the customer gave in each draft_order call of one step (kit/tools/draft_order.py)
    to typed: names (name, print_name), phones (phone) and addresses (address)."""
    try:
        calls = json.loads(raw) if raw else []
    except ValueError:
        return
    for call in calls if isinstance(calls, list) else []:
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict) or fn.get("name") != "draft_order":
            continue
        args = fn.get("arguments")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except ValueError:
            continue
        if not isinstance(args, dict):
            continue
        names = [args.get(k) for k in TYPED_NAMES]
        names += [i.get(TYPED_PRINT) for i in args.get("items") or [] if isinstance(i, dict)]
        typed["names"] |= {n.strip() for n in names if isinstance(n, str) and 2 <= len(n.strip()) <= MAX_TYPED}
        if isinstance(args.get("phone"), str):
            typed["phones"] |= {hist.phone_key(args["phone"])} - {""}
        if isinstance(args.get("address"), str) and 5 <= len(args["address"].strip()) <= MAX_TYPED:
            typed["addresses"].add(args["address"].strip())


class _Typed:
    """One chat's cleaner (arena/clean.py ChatCleaner) with the addresses the customer gave for an
    order taken out first, wherever they are typed, as [address]."""

    def __init__(self, inner, addresses):
        self.inner = inner
        words = [a.split() for a in sorted(addresses, key=len, reverse=True)]
        self.rx = re.compile("|".join(r"\s+".join(map(re.escape, w)) for w in words if w),
                             re.IGNORECASE) if any(words) else None

    def _out(self, text):
        return self.rx.sub("[address]", text) if self.rx is not None and isinstance(text, str) else text

    def __call__(self, text):
        return self.inner(self._out(text))

    def texts(self, messages):
        return self.inner.texts([dataclasses.replace(m, text=self._out(m.text)) for m in messages])


def _media(raw):
    try:
        got = json.loads(raw) if raw else None
    except ValueError:
        return None
    kinds = [m.get("kind") for m in got if isinstance(m, dict)] if isinstance(got, list) else []
    return next((k for k in kinds if isinstance(k, str)), None)


def hard(chat, signs):
    """A won chat worth practising: HARD_TURNS customer messages or more, a person stepped in, or a
    send check failed."""
    return (sum(not m.team for m in chat.messages) >= HARD_TURNS or bool(signs.get("person"))
            or bool(signs.get("check_failed")))


SETTLED = frozenset({label_mod.NO_PRICE})  # unclear but over: quiet with no price given
WAITING = frozenset({label_mod.OPEN, label_mod.UNANSWERED, label_mod.VOICE})  # unclear for now, settles soon


def grow(db, pool, *, since, until, tagger, calls=None, most=MAX_NEW, quiet_hours=label_mod.QUIET_HOURS):
    """The night's new practice items from the real chats into the pool. Returns counts only."""
    from arena.personas import turns_of  # the persona build's own turns, cleaned the same way
    n = Counter()
    chats = real_chats(db, since - quiet_hours * 3600, until, pool)
    cleaner = Cleaner({name for _, chat, _, _ in chats for name in chat.names})  # every name of the night
    for chat_id, chat, signs, last in chats:
        if last is None:  # no step since the last one read
            n["already read"] += 1
            pool.unpend(chat_id)
            continue
        n["read"] += 1
        lab, why = label_mod.label(chat, until, quiet_hours)
        if lab == label_mod.UNCLEAR:
            n["unclear, skipped"] += 1
            if why in SETTLED:
                pool.mark(chat_id, *last)
            elif why in WAITING:
                pool.pend(chat_id)
            else:  # left unmarked: read again with what comes after it once the chat has a new message
                pool.unpend(chat_id)
            continue
        if lab == label_mod.WON and not hard(chat, signs):
            n["easy wins, skipped"] += 1
            pool.mark(chat_id, *last)
            continue
        if n["added"] >= most or not tagger.can_ask() or (calls is not None and calls.reached):
            n["left for a later night"] += 1
            pool.pend(chat_id, tried=False)
            continue
        chat_cleaner = _Typed(cleaner.chat(chat.names), getattr(chat, "addresses", ()))
        turns = turns_of(chat, chat_cleaner)
        tags = tagger(turns, lab, cleaner=chat_cleaner)
        if tags is None:
            n["not tagged"] += 1
            if not pool.pend(chat_id):  # tried MAX_TRIES nights: let it go
                pool.mark(chat_id, *last)
            continue
        pool.add({"label": lab, "why": why, "hard": lab == label_mod.WON, "tags": tags,
                  "style": cards_mod.style_of(chat), "turns": turns}, chat_id, *last)
        n["added"] += 1
        n["lost" if lab == label_mod.LOST else "hard"] += 1
    return dict(n)


def tag_model():
    """The tagger's model: Muse Spark Open, as the persona build tags (arena/tag.py)."""
    from arena import tag as tag_mod
    from kit import model as model_mod
    return model_mod.Model(timeout=tag_mod.TIMEOUT, route=model_mod.OPEN)


def night(db_path, plug, recipe_path, since, until):
    """The night step for an agent that grows practice customers: new real chats into its owner's
    pool. Returns counts and the pool's summary; stopped names why nothing more was read."""
    from arena import recipe as recipe_mod
    from arena import run as arena_run
    from arena import tag as tag_mod
    from kit.db import Db
    folder = Path(db_path).expanduser().resolve().parent
    rep = {"kind": kind_of(plug), "stopped": None}
    if not recipe_path:
        rep["stopped"] = "no recipe given (--recipe); no chat read"
        return rep
    try:
        recipe = recipe_mod.load(recipe_path)
        pool = Pool(owner_of(folder), kind_of(plug))
    except (hist.Refused, Refused) as e:
        rep["stopped"] = str(e)
        return rep
    calls = arena_run.Calls(folder / arena_run.CALLS_FILE, arena_run.DEFAULT_CAP)
    tagger = tag_mod.Tagger(model=calls.model(tag_model()), cap=MAX_NEW, recipe=recipe)
    db = Db(str(db_path))
    try:
        rep.update(grow(db, pool, since=since, until=until, tagger=tagger, calls=calls))
    finally:
        db.close()
    if rep.get("added"):
        pool.rebuild(recipe)
    if pool.changed:
        try:
            pool.save()
        except OSError as e:  # the night's report is still saved; the counts above were not kept
            rep["stopped"] = f"the pool was not saved ({type(e).__name__})"
            rep.update(pool.summary())
            return rep
    if calls.reached:
        rep["stopped"] = "the Arena's call cap"
    elif tagger.stopped:
        rep["stopped"] = tagger.stopped
    rep.update(pool.summary())
    return rep


def line(rep):
    """The night step in one plain line."""
    if rep.get("stopped") and "items" not in rep:
        return f"practice customers: not grown, {rep['stopped']}"
    return (f"practice customers: {rep.get('added', 0)} new from real chats ({rep.get('lost', 0)} lost, "
            f"{rep.get('hard', 0)} hard); {rep.get('easy wins, skipped', 0)} easy wins and "
            f"{rep.get('unclear, skipped', 0)} unclear skipped; the pool holds {rep['grown_cards']} cards from "
            f"{rep['items']} chats, shared by {', '.join(rep['siblings']) or 'this agent only'}"
            + (f" (stopped: {rep['stopped']})" if rep.get("stopped") else ""))
