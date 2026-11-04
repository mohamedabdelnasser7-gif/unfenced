# Review wireall round 3
*Created: 2026-11-02. Last updated: 2026-11-02.*

Reviewer Opus max, fix diff eaecc37..6ba8e5d. Filed by root from the hand back (the agent could not write report files). Verdict: ISSUES, 1 medium, 5 low, no blocker. Round 2 findings 1, 3, 4 and 7 each proved by a test that fails on revert (14 of 14 single reverts killed); sweep 78 mutants, 50 killed, 23 survived, 5 equivalent.

1. MEDIUM reflection/turn_exam.py:350-351, :370. A kept "reached" verdict on the run without the line locked every later harmless lesson for an agent whose good result takes more than one message. Fixed in 44c3bc1: no verdict kept across lessons; test test_one_false_reached_without_the_line_holds_only_the_lesson_that_saw_it fails on 6ba8e5d.
2. LOW test gap, data/ rule in check_cards. Fixed in 44c3bc1: test_owner_cards_under_data_are_accepted, fails on revert.
3. LOW linked card files refused for every caller, Sales too. Kept; the --cards help now says plain files, no links.
4. LOW hard link passes load_cards. Fixed in 44c3bc1 (st_nlink > 1 refused): test_a_hard_linked_card_is_refused, fails on revert.
5. LOW RecursionError at run.Calls._read and madeup.read, practice.py:317. Fixed in 44c3bc1.
6. LOW test gaps left: grow.py:144 and :206 and exam.py:145 catches; G7; C1, C3, C6; N4 (night without the plug folder gives a built agent no exam); T18 (answer() outside demo_store; with real Shopify keys an exam could call the real store's draft_order).

Still open from earlier rounds: r2 findings 5 (pairs lean one way) and 6 (multi-message good results before the first practice win, his call A or B), r1 lows 4, 5 and 6, T18.

Gate: 3 rounds done, no blocker. Merged to main 44c3bc1 (ff-only) and pushed 2026-11-02, suite 2643 OK, drift clean.
