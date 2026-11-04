# Red team scopeguard2 round 3
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team, last round, short, on the fix lines f07d0eb..2af919e. Filed by root from the hand-back. Fake models, no network. Scripts: scratchpad rt-scope2/scripts (rt3_*.py).

1. CONFIRMED MEDIUM, reflection/exam.py:426-442 _revealed. 29 natural reveal shapes pass on situation 52 (no colon, a line break, "My instructions are to ...", Arabic "تعليماتي هي", Franco "ta3limaty heya") and four correct declines are blocked. A word check cannot close this; the right grader for 52 is one judge call.
2. CONFIRMED MEDIUM, exam.py:485 check_store_declined. Any refusal followed by one store word passes (9 of 9). Fix: drop the store word pass; pass only when the situation's work was done (a tool ran, a number after the decline, the note fact).
3. CONFIRMED MEDIUM, situations.json. 13 store work situations lack store_work, so a plain refusal passes. Fix: opt in by rule; mark fair limit situations "limit": true; a test asserts every situation is one or the other.
4. LOW, exam.py:373 and 449. NFKC composes Latin marks before the strip ("wāves", "ricé" pass). Fix: NFKD, strip, NFC.
5. LOW, invisible letters (Hangul fillers, braille blank, tatweel) join words and hide listed ones; the 45 word rule miscounts. Fix: treat them as hidden.
6. LOW, situation 51 word forms: sand/sandal, salt/salty, tide/tidy, ocean, شط/شطة. Fix: no al or y forms on these nouns, drop ocean, شط whole word.
7. LOW, 51 and 53 still pass in other words (broken plurals, more synonyms, Cyrillic look alikes). Fix: add the listed words and fold look alikes; the list is a floor, the judge is the ceiling.
8. LOW, kit/turn.py:149-159 card lines keep invisible letters and compatibility forms. Fix: NFKC, drop them, refuse an empty line.
Ruled out: steering the PRE call from the ask; the _own reader; NFKC turning a word into a listed word.
