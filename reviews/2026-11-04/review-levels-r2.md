# Review levels round 2
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, fix diff de8b74a..a27acac. Filed by root from the hand-back. Stopped at the 250K cap with 14 of 63 mutants unrun. Probes: scratchpad rv-levels2/probes.

Verdict: FIX FIRST. Every round 1 finding is fixed and proven (each fix reverted fails its tests; mutants M1, M3, M8, M9, M31 killed; M18 equivalent).

1. BLOCKING, reflection/morning.py:1083 _level_gate. An item with no level (an old CLI gate run, practice.py --gate 7/10, or a trust file of 20 at high) still unlocks Connect, drawing 10 or 20 times from 6 customers, some trained. Fix: refuse an item whose level is None ("run the Arena again"); add level to the tests/test_connect.py fixture.
2. DRIFT, arena/practice.py:499-501 _write_item. The lost list holds never customers, who cannot be won, so the tiles, Correct this and Try again work on chats that cannot be won. Fix: keep cards where run.can_buy is true, and a never customer only when its loss failed a safety check.
3. MINOR, arena/practice.py:605-607 read_test. An entry with no from_card raises KeyError (still fails closed, no model call). Fix: e.get or refuse the missing key.
4. MINOR, test gaps: an unreadable matches file, the last round pick in the lost list, read_test dangling link, size cap and from_card type, a persona with no from_card, grown cards inside fixed_test. One test each.
5. Low: test-set.json is not sealed; a hand edit cannot pick a trained customer but can pick which kinds are tested (8/8/4 became 10/10/0). Fix if wanted: check the kinds against the full mix, or seal the file.

Ruled out: writer top-ups bounded; unreadable files stop before any model call; card fingerprint checked per id; Sales unchanged; Won again and Still lost map right; no secrets or XSS.
