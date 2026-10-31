"""Where private Arena files may sit: outside the repo, and Arena state also under its ignored data/ folder.

The checks ignore case and Unicode form, since a Mac folder opens under any case and either form (DECISIONS item 17).
"""
import unicodedata
from pathlib import Path

from reflection import history

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _parts(p):
    return [unicodedata.normalize("NFC", x).casefold() for x in Path(p).expanduser().resolve().parts]


def within(p, folder):
    """True when p is folder or sits under it, case ignored, or when the real folder is one of its
    parents on disk (a second name for the same folder, such as /System/Volumes/Data on macOS)."""
    a, b = _parts(p), _parts(folder)
    return a[:len(b)] == b or history.within(Path(p).expanduser(), folder)


def inside_repo(p):
    return within(p, ROOT)
