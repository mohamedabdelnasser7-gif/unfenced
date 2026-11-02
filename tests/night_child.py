"""A stand in for the night command (python3 -m reflection.night), run by the scheduler tests as a
child process. It takes the same flags, writes what it saw to child.json next to the database and
does what NIGHT_CHILD_MODE says: "exit N" ends with N, "sleep" never ends by itself, "bleed" changes
its own env and logging the way a night's exam does, then ends with 0."""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plug")
    ap.add_argument("--db")
    ap.add_argument("--until", type=float)
    args = ap.parse_args()
    mode = os.environ.get("NIGHT_CHILD_MODE", "exit 0")
    seen = {"pid": os.getpid(), "cwd": os.getcwd(), "argv": sys.argv[1:], "until": args.until,
            "store": os.environ.get("SHOPIFY_STORE")}
    (Path(args.db).parent / "child.json").write_text(json.dumps(seen), encoding="utf-8")
    print(f"stand in night of {args.plug}: {mode}", flush=True)
    if mode == "sleep":
        time.sleep(120)
        return 0
    if mode == "bleed":
        os.environ.pop("SHOPIFY_STORE", None)
        logging.disable(logging.WARNING)
        return 0
    return int(mode.split()[1])


if __name__ == "__main__":
    sys.exit(main())
