# Review round 3, unfenced-feed-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on the fix diff ac08816..8fd4dc0 plus callers. Saved by root; status reported until root checks each item. Suite: 2161 OK. Rebase checked: night.py only adds on top of main, study.py equals main. Files: scratchpad rvfeed3/.

**Verdict: FIX FIRST.** One medium regression.

## Earlier items
FIXED: round 2 finding 1 (q1 0 of 5 leak; see new 1), 2 (split; low residual: after one --held-out run the saved gate keeps a card trained in that run), 3 (old pool; low: a restored older file adds a talk twice), red team 1 numbers, red team 5 folder mode (the link-swap half unchanged), all round 2 test gaps. PARTLY: red team 1 pattern hang (new 2).

## New findings
1. MEDIUM, CONFIRMED, regression. arena/clean.py:794 learns every masked word, including chain (:775) and beside (:785) words, and :978 re-cleans twice, so product words are masked as names across the whole chat and in the tagger (jacket, order, black, boots names, colour words). Lost chats are marked read, so the loss is permanent. Fix: learn only cue words; one re-clean pass; ال-words beside a name only when they end in ي; no lowercase Latin beside-words except before "here"; tests from fp.py plus a tag field test.
2. LOW, CONFIRMED (needs a pool write). arena/grow.py:374 misses adjacent stars (`\w*` ten times takes 9.7 s). Fix: store the capped words and rebuild the pattern with recipe._words on load.

## Mutants
68 run, 49 killed, 19 survived; all 28 round 2 reverts killed. Equivalent 6. Test gaps 13 (low), mostly the learning knobs.
