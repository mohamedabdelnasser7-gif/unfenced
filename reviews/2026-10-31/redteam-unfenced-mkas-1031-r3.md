# Red team round 3, unfenced-marketing-1031 and unfenced-assistant2-1031
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team (Fable 5.1). Five holes, all low, none blocking. Scripts: scratchpad rt-mkas3/.
1. LOW. Sign off words in STOP_LA let a surname like Best pass after a name (arena/words.py:109). FIXED by root 1f15768: SIGN_OFF is checked only for the word before a name.
2. LOW now, medium once live. assistant/arena.py:294, :338: a name above a long last line (address) or a tail over 4 lines skips the signature mask. Not reachable: keep_finished has no caller. Must be fixed before keep_finished is wired: mask every line from the sign off or signature block to the end.
3. LOW, same reach. assistant/arena.py:270: lower case names after with, and, و pass; a 4th name word passes. Fix before wiring.
4. LOW. engine/handover.py:185: the no repeat check ignored the kind. FIXED by root 61f7f8d (AND kind = ?), test fails on revert.
5. LOW. Two hands_over entries for one agent: not reachable, hands_over is keyed by agent in the plug.
Ruled out: two notes in one night, an unchanging case set (one note then quiet, intended), night_of on odd values, the trap mark skip, initials, the busy lock and 7 day clearing.
