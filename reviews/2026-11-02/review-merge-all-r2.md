# Review merge-all round 2 (reviewer, max)
*Created: 2026-11-02. Last updated: 2026-11-02.*

Fix diff f52819d..465404b. Verdict PASS. All 8 round 1 findings fixed, each proven by reverting the fix and running its own test (10 of 10 failed on revert). Sweep 41 mutants, 34 killed, 2 equivalent, 5 survived. Probes in the session scratchpad review-merge-all/r2.

1. LOW arena/notes.py:87. The losing reply's name check is capital based; Arabic, Franco and lower case names pass. Fix: refuse when arena/clean.py ChatCleaner marks a name over the customer lines plus the reply.
2. LOW reflection/exam.py:75, :239. Any exchange word allows 14 for every day count; bare بدل counts. Fix: the same clause only; drop bare بدل.
3. LOW reflection/quickstart.py:188. Finding 3 partly fixed: step in, jump in, get back, call them back, join, pick up still pass in a tag line. Fix: excuse only handle and deal with.
4. LOW arena/practice.py:218 with match.py:183. No deadlock, but the page waits a whole practice match per exam situation. Fix: enter demo_store once per agent turn.

Test gaps: night.py:440 too large line; known= in the losing reply check; follow up, carry on, go on in tag tests; scheduler.py:201 fstat error; RLock vs Lock (equivalent today).
Ruled out: nothing the agent reads says check with the team (assistant/simday.py:44 is the other agent); a hotfix is never handed twice.
