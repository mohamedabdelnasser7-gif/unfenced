# Review crossowner round 3
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, last round, fix diff f234f77..c5ffaed. Filed by root from the hand-back. Probes: scratchpad rv-crossowner3/probes. Every round 2 finding is proven fixed by a test that fails when its fix is reverted.

Verdict: PASS (nothing blocking; finding 1 advised before merge)

1. DRIFT, reflection/shared.py:930-931 with engine/study.py:728-729. A writer that gives no line marks the give failed and keeps no key; the study stops at the first failure, oldest first, so one lesson that can never be made general blocks every later lesson from the pool. Fix: move on to the next lesson within the give cap and stop only on a writer error or a broken pool; record the key after a second night with no line; test with two lessons.
2. MINOR, shared.py:216-224. The 1934 list lacks common words (paid, held, women, feet, box, podcast, webinar and others) and British forms (practise, programme, licence); 11 of 102 plain lines across six agent kinds were refused, and a refusal keeps the key. Fix: add them to SAFE or a small supplement; a CLEAN table line with paid, women and box.
3. MINOR, shared.py:280-290 and 527. A missing or broken words_en.xz on an empty pool still asks the writer, drops the line and keeps the key, and the empty list is cached. Fix: ready() returns BROKEN when the list is empty; test with the file moved away.
4. MINOR, shared.py:713-724 and tests/test_shared_lessons.py:373. After clear_owner the old hash stays on earlier patterns, so one business counts as 2 owners, and a test pins it. Fix: clear() records the old hash for the name and the next add() replaces it; the test expects 1.
5. MINOR, security residual (low, same as red team r3 finding 1): short sound alike runs, number nouns, names and brands that are common words. Fix (optional): count 3 or more strong sound alikes anywhere in the line; add the names.
6. MINOR, test gaps: C07, R-B12, R-B9, C06, C16 one test each.
7. MINOR, tests/test_shared_arena.py:324 is flaky (2 to 3 runs in 10, before this round). Fix: a deterministic draw.
8. MINOR, two test classes after the main guard; a commit message says a chat with no line is asked again, but it never is.

Ruled out: old pools (none exist outside this branch); words_en.xz rebuilds exactly from the system list, lowercase only, no number words, loads in 64 ms; make_words.py never imported; Arabic refused; Franco refused apart from harmless homographs; the relock deadlock handled.
