# Review levels round 3
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, last round, fix diff a27acac..208166b. Filed by root from the hand-back. Probes: scratchpad rv-levels3/probes. 13 of 14 fix reverts fail the new tests; the one that does not (the mix argument) is covered by the whole revert. Sweep: 53 mutants, 34 killed, 19 survived (11 equivalent).

Verdict: PASS (all findings minor)

1. MINOR, arena/practice.py:671-698 with reflection/morning.py:910. A torn last line or a missing matches file stops every later run, and the page gives no way out. Fix: the note names the file and the one step to take, or a page reset starts a new test set from new customers and counts every old one as trained; never skip the bad line.
2. MINOR, arena/practice.py:425 with arena/retry.py. A never customer kept on the lost list always reads lost on Try again, even after the slip is fixed. Fix: judge a never customer's Try again on its safety checks only, or keep it off Try again with a plain line saying why.
3. MINOR, reflection/pages.py:995-1010 and practice.py blocks() 462-489. An unjudged test match shows as "9 won of 9 played (the run stopped before all 10)", and the help line suggests steps that cannot pass. Fix: say one test match could not be judged, add an unjudged block, drop the help line there.
4. MINOR, practice.py:831. No test for the refusal when the test set cannot be filled (the guard that keeps the round 2 blocker closed). Fix: a test expecting run.Refused and no item.
5. MINOR, practice.py:823. No levels run with blended customers. Fix: one test on owner cards.
6. MINOR, practice.py:805 and 828. No test for the 5 top ups or the plain refusal at 99. Fix: a writer that repeats people.
7. MINOR, practice.py:824. Passing mix to fixed_test is untested. Fix: a hand edited test set of 10 easy, then a medium run keeps 4/4/2.

Builder calls accepted: old lines count as training; a test set with no matches file is refused (a fresh install cannot hit it); top ups bounded; no size cap on the matches file; no seal on test-set.json.

Outside the fix lines: arena/gate.py:370 FreshTurn._wins reruns every past win, test matches included, when it examines a lesson (on main before levels); the test_match field could filter it. scopeguard2 holds the round 2 code; merge levels first.
