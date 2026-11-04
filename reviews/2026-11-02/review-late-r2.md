# Review late round 2
*Created: 2026-11-02. Last updated: 2026-11-02.*

Reviewer Opus max (handed back at its cap after the sweep; note PROGRESS-late-r2-reviewer.md in the session scratchpad) and red team Fable 5.1 max, fix diff ae34884..a6b9999. Filed by root. Every round 1 finding fixed and proven by a test that fails on revert. Full suite 112 modules OK. Sweep 52 mutants, 38 killed, 14 survived.

Reviewer
1. MEDIUM drift from 67, engine/log.py:133-135 (the round 1 window fix): the per pattern second signal (study.py second_counts) never shows a delivery that lands after the 2 day Sales window; deliveries take 2 to 7 days. Proof: 15 nights, fixed tree 0 delivered, old tree 160. Open: his call, A count by case id as results land, B drop the per pattern line.
2. LOW scheduler.py:162-171: the server stopping mid night leaves the child running with no limit (daemon thread, the kill never runs); next server locked out until STALE. Open.
3. LOW bosta.py:416-417: slow headers pass the deadline; capped by the night limit. Documented in 9ee59a9.
Test gaps from the sweep: killpg and the new session, claim and _had each alone, the across plug pass (study.py:545), late() ignoring the agent, a shared reference on late_mark and in a sheet, a three column sheet row; the API size cap test is vacuous (non JSON body). Open, cheap ones with the next fix.

Red team
1. LOW slow header drip, same as reviewer 3. Documented 9ee59a9.
2. LOW nights.log unbounded, umask perms. Fixed 9ee59a9 (0600, 5 MB then nights.log.1).
Cleared: body drip, group kill, stale lock while the child runs, HMAC key leak, child argv injection, case_ref_key.
