# Review unfenced-risky-1031, round 2
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max), saved by root. Scope: fix diff 54674a0..e6372b4 and its callers; findings 1 to 9 and R1 to R7; the 6 sweep survivors; R7 and metering probes.

Verdict: ISSUES (7): 1 medium, 5 low, 1 minor. Nothing blocking.

## Earlier findings
Each fixed file reverted alone to 54674a0: its tests failed every time (8 of 8).

| # | State | Proof |
|---|---|---|
| 1, R5 | FIXED | test_one_model_key_of_either_kind_is_enough, test_one_meta_key_is_enough |
| 2 | FIXED | idna and year mutants killed; OverflowError catch has no test (new 2) |
| 3, R6 | PARTLY | From, Delivered-To, Received, Inbox+Sent mutants killed; label position not checked (new 1) |
| 4 | FIXED | MAX_PART and size-sum mutants killed |
| 5 | FIXED | payment and personal_data mutants killed |
| 6, R3 | FIXED | 4 metering mutants killed |
| 7, R4 | FIXED | test_ssl_and_other_os_errors_fall_back...; no-fallback mutant killed |
| 8 | NOT | new test covers ">" lines, not the header break |
| 9 | FIXED | test_an_inline_comment_is_cut_from_an_unquoted_value_only |
| R1 | PARTLY | policy pattern untested; some notes pass (new 3) |
| R2 | FIXED | test_any_line_break_python_knows_makes_two_lines |
| R7 | NOT, bounded | new 6 |

Survivors: five are test gaps (overflow catch, final cut, attachments, quote header, lookahead). The body cap break gives the same output either way; only memory differs (34 MB against about 0 on a 22 MB mail).

## New findings
1. MEDIUM, CONFIRMED, assistant/mbox.py:132. In a non-Gmail export, an outside mail with its own "X-Gmail-Labels: Sent" below its Received lines counts as Sent. Fix: trust the label only above the first Received, Delivered-To or Return-Path line.
2. LOW, tests. Outlook "Original Message" block kept as the user's words; a Date with year 99999999999 crashes the read; a promise past 20,000 characters or in the only attachment is kept. Fix: one test each.
3. LOW, CONFIRMED, reflection/fast.py:148. Policy pattern never tested on its own; "shipping isn't charged", "delivery's on us", "the price's final", "no fee for delivery", "won't cost them anything extra", "price drops", "gift bag" pass.
4. LOW, arena/factcheck.py:317. Printing extra stands in for the boot, so "Vapor 17 Elite with name printing is 16,900 EGP" fails (also on 54674a0). Fix: `_boots(...) or pool`; add a lookahead test.
5. LOW, reflection/fast.py:241. An ending that hits the writer cap loses its note for good. Fix: stop the sweep when over the limit.
6. LOW, R7. An unescaped envelope-like body line makes a full Sent message. Needs an exporter that does not escape (mboxrd). Fix: name it in the Safety lines.
7. MINOR, kit/env.py:29. KEY="abc" # note keeps quotes and comment (same as red team R2-5).

Probe scripts: scratchpad rv2-probes/. Root confirmed red team R2-1 and R2-2 by rerunning; all items sent to the fix builder (worktree wt-secfix2) on 2026-10-31.
