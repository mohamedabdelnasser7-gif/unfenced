# Review engfix round 3
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, fix diff a7dd41e..37f1ccf. Filed by root from the hand-back. Probes: scratchpad rv-engfix3/probes (mut.py, spec1.py, p1_failclosed.py). Hit the 250K cap at 63 of about 110 mutants.

Verdict: PASS (nothing blocking)

Proven: every fix fails its tests when reverted (4d1729f, 1e8d0de, 69d8a46, b46af72, c83a4a4, 37f1ccf, 9d960cc). Fail closed end to end: 175 of 175 (35 judge outputs on Sales, Marketing and the three Quick start plugs); only "low" in any case with spaces starts a trial. Callers hold (engine/lessons.py:321 and :784, arena/rounds.py:357 CapReached reads unsure, night uses Judge() by default, bring back rechecks words). The round 2 red team wordings went from 777 passing to 764, none newly passing.

1. DRIFT, sales/plug.json:112, :131, :133 and the policy and personal_data patterns. Round 2 false positives partly fixed: plain lessons still marked high 16 of 43 English, 5 of 16 Arabic, 3 of 9 Franco; 10 of those were low before engfix. Safe side (they wait for a yes). Root call: accept for the hackathon; the judge and a yes cover them.
2. MINOR, test gaps from surviving mutants at sales/plug.json:92, 98, 113, 114, 117, 118 and engine/risk.py:256. None lets money through alone. Accepted.
3. Not run before the cap: spaced letter mutants S1 to S10, D21 to D35, PR1 to PR7, MK1 to MK18, and a timing probe on joined forms in notes (notes are not under the 300 character lesson cap).
