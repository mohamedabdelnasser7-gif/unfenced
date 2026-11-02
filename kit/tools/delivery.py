"""delivery: the delivery fee and days for the customer's governorate.

The place can come in Arabic, English or Franco ("الجيزة", "Giza", "el giza"). Each of
Egypt's 27 governorates is in demo/governorates.json with its spellings and its zone; the
fee and days come only from the zone in the delivery data, never from the model.

A place that matches no governorate, or more than one, comes back with ok false and a
note asking which governorate. Cities and districts are not in the list yet.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from kit.tools import store

ROOT = Path(__file__).resolve().parents[2]
GOVERNORATES = ROOT / "demo" / "governorates.json"
MAX_PLACE = 120

NAME = "delivery"
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Get the delivery fee and delivery days for the customer's governorate (محافظة). "
        "Pass the place as the customer wrote it, in Arabic, English or Franco."),
    "parameters": {
        "type": "object",
        "properties": {"governorate": {
            "type": "string", "description": "The governorate as the customer wrote it, for example الجيزة, Alex or eskendereya."}},
        "required": ["governorate"],
        "additionalProperties": False,
    },
}}

ASK_WHICH = "Ask the customer which governorate (محافظة) they are in."

# Spellings are compared after folding: Arabic letter forms, the article, doubled Latin letters.
AR_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
AR_MARKS = re.compile("[ؐ-ًؚ-ٰٟـ]")
TOKEN = re.compile(r"[a-z0-9ء-ي]+")
AR_ARTICLE = re.compile(r"^(?:و|ف)?(?:بال|كال|لل|ال)(?=[ء-ي]{2})")
AR_PREFIX = "بلوف"
LATIN_ARTICLES = frozenset({"el", "al", "l"})


def check(args, ctx):
    extra = set(args) - {"governorate"}
    if extra:
        return False, f"Unknown arguments: {', '.join(sorted(extra))}. Only governorate is allowed."
    place = args.get("governorate")
    if not isinstance(place, str) or not place.strip():
        return False, "Give the governorate the customer wrote."
    if len(place) > MAX_PLACE:
        return False, f"governorate must be a short place name, {MAX_PLACE} characters at most."
    return True, ""


def run(args, ctx):
    return quote(args["governorate"])


def quote(place):
    """The delivery result for a place: fee and days from the data, or ok false with a note."""
    found = find(place)
    if not found:
        return {"ok": False, "note": f"No Egyptian governorate matched that place. {ASK_WHICH}"}
    if len(found) > 1:
        names = ", ".join(g["name"] for g in found)
        return {"ok": False, "note": f"That matches more than one governorate ({names}). {ASK_WHICH}"}
    gov = found[0]
    zone = next((z for z in store.delivery().get("zones", []) if z.get("area") == gov["zone"]), None)
    if zone is None or not all(k in zone for k in ("fee", "days_min", "days_max")):
        return {"ok": False, "note": "The delivery data has no fee for this governorate."}
    return {"ok": True, "governorate": gov["name"], "governorate_ar": gov["name_ar"], "area": zone["area"],
            "fee": zone["fee"], "days_min": zone["days_min"], "days_max": zone["days_max"]}


def find(place):
    """Every governorate named in the text, in order, each once."""
    toks = tokens(place)
    idx = _index()
    longest = max(len(k) for k in idx)
    hits, i = [], 0
    while i < len(toks):
        for n in range(min(longest, len(toks) - i), 0, -1):
            gov = _lookup(idx, toks[i:i + n])
            if gov:
                hits.append(gov)
                i += n
                break
        else:
            i += 1
    by_name = {g["name"]: g for g in _data()["governorates"]}
    return [by_name[n] for n in dict.fromkeys(hits)]


def tokens(text):
    """The words of a place, folded so spellings compare: lowercase, no article, no doubled Latin letters."""
    text = AR_MARKS.sub("", (text or "").lower().translate(AR_FOLD))
    out = []
    for tok in TOKEN.findall(text):
        if tok in LATIN_ARTICLES:
            continue
        if re.match(r"[a-z0-9]", tok):
            tok = re.sub(r"([a-z])\1+", r"\1", tok)
        else:
            tok = AR_ARTICLE.sub("", tok)
        out.append(tok)
    return tuple(out)


def _lookup(idx, key):
    if key in idx:
        return idx[key]
    first = key[0]
    if first[0] in AR_PREFIX and len(first) > 3:  # بسوهاج, لسوهاج: a one-letter prefix with no article
        return idx.get((first[1:],) + key[1:])
    return None


@lru_cache(maxsize=1)
def _data():
    return json.loads(GOVERNORATES.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _index():
    """Folded spelling -> governorate name. A spelling shared by two governorates is an error in the data."""
    idx = {}
    for g in _data()["governorates"]:
        for s in (g["name"], g["name_ar"], *g["spellings"]):
            key = tokens(s)
            if key and idx.setdefault(key, g["name"]) != g["name"]:
                raise ValueError(f"the spelling {s!r} names two governorates")
    return idx
