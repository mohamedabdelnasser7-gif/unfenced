"""The personal assistant, the second agent on the engine (new, 2026-10-31; spec
notes/personal-assistant-spec-2026-10-31.md, DECISIONS items 18, 36, 37, 38).

PLUG is its plug, read from assistant/plug.json: a case is one day, the stages are the modes.
"""
from pathlib import Path

from engine import plug as _plug

HERE = Path(__file__).resolve().parent
PLUG = _plug.load(HERE / "plug.json")
