# Review round 3, unfenced-marketing-1031 and unfenced-assistant2-1031
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer (Opus, max), fix diffs. Files: scratchpad rv-mkas3/.

## Marketing: PASS. MERGED 61f7f8d (main, pushed).
One note per Cairo night holds over two years of runs with drift and DST; reruns show the earlier note; the no repeat rule never blocks for good. Lows left: a database from round 1 or 2 code has no night column (none exists outside dev); no test mixes old and new cases; a manual run after noon takes the coming night.

## Assistant: FIX FIRST (not reachable: keep_finished has no caller)
1. MEDIUM, regression. _display_name (arena.py:435 to 451) needs an address tie, so two-word display names leak.
2. MEDIUM. Sign-off cut (:338 to 350) still cuts a short ask with no question mark.
3. MEDIUM, new. _signature (:286 to 306) and WITH_NAME (:107) mask content (Arabic lines without punctuation, with Marketing).
Round 3 was the last: root sent one builder with the reviewer fixes (same path he approved for feed: "Do the recommended if they are not a big thing"), root verifies with the probes, then merge.
Mutants: marketing 10 of 15, assistant 45 of 57; all round 2 reverts killed.
