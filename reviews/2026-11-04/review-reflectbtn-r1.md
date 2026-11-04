# Review reflectbtn round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Quick check, reviewer at high, d470fba..61580d8 (decisions 92, 93, 95). Filed by root from the hand-back. Probes: scratchpad rvreflect1. 88 tests pass in the touched modules; 14 mutants, 8 killed.

Verdict: FIX FIRST (2 medium, 4 low)

1. MEDIUM, Sales dead end: Run reflection on Sales says run the Arena first, but run_arena refuses Sales and arena/run.py --db writes cases to an arena copy, never the page database. The assistant and marketing plugs show the same line.
2. MEDIUM, the no key line points to recorded/play.py, which holds a scripted Arena run and a Sales chat, no reflection. Decision 92 promised a real recording.
3. LOW-MEDIUM, morning.py:1078-1085: Ctrl+C mid run leaves the night lock until STALE (6 h). Fix: host and pid in the holder; take over when that pid is gone.
4. LOW, Run the Arena and the manual night take no night lock; docs promise only what the code guards.
5. LOW, test gaps: no test proves exam and judge calls count (no fake writes a lesson); no test that a raising start frees the lock.
6. LOW, a built agent's exam rerun counts twice on the cap; Sales rerun calls are missing from the run's count. Fix: one Calls passed through binding and wrap_turn.
Stale: judges.md:54 says only the Sales agent makes data/ascent.db.

Ruled out: CSRF and CSP on the new route; escaping; the empty database creation; lock freed on raise, cap and errors.
