# Red team round 3, unfenced-gatefb-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Red team (Fable 5.1) on head d7730fc, paper attacks on the review copy (demo data). Saved by root; status reported until root checks each item. Scripts: scratchpad rt-gatefb-r3/. test_gatefb*: 65 OK.

Reruns: all 13 round 1 and 2 price lines blocked; the 6 round 2 name lines blocked; quotes, colon and comma around a mid-sentence name blocked; a hidden character inside "with" blocked; "Deliver to Zayed" refused; the own-price exception held.

## New holes
1. HIGH, blocking (red team call). engine/fast.py:568 to 575 (_introduced) with :143, :551 to 565. A two-word name answer registers only the second word; "Ahmed hena", "Ahmed men Giza", "Ahmed - size 42", small-letter "ahmed" register nothing. A note naming Ahmed passes for 15 of 19 turn shapes. Fix: a turn's first word counts as a name whatever follows and whatever its case, unless it is an opener or an own word.
2. HIGH, blocking (red team call). engine/fast.py:522 to 544 via :443 to 447. Only note words with a capital first letter are checked: "ask ahmed the size first.", "aHMED", Arabic "اسأل أحمد" pass. Fix: compare normalised note words regardless of case; in Arabic a word after أنا, انا, اسمي or a lone turn is a name.
3. MEDIUM, blocking (red team call). arena/factcheck.py:246 to 280 with JOIN :155, AND :156. The joiner list is a block-list: 19 of 20 joiner variants pass a wrong boot price ("printed with your name", "inclusive of", Franco and Arabic forms). Fix: boot first holds the extra's price only when a toward word opens the clause before the boot, or via _own_price_then_extra.
4. MEDIUM. :274 to 278. A toward word anywhere in reach passes ("The printed version of the Vapor 17 Elite is 400 EGP"). Fix: the toward word must sit right after the extra.
5. MEDIUM. :437 to 445 with ADDON_AFTER :143. An earlier clause naming the extra lets "the Elite is 400 EGP more to upgrade" pass. Fix: an earlier clause gives an add-on only when it opens with if, when, with, لو, مع or بـ.
6. LOW to MEDIUM. _visible :581 to 585 drops format characters only; combining marks and Hangul fillers inside key words pass. Fix: reuse risk.normalize's rules.
7. LOW to MEDIUM. _beside_ok :499 to 505. A delivery word anywhere in the sentence lets a one-word place that is also a name pass ("Ask Zayed about delivery."). Fix: the place passes only right after a toward or delivery word, never as subject, never when the source introduced it.
8. LOW. _plain :508 to 513. A combining mark between words fuses them. Fix: read marks like format characters, both ways.

Info, wrong refusals: "The Vapor 17 Elite is 400 EGP more if you add printing."; "number: one" in notes.
