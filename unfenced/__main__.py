"""The one command to start from (python3 -m unfenced).

    python3 -m unfenced [options]           the page, as python3 -m reflection.morning, every option passed through
    python3 -m unfenced arena [options]     the Arena, as python3 -I arena/run.py
    python3 -m unfenced night [options]     one night study, as python3 -m reflection.night

Run it from the repo's root folder. With no --db, --demo-days or --html and no database at data/ascent.db
yet, it makes that database empty first, so the page opens on a fresh clone; the Sales agent writes to the
same file once it runs. A database named with --db is never made here: the page refuses one that is not there.
"""
import sys
from pathlib import Path

from kit.db import DEFAULT_PATH

SUBCOMMANDS = ("arena", "night")


def _own_database(argv):
    """The page opens the default database: no option that names another, the sample days, a file or help."""
    return not any(a.startswith(("--d", "--h", "-h")) for a in argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["arena"]:
        from arena import run
        return run.main(argv[1:])
    if argv[:1] == ["night"]:
        from reflection import night
        return night.main(argv[1:])
    from reflection import morning
    path = Path(DEFAULT_PATH)
    if _own_database(argv) and not path.exists():
        from kit.db import Db
        path.parent.mkdir(parents=True, exist_ok=True)
        Db(str(path)).close()
        print(f"No database yet, so an empty one was made at {path}. Build an agent on New agent to start.")
    return morning.main(argv)


if __name__ == "__main__":
    sys.exit(main())
