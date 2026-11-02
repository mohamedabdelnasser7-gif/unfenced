"""Made-up agents for the engine tests. Each is only a plug: if one of them needs a change
in engine/ to run, the engine is not generic yet.

waterer: waters garden beds; a case is one bed. fan: runs a greenhouse fan, same field.
ledger: keeps a shop's books, another field. Each case names its own source.
"""
import copy
import json
import tempfile
from pathlib import Path

from engine import plug

WATERER = {
    "agent": "waterer",
    "about": "Waters garden beds on a round.",
    "case": "One garden bed.",
    "fields": ["gardening"],
    "stages": ["seedling", "grown"],
    "actions": {"water": "Water the bed.", "skip": "Leave the bed dry this round."},
    "results": {
        "soaked": {"speed": "fast", "shows_in_days": [0, 0], "after": "water", "about": "The soil took the water."},
        "ran_off": {"speed": "fast", "shows_in_days": [0, 0], "after": "water", "about": "The water ran off the bed."},
        "skipped": {"speed": "fast", "shows_in_days": [0, 0], "after": "skip"},
        "grew": {"speed": "slow", "shows_in_days": [3, 10], "about": "The plants grew."},
        "wilted": {"speed": "slow", "shows_in_days": [1.5, 5], "about": "The plants wilted."},
    },
    "causes": {"frost": "A night frost.", "pests": "Pests ate the leaves."},
    "source": {"about": "The bed itself; one case is one bed.", "known_by": "case"},
    "harm": {"results": ["ran_off"], "about": "Water that runs off is wasted and washes the soil away."},
    "decides": {"good": "grew", "bad": ["wilted"]},
    "risk": {
        "high": {"about": "High risk: chemicals and amounts.",
                 "words": {"chemicals": ["poison", "pesticide", "bleach"]},
                 "patterns": {"amount": ["[0-9]"]},
                 "tools": ["sprayer"]},
        "low": {"about": "Low risk: which bed to visit first, how long to wait between rounds."},
    },
    "trial": {"fast": {"share": 0.8, "days": 3}, "careful": {"share": 0.5, "days": 7}},
    "slot": "Notes from past rounds:",
}

FAN = dict(copy.deepcopy(WATERER), agent="fan", about="Runs a greenhouse fan.", case="One greenhouse.",
           actions={"spin": "Turn the fan on."},
           results={"spun": {"speed": "fast", "shows_in_days": [0, 0], "after": "spin"},
                    "stalled": {"speed": "fast", "shows_in_days": [0, 0], "after": "spin"},
                    "cooled": {"speed": "slow", "shows_in_days": [1.5, 3]},
                    "warmed": {"speed": "slow", "shows_in_days": [1.5, 3]}},
           source={"about": "The greenhouse itself.", "known_by": "case"},
           harm={"results": ["stalled"]}, decides={"good": "cooled", "bad": ["warmed"]},
           slot="Fan notes:")

LEDGER = dict(copy.deepcopy(WATERER), agent="ledger", about="Keeps the books.", case="One month of books.",
              fields=["bookkeeping"], stages=["open", "closed"],
              actions={"post": "Post an entry."},
              results={"posted": {"speed": "fast", "shows_in_days": [0, 0], "after": "post"},
                       "rejected": {"speed": "fast", "shows_in_days": [0, 0], "after": "post"},
                       "balanced": {"speed": "slow", "shows_in_days": [2, 30]},
                       "unbalanced": {"speed": "slow", "shows_in_days": [2, 30]}},
              source={"about": "The month of books itself.", "known_by": "case"},
              harm={"results": ["rejected"]}, decides={"good": "balanced", "bad": ["unbalanced"]},
              slot="Ledger notes:")

# A made-up agent whose case is settled by the courier (DECISIONS item 66): delivered decides good,
# refused bad, both slow, and no day count. Its ship action names the order in its detail, so the
# delivery webhook and the API check find its case (channels/bosta.py, reflection/late.py).
SHIPPER = dict(copy.deepcopy(WATERER), agent="shipper", about="Ships parcels for a small seller.",
               case="One parcel sent.", fields=["delivery"], stages=["sending"],
               actions={"ship": "Hand the parcel to the courier."},
               results={"shipped": {"speed": "fast", "after": "ship"},
                        "delivered": {"speed": "slow", "about": "The courier delivered it."},
                        "refused": {"speed": "slow", "about": "The buyer refused it at the door."}},
               causes={}, source={"about": "The parcel itself.", "known_by": "case"},
               harm={"results": ["shipped"]}, decides={"good": "delivered", "bad": ["refused"]},
               slot="Shipping notes:")


def load(data, test):
    """Write the plug to a file and read it back the way a real agent's plug is read."""
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    path = Path(d.name) / "plug.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return plug.load(path)


def changed(base, **changes):
    out = copy.deepcopy(base)
    out.update(changes)
    return out
