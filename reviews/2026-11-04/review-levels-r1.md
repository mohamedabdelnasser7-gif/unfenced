# Review levels round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier (the level unlocks Connect, so go-live), 5d6e6d9..de8b74a against DECISIONS 84 and 85 (with 77, 80, 81). Filed by root from the hand-back; root read the cited code. Suite 3,213 OK; mutants 25 of 30 killed.

Verdict: FIX FIRST

1. BLOCKING, reflection/morning.py _level_gate: the run is scored against the current level with the run's own gate size and no minimum. A trust file of one match unlocked Connect for a high agent; a medium run of 10 raised to high unlocks at 8 of 10 (same as red team 1). Fix: also require played at least the level's gate size.
2. BLOCKING, arena/practice.py test_set with arena/madeup.py top ups: the test set is recomputed over whatever customers are on disk, so after 6, 20 and 30 customer top ups, 3 to 5 who trained at medium land in the high test set. Breaks decision 85 (test customers never studied). Fix: store the test ids, or leave out every customer that played a training match and write more to cover the gap.
3. DRIFT, reflection/morning.py with arena/run.py rounds_item: Try again for a built agent replays the last test round's losses, so test customers. Decision 81 says practice customers. Fix: give Try again the last round's lost training matches.
4. MINOR, arena/practice.py _passed: unjudged test matches are skipped, so 16 won of 17 played stops the run as passed (Connect stays locked, no blocks shown). Fix: require played equal to the gate size.
5. MINOR, reflection/pages.py: a test round cut short by the cap shows N of 10 as if all 10 were played. Fix: show played when it is below the size.
6. MINOR, test gaps from surviving mutants M3, M8, M9, M31 (M18 equivalent).

Ruled out: POST /arena/level forgery; Try again unlocking Connect; quick or unsealed runs unlocking; cap hits passing; lowering touching lesson risk; the 1,500 cap leaking; old gate and quick shape; test customers playing more than once a round.
