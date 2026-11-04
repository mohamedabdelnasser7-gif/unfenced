"""Store offers, for every agent (decision 105, 2026-11-04).

A store's offers are data, never code: one line each (what it is, its terms, when it fits), plus the
numbers the totals need. The Sales agent's are in demo/offers.json; an agent made at Build keeps its own
in its folder, <db folder>/agents/<name>/offers.json, the same shape:

    {"max_stack": 1, "stack_counts": {kind: false}, "pick": "most_saved" or "listed",
     "apply": [kinds, in the order they are worked out], "round_to": 1,
     "payment_methods": [method ids], "offer_talk": [words that talk about an offer],
     "offers": [{"id", "kind", "what", "terms", "when", ...the kind's numbers..., "names", "covers"}]}

Kinds and the keys each reads:
- payment: method, and percent_off on the items when the order is paid that way (or none, months only).
- delivery: fee, the delivery fee whatever the zone (the days stay per zone).
- addon: free (what goes free, as line keys and values), with (the line that earns it), per_item (one free
  for each line unit that earns it, else one an order).
- nth_item: nth, percent_off, applies_to (the lines it counts), which ("cheaper" or "dearer" units get it),
  every_nth (every nth unit, else only one).
- choice: nothing to work out; a line the agent may offer (a cheaper option).
A line's keys are the store lines' own keys (type, tier, size); {"has": key} means the line has that key.

Totals (apply): each qualifying offer's saving is worked out alone. A kind whose stack_counts is false always
applies; the rest are cut to max_stack by pick (most saved first, a tie to the one listed first; or the
listed order). The kept offers are then worked out in the "apply" order, a payment percent on what the
items cost after the line offers before it. Each discount is rounded to round_to, half up.

Every value is untrusted: lines are plain and capped, numbers are checked, unknown keys are dropped, and the
file is read as text and parsed with json, never run. No store word is in this code: the code reads only
the keys above.
"""
import contextvars
import json
import os
import secrets
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from kit.sample import _key, line

FILE = "offers.json"
ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / FILE
MAX_BYTES = 32_000
MAX_OFFERS = 20
MAX_WORDS = 30         # names, covers, talk words in one list
MAX_WORD = 60
MAX_LINE = 200         # what, terms, when
MAX_METHODS = 8
MAX_MATCH = 6          # keys in a free, with or applies_to
MAX_STACK = 10

KINDS = ("payment", "delivery", "addon", "nth_item", "choice")
WORKED = ("addon", "nth_item", "payment", "delivery")   # the kinds apply works out, in the default order
PICKS = ("most_saved", "listed")
WHICH = ("cheaper", "dearer")
HAS = "has"
HIDDEN = ("names", "covers")   # never in a tool result: the words the send check reads

PROMPT_LINE = ("Offer only what a tool lists under offers, when its when line fits; never make up a discount, "
               "a percent or a payment method.")

# The offers of the agent this turn runs (kit/turn.py sets them, EMPTY when it has none). Unset means the
# Sales agent, whose offers are the store data's (demo/offers.json).
OFFERS = contextvars.ContextVar("offers", default=None)
EMPTY = {"max_stack": 1, "stack_counts": {}, "pick": "most_saved", "apply": list(WORKED), "round_to": 1,
         "payment_methods": [], "offer_talk": [], "offers": []}


class Refused(ValueError):
    """Offers that cannot be taken; the message says why in plain words, nothing was saved."""


# reading and cleaning

def _num(v, lo, hi, whole=False):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        d = Decimal(str(v).strip())
    except InvalidOperation:
        return None
    if not d.is_finite() or not lo <= d <= hi or (whole and d != d.to_integral_value()):
        return None
    return int(d) if d == d.to_integral_value() else float(d)


def _words(v, most=MAX_WORDS):
    out = []
    for w in v if isinstance(v, list) else []:
        w = line(w, MAX_WORD) if isinstance(w, (str, int, float)) and not isinstance(w, bool) else ""
        if w and w not in out:
            out.append(w)
        if len(out) >= most:
            break
    return out


def _keys(v, most=MAX_WORDS):
    out = []
    for w in v if isinstance(v, list) else []:
        k = _key(w) if isinstance(w, str) else ""
        if k and k not in out:
            out.append(k)
        if len(out) >= most:
            break
    return out


def _match(v):
    """A line match: {key: plain value}, or {"has": key}. None when nothing is left."""
    if not isinstance(v, dict):
        return None
    out = {}
    for k, val in list(v.items())[:MAX_MATCH * 2]:
        key = _key(k) if isinstance(k, str) else ""
        if key == HAS:
            val = _key(val) if isinstance(val, str) else ""
        elif isinstance(val, (str, int, float)) and not isinstance(val, bool):
            val = line(val, MAX_WORD)
        else:
            val = ""
        if key and val and len(out) < MAX_MATCH:
            out[key] = val
    return out or None


def _offer(raw):
    """One clean offer, or None when it has no plain what or no known kind."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind") if raw.get("kind") in KINDS else None
    what = line(raw.get("what") or "", MAX_LINE) if isinstance(raw.get("what"), str) else ""
    if not kind or not what:
        return None
    o = {"id": _key(raw["id"]) if isinstance(raw.get("id"), str) else "", "kind": kind, "what": what}
    for k in ("terms", "when"):
        if isinstance(raw.get(k), str) and line(raw[k], MAX_LINE):
            o[k] = line(raw[k], MAX_LINE)
    if isinstance(raw.get("method"), str) and _key(raw["method"]):
        o["method"] = _key(raw["method"])
    for k, lo, hi, whole in (("percent_off", 0, 100, False), ("months", 1, 120, True), ("fee", 0, 1e9, False),
                             ("nth", 2, 20, True)):
        n = _num(raw.get(k), lo, hi, whole)
        if n is not None and not (k == "percent_off" and n == 0):
            o[k] = n
    for k in ("free", "with", "applies_to"):
        m = _match(raw.get(k))
        if m:
            o[k] = m
    for k in ("per_item", "every_nth"):
        if isinstance(raw.get(k), bool):
            o[k] = raw[k]
    if raw.get("which") in WHICH:
        o["which"] = raw["which"]
    for k in ("names", "covers"):
        words = _words(raw.get(k))
        if words:
            o[k] = words
    return o


def clean(raw):
    """Offers data with every field checked and capped. raw is the whole data, or a list of offer lines
    (a Build card's), which get the defaults. Offers with no id get one from their place in the list."""
    if isinstance(raw, list):
        raw = {"offers": raw}
    if not isinstance(raw, dict):
        raw = {}
    out = json.loads(json.dumps(EMPTY))
    n = _num(raw.get("max_stack"), 1, MAX_STACK, whole=True)
    if n is not None:
        out["max_stack"] = n
    if isinstance(raw.get("stack_counts"), dict):
        out["stack_counts"] = {k: v for k, v in raw["stack_counts"].items() if k in KINDS and isinstance(v, bool)}
    if raw.get("pick") in PICKS:
        out["pick"] = raw["pick"]
    order = [k for k in dict.fromkeys(raw.get("apply") or []) if k in WORKED] if isinstance(raw.get("apply"), list) else []
    if order:
        out["apply"] = order
    r = _num(raw.get("round_to"), Decimal("0.01"), 1000)
    if r is not None:
        out["round_to"] = r
    out["payment_methods"] = _keys(raw.get("payment_methods"), MAX_METHODS)
    out["offer_talk"] = _words(raw.get("offer_talk"))
    offers, ids = [], set()
    for i, o in enumerate(raw.get("offers") if isinstance(raw.get("offers"), list) else []):
        if len(offers) >= MAX_OFFERS:
            break
        o = _offer(o)
        if o is None:
            continue
        o["id"] = o["id"] or f"offer_{i + 1}"
        if o["id"] in ids:
            continue
        ids.add(o["id"])
        offers.append(o)
    out["offers"] = offers
    return out


def read(folder_or_path):
    """The offers in a folder (its offers.json) or at a path, cleaned; None when there are none or the file
    cannot be read."""
    p = Path(folder_or_path)
    p = p / FILE if p.is_dir() and not p.is_symlink() else p
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(d, (dict, list)):
        return None
    got = clean(d)
    return got if got["offers"] or got["payment_methods"] else None


def text_of(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def write(folder, data):
    """The agent's offers written whole, cleaned: a hidden file first, renamed into place. Refused over
    MAX_BYTES or when the folder is not a plain folder."""
    folder = Path(folder)
    body = text_of(clean(data))
    if len(body.encode("utf-8")) > MAX_BYTES:
        raise Refused("That is more offers than one agent keeps. Send fewer.")
    target = folder / FILE
    if target.is_symlink() or folder.is_symlink() or not folder.is_dir():
        raise Refused("The agent's folder is not a plain folder, so no offers were saved.")
    tmp = folder / f".{FILE}.{secrets.token_hex(4)}.tmp"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)


_demo = {"data": None}


def demo():
    """The store data's offers (demo/offers.json), read once."""
    if _demo["data"] is None:
        _demo["data"] = read(DEMO) or json.loads(json.dumps(EMPTY))
    return _demo["data"]


def current():
    """The offers of the agent this turn runs: its own when kit/turn.py set them, else the store data's."""
    got = OFFERS.get()
    return demo() if got is None else got


def own():
    """The offers kit/turn.py set for this turn, or None (no fallback to the store data)."""
    return OFFERS.get()


# what tools and the send check read

def for_tool(data):
    """The offer lines a tool gives the model: no names or covers."""
    return [{k: v for k, v in o.items() if k not in HIDDEN} for o in (data or {}).get("offers", [])]


def limit_line(data):
    """How many offers one order takes, in plain words from the data's limit, or "" with no offers to limit."""
    data = data or {}
    counted = [o for o in data.get("offers", []) if o["kind"] in _worked(data) and o["kind"] != "choice"
               and data.get("stack_counts", {}).get(o["kind"], True)]
    if not counted:
        return ""
    n = data.get("max_stack", 1)
    head = "One offer an order" if n == 1 else f"At most {n} offers an order"
    picked = ("the one that saves the customer most applies" if n == 1 else "the ones that save the customer most apply") \
        if data.get("pick") == "most_saved" else ("the first listed applies" if n == 1 else "the first listed apply")
    on_top = [o["id"] for o in data.get("offers", []) if data.get("stack_counts", {}).get(o["kind"], True) is False]
    tail = f"; always on top: {', '.join(on_top)}" if on_top else ""
    return f"{head}: {picked}{tail}."


def mention_words(data):
    """{offer id: the words that name it}, the id's own words included."""
    return {o["id"]: list(dict.fromkeys([o["id"].replace("_", " "), *o.get("names", [])]))
            for o in (data or {}).get("offers", [])}


def talk_words(data):
    """The store data's words that talk about an offer at all (offer_talk)."""
    return list((data or {}).get("offer_talk", []))


def percents(data):
    """Every percent an offer gives, as Decimals."""
    return {Decimal(str(o["percent_off"])) for o in (data or {}).get("offers", []) if "percent_off" in o}


def payment_methods(data):
    return list((data or {}).get("payment_methods", []))


def delivery_fee(data, zone_fee):
    """The delivery fee after a delivery offer: the lowest of the zone's fee and any delivery offer's fee.
    The zone's fee as it was when there is no such offer."""
    fees = [o["fee"] for o in (data or {}).get("offers", []) if o["kind"] == "delivery" and "fee" in o]
    if not fees or zone_fee is None:
        return zone_fee
    low = min(fees)
    return low if _dec(low) < _dec(zone_fee) else zone_fee


def delivery_offer(data):
    """The delivery offer that sets the fee, or None."""
    return next((o for o in (data or {}).get("offers", []) if o["kind"] == "delivery" and "fee" in o), None)


# totals

def _dec(x):
    if isinstance(x, bool):
        raise ValueError("not an amount")
    try:
        d = Decimal(str(x).strip())
    except InvalidOperation:
        raise ValueError("not an amount") from None
    if not d.is_finite() or d < 0:
        raise ValueError("not an amount")
    return d


def _fold(v):
    return " ".join(str(v or "").casefold().split())


def matches(ln, want):
    """True when a line has every key and value of want ({"has": key} means the key is there and not empty)."""
    if not want:
        return False
    for k, v in want.items():
        if k == HAS:
            if not str(ln.get(v) or "").strip():
                return False
        elif _fold(ln.get(k)) != _fold(v):
            return False
    return True


def _units(lines, want):
    """The unit prices of every unit on the lines that match, one entry a unit."""
    out = []
    for ln in lines:
        if matches(ln, want):
            out += [_dec(ln["price"])] * int(ln.get("quantity", 1))
    return out


def _round(d, step):
    step = _dec(step)
    return (d / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


def _worked(data):
    return list(data.get("apply") or WORKED)


def _saving(o, lines, payment, base):
    """What one offer saves on its own (before rounding), base being what the items cost so far."""
    k = o["kind"]
    if k == "payment":
        if payment is None or o.get("method") != _key(str(payment)) or "percent_off" not in o:
            return Decimal(0)
        return base * _dec(o["percent_off"]) / 100
    if k == "addon":
        free = sorted(_units(lines, o.get("free")), reverse=True)
        earned = len(_units(lines, o.get("with"))) if o.get("per_item") else min(1, len(_units(lines, o.get("with"))))
        return sum(free[:earned], Decimal(0))
    if k == "nth_item":
        units = sorted(_units(lines, o.get("applies_to")), reverse=o.get("which") == "dearer")
        nth = o.get("nth", 2)
        count = len(units) // nth if o.get("every_nth") else min(1, len(units) // nth)
        if "percent_off" not in o:
            return Decimal(0)
        return sum(units[:count], Decimal(0)) * _dec(o["percent_off"]) / 100
    return Decimal(0)


def apply(lines, payment=None, data=None, fee=None):
    """The order's totals with the offers, in Decimal.

    lines: [{"price", "quantity", and the line's own keys (type, tier, size)}]. payment: the method id or None.
    fee: the delivery fee before offers, or None when no place is known yet.
    Returns {"subtotal", "discounts": [{"offer", "what", "discount"}], "fee", "total"}; fee and its part of
    the total only when a fee was given.
    """
    data = current() if data is None else data
    subtotal = sum((_dec(ln["price"]) * int(ln.get("quantity", 1)) for ln in lines), Decimal(0))
    order = _worked(data)
    step = data.get("round_to", 1)
    alone = []
    for i, o in enumerate(data.get("offers", [])):
        if o["kind"] not in order or o["kind"] == "delivery":
            continue
        s = _round(_saving(o, lines, payment, subtotal), step)
        if s > 0:
            alone.append((i, o, s))
    always = [a for a in alone if data.get("stack_counts", {}).get(a[1]["kind"], True) is False]
    counted = [a for a in alone if a not in always]
    if data.get("pick") == "most_saved":
        counted.sort(key=lambda a: (-a[2], a[0]))
    kept = {a[0] for a in always + counted[:int(data.get("max_stack", 1))]}
    discounts, base = [], subtotal
    for kind in order:
        for i, o in enumerate(data.get("offers", [])):
            if i not in kept or o["kind"] != kind:
                continue
            d = min(_round(_saving(o, lines, payment, base), step), base)
            if d > 0:
                discounts.append({"offer": o["id"], "what": o["what"], "discount": d})
                base -= d
    out = {"subtotal": subtotal, "discounts": discounts}
    total = base
    if fee is not None:
        out["fee"] = _dec(delivery_fee(data, fee))
        total += out["fee"]
    out["total"] = total
    return out
