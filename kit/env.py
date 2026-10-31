"""A tiny .env loader. Reads KEY=VALUE lines into os.environ.

Values already set in the environment win. Nothing is ever printed. An unquoted value ends
before an inline comment (a space or tab, then #): KEY=abc # mine gives abc. A quoted value is
kept as written between its quotes.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_COMMENT = re.compile(r"\s+#.*$")


def load(path=None):
    """Load the repo's .env (or the given file). Returns the names it set."""
    path = Path(path) if path else ROOT / ".env"
    if not path.is_file():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif value[:1] not in ("\"", "'"):
            # " # mine" after the = (the space went before group 2) is a comment with no value
            spaced = value.startswith("#") and line[m.start(2) - 1].isspace()
            value = "" if spaced else _COMMENT.sub("", value)
        if name not in os.environ:
            os.environ[name] = value
            names.append(name)
    return names


def get(name, default=""):
    return os.environ.get(name, default).strip() or default
