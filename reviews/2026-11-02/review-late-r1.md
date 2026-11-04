# Review late round 1
*Created: 2026-11-02. Last updated: 2026-11-02.*

Reviewer Opus max (stopped at its cap, partial; progress note in the session scratchpad PROGRESS-adac9e14a04ce52c3.md) and red team Fable 5.1 max, branch late 44c3bc1..ae34884 plus smallfix abb4e66. Filed by root from the hand backs. Root opened every cited line. Verdict: ISSUES.

Reviewer
1. HIGH scheduler.py:137-140 with whatsapp.py:642. The night runs inside the WhatsApp server's process; the exam and Arena rerun (demo_store) strip SHOPIFY_* and OPERATOR_WHATSAPP from os.environ, disable warnings and reset the store cache for the whole process, so a live turn during a night sees the demo store (a real order lands in demo_orders) and live warnings drop. Fix: the night in a child process with a time limit. Open.
2. MEDIUM drift from 67: a second signal row saved today pulls an old good Sales case into tonight's study (engine/log.py window). Fix: count a case only for a row in the window that is not a second signal. Open.
3. LOW late.py:119 saves API results at the night's own until, read at < until, so tonight still sees the case pending. Open.
4. LOW morning.py:2311 shows_in_days None crashes the A3 render for built agents' ideas. Fixed in 7adf837 with test.
Not done: full suite run, mutant sweep, red team cross check (round 2).
Smallfix: PASS (same exam rows over 50 situations for 3 fixed models).

Red team
1. MEDIUM no time limit on a night: a dripping courier answer (bosta.py:414, per read timeout only) or a stuck model call holds the scheduler thread forever, no later night runs. Fix: the child process limit (reviewer 1) and one deadline for the whole courier read. Open.
2. LOW the c- reference is sha256(agent, case id)[:10] with no secret; a phone number comes back in minutes. Fix: HMAC with a random key kept once. Open.
3. LOW a night past STALE is marked stopped while its thread lives; a second runner starts. Covered by the limit in 1. Open.
4. LOW the courier's reason reached the team line with its line breaks. Fixed in c1b460f with test.
Cleared: webhook secret before body, replay, unknown and shared orders, lost to won, page CSRF and sheet limits, scheduler env, keys.
Outside this branch: kit/model.py reads its answer with a per read timeout only (same hang shape). Open, its own task.
