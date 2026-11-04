"""Example agents a fresh clone shows on Agents (2026-11-04).

Each folder under examples/agents/<name>/ in the repo is an agent as Quick start's Build writes it
(reflection/quickstart.py): plug.json, instructions.md, card.json, exam.json, level.json, its sample data
and its made-up practice customers. It holds no lessons, no Arena matches and no saved run: like every
agent, it starts from zero and earns each lesson in the Arena.

install() copies each one into the page's agents folder (<db folder>/agents/<name>/, kit/turn.py AGENTS)
when python3 -m unfenced starts on its own database, so the example then runs exactly like an agent
made in Quick start. Only the files above are copied. An example is copied once per agents folder:
never over a folder that is there, never on a name an agent on the page or a built-in agent has
(quickstart.taken_line), and never again after it was copied once, so an example the user removed
stays removed. The names copied are kept in <db folder>/agents/.examples.json, a hidden file the
agents list never reads.
"""
import json
import logging
import os
import secrets
import shutil
from pathlib import Path

from engine import plug as plug_mod

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "agents"
MARK = ".examples.json"
FILES = ("plug.json", "instructions.md", "card.json", "exam.json", "level.json", "sample-data.json", "offers.json")
CARDS = "practice-cards"
MAX_MARK = 16_000


def _copied(agents):
    """The names copied before, or None when the mark is there but cannot be read (then nothing is copied)."""
    path = agents / MARK
    if not path.exists() and not path.is_symlink():
        return set()
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MARK:
            return None
        names = json.loads(path.read_text(encoding="utf-8")).get("copied")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        return None
    return set(names)


def _mark(agents, names):
    tmp = agents / f"{MARK}.{secrets.token_hex(4)}.tmp"
    tmp.write_text(json.dumps({"copied": sorted(names)}) + "\n", encoding="utf-8")
    os.replace(tmp, agents / MARK)


def _plain_file(p):
    return p.is_file() and not p.is_symlink()


def _copy(src, agents, name):
    """The example's files into agents/<name>, written whole: a hidden folder first, renamed into place."""
    tmp = agents / f".{name}.{secrets.token_hex(4)}.tmp"
    tmp.mkdir()
    try:
        for f in FILES:
            if _plain_file(src / f):
                shutil.copyfile(src / f, tmp / f)
        cards = src / CARDS
        if cards.is_dir() and not cards.is_symlink():
            (tmp / CARDS).mkdir(mode=0o700)
            for p in sorted(cards.glob("persona-*.json")):
                if _plain_file(p):
                    shutil.copyfile(p, tmp / CARDS / p.name)
        target = agents / name
        if target.exists() or target.is_symlink():
            return False
        os.rename(tmp, target)
        return True
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def install(db_path, taken=(), source=SOURCE):
    """Copy each example agent not copied before into <db_path's folder>/agents/. taken: the names of the
    agents on the page (the repo's plugs). Returns the names copied now. Nothing is copied when the agents
    folder is not a plain folder or its mark cannot be read; an example that fails is left out and logged."""
    from reflection import quickstart
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        return []
    try:
        agents = quickstart._agents_dir(Path(db_path).resolve().parent)
    except quickstart.Refused as e:
        log.warning("example agents not copied: %s", e)
        return []
    copied = _copied(agents)
    if copied is None:
        log.warning("example agents not copied: %s cannot be read", MARK)
        return []
    taken = set(taken)
    done = []
    for src in sorted(source.iterdir()):
        name = src.name
        if name in copied or name.startswith(".") or src.is_symlink() or not src.is_dir() \
                or not plug_mod.AGENT_NAME.fullmatch(name):
            continue
        if quickstart.taken_line(name, taken, agents) is not None:  # the user's own agent of that name stays
            continue
        try:
            if _copy(src, agents, name):
                done.append(name)
        except OSError as e:
            log.warning("example agent %s not copied: %s", name, e)
            continue
    if done:
        _mark(agents, copied | set(done))
    return done
