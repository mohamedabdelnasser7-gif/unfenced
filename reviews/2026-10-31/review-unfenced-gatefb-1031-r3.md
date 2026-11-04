# Review round 3, unfenced-gatefb-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on the fix diff 4e6fc1a..d7730fc plus callers. Saved by root; status reported until root checks each item. Suite on copy: 2053 OK, 2 skipped. Files: scratchpad rvgfb3/.

**Verdict: FIX FIRST.** One medium regression.

## Earlier items
All 12 fix reverts fail a test. FIXED: N1, N2 and B, N3, N4, N5 (opened finding 1), call 8, A, C (as root ruled), D, E; 12 of 13 test gaps killed, st1 equivalent. known() pairs: its one caller and the engine's four reads all handle pairs.

## New findings
1. MEDIUM, CONFIRMED, regression. arena/factcheck.py _extra_not_held, last return. A participle right after the boot passes the boot-with-printing price ("The Vapor 17 Elite printed is 400 EGP.", Arabic مطبوع). Fix: a participle word returns True. **Root applied it: 29eaee5, test fails on revert, 2054 OK, drift clean.**
2. LOW, regression. check(), `and not set(amounts) & sums`: "The Vapor 17 Elite with printing is 400 EGP and 16,900 EGP in total." passes. Fix: exempt only when the extra's own price is not among the amounts.
3. LOW, gap in root's rule. engine/fast.py _introduced: a full-name turn ("Ahmed Hassan") leaves the first name free at a note start. Fix: count every word in a leading run of capitalised words.
4. LOW. Subject rule residuals ("brings it to 400 EGP"); bare و in ADDON_AFTER with no letter check; hidden characters read one way in the price check.

## Mutants
96 run, 74 killed, 22 survived. Equivalent 2 (st1, ef18); c8-7 agreed equivalent. Test gaps 20 (fc3, JOIN and AND words, fc22, fc26, fc23, fc27, ef5, ef8, ef9, ef10, ef13, ef16, ef17).
