"""The Sales agent's binding to the learning engine (engine/).

PLUG is the Sales agent's plug, read from sales/plug.json. results.py and lessons.py
give the engine's log and lessons the names the Sales agent code already uses: a case is
one chat, and a result is an outcome.
"""
from pathlib import Path

from engine import plug as _plug

PLUG = _plug.load(Path(__file__).resolve().parent.parent / "sales" / "plug.json")
