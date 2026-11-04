# Review round 2, unfenced-gatefb-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on the fix diff 709b72d..4e6fc1a plus callers. Saved by root; status reported until root checks each item. Suite on copy: 2010 OK, 2 skipped. Files: scratchpad rvgfb2/.

**Verdict: FIX FIRST.** One medium plus minors.

## Earlier items
All 14 fix reverts fail a test. FIXED: rv1, rv3, rv4, rv5 (opener probe 0 of 15 names refused wrongly), rv6, rt1 (22 old shapes refused), rt3, rt4, rt5. PARTLY: rv2 (N1), rt2 (N2).

## New findings
1. MEDIUM, CONFIRMED. arena/factcheck.py:351. The boot's own clause has the add-on word and the extra comes later: "The Elite is 400 EGP more, and printing is available too." passes (also "an extra 400", "plus 400", Arabic). Fix tested on scratch: when the amount's clause names a boot or tier, take the extra only from the sentence text before that clause.
2. LOW to MEDIUM, CONFIRMED. factcheck.py:132 NOT_ADDON_AFTER. Block-list leaks ("more or so", "more-or-less", hidden space, "give or take", Arabic). Fix: count the add-on word only when the clause ends or for, on, to, if, with, and, each, so (Arabic عشان, لو, و) follows. Scratch: 12 of 14 refused, 112 price tests green.
3. MINOR. engine/fast.py:129. ";" and ":" count as sentence starts. Drop them from _SENTENCE_ENDS. Residual of root's rule: a name the customer gave at a sentence start opens a note (12 of 13 shapes); reviewer rates it low, the red team rates it high (r2 item C).
4. MINOR. reflection/morning.py:1186, reflection/night.py:448. When a close line's exam fails, the close-to line disappears from the card. Add it to the exam branch.
5. MINOR. factcheck.py:65 _boot_first refuses true lines ("For the Vapor 17 Elite the printing is 400 EGP."). Count boot-first only with a joining word (with, plus, +, and, مع, ب) between boot and extra.

Zones: owner-set zones like "Ahmed and Cairo" let that name through; not a regression.

## Mutants
58 run, 32 killed, 26 survived. Equivalent 4 (fc14, ef9, ef10, ef14), equivalent on demo data 2 (fc13, st6). Test gaps 20: fc3, fc4, fc5, fc7, fc9, fc12, fc17, ef2, ef3, ef12, rf5, rf6, st1, st4, st7, st11, st13, st15, st16, st17.
