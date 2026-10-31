"""The Arena replay of real lost chats (new, 2026-10-30; DECISIONS items 4 and 21).

After the Sales agent wins its persona matches, it replays old chats that were lost and tries
to close them. The chats are the persona build's replay set (arena/personas.py writes
replay.jsonl next to the cards: every won and lost chat, cleaned, each {id, label, why, source,
worry, turns[{from, text, media, min}]}). Only the lost ones are played.

For each lost chat: the opening is the customer's own words before the store's first reply
(several lines joined, one message, media left out); the persona is the card with the chat's
worry (a card that can buy first, then the heaviest, then by id). The Sales agent answers that
opening and the persona goes on from there, through the same match as the persona matches
(arena/match.py), scored with the same fact checks and verdict, and counted against the same
model call cap. A chat is skipped, never guessed, when it has no worry tag, no card with its
worry, only a card that will not buy, or no customer words before the store's first reply.

Cleaned real chat lines (names, numbers and addresses removed) may sit in the repo (DECISIONS
item 23; only the original lines stay out): arena/real/replay.jsonl is the cleaned replay set.
load() still refuses a file inside the repo, so a run names a copy outside it. The tests use the
set built from the made-up chats (demo/make_arena_history.py) and never read arena/real/.
"""
import json
from pathlib import Path

from arena import label, paths

ROOT = Path(__file__).resolve().parent.parent
MAX_REPLAYS = 10
MAX_BYTES = 20_000_000
NO_WORRY = "no worry tag"
NO_CARD = "no card with its worry"
WILL_NOT_BUY = "its card will not buy"
NO_OPENING = "no customer words before the store's first reply"


class Refused(ValueError):
    pass


def load(path):
    """The replay set's entries, in file order. Refuses a file inside the repo."""
    p = Path(path).expanduser().resolve()
    if paths.inside_repo(p):
        raise Refused("the replay set sits inside the repo; keep real chats outside it (DECISIONS item 17)")
    if not p.is_file():
        raise Refused("the replay set is not a regular file")
    if p.stat().st_size > MAX_BYTES:
        raise Refused(f"the replay set is over {MAX_BYTES} bytes")
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            raise Refused(f"replay line {n} is not JSON") from None
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not isinstance(e.get("turns"), list):
            raise Refused(f"replay line {n}: an entry is an object with an id and turns")
        out.append(e)
    return out


def opening(entry):
    """The customer's words before the store's first reply, one message; "" when there are none."""
    lines = []
    for t in entry.get("turns") or []:
        if not isinstance(t, dict):
            continue
        if t.get("from") == "store":
            break
        text = t.get("text")
        if t.get("from") == "customer" and isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return "\n".join(lines)


def persona(entry, cards):
    """(the card for the chat, None) or (None, why it is skipped)."""
    worry = entry.get("worry")
    if not isinstance(worry, str) or not worry:
        return None, NO_WORRY
    same = [c for c in cards if c.get("worry") == worry]
    if not same:
        return None, NO_CARD
    buyers = [c for c in same if not c.get("unwinnable")]
    if not buyers:
        return None, WILL_NOT_BUY
    buyers.sort(key=lambda c: (-float(c.get("arena_weight") or 0), str(c.get("id"))))
    return buyers[0], None


def plan(entries, cards, most=MAX_REPLAYS):
    """The lost chats to play, [(entry, card, opening)], at most `most`, spread evenly over the
    file, and {why: count} of the lost chats skipped."""
    ready, skipped = [], {}
    for e in entries:
        if e.get("label") != label.LOST:
            continue
        card, why = persona(e, cards)
        first = opening(e) if card is not None else ""
        if card is not None and not first:
            why = NO_OPENING
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        ready.append((e, card, first))
    if most is not None and len(ready) > most:
        ready = [ready[i * len(ready) // most] for i in range(most)]
    return ready, skipped
