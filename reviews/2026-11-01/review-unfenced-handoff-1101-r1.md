# Review round 1, unfenced-handoff-1101
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer (Opus, max) on 9c415df..8621b0d, 8 files. Saved by root from the hand-back (the agent could not write files). Status reported until root checks each item. Probes: scratchpad rv-handoff1/probes.

**Verdict: FIX FIRST.** One medium. 48 wrong-price inputs on the demo store all still failed.

1. MEDIUM, CONFIRMED. kit/send_check.py:426-427. Skipping F50 on the customer line turns Franco customers into English ones ("el F50 bekam?" with a Franco reply fails 3 times and hands off; the old code replied). Breaks DECISIONS 33. sales/loop.py:237 and kit/tools/handoff.py:98 still read the line as Franco. Fix: keep the skip on the reply only (line 446); when the two readings differ refuse only Arabic letters; e2e test.
2. LOW, latent. send_check.py:324-337. The exemption trusts any title number of any length after any title word ("Nike Guard Pro 500" lets "Pro 500" through). Fix: exempt only 1 or 2 digits, skip tier and cue words.
3. LOW. factcheck.py:318 strips before _plain, the live check after ("The Superfly 11 000 EGP" passes live, fails the fact check). Fix: _plain in without_model_numbers.
4. LOW. reflection/exam.py:256,267 call prices_in without names.
5. LOW. 27 mutants, 8 meaningful survivors, all test gaps (multi-turn checks, handoff_failed, exam names, Franco list).
6. LOW. 600 titles cost 170 ms per check. Compile once.
