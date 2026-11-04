# Red team crossowner round 3
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team, last round, short, on the fix lines f234f77..c5ffaed. Filed by root from the hand-back. Scratch copy, fake data, no model, no network. All 31 round 2 bypasses are now blocked; the red team would accept the fix.

1. CONFIRMED LOW, reflection/shared.py check() :455 with _not_english :343, _shop_like :399 and _folded :348. A short identifier still passes when written only in lowercase dictionary words: letter name words spelling a two or three letter brand or handle (the 1934 list keeps bee, dee, jay, kay, em and the rest), and single digit sound alike words that do not fold alone or in a run broken by a filler word (oh, won, too, tree, for, ate). Also first names and places that are common words (dean, grant, reading, march). Low because the writer is told to generalise and a copied run of 5 words is caught. Fix: flag a run of 2 or more letter name or digit sound words, ignoring fillers; move the clear sound alikes into ALWAYS_SOUNDS (:120); drop the spelled alphabet in make_words.py as NUMBERISH is.
2. RULED OUT: owner counting (delete and remint, two db paths, clear_owner, edited, copied or deleted seals, symlinks). By design: one operator can still make two owner folders; the module says so.
3. RULED OUT: fail closed (missing, truncated or swapped words_en.xz refuses every pattern; a half broken pool keeps good rows; an all broken pool is not overwritten; a write error leaves the pool as it was and the night goes on).
