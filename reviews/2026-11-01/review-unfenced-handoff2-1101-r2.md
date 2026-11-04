# Review round 2: unfenced, branch handoff, fix diff 5d60f6e..ed9efb0
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Suite in copy: 2399 OK. Probes and sweep: session scratchpad rv-ho2r2/ (p1_scan, p2_slow_sweep, p3_stuck_pending, sweep.txt, spec.json, spec2.json). 45 mutants.

Verdict: FIX FIRST (1 medium, 2 low, 1 minor, test gaps).

1. MEDIUM. sales/quiet.py:64-66 with channels/whatsapp.py:502-508: the 5 minute LATE bound uses the wall clock, but the tick shares the thread with the fast reflection sweep (up to 20 model calls, 30 s each). A notice due during a slow sweep is skipped and the chat closes silently about 36 min after the last message; a yes at minute 40 starts a new chat. Departs from DECISIONS 54. Fix: close silently only when the notice was due before this process started (App start time passed to tick); any later notice goes out however late. Slow sweep test; dated note on item 54.
2. LOW. kit/chats.py:112-114: the pending hold has no age limit; a message stuck pending with 0 attempts holds the chat open until a restart (1, 6, 48 hours in p3). Fix: count pending only when younger than CLOSE_AFTER.
3. LOW. kit/chats.py:183, 200: PENDING_FOR scans all seen_messages per open chat per tick; no index, never pruned; 300k rows and 100 chats hold the lock 570 ms every 30 s. Fix: partial index on pending rows.
4. MINOR. sales/quiet.py:104: a late close records quiet_minutes 60.

Earlier findings: all proven fixed by tests that fail on revert, except finding 2's SQL pending guard alone (survives; only both guards together are killed).
Test gaps (survivors): loop.py:203 upto=n - 1 (message sent to the model twice, uncaught); failed_turn transaction revert; SQL pending guard alone; migration role filter and created_at only (fixture too close); STOCK_COUNT "is" case ("1 pair is in stock.").
Callers: correct() has no live caller; _card, view and approve share WANTS_YES; Results and Chats share one Db.
