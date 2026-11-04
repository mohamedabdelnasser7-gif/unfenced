"""One agent's shared bookings, kept beside the database (2026-11-05).

A booking made in one chat used to live only on that chat's copy (its own tool rows), so a new chat (Start over on
the agent's page, a new customer) could book the same slot again. Every booking a live chat of an agent makes now
goes to one file in the agent's own folder, <db folder>/agents/<agent>/bookings.json:

    {"bookings": [{"item", "date", "start", "end", "case", "who", "at"}]}

item is what is booked (an apartment's name; "" for the assistant's calendar, where every meeting takes the whole
calendar), date YYYY-MM-DD, start and end HH:MM, case the chat that booked it, who a short line on who it is for.

kit/turn.py turn(bookings=...) hands the file to the tools (Context.bookings). The page chat (reflection/try_sales.py
TryAgent) passes it; Arena practice matches and exams pass nothing, so practice books on the case copy only and
never fills a real slot. Start over opens a new chat and keeps this file (that is the point).

add() reads the file, runs the caller's clash test on what is there and writes the new booking, all under one lock
(fcntl on a lock file beside it, opened anew each time, so other threads and processes wait), and writes the file whole (a hidden file, then os.replace),
so two chats booking at once never lose a booking and never both take one slot. Values are plain short lines;
the file and its rows are capped; a link in its place is refused, never followed.
"""
import contextlib
import fcntl
import json
import os
import re
import secrets
import time
from pathlib import Path

FILE = "bookings.json"
LOCK = ".bookings.lock"
MAX_BOOKINGS = 2000
MAX_BYTES = 600_000
MAX_LINE = 120
KEYS = ("item", "date", "start", "end", "case", "who", "at")
_TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f<>]")


class Refused(ValueError):
    """The bookings file cannot be written; the message says why."""


def path_of(folder):
    """The bookings file of the agent folder, or None for no folder."""
    return None if folder is None else Path(folder) / FILE


def plain(v, cap=MAX_LINE):
    return " ".join(_CONTROL.sub(" ", str(v or "")).split())[:cap].rstrip()


def _clean(b):
    if not isinstance(b, dict):
        return None
    date, start, end = str(b.get("date") or ""), str(b.get("start") or ""), str(b.get("end") or "")
    if not _DATE.match(date) or not _TIME.match(start) or not _TIME.match(end) or start >= end:
        return None
    return {"item": plain(b.get("item")), "date": date, "start": start, "end": end, "case": plain(b.get("case"), 60),
            "who": plain(b.get("who")), "at": b.get("at") if isinstance(b.get("at"), (int, float)) else 0}


def read(path):
    """Every booking in the file, oldest first; [] when there is none, it is a link or it cannot be read."""
    if path is None:
        return []
    p = Path(path)
    try:
        if p.is_symlink() or p.parent.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
            return []
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return []
    rows = d.get("bookings") if isinstance(d, dict) else None
    return [c for c in (_clean(b) for b in (rows if isinstance(rows, list) else [])[-MAX_BOOKINGS:]) if c]


@contextlib.contextmanager
def _locked(path):
    folder = Path(path).parent
    if folder.is_symlink() or not folder.is_dir():
        raise Refused("The agent's folder is not a plain folder, so nothing was booked.")
    fd = os.open(folder / LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)  # one open each, so threads wait too
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _write(path, rows):
    p = Path(path)
    if p.is_symlink():
        raise Refused("The bookings file is a link, so nothing was booked.")
    body = json.dumps({"bookings": rows[-MAX_BOOKINGS:]}, ensure_ascii=False, indent=1) + "\n"
    tmp = p.parent / f".{FILE}.{secrets.token_hex(4)}.tmp"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, p)


def add(path, booking, clash):
    """Book booking ({item, date, start, end, case, who}) when clash(every booking in the file) gives None; else
    give back its reason. Returns (True, the booking as saved) or (False, reason). The read, the test and the write
    are one step under the lock."""
    entry = _clean(dict(booking, at=time.time()))
    if entry is None:
        return False, "the booking needs a date (YYYY-MM-DD) and a start before its end (HH:MM)"
    with _locked(path):
        rows = read(path)
        why = clash(rows)
        if why:
            return False, why
        rows.append(entry)
        _write(path, rows)
    return True, entry


def minutes(hhmm):
    m = _TIME.match(hhmm or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def hhmm(n):
    return f"{n // 60:02d}:{n % 60:02d}"


def overlaps(rows, date, start, end, item=None):
    """The first booking in rows on date that overlaps start to end (for item, when item is given; "" or None
    means every booking counts), or None."""
    s, e = minutes(start), minutes(end)
    for b in rows:
        if b.get("date") != date:
            continue
        if item and b.get("item") and b["item"].casefold() != item.casefold():
            continue
        bs, be = minutes(b.get("start")), minutes(b.get("end"))
        if bs is not None and be is not None and s < be and bs < e:
            return b
    return None


def next_free(rows, date, length, lo, hi, after, item=None, step=30):
    """The first start (HH:MM) at or after after (minutes), on the step, inside lo to hi (minutes) with room for
    length minutes and no overlap in rows; None when the day has none."""
    t = max(lo, after)
    t += (-(t - lo)) % step
    while t + length <= hi:
        if overlaps(rows, date, hhmm(t), hhmm(t + length), item) is None:
            return hhmm(t)
        t += step
    return None
