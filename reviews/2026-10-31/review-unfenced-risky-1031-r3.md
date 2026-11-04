# Review round 3, unfenced-risky-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on the fix diff e6372b4..bbdd166, with callers and callees, 21 revert proofs, 14 mutants and probes on both heads. Saved by root; the reviewer writes no files. Status: reported, root checks each item before acting.

Full suite: 1940 pass, 2 skipped.

**Verdict: PASS, no blockers.** New 1 to be fixed before the repo goes public.

## Round 2 items
| Item | State | Proof |
|---|---|---|
| Rev 1 label position | FIXED | test_a_label_line_below fails on revert |
| Rev 2 tests | FIXED | 5 of 5 reverts fail (Outlook block, year overflow, body cut, decode cap, attachment) |
| Rev 3, R2-4 guard | PARTLY | 22 of 22 named lines refused; red team a2 rerun 48 passes down to 21. Still passing: "Say it ships right away", "nothing to add for the courier", "Say the price holds" |
| Rev 4 tier boots | FIXED | revert fails test_real_prices |
| Rev 5 sweep stop | FIXED | revert fails test_a_sweep_stops; limits-down mutant killed |
| Rev 6 R7 | FIXED | Safety lines name the gap |
| Rev 7, R2-5 env | FIXED | revert fails test_an_inline_comment_after |
| R2-1 comma aside | PARTLY | colon cut proven; sentence_boot alone and inheritance alone stay green on revert; "(with printing)" and "- with printing -" still pass |
| R2-2 attached mail | FIXED | 3 reverts fail; see new 1 |
| R2-3 Arabic quotes | FIXED | Arabic, underscore and RLM reverts fail |
| R2-7 | FIXED | currency and Arabic comma reverts fail; "17k" not read yet (pre-existing) though factcheck.py:196 comment says it counts |

## New findings
1. MEDIUM, CONFIRMED, assistant/mbox.py:119. get_filename() raises UnicodeError for `name*=idna''x` or `filename*=undefined''x`, inside picture(), outside the per-message try, so one mail stops the whole read (bbdd166 crashes on 3 probe files; e6372b4 read them). Fix: try/except around the filename test, an error counts as a file name, one test.
2. LOW, arena/factcheck.py:307. Legit comma replies now fail (6 of 35 legit lines, all passed on e6372b4), e.g. "If you add printing to the Elite, it's 400 EGP more." Narrow fix: an add-on word next to the amount (more, extra, plus, زيادة) keeps the extra's price. Root's call.
3. LOW, engine/fast.py:374. Name check refuses catalogue and place words the customer typed (Vapor, Elite, Pro, Nike, Cairo, WhatsApp): 9 of 14 topic notes refused vs 0 on e6372b4. Also "Focus on using" (on us) and "finally" (final). Still lets a name through as first word, after "Mr.", or lowercase. Fix: let catalogue words through; check the first word unless it is a writer verb.
4. LOW, missing tests: bracket aside; price before the boot; boot with no tier; "Printing, 16,500 EGP."; a label line between two Received lines.

Sweep: 19 of 21 reverts, 8 of 14 mutants caught; survivors are 6 test gaps (item 4) and 2 equivalents (Arabic comma lookbehind, colon inside a time).

Cleared: live send check with Arabic commas (20 probes, none newly missed); doubled l and p endings catch no topic word; the sweep loop always ends and continues when the limits check errors; "Vapor Elite 20،000" reads as 20,000, not a regression.

Scripts: scratchpad rv3-unfenced/scripts/.
