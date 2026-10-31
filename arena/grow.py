"""Practice customers grown from an agent's real chats (new, 2026-10-31; DECISIONS items 30, 32, 33,
47, 48, 51).

Both sides grow, the way the assistant's Arena grows from real days (assistant/arena.py). Each
night Reflection reads the Sales agent's new real chats (kit/chats.py, the agent's database) and
sends the Arena new practice cases beside its lessons (item 47):
  lost     quiet after the price (arena/label.py): kept.
  hard     won, but only after at least HARD_TURNS customer messages, a person stepping in or a
           failed send check: kept.
  easy     any other win: skipped, there is nothing in it to practise.
  unclear  skipped, never guessed (arena/label.py). A chat still open is not marked as read, so a
           later night labels it again once it has settled.
The chats read are the ones with a message since the night's window opened, looking back
label.QUIET_HOURS more, so a chat that went quiet just before the window still counts. A chat
the pool has read is never read twice.

Each kept chat is cleaned (arena/clean.py: names, numbers and places out) before the tagger
(arena/tag.py) sees it and before anything is written; no second scan (item 40). The cleaner
knows what the customers gave for their orders: every name and name to print in the night's
draft_order calls is masked in any chat of the night, and in its own chat each word of it, the
address and the chat's number too, so a name typed bare with no cue word still goes. Its tags and
cleaned turns join the pool, and the pool's cards are rebuilt through the card code
(arena/cards.py build), so the unwinnable share and the capped wants (item 33: name printing at
most 25%) hold for the grown cards as for the first ones. A grown card's id names its group
(grown-<worry>, grown-<worry>-no-budget), so it keeps its losses when the pool is rebuilt.

A practice customer that beats the agent comes back more often: the pool counts each card's
losses in training matches (arena/run.py), and a card is drawn 1 + LOST_WEIGHT times as often per
loss (deck). Each side, winnable and unwinnable, keeps its share of the draws, and the capped
wants are held again after the losses are counted, so neither cap moves.

Pools are per owner (item 51). The pool is practice-<kind>.json in the owner's state folder (in
data/, which git ignores, or outside the repo). An agent's own folder is the folder of its
database; when that folder holds the agent's plug (<folder>/plug.json), the owner's folder is the
one above it, so several agents of one owner each keep their own database and Arena files and
share one owner folder. A sibling is a plug of the same kind (engine/plug.py kind) in the same
owner folder: siblings share the pool, so a new agent of a kind the owner already runs starts
with zero lessons (item 20) and faces the practice customers its siblings' real work grew. A pool
path outside the owner's folder is refused, a link included, so nothing crosses to another
owner, even cleaned.

The tagger's calls count against the Arena's daily cap in the agent's own folder (arena/run.py
Calls), at most MAX_NEW chats a night. The step needs the persona recipe (arena/recipe.py,
private): with none it reads no chat and says so.
"""
import dataclasses
import json
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
HARD_TURNS = 6
MAX_NEW = 50
MAX_ITEMS = 500
MAX_SEEN = 5000
MAX_PATTERN = 20_000
DEFAULT_KIND = "sales"
KIND = re.compile(r"[a-z][a-z0-9_]{0,40}")
POOL_FILE = "practice-{kind}.json"
PERSON = "person"  # kit/chats.py PERSON: a team member's own reply


class Refused(ValueError):
    pass


# ---- owners, kinds and siblings

def kind_of(plug):
    """The plug's kind: its own when it names one, else its agent's name."""
    return getattr(plug, "kind", "") or plug.agent


def owner_of(folder):
    """The owner's state folder for an agent's folder (see the module lines)."""
    folder = Path(folder).expanduser().resolve()
    return folder.parent if (folder / "plug.json").is_file() else folder


def kind_at(folder, default=DEFAULT_KIND):
    """The kind of the agent whose plug sits in folder, or default when none does."""
    path = Path(folder).expanduser().resolve() / "plug.json"
    return kind_of(plug_mod.load(path)) if path.is_file() else default


def siblings(owner, kind):
    """The agents of this kind with a plug in the owner's folder (<folder>/plug.json), sorted."""
    out = []
    for path in sorted(Path(owner).expanduser().resolve().glob("*/plug.json")):
        try:
            plug = plug_mod.load(path)
        except (OSError, ValueError):
            continue
        if kind_of(plug) == kind:
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
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        self.items = [i for i in (data.get("items") or []) if _item_ok(i)][-MAX_ITEMS:]
        self.seen = [str(s) for s in (data.get("seen") or []) if isinstance(s, str)][-MAX_SEEN:]
        self.played = {str(k): v for k, v in (data.get("played") or {}).items()
                       if isinstance(v, dict) and _count(v.get("played")) and _count(v.get("lost"))}
        self.cards = [c for c in (data.get("cards") or []) if _card_ok(c)]
        capped = data.get("capped")  # None until the pool is first built from a recipe
        self.capped = [c for c in capped if _capped_ok(c)] if isinstance(capped, list) else None
        self._seen = set(self.seen)
        self.changed = False

    def weight(self, card_id):
        return 1 + LOST_WEIGHT * int(self.played.get(str(card_id), {}).get("lost", 0))

    def record(self, card_id, won):
        row = self.played.setdefault(str(card_id), {"played": 0, "lost": 0})
        row["played"] += 1
        row["lost"] += 0 if won else 1
        self.changed = True

    def has(self, chat_id):
        return str(chat_id) in self._seen

    def mark(self, chat_id):
        if not self.has(chat_id):
            self.seen.append(str(chat_id))
            self._seen.add(str(chat_id))
            self.changed = True

    def add(self, item, chat_id):
        """A cleaned, tagged real chat joins the pool ({label, tags, style, turns}, as arena/cards.py takes)."""
        if not _item_ok(item):
            raise ValueError("a practice item has a label, tags, a style and turns")
        self.items = (self.items + [item])[-MAX_ITEMS:]
        self.mark(chat_id)

    def rebuild(self, recipe):
        """The pool's cards from its items, through the card code; ids name each card's group."""
        built, _ = cards_mod.build([{**i, "grown": True} for i in self.items], recipe) if self.items else ([], None)
        for c in built:
            c["id"] = grown_id(c)
        self.cards = built
        self.capped = [{"name": name, "pattern": rx.pattern, "most": most}
                       for name, rx, most in getattr(recipe, "capped", ())]
        self.changed = True

    def save(self):
        self.seen = self.seen[-MAX_SEEN:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"kind": self.kind, "items": self.items, "seen": self.seen, "played": self.played,
                                   "cards": self.cards, "capped": self.capped}, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)
        self.changed = False

    def summary(self):
        return {"kind": self.kind, "grown_cards": len(self.cards), "items": len(self.items),
                "siblings": siblings(self.owner, self.kind)}


def _count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _item_ok(i):
    return (isinstance(i, dict) and i.get("label") in (label_mod.WON, label_mod.LOST)
            and isinstance(i.get("tags"), dict) and isinstance(i.get("style"), dict) and isinstance(i.get("turns"), list))


def _card_ok(c):
    return (isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"].startswith("grown-")
            and isinstance(c.get("arena_weight"), (int, float)) and isinstance(c.get("want"), list))


def _capped_ok(c):
    return (isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("pattern"), str)
            and len(c["pattern"]) <= MAX_PATTERN and isinstance(c.get("most"), (int, float))
            and not isinstance(c["most"], bool) and 0 < c["most"] < 1)


def grown_id(card):
    """grown-<worry>, with -no-budget for a card unwinnable for no budget: the same group, the same id."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(card.get("worry") or "other").casefold()).strip("-") or "other"
    return f"grown-{slug}" + ("-no-budget" if card.get("why_unwinnable") == "no budget" else "")


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


def deck(base, pool):
    """The cards the Arena draws from: the base cards and the pool's grown ones, each part by its
    chats, every card's weight times its losses (Pool.weight), each side kept at its share of the
    draws and the capped wants held (arena/cards.py cap_wants): the owner's recipe's, saved in the
    pool when it was built, or the example recipe's (item 33) for a pool never built. With no pool, no grown card and no
    loss counted, the base cards as they are. Base cards built with the pool already in them (a
    "grown" count on each, arena/personas.py --state) take no grown card again."""
    if pool is None:
        return base
    folded = any("grown" in c for c in base)
    grown = [] if folded else [dict(c) for c in pool.cards]
    if not grown and not any(pool.weight(c["id"]) > 1 for c in base):
        return base
    out = [dict(c) for c in base] + grown
    parts = ((out[:len(base)], sum(int(c.get("chats") or 1) for c in base)),
             (grown, sum(int(c.get("chats") or 1) for c in grown)))
    total = sum(n for _, n in parts) or 1
    for cards, n in parts:
        mass = sum(max(0.0, float(c["arena_weight"])) for c in cards)
        for c in cards:
            c["arena_weight"] = (max(0.0, float(c["arena_weight"])) / mass * n / total) if mass else 0.0
    sides = {u: sum(c["arena_weight"] for c in out if bool(c.get("unwinnable")) == u) for u in (False, True)}
    for c in out:
        c["arena_weight"] *= pool.weight(c["id"])
    for u, share in sides.items():
        mine = [c for c in out if bool(c.get("unwinnable")) == u]
        mass = sum(c["arena_weight"] for c in mine)
        for c in mine:
            c["arena_weight"] = round(c["arena_weight"] / mass * share, 6) if mass else 0.0
    cards_mod.cap_wants(out, _Caps(pool.capped if pool.capped is not None else example_caps()))
    return out


# ---- the night: real chats into practice customers

def real_chats(db, since, until):
    """[(chat id, reflection/history.py Chat, hard signs)] for the agent's chats with a message in
    [since, until): customer steps as the customer's, the agent's and a person's replies as the
    store's; tool calls and events left out, a failed send check and a person's reply counted.
    What the customer gave for an order (the name, the name to print, the address and the phone in
    each draft_order call) and the chat's own number go on the Chat (names, address, phone,
    typed_phones), so the cleaner masks them wherever they are typed, with or without a cue."""
    with db.tx() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"chats", "steps"} <= tables:
            return []
        ids = [(r[0], r[1]) for r in c.execute(
            "SELECT id, customer_id FROM chats WHERE parent_id IS NULL AND updated_at >= ? AND updated_at < ? "
            "ORDER BY created_at", (since, until))]
        out = []
        for chat_id, customer in ids:
            rows = c.execute("SELECT role, content, tool_calls, name, media, at FROM steps WHERE chat_id = ? "
                             "AND at < ? ORDER BY n", (chat_id, until)).fetchall()
            msgs, signs = [], {"person": False, "check_failed": False}
            typed = {"names": set(), "phones": set(), "addresses": set()}
            for role, content, tool_calls, name, media, at in rows:
                if role == "event":
                    signs["check_failed"] |= '"check_failed"' in (content or "")
                elif role == "user":
                    msgs.append(hist.Message(at=float(at), team=False, text=content or "", media=_media(media)))
                elif role == "assistant":
                    _typed(tool_calls, typed)
                    if (content or "").strip():
                        signs["person"] |= name == PERSON
                        msgs.append(hist.Message(at=float(at), team=True, text=content))
            phone = hist.phone_key(customer or "")
            chat = hist.Chat(source=hist.WHATSAPP, key=chat_id, place=0, messages=msgs, phone=phone,
                             names=typed["names"], typed_phones=(typed["phones"] | {phone}) - {""})
            chat.addresses = typed["addresses"]
            out.append((chat_id, chat, signs))
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


def grow(db, pool, *, since, until, tagger, calls=None, most=MAX_NEW, quiet_hours=label_mod.QUIET_HOURS):
    """The night's new practice items from the real chats into the pool. Returns counts only."""
    from arena.personas import turns_of  # the persona build's own turns, cleaned the same way
    n = Counter()
    chats = real_chats(db, since - quiet_hours * 3600, until)
    cleaner = Cleaner({name for _, chat, _ in chats for name in chat.names})  # every name of the night
    for chat_id, chat, signs in chats:
        if pool.has(chat_id):
            n["already read"] += 1
            continue
        n["read"] += 1
        lab, why = label_mod.label(chat, until, quiet_hours)
        if lab == label_mod.UNCLEAR:
            n["unclear, skipped"] += 1
            if why != label_mod.OPEN:  # still open: a later night reads it again
                pool.mark(chat_id)
            continue
        if lab == label_mod.WON and not hard(chat, signs):
            n["easy wins, skipped"] += 1
            pool.mark(chat_id)
            continue
        if n["added"] >= most or not tagger.can_ask() or (calls is not None and calls.reached):
            n["left for a later night"] += 1
            continue
        chat_cleaner = _Typed(cleaner.chat(chat.names), getattr(chat, "addresses", ()))
        turns = turns_of(chat, chat_cleaner)
        tags = tagger(turns, lab, cleaner=chat_cleaner)
        if tags is None:
            n["not tagged"] += 1
            continue
        pool.add({"label": lab, "why": why, "hard": lab == label_mod.WON, "tags": tags,
                  "style": cards_mod.style_of(chat), "turns": turns}, chat_id)
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
        pool.save()
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
