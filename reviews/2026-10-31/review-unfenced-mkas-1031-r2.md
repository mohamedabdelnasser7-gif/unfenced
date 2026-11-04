# Review round 2, unfenced-marketing-1031 and unfenced-assistant2-1031
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer (Opus, max), fix diffs marketing 0b2daf4..760d131, assistant 2f3854f..00a2f48. Saved by root; reported until checked. Files: scratchpad rv-mkas2/.

## Marketing: PASS
Round 1 items fixed and proven (all 3 reverts killed).
1. LOW, CONFIRMED. handover.py:78 to 82 with night.py:202: a run a few seconds earlier than the night before overlaps and writes nothing; days=2 gave 4 of 10 nights, one day of cases never in a note. Fix: allow a small overlap (one hour) or key on the Cairo date.
Mutants 16 of 25. Gaps: more sources with fewer cases, two senders, since <= edge.

## Assistant: FIX FIRST
Round 1 fixes hold (15 of 17 reverts killed).
1. MEDIUM, CONFIRMED, new. arena.py:98, :270: a sign-off line mid mail cuts the rest (the ask and a trap are lost). Fix: cut only when what follows is at most 4 lines, 200 characters, no question mark.
2. MEDIUM, test gap. arena.py:338: display names not tested (someone@example.com, Karim Tawfik El Sherbiny).
3. LOW, test gap. Typed single fields (at, own_mode, kind, counts) untested with a name and phone.
4. LOW, CONFIRMED. arena.py:533: a second night at the same time moves the first night .taken aside; quarantine never deleted. Fix: non-blocking lock before moving; delete quarantine after N days.
5. LOW. arena.py:241: date put-back accepts any year. Fix: 2000 to 2100 only.
6. LOW. A display name of ordinary words masks them all day. Fix: only name-like words.
Mutants 29 of 60. Gaps listed in the hand-back (NEAR, MAX_TEXT, filters, lock and link checks, quarantine mode).
