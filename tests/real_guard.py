"""No test reads arena/real/ (new, 2026-10-31; DECISIONS items 23 and 40).

The Arena's default cards are the cleaned real cards (arena/run.py DEFAULT_CARDS, arena/real/cards).
The tests play the made-up set instead: install() points DEFAULT_CARDS at DEMO_CARDS for the whole
suite, and adds an audit hook that refuses any open of a file under arena/real/, and any database
opened there, before the file is read. Listing the folder's names is allowed. The refusal is a
RealRead, a BaseException, so no "except Exception" in the code under test can swallow it: the
test that tried fails. tests/__init__.py calls install() once, before any test module loads.

A path is under arena/real/ when it or one of its parent folders is that folder by device and
inode (st_dev, st_ino), so another spelling of it is refused too: another case on a case blind
disk, /System/Volumes/Data in front, a link to the folder or to a folder above it, a relative
path. A sqlite "file:" URI is read as the path it names. Out of scope, as no test does them: child
processes (the hook is this process's only), a file opened by a folder descriptor (dir_fd), and a
new name made for a file in the folder with os.link or os.symlink (the hook sees the new name).
"""
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = os.path.normcase(os.path.abspath(ROOT / "arena" / "real"))
EVENTS = ("open", "sqlite3.connect", "sqlite3.connect/handle")
REAL_DEFAULT = None  # arena/run.py DEFAULT_CARDS as shipped, kept for the test that checks it
refused = []  # every path refused this run


class RealRead(BaseException):
    """A test tried to read a file under arena/real/."""


def _id(path):
    """(st_dev, st_ino) of path, following links; None when it is not there. A stat, never an open."""
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return None
    return st.st_dev, st.st_ino


def _plain(p):
    """A sqlite file: URI as the path it names; any other path as it is."""
    if not p.startswith("file:"):
        return p
    p = p[len("file:"):].split("?", 1)[0].split("#", 1)[0]
    if p.startswith("//"):  # file://host/path: the path starts at the next slash
        p = p[2:]
        p = p[p.find("/"):] if "/" in p else ""
    return urllib.parse.unquote(p)


def under_real(path):
    if isinstance(path, int) or path is None:  # an open file descriptor, or no path
        return False
    try:
        p = os.fsdecode(os.fspath(path))
    except TypeError:
        return False
    p = _plain(p)
    if not p or p == ":memory:":
        return False
    rp = os.path.normcase(os.path.realpath(p))  # a link into arena/real plus ".." lands here
    p = os.path.normcase(os.path.abspath(p))
    reals = {REAL, os.path.normcase(os.path.realpath(REAL))}
    if any(q == r or q.startswith(r + os.sep) for q in (p, rp) for r in reals):
        return True
    real = _id(REAL)
    if real is None:
        return False
    while True:  # the path or a parent folder that is arena/real by device and inode
        if _id(p) == real:
            return True
        up = os.path.dirname(p)
        if up == p:
            return False
        p = up


def _hook(event, args):
    if event in EVENTS and args and under_real(args[0]):
        refused.append(args[0])
        raise RealRead(f"a test opened {args[0]}: tests never read arena/real/; use run.DEMO_CARDS")


def install():
    global REAL_DEFAULT
    if REAL_DEFAULT is not None:
        return
    from arena import run
    REAL_DEFAULT = run.DEFAULT_CARDS
    run.DEFAULT_CARDS = run.DEMO_CARDS
    sys.addaudithook(_hook)
