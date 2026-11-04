# Red team crossowner round 2
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team, short round, on f234f77 (fix lines e68d121..f234f77). Scratch copy, fake data, no network. Filed by root from the hand-back.

1. CONFIRMED HIGH, reflection/shared.py number guard is a word list: number homophones, split or misspelled number words, more Franco forms, ordinals and fractions, other languages and roman numerals pass (31 of 42 probe lines stored). Needs the writer to paraphrase; a 5 word copy is caught. Fix: fold homophones and number words to digits before the phone and amount tests; add ordinals, fractions, couple and pair; refuse any word not in an English word list apart from listed number and Franco forms.
2. CONFIRMED MEDIUM, shared.py: deleting an owner's owner-id file mints a new id, so the same lesson is given again and counts as a second owner. Needs delete access to that owner's folder. Fix: key what was given by the lesson's own id, and a known owner name with a new id gives nothing until the operator clears it.
3. CONFIRMED LOW, a pool file whose rows all fail the row check reads as not broken, so the first add() overwrites it (the older file format is wiped after an upgrade). Fix: count raw rows.
4. CONFIRMED LOW, the refuse path: a new owner key is made before the broken pool is found; a broken pool still costs writer calls; a writer returning nothing is not marked failed. Fix: read under the lock first; treat a refusal and an empty line as failed.
5. CONFIRMED LOW, unlisted lower case names (a bare brand, first names, hotels, districts) pass. Fix: the word list in item 1.

Ruled out: seal replay, rows copied to another kind, key swap, truncated file, reordered rows, duplicated rows, symlinked or copied owner-id, chain cycles and the 50 cap, pooled lessons that were edited, returned or copied, other numeral scripts, an owner's own patterns served back.
