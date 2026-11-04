# Review round 3 (last): unfenced, branch handoff, fix diff fcfa213..abc8a36
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Stopped at the 250K cap: 100 of 142 mutants run; progress note in the session scratchpad PROGRESS-a7d9d7ee121aa9281.md; probes in review-handoff-r3/. Full suite at abc8a36: 2,413 OK (2 skipped).

Verdict: FIX FIRST. 2 blocking, both regressions from this fix round. Every round 2 finding is FIXED and each revert fails a test (18 of 18 R- reverts killed).

1. BLOCKING, MEDIUM, new. Ordinary sales lines refused as exact stock counts (pass at 9c415df and fcfa213, refused at abc8a36; end to end the chat is handed off after 3 failed checks):
   - Franco singular "available": "el F50 mawgod fel 43 ya basha", "el Vapor 17 mwgod b 16,500 geneh", "el Phantom 6 mawgoda fel 42". Cause: mawgod/mwgod prefix stems (:385, :517).
   - Order summaries: "Your order has 2 pairs in size 43, Phantom 6 and Vapor 17.", "There are 2 pairs in your cart, size 42 and 43." Cause: :508.
   - "tamam, el order 2 goz bs, size 43" and its Arabic twin. Cause: :510.
   - "Yes, UK 8 is in stock, that is EU 42.", "Option 2 is available in 43.", "The Air Max 90 is available in 43." Cause: :506-507.
   Fix (tried, 606 core tests green): (a) `ma?wgo[ou]?d(?:in|een|ein)` at :385, :517; (b) have shape only after we/we've (+ still/only/just); (c) bridge words only before left or remain; (d) skip a goz-bs sentence that names the order. Add the lines to test_orders_offers_codes_and_the_verb_are_not_counts.
2. BLOCKING, MEDIUM, regression. English refused as "not Franco" (pass at fcfa213): "We're open daily 9am-9pm.", "Our working hours are 9am-5pm, Sunday to Thursday.", "Delivery comes 2pm-5pm."; "mesh" twice ("Mesh upper, mesh tongue"); "Boots w/o box, items w/o tag." persona-05's worry is delivery time. Fix (tried): accept a clock-time neighbour at :596; count "mesh" once when lenient; "w/o" reads "without" at :581. Add to LenientEnglish pass list.
3. MINOR. Allow list brings back old refusals: "se3r el Phantom 6 b7,500 geneh" (ب or b glued), U+2026 and U+061B after a model number, "Is it the Vapor 17 ?". Fix: `[بb](?=\d)|` at :395; add U+2026, U+061B to the end marks at :396.
4. MINOR, none new vs fcfa213. NARROW_BLANKS lists only four blanks (same as red team r3 item 2a); "Only Vapor 17 remain available in 43." passes; k class with brackets; Franco read as English (script only); docs/known-limits.md:31 should name 1 and 2 if they ship unfixed.
5. MINOR. Mutants: 36 survivors of 82 non-revert mutants, all test gaps (allow-list parts, look-alike parts, 16 of 21 TIME_WORDS, WITH_SHORT guards, tlaf, some bridges). Not run: count stem, REMAIN, STOCK_COUNT, store-word tier.

Other checks: 226 demo lines read the same at fcfa213 and abc8a36; worst-case timing 14-20 ms; persona-05 change is language shares only (franco 0.11 to 0.22, english 0.56 to 0.44), English stays top so its prompt is unchanged.
