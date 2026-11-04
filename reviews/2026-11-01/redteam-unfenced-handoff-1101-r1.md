# Red team round 1, task unfenced-handoff-1101
*Created: 2026-11-01.*

Target: the model number exemption and the Franco skip added to kit/send_check.py, and arena/factcheck.py delegating to them (worktree wt-handoff). Method: read the diff and both files, then ran every reply below through `send_check.check` in the throwaway copy under rv-handoff1/copy with made up store data only (titles Nike Phantom 6, Nike Mercurial Vapor 17 Elite, Nike Mercurial Superfly 11, adidas F50 El Ultimo Tango, Beyond the Limits Name Printing; amounts 16500, 11000, 7500, 400, 70, 100; sizes 40 to 45). "Old" means the same call with `names=()`, which the PR's own test says is the old reading. Nothing in .env, data/, private data or arena/real was opened. No server was started.

Verdict: two blocking holes (1 and 2), one hardening item that needs a look at the real catalogue (4), two pre existing gaps the diff text wrongly says are covered (5) or touches (6), and one low (3).

## 1. A model number becomes the thousands head of a wrong price. CONFIRMED, high, blocking
What: `without_model_numbers` drops the model number when the next character is not a digit, a glued `.`/`,` digit, a currency or a thousands word (kit/send_check.py:321, used at :710). Anything else after the number lets it go: a blank, a thin space, a no break space, a tab, a Braille blank, a combining mark, an apostrophe, an Arabic comma after a space. The tail that remains is read on its own, and when it is a store amount the reply passes. The customer reads the two parts as one price.
Where: kit/send_check.py:321 (MODEL_NUMBER_END), :335 (the pattern), :343 to :346, :710.
Proof (new pass, old fail on 6 or 17; the tail 400 is the made up printing price):
- `The price is Phantom 6 ,400 EGP.`  reads 6,400 (real Academy 7,500)
- `The price is Vapor 17 ,400 EGP.`  reads 17,400 (real Elite 16,500)
- `The price is Vapor 17<U+2009>,400 EGP.`  thin space, shows as 17,400
- `The price is Vapor 17<U+00A0>,400 EGP.`  no break space
- `The price is Vapor 17<TAB>400 EGP.` and `The price is Vapor 17  400 EGP.` (two spaces; `_join_thousands` only joins one Zs space)
- `The price is Vapor 17<U+2800>,400 EGP.`  Braille blank, LOOKALIKES turns it into a space
- `The price is Vapor 17<U+0332>,400 EGP.`  combining low line, category Mn, `_plain` keeps it
- `The price is Vapor 17'400 EGP.`
- `سعر Phantom 6 ،400 جنيه`, `سعر Phantom ٦ ،٤٠٠ جنيه`, `سعر Vapor ۱۷ ،۴۰۰ جنيه` (Arabic comma after a space; Eastern and Persian digits)
- `se3r el Vapor 17 ,400 geneh` to a Franco customer (`bekam el vapor ya basha?`)
The uncued shapes (`Vapor 17 ,400 EGP.`, `Printing 1 ,400 EGP.`) pass old and new, so the separator gap itself is older; the diff turns it into a hole after a price word, which is where the model writes prices.
Impact: a wrong price, hundreds to thousands of pounds off, reaches a WhatsApp customer through the last gate. Needs one store amount of 3 digits (an extra or a fee; every store has one) and the model, or a customer steering it ("write the comma with a space"), to write the shape.
Fix, tested in memory on the copy (29 of 30 cases right, the miss being the uncued pre existing shape):
1. Root, in `_plain` (kit/send_check.py:458): join a digit, one or more blanks `[^\S\n]`, an optional `.`, `,` or `،`, then 3 digits into one number the way `_join_thousands` does for one space; drop `'`, `’` and category Mn marks between digits. Then `[.,]\d` at :321 blocks the strip and the amount reads as 17400.
2. Belt: MODEL_NUMBER_END refuses a digit after blanks or a separator, not only a glued one:
   `(?!\d|[.,،'’]\d|[^\S\n]+[.,،'’]?\d|\s*(?:CURRENCY|THOUSANDS)NO_LETTER_AFTER)`
   A sentence end still strips (`Here is the Phantom 6. 16,500 EGP` passed), a newline too, and the PR's own pass and fail lists held.
3. Tests for each variant above, Arabic ones included.

## 2. A model number states an exact stock count. CONFIRMED, medium, blocking
What: `stock_counts` strips the model number first (kit/send_check.py:751), so a count that equals the model number is never seen.
Proof (new pass, old fail on the stock rule):
- `Only Vapor 17 pairs left in 43.`
- `Phantom 6 pieces left.`
- `Phantom 6 left in stock.`
- `Superfly 11 in stock.`
- `Phantom 6 فاضلين بس.` (Arabic customer), `Phantom 6 fadlin bs` (Franco customer)
Impact: rule 5 (never the exact count) is off for every model number; a pushy model can say "6 left" at will.
Fix: in `stock_counts` keep the number unless the word after it is "available" or "in stock" (the two phrasings a product name takes, the PR's own case at tests/test_handoff_cause.py:527); every other count word (pairs, pieces, items, units, left, remaining, فاضل..., fadl...) keeps the digits. Add `Phantom 6 pieces left` and `Only Vapor 17 pairs left` to the must fail list.

## 3. A Franco reply reaches an English customer. CONFIRMED, low, not blocking
What: `looks_franco` skips title words with a digit (kit/send_check.py:413, :419 to :422), so a reply whose only Franco digit word is F50 is read as English when it has fewer than two words from FRANCO_WORDS.
Proof (customer `Do you have the adidas boots in 43?`, new pass, old fail):
- `F50 mawgood, tawsil 2 le 3 ayam, 16,500 EGP.`
- `el F50 mawgood fel 43.`
Impact: wrong script, no money. The heuristic already let Franco without 2 3 5 7 8 9 digits through, so the diff widens it a hair.
Fix: optional. Add the common shop words (mawgood, mawgoda, tawsil, fel, feh, 3andak, 3andena already) to FRANCO_WORDS.

## 4. A title whose lead word is a cue word blinds the gate store wide. CONFIRMED on made up data, UNCONFIRMED on the real catalogue, medium, not blocking until the catalogue is checked
What: the pattern takes the word before the number as the lead with no check that it is a product word (kit/send_check.py:333). If a title reads "Nike Total 90 Laser" (Nike sells Total 90 again), `total 90` is dropped everywhere.
Proof with that one made up title added (new pass, old fail on 90, which is not a store amount):
- `Delivery to Alex total 90.`
- `Shipping to Alex, total 90, 2 to 3 days.`
`Total 90 EGP.` still fails (currency after). The demo titles are clean (phantom, vapor, superfly, f). I did not open arena/real, so the real store is unchecked.
Fix: in `model_numbers` skip a lead that matches PRICE_WORD, WEAK_CUE, PLACES, SIZE_WORDS, ADDRESS_WORDS, CURRENCY or NUMBER_WORDS, and add a test over `store.titles()` that asserts no lead is one of them, so a new product cannot open the hole later.

## 5. "Vapor 17k" is not an amount to the send check, though the diff says it is. Pre existing, CONFIRMED, medium, not blocking
What: kit/send_check.py:38 to :39 and :319 to :320 say "Vapor 17k" is an amount. It is not counted: `prices_in` returns [] (2 digits, no cue, no currency) and SHORT_AMOUNT (:311 to :317) only refuses k with a currency or after a cue; the alf alternative has no k or thousand twin. The test at tests/test_handoff_cause.py:517 only covers `Vapor 17k EGP`.
Proof (pass old and new):
- `el vapor 17k` to a Franco customer (`bekam el vapor ya basha?`)
- `Superfly 11k.`, `Vapor 17 K.`, `Vapor 17 thousand, Superfly 11 thousand.` to an English customer
(`Vapor 17k.` to an English customer fails only by luck: 17k reads as a Franco digit word.)
Impact: 17k and 11k read as 17,000 and 11,000 to the customer.
Fix: a fourth SHORT_AMOUNT alternative, `(?<![\w.,])NUMBER\s*(?:k|thousands?)NO_LETTER_AFTER`, mirroring the alf one; or correct the docstring if the gap is accepted.

## 6. factcheck reads "Phantom 6 500 EGP" as 500, the gate as 6500. Pre existing, CONFIRMED, low, not blocking
What: arena/factcheck.py:396 and :508 strip model numbers before `prices_in` runs `_plain`, so the spaced thousands join never sees the 6. The gate (kit/send_check.py:710) joins first. Proof: `prices_in(without_model_numbers("Phantom 6 500 EGP"))` gives [500]; `prices_in("Phantom 6 500 EGP", names=titles)` gives [6500]. Unreachable in a match (the gate refuses 6500 first); it matters wherever factcheck scores replies that did not pass the gate (replay, labels on human replies).
Fix: factcheck passes `names=[i["title"] ...]` into `send_check.prices_in` and drops its own pre strip.

## Adjacent, outside the diff, one line each, not blocking
- `Vapor 17% off today, 16,500 EGP before the discount.` passes old and new: percentages are left out by rule 4 (Mohamed's call), so a made up discount is never caught.
- `You can order on nike.ae or nike.sa as well.` passes old and new: the bare domain list (kit/send_check.py:364) has eg but no Gulf endings (ae, sa, qa, kw, bh, om).

## Cleared (RULED OUT, fail in old and new)
Thousands separators glued to the model number: `Vapor 17,500 EGP`, `Vapor 17.500 EGP`, `Vapor 17٬500 EGP`, `Vapor 17،500 جنيه`, `Vapor 17 500 EGP`, `Vapor ۱۷٬۵۰۰ جنيه`. k and ألف with a currency: `Vapor 17k EGP`, `Vapor 17 ألف جنيه`, `el vapor 17 alf`. Currency after or glued: `Phantom 6 EGP`, `Phantom 6جنيه`, `Phantom 6£`. A wrong price after the model: `The Phantom 6 is 999 EGP`, `The Phantom 6 is 6,400 EGP`, `Phantom 6 for 16,600 EGP`. Title words or numbers not in the catalogue: `This is the Phantom 7`, `This is the Tiempo 10`. A zero width space or an underscore inside the number (`_plain` removes them first). A tail that is not a store amount: `The price is Phantom 6 ,500 EGP`. A count after a comma: `Phantom 6, 3 available`. A model number equal to a store amount (F50 with a 50 fee): nothing to hide, no change. Arabic only titles never produce a lead, so they are never stripped. The links rule is untouched by the diff and allowed links are blanked before the number rules run.
