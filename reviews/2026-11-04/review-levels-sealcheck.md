# Review levels seal check
*Created: 2026-11-04. Last updated: 2026-11-04.*

Short check after round 3, reviewer at max, on f5c4b57..151d083 (decision 90). Filed by root from the hand-back. Probes: scratchpad rv-levels4/probes. Suite 3473 OK; 18 reverts, 15 killed. The merge keeps both sides; the seal and roster hold on every case but one; a fresh agent's first quick and full runs work.

Verdict: FIX FIRST

1. MEDIUM, arena/practice.py:860-884 keep_trained. Deleting all three record files makes the folder read as never run, so a trained customer can join the next test set. Fix: when the roster is built for a folder with none, add every saved practice card as trained, as new_test_set does; tests call keep_trained before writing customers; add the delete all case.
2. LOW, arena/gate.py:282-294 CorrectionRound.cards still plays saved test customers. Fix: leave out read_test ids; test it.
3. MINOR, practice.py:905 and 1124. Repeated resets hit the 99 customer cap and the refusal names no way on. Fix: name lowering the level, or warn at reset.
4. MINOR, test gaps: the seal check in is_test, quick runs checking the record, keep_trained's refusal when the roster is gone.
5. MINOR, practice.py:1167-1206. The command line has no way to start a new test set. Fix: a --new-test-set flag named in the refusal.

Accepted: rollback of a whole old folder copy; a sibling copy of test-set.json (trained and fingerprint filters still hold); key readers can seal anything (kit/seal.py says so).
