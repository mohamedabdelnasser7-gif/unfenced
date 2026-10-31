"""The persona recipe (new, 2026-10-30): the tag prompt and the worry list, kept out of the code
and out of this public repo (DECISIONS item 17). A run needs its own recipe, a private file given
with --recipe; there is no built-in one. demo/personas/recipe.example.json shows the shape with
stand-in text.

A recipe is a JSON file:
  prompt      the instructions the model gets. It must hold {worries}, filled with the worry
              names, and the five answer keys (want, worry, buy_trigger, patience, no_budget),
              so a tuned prompt cannot drop the answer the code reads.
  worries     2 to 12 of {"name": lower case letters and spaces, "words": [plain words]}. The
              words pick a card's example lines and drive the scripted model; they are plain
              text, not patterns: Arabic alef, ta marbuta and ya forms count as one, and an
              Arabic word also matches with و, ف, ب, ل or ال before it.
  unwinnable  the worry names that make a chat unwinnable (the example: just browsing).
  fallback    the worry the scripted model gives when no word matches.
  capped_wants  optional, at most MAX_CAPPED of {"name": as a worry's, "words": 1 or more plain
              words as above, "most": a share above 0 and below 1}: a want the Arena draws at
              most that share of the time (arena/cards.py cap_wants; DECISIONS item 33, the
              name printing at most 25% of practice customers). A card is that want's when one
              of its wants holds one of the words.
The file is read like any other input: no link, a plain file, at most MAX_BYTES, JSON depth
checked. A file inside the repo is refused (case ignored, arena/paths.py), except the example,
so a private recipe can never sit where it could be committed. A refusal names what is wrong,
never the file's text.
"""
import hashlib
import os
import re
import stat
from pathlib import Path

from kit import send_check
from reflection import history as hist
from arena import clean, paths

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "demo" / "personas" / "recipe.example.json"  # the shape only, never a run's recipe
MAX_BYTES = 256 * 1024
MAX_PROMPT = 8000
KEYS = ("want", "worry", "buy_trigger", "patience", "no_budget")
NAME = re.compile(r"[a-z][a-z ]{0,38}[a-z]")
MAX_WORDS, MAX_WORD = 200, 60
MAX_CAPPED = 4


def _read(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        fd = None
    if fd is None:
        raise hist.Refused("the recipe: a link, not found or not readable")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            raise hist.Refused(f"the recipe: not a plain file of at most {MAX_BYTES // 1024} KB")
        data = os.read(fd, MAX_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_BYTES:
        raise hist.Refused("the recipe: over the size cap")
    return data


def _words(words):
    parts = []
    for w in words:
        w = " ".join(w.split())
        if w:
            parts.append(clean._arabic_place(w) if send_check.ARABIC.search(w) else clean._latin_place(w))
    if not parts:
        return None
    parts.sort(key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)


class Recipe:
    """A checked recipe: prompt (filled), worries (names in order), words ({name: pattern or
    None}), unwinnable (names), fallback, capped ((name, pattern, most) a capped want, in order),
    capped_words ({name: its plain words}),
    sha (the file's first 12 hex of sha256), example (True when it is the example file)."""

    def __init__(self, data, sha="", example=False):
        bad = "the recipe: "
        if not isinstance(data, dict):
            raise hist.Refused(bad + "not a JSON object")
        prompt, worries = data.get("prompt"), data.get("worries")
        if not isinstance(prompt, str) or not 0 < len(prompt) <= MAX_PROMPT:
            raise hist.Refused(bad + f"prompt is text of at most {MAX_PROMPT} characters")
        missing = [k for k in ("{worries}", *KEYS) if k not in prompt]
        if missing:
            raise hist.Refused(bad + "prompt must hold " + ", ".join(missing))
        if not isinstance(worries, list) or not 2 <= len(worries) <= 12:
            raise hist.Refused(bad + "worries is a list of 2 to 12")
        names, words = [], {}
        for w in worries:
            name = w.get("name") if isinstance(w, dict) else None
            got = w.get("words", []) if isinstance(w, dict) else None
            if not isinstance(name, str) or not NAME.fullmatch(name) or name in names:
                raise hist.Refused(bad + "each worry has a new name of lower case letters and spaces")
            if not isinstance(got, list) or len(got) > MAX_WORDS or \
                    not all(isinstance(x, str) and 0 < len(x) <= MAX_WORD and x.isprintable() for x in got):
                raise hist.Refused(bad + f"each worry's words are at most {MAX_WORDS} plain words")
            names.append(name)
            words[name] = _words(got)
        unwinnable, fallback = data.get("unwinnable", []), data.get("fallback")
        if not isinstance(unwinnable, list) or not all(u in names for u in unwinnable):
            raise hist.Refused(bad + "unwinnable lists worry names only")
        if fallback not in names:
            raise hist.Refused(bad + "fallback is one of the worry names")
        self.capped = _capped(data.get("capped_wants", []), bad)
        # the plain words of each capped want: a grown pool keeps these and builds the pattern again
        self.capped_words = {c["name"]: list(c["words"]) for c in data.get("capped_wants", [])}
        self.worries = tuple(names)
        self.words = words
        self.unwinnable = frozenset(unwinnable)
        self.fallback = fallback
        self.prompt = prompt.replace("{worries}", ", ".join(names))
        self.sha, self.example = sha, example


def _capped(capped, bad):
    """The recipe's capped wants as ((name, pattern, most), ...); refused when not their shape."""
    if not isinstance(capped, list) or len(capped) > MAX_CAPPED:
        raise hist.Refused(bad + f"capped_wants is a list of at most {MAX_CAPPED}")
    out = []
    for c in capped:
        name, got, most = (c.get("name"), c.get("words"), c.get("most")) if isinstance(c, dict) else (None,) * 3
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in [n for n, _, _ in out]:
            raise hist.Refused(bad + "each capped want has a new name of lower case letters and spaces")
        if not isinstance(got, list) or not 0 < len(got) <= MAX_WORDS or \
                not all(isinstance(x, str) and 0 < len(x) <= MAX_WORD and x.isprintable() for x in got) or \
                _words(got) is None:
            raise hist.Refused(bad + f"each capped want has 1 to {MAX_WORDS} plain words")
        if isinstance(most, bool) or not isinstance(most, (int, float)) or not 0 < most < 1:
            raise hist.Refused(bad + "each capped want's most is a share above 0 and below 1")
        out.append((name, _words(got), float(most)))
    return tuple(out)


def load(path=None):
    """The recipe at path. No path is refused: the recipe is private and there is no default."""
    if not path:
        raise hist.Refused("the recipe: none given. The recipe is private; give your own file with --recipe "
                           f"(the shape: {EXAMPLE.relative_to(ROOT).as_posix()})")
    path = Path(path)
    if paths.inside_repo(path) and not _is_example(path):
        raise hist.Refused("the recipe: the file sits inside the repo, where it could be committed; keep your recipe "
                           "outside it (DECISIONS item 17). Only the example may sit there.")
    data = _read(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is None:
        raise hist.Refused("the recipe: not UTF-8 text")
    try:
        doc = hist.load_json(text)
    except hist.Refused as e:
        raise hist.Refused(f"the recipe: {e}") from None
    return Recipe(doc, hashlib.sha256(data).hexdigest()[:12], _is_example(path))


def _is_example(path):
    try:
        return os.path.samefile(path, EXAMPLE)
    except OSError:
        return False
