# Red team levels round 2
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team, short round, on the fix lines de8b74a..a27acac. Filed by root from the hand-back. Scratch copy, fake data, no model, no network.

1. Connect gate: RULED OUT on every variant (small or relabelled run, raising the level between runs, lowering then raising, a cut run, trust files edited, two runs summed, an edited item). The floor in reflection/morning.py _level_gate (1073, 1083 to 1085) closes round 1 finding 1.
2. CONFIRMED MEDIUM, arena/practice.py trained() :628. The fixed test set trusts arena-matches.jsonl to say who trained, and that reader is not fail closed: it follows a symlink (:638), skips a corrupt line (:641 to 643), treats any id ending -r<n>-g<n> as a test match (:645), and reads a deleted file as no training (:634). With write to the agent folder (not the seal key) a trained customer can be put into the test set, or hard customers pushed out, so a sealed gate run passes too easily. Fix: refuse a symlinked or non file matches file as read_test does; an unreadable line fails closed or counts as unknown training; classify test and training on a recorded field, not the id string; consider tying the files to the seal key.
3. RULED OUT: the writer top-up loop (at most 6 passes, never over 99 customers, every call on the day cap).
4. RULED OUT: Try again replaying practice losses (training only; in memory Db; never counted by the gate).
