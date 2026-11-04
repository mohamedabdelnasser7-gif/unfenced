# Review round 2, unfenced-feed-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on the fix diff df37745..02de34c plus callers. Saved by root; status reported until root checks each item. Suite: 2020 OK. Files: scratchpad rvfeed2/.

**Verdict: FIX FIRST.** 2 medium.

## Earlier items
FIXED: 2 and F9, 3 and F2 (with a regression, finding 2), 4, 5 and F7 (cap 5 per group, root's call), 6 and F3, 7, 8 with F4 to F6 and F10, 9. PARTLY: 1 and F1 (finding 1). OPEN low: F8 (no per-night share cap, no two-message minimum). F11 unconfirmed.

## New findings
1. MEDIUM, CONFIRMED, customer data. arena/grow.py:607, :632. The cleaner learns names only from order calls; lost chats have no order, so surnames reach the pool and the tagger (q1.py: 5 of 5 leaked). Fix: mask a name-shaped word right before or after a [name] mask unless it is a common word; tests with the 5 lines.
2. MEDIUM, CONFIRMED, regression. arena/run.py:268 to 275, arena/grow.py:219 to 221. The never-hold-out list only grows; once it covers every card that can buy, the Arena stops for good ("no card can buy"); --held-out once shrinks the gate forever. Fix: keep a saved split while its ids and seed match; on a redraw prefer untrained cards and top up from the least played; redraw a saved split that split() refuses; tests in the q3 and q4 shapes.
3. LOW. arena/grow.py:196, :212. Pools from df37745 keep a seen list and items with no read key; a rerun adds a talk twice. Never merged. Fix: map old seen ids on load, or rebuild old pools.

Unchanged: the Arena saves the whole pool at the end with no lock; a night during an Arena run loses its items.

## Mutants
86 run, 73 killed, 13 survived. Equivalent 7. Test gaps 6 (low): earlier-talk order names masked later, saved split ignores the seed, MAX_PENDING, bad read rows on load, held list not a subset, held list empty.
