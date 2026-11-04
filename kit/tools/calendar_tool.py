"""calendar: the personal assistant's calendar, with booking checked in code (decision 109).

Quick start's "calendar" key (reflection/quickstart.py TOOLS). It reads the user's demo calendar and rules
(assistant/demo/calendar.json, sample data, kit/sample.py LABEL, decision 107). Called with no start and no
end it gives the day's meetings and the user's rules. Called with a title, a start and an end (HH:MM, on date,
which defaults to today, the calendar's first day) it books the meeting only when the code finds no clash with any
meeting that day and no broken rule (no meetings before or after the user's hours), the same test the
assistant's desk makes (assistant/desk.py _book); else it refuses and says why, so a clash or a broken rule
can never be booked.

The sample calendar is moved onto today whenever it is read, the way the mailbox is (kit/tools/mailbox.py
onto_today): every meeting moves by the whole number of days that puts its first day on today, the date the
mailbox names as today, so "today's meetings" and "book it tomorrow" read the same day as the mail. Each answer
says that date (today).

A booking is on this case's copy of the calendar only: the meetings booked earlier in the same chat (its own
tool rows, kit/chats.py steps) count as taken, and the demo file is never written.
"""
import datetime as dt
import json
import re
from pathlib import Path

from kit import sample
from kit.tools import mailbox

NAME = "calendar"
DEMO = Path(__file__).resolve().parent.parent.parent / "assistant" / "demo" / "calendar.json"
TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
MAX_TITLE = 120
KEYS = ("date", "title", "start", "end")
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "The user's calendar and rules (sample data, nothing connected yet). With no start and no end: the day's "
        "meetings and the user's rules. With a title, a start and an end (HH:MM): book that meeting, which the code "
        "does only when it clashes with nothing and keeps the user's rules; else it says why it was not booked."),
    "parameters": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD; empty for today."},
            "title": {"type": "string", "description": "The meeting's title, to book."},
            "start": {"type": "string", "description": "HH:MM, to book."},
            "end": {"type": "string", "description": "HH:MM, to book."}},
        "additionalProperties": False,
    },
}}


def minutes(hhmm):
    m = TIME.match(hhmm)
    return int(m.group(1)) * 60 + int(m.group(2))


def demo():
    """(user, rules, events) of the demo calendar."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    return str(d.get("user") or ""), dict(d.get("rules") or {}), list(d.get("events") or [])


def moved(events, at=None):
    """events with each date moved by the whole days that put the first event's day on today (mailbox.onto_today,
    at the mailbox's clock when at is None); a date that is not a date stays."""
    if not events:
        return []
    days = mailbox.onto_today(events[0].get("date"), at)
    out = []
    for e in events:
        try:
            date = (dt.date.fromisoformat(str(e.get("date"))) + dt.timedelta(days=days)).isoformat()
        except ValueError:
            date = e.get("date")
        out.append(dict(e, date=date))
    return out


def booked(ctx):
    """The meetings this chat booked so far: each calendar tool row of the chat that says booked."""
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
    date = (args.get("date") or "").strip()
    if date and not DATE.match(date):
        return False, "date is YYYY-MM-DD."
    start, end = (args.get("start") or "").strip(), (args.get("end") or "").strip()
    if bool(start) != bool(end):
        return False, "To book, give both a start and an end (HH:MM)."
    if start:
        if not TIME.match(start) or not TIME.match(end):
            return False, "start and end are HH:MM."
        if minutes(start) >= minutes(end):
            return False, "A meeting ends after it starts."
        title = (args.get("title") or "").strip()
        if not title or len(title) > MAX_TITLE:
            return False, f"To book, give a title of at most {MAX_TITLE} characters."
    return True, ""


def run(args, ctx):
    _, rules, events = demo()
    at = mailbox.now()
    events = moved(events, at)
    date = (args.get("date") or "").strip() or (events[0].get("date") if events else "")
    day = [e for e in events if e.get("date") == date] + [b for b in booked(ctx) if b.get("date") == date]
    start, end = (args.get("start") or "").strip(), (args.get("end") or "").strip()
    out = {"ok": True, "about": "the user's calendar", "data": sample.LABEL, "today": mailbox.today(at), "date": date,
           "rules": rules}
    if not start:
        return dict(out, meetings=day)
    s, e = minutes(start), minutes(end)
    before, after = rules.get("no_meetings_before"), rules.get("no_meetings_after")
    why = None
    if before and s < minutes(before):
        why = f"the user's rule: no meetings before {before}"
    elif after and e > minutes(after):
        why = f"the user's rule: no meetings after {after}"
    else:
        hit = next((m for m in day if s < minutes(m["end"]) and minutes(m["start"]) < e), None)
        if hit is not None:
            why = f"it clashes with {hit.get('title') or hit.get('id')} ({hit['start']} to {hit['end']})"
    if why:
        return {"ok": False, "feedback": f"Not booked: {why}. Pick another time.", "date": date, "meetings": day,
                "rules": rules, "data": sample.LABEL}
    meeting = {"id": f"b{len(day) + 1}", "date": date, "title": " ".join(args["title"].split()), "start": start,
               "end": end, "by": "assistant"}
    return dict(out, booked=meeting, note="Booked on this case's copy of the calendar: no clash, inside the rules.")
