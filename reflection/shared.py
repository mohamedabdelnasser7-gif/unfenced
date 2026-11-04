"""The shared pool: patterns learned across owners (new, 2026-11-04; DECISIONS items 24, 51, 62, 79, 83).

A kept lesson or a lost case of any agent kind becomes one general pattern. The model writes it
(Writer, on Muse Spark Open as the fit check and the adapter are), then code checks that it is
clean (check): no name of a person, shop or place, no digit in any script, no amount, price or
currency, no phone, email, link or handle, no quoted words and no run of COPY_RUN words copied
from what it was written from (the lesson's line, the customer's turns), no line that hands a chat
to a person, one line of MIN_CHARS to MAX_CHARS characters and MIN_WORDS to MAX_WORDS words. The
checks reuse arena/clean.py (names, phones, emails, links, places and addresses), engine/risk.py
(the normal form, links, phones, handles and the copy runs), kit/send_check.py (currency and spelled
amounts) and reflection/quickstart.py names_a_person. A pattern that fails is dropped, never stored:
only a hash of where it came from is kept, so the same lesson or chat is not written again.

There is one pool per kind across owners, patterns-<kind>.json in the install's shared folder
(root_for: the folder named "shared" beside the agents' database, inside the repo only under
data/), written under a fresh name and moved into place (arena/personas.py _write), under a lock
so two owners' nights never lose each other's patterns. Each pattern keeps which owners it was
seen at as keyed hashes (owner_hash: HMAC with the folder's own random key), never an owner's name
or id. A pattern written at a second owner joins the first when it is near equal: the same kind of
pattern (lesson or lost) and, on their content words (casefolded, marks and small words out), an
overlap of at least SAME. A pattern is shared only once it is seen at MIN_OWNERS (2) distinct owners.
An agent that names no owner gives nothing (its folder alone never says who the owner is, as in
arena/grow.py); it still reads the pool.

Where the patterns go, each through the paths siblings already take:
  lessons  engine/study.py step 6 reads the shared lesson patterns of its kind beside its siblings,
           after them, for a new agent's first night and every night of a running one. Each goes
           through the fit check and the adapter like a sibling's kept lesson, and on trial only
           through the agent's eval gate and the Canary; with no gate it waits for a yes. A pattern
           seen at this agent's own owner is not read back. The lesson's source line names the
           pattern and "learned from N owners", which the console shows (reflection/console.py).
  lost     arena/grow.py turns each shared lost pattern into a fresh practice customer for every
           owner's Arena (practice_cards): the card holds the pattern and nothing else of any
           chat, so one owner's practice customers never cross (item 51 holds).
"""
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from arena import clean as clean_mod
from arena import paths
from engine import risk as risk_mod
from engine.plug import AGENT_NAME
from engine.study import SMALL_WORDS
from kit import send_check
from reflection import study as parts

LESSON, LOST = "lesson", "lost"
WHATS = (LESSON, LOST)
MIN_OWNERS = 2       # a pattern is shared only once seen at this many distinct owners (item 83)
SAME = 0.6           # the content word overlap at which two owners' patterns are one
MIN_SAME_WORDS = 3   # fewer content words than this: only the very same words are one pattern
MIN_CHARS, MAX_CHARS = 20, 240
MIN_WORDS, MAX_WORDS = 4, 40
MAX_PATTERNS = 500   # per kind; the oldest seen at one owner only go first
MAX_OWNERS = 1000    # owner hashes a pattern keeps
MAX_KEYS = 20_000    # hashes of where patterns came from
MAX_CARDS = 20       # fresh practice customers from shared lost patterns, most owners first
GIVE = 5             # kept lessons a night may send to the writer
GIVE_LOST = 5        # lost chats a night may send to the writer
POOL_FILE = "patterns-{kind}.json"
KEY_FILE = "owner-key"
SHARED_DIR = "shared"
POOL_AGENT = "shared_pool"  # the name the study's notes and links give the pool
MAX_FILE = 5_000_000
HASH = re.compile(r"[0-9a-f]{32}")
PID = re.compile(r"[0-9a-f]{12}")
LABEL = re.compile(r"[a-z]+(?: [a-z]+){0,3}")


class Refused(ValueError):
    pass


# ---- the clean check

_EXTRA_MONEY = (r"dollars?|usd|\$|€|euros?|riyals?|sar|aed|dirhams?|ريال|ريالات|دولار|دولارات|درهم|يورو"
                r"|dolar|dollar|riyal|dirham")
CURRENCY = re.compile(r"(?<![^\W\d_])(?:" + send_check.CURRENCY + "|" + _EXTRA_MONEY + r")(?![^\W\d_])",
                      re.IGNORECASE)
MAGNITUDE = re.compile(r"(?<![^\W\d_])" + send_check.MAGNITUDE_WORDS + r"(?![^\W\d_])", re.IGNORECASE)
QUOTES = re.compile("[\"“”„‟«»‹›〝〞「」『』]|(?<![^\\W\\d_])['‘’]|['‘’](?![^\\W\\d_])")
CAPITAL = re.compile(r"[A-Z]")
SENTENCE = re.compile(r"(?:^|[.!?؟:;]\s+)$")
LINE_BREAK = re.compile(r"[\r\n  ]")
BRACKET = re.compile(r"\[[^\]]*\]")


def check(text, sources=()):
    """Why the pattern is not clean, as plain reasons; [] when it is. sources: the texts it was
    written from (the lesson's line, the customer's turns); a run of risk.COPY_RUN words from one is
    quoted words."""
    if not isinstance(text, str) or not text.strip():
        return ["not a line"]
    out = []
    plain = clean_mod.normalize(text).strip()  # NFKC, hidden marks out, Eastern digits as 0 to 9
    norm = risk_mod.normalize(text)    # every numeral sign as a digit, look alikes as letters
    words = re.findall(r"[^\W_]+", plain)
    if not MIN_CHARS <= len(text.strip()) <= MAX_CHARS or not MIN_WORDS <= len(words) <= MAX_WORDS:
        out.append(f"length: {MIN_CHARS} to {MAX_CHARS} characters and {MIN_WORDS} to {MAX_WORDS} words")
    if LINE_BREAK.search(text):
        out.append("more than one line")
    if any(ch.isdigit() for ch in text) or re.search(r"\d", norm) or re.search(r"\d", plain):
        out.append("a digit")
    if any(rx.search(t) for rx in (CURRENCY, send_check.SPELLED_AMOUNT) for t in (plain, norm)):
        out.append("a currency or an amount")
    elif any(MAGNITUDE.search(t) for t in (plain, norm)):
        out.append("an amount in words")
    if QUOTES.search(plain):
        out.append("quoted words")
    if BRACKET.search(plain):
        out.append("a masked word")
    cleaned = clean_mod.clean(plain)
    masked = sorted(set(clean_mod.PLACEHOLDER.findall(cleaned)) - set(clean_mod.PLACEHOLDER.findall(plain)))
    if masked:
        out.append("a name, phone, email, link, place or address (" + ", ".join(masked) + ")")
    if any(rx.search(norm) for _, rx in risk_mod.CORE):
        out.append("a link, phone or handle")
    if _proper(plain):
        out.append("a capitalised name")
    if sources:
        mine = risk_mod._runs(text)
        if any(mine & risk_mod._runs(s) for s in sources if isinstance(s, str)):
            out.append("quoted words: a run of words copied from what it was written from")
    from reflection.quickstart import names_a_person  # late: quickstart imports much of the repo
    if names_a_person(plain):
        out.append("hands a chat to a person")
    return out


def _proper(text):
    """A Latin word with a capital letter that does not open a sentence (a name, a shop, a place,
    a brand); I alone is a word, not a name."""
    for m in re.finditer(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text):
        w = m.group(0)
        if not CAPITAL.search(w) or w in ("I", "I'm", "I’m"):
            continue
        if CAPITAL.search(w[1:]) or not SENTENCE.search(text[:m.start()]):
            return True
    return False


# ---- near equal patterns

_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})


def _stem(w):
    if w.startswith("ال") and len(w) > 4:
        w = w[2:]
    for end in ("ing", "ed", "es", "ly", "s"):
        if w.endswith(end) and len(w) - len(end) >= 4:
            return w[:-len(end)]
    return w


def words(text):
    """The pattern's content words: casefolded, marks out, Arabic letter forms joined, small words
    and one letter words out, a few endings off; a sorted list."""
    plain = risk_mod.normalize(text, letters=True).translate(_FOLD)
    return sorted({_stem(w) for w in re.findall(r"[^\W\d_]+", plain) if len(w) > 1 and w not in SMALL_WORDS})


def same(a, b):
    """Two patterns' content words (words) are one pattern: the very same words, or both at least
    MIN_SAME_WORDS long with an overlap (shared over all) of at least SAME."""
    a, b = set(a), set(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < MIN_SAME_WORDS:
        return False
    return len(a & b) / len(a | b) >= SAME


# ---- the pool

def root_for(db_path):
    """The install's shared folder: "shared" beside the agents' database."""
    return Path(db_path).expanduser().resolve().parent / SHARED_DIR


def check_root(root):
    root = Path(root).expanduser()
    if root.is_symlink():
        raise Refused("the shared folder is a link")
    root = root.resolve()
    if paths.inside_repo(root) and not paths.within(root, paths.DATA):
        raise Refused("the shared folder sits inside the repo outside data/")
    return root


class Pool:
    """One kind's patterns across owners. Read on open; add() takes the lock, reads again, adds and
    writes."""

    def __init__(self, kind, root):
        if not isinstance(kind, str) or not AGENT_NAME.fullmatch(kind):
            raise Refused("a kind is lowercase letters, digits and _, starting with a letter")
        self.kind, self.root = kind, check_root(root)
        self.path = self.root / POOL_FILE.format(kind=kind)
        self._key = None
        self._read()

    # the owner key and the hashes

    def _secret(self, make=True):
        if self._key is not None:
            return self._key
        path = self.root / KEY_FILE
        if path.is_symlink():
            raise Refused("the shared folder's key is a link")
        if not path.exists():
            if not make:
                return None
            from arena.personas import _write
            os.makedirs(self.root, mode=0o700, exist_ok=True)
            with self._locked():
                if not path.exists():
                    _write(path, secrets.token_hex(32).encode("ascii"))
        raw = path.read_bytes()[:200].strip()
        if not re.fullmatch(rb"[0-9a-f]{64}", raw):
            raise Refused("the shared folder's key is out of shape")
        self._key = bytes.fromhex(raw.decode("ascii"))
        return self._key

    def owner_hash(self, owner):
        """The owner as the pool keeps it: a keyed hash, never the name or id itself."""
        if not isinstance(owner, str) or not owner:
            raise Refused("an owner is a name")
        return hmac.new(self._secret(), b"owner\x00" + owner.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def key_hash(self, owner, key):
        """Where a pattern came from (an owner's agent and lesson, or chat and step), as a keyed hash."""
        raw = f"{owner}\x00{key}".encode("utf-8")
        return hmac.new(self._secret(), b"from\x00" + raw, hashlib.sha256).hexdigest()[:32]

    # reading and writing

    def _read(self):
        data = {}
        if self.path.is_symlink():
            raise Refused("the pool file is a link")
        try:
            if self.path.is_file() and self.path.stat().st_size <= MAX_FILE:
                data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            data = {}
        data = data if isinstance(data, dict) else {}
        if data.get("kind", self.kind) != self.kind:
            raise Refused("the pool file is for another kind of agent")
        self.patterns = [p for p in (data.get("patterns") or [])[:MAX_PATTERNS] if _pattern_ok(p)]
        for p in self.patterns:
            p["words"] = words(p["text"])
        keys = data.get("keys")
        self.keys = [k for k in keys if isinstance(k, str) and HASH.fullmatch(k)][-MAX_KEYS:] \
            if isinstance(keys, list) else []

    @contextlib.contextmanager
    def _locked(self):
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        fd = os.open(self.root / f".patterns-{self.kind}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _save(self):
        from arena.personas import _write
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        if not self.root.is_symlink():
            os.chmod(self.root, 0o700)
        kept = [{k: p[k] for k in ("id", "what", "text", "worry", "owners", "at")} for p in self.patterns]
        _write(self.path, json.dumps({"kind": self.kind, "patterns": kept, "keys": self.keys[-MAX_KEYS:]},
                                     ensure_ascii=False).encode("utf-8"))

    def given(self, owner, key):
        """True when this owner's lesson or chat was written up before (kept or dropped)."""
        return self.key_hash(owner, key) in self.keys

    def add(self, what, text, owner, key, *, worry=None, sources=(), now=None):
        """One owner's pattern into the pool: (the pattern, []) when it was added or joined a near
        equal one, (None, reasons) when the clean check dropped it. Either way only a hash of the
        owner and of where it came from is written; a dropped pattern's words never are."""
        if what not in WHATS:
            raise Refused("a pattern is a lesson or a lost case")
        reasons = check(text, sources)
        worry = _label(worry) if what == LOST else None
        if worry and check(worry + " is what worried the customer"):
            worry = None
        oh, kh = self.owner_hash(owner), self.key_hash(owner, key)
        with self._locked():
            self._read()
            if kh not in self.keys:
                self.keys.append(kh)
            if reasons:
                self._save()
                return None, reasons
            text = " ".join(text.split())
            mine = words(text)
            best, score = None, -1.0
            for p in self.patterns:
                if p["what"] != what or not same(mine, p["words"]):
                    continue
                a, b = set(mine), set(p["words"])
                s = len(a & b) / len(a | b)
                if s > score:
                    best, score = p, s
            if best is None:
                pid = hashlib.sha256(f"{what}\x00{text}".encode("utf-8")).hexdigest()[:12]
                best = next((p for p in self.patterns if p["id"] == pid), None)
            if best is None:
                best = {"id": pid, "what": what, "text": text, "worry": worry, "owners": [],
                        "at": float(time.time() if now is None else now), "words": mine}
                self.patterns.append(best)
            if oh not in best["owners"] and len(best["owners"]) < MAX_OWNERS:
                best["owners"].append(oh)
            if len(self.patterns) > MAX_PATTERNS:  # the oldest seen at one owner only go first
                lone = [p for p in self.patterns if len(p["owners"]) < MIN_OWNERS and p is not best]
                drop = {id(p) for p in lone[:len(self.patterns) - MAX_PATTERNS]}
                self.patterns = [p for p in self.patterns if id(p) not in drop][-MAX_PATTERNS:]
            self._save()
            return dict(best), []

    def shared(self, what, but=None):
        """The patterns of this kind (lesson or lost) seen at MIN_OWNERS or more distinct owners, most
        owners first. but: an owner whose own patterns are left out (an agent never reads back what
        its own owner gave)."""
        mine = self.owner_hash(but) if but else None
        out = [p for p in self.patterns if p["what"] == what and len(set(p["owners"])) >= MIN_OWNERS
               and (mine is None or mine not in p["owners"])]
        return sorted(out, key=lambda p: (-len(set(p["owners"])), p["at"], p["id"]))


def _pattern_ok(p):
    """A pattern as add() writes it, its text clean by check() again (a hand edited file gains
    nothing), its owners hashes only."""
    return (isinstance(p, dict) and isinstance(p.get("id"), str) and PID.fullmatch(p["id"])
            and p.get("what") in WHATS and isinstance(p.get("text"), str) and not check(p["text"])
            and (p.get("worry") is None or isinstance(p["worry"], str) and LABEL.fullmatch(p["worry"]))
            and isinstance(p.get("owners"), list) and 0 < len(p["owners"]) <= MAX_OWNERS
            and all(isinstance(o, str) and HASH.fullmatch(o) for o in p["owners"])
            and len(set(p["owners"])) == len(p["owners"])
            and isinstance(p.get("at"), (int, float)) and not isinstance(p["at"], bool))


def _label(v):
    """A worry as a short plain label (arena/madeup.py: a few lower case words), else None."""
    v = " ".join(v.casefold().split()) if isinstance(v, str) else ""
    return v if LABEL.fullmatch(v) else None


# ---- the writer

PROMPT = """You turn one {what} of a {kind} agent into one general pattern that an agent of the same
kind at another business could learn from. {about}
Write one plain sentence in English. Never write a name of a person, a shop, a brand or a place, a
number in digits or words, a price, an amount or a currency, a phone number, an email or a link, and
never quote anyone's words. Say what happens or what to do, in general terms.
Answer with JSON only: {{"pattern": "the sentence"}}"""
ABOUT = {LESSON: "The data holds the lesson the agent kept after its trial.",
         LOST: "The data holds a practice chat the agent lost, cleaned, and the customer's worry; write how "
               "this kind of customer behaves, so a practice customer can play it."}


class Writer(parts._Part):
    """writer(what, kind, data): the pattern line, or None for anything odd. check() decides if it
    is kept."""

    def __call__(self, what, kind, data):
        said = self.ask(PROMPT.format(what="kept lesson" if what == LESSON else "lost case", kind=kind,
                                      about=ABOUT[what]), data)
        got = parts.read_json(said)
        line = got.get("pattern") if isinstance(got, dict) else None
        return line.strip() if isinstance(line, str) and line.strip() else None


# ---- the link the night study and the night's practice step read

class Link:
    """One agent's way into its kind's pool. owner: the owner its plug names, or "" (gives nothing).
    writer: Writer or a test's stand in. give, give_lost: the writer's calls a night at most."""

    def __init__(self, kind, owner, writer, root, give=GIVE, give_lost=GIVE_LOST):
        self.kind, self.owner, self.writer = kind, owner or "", writer
        self.root, self.give, self.give_lost = root, int(give), int(give_lost)
        self._pool = None

    @classmethod
    def for_plug(cls, plug, writer, root, **kw):
        return cls(getattr(plug, "kind", "") or plug.agent, getattr(plug, "owner", ""), writer, root, **kw)

    @property
    def pool(self):
        if self._pool is None:
            self._pool = Pool(self.kind, self.root)
        return self._pool

    def lessons(self):
        """The shared lesson patterns this agent may take: [{id, text, owners}] (owners: how many)."""
        pool = self.pool
        pool._read()  # what other owners' nights added since this link opened it
        return [{"id": p["id"], "text": p["text"], "owners": len(set(p["owners"]))}
                for p in pool.shared(LESSON, but=self.owner or None)]

    def source(self, pid, owners):
        """The source line a lesson taken from pattern pid carries (the console reads owners off it)."""
        return source_line(self.kind, pid, owners)

    @staticmethod
    def pattern_of(source):
        """The pattern a lesson's source line names, or None for a lesson not from the pool."""
        return pattern_in(source)

    def _give(self, what, key, data, sources, worry=None):
        if not self.owner:
            return {"pattern": None, "why": "this agent names no owner, so it gives nothing"}
        if self.pool.given(self.owner, key):
            return {"pattern": None, "why": "given before"}
        try:
            line = self.writer(what, self.kind, data)
        except Exception as e:  # a failing writer gives nothing tonight; asked again another night
            return {"pattern": None, "why": f"the writer failed ({type(e).__name__})", "asked": True}
        got, reasons = self.pool.add(what, line or "", self.owner, key, worry=worry, sources=sources)
        if got is None:
            return {"pattern": None, "why": "dropped: " + "; ".join(reasons), "asked": True}
        return {"pattern": got["id"], "owners": len(set(got["owners"])), "why": None, "asked": True}

    def give_lesson(self, agent, lesson):
        """One kept lesson ({id, text}) of this owner's agent into the pool, once."""
        return self._give(LESSON, f"lesson:{agent}:{lesson['id']}", {"lesson": lesson["text"]}, [lesson["text"]])

    def give_chat(self, chat_key, turns, worry):
        """One lost chat, already cleaned (arena/grow.py), into the pool, once. Its customer turns are
        the copy check's sources."""
        said = [t.get("text", "") for t in turns if isinstance(t, dict) and isinstance(t.get("text"), str)]
        return self._give(LOST, f"chat:{chat_key}", {"lost case": turns, "worry": _label(worry) or "other"},
                          said, worry=worry)


def practice_cards(kind, root):
    """Fresh practice customers from the shared lost patterns of this kind, for any owner's Arena:
    at most MAX_CARDS, most owners first. A card holds the pattern as how the customer behaves and
    nothing of any chat (no want, example or line), training only (a grown- id, arena/grow.py decks)."""
    if root is None:
        return []
    try:
        pool = Pool(kind, root)
    except Refused:
        return []
    out = []
    for p in pool.shared(LOST)[:MAX_CARDS]:
        arabic = bool(send_check.ARABIC.search(p["text"]))
        out.append({"id": f"grown-shared-{p['id']}", "worry": p["text"], "unwinnable": False,
                    "why_unwinnable": None, "want": [], "buy_trigger": [], "patience": {"median": 3.0, "most": 4},
                    "style": {"length": {"short": 1.0}, "language": {"arabic" if arabic else "english": 1.0},
                              "voice_notes": 0.0, "opening": {"greeting": 1.0}},
                    "chats": 1, "won": 0, "lost": 0, "examples": [], "arena_weight": 1.0,
                    "shared": {"owners": len(set(p["owners"])), "worry": p["worry"]}})
    return out


SOURCE = re.compile(r"shared pool of [a-z][a-z0-9_]* agents, pattern ([0-9a-f]{12}), learned from (\d+) owners")


def source_line(kind, pid, owners):
    return f"shared pool of {kind} agents, pattern {pid}, learned from {int(owners)} owners"


def owners_in(source):
    """How many owners a lesson from the pool was learned from, read off its source line; None for
    any other lesson."""
    m = SOURCE.search(source or "") if isinstance(source, str) else None
    return int(m.group(2)) if m else None


def pattern_in(source):
    m = SOURCE.search(source or "") if isinstance(source, str) else None
    return m.group(1) if m else None
