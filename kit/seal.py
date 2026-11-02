"""The Arena run's seal on its Morning page item (review simplify round 3, red team B).

A run writes its item (arena/run.py Arena._write_item) with an HMAC SHA-256 over the whole item, keyed
with a random key the run makes once in its own folder, beside the database (KEY_FILE, owner read and
write only). The key is never in the repo (the Arena's folder is outside it or under data/), never
printed and never logged. Morning.gate counts a pass only when the seal matches with that key, so an
item written by hand, or one edited after the run (quick true made false), never unlocks Connect. An
item with no seal, from before this, stays locked until a new run. Someone who can read the key can
still make a seal; the key sits beside the database, which they could change directly anyway.
"""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

KEY_FILE = "arena-seal.key"
FIELD = "seal"
KEY_BYTES = 32


def key(folder, make=False):
    """The folder's key as bytes, or None when there is none or it cannot be read. make: a run makes
    the key when the folder has none yet; a reader never makes one."""
    path = Path(folder) / KEY_FILE
    if make and not path.exists():
        try:
            _make(path)
        except OSError:
            return None
    try:
        got = path.read_bytes()
    except OSError:
        return None
    return got if len(got) == KEY_BYTES else None


def _make(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{KEY_FILE}.{os.getpid()}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(KEY_BYTES))
        try:
            os.link(tmp, path)  # whole or not at all; a run that made one first wins
        except FileExistsError:
            pass
    finally:
        tmp.unlink(missing_ok=True)


def _mac(item, k):
    """The seal of item (its seal field left out) as it reads back from its JSON file."""
    body = json.loads(json.dumps({x: v for x, v in item.items() if x != FIELD}, ensure_ascii=False))
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hmac.new(k, text.encode("utf-8"), hashlib.sha256).hexdigest()


def sign(item, folder):
    """Put the run's seal on item, making the folder's key if it has none. With no key that can be
    made or read the item goes out with no seal, so it never unlocks Connect."""
    k = key(folder, make=True)
    if k is not None:
        item[FIELD] = _mac(item, k)
    return item


def holds(item, k):
    """True when item carries a seal that matches key k (bytes from key()); False for no key or no seal."""
    got = item.get(FIELD) if isinstance(item, dict) else None
    return k is not None and isinstance(got, str) and hmac.compare_digest(got, _mac(item, k))
