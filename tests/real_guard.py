"""No test reads arena/real/ (new, 2026-10-31; DECISIONS items 23 and 40).

The Arena's default cards are the cleaned real cards (arena/run.py DEFAULT_CARDS, arena/real/cards).
The tests play the made-up set instead: install() points DEFAULT_CARDS at DEMO_CARDS for the whole
suite, and adds an audit hook that refuses any open of a file under arena/real/, and any database
opened there, before the file is read. Listing the folder's names is allowed. The refusal is a
RealRead, a BaseException, so no "except Exception" in the code under test can swallow it: the
test that tried fails. tests/__init__.py calls install() once, before any test module loads.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = os.path.normcase(os.path.abspath(ROOT / "arena" / "real"))
EVENTS = ("open", "sqlite3.connect", "sqlite3.connect/handle")
REAL_DEFAULT = None  # arena/run.py DEFAULT_CARDS as shipped, kept for the test that checks it
refused = []  # every path refused this run


class RealRead(BaseException):
    """A test tried to read a file under arena/real/."""


def under_real(path):
    if isinstance(path, int) or path is None:  # an open file descriptor, or no path
        return False
    try:
        p = os.fsdecode(os.fspath(path))
    except TypeError:
        return False
    if not p or p == ":memory:":
        return False
    p = os.path.normcase(os.path.abspath(p))
    return p == REAL or p.startswith(REAL + os.sep)


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
