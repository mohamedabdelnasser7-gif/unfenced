"""Rows and offers the user adds on the page for the Sales agent (2026-11-05).

An agent made in Quick start, an example agent and the personal assistant keep their sample data and offers
in their own folder beside the database (<db folder>/agents/<name>/, kit/sample.py and kit/offers.py). The
Sales agent has no such folder: its products are the store's (Shopify, or the demo catalogue in demo/) and
its offers the store data's (demo/offers.json), both repo files that are never written. What the user adds
for it on its Overview goes beside the database instead, in <db folder>/added/sales/, in the same two files
and shapes: sample-data.json (rows, marked as the user's) and offers.json (only the added offers).

The readers take them from there: the store tool's catalogue adds the rows that read as products to the demo
catalogue when no Shopify keys are set (real keys always win, as for a built agent's sample products), and
the store data's offers (kit/offers.py demo) add the added offers after the demo file's. So the Sales agent's
replies, its page chat and its Arena matches read them.

The database folder is the process's: the live page sets it when its Morning starts with a database path,
and the WhatsApp channel sets it to the database it opens. Unset (the sample days, the tests that start no
page), nothing is added and the repo data reads as before.
"""
from pathlib import Path

FOLDER = "added"
SALES = "sales"

_home = {"db_folder": None}


def use(db_path):
    """The database this process runs on; its folder holds the added data. None clears it."""
    _home["db_folder"] = None if db_path is None else Path(db_path).resolve().parent


def folder(agent=SALES, make=False):
    """The folder of what the user added for this agent, or None when no database is set or it is not a plain
    folder. make: create it (and <db folder>/added/) when it is missing."""
    base = _home["db_folder"]
    if base is None:
        return None
    top = base / FOLDER
    f = top / agent
    if make and not f.exists() and not f.is_symlink():
        if top.is_symlink():
            return None
        f.mkdir(parents=True, exist_ok=True)
    if top.is_symlink() or f.is_symlink() or not f.is_dir():
        return None
    return f


def rows(agent=SALES):
    """The rows added for this agent (kit/sample.py read), or None."""
    from kit import sample
    f = folder(agent)
    return None if f is None else sample.read(f)


def offers(agent=SALES):
    """The offers added for this agent (kit/offers.py read), or None."""
    from kit import offers as offers_mod
    f = folder(agent)
    return None if f is None else offers_mod.read(f)
