# Review caseid round 2
*Created: 2026-11-03. Last updated: 2026-11-03.*

Reviewer (Opus, max), fix commits 6e0d977 and adacc4a: the fix diff, what it calls, 22 revert mutants, a 70 mutant sweep, probes. No live model run. Saved by root from the hand-back.

Verdict: ISSUES (4). Do not merge until 1 is fixed.

Earlier findings: R1/F1 deal guard FIXED in code (see 3); R2 links and retries FIXED; R3 test gaps PARTLY (8 of 10; kit/chats.py:218 branch filter and main() memory wiring still pass the suite); R4 wording FIXED; R5 team label FIXED; F2 retry loop FIXED but see 1.

1. BLOCKING, sales/memory.py:224-226 with :238. While a retry waits and an older note exists, the turn sends every message since that note (probe: 50, 58, 74, 82, 98 messages, then 60 to 92 on talk 2). Breaks the locked "falls back to the last 40". Fix: on a wait send the last WINDOW messages; test.
2. DRIFT, medium, :77-82. 16 of 21 honest notes refused: off white, free size, postal code, dropped off, asked for a manager, agreed on size 43, wallet as a product, 100% cotton, an em dash, ellipsis or accent. On an ended talk one refusal is final. Fix: dashes and ellipses to ASCII before the letters check; narrow off, code, free and % to deal phrases.
3. MEDIUM. Code gap CONFIRMED, model obeying it UNCONFIRMED. 26 plain English dodges pass: half price, on the house, no charge, complimentary, comp, Vodafone Cash, Fawry, valU, Visa, card, insta pay, per cent, gift, money back. Fix: add them, a test per word.
4. DRIFT. 29 sweep survivors, 3 equivalent. Untested: the tries query's case and talk filter, ended branch always waits, the SPAN boundary, most single DEALS words, www.

## Root status (2026-11-03)
- Red team r2 (redteam-caseid-r2.md) F1 says the same as 3 and points at reflection/fast.py _NEVER_WORDS (:82-140) and engine/risk.py code_check (:297) as the list to reuse. Round 3 fix builder gets 1 to 4 plus that, and the LOW prune of case_memory_tries.
