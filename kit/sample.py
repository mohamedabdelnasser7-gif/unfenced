"""Sample data for an agent made by Quick start (2026-11-03).

An agent whose work reads data it has no real connection for (stock levels with no store keys, open
tickets, leads, briefs) gets a small made-up dataset at Build: one model call writes it from the card
(reflection/quickstart.py), every row marked made up. The user can add more on the build page or the
agent's Overview, pasted as rows or text or as a CSV or JSON file; those rows are marked as the
user's. All of it sits in one file in the agent's folder, <db folder>/agents/<name>/sample-data.json:

    {"what": "products with stock counts", "rows": [{"by": "made_up" or "user", "row": {key: value}}]}

Every value is untrusted: keys and values are plain short lines with no markup characters, numbers
stay numbers, anything nested is cut to a line; rows, keys and the file are capped. A file is read
as text and parsed with json or csv, never run.

The agent reads it through the data tool (kit/tools/data.py), and for a store need with no Shopify
keys the store tool reads its products (store_items, kit/tools/store.py SAMPLE). Real keys always
win. Practice customers and the judge read the same rows (for_prompt).
"""
import csv
import io
import json
import os
import re
import secrets
from pathlib import Path

FILE = "sample-data.json"
MADE_UP, USER = "made_up", "user"
MAX_BYTES = 96_000      # the file
MAX_ROWS = 200          # rows in the file
MAX_MADE = 30           # rows the model writes at Build
MAX_ADD = 100           # rows one paste or file adds
MAX_KEYS = 12           # keys in one row
MAX_KEY = 40
MAX_CELL = 300
MAX_WHAT = 80
MAX_TEXT = 20_000       # characters of pasted text or of a file
MAX_UPLOAD = 64 * 1024  # bytes of one uploaded file
MAX_PROMPT = 4000       # characters of rows a practice customer or the judge reads

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_MARKUP = re.compile(r"[<>]")
_KEY = re.compile(r"[^a-z0-9_]+")

TITLE_KEYS = ("title", "name", "product", "product_name", "item")
PRICE_KEYS = ("price", "unit_price", "cost")
STOCK_KEYS = ("stock", "quantity", "qty", "in_stock", "stock_count", "stock_level", "inventory", "units", "on_hand")
SIZE_KEYS = ("size", "variant")
TYPE_KEYS = ("type", "category", "product_type")
LEVELS = ("in stock", "few left", "out")


class Refused(ValueError):
    """Sample data that cannot be taken; the message says why in plain words, nothing was saved."""


def line(v, cap):
    """One plain line: no control or markup characters, spaces folded, capped."""
    v = " ".join(_MARKUP.sub("", _CONTROL.sub("", str(v))).split())
    return v[:cap].rstrip()


def _key(k):
    k = _KEY.sub("_", line(k, MAX_KEY * 2).lower()).strip("_")
    return k[:MAX_KEY]


def clean_row(raw):
    """One row as {key: value}: string keys made plain lowercase words joined by _, at most MAX_KEYS;
    numbers and true or false kept, anything else one plain line. None when nothing is left."""
    if not isinstance(raw, dict):
        raw = {"text": raw}
    out = {}
    for k, v in raw.items():
        if len(out) >= MAX_KEYS:
            break
        key = _key(k)
        if not key or key in out or v is None:
            continue
        if isinstance(v, bool) or (isinstance(v, (int, float)) and v == v and abs(v) < 1e15):
            out[key] = v
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        v = line(v, MAX_CELL)
        if v:
            out[key] = v
    return out or None


def clean_rows(raws, by, most):
    rows = []
    for r in raws if isinstance(raws, list) else []:
        if len(rows) >= most:
            break
        got = clean_row(r)
        if got:
            rows.append({"by": by, "row": got})
    return rows


def made(what, rows):
    """The sample data the model wrote at Build, or None when no row is left."""
    rows = clean_rows(rows, MADE_UP, MAX_MADE)
    if not rows:
        return None
    return {"what": line(what, MAX_WHAT) or "sample rows", "rows": rows}


def read(folder):
    """The agent's sample data, {what, rows}, or None when there is none or it cannot be read."""
    p = Path(folder) / FILE
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("rows"), list):
        return None
    rows = []
    for r in d["rows"][:MAX_ROWS]:
        if isinstance(r, dict) and r.get("by") in (MADE_UP, USER):
            got = clean_row(r.get("row"))
            if got:
                rows.append({"by": r["by"], "row": got})
    if not rows:
        return None
    return {"what": line(d.get("what") or "", MAX_WHAT) or "sample rows", "rows": rows}


def text_of(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def write(folder, data):
    """The file written whole: a hidden file first, renamed into place. Refused over MAX_BYTES."""
    folder = Path(folder)
    body = text_of(data)
    if len(body.encode("utf-8")) > MAX_BYTES:
        raise Refused("That is more sample data than one agent keeps. Send fewer rows.")
    target = folder / FILE
    if target.is_symlink() or folder.is_symlink() or not folder.is_dir():
        raise Refused("The agent's folder is not a plain folder, so nothing was added.")
    tmp = folder / f".{FILE}.{secrets.token_hex(4)}.tmp"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)


def parse(text):
    """Rows from pasted text or a file's text: JSON (a list of objects, or an object holding one), CSV
    with a header row (comma, semicolon or tab), else one row a line as {"text": line}."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    if len(text) > MAX_TEXT:
        raise Refused(f"At most {MAX_TEXT} characters at a time, please.")
    if text[0] in "[{":
        try:
            got = json.loads(text)
        except (ValueError, RecursionError):
            raise Refused("That looked like JSON but could not be read. Check it, or paste it as plain lines.") from None
        if isinstance(got, dict):
            lists = [v for v in got.values() if isinstance(v, list)]
            got = lists[0] if len(lists) == 1 else [got]
        return got if isinstance(got, list) else [got]
    lines = [x for x in text.split("\n") if x.strip()]
    head = lines[0]
    delim = max((",", ";", "\t"), key=head.count)
    if len(lines) >= 2 and head.count(delim) >= 1:
        try:
            reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delim)
            rows = [{k: v for k, v in r.items() if k is not None} for r in reader]
        except csv.Error:
            raise Refused("That looked like a CSV but could not be read. Check it, or paste it as plain lines.") from None
        return rows
    return [{"text": x} for x in lines]


def decode(raw):
    """A file's bytes as text: UTF-8 only, under MAX_UPLOAD."""
    if len(raw) > MAX_UPLOAD:
        raise Refused(f"The file is over {MAX_UPLOAD // 1024} KB. Send a smaller one.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Refused("The file is not plain text. Send a CSV or a JSON file.") from None


def add(folder, text="", raw=b""):
    """The user's rows added to the agent's sample data, marked as theirs. Returns how many were added.
    Refused, with nothing saved, when there is nothing to add, it cannot be read or it is too much."""
    raws = parse(text) + (parse(decode(raw)) if raw else [])
    rows = clean_rows(raws, USER, MAX_ADD)
    if not rows:
        raise Refused("There was nothing to add. Paste rows or text, or choose a CSV or JSON file.")
    if len(raws) > MAX_ADD:
        raise Refused(f"At most {MAX_ADD} rows at a time, please.")
    data = read(folder) or {"what": "rows you added", "rows": []}
    if len(data["rows"]) + len(rows) > MAX_ROWS:
        raise Refused(f"It keeps at most {MAX_ROWS} rows of sample data, and this would go over.")
    data["rows"] += rows
    write(folder, data)
    return len(rows)


def counts(data):
    """(made up rows, the user's rows)."""
    rows = (data or {}).get("rows") or []
    return sum(r["by"] == MADE_UP for r in rows), sum(r["by"] == USER for r in rows)


def words(data):
    """The card's line about the sample data, or "" when there is none."""
    if not data:
        return ""
    made_up, user = counts(data)
    out = f"Sample data made for this agent: {data['what']}, {made_up} made up" if made_up else \
        f"Sample data for this agent: {data['what']}"
    if user:
        out += f", {user} added by you"
    return out + "."


def rows_of(data):
    """The rows the tool and the prompts read, each with where it came from."""
    return [dict(r["row"], source="made up" if r["by"] == MADE_UP else "added by the user")
            for r in (data or {}).get("rows") or []]


def for_prompt(data, cap=MAX_PROMPT):
    """The rows as one JSON line for a practice customer or the judge, capped; "" when none."""
    if not data:
        return ""
    out = []
    size = 0
    for r in rows_of(data):
        one = json.dumps(r, ensure_ascii=False)
        if size + len(one) > cap:
            break
        out.append(r)
        size += len(one) + 2
    return json.dumps(out, ensure_ascii=False)


def _first(row, keys):
    for k in keys:
        if k in row and row[k] not in ("", None):
            return row[k]
    return None


def stock_word(v):
    """A stock value as the store tool's level (in stock, few left, out), never a count; None when it is
    not one."""
    from kit.tools import store
    if isinstance(v, bool):
        return "in stock" if v else "out"
    if isinstance(v, (int, float)):
        return store.stock_level(v)
    s = str(v).strip().lower()
    if s in LEVELS:
        return s
    if re.fullmatch(r"\d{1,9}", s):
        return store.stock_level(int(s))
    return {"yes": "in stock", "no": "out", "true": "in stock", "false": "out", "sold out": "out",
            "out of stock": "out", "low": "few left"}.get(s)


def store_items(data):
    """The sample rows that read as products, in the store tool's shape ({title, type, variants: [{size,
    price, stock}]}); [] when none do. Stock goes out as a level, never a count, as the store's does."""
    items, by_title = [], {}
    for r in (data or {}).get("rows") or []:
        row = r["row"]
        title = _first(row, TITLE_KEYS)
        if not isinstance(title, str) or not title:
            continue
        price, stock = _first(row, PRICE_KEYS), stock_word(_first(row, STOCK_KEYS))
        if price is None and stock is None:
            continue
        var = {}
        size = _first(row, SIZE_KEYS)
        if size is not None:
            var["size"] = str(size)
        if price is not None:
            var["price"] = str(price)
        if stock is not None:
            var["stock"] = stock
        item = by_title.get(title)
        if item is None:
            item = by_title[title] = {"title": title}
            kind = _first(row, TYPE_KEYS)
            if isinstance(kind, str):
                item["type"] = kind
            item["variants"] = []
            items.append(item)
        item["variants"].append(var)
    return items
