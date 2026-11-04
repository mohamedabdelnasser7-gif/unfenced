# Review crossowner round 2
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, fix diff e68d121..f234f77 (11 commits). Filed by root from the hand-back. Mutants 67 killed, 10 survived (4 equivalent). Probes: scratchpad rv-crossowner2/probes.

Verdict: PASS (nothing blocking)

Every round 1 finding is proven fixed by a test that fails when the fix is reverted (review 1 to 4 and 6 to 10; red team 1 to 3). Review 5 waits for Mohamed; red team 4 accepted LOW by root.

1. LOW, reflection/night.py: a malformed or linked owner-id raises in Link.for_agent and the night stops for every agent of that owner; none of the callers catch OSError. Fix: catch Refused and OSError, run the study without the pool, add a note and a test.
2. LOW, shared.py and grow.py: with a broken pool file the writer is still asked before add() refuses (12 calls against 5 in a probe), every night. Fix: check the pool first and count it as failed.
3. LOW: lower case made-up shop names standing alone, fiver, tenner, score, quarter, ordinals, some Franco tens, and two place names still pass check(). Same root as red team r2 item 1. Plain openers for other kinds (Students, Members, Followers) are refused, which only drops patterns.
4. MINOR test gaps: E07 (a seal without the owner hash), K03, O02, P03, P04, P07.
