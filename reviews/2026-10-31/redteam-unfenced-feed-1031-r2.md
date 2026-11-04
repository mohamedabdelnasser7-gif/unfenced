# Red team round 2, unfenced-feed-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Red team (Fable 5.1) on head 02de34c, paper and fake-data runs on the pack copy. Saved by root; status reported until root checks each item. Scripts: scratchpad rt-feed-r2/r2_attacks.py, e_writer.py.

**Blocking: none.**

## Reruns
F1 blocked on the main path (cue names, split names, Latin order name repeated in Arabic or Franco, long names, address all masked end to end). F2, F3, F4, F5, F7, F8, F9, F10 blocked. F6 passes with new values (1). F11 unchanged, unconfirmed.

## New holes
1. LOW, CONFIRMED (needs a pool write). grow.py:344 to 347, 320 to 321, 351 to 357. Huge numbers (10**400) pass the value checks and crash the Arena outside run.main's except list (run.py:750); a nested-quantifier pattern passes _capped_ok and hangs decks(). Fix: numbers must be int or float, not bool, within 2**53; MAX_PATTERN 300 and refuse a quantified group followed by a quantifier.
2. LOW to MEDIUM, CONFIRMED, customer-reachable. grow.py:607, clean.py:764, 784. A bare surname in a lost chat with no order survives; a 3-token order name ("Nourhan El Sherbiny") does not mask its 2-token Arabic form. Fix: add the words of each cue hit to the chat's names; merge el and al prefix tokens before the skeleton compare.
3. LOW, CONFIRMED. run.py:268, 239. Two winnable cards of one worry: run 2 finds every group trained and stops. Not reachable on a build-made set. Fix: keep the saved split when a fresh draw has no winnable card.
4. LOW, design limit. grow.py:133 to 160. A plug under a marked parent naming the neighbour's owner shares that pool. Fix: owner.json lists its agent folders.
5. LOW. grow.py:291. An existing owner folder stays 0755; a folder swapped to a link after init is written through.
