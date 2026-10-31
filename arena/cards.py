"""Persona cards for the Arena (new, 2026-10-30): the tagged chats grouped by worry, one card a
group. The card holds the real data of a group of real customers (DECISIONS item 21).

A chat is unwinnable when its worry is on the recipe's unwinnable list (the example recipe:
just browsing) or the model says it has no budget. The worry words and their order come from
the recipe (arena/recipe.py).
Winnable chats group by worry; unwinnable ones by worry too, in their own groups, so "price"
and "price, no budget" are two cards. Each card: the group's wants and buy triggers (the
most common first, at most 3), its worry, patience (dodged answers taken before the chat
ended: median and most), style, how many chats it stands for and their share of every
tagged chat, its Arena weight and up to 4 cleaned example lines from its customers.

Style is counted in code from each customer's own messages; only numbers come out:
  length       the median words of a customer's text messages: short (up to 4), medium (5 to
               12) or long; the card gives the share of its chats in each band
  language     kit/send_check.py detect_script on each text message: Arabic, Franco or
               English; the card gives the mean share
  voice_notes  the share of a customer's messages that are voice notes, the card's mean
  opening      how the customer's first message opens: voice note, photo or link, price,
               size, availability, greeting or other; the card gives the share of its chats

Arena weight: how often the Arena draws the card. Unwinnable cards together get one in five
(UNWINNABLE_SHARE) unless the real share is known, from at least MIN_FOR_SHARE tagged
chats; then they get the real share. Inside each side a card's part follows its chats. No
card is made up: with no unwinnable chat there is no unwinnable card, and the summary says so.
Then each of the recipe's capped wants is held to its most share of the draws (cap_wants;
DECISIONS item 33: the name printing at most 25% of practice customers).
"""
import math
import re
import statistics
from collections import Counter

from kit import send_check
from reflection import history as hist
from arena import clean

UNWINNABLE_SHARE = 0.2
MIN_FOR_SHARE = 20
MAX_EXAMPLES = 4
TOP = 3
BANDS = ("short", "medium", "long")
LANGUAGES = ("arabic", "franco", "english")
OPENINGS = ("voice note", "photo or link", "price", "size", "availability", "greeting", "other")
OPEN_PRICE = re.compile(r"(?<!\w)(?:بكام|كام|سعر|السعر|price|how\s+much|bkam|b\s?kam|be\s?kam|el\s?se3r|se3r)(?!\w)",
                        re.IGNORECASE)
OPEN_SIZE = re.compile(r"(?<!\w)(?:مقاس|المقاس|size|ma2as)(?!\w)", re.IGNORECASE)
OPEN_AVAILABLE = re.compile(r"(?<!\w)(?:متاح[ةه]?|متوفر[ةه]?|موجود[ةه]?|عندكم|لسه|available|in\s+stock|mawgood|"
                            r"metaa7|mota7|3andko|3ndko|lessa|lsa)(?!\w)", re.IGNORECASE)
GREETING = re.compile(r"(?<!\w)(?:السلام|سلام|[اأ]هلا|هاي|هالو|مساء|صباح|hi|hello|hey|salam|ahlan|masa2|saba7)(?!\w)",
                      re.IGNORECASE)


# ---- style of one chat, counted in code

def style_of(chat):
    """{length band, language shares, voice note share, opening} of one chat's customer side."""
    mine = [m for m in chat.messages if not m.team]
    texts = [m.text for m in mine if m.text]
    words = [len(re.findall(r"\w+", t)) for t in texts]
    mid = statistics.median(words) if words else 0
    band = "short" if mid <= 4 else "medium" if mid <= 12 else "long"
    scripts = Counter(s for s in map(send_check.detect_script, texts) if s in LANGUAGES)
    total = sum(scripts.values())
    return {"length": band,
            "language": {k: (scripts[k] / total if total else 0.0) for k in LANGUAGES},
            "voice_notes": sum(m.media == "audio" for m in mine) / len(mine) if mine else 0.0,
            "opening": opening_of(mine[0]) if mine else "other"}


def opening_of(m):
    if m.media == "audio":
        return "voice note"
    if m.media or (m.text and clean.LINK.search(m.text)):
        return "photo or link"
    text = m.text or ""
    for kind, rx in (("price", OPEN_PRICE), ("size", OPEN_SIZE), ("availability", OPEN_AVAILABLE),
                     ("greeting", GREETING)):
        if rx.search(text):
            return kind
    return "other"


# ---- example lines

DIGIT_RUN = re.compile(r"\d(?:[\W_]{0,3}\d){4,}")


def example_ok(line):
    """A cleaned customer line fit to show: no placeholder left, 3 to 30 words, at most 200
    characters, no 5 digits in a row (up to 3 signs or spaces between them count as a row), no
    address, no word after يا that looks like a name and no listed first name. The line is
    read normalized (arena/clean.py normalize: no hidden marks, Western digits)."""
    if not isinstance(line, str) or not line:
        return False
    plain = clean.normalize(line)
    if clean.PLACEHOLDER.search(plain) or len(line) > 200 or DIGIT_RUN.search(plain):
        return False
    n = len(re.findall(r"\w+", plain))
    return (3 <= n <= 30 and not clean.gives_address(plain) and not hist.calls_by_name(plain)
            and not clean.has_name(plain))


def examples(items, rx=None):
    """Up to MAX_EXAMPLES lines from different chats: lines that name the worry (rx, the
    recipe's words for it) first."""
    picked = []
    for n, item in enumerate(items):
        lines = [" ".join(t["text"].split()) for t in item["turns"] if t["from"] == "customer" and t.get("text")]
        lines = [x for x in lines if example_ok(x)]
        if not lines:
            continue
        hit = next((x for x in lines if rx is not None and rx.search(x)), None)
        picked.append((hit is None, n, hit or lines[0]))
    out = []
    for _, _, line in sorted(picked):
        if line not in out:
            out.append(line)
        if len(out) >= MAX_EXAMPLES:
            break
    return out


# ---- the cards

def unwinnable_why(tags, recipe):
    if tags["worry"] in recipe.unwinnable:
        return tags["worry"]
    return "no budget" if tags["no_budget"] else None


def _shares(counter, keys, n):
    return {k: round(counter[k] / n, 2) if n else 0.0 for k in keys}


def card(items, worry, why, rx=None):
    """One card from the items of one group (each: label, tags, style, turns). rx: the
    recipe's words for the worry, to pick example lines."""
    n = len(items)
    tags = [i["tags"] for i in items]
    patience = [t["patience"] for t in tags]
    styles = [i["style"] for i in items]
    return {
        "worry": worry,
        "unwinnable": why is not None,
        "why_unwinnable": why,
        "want": [w for w, _ in Counter(t["want"].casefold() for t in tags).most_common(TOP)],
        "buy_trigger": [w for w, _ in Counter(t["buy_trigger"].casefold() for t in tags).most_common(TOP)],
        "patience": {"median": statistics.median(patience), "most": max(patience)},
        "style": {
            "length": _shares(Counter(s["length"] for s in styles), BANDS, n),
            "language": {k: round(sum(s["language"][k] for s in styles) / n, 2) for k in LANGUAGES},
            "voice_notes": round(sum(s["voice_notes"] for s in styles) / n, 2),
            "opening": _shares(Counter(s["opening"] for s in styles), OPENINGS, n),
        },
        "chats": n,
        "won": sum(i["label"] == "won" for i in items),
        "lost": sum(i["label"] == "lost" for i in items),
        "examples": examples(items, rx),
    }


def build(items, recipe):
    """(cards, info) from the tagged items. info has counts and shares only."""
    groups = {}
    for item in items:
        why = unwinnable_why(item["tags"], recipe)
        groups.setdefault((item["tags"]["worry"], why), []).append(item)
    place = {w: n for n, w in enumerate(recipe.worries)}
    order = sorted(groups, key=lambda k: (-len(groups[k]), k[1] is not None, place.get(k[0], 99), k[1] or ""))
    cards = []
    total = len(items)
    for n, key in enumerate(order, 1):
        c = {"id": f"persona-{n:02d}", **card(groups[key], *key, rx=recipe.words.get(key[0]))}
        c["share"] = round(c["chats"] / total, 3)
        cards.append(c)
    unwinnable = sum(c["chats"] for c in cards if c["unwinnable"])
    winnable = total - unwinnable
    real = round(unwinnable / total, 3) if total >= MIN_FOR_SHARE else None
    used = real if real is not None else UNWINNABLE_SHARE
    if not unwinnable:
        used = 0.0
    elif not winnable:
        used = 1.0
    for c in cards:
        side, pool = (used, unwinnable) if c["unwinnable"] else (1 - used, winnable)
        c["arena_weight"] = round(side * c["chats"] / pool, 3)
    capped = cap_wants(cards, recipe)
    if any(c.get("crossed") for c in capped):
        used = round(sum(c["arena_weight"] for c in cards if c["unwinnable"]), 3)
    info = {"cards": len(cards), "unwinnable_cards": sum(c["unwinnable"] for c in cards),
            "tagged_chats": total, "unwinnable_chats": unwinnable, "unwinnable_share_real": real,
            "unwinnable_share_used": used, "capped_wants": capped}
    return cards, info


def cap_wants(cards, recipe):
    """Hold each of the recipe's capped wants to its most share of the Arena's draws. A card is a
    capped want's when one of its wants holds one of that want's words (the customer who plays it
    is told every want on the card, arena/match.py). When those cards' weights add up to more than
    most, each is cut by the same factor (rounded down, so they stay at or under most), and the
    weight they give up goes to the cards under no capped want on the same side (winnable or
    unwinnable), by their weights, so the unwinnable share holds; to the other side's only when
    the side has none ("crossed"). With no card left to take it the weights stay ("held": false).
    Returns [{name, most, share_real, share_used}] in the recipe's order; weights change in place."""
    out = []
    capped = getattr(recipe, "capped", ())
    if not capped:
        return out

    def under(c, rx):
        return any(rx.search(w) for w in c["want"])
    free = [c for c in cards if not any(under(c, rx) for _, rx, _ in capped)]
    for name, rx, most in capped:
        mine = [c for c in cards if under(c, rx)]
        real = round(sum(c["arena_weight"] for c in mine), 3)
        rec = {"name": name, "most": most, "share_real": real, "share_used": real}
        out.append(rec)
        if real <= most:
            continue
        if not free:
            rec["held"] = False
            continue
        given = {}
        for c in mine:
            cut = math.floor(c["arena_weight"] * most / real * 1000 + 1e-9) / 1000  # 1e-9: 0.15 never reads 0.149
            given[c["unwinnable"]] = given.get(c["unwinnable"], 0.0) + c["arena_weight"] - cut
            c["arena_weight"] = cut
        for side, weight in sorted(given.items()):
            takers = [c for c in free if c["unwinnable"] == side]
            if not takers:
                takers, rec["crossed"] = free, True
            pool = sum(c["arena_weight"] for c in takers)
            for c in takers:
                part = c["arena_weight"] / pool if pool else 1 / len(takers)
                c["arena_weight"] = round(c["arena_weight"] + weight * part, 3)
        rec["share_used"] = round(sum(c["arena_weight"] for c in mine), 3)
    return out

