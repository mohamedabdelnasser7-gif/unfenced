"""New modes per user (new, 2026-10-31; spec section 3, DECISIONS items 35, 36).

During the day, a moment that fits no mode is noted (assistant/modes.py unfit). keep_moments adds
them to moments.jsonl in the assistant's state folder. At night, propose reads them: moments that
share a word, on at least MIN_DAYS days and MIN_MOMENTS times, become a candidate mode named by
that word (the user's own word, never a preset). arena_test plays the user's past days twice,
without and with the candidate, and counts the days it fixed and the days it broke, as the eval
gate does for lessons. A candidate that fixed at least one day and broke none becomes one card,
mode-<agent>-<run>.json next to the database: the Morning page's existing items are night reports
and Arena stuck items, so this card is a data file the page can read later (no page code changed
here). At most one card a night, the strongest, and none while one waits, so the page stays light.

The card holds data only (the name, its words, the counts and the choices yes, rename or drop);
the words the user reads are written when the page shows it, never fixed here (item 38).
answer_card applies the user's choice to the modes file (modes.json): yes or rename adds the mode,
drop keeps the name from coming back. A card with no answer changes nothing (item 35).
"""
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from assistant import modes as modes_mod

AGENT = "assistant"
MOMENTS_FILE, MODES_FILE = "moments.jsonl", "modes.json"
MIN_MOMENTS, MIN_DAYS = 3, 2
CHOICES = ("yes", "rename", "drop")
WORD = re.compile(r"[a-z][a-z']+")
NAME = re.compile(r"^[a-z]+( [a-z]+)?$")
STOP = {"i'm", "im", "i", "am", "the", "a", "an", "at", "now", "all", "day", "today", "this", "week", "right", "in",
        "on", "and", "to", "of", "for", "my", "is", "it", "be", "so", "mode", "with", "from", "just", "very"}
STEMS = ("ing", "ed", "s")


def keep_moments(state, moments):
    """Add the day's noted moments to moments.jsonl. Returns how many were added."""
    path = Path(state) / MOMENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for m in moments:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return len(moments)


def read_moments(state):
    path = Path(state) / MOMENTS_FILE
    out = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict) and isinstance(m.get("said"), str):
            out.append(m)
    return out


def _stem(w):
    for end in STEMS:
        if w.endswith(end) and len(w) - len(end) >= 4:
            return w[: -len(end)]
    return w


def _words(m):
    if m.get("named"):
        return {_stem(m["named"].casefold())}
    return {_stem(w) for w in WORD.findall(m["said"].casefold()) if w not in STOP}


def propose(moments, *, known=(), dropped=()):
    """Candidate modes, strongest first: [{"name", "words", "moments", "days"}]."""
    taken = {n.casefold() for n in (*modes_mod.DEFAULT, *known, *dropped)}
    by_word = defaultdict(list)
    for m in moments:
        for w in _words(m):
            by_word[w].append(m)
    out = []
    for w, ms in by_word.items():
        days = {m.get("date") for m in ms if m.get("date")}
        if w in taken or len(ms) < MIN_MOMENTS or len(days) < MIN_DAYS:
            continue
        said = sorted({x for m in ms for x in WORD.findall(m["said"].casefold()) if _stem(x) == w})
        out.append({"name": w, "words": said or [w], "moments": len(ms), "days": len(days)})
    out.sort(key=lambda c: (c["days"], c["moments"], c["name"]), reverse=True)
    return out


def arena_test(candidate, days, play):
    """play(day, added) -> won. Counts the past days the candidate fixed and broke."""
    added = [{"name": candidate["name"], "words": candidate["words"]}]
    fixed = broken = with_won = without_won = 0
    for day in days:
        a, b = bool(play(day, ())), bool(play(day, added))
        without_won += a
        with_won += b
        fixed += b and not a
        broken += a and not b
    return {"days": len(days), "without": without_won, "with": with_won, "fixed": fixed, "broken": broken,
            "passed": fixed >= 1 and broken == 0}


def write_card(folder, candidate, counts, *, now=None):
    """One mode card as a data file; returns its path."""
    now = time.time() if now is None else now
    run = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now))
    card = {"agent": AGENT, "kind": "mode_card", "at": now, "run": run, "name": candidate["name"],
            "words": candidate["words"], "moments": candidate["moments"], "days": candidate["days"],
            "arena": counts, "choices": list(CHOICES), "answer": None}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"mode-{AGENT}-{run}.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def read_modes(state):
    try:
        data = json.loads((Path(state) / MODES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"added": [a for a in data.get("added", []) if isinstance(a, dict) and isinstance(a.get("name"), str)],
            "dropped": [d for d in data.get("dropped", []) if isinstance(d, str)]}


def answer_card(card_path, state, choice, *, name=None, by):
    """The user's answer: yes, rename (with name) or drop. Returns the modes file's new content."""
    if choice not in CHOICES:
        raise ValueError(f"a mode card answer is one of {', '.join(CHOICES)}")
    card_path = Path(card_path)
    card = json.loads(card_path.read_text(encoding="utf-8"))
    if card.get("kind") != "mode_card" or card.get("answer") is not None:
        raise ValueError("not an open mode card")
    current = read_modes(state)
    if choice == "drop":
        current["dropped"].append(card["name"])
    else:
        new = (name or "").strip().casefold() if choice == "rename" else card["name"]
        if not NAME.match(new):
            raise ValueError("a mode name is a word or two, letters only")
        if new in {*modes_mod.DEFAULT, *(a["name"] for a in current["added"])}:
            raise ValueError(f"there is a mode {new!r} already")
        current["added"].append({"name": new, "words": card["words"]})
    path = Path(state) / MODES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
    card["answer"] = {"choice": choice, "name": name, "by": by, "at": time.time()}
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    return current


def night(state, days, play, *, reports=None, now=None):
    """The night's new mode step: propose from the kept moments, test the strongest that is new in
    the Arena on past days, and write at most one card. Returns the card's path or None."""
    folder = Path(reports or state)
    if open_cards(folder):
        return None
    current = read_modes(state)
    for cand in propose(read_moments(state), known=[a["name"] for a in current["added"]], dropped=current["dropped"]):
        counts = arena_test(cand, days, play)
        if counts["passed"]:
            return write_card(folder, cand, counts, now=now)
    return None


def open_cards(folder):
    """The mode cards in folder still waiting for an answer."""
    out = []
    for path in sorted(Path(folder).glob(f"mode-{AGENT}-*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(card, dict) and card.get("kind") == "mode_card" and card.get("answer") is None:
            out.append(path)
    return out
