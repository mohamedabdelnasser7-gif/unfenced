# Red team round 3 (last): unfenced, branch handoff, fix diff ed9efb0..c891080
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team, short, saved by root from the hand-back. Proofs: session scratchpad redteam-handoff2-r3/attack_r3.py, attack_r3b.py. No critical, high or medium.

Ruled out: nested tx (V5) fixed by savepoints (kit/db.py:29-64, sales/quiet.py:106-112); _close_old pending fixed (kit/chats.py:128-137); inner error caught inside an outer tx; savepoints with the RLock across threads (8x50, no deadlock); PENDING_HOLD keeping a chat open (30 min at most); requeued message in a new chat (by design); seen_pending index on new, old and older databases.

1. LOW, CONFIRMED. sales/quiet.py:72-76 with channels/whatsapp.py:455: a notice due just before started is skipped with zero slack (restart 0.5 s after it falls due gives a silent close); a process started on a future clock then corrected back closes fresh chats silently until the next restart. Only the courtesy notice is lost. Fix: a grace window, since + NOTICE_AFTER < started - GRACE.
