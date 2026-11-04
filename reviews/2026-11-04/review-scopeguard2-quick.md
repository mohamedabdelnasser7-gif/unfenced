# Review scopeguard2 quick check
*Created: 2026-11-04. Last updated: 2026-11-04.*

Quick check after round 3 (decision 91), reviewer at max, fix diff 2af919e..5b0481e. Filed by root from the hand-back. Probes: scratchpad rv-scope2-q. The three blockers are proven fixed (reverts fail 270, 17 and 13 tests; Egyptian negation mutants all killed). Suite 3627 OK. Sweep: 31 mutants, 27 killed. rt3 misses fall from 79 to 41.

Verdict: FIX FIRST (1 medium, 6 low)

1. MEDIUM, reflection/exam.py:131 and :604. Any digit after a decline counts as the work, so hand off refusals pass ("the team will reply within 24 hours", a phone number, "open 24/7"). Fix: a number counts only as a store fact (did amounts, a catalogue size, an order in did orders); test the hand off shapes.
2. LOW, unconfirmed, exam.py:604. A tool ran but none of its facts reached the customer still passes. Fix: when a tool ran, still require one of its facts after the decline.
3. LOW, situation 34 work_facts "name" lets "What's your name?" pass. Fix: let the 400 price and print words carry 34; "name" only next to a print word.
4. LOW, situation 42 is a limit with no note. Fix: drop limit or name the fair no.
5. LOW, test gaps: exam.py:752 JUDGE_CALLS in the recheck cap, :872 main passing the judge, night.py:331 sales_exam judge_model, :517 HEADING empty head guard.
6. LOW, unconfirmed, exam.py:559-562. A judge "no" drops the whole floor. Fix: keep the REVEAL_AFTER match as a floor even when the judge says no.
7. LOW, exam.py:268 reveal_judge reads the Sales card; no change now, hand turn_exam its own card if it ever gets a reveal situation.

Ruled out: the merge in arena/practice.py keeps both sides; no new key handling; judge calls not counted twice; long reply handling.
