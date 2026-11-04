# Red team round 2: unfenced, branch handoff, fix diff 5d60f6e..ed9efb0
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team, short, saved by root from the hand-back. Proof: session scratchpad redteam-handoff2-r2/attack_race_r2.py (28 runs). Suite in copy 2399 OK. No critical, high or medium.

1. Close mid-turn and stale-view variants: RULED OUT (kit/chats.py:142-150, 190-222; sales/loop.py:200-203; sales/quiet.py:62).
2a. Chat open forever: RULED OUT. Residual low by design: the third requeue waits with no hold (needs three restarts).
2b. LATE and migration: RULED OUT for dropping a real chat or a wrong recipient. Low: _close_old (kit/chats.py:118-124) ignores the pending hold, so a message accepted before the stop lands in a new chat once; fix: add NOT PENDING_FOR. Low: serial notice sends with a 20 s timeout can push the next tick past LATE in a Graph outage (covered by review r2 finding 1).
2c. correct() raising: RULED OUT (no live caller; a future page caller must pass an exam).
3. LOW, CONFIRMED (V5): kit/db.py:28-37 tx() does not nest; in quiet._close chats.close commits before results.result, so a failing result write leaves a closed chat with no chat_closed row. Fix: depth-counted tx or savepoints.
Process: the pack copy was rewritten during the run (mutant sweep sharing copy/); give each agent its own copy.
