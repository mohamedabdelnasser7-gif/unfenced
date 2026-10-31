"""The mailbox reader (new, 2026-10-31; spec section 1, DECISIONS item 37): an uploaded .mbox
export (Inbox and Sent) in, a picture of the user out. Patterns only.

    python3 -I assistant/mbox.py --user ADDRESS --out PICTURE.json FILE.mbox [FILE.mbox ...]

A message is the user's (Sent) by is_sent: a message with Gmail labels (X-Gmail-Labels) is Sent
only when they hold Sent and neither Inbox nor Spam, whatever its From says, and the label line
sits above the first Received, Delivered-To or Return-Path line (below them, the sender wrote it,
so the message is Inbox); with no labels, a
message that was delivered to someone (Delivered-To or Received) is Inbox, and only then does a
From of the user's address make it Sent. A forged From alone never makes an outside mail the
user's. Any other message is Inbox. Inbox and Sent may come as two files or one. Messages are
split only on an envelope line (From, a sender, then the mbox date), so a body line that starts
with From is text.

What the picture keeps, and nothing more:
  busy_hours     the hours the user is most active, from counts of messages per hour.
  fast_replies   who the user answers fast (who matters): their address, how many replies and the
                 median minutes to reply, from Sent replies matched to the Inbox message they answer.
  style          how the user writes, from the user's own Sent text with quoted parts cut: median
                 words, the usual greeting and sign-off when one is common, the share of questions
                 and exclamations.
  promises       promises the user made in Sent: to whom, when, and the user's own sentence.
  inbox          counts only: messages per hour, and how many messages promised the user something.
  starting_modes working start and end, and how short a short reply is for this user (the mode
                 picker's signals, assistant/modes.py).
Other people's message text is never stored: Inbox subjects and bodies are read only to count, and
quoted text inside the user's replies is cut before anything is kept.

Safety: the file is untrusted. It is read as bytes, capped (MAX_BYTES for all the files together,
MAX_MESSAGES in all, MAX_BODY characters a message), only text/plain parts are decoded, a part
over MAX_PART raw characters is skipped before it is decoded, attachments, attached messages, parts
with a file name and every part under them are skipped, an odd charset or date is read as UTF-8 or
no date, and a message that cannot be parsed is counted as skipped. Nothing in it is run or
followed. Known gap: a body line that looks exactly like an envelope line (From, a sender, then a
full mbox date) and was not escaped as ">From" by the exporter still starts a new message there;
the rest of that body is read as one more message, so an outside mail built that way can have its
tail counted as the user's when the tail starts with the user's From and no delivery lines (red
team round 1, R7; real exporters escape such lines).
"""
import argparse
import collections
import datetime
import email
import email.policy
import email.utils
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

MAX_BYTES = 200 * 1024 * 1024
MAX_MESSAGES = 20000
MAX_BODY = 20000
MAX_PART = 4 * MAX_BODY  # raw characters in one part; a longer part is skipped before decoding
YEARS = (1970, 2100)     # a Date outside these years is no date
MAX_PROMISES = 20
MAX_FAST = 8
FAST_MINUTES = 120
# The mbox envelope line: From, the sender, then the date as mbox writes it (asctime, with a zone
# before the year in Gmail exports): "From a@b.test Thu Oct 30 10:00:00 2026" or
# "From 123@xxx Wed Jan 05 15:23:00 +0000 2022".
SPLIT = re.compile(rb"(?:\A|\r?\n)From [^ \t\r\n]+[ \t]+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[ \t]+"
                   rb"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[ \t]+[0-9]{1,2}[ \t]+"
                   rb"[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?[ \t]+(?:[+-][0-9]{4}[ \t]+|[A-Za-z]{2,5}[ \t]+)?"
                   rb"[0-9]{4}[ \t]*\r?\n")
# A quote header: everything from it on is someone else's mail. English Gmail and Outlook headers, a line of
# underscores (Outlook's), the Arabic Outlook header lines (from, to, sent, subject) and an Arabic
# Gmail "wrote:" line, its name before or after the word (red team round 2, R2-3).
QUOTE_START = re.compile(r"^(on .{3,200} wrote:|-{2,} ?original message ?-{2,}|from: .+|_{5,}"
                         r"|(?:من|إلى|الى|تاريخ الإرسال|الموضوع) ?:.*|.{0,200}(?<!\w)كتبت?(?!\w).{0,200}:)$", re.IGNORECASE)
GREETINGS = ("hi", "hey", "hello", "dear", "good morning", "morning")
PROMISE = re.compile(r"\b(i'll|i will|i can get|let me|i'm going to|will send|will get back|will reply|will share)\b",
                     re.IGNORECASE)
WHEN = re.compile(r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|"
                  r"end of day|eod|this week|by [0-9]{1,2}(?::[0-9]{2})?|[0-9]{4}-[0-9]{2}-[0-9]{2})\b", re.IGNORECASE)
TO_USER = re.compile(r"\b(i'll|i will|we will|we'll)\b", re.IGNORECASE)
SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
WORD = re.compile(r"\w+", re.UNICODE)
# Lines a mail server adds on delivery. Gmail writes its own label line above them, so a label line
# below the first of them was written by the sender.
TRACE_HEADERS = ("received", "delivered-to", "return-path")


class Refused(ValueError):
    pass


def split_mbox(data):
    """The raw messages of one mbox file, as bytes."""
    return [m for m in SPLIT.split(data) if m.strip()]


def _addr(value):
    return email.utils.parseaddr(str(value or ""))[1].strip().casefold()


def _when(msg):
    try:
        d = email.utils.parsedate_to_datetime(str(msg.get("Date", "")))
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if d is None or d.tzinfo is None or not YEARS[0] <= d.year <= YEARS[1]:
        return None  # a year far out would overflow when the time is moved to the user's zone
    return d


def _parts(msg):
    """The message's leaf parts in order, leaving out an attached message (message/rfc822 or any other
    message type), an attachment and a part with a file name, with every part under them: a mail
    forwarded as an attachment is someone else's words (red team round 2, R2-2). No recursion, so a
    deep nesting cannot overflow the stack."""
    stack = [msg]
    while stack:
        part = stack.pop()
        if (part.get_content_maintype() == "message" or part.get_content_disposition() == "attachment"
                or part.get_filename() is not None):
            continue
        if part.is_multipart():
            stack.extend(reversed(part.get_payload()))
            continue
        yield part


def _text(msg):
    """The text/plain parts, decoded, capped; attachments skipped (_parts)."""
    out = []
    for part in _parts(msg):
        if part.get_content_type() != "text/plain":
            continue
        payload = part.get_payload()
        if isinstance(payload, str) and len(payload) > MAX_PART:
            continue  # too long to decode: one base64 part could take a lot of memory
        raw = part.get_payload(decode=True) or b""
        try:
            out.append(raw.decode(part.get_content_charset() or "utf-8", errors="replace"))
        except (LookupError, ValueError):  # a charset Python does not know or cannot use (idna): UTF-8
            out.append(raw.decode("utf-8", errors="replace"))
        if sum(map(len, out)) >= MAX_BODY:
            break
    return "\n".join(out)[:MAX_BODY]


def own_text(body):
    """The user's own words in a reply: quoted lines and everything after a quote header cut."""
    keep = []
    for line in body.splitlines():
        s = "".join(ch for ch in line if unicodedata.category(ch) != "Cf").strip()  # no direction marks
        if s.startswith(">") or QUOTE_START.match(s):
            if QUOTE_START.match(s):
                break
            continue
        keep.append(line)
    return "\n".join(keep).strip()


def is_sent(msg, user):
    """Is the message the user's own (see the module lines)? user: the address, casefolded."""
    labels = msg.get("X-Gmail-Labels")
    names = [str(k).casefold() for k in msg.keys()]
    trace = [i for i, k in enumerate(names) if k in TRACE_HEADERS]
    if labels is not None and trace and names.index("x-gmail-labels") > trace[0]:
        return False  # a label line below the delivery lines came inside an outside mail (review round 2)
    if labels is not None:  # Gmail's own labels, and nothing else
        got = {x.strip() for x in str(labels).casefold().split(",")}
        return "sent" in got and not got & {"inbox", "spam"}
    if msg.get("Delivered-To") is not None or msg.get("Received") is not None:
        return False  # delivered to a mailbox: an inbound mail, whatever its From says
    return _addr(msg.get("From")) == user


def load(paths, user, *, max_bytes=MAX_BYTES, max_messages=MAX_MESSAGES):
    """[(is_sent, msg)] from the files, and how many were skipped. max_bytes: all the files together."""
    user = (user or "").strip().casefold()
    if "@" not in user:
        raise Refused("the user's address is needed to tell Sent from Inbox")
    paths = [Path(p) for p in paths]
    if sum(p.stat().st_size for p in paths) > max_bytes:
        raise Refused("the files are over the size cap")
    out, skipped = [], 0
    for p in paths:
        for raw in split_mbox(p.read_bytes()):
            if len(out) >= max_messages:
                raise Refused("the export is over the message cap")
            try:
                msg = email.message_from_bytes(raw, policy=email.policy.compat32)
            except Exception:  # an untrusted file: any parse failure is one skipped message
                skipped += 1
                continue
            out.append((is_sent(msg, user), msg))
    return out, skipped


def picture(messages, user, *, skipped=0):
    """The user picture from [(is_sent, msg)]. Patterns only (see the module lines)."""
    user = user.strip().casefold()
    sent = [m for s, m in messages if s]
    inbox = [m for s, m in messages if not s]
    offsets = collections.Counter(d.utcoffset() for d in (_when(m) for m in sent) if d is not None)
    tz = datetime.timezone(offsets.most_common(1)[0][0]) if offsets else datetime.timezone.utc

    def local(m):
        d = _when(m)
        return d.astimezone(tz) if d is not None else None

    hours = collections.Counter()
    inbox_hours = collections.Counter()
    for m in sent:
        d = local(m)
        if d:
            hours[d.hour] += 1
    for m in inbox:
        d = local(m)
        if d:
            hours[d.hour] += 1
            inbox_hours[d.hour] += 1

    received = {}
    promised_to_user = 0
    for m in inbox:
        mid = str(m.get("Message-ID", "")).strip()
        d = _when(m)
        if mid and d is not None:
            received[mid] = (_addr(m.get("From")), d)
        if TO_USER.search(_text(m)):
            promised_to_user += 1  # counted, never kept

    replies = collections.defaultdict(list)
    lengths, greetings, sign_offs, questions, exclaims, promises = [], collections.Counter(), collections.Counter(), 0, 0, []
    for m in sent:
        d = _when(m)
        parent = received.get(str(m.get("In-Reply-To", "")).strip())
        if parent and d is not None:
            mins = (d - parent[1]).total_seconds() / 60
            if 0 <= mins <= 7 * 24 * 60 and parent[0] and parent[0] != user:
                replies[parent[0]].append(mins)
        mine = own_text(_text(m))
        if not mine:
            continue
        lengths.append(len(WORD.findall(mine)))
        lines = [x.strip() for x in mine.splitlines() if x.strip()]
        first = lines[0].casefold() if lines else ""
        for g in GREETINGS:
            if first == g or first.startswith(g + " ") or first.startswith(g + ","):
                greetings[lines[0][:len(g)]] += 1  # as the user writes it
                break
        tail = [x.rstrip(",") for x in lines[1:][-2:] if len(WORD.findall(x)) <= 3]
        if tail and len(tail) == len(lines[1:][-2:]):
            sign_offs[", ".join(tail)] += 1
        questions += "?" in mine
        exclaims += "!" in mine
        if len(promises) < MAX_PROMISES:
            for s in SENTENCE.findall(mine):
                s = s.strip()
                if PROMISE.search(s) and WHEN.search(s):
                    promises.append({"to": _addr(m.get("To")), "at": d.astimezone(tz).date().isoformat() if d else None,
                                     "line": s[:160], "when": WHEN.search(s).group(0)})
                    break

    n = len(lengths)
    style = {"median_words": int(statistics.median(lengths)) if lengths else None,
             "greeting": _common(greetings, n), "sign_off": _common(sign_offs, n),
             "questions_share": round(questions / n, 2) if n else None,
             "exclaims_share": round(exclaims / n, 2) if n else None}
    fast = sorted(({"who": who, "replies": len(v), "median_minutes": round(statistics.median(v))}
                   for who, v in replies.items() if statistics.median(v) <= FAST_MINUTES),
                  key=lambda r: (r["median_minutes"], -r["replies"], r["who"]))[:MAX_FAST]
    return {"user": user, "messages": {"inbox": len(inbox), "sent": len(sent), "skipped": skipped},
            "busy_hours": [h for h, _ in sorted(hours.items(), key=lambda kv: (-kv[1], kv[0]))[:4]],
            "fast_replies": fast, "style": style, "promises": promises,
            "inbox": {"per_hour": {f"{h:02d}": c for h, c in sorted(inbox_hours.items())},
                      "promised_to_user": promised_to_user},
            "starting_modes": starting_modes(sent, local, lengths)}


def _common(counter, n):
    """The most common value when at least a third of the messages have it, else None."""
    if not counter or not n:
        return None
    value, count = counter.most_common(1)[0]
    return value if count * 3 >= n else None


def starting_modes(sent, local, lengths):
    """The mode picker's starting signals from the user's own sending times and lengths."""
    times = sorted(d.hour * 60 + d.minute for d in (local(m) for m in sent) if d)
    out = {"work_start": "09:00", "work_end": "18:00", "short_reply_words": 8}
    if len(times) >= 5:
        lo = times[len(times) // 10]
        hi = times[min(len(times) - 1, (len(times) * 9) // 10)]
        start, end = max(5, min(12, lo // 60)), max(14, min(23, hi // 60 + 1))
        out.update(work_start=f"{start:02d}:00", work_end=f"{end:02d}:00")
    if len(lengths) >= 4:
        out["short_reply_words"] = max(3, sorted(lengths)[len(lengths) // 4])
    return out


def read(paths, user, **caps):
    msgs, skipped = load(paths, user, **caps)
    return picture(msgs, user, skipped=skipped)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="assistant/mbox.py")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--user", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    try:
        pic = read(args.files, args.user)
    except (Refused, OSError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    text = json.dumps(pic, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
