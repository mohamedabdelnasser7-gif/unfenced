"""Which practice customers an offer meets (decision 105, 2026-11-04), in code, 0 model calls.

A practice card keeps its real voice and worry from real chats; whether it can buy now comes from the
agent's offers (kit/offers.py), not from the old buy rate. cover(card, data) reads the card's buy
triggers, each as "any one of these is enough", and the covers words of every offer: a card whose
trigger holds an offer's covers word is covered by that offer, and a win is a sale; a card no offer
covers (and not told it will never buy) is a close card: it still plays the gate at its real share and
wins on a correct close (arena/close.py, arena/good.py close_case), never studied as a loss.

Words compare folded the way delivery places are (kit/tools/delivery.py tokens: lowercase, Arabic
letter forms folded, the article dropped, doubled Latin letters made one), a covers word matching
when its words come in a row in the trigger; a Latin word also matches with a plural s, an Arabic one
with one of the joined letters before it. With no offers at all nothing is marked a close card, so an
agent with no offers plays as before.

A store pre-order rule (decision 108, kit/offers.py preorder) covers a card too: one whose want or buy
trigger holds one of the rule's covers words ("sold out"), or whose want names a size that every product it
names (any product when it names none) has only out in the store, can buy through a pre-order.

mark(cards, data) sets "covered_by" (the offers' what lines) and "close" on each card in place.
team_rate(cards) is the store team's real rate on the cards: the chats they won of the chats they had,
shown as a report line only; the gate's bar stays as the trust level sets it.
"""
import re

from kit import offers as kit_offers
from kit.tools import store
from kit.tools.delivery import AR_PREFIX, tokens

SIZE = re.compile(r"(?<!\d)(\d{2})(?!\d)")

TEAM_LINE = ("The store team's real rate on these customers: {won} of {chats} chats. "
             "Report only; the bar stays {wins} of {matches}.")


def _variants(tok):
    """The ways a trigger word may hold a covers word: as it is, without a plural s, without one joined letter."""
    out = {tok}
    if tok.isascii() and len(tok) > 3 and tok.endswith("s"):
        out.add(tok[:-1])
    if not tok.isascii() and len(tok) > 3 and tok[0] in AR_PREFIX:
        out.add(tok[1:])
    return out


def _holds(trigger, word):
    """True when the covers word's tokens come in a row in the trigger's tokens."""
    want = tokens(word)
    if not want:
        return False
    have = [_variants(t) for t in trigger]
    for i in range(len(have) - len(want) + 1):
        if all(w in have[i + j] for j, w in enumerate(want)):
            return True
    return False


def _triggers(card):
    got = card.get("buy_trigger") if isinstance(card, dict) else None
    if isinstance(got, str):
        got = [got]
    return [tokens(t) for t in got or [] if isinstance(t, str) and t.strip()]


def _wants(card):
    got = card.get("want") if isinstance(card, dict) else None
    return [got] if isinstance(got, str) else [w for w in got or [] if isinstance(w, str) and w.strip()]


def wants_out(card):
    """True when the card's want names a size (a two digit number) that the products it names, in the tiers it
    names, have only out in the store (any product or tier when it names none), and at least one has that size."""
    try:
        items = store.catalogue()
    except Exception:
        return False
    from arena import factcheck   # imported here to keep this module's imports light
    for want in _wants(card):
        named = factcheck.products_named(want, items) or items
        tiers = factcheck.tiers_named(want, store.tiers())
        for n in SIZE.findall(want):
            sized = [v for i in named for v in factcheck._of_tiers(i.get("variants", []), tiers)
                     if str(v.get("size", "")).split(" (")[0] == n]
            if sized and all(v.get("stock") == "out" for v in sized):
                return True
    return False


def cover(card, data):
    """{"covered_by": [the what of each offer a buy trigger meets, and of the pre-order rule for a card that
    wants an out of stock size], "close": True for a card nothing covers that is not told it will never buy}.
    No offers and no pre-order rule: nothing covered and no close card."""
    offers = [o for o in (data or {}).get("offers", []) if isinstance(o, dict)]
    rule = kit_offers.preorder(data)
    if not offers and not rule:
        return {"covered_by": [], "close": False}
    triggers = _triggers(card)
    by = []
    for o in offers:
        words = [w for w in o.get("covers") or [] if isinstance(w, str)]
        if any(_holds(t, w) for t in triggers for w in words) and o.get("what") not in by:
            by.append(o.get("what") or o.get("id"))
    if rule:
        said = triggers + [tokens(w) for w in _wants(card)]
        words = [w for w in rule.get("covers") or [] if isinstance(w, str)]
        if (any(_holds(t, w) for t in said for w in words) or wants_out(card)) and rule["what"] not in by:
            by.append(rule["what"])
    return {"covered_by": by, "close": not by and not card.get("unwinnable")}


def mark(cards, data):
    """Sets covered_by and close on each card in place (cover); returns the cards."""
    for c in cards or ():
        if isinstance(c, dict):
            c.update(cover(c, data))
    return cards


def current():
    """The offers the Sales Arena marks its cards with: the store data's (kit/offers.py current)."""
    return kit_offers.current()


def team_rate(cards):
    """{"won", "chats"}: the real chats the cards stand for that the store team won, of all of them."""
    won = chats = 0
    for c in cards or ():
        try:
            w, n = int(c.get("won") or 0), int(c.get("chats") or 0)
        except (TypeError, ValueError):
            continue
        if w >= 0 and n >= 0:
            won, chats = won + w, chats + n
    return {"won": won, "chats": chats}


def team_line(rate, wins, matches):
    """The report line for team_rate, or "" when the cards count no chats."""
    if not rate or not rate.get("chats"):
        return ""
    return TEAM_LINE.format(won=rate["won"], chats=rate["chats"], wins=wins, matches=matches)
