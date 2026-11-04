# Red team round 2, unfenced-gatefb-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Red team (Fable 5.1) on head 4e6fc1a, paper attacks on the review copy (demo data only). Saved by root; status reported until root checks each item. Scripts: scratchpad rt-gatefb-r2/attack_r2.py, attack_r2b.py. test_failed_back and test_gatefb_fixes: 48 OK.

## Round 1 attacks on the new head
1. Boot-first price: round 1 lines blocked; variants pass (A).
2. Add-on lookahead: round 1 lines blocked; variants pass (B).
3. Zone phrases: round 1 names blocked; "Nasr City - Badr" stays one phrase. Single-word zones pass (D).
4. Close-to-failed line: blocked. It takes the exam and the card names the failed check; a yes still starts it (by design).
5. Trimmed why: blocked as far as the fix goes (300 characters, one line). A planted instruction still reaches the proposer as data (unconfirmed, low, unchanged).

## New holes
A. CONFIRMED medium. arena/factcheck.py:209 to 218 (_boot_first) via :358. Extra named first with the boot still the subject passes ("With printing the Vapor 17 Elite is 400 EGP.", Arabic and Franco forms); an allowed amount in the head also defeats it. Fix: a clause that names a boot or tier holds the extra's price only when the extra is the subject before any boot word and the amount follows right after it; otherwise it must carry the boot's price or a sum.
B. CONFIRMED medium. arena/factcheck.py:133 to 134 (NOT_ADDON_AFTER) via :349. A block-list cannot close it ("more or so", "more-or-less", "more costly than", "extra large", Arabic forms, a hidden character inside "than"). Fix: an allow-list; an add-on word counts only when it ends the clause or is followed by a currency word, "for", "with" or "if".
C. CONFIRMED high. engine/fast.py:422 to 424 with :488 (_their_capitals). A name the customer wrote only at a sentence start (a one-word answer to the name question, kit/tools/draft_order.py:73) never counts, so a note can open a sentence with it. Fix: treat a one-word turn and a turn-opening word as capitalised; exempt only words the source also wrote in lowercase.
D. CONFIRMED low today, medium with real zones. reflection/fast.py:195 to 201. A single-word zone ("Zayed", "Rehab") goes into the own words, so "Ask Zayed about the size." passes for a customer named Zayed. Fix: keep only multi-word places in known, or require a delivery word beside a one-word place.
E. CONFIRMED low. engine/fast.py:455 to 465. The note side reads hidden characters as nothing only, so two words fuse past the check. Fix: read the note both ways, union the results.

Cleared: right lines still pass (extra first, DECISIONS 52, two-clause prices); dash-joined zones hold; names after a comma, dash or emoji still count.
