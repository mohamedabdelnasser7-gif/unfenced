"""The chats of a running Arena run as they happen, for the screen only (Mohamed 2026-11-05: "i need to see the
live chats happening even the losing ones so i can correct with hotfix"). Every agent's run writes them:
the Sales agent's (arena/run.py Arena.play) and a built agent's (arena/practice.py Practice.play).

One file a match playing now, <state>/live/<match id>.json: {"id", "who", "about", "status" ("playing", then
"finished" with "won" while a match played beside others waits to be folded in), "turns": the turns so far, in
arena/match.py's shape, "at"}. Written whole each time (a temp file, then os.replace), so a reader only ever
meets a whole file. Removed once the match is saved or dropped. The matches file stays the only record: the
gate, the exam, Train and the night never read this folder."""
import json
import os
import re
import tempfile
import time
from pathlib import Path

LIVE_DIR = "live"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
MAX_FILE = 2_000_000  # bytes read at most from one live file
WHO = "Practice case"
STALE = 15 * 60  # seconds with no write before a live file is read as left behind


def folder(state):
    return Path(state) / LIVE_DIR


def path_of(state, match_id):
    """The live file of match_id under state, or None for an id that is not a plain file name."""
    if not isinstance(match_id, str) or not SAFE_ID.match(match_id) or ".." in match_id:
        return None
    return folder(state) / f"{match_id}.json"


def who_of(card):
    """(the name a tile shows, its one about line) for a practice customer card; the card's id is never shown."""
    card = card if isinstance(card, dict) else {}
    parts = ["Made up for the Arena"]
    worry = card.get("worry")
    if isinstance(worry, str) and worry.strip():
        parts.append(f"worry: {' '.join(worry.split())[:60]}")
    want = card.get("want")
    first = want[0] if isinstance(want, list) and want and isinstance(want[0], str) else None
    if first and first.strip():
        parts.append(f"wants {' '.join(first.split())[:80]}")
    return WHO, ", ".join(parts)


def _write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".live-", suffix=".tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def remove(state, match_id):
    """Removes match_id's live file; never raises."""
    p = path_of(state, match_id)
    if p is None:
        return
    try:
        p.unlink()
    except OSError:
        pass


class Watch:
    """One playing match's live file. Its call (match play's on_turn) writes the turns so far. Nothing it does
    ever raises: a live file that cannot be written leaves the match as it would be with none."""

    def __init__(self, state, match_id, card, now=time.time):
        self.state, self.id, self.now = state, match_id, now
        self.path = path_of(state, match_id)
        self.who, self.about = who_of(card)
        self.turns = []

    def _put(self, status, **more):
        if self.path is None:
            return
        try:
            _write(self.path, {"id": self.id, "who": self.who, "about": self.about, "status": status,
                               "turns": self.turns, "at": self.now(), **more})
        except Exception:
            pass

    def start(self):
        self._put("playing")
        return self

    def __call__(self, turns):
        try:
            self.turns = [dict(t) for t in turns if isinstance(t, dict)]
        except Exception:
            return
        self._put("playing")

    def finish(self, won, why=""):
        """The match is judged but waits to be folded in (a lane): the tile shows Won or Lost until its
        line is on the matches file."""
        self._put("finished", won=bool(won), why=why if isinstance(why, str) else "")

    def remove(self):
        remove(self.state, self.id)


def read(state, now=None):
    """The live files under state, each a dict with id, who, about, status, turns (and won, why when finished),
    in match id order (a run's matches by round and number); files that cannot be read are left out, and so is
    one not written for STALE seconds (a run the server stopped mid match leaves its file behind)."""
    now = time.time() if now is None else now
    out = []
    d = folder(state)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json") or n.startswith("."):
            continue
        p = d / n
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE:
                continue
            x = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            continue
        if not isinstance(x, dict) or not isinstance(x.get("id"), str) or x["id"] + ".json" != n:
            continue
        turns = x.get("turns") if isinstance(x.get("turns"), list) else []
        row = {"id": x["id"], "who": str(x.get("who") or WHO), "about": str(x.get("about") or ""),
               "status": "finished" if x.get("status") == "finished" else "playing",
               "turns": [t for t in turns if isinstance(t, dict)],
               "at": x.get("at") if isinstance(x.get("at"), (int, float)) else 0}
        if now - row["at"] > STALE:
            continue
        if row["status"] == "finished":
            row["won"], row["why"] = x.get("won") is True, str(x.get("why") or "")
        out.append(row)
    out.sort(key=lambda r: r["id"])
    return out
