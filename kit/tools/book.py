"""book: a built agent books one of its sample rows (an apartment viewing, an appointment) at a date and time,
checked in code (2026-11-05).

kit/turn.py offers it to an agent with sample data (kit/sample.py) whose card books things (books(card): a need,
its case or its good result says book, viewing, appointment, reserve, slot or schedule). Before it, such an agent
had only the read-only data tool, so "booked" was only words.

A booking names a row by its name (the row's name or title column), a date (YYYY-MM-DD, or a weekday name for the
next such day from today) and a start (HH:MM; the end defaults to LENGTH minutes later). The code books it only
when:
  - the row exists and the date has not passed;
  - nothing booked for that row overlaps it: this chat's own earlier bookings (its tool rows), and in a live chat
    (the page chat, kit/turn.py turn bookings=) every booking any chat of this agent made (kit/bookings.py, the
    shared file beside the database). The read, the test and the write are one step under the file's lock.
Else it refuses, says why in plain words and names the next free time that day when there is one. Arena practice
hands no shared file, so a practice booking stays on the case's copy and never fills a real slot.

Which days and hours a row may be booked (a viewing_days or viewing_hours column, a move in date) is the agent's
to follow from its prompt and its rows, never checked here (Mohamed 2026-11-05).
Called with no start it gives today's date, the rows' names and the times already booked.
"""
import datetime as dt
import json
import re

from kit import bookings, sample
from kit.tools import mailbox

NAME = "book"
LENGTH = 30
MAX_ITEM = 120
MAX_WHO = 80
KEYS = ("item", "date", "start", "end", "who")
TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
NAME_KEYS = ("name", "title", "item", "product", "product_name", "unit", "listing", "property")
# The card words that say an agent books things (its needs, its case, its good result)
BOOK_WORDS = re.compile(r"\b(?:book\w*|viewings?|appointments?|reserv\w*|slots?|schedul\w*)\b", re.I)
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Book one of your rows (a viewing, an appointment) by its name at a date and a time. Sample data, nothing "
        "connected yet. The code refuses only a time another booking of that row overlaps, in any chat, and then "
        "says the next free time; which days and hours to offer is yours to follow from your instructions and the "
        "rows. With no start: today's date, the rows and the times already booked. Never say something is booked "
        "unless this tool booked it."),
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "The row's name, exactly as the data says it."},
            "date": {"type": "string", "description": "YYYY-MM-DD, or a weekday name for the next one; empty for today."},
            "start": {"type": "string", "description": "HH:MM, to book."},
            "end": {"type": "string", "description": f"HH:MM; empty for {LENGTH} minutes after the start."},
            "who": {"type": "string", "description": "Who it is for, a short line (a first name)."}},
        "additionalProperties": False,
    },
}}


def books(card):
    """True when the card's needs, its case or its good result say the agent books things."""
    if not isinstance(card, dict):
        return False
    case = card.get("case") if isinstance(card.get("case"), dict) else {}
    texts = [n.get("what", "") for n in card.get("needs", []) if isinstance(n, dict)]
    texts += [str(card.get("needs") if isinstance(card.get("needs"), str) else "")]
    texts += [str(case.get("output") or ""), str(case.get("ends") or ""), str(card.get("good") or "")]
    return any(BOOK_WORDS.search(t or "") for t in texts)


def _rows(ctx):
    return sample.rows_of(getattr(ctx, "data", None))


def row_name(row):
    for k in NAME_KEYS:
        if isinstance(row.get(k), str) and row[k].strip():
            return row[k].strip()
    return ""


def find(rows, item):
    """The row whose name is item (case and spaces aside), else the one row whose name holds it; None when none
    or more than one."""
    want = " ".join(item.split()).casefold()
    named = [(row_name(r).casefold(), r) for r in rows if row_name(r)]
    exact = [r for n, r in named if " ".join(n.split()) == want]
    if exact:
        return exact[0]
    near = [r for n, r in named if want and want in n]
    return near[0] if len(near) == 1 else None


def _day(text, today):
    """The date text names: YYYY-MM-DD, a weekday name (the next one from today, today included) or empty for
    today; None when it is neither."""
    text = (text or "").strip()
    if not text:
        return today
    if DATE.match(text):
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            return None
    w = text.lower().rstrip(".")
    if w[:3] in DAYS and DAY_NAMES[DAYS.index(w[:3])].lower().startswith(w):
        return today + dt.timedelta(days=(DAYS.index(w[:3]) - today.weekday()) % 7)
    return None


def own(ctx):
    """The bookings this chat made so far: each book tool row of the chat that says booked."""
    out = []
    try:
        steps = ctx.chats.steps(ctx.chat_id)
    except Exception:
        return out
    for s in steps:
        if s.get("role") != "tool" or s.get("name") != NAME:
            continue
        try:
            got = json.loads(s.get("content") or "null")
        except ValueError:
            continue
        if isinstance(got, dict) and got.get("ok") is True and isinstance(got.get("booked"), dict):
            out.append(got["booked"])
    return out


def check(args, ctx):
    extra = set(args) - set(KEYS)
    if extra:
        return False, f"Unknown arguments: {', '.join(sorted(extra))}. Only {', '.join(KEYS)} are allowed."
    for k in KEYS:
        if k in args and not isinstance(args[k], str):
            return False, f"{k} must be a string."
    if len(args.get("item") or "") > MAX_ITEM or len(args.get("who") or "") > MAX_WHO:
        return False, f"item is at most {MAX_ITEM} characters and who at most {MAX_WHO}."
    if _day(args.get("date"), dt.date(2026, 1, 1)) is None:
        return False, "date is YYYY-MM-DD or a weekday name."
    start, end = (args.get("start") or "").strip(), (args.get("end") or "").strip()
    if end and not start:
        return False, "To book, give a start (HH:MM)."
    if start:
        if not TIME.match(start) or (end and not TIME.match(end)):
            return False, "start and end are HH:MM."
        if end and bookings.minutes(start) >= bookings.minutes(end):
            return False, "It ends after it starts."
        if not (args.get("item") or "").strip():
            return False, "To book, name the row (item) as the data says it."
    return True, ""


def run(args, ctx):
    rows = _rows(ctx)
    path = getattr(ctx, "bookings", None)
    today = mailbox.now().date()
    out = {"ok": True, "about": "bookings of your rows", "data": sample.LABEL,
           "today": f"{today.isoformat()} ({DAY_NAMES[today.weekday()]})"}
    if not rows:
        return {"ok": False, "feedback": "This agent has no rows to book yet."}
    item = " ".join((args.get("item") or "").split())
    row = find(rows, item) if item else None
    if item and row is None:
        names = ", ".join(n for n in (row_name(r) for r in rows[:30]) if n)
        return {"ok": False, "feedback": f"Not booked: no row is called {item}. The rows are: {names}."}
    date = _day(args.get("date"), today)
    start = (args.get("start") or "").strip()
    taken = [dict(b, case=str(ctx.chat_id)) for b in own(ctx)] + bookings.read(path)
    if not start:
        picked = [row] if row is not None else rows[:30]
        names = {row_name(r).casefold() for r in picked}
        booked = sorted({(b["item"], b["date"], b["start"], b["end"]) for b in taken
                         if b.get("item", "").casefold() in names and b["date"] >= today.isoformat()})
        return dict(out, rows=[{"item": row_name(r)} for r in picked],
                    booked=[{"item": i, "date": d, "start": s, "end": e} for i, d, s, e in booked])
    name = row_name(row)
    s = bookings.minutes(start)
    end = (args.get("end") or "").strip() or bookings.hhmm(min(s + LENGTH, 24 * 60 - 1))
    e = bookings.minutes(end)
    day_name = DAY_NAMES[date.weekday()]
    why = None
    if date < today:
        why = f"{date.isoformat()} has passed; today is {today.isoformat()}"
    iso = date.isoformat()

    def clash(rows_):
        hit = bookings.overlaps(taken + rows_, iso, start, end, name)
        if hit is None:
            return None
        free = bookings.next_free(taken + rows_, iso, e - s, 0, 24 * 60, s, name)
        return (f"{name} is already booked on {day_name} {iso} from {hit['start']} to {hit['end']}"
                + (f"; the next free time that day is {free}" if free else "; that day has no free time left"))

    booking = {"item": name, "date": iso, "start": start, "end": end, "case": str(ctx.chat_id),
               "who": " ".join((args.get("who") or "").split())[:MAX_WHO]}
    if why is None and path is None:
        why = clash([])
    elif why is None:
        try:
            ok, got = bookings.add(path, booking, clash)
        except (bookings.Refused, OSError):
            ok, got = False, "the bookings could not be saved"
        if not ok:
            why = got
    if why:
        return {"ok": False, "feedback": f"Not booked: {why}. Pick another time.", "item": name, "date": iso,
                "data": sample.LABEL}
    booked = {"item": name, "date": iso, "day": day_name, "start": start, "end": end}
    note = ("Booked for every chat of this agent: no other booking of it overlaps this time."
            if path is not None else "Booked on this case's copy only (practice): no other booking here overlaps it.")
    return dict(out, booked=booked, note=note)
