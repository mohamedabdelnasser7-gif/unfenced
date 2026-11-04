# Review round 3 (last): unfenced, branch handoff, fix diff ed9efb0..c891080
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. 30 mutants plus 3 gap reverts; probes p1 to p4 in session scratchpad rv-ho2r3/. Suite 2416 OK.

Verdict: FIX FIRST, 1 low (one line, fixed in session).

All round 2 findings fixed and proven by tests that fail on revert (F1 p2 notice at 36.2 min, F2, F3 p1 0 ms at 300k rows, minor 4, red team 3 and 2b, test gaps). Nested tx safe for every caller (instrumented suite; only quiet._close nests).

1. LOW, CONFIRMED. kit/chats.py:196-198, 438-443, channels/whatsapp.py:622-626: the 30 min hold counts from arrival, not from the restart's requeue; after a stop over 30 min the first tick can close a chat before the worker reaches the requeued message (p4: new chat, chat_closed written). Fix: pending() sets the arrival time to now when it counts an attempt; order by at, rowid; p4 as a test.

Survivors, test gaps: K9 (_close_old in the column loop, no older seen_messages fixture); D4 and D7 (kit/db.py:57-59, inner error hidden or swallowed); K5 equivalent.
