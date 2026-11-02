"""The history importer: a brand's old chats, orders and delivery results written as Sales agent
cases, so the night study can read months of real results on its first night.

Not part of the demo flow. Every agent starts from zero and earns its lessons in the Arena, so
no lesson is mined from old chats before the Arena: arena/run.py refuses a database that holds
a lesson sourced from history rows. The Arena reads old chats only through arena/personas.py
(read_all below), for its practice customers and the replay.

    python3 -I reflection/importer.py --db PATH [--plug sales/plug.json] [--whatsapp DIR]
        [--instagram DIR] [--orders CSV] [--deliveries CSV] [--team NAME]... [--days 3]
        [--tz Africa/Cairo] [--pairs JSON] [--dry-run] [--json]

It reads the files (reflection/history.py, every file untrusted and capped), joins each order to
its chat and each order to its delivery result, and writes the three below, every text in them
masked first by one reflection/history.py Masker for the whole import (every name and order
name in it, joined or not; phones, emails, address numbers):
1. The chats store (kit/chats.py): one chat per export or Instagram thread, on the channel
   "history:whatsapp" or "history:instagram" so the live Sales agent never opens one, with
   every message as a step at its real past time, its text masked; a team message is a
   person's step.
2. The log the Sales agent writes (engine/log.py through the plug, as reflection/results.py
   record does), at real past times: person_replied for each team message, with its text and
   the customer's text before it, both masked; order_created for each joined order, its store
   "history" so a live courier result never lands on it; delivered or refused for its result.
   With no deliveries file no result is written and each order row says "result_unknown": under
   a plug that decides on delivered or refused the night study keeps those cases pending
   (engine/study.py settle), and the report says so. The Sales plug decides on order_created,
   so there the order row settles the case. A chat joined to no order gets chat_closed at its
   last message, since a past chat is over; an order with no result in a given deliveries file
   stays pending under a delivery plug, never a guessed loss: no timer settles a case
   (DECISIONS item 66). Every row's detail has "history": true, its source
   and a stable import key. Rows
   carry no lessons, and a trial never counts a history row (engine/trial.py).
3. Reply candidates (engine/humanizer.py): the team's text replies in chats that ended
   delivered, masked, at most PER_CASE a chat; one that gives an address or still calls
   someone by name after يا is left out. At most MAX_CANDIDATES waiting or refined at once (a
   rejected one holds no place). They are never used as they are. The demo humanizer runs on
   the ones waiting only when every input is under demo/history: it answers from the pairs in
   demo/history/humanizer.json and rejects any reply it has no pair for. On any other files no
   humanizer runs and the candidates wait. Nothing reads them into a prompt yet.
Importing the same files again adds nothing: every step, row and candidate has a key made from
its source, its chat and its own content, and a message's key names its sender, not whether
the sender is on the team, so a corrected --team list makes no second copy of a step. A row
timed after now or before 2000 is not written.
--dry-run reads and joins everything and opens no database. The report has counts only, never
a name, a phone or a message.
"""
import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I, as sim/run.py is
    sys.path.insert(0, str(ROOT))

from engine import humanizer as hum  # noqa: E402
from engine import plug as plug_mod  # noqa: E402
from engine.log import Log  # noqa: E402
from kit.chats import FIRST_STAGE, PERSON, Chats  # noqa: E402
from kit.db import Db  # noqa: E402
from reflection import history as hist  # noqa: E402

DAY = 86400
MIN_AT = 946_684_800.0      # 2000-01-01: a row before it is a bad date
MAX_CANDIDATES = 100        # reply candidates one agent keeps
PER_CASE = 3                # candidates from one chat
MIN_WORDS = 3
MAX_CANDIDATE_CHARS = 400
MAX_CUSTOMER_CHARS = 1000   # customer text kept on one row
MAX_PAIRS = 500
DEFAULT_PLUG = ROOT / "sales" / "plug.json"
DEFAULT_PAIRS = ROOT / "demo" / "history" / "humanizer.json"
NEEDED = ("person_replied", "order_created", "delivered", "refused")
STEPS = """
CREATE TABLE IF NOT EXISTS history_steps (
  key TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL REFERENCES chats (id),
  n INTEGER NOT NULL
);
"""


def key(*parts):
    """A stable import key: a hash of its parts."""
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]


# ---- reading

def read_all(reader, *, whatsapp=None, instagram=None, orders=None, deliveries=None, team=(), tz=hist.TZ,
             counts=None):
    """(chats, orders, deliveries). A file refused inside a folder is counted and skipped; a folder
    or a file given by name that is refused stops the import (hist.Refused, naming its kind)."""
    counts = Counter() if counts is None else counts
    chats, got_orders, got_deliveries = [], {}, {}
    if whatsapp:
        where = _given(hist.folder, whatsapp, "the WhatsApp folder")
        files = hist.entries(reader, where, hist.WHATSAPP, name=lambda n: n.lower().endswith(".txt"))
        for place, path in enumerate(files, 1):
            try:
                chat = hist.parse_whatsapp(reader.read(path), team, file_name=path.name, tz=tz, place=place,
                                           counts=counts)
                reader.count(len(chat.messages))
            except hist.Refused as e:
                reader.refuse(hist.WHATSAPP, str(e))
                continue
            chats.append(chat)
    if instagram:
        base = _given(hist.folder, instagram, "the Instagram folder")
        threads = [t for inbox in _inboxes(reader, base)
                   for t in hist.entries(reader, inbox, hist.INSTAGRAM, dirs=True)]
        for place, thread in enumerate(threads, 1):
            files = hist.entries(reader, thread, hist.INSTAGRAM, name=lambda n: re.fullmatch(r"message_\d{1,4}\.json", n))
            if not files:
                continue
            try:
                docs = [hist.load_json(reader.read(f)) for f in files]
                chat = hist.parse_instagram(docs, team, key=thread.name, place=place, counts=counts)
                reader.count(len(chat.messages))
            except hist.Refused as e:
                reader.refuse(hist.INSTAGRAM, str(e))
                continue
            chats.append(chat)
    if orders:
        got_orders = _given(lambda p: hist.parse_orders(reader.read(p), reader, tz=tz, counts=counts),
                            orders, "the orders file")
    if deliveries:
        got_deliveries = _given(lambda p: hist.parse_deliveries(reader.read(p), reader, tz=tz, counts=counts),
                                deliveries, "the deliveries file")
    return chats, got_orders, got_deliveries


def _given(fn, path, what):
    try:
        return fn(path)
    except hist.Refused as e:
        raise hist.Refused(f"{what}: {e}") from None


def _inboxes(reader, base):
    """messages/inbox under the download folder, and under your_instagram_activity/, no link followed."""
    out = []
    for parts in (("messages", "inbox"), ("your_instagram_activity", "messages", "inbox")):
        where = base
        for part in parts:
            try:
                st = os.lstat(where / part)
            except OSError:
                where = None
                break
            if stat.S_ISLNK(st.st_mode):
                reader.refuse(hist.INSTAGRAM, "a link")
                where = None
                break
            if not stat.S_ISDIR(st.st_mode):
                where = None
                break
            where = where / part
        if where is not None:
            out.append(where)
    return out


# ---- the plan: what would be written

def plan(chats, orders, deliveries, *, days=hist.JOIN_DAYS, now, counts):
    """[case] with its chat, steps, log rows and whether it ended delivered; nothing written."""
    joined, alone = hist.join(chats, orders, days)
    counts["orders with no chat"] += len(alone)
    counts["delivery rows with no order"] += len(set(deliveries) - set(orders))
    # one mask for the whole import: every name and order name in it, joined to the chat or not
    masker = hist.Masker({n for c in chats for n in c.names} | {n for o in orders.values() for n in o.names},
                         orders)
    cases = []
    for i, chat in enumerate(chats):
        case_id = "h" + key(chat.source, chat.key)[:31]
        order_names = joined.get(i, [])
        steps, rows, seen, before = [], [], Counter(), []
        for m in chat.messages:
            if not MIN_AT <= m.at <= now:
                counts["rows outside time"] += 1
                continue
            body = m.text if not m.media else f"[{m.media}]" + (" " + m.text if m.text else "")
            seen[(m.at, m.sender, body)] += 1  # by sender, not team or customer: a corrected team list keeps the key
            k = key("message", chat.source, chat.key, f"{m.at:.3f}", m.sender, body, seen[(m.at, m.sender, body)])
            text = masker(m.text) if m.text else ""
            steps.append({"key": k, "message": m, "text": text})
            counts["media markers"] += bool(m.media)
            counts["team messages" if m.team else "customer messages"] += 1
            if not m.team:
                before.append(f"[{m.media}]" + (" " + text if text else "") if m.media else text)
                continue
            detail = {"history": True, "source": chat.source, "import_key": k}
            if m.text:
                detail["reply"] = text
            if m.media:
                detail["media"] = m.media
            if before:
                detail["customer"] = "\n".join(before)[:MAX_CUSTOMER_CHARS]
                before = []
            rows.append({"key": k, "outcome": "person_replied", "at": m.at, "step": k, "detail": detail})
        good, placed = None, []
        for name in order_names:
            order = orders[name]
            if not MIN_AT <= order.at <= now:
                counts["rows outside time"] += 1
                continue
            placed.append(name)
            detail = {"history": True, "source": hist.ORDERS, "import_key": key("order", name), "order": name,
                      "store": "history"}
            if order.total is not None:
                detail["total"] = order.total
            if order.cancelled:
                detail["cancelled"] = True
            rows.append({"key": detail["import_key"], "outcome": "order_created", "at": order.at, "detail": detail,
                         "order": name})
            got = deliveries.get(name)
            if got is None:
                if not deliveries:  # no deliveries file: its result is not known (pending under a delivery plug)
                    detail["result_unknown"] = True
                counts["orders with no result"] += 1
                continue
            state, at, returned = got
            if not order.at <= at <= now:
                counts["rows outside time"] += 1
                continue
            detail = {"history": True, "source": hist.DELIVERIES, "import_key": key("result", name), "order": name}
            if returned:
                detail["returned"] = True
            rows.append({"key": detail["import_key"], "outcome": state, "at": at, "detail": detail, "order": name})
            counts[state] += 1
            counts["returned"] += returned
        if not order_names and steps:  # a past chat with no order is over: closed at its last message (item 66)
            k = key("closed", chat.source, chat.key)
            rows.append({"key": k, "outcome": "chat_closed", "at": steps[-1]["message"].at,
                         "detail": {"history": True, "source": chat.source, "import_key": k}})
        decided = sorted((r["at"], r["outcome"]) for r in rows if r["outcome"] in (hist.DELIVERED, hist.REFUSED))
        good = bool(decided) and decided[-1][1] == hist.DELIVERED
        counts["chats with an order" if placed else "chats with no order"] += 1
        counts["chats with no team reply"] += not any(s["message"].team for s in steps)
        cases.append({"chat": chat, "case": case_id, "orders": order_names, "steps": steps, "rows": rows,
                      "good": good})
    return cases


def candidates(cases, agent):
    """[(key, masked text, case id, source, at)]: the team's text replies in chats that ended
    delivered, masked, at most PER_CASE a chat, newest chats first, each text once. A reply
    that gives an address (hist.gives_address, on the text as written) or still calls someone
    by a name after يا (hist.calls_by_name, on the masked text) is left out."""
    out, seen = [], set()
    for case in sorted((c for c in cases if c["good"]), key=lambda c: -max((s["message"].at for s in c["steps"]),
                                                                             default=0)):
        taken = 0
        for s in case["steps"]:
            m = s["message"]
            if taken >= PER_CASE:
                break
            if not m.team or m.media or not m.text:
                continue
            text = " ".join(s["text"].split())
            bare = re.sub(r"\[(?:name|phone|order|number|email)\]", "", text)
            if len(re.findall(r"\w+", bare)) < MIN_WORDS or len(text) > MAX_CANDIDATE_CHARS:
                continue
            if hist.gives_address(m.text) or hist.calls_by_name(text):
                continue
            k = key("candidate", agent, text)
            if k in seen:
                continue
            seen.add(k)
            out.append((k, text, case["case"], case["chat"].source, m.at))
            taken += 1
    return out


# ---- writing

def _record(log, case, outcome, *, at, step=None, detail):
    """reflection/results.py Results.record with the row's real past time: an outcome that ends an
    action is saved with that action, the rest attach to the case. Never with lessons."""
    after = log.plug.result(outcome).after
    if after is not None:
        return log.act(case, after, result=outcome, step=step, detail=detail, at=at)
    return log.result(case, outcome, step=step, detail=detail, at=at)


def write(db, plug, cases, *, now, counts):
    """Write the cases; what is already there (by key) is left as it is."""
    log = Log(db, plug)
    Chats(db)  # makes the chats schema; history steps are written below with their own past times
    db.script(STEPS)
    with db.tx() as c:
        rows = c.execute("SELECT case_id, json_extract(detail, '$.import_key') AS k FROM trace WHERE agent = ? "
                         "AND json_valid(detail) AND json_extract(detail, '$.history') = 1", (plug.agent,)).fetchall()
        known = {r["k"]: r["case_id"] for r in rows}
        steps, team_side = {}, {}
        for r in c.execute("SELECT h.key, h.n, s.role FROM history_steps h LEFT JOIN steps s "
                           "ON s.chat_id = h.chat_id AND s.n = h.n"):
            steps[r["key"]], team_side[r["key"]] = r["n"], r["role"] == "assistant"
    for case in cases:
        if not case["steps"] and not case["rows"]:
            continue
        cid, chat = case["case"], case["chat"]
        times = [s["message"].at for s in case["steps"]] or [r["at"] for r in case["rows"]]
        with db.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO chats (id, channel, customer_id, stage, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)", (cid, "history:" + chat.source,
                                                          chat.phone or "unknown-" + cid[1:13], FIRST_STAGE,
                                                          min(times), max(times)))
            counts["chats written"] += cur.rowcount
            for s in case["steps"]:
                if s["key"] in steps:
                    if s["key"] in team_side and team_side[s["key"]] != s["message"].team:
                        counts["messages on the other side before"] += 1  # a corrected --team: a new database
                    continue
                m = s["message"]
                n = c.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM steps WHERE chat_id = ?", (cid,)).fetchone()[0]
                c.execute("INSERT INTO steps (chat_id, n, role, content, name, media, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (cid, n, "assistant" if m.team else "user", s["text"] or None, PERSON if m.team else None,
                           json.dumps([{"kind": m.media, "history": True}]) if m.media else None, m.at))
                c.execute("INSERT INTO history_steps (key, chat_id, n) VALUES (?, ?, ?)", (s["key"], cid, n))
                steps[s["key"]] = n
                counts["steps written"] += 1
        for r in case["rows"]:
            if r["key"] in known:
                counts["rows already there"] += 1
                continue
            target = cid
            if r["outcome"] in (hist.DELIVERED, hist.REFUSED):  # a result joins the chat its order is on
                target = known.get(key("order", r["order"]), cid)
            _record(log, target, r["outcome"], at=r["at"], step=steps.get(r.get("step")), detail=r["detail"])
            known[r["key"]] = target
            counts["rows written"] += 1


def load_pairs(reader, path):
    """The demo humanizer's pairs: {"pairs": [{"theirs": text, "ours": text}]}, capped."""
    data = hist.load_json(reader.read(path))
    pairs = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, list) or len(pairs) > MAX_PAIRS:
        raise hist.Refused(f"a pairs file is {{\"pairs\": [...]}} with at most {MAX_PAIRS}")
    out = []
    for p in pairs:
        if isinstance(p, dict) and isinstance(p.get("theirs"), str) and isinstance(p.get("ours"), str):
            out.append((p["theirs"], p["ours"]))
    return out


def clean(text):
    """The check on a refined reply: None when the masks find nothing in it (no phone, order
    number, long number, email or address number)."""
    return None if hist.mask(text) == text else "it names a phone, an order number, an email or an address number"


def demo_only(*paths):
    """True when at least one input was given and every one given is under demo/history (by
    device and inode, as the place check compares). Only then do the demo pairs run."""
    given = [p for p in paths if p]
    return bool(given) and all(hist.within(p, hist.ALLOWED) for p in given)


# ---- one import

def run(db_path, plug, *, whatsapp=None, instagram=None, orders=None, deliveries=None, team=(), days=hist.JOIN_DAYS,
        tz=hist.TZ, pairs=DEFAULT_PAIRS, humanizer=None, dry_run=False, now=None):
    """One import. Returns the report as plain data (counts only). humanizer: given in tests;
    otherwise the demo pairs humanizer from pairs, only when every input is under demo/history,
    or none (pairs None, or any input elsewhere: a real brand's candidates wait)."""
    for name in NEEDED:
        plug.result(name)
    now = time.time() if now is None else float(now)
    counts, reader = Counter(), hist.Reader()
    chats, got_orders, got_deliveries = read_all(reader, whatsapp=whatsapp, instagram=instagram, orders=orders,
                                                 deliveries=deliveries, team=team, tz=tz, counts=counts)
    cases = plan(chats, got_orders, got_deliveries, days=days, now=now, counts=counts)
    found = candidates(cases, plug.agent)
    times = [r["at"] for c in cases for r in c["rows"]]
    rep = {"agent": plug.agent, "dry_run": dry_run, "deliveries_file": bool(deliveries),
           "delivery_decides": bool({plug.decides.good, *plug.decides.bad} & {hist.DELIVERED, hist.REFUSED}),
           "read": {"whatsapp_chats": sum(c.source == hist.WHATSAPP for c in chats),
                    "instagram_chats": sum(c.source == hist.INSTAGRAM for c in chats),
                    "orders": len(got_orders), "delivery_rows": len(got_deliveries)},
           "not_read": [{"kind": k, "why": w, "files": n} for (k, w), n in sorted(reader.refused.items())],
           "window": None, "candidates": {"found": len(found), "cap": MAX_CANDIDATES}}
    if times:
        since = min(times)
        rep["window"] = {"since": since, "until": max(times) + 1, "days": math.ceil((now - since) / DAY) + 1}
    if not dry_run:
        if humanizer is None and pairs is not None and demo_only(whatsapp, instagram, orders, deliveries):
            humanizer = hum.Pairs(load_pairs(reader, pairs))  # read before anything is written
        db = Db(db_path)
        try:
            write(db, plug, cases, now=now, counts=counts)
            rep["candidates"].update(_candidates(db, plug, found, humanizer, now))
        finally:
            db.close()
    rep["counts"] = {k: counts[k] for k in sorted(counts)}
    return rep


def _candidates(db, plug, found, humanizer, now):
    store = hum.Candidates(db, plug.agent)
    held = len(store.mine(hum.WAITING)) + len(store.mine(hum.REFINED))  # a rejected one holds no place
    added = 0
    for k, text, case_id, source, at in found:
        if held + added >= MAX_CANDIDATES:
            break
        added += store.add(k, text, case_id=case_id, source=source, at=at, now=now)
    ran = Counter()
    if humanizer is not None:  # only on this import's texts: another import's waiting candidates get no answer
        mine = {text for _, text, *_ in found}
        ran = store.run(lambda text: humanizer(text) if text in mine else None, check=clean,
                        by=getattr(humanizer, "label", None) or type(humanizer).__name__, now=now)
    return {"added": added, "ran": dict(ran),
            "status": {s: len(store.mine(s)) for s in (hum.REFINED, hum.REJECTED, hum.WAITING)}}


# ---- the report

def text(rep, db_path="PATH"):
    """The report in plain lines: counts only."""
    c = Counter(rep["counts"])
    r = rep["read"]
    lines = [f'History import of {rep["agent"]}' + (" (a dry run: nothing written)" if rep["dry_run"] else ""),
             f'Read: {r["whatsapp_chats"]} WhatsApp chats, {r["instagram_chats"]} Instagram chats, {r["orders"]} orders, '
             f'{r["delivery_rows"]} delivery rows']
    for n in rep["not_read"]:
        lines.append(f'Not read: {n["files"]} {n["kind"]} file(s), {n["why"]}')
    lines += [f'Messages: {c["customer messages"]} from customers, {c["team messages"]} from the team, '
              f'{c["media markers"]} media markers; skipped {c["system lines"]} system lines, {c["bad lines"]} bad lines',
              f'Joined: {c["chats with an order"]} chats to an order, {c["chats with no order"]} chats with none; '
              f'{c["orders with no chat"]} orders with no chat',
              f'Results: {c["delivered"]} delivered, {c["refused"]} refused ({c["returned"]} of them returned); '
              f'{c["orders with no result"]} orders with no result, {c["delivery rows with no order"]} delivery rows '
              f'with no order, {c["bad rows"]} bad rows, {c["rows outside time"]} rows timed after now or before 2000']
    if not rep["deliveries_file"] and r["orders"] and rep.get("delivery_decides"):
        lines.append(f'No deliveries file: {c["orders with no result"]} orders stay pending, with no delivered or '
                     f'refused written for them')
    elif not rep["deliveries_file"] and r["orders"]:
        lines.append(f'No deliveries file: no delivered or refused written for {c["orders with no result"]} orders; '
                     f'this plug does not decide on them, so their cases do not wait')
    cand = rep["candidates"]
    if rep["dry_run"]:
        lines.append(f'Would write the chats, their steps and their log rows; found {cand["found"]} reply candidates '
                     f'(cap {cand["cap"]})')
    else:
        st = cand["status"]
        lines += [f'Written: {c["chats written"]} chats, {c["steps written"]} chat steps, {c["rows written"]} log rows; '
                  f'{c["rows already there"]} rows already there',
                  f'Reply candidates: {cand["added"]} new (cap {cand["cap"]}); {st["refined"]} refined, '
                  f'{st["rejected"]} rejected, {st["waiting"]} waiting']
        if c["messages on the other side before"]:
            lines.append(f'{c["messages on the other side before"]} messages were imported before on the other side '
                         f'(team or customer) and stay as they were; a corrected --team needs a new database')
    w = rep["window"]
    if w:
        lines.append(f'History window: {_day(w["since"])} to {_day(w["until"])}. To study it: '
                     f'python3 -m reflection.night --days {w["days"]} --db {db_path}')
    return "\n".join(lines)


def _day(t):
    return time.strftime("%d %b %Y", time.gmtime(t))


def main(argv=None, *, now=None):
    ap = argparse.ArgumentParser(prog="reflection/importer.py", description="Import a brand's old data as history cases.")
    ap.add_argument("--plug", default=str(DEFAULT_PLUG), help="the agent's plug file (default: the Sales agent's)")
    ap.add_argument("--db", required=True, help="the database to write")
    ap.add_argument("--whatsapp", help="a folder of WhatsApp chat exports, one .txt per chat")
    ap.add_argument("--instagram", help="an Instagram data download folder")
    ap.add_argument("--orders", help="a Shopify orders export (CSV)")
    ap.add_argument("--deliveries", help="a deliveries file in our format: order, state, date (CSV)")
    ap.add_argument("--team", action="append", default=[], help="a display name of the business's own side; repeat it")
    ap.add_argument("--days", type=int, default=hist.JOIN_DAYS, help="days after a chat's last customer message an "
                    "order may come and still join it (default 3)")
    ap.add_argument("--tz", default=hist.TZ, help="the time zone of the WhatsApp exports (default Africa/Cairo)")
    ap.add_argument("--pairs", default=str(DEFAULT_PAIRS), help="the demo humanizer's pairs (default demo/history)")
    ap.add_argument("--dry-run", action="store_true", help="read and join, write nothing")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    if not (args.whatsapp or args.instagram or args.orders or args.deliveries):
        ap.error("give at least one of --whatsapp, --instagram, --orders, --deliveries")
    if not 0 <= args.days <= 30:
        ap.error("--days is 0 to 30")
    try:
        ZoneInfo(args.tz)
    except (ValueError, KeyError):
        ap.error("--tz is a time zone name such as Africa/Cairo")
    try:
        rep = run(args.db, plug_mod.load(args.plug), whatsapp=args.whatsapp, instagram=args.instagram,
                  orders=args.orders, deliveries=args.deliveries, team=args.team, days=args.days, tz=args.tz,
                  pairs=args.pairs or None, dry_run=args.dry_run, now=now)
    except hist.Refused as e:
        print(f"Refused, nothing written: {e}", file=sys.stderr)
        return 2
    except ValueError as e:  # a plug that is wrong or lacks a result the import writes
        print(f"Stopped: {e}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=1) if args.json else text(rep, args.db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
