# Red team levels round 3
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team, last round, short, on the fix lines a27acac..208166b. Filed by root from the hand-back. Scratch copy, fake data, no model, no network.

1. CONFIRMED MEDIUM (carried from round 2 finding 2), arena/practice.py:693 with the field written at :422. The test_match field and the -g id both live in arena-matches.jsonl, so whoever can write the agent folder can relabel a training line as a test match, hide that the customer trained, and list that customer in test-set.json; a sealed gate run on that test set passes too easily. The seal signs the run's item, not its inputs. Fix: tie each match line (or the file) to the seal key, so a rewritten or hand written line counts as training or refuses.
2. LOW, same root: whoever can write test-set.json chooses which never trained customers fill each kind. Same fix.
3. RULED OUT: old format lines (count as training), mixed lines, a symlinked parent folder, a hard link, a deleted then recreated matches file (deterministic rebuild, no contamination), truncation mid line (refused), a test set with the wrong kinds (rebuilt).
4. RULED OUT: the Connect gate (no level, a hand written level breaks the seal, old gate runs, raising and lowering the level).
5. RULED OUT: a permanent owner lockout. A bad file stops new full runs until the owner cleans it up; an existing pass is not revoked; quick runs are unaffected.
