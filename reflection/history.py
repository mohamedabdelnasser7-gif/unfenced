"""Reading a brand's old data: WhatsApp chat exports, an Instagram data download, a Shopify
orders export and a deliveries file, then each order joined to the chat it came from.

Every file is untrusted input. Reader opens only the files and folders it was given: a link
is refused (the file itself and any entry inside a given folder), so nothing outside them is
followed; anything inside this repo is refused except demo/history, its folders compared by
device and inode so a change of case does not get round it; each file has a size cap and so
has the whole import; messages, rows and JSON depth have caps too. A folder that cannot be
read is refused and counted. CSV goes through the csv module (a line it cannot read is
refused) and JSON through json after a depth check; nothing is evaluated. A refusal names
the kind of file, never its name, since a WhatsApp export and an Instagram thread folder are
named after the customer. Nothing here prints or logs a message, a name or a phone.

1. WhatsApp: one .txt export per chat. Android lines ("29/10/2026, 14:05 - Name: text") and
   iOS lines ("[29/10/2026, 14:05:09] Name: text"), 24 hour or am/pm, day first unless a
   date in the file only reads month first. A line with no header goes on the message before
   it. System lines are skipped (no "Name: " part, an iOS line marked with U+200E, or a known
   notice such as a deleted message). A media line ("<Media omitted>", "image omitted", a
   file attached) is kept as a media marker with its kind. Times are local, in the zone given.
   A sender on the team list is the team; everyone else is the customer. The chat's phone
   comes from the file name, or from the customer line when the sender is a number.
2. Instagram: messages/inbox/<thread>/message_N.json (also under your_instagram_activity/).
   Its text is UTF-8 written as Latin-1 (mojibake); fix_text turns it back. "Liked a message"
   and reactions are skipped; a photo, video, audio, sticker, file or share is a media marker.
3. Shopify orders CSV: one row per line item, grouped by Name; an order's own fields are on
   its first row. Phones from Phone, Shipping Phone and Billing Phone; Billing Name and
   Shipping Name, when there, are kept only to mask them.
4. Deliveries CSV in our own format, not a Bosta export: columns order, state, date. State
   is delivered, refused or returned; returned counts as refused (call 14A). The last row of
   an order by date wins.
5. The join (join()): a chat and an order meet by phone (kit/orders.py phone_key) or by an
   order number the customer typed, when the order was placed from the chat's first customer
   message up to JOIN_DAYS days after its last one. Phones are the chat's own and any the
   customer typed; an Instagram chat has only the typed ones, so it joins an order only when
   the customer typed a phone or an order number. Each order joins at most one chat: of the
   chats it fits, the one that started last before it.
"""
import csv
import datetime
import io
import json
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from kit import send_check
from kit.orders import phone_key

ROOT = Path(__file__).resolve().parent.parent
REPO = Path(os.path.realpath(ROOT))
ALLOWED = Path(os.path.realpath(ROOT / "demo" / "history"))

MAX_FILE_BYTES = 20 * 1024 * 1024     # one file
MAX_TOTAL_BYTES = 200 * 1024 * 1024   # every file of one import
MAX_FILES = 5000
MAX_MESSAGES_PER_FILE = 50_000
MAX_MESSAGES = 500_000                # every chat of one import
MAX_ROWS = 200_000                    # rows of one CSV file
MAX_TEXT = 4000                       # characters kept of one message
MAX_JSON_DEPTH = 20
JOIN_DAYS = 3
DAY = 86400
TZ = "Africa/Cairo"

WHATSAPP, INSTAGRAM, ORDERS, DELIVERIES = "whatsapp", "instagram", "orders", "deliveries"
DELIVERED, REFUSED, RETURNED = "delivered", "refused", "returned"


class Refused(Exception):
    """A file or folder that is not read, in plain words with no name, phone or text in them."""


# ---- reading files under the caps

class Reader:
    """Opens the given files under the caps. One per import, so the total caps span every file.
    max_files: the file count cap of this import, MAX_FILES unless given. Only the persona build
    (arena/personas.py --max-files) gives one; every upload keeps MAX_FILES."""

    def __init__(self, max_files=None):
        self.max_files = MAX_FILES if max_files is None else max_files
        self.bytes = 0
        self.files = 0
        self.messages = 0
        self.refused = Counter()   # (kind, why): files not read

    def refuse(self, kind, why):
        self.refused[(kind, why)] += 1

    def read(self, path):
        """The file's text. Refused: a link, not a plain file, inside the repo (but demo/history),
        over a size cap or over the file count."""
        check_place(path)
        if self.files >= self.max_files:
            raise Refused("over the file count cap")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            raise Refused("a link, or not readable") from None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise Refused("not a plain file")
            if st.st_size > MAX_FILE_BYTES:
                raise Refused("over the size cap of one file")
            if self.bytes + st.st_size > MAX_TOTAL_BYTES:
                raise Refused("over the size cap of the whole import")
            chunks, size = [], 0
            while size <= MAX_FILE_BYTES:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
        finally:
            os.close(fd)
        if size > MAX_FILE_BYTES or self.bytes + size > MAX_TOTAL_BYTES:  # it grew while read
            raise Refused("over the size cap")
        self.bytes += size
        self.files += 1
        return b"".join(chunks).decode("utf-8-sig", errors="replace")

    def count(self, n):
        """n more messages; Refused over the cap of one file or of the whole import."""
        if n > MAX_MESSAGES_PER_FILE:
            raise Refused("over the message cap of one file")
        if self.messages + n > MAX_MESSAGES:
            raise Refused("over the message cap of the whole import")
        self.messages += n


def _ids(path):
    st = os.stat(path)
    return st.st_dev, st.st_ino


def within(path, folder):
    """True when the real path of path is folder or inside it. The path and each of its parents
    are compared with folder by device and inode, not by name, so a change of case on a disk
    that ignores case (<repo>/COPY/README.md on macOS) is still inside."""
    try:
        want = _ids(folder)
    except OSError:
        return False
    real = Path(os.path.realpath(path))
    for p in (real, *real.parents):
        try:
            if _ids(p) == want:
                return True
        except OSError:
            continue
    return False


def check_place(path):
    """Refused for a path inside this repo, except under demo/history (links resolved, folders
    compared by device and inode)."""
    if within(path, REPO) and not within(path, ALLOWED):
        raise Refused("inside the repo; only demo/history may be read there")


def folder(path):
    """A folder the CLI was given: not a link, a real folder, not inside the repo but demo/history."""
    try:
        st = os.lstat(path)
    except OSError:
        raise Refused("not found") from None
    if stat.S_ISLNK(st.st_mode):
        raise Refused("a link")
    if not stat.S_ISDIR(st.st_mode):
        raise Refused("not a folder")
    check_place(path)
    return Path(path)


def entries(reader, where, kind, *, dirs=False, name=None):
    """The plain files (or folders) right inside where, sorted by name, links refused and counted.
    A folder that cannot be read is refused and counted too, with nothing inside it read."""
    out = []
    try:
        with os.scandir(where) as it:
            for e in sorted(it, key=lambda e: e.name):
                if e.is_symlink():
                    reader.refuse(kind, "a link")
                    continue
                if (e.is_dir(follow_symlinks=False) if dirs else e.is_file(follow_symlinks=False)) and \
                        (name is None or name(e.name)):
                    out.append(Path(e.path))
    except OSError:  # its name is never shown: an Instagram thread folder is named after the customer
        reader.refuse(kind, "a folder that cannot be read")
        return []
    return out


def load_json(text):
    """JSON from untrusted text: nested at most MAX_JSON_DEPTH deep, checked before parsing."""
    bare = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    depth = 0
    for ch in re.findall(r"[\[\]{}]", bare):
        depth += 1 if ch in "[{" else -1
        if depth > MAX_JSON_DEPTH:
            raise Refused("JSON nested too deep")
    try:
        return json.loads(text)
    except ValueError:
        raise Refused("not JSON") from None


# ---- chats

@dataclass
class Message:
    at: float
    team: bool
    text: str
    media: str = None   # the media kind when the message was a photo, voice note and so on
    sender: str = ""    # the sender's display name as name_key gives it, for the import keys


@dataclass
class Chat:
    source: str          # whatsapp or instagram
    key: str             # stable within the source: the chat's phone, its senders or its folder
    place: int           # its file's place in the list, for counts only
    messages: list
    phone: str = ""
    names: set = field(default_factory=set)          # every sender's display name, to mask them
    typed_phones: set = field(default_factory=set)   # phones the customer typed
    typed_orders: set = field(default_factory=set)   # order numbers the customer typed

    def customer_times(self):
        return [m.at for m in self.messages if not m.team]

    def phones(self):
        return ({self.phone} | self.typed_phones) - {""}


_MARKS = re.compile("[‎‏‪-‮⁦-⁩﻿]")


def name_key(s):
    """A display name compared without direction marks, case or extra spaces."""
    return " ".join(_MARKS.sub("", str(s)).casefold().split())


_TIME = (r"(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{2}|\d{4}),? (?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?"
         r"(?:[   ]?(?P<ap>[AaPp]\.?[Mm]\.?))?")
ANDROID = re.compile(r"^" + _TIME + r" - (?P<rest>.*)$")
IOS = re.compile(r"^[‎‏]?\[" + _TIME + r"\] (?P<rest>.*)$")
SYSTEM = re.compile(r"^(?:this message was deleted|you deleted this message|missed (?:voice|video) call"
                    r"|messages and calls are end-to-end encrypted\b.*|waiting for this message\b.*"
                    r"|liked a message|reacted .{1,40} to your message)$", re.IGNORECASE)
MEDIA = re.compile(r"^(?:<media omitted>|(?P<word>image|video|audio|sticker|gif|document|contact card) omitted"
                   r"|<attached: [^>]{1,200}>|[^\n]{1,200} \(file attached\)|[^\n]{0,200} sent an attachment\.?)$",
                   re.IGNORECASE)
_KINDS = {"image": "image", "video": "video", "gif": "video", "audio": "audio", "sticker": "sticker",
          "document": "document", "contact card": "document"}
_EXT = {"jpg": "image", "jpeg": "image", "png": "image", "webp": "image", "mp4": "video", "opus": "audio",
        "ogg": "audio", "m4a": "audio", "mp3": "audio"}
NUMBER_NAME = re.compile(r"[+\d\s().\- ]+")
TYPED_ORDER = re.compile(r"#\s*(\d{1,6})(?!\d)")


def media_kind(text):
    """The media kind a media line names, or None when the line is not a media line."""
    m = MEDIA.match(text.strip())
    if m is None:
        return None
    if m.group("word"):
        return _KINDS[m.group("word").lower()]
    ext = re.search(r"\.([A-Za-z0-9]{2,4})(?:>|\s\(file attached\))", text)
    return _EXT.get(ext.group(1).lower(), "document") if ext else "media"


def _stamp(m, day_first, tz):
    a, b, year = int(m["d"]), int(m["m"]), int(m["y"])
    day, month = (a, b) if day_first else (b, a)
    year += 2000 if year < 100 else 0
    hour = int(m["H"])
    if m["ap"]:
        pm = m["ap"][0] in "Pp"
        if not 1 <= hour <= 12:
            raise ValueError("an am or pm hour is 1 to 12")
        hour = hour % 12 + (12 if pm else 0)
    when = datetime.datetime(year, month, day, hour, int(m["M"]), int(m["S"] or 0), tzinfo=tz)
    return when.timestamp()


def parse_whatsapp(text, team, *, file_name="", tz=TZ, place=0, counts=None):
    """One WhatsApp export as a Chat. team: the business's own display names. counts: a Counter
    that gets lines skipped (system, bad, orphan) by kind."""
    counts = Counter() if counts is None else counts
    tz = ZoneInfo(tz) if isinstance(tz, str) else tz
    team = {name_key(t) for t in team}
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heads = [(ANDROID.match(line) or IOS.match(line)) for line in lines]
    day_first = not (any(h and int(h["m"]) > 12 for h in heads) and not any(h and int(h["d"]) > 12 for h in heads))
    raw, cur = [], None
    for line, h in zip(lines, heads):
        if h is None:
            if cur is None:
                counts["orphan lines"] += bool(line.strip())
            elif cur != "system" and cur["size"] < MAX_TEXT:  # lines past MAX_TEXT would be cut anyway
                cur["size"] += len(line) + bool(cur["parts"])
                cur["parts"].append(line)
            continue
        rest = h["rest"]
        sender, sep, body = rest.partition(": ")
        if not sep or not sender.strip() or len(sender) > 100:
            counts["system lines"] += 1
            cur = "system"
            continue
        try:
            at = _stamp(h, day_first, tz)
        except ValueError:
            counts["bad lines"] += 1
            cur = "system"
            continue
        kind = media_kind(_MARKS.sub("", body))
        bare = _MARKS.sub("", body).strip()
        if kind is None and (body.startswith("‎") or SYSTEM.match(bare)):
            counts["system lines"] += 1
            cur = "system"
            continue
        parts = [body] if body and not kind else []
        cur = {"at": at, "sender": sender.strip(), "parts": parts, "size": len(body) if parts else 0, "media": kind}
        raw.append(cur)
    for r in raw:  # the lines of each message joined once
        r["text"] = "\n".join(r.pop("parts"))
    return _chat(WHATSAPP, raw, team, file_name=file_name, place=place)


def _chat(source, raw, team, *, file_name="", key=None, place=0):
    msgs, names, customers = [], set(), set()
    for r in sorted(raw, key=lambda r: r["at"]):
        is_team = name_key(r["sender"]) in team
        names.add(r["sender"])
        if not is_team:
            customers.add(r["sender"])
        msgs.append(Message(r["at"], is_team, r["text"][:MAX_TEXT].strip(), r["media"], name_key(r["sender"])))
    chat = Chat(source, key or "", place, msgs, names=names)
    found = send_check.PHONE.search(file_name or "")
    if found and phone_key(found.group(0)):
        chat.phone = phone_key(found.group(0))
    else:
        for name in sorted(customers):
            bare = _MARKS.sub("", name).strip()
            if NUMBER_NAME.fullmatch(bare) and phone_key(bare):
                chat.phone = phone_key(bare)
                break
    for m in msgs:
        if not m.team and m.text:
            chat.typed_phones |= {phone_key(p.group(0)) for p in send_check.PHONE.finditer(m.text)} - {""}
            chat.typed_orders |= {"#" + n for n in TYPED_ORDER.findall(m.text)}
    if not chat.key:  # every sender, team or not, so a corrected team list keeps the same chat
        chat.key = chat.phone or "senders:" + "|".join(sorted({name_key(n) for n in names}))
    return chat


def fix_text(s):
    """Instagram's text written back: UTF-8 bytes that were read as Latin-1, read as UTF-8 again.
    A text that does not turn back is left as it is."""
    if not isinstance(s, str):
        return ""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


_IG_MEDIA = (("photos", "image"), ("videos", "video"), ("audio_files", "audio"), ("gifs", "video"),
             ("sticker", "sticker"), ("files", "document"), ("share", "media"))
_MIN_MS, _MAX_MS = 946_684_800_000, 4_102_444_800_000   # 2000 to 2100


def parse_instagram(docs, team, *, key, place=0, counts=None):
    """One Instagram thread as a Chat, from its message_N.json documents. team: the business's
    own display names."""
    counts = Counter() if counts is None else counts
    team = {name_key(t) for t in team}
    raw = []
    for doc in docs:
        if not isinstance(doc, dict) or not isinstance(doc.get("messages"), list):
            raise Refused("not an Instagram messages file")
        for m in doc["messages"]:
            if not isinstance(m, dict):
                counts["bad lines"] += 1
                continue
            sender, ms = fix_text(m.get("sender_name")), m.get("timestamp_ms")
            if not sender.strip() or isinstance(ms, bool) or not isinstance(ms, int) or not _MIN_MS <= ms <= _MAX_MS:
                counts["bad lines"] += 1
                continue
            text = fix_text(m.get("content")) if isinstance(m.get("content"), str) else ""
            kind = next((k for f, k in _IG_MEDIA if m.get(f)), None)
            if SYSTEM.match(text.strip()):
                counts["system lines"] += 1
                continue
            if media_kind(text) is not None:
                kind, text = kind or media_kind(text), ""
            if not text and kind is None:
                counts["system lines"] += 1
                continue
            raw.append({"at": ms / 1000.0, "sender": sender, "text": text, "media": kind})
    return _chat(INSTAGRAM, raw, team, key=key, place=place)


# ---- orders and deliveries

@dataclass
class Order:
    name: str
    at: float
    phones: set
    total: str = None
    cancelled: bool = False
    names: set = field(default_factory=set)   # billing and shipping names, to mask them


ORDER_NAME = re.compile(r"#?[A-Za-z]{0,3}\d{1,12}")
AMOUNT = re.compile(r"\d{1,9}(?:\.\d{1,2})?")


def _rows(text, reader):
    try:
        rows = csv.DictReader(io.StringIO(text, newline=""))
        out = []
        for row in rows:
            if len(out) >= MAX_ROWS:
                raise Refused("over the row cap of one file")
            out.append({(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in row.items()})
        return out, [(c or "").strip() for c in (rows.fieldnames or [])]
    except csv.Error:  # such as a field over the csv module's size limit
        raise Refused("a CSV line that cannot be read, such as a field over the size limit") from None


def when(s, tz, *, noon=False):
    """Seconds from a date and time ("2026-10-29 14:05:09 +0200", ISO 8601) or a date (local,
    at noon when noon); None when it is neither."""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M %z"):
        try:
            return datetime.datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    try:
        d = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if len(s) == 10 and noon:
        d = d.replace(hour=12)
    return (d if d.tzinfo else d.replace(tzinfo=tz)).timestamp()


def parse_orders(text, reader, *, tz=TZ, counts=None):
    """{order name: Order} from a Shopify orders export, its line item rows grouped by Name."""
    counts = Counter() if counts is None else counts
    tz = ZoneInfo(tz) if isinstance(tz, str) else tz
    rows, columns = _rows(text, reader)
    if "Name" not in columns or "Created at" not in columns:
        raise Refused("an orders file needs the columns Name and Created at")
    groups = {}
    for row in rows:
        name = row.get("Name", "")
        if not ORDER_NAME.fullmatch(name):
            counts["bad rows"] += 1
            continue
        groups.setdefault(name, []).append(row)
    out = {}
    for name, group in groups.items():
        def first(col):
            return next((r.get(col, "") for r in group if r.get(col, "")), "")
        at = when(first("Created at"), tz)
        if at is None:
            counts["bad rows"] += 1
            continue
        phones = {phone_key(first(c)) for c in ("Phone", "Shipping Phone", "Billing Phone")} - {""}
        total = first("Total")
        out[name] = Order(name, at, phones, total if AMOUNT.fullmatch(total) else None, bool(first("Cancelled at")),
                          {n for n in (first("Billing Name"), first("Shipping Name")) if n})
    return out


def parse_deliveries(text, reader, *, tz=TZ, counts=None):
    """{order name: (state, at, returned)} from our deliveries file (order, state, date); returned
    counts as refused; the last row of an order by date wins."""
    counts = Counter() if counts is None else counts
    tz = ZoneInfo(tz) if isinstance(tz, str) else tz
    rows, columns = _rows(text, reader)
    if not {"order", "state", "date"} <= set(columns):
        raise Refused("a deliveries file needs the columns order, state and date")
    out = {}
    for row in rows:
        name, state, at = row.get("order", ""), row.get("state", "").lower(), when(row.get("date"), tz, noon=True)
        if not ORDER_NAME.fullmatch(name) or state not in (DELIVERED, REFUSED, RETURNED) or at is None:
            counts["bad rows"] += 1
            continue
        if name not in out or at >= out[name][1]:
            out[name] = (REFUSED if state == RETURNED else state, at, state == RETURNED)
    return out


# ---- the join

def join(chats, orders, days=JOIN_DAYS):
    """({chat index: [order names, oldest first]}, [order names with no chat]). A chat and an order
    meet by phone or by a typed order number, when the order was placed from the chat's first
    customer message up to days after its last one. Each order joins one chat at most: of the
    chats it fits, the one whose first customer message came last before it."""
    spans = []
    for i, chat in enumerate(chats):
        times = chat.customer_times()
        spans.append((min(times), max(times)) if times else None)
    joined, alone = {}, []
    for name, order in sorted(orders.items(), key=lambda kv: (kv[1].at, kv[0])):
        fits = [i for i, chat in enumerate(chats) if spans[i] is not None
                and (chat.phones() & order.phones or name in chat.typed_orders)
                and spans[i][0] <= order.at <= spans[i][1] + days * DAY]
        if not fits:
            alone.append(name)
            continue
        best = max(fits, key=lambda i: (spans[i][0], spans[i][1], chats[i].source, chats[i].key))
        joined.setdefault(best, []).append(name)
    return joined, alone


# ---- masks for text that leaves the chat (voice examples, what the study reads, the chat steps)

EMAIL = re.compile(r"(?<![\w.+\-])[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
LONG_NUMBER = re.compile(r"(?<!\w)\+?\d(?:[ .\-]?\d){6,}(?!\w)")   # spaced, dotted or dashed, any digits
ORDER_REF = re.compile(r"(?:#\s*|(?<![\w.,#]))(?P<n>[A-Za-z]{0,3}\d{1,12})(?!\w)(?![.,]\d)")
NUMBER_BEFORE_ADDRESS = re.compile(r"(?<![\w.,])\d+(?=\s+(?:" + "|".join(send_check.ADDRESS_WORDS) + r")(?!\w))",
                                   re.IGNORECASE)
_TOKEN = re.compile(r"\[(?:name|phone|order|number|email)\]|\w+")
_NAME_RUN = re.compile(r"\[name\](?:[ \t]+\[name\])+")


def _order_key(name):
    return str(name).translate(send_check.EASTERN_DIGITS).strip().lstrip("#").strip().casefold()


class Masker:
    """Masks text that leaves the chat. Built once for an import from every display name and
    order name seen in it, joined to this chat or not. In this order: emails; every PHONE match
    (kit/send_check.py) whatever its grouping; any run of 7 or more digits, spaced, dotted or
    dashed, in any script of digits; the import's order names, with # (#1045, # 104567) or alone
    when they have 3 digits or more or an order word stands before them (رقم الاوردر 1045), but
    not a bare number with a money or size word next to it (السعر 450 جنيه, مقاس 43); draft
    names and # with up to 5 digits (send_check DRAFT_NAME, ORDER_NAME); the number after an
    address word (send_check ADDRESS: عمارة 125, شارع 9) or right before one (12 شارع التجربة);
    then names: a whole name with a word shorter than 3 letters in it, every word of 3 letters
    or more of every name, and a name of one word of 2 letters or more, also typed joined to يا,
    و, ب or ل (يامنى), case and direction marks ignored."""

    def __init__(self, names=(), orders=()):
        self.orders = {k for k in map(_order_key, orders) if k}
        self.words, phrases = set(), set()
        for name in names:
            bare = " ".join(_MARKS.sub("", str(name)).split())
            tokens = [t for t in re.findall(r"\w+", bare) if not t.isdigit()]
            self.words |= {t.casefold() for t in tokens if len(t) >= 3}
            if len(tokens) == 1 and len(tokens[0]) >= 2:
                self.words.add(tokens[0].casefold())
            elif len(tokens) > 1 and any(len(t) < 3 for t in tokens):
                phrases.add(bare)
        self.phrases = re.compile("|".join(r"(?<!\w)" + re.escape(p) + r"(?!\w)" for p in
                                           sorted(phrases, key=len, reverse=True)), re.IGNORECASE) if phrases else None

    def _order(self, m):
        n = m.group("n").translate(send_check.EASTERN_DIGITS).casefold()
        if n not in self.orders:
            return m.group(0)
        if m.group(0).startswith("#") or send_check.ORDER_WORD_BEFORE.search(m.string, 0, m.start()):
            return "[order]"
        if MONEY_AFTER.match(m.string, m.end()) or MEASURE_BEFORE.search(m.string, 0, m.start()):
            return m.group(0)  # a price or a size that happens to match an order number
        return "[order]" if sum(ch.isdigit() for ch in n) >= 3 else m.group(0)

    def _word(self, m):
        w = m.group(0)
        if w[0] == "[":
            return w
        if w.casefold() in self.words:
            return "[name]"
        joined = JOINED.match(w)  # a name typed joined to يا, و, ب or ل (يامنى, ومنى)
        return "[name]" if joined and not joined.group(2).startswith("ال") and joined.group(2).casefold() in self.words else w

    def __call__(self, text):
        if "@" in text:
            text = EMAIL.sub("[email]", text)
        text = send_check.PHONE.sub("[phone]", text)
        text = LONG_NUMBER.sub("[number]", text)
        if self.orders:
            text = ORDER_REF.sub(self._order, text)
        text = send_check.ORDER_NAME.sub("[order]", send_check.DRAFT_NAME.sub("[order]", text))
        text = send_check.ADDRESS.sub(lambda m: re.sub(r"\d+$", "[number]", m.group(0)), text)
        text = NUMBER_BEFORE_ADDRESS.sub("[number]", text)
        if self.phrases is not None:
            text = self.phrases.sub("[name]", text)
        if self.words:
            text = _NAME_RUN.sub("[name]", _TOKEN.sub(self._word, text))
        return text


MONEY_AFTER = re.compile(r"\s*(?:جنيه|جنية|ج(?!\w)|EGP|LE(?!\w)|L\.E|سم(?!\w)|كيلو)", re.IGNORECASE)
MEASURE_BEFORE = re.compile(r"(?:مقاس|سعر|السعر|بسعر)\s*:?\s*$")
JOINED = re.compile(r"(يا|و|ب|ل)(\w{2,})$")


def mask(text, names=(), orders=()):
    """The text masked by a Masker of these names and order names (one text; an import builds
    one Masker and keeps it)."""
    return Masker(names, orders)(text)


def gives_address(text):
    """True when the text has a number after an address word or right before one."""
    return bool(send_check.ADDRESS.search(text) or NUMBER_BEFORE_ADDRESS.search(text))


_PLAIN = str.maketrans("أإآةى", "اااهي")
FORMS_OF_ADDRESS = frozenset(w.translate(_PLAIN) for w in (
    "فندم", "افندم", "حضرتك", "حضرتكم", "باشا", "باشمهندس", "باشمهندسة", "جماعة", "استاذ", "استاذة",
    "معلم", "معلمة", "ريس", "ريسة", "مدام", "هانم", "بيه", "دكتور", "دكتورة", "كابتن", "حاج", "حاجة",
    "عم", "شباب", "رجالة", "بنات", "حبيبي", "حبيبتي", "غالي", "غالية", "عزيزي", "عزيزتي", "قمر", "ست",
    "سيدي", "سيدتي", "اخويا", "اختي", "صاحبي", "بطل", "برنس", "ريت", "رب", "سلام", "ترى", "خبر", "هلا",
    "ستي", "جميل", "جميلة", "انسه", "قلبي", "روحي", "كبير", "بنتي", "ابني", "عسل", "اما", "اختى"))
YA = re.compile(r"(?<!\w)يا\s+(\[\w+\]|[\w\u064B-\u0652]+)")  # a word with its short vowel marks
_VOWEL_MARKS = re.compile("[\u064B-\u0652]")


def calls_by_name(text):
    """True when يا stands before a word that is still unmasked and is not a plain form of
    address (يا فندم, يا باشا, يا أستاذ): most likely a name the masks missed."""
    return any(_name_like(m.group(1)) for m in YA.finditer(text))


def _name_like(word):
    if word.startswith("["):
        return False
    plain = _VOWEL_MARKS.sub("", word).translate(_PLAIN)
    return not plain.startswith("ال") and plain not in FORMS_OF_ADDRESS
