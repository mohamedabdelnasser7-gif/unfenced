"""Fact cards (call 10): a fact worked out from one plug's results only, for a person to keep
or dismiss.

A fact card is one plain fact read from an agent's own results, with the numbers behind it.
No model writes it, and nothing acts on it by itself: the morning page (reflection/morning.py)
shows each card with Keep and Dismiss, and each answer is one saved row in fact_answers with
the fact as shown, its numbers, who answered and when. A row is never changed or deleted. A
kept fact is shown on the page. No agent reads a fact, kept or not (see the end of this note).

Plug 1's fact, the Sales agent's delivery days. For each order delivered in the last 14 days:
the days from its order_created row to its delivered row, in the same chat and for the same
order number (with or without its #), the order placed at or before the delivery. The usual
days are the median. This week is the 7 days up to now and last week the 7 days before; a
delivery counts in the week its delivered row came in. They are grouped by zone, the delivery
data's area for the order's governorate, which the order_created row carries
(kit/tools/draft_order.py); orders whose row saved no zone are one group, "zone not saved". A
group gets a card only with at least MIN_RESULTS deliveries in each of the two weeks; with
fewer, there is no card. Rows imported from a business's past (reflection/importer.py, "history"
in their detail) are left out, so a fact comes from the agent's own new results. A group that
was answered, kept or dismissed, in the last 7 days gets no new card until those days pass.

How a kept fact would plug in (not done): kit/tools/delivery.py quote() takes a zone's days
only from the store's delivery data and reads no database. A kept fact could go beside them,
as the zone's latest kept fact from Facts.kept(), only a kept one and only from the last 7
days, with a line in sales/instructions.md on how to say it. It is left out because it
would change the days customers are told, which the Sales agent's own risk list marks high,
so it waits for Mohamed's call.
"""
import hashlib
import json
import statistics
import time

from engine.log import is_history
from kit.tools import store
from reflection import PLUG

DAY = 86400.0
WEEK = 7 * DAY
MIN_RESULTS = 5            # deliveries a group needs in each of the two weeks for a card
DELIVERY_DAYS = "delivery_days"
KEEP, DISMISS = "keep", "dismiss"
NO_ZONE = ""               # the key of the orders whose order_created row saved no zone
MAX_ZONE = 80              # characters; a longer zone is read as not saved
CHUNK = 500                # chats read at a time

SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_answers (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  fact TEXT NOT NULL,
  numbers TEXT NOT NULL,
  answer TEXT NOT NULL CHECK (answer IN ('keep', 'dismiss')),
  by TEXT NOT NULL CHECK (length(trim(by)) > 0),
  at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS fact_answers_latest ON fact_answers (agent, kind, key, id);
CREATE TRIGGER IF NOT EXISTS fact_answers_never_changed BEFORE UPDATE ON fact_answers
BEGIN SELECT RAISE(ABORT, 'a fact answer is never changed; add a new one'); END;
CREATE TRIGGER IF NOT EXISTS fact_answers_never_deleted BEFORE DELETE ON fact_answers
BEGIN SELECT RAISE(ABORT, 'a fact answer is never deleted'); END;
CREATE TRIGGER IF NOT EXISTS fact_answers_never_replaced BEFORE INSERT ON fact_answers
WHEN EXISTS (SELECT 1 FROM fact_answers WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'a fact answer is never replaced'); END;
"""


class Facts:
    """The fact cards of every agent that has a fact, and the answers to them."""

    def __init__(self, db):
        self.db = db
        self.db.script(SCHEMA)

    def cards(self, agent, now=None):
        """The agent's fact cards at `now`, worked out from its results, less the ones answered in
        the last 7 days. [] for an agent with no fact."""
        now = _now(now)
        make = MAKERS.get(agent)
        if make is None:
            return []
        with self.db.tx() as c:
            return [card for card in make(c, agent, now) if not _answered(c, agent, card["kind"], card["key"], now)]

    def answer(self, card, answer, by, now=None):
        """A person's Keep or Dismiss of a card as it was shown: one row with the fact, its
        numbers, who and when. Refused when the same fact was answered in the last 7 days.
        Returns the row id."""
        if answer not in (KEEP, DISMISS):
            raise ValueError(f"an answer is {KEEP} or {DISMISS}")
        if not isinstance(by, str) or not by.strip() or "\n" in by or "\r" in by:
            raise ValueError("by: the person, one line of text")
        now = _now(now)
        numbers = {k: card[k] for k in ("this", "last", "told", "until")}
        with self.db.tx() as c:
            if _answered(c, card["agent"], card["kind"], card["key"], now):
                raise ValueError("this fact was answered in the last 7 days")
            cur = c.execute("INSERT INTO fact_answers (agent, kind, key, fact, numbers, answer, by, at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (card["agent"], card["kind"], card["key"], card["fact"],
                             json.dumps(numbers, sort_keys=True), answer, by.strip(), now))
            return cur.lastrowid

    def kept(self, agent, kind=None):
        """The facts that stand for the agent: for each fact (kind and key), its latest answer when
        that answer is Keep, newest first. A Dismiss after a Keep takes the Keep back."""
        out = []
        for row in self.answers(agent, kind)[::-1]:
            if any((o["kind"], o["key"]) == (row["kind"], row["key"]) for o in out):
                continue
            out.append(row)
        return [row for row in out if row["answer"] == KEEP]

    def answers(self, agent, kind=None):
        """Every answer of the agent, oldest first: {id, kind, key, fact, numbers, answer, by, at}."""
        sql, args = "SELECT * FROM fact_answers WHERE agent = ?", [agent]
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        with self.db.tx() as c:
            rows = c.execute(sql + " ORDER BY id", args).fetchall()
        return [dict(r, numbers=json.loads(r["numbers"])) for r in rows]


def delivery_days(c, agent, now):
    """Plug 1's fact cards: the usual delivery days this week against last week, by zone (the
    module note). c: an open connection."""
    if not _has(c, "trace"):
        return []
    delivered = [_row(r) for r in c.execute(
        "SELECT case_id, at, detail FROM trace WHERE agent = ? AND result = 'delivered' AND at >= ? AND at < ? "
        "ORDER BY id", (agent, now - 2 * WEEK, now))]
    delivered = [r for r in delivered if not is_history(r)]
    placed = {}
    chats = sorted({r["case_id"] for r in delivered})
    for i in range(0, len(chats), CHUNK):
        part = chats[i:i + CHUNK]
        for r in c.execute("SELECT case_id, at, detail FROM trace WHERE agent = ? AND result = 'order_created' "
                           f"AND case_id IN ({', '.join('?' for _ in part)}) ORDER BY at, id", (agent, *part)):
            r = _row(r)
            if not is_history(r):
                placed.setdefault(r["case_id"], []).append(r)
    weeks = {}
    for d in delivered:
        ref = _ref((d["detail"] or {}).get("order"))
        order = next((o for o in placed.get(d["case_id"], [])
                      if ref is not None and _ref((o["detail"] or {}).get("order")) == ref and o["at"] <= d["at"]), None)
        if order is None:
            continue
        week = "this" if d["at"] >= now - WEEK else "last"
        weeks.setdefault(_zone(order["detail"]), {"this": [], "last": []})[week].append((d["at"] - order["at"]) / DAY)
    cards = []
    for zone in sorted(weeks):
        this, last = weeks[zone]["this"], weeks[zone]["last"]
        if len(this) < MIN_RESULTS or len(last) < MIN_RESULTS:
            continue  # too few results: no card
        card = {"agent": agent, "kind": DELIVERY_DAYS, "key": zone, "zone": zone or None,
                "this": _week(this), "last": _week(last), "told": _told(zone), "until": now}
        who = f"Orders to {zone}" if zone else "Orders whose zone was not saved"
        card["fact"] = (f"{who} usually took {days_text(card['this']['usual'])} to arrive this week, against "
                        f"{days_text(card['last']['usual'])} last week.")
        card["shown"] = shown(card)
        cards.append(card)
    return cards


MAKERS = {PLUG.agent: delivery_days}  # the agents that have a fact card, and how each is worked out


def shown(card):
    """A short digest of a card's fact and numbers, put in its form, so an answer is saved only
    for the fact the person saw."""
    data = json.dumps([card["agent"], card["kind"], card["key"], card["this"], card["last"], card["told"]],
                      sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def days_text(x):
    return f"{x:g} day" + ("" if x == 1 else "s")


def _week(days):
    return {"orders": len(days), "usual": round(statistics.median(days), 1), "fastest": round(min(days), 1),
            "slowest": round(max(days), 1)}


def _told(zone):
    """What the delivery data tells customers for this zone, as "1 to 2 days"; None when it has
    no days for it."""
    if not zone:
        return None
    try:
        found = next((z for z in store.delivery().get("zones", []) if z.get("area") == zone), None)
    except (OSError, ValueError, AttributeError):
        return None
    if not found or not all(isinstance(found.get(k), (int, float)) for k in ("days_min", "days_max")):
        return None
    return f"{found['days_min']:g} to {found['days_max']:g} days"


def _zone(detail):
    zone = (detail or {}).get("area")
    return zone.strip() if isinstance(zone, str) and 0 < len(zone.strip()) <= MAX_ZONE else NO_ZONE


def _ref(order):
    """An order number without its #, so #1001 and 1001 are one order; None when there is none."""
    if not isinstance(order, str) or not order.strip("# "):
        return None
    order = order.strip()
    return order[1:] if order.startswith("#") else order


def _answered(c, agent, kind, key, now):
    return c.execute("SELECT 1 FROM fact_answers WHERE agent = ? AND kind = ? AND key = ? AND at > ? LIMIT 1",
                     (agent, kind, key, now - WEEK)).fetchone() is not None


def _has(c, table):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def _row(r):
    d = dict(r)
    try:
        d["detail"] = json.loads(d["detail"]) if d["detail"] else None
    except ValueError:
        d["detail"] = None
    if not isinstance(d["detail"], dict):
        d["detail"] = None
    return d


def _now(now):
    return time.time() if now is None else float(now)
