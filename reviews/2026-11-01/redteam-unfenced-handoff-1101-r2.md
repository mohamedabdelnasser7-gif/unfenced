# Red team round 2, task unfenced-handoff-1101
*Created: 2026-11-01.*

Target: the fix diff 8621b0d..fcfa213 on kit/send_check.py (worktree wt-handoff), against my round 1 blockers. Method: read the diff, then ran every reply below through `send_check.named_problems` in the scratch copy under review-handoff-r2/copy with the same made up store data as round 1 (titles Nike Phantom 6, Nike Mercurial Vapor 17 Elite, Nike Mercurial Superfly 11, adidas F50 El Ultimo Tango, Beyond the Limits Name Printing; amounts 16500, 11000, 7500, 400, 70, 100; sizes 40 to 45). Three readings per probe: "new" is fcfa213, "old" is 8621b0d (the module round 1 attacked, loaded on its own, stdlib only), and "fix" is a patched copy of fcfa213 with the fixes below applied, so each fix is shown to close the hole and keep the builder's own pass cases. Nothing in .env, data/, private data or arena/real was opened. No model call, no network, no server started. Line numbers are fcfa213.

Verdict: the 18 exact round 1 shapes are all blocked now (cleared list at the end). The three fixes are word and character lists, and each list has a gap a variant walks through: 14 other Unicode separators and a narrow blank after the comma reopen item 1 (finding 1, high); three thousands words reopen the price hole after a model number (finding 2, medium); inflections and bridge words reopen item 2 (finding 3, medium). The lenient English reading lets natural Franco through (finding 4, low, not blocking). The title word list holds on the demo titles and is an open class on the real catalogue (finding 5, low).

Runnable one line probe (swap the reply and the customer line; `\uXXXX` escapes are read by Python):
`python3 -c 'import sys; sys.path.insert(0, "scratch/review-handoff-r2/copy"); from kit import send_check as s; print(s.check("The price is Vapor 17‚400 EGP.", "Do you have the adidas boots in 43?", (16500, 11000, 7500, 400, 70, 100), frozenset(), ("40", "41", "42", "43", "44", "45"), names=("Nike Phantom 6", "Nike Mercurial Vapor 17 Elite", "Nike Mercurial Superfly 11", "adidas F50 El Ultimo Tango")))'`
Customer lines: EN `Do you have the adidas boots in 43?`, FR `bekam el vapor ya basha?`, AR `بكام الجزمة؟`. The full probe set is review-handoff-r2/probes_r2.py and run_fixed.py in the scratchpad; the fix text is make_fixed.py, applied as fixed/send_check.py.

## 1. The separator fix is an allowlist of two apostrophes; 14 other separators and a narrow blank after the comma pass. CONFIRMED, high, blocking
What: THOUSANDS_GAP (kit/send_check.py:140) joins blanks then one of `. , ، ' ’`, and MODEL_NUMBER_END (:345) refuses the strip for the same five. Any other character that shows as a comma, a dot or an apostrophe is not a blank and not in the set, so the model number is stripped and the 400 tail passes on its own (the round 1 mechanism). The rule "a separator then a blank is a list" is right for a real space, but a hair space (U+200A), a thin space (U+2009) or a narrow no break space (U+202F) after the comma shows as nothing, and "17,<hair>400" reads as 17,400.
Where: :140 (THOUSANDS_GAP), :345 (MODEL_NUMBER_END), :77 (LOOKALIKES has no separator look alikes), :581 (_loose_marks_out handles Mn and Me, not Mc).
Proof, all PASS in new and old, BLOCK in fix with 17400 read (customer EN unless said; the same with "The price is Vapor 17 <char>400 EGP.", a blank before the separator):
- `The price is Vapor 17‚400 EGP.`  U+201A single low 9 quote, the same glyph as a comma
- `The price is Vapor 17，400 EGP.`  U+FF0C fullwidth comma; `﹐` small comma; `、` ideographic comma
- `The price is Vapor 17‘400 EGP.`  U+2018; `‛`; `′` prime; `ʼ` and `ʹ` modifier letters (these two are `\w`, so glued they also passed before the model number work); `＇`; `´`
- `The price is Vapor 17․400 EGP.`  U+2024 one dot leader; `．` fullwidth stop; `·` middle dot
- `The price is Vapor 17, 400 EGP.`  comma then hair space; `, ` thin; `, ` narrow no break
- `The price is Vapor 17 , 400 EGP.` and `17 , 400`
- `The price is Vapor 17 , 400 EGP.` and `17 . 400` (a plain space on both sides; weaker, the gap shows)
- `The price is Vapor 17ः,400 EGP.`  U+0903, a spacing mark (Mc), shows as a glyph, listed for completeness
- `سعر Vapor ١٧‚٤٠٠ جنيه` (AR), `سعر Vapor ١٧، ٤٠٠ جنيه` (AR), `se3r el Vapor 17‚400 geneh` (FR)
Left by design, still pass: `17, 400` and `17, 400` (a separator then a full width blank is a list, the builder's call) and `17\n,400` (two lines on the phone).
Impact: as round 1 item 1, a wrong price by thousands reaches the customer through the last gate. Reachability is one step lower than round 1 (the model has to write a look alike or a hair space rather than a plain blank), so the class stays high because any one of 15 characters works and the fix was the exact two characters round 1 named.
Fix, tested in fixed/send_check.py (every case above blocks with the joined number; "Here is the Phantom 6. 16,500 EGP", "Phantom 6 (16,500 EGP).", "Phantom 6: 16,500 EGP.", "Cairo 70, Alex 100 EGP." and the rest of the pass list still pass):
1. Root, LOOKALIKES (:77): map U+201A, U+FF0C, U+FE50, U+FE51, U+3001, U+060D to ","; U+2024, U+FF0E, U+FE52, U+00B7, U+2027 to "."; U+2018, U+201B, U+2032, U+2035, U+02B9, U+02BB, U+02BC, U+02BD, U+00B4, U+FF07, U+275B, U+275C to "'". The number then reads as 17,400 in every rule.
2. Root, _plain (:571): a narrow blank (U+2009, U+200A, U+2006, U+202F) between a separator and 3 digits, or between a digit and a separator then 3 digits, is taken out before _join_thousands: `NARROW_BLANK = re.compile(r"(?<=[.,،'’])[    ]+(?=\d{3}(?!\d))|(?<=\d)[    ]+(?=[.,،'’]\d{3}(?!\d))")`.
3. Belt, MODEL_NUMBER_END (:345): one more alternative, a blank, a separator, blanks, a digit: `[^\S\n]+[.,،'’][^\S\n]*\d`. A sentence end still strips ("6. 16,500" has no blank before the dot).
4. _loose_marks_out (:581): `("Mn", "Me", "Mc")`.
5. Tests: one per character above, the hair and thin space shapes, and the pass list.

## 2. Three thousands words after a model number pass. CONFIRMED, medium, blocking
What: model_thousands (:405) and SHORT_AMOUNT use THOUSANDS (:326 THOUSANDS_WORDS plus k and thousand). "ألاف" (the common misspelling of آلاف), "تلاف" (Egyptian for thousands after 3 to 10: "6 تلاف" is 6,000) and Franco "talaf" are in none of them, so the model number is stripped and nothing is left to read. Before the model number work the cue caught the 17 or the 6 (old in probes_r2.py, names=(), blocks on amounts).
Where: :326 (THOUSANDS_WORDS), :304 (MAGNITUDE_WORDS has تلاف but not ألاف or talaf), :345, :405.
Proof (PASS new and old 8621b0d, BLOCK fix):
- `سعر Vapor 17 ألاف` and `سعر Vapor ١٧ ألاف` (AR)  reads 17 thousand
- `سعره Phantom 6 تلاف.` and `Phantom 6 تلاف بس` (AR)  reads 6,000, the Phantom 6 Academy is 7,500 in the demo data
- `se3ro Phantom 6 talaf` and `el phantom 6 talaf` (FR)
Impact: a wrong price in words after a model number, the shape rule 3 exists to refuse.
Fix, tested: THOUSANDS_WORDS `(?:alf|ألف|الف|آلاف|الاف|ألاف|تلاف|talaf|tlaf)`; add talaf, tlaf and ألاف to MAGNITUDE_WORDS (:304) so amount_in_words reads them too. Pre existing and left: `Vapor 17.5k.`, `Vapor 17kEGP.`, `Vapor 17 thou.`, `Vapor 17 grand.` pass old and new (the docstring at :408 accepts "1.5k" with no cue; the others are not Egyptian usage).

## 3. The count word list misses inflections and bridge words; every miss was blocked before the model number work. CONFIRMED, medium, blocking
What: COUNT_AFTER (:339) needs the count word right after the number (one optional بس or bs) and ends each word with NO_LETTER_AFTER. A bridge word (are, still, لسه, lesa) or an inflection (fadla, ba2yeen, باقيه, متبقية, remain) misses, the model number is stripped, and the count is gone. STOCK_COUNT (:428, alt 4) matches the Arabic and Franco stems by prefix, so before the strip these inflections were caught; the English bridges were caught by the amounts cue ("Only ... 17"). The belt and the catch disagree on "pcs" too: COUNT_AFTER keeps it, STOCK_COUNT does not know it, UNIT_AFTER (:212) then reads it as a unit, so `Only Vapor 17 pcs left.` passes old and new.
Where: :339 to :341 (COUNT_AFTER), :345, :428 to :436 (STOCK_COUNT), :876 (stock_counts).
Proof (PASS new, BLOCK in probes_r2.py old with names=(), BLOCK fix):
- `Only Vapor 17 are left in 43.`, `Only Vapor 17 still left.`, `Only Vapor 17 remain.`, `Only Vapor 17 remains.`, `Only Vapor 17 pc left.` (EN)
- `Phantom 6 باقيه بس`, `Phantom 6 متبقية` (AR)
- `Phantom 6 fadla bs`, `Phantom 6 ba2yeen bs`, `Phantom 6 fadlen` (FR)
Pass old and new, STOCK_COUNT gaps the strip now makes permanent: `Only Vapor 17 pcs left.`, `Only Vapor 17 pairs are left.`, `Phantom 6 لسه فاضلين`, `Phantom 6 lesa fadlin`, `Phantom 6 mawgodeen bs`, `Vapor 17 only left.`
Impact: rule 5 (never the exact count) is off for a model number again, with a natural sentence ("only 17 are left").
Fix, tested (all of the above block except `mawgodeen`, which needs the STOCK_COUNT stem change in the last line): COUNT_AFTER as stems with up to two bridge words, no NO_LETTER_AFTER on the stems:
`COUNT_BRIDGE = r"(?:بس|bs|لسه|لسة|lesa|lessa|still|now|are|is)"`, `COUNT_STEMS = r"(?:pairs?|pieces?|pcs|pc|items?|units?|left|remain(?:s|ing)?|قطعة|قطعه|قطع|حتة|حته|حتت|7etta|7etat|فاضل|باقي|باقى|متبقي|متبقى|متاحين|موجودين|fadl|fadel|ba2y|ba2i|mawgod|mwgod)"`, `COUNT_AFTER = rf"[^\S\n]*(?:{COUNT_BRIDGE}[^\S\n]+){{0,2}}{COUNT_STEMS}|[^\S\n]*more{NO_LETTER_AFTER}"` ("more" stays exact so "the price of the Phantom 6 is more than" passes, checked). STOCK_COUNT alt 1 takes pcs, pc, remain(s) and `(?:(?:are|is|still|now|only)\s+){0,2}` before left; alt 4 takes لسه, لسة, lesa, lessa among the small words and should match mawgod and fadl as stems. Add the cases above to the must fail list.

## 4. The lenient English reading lets natural Franco through. CONFIRMED, low, not blocking
What: three parts of rule 8 open a Franco reply to an English customer, and 8621b0d blocked every one of these.
- The "count once" rule (:503 to :504): "el" is the most common Franco word, so a reply built on it is English now. The title pairs (:513) already cover a title said twice ("The El Ultimo Tango is 16,500 EGP, the El Ultimo Tango in 43 too." passes without the count once rule, checked), so the dedupe adds nothing but this hole.
- NOT_FRANCO_SHAPE `\d{1,2}(?:am|pm)` (:98): "3am" is "عم" or "عام" in Franco ("ya 3am" is as common as "ya basha").
- `[a-z]*\d{2,}[a-z]*` (:98): a Franco word with a doubled digit letter ("ba22a", "sha22a", "7a22ak" has no run) is passed over.
- Pairs (:513): "el" next to "f50" or "ultimo" is never a Franco word.
Proof (PASS new, BLOCK old 8621b0d, customer EN):
- `el vapor mawgood, el superfly mawgood, el tawsil 70 geneh.`
- `mawgood ya 3am, 16,500 geneh.` and `3am, el vapor mawgood, 16,500 geneh.`
- `mawgood ba22a, 16,500 geneh.`
- `f50 el ultimo mawgood ya basha, 16,500 geneh.`
Impact: wrong script, no money, as round 1 item 3; the first shape is the one a model writes.
Fix, tested on a patched looks_franco (the three builder cases "Call us at 3pm or 9am.", "We open at 9am and close at 9pm, EU42 is in stock.", "Open from 9am to 9pm." and the El Ultimo Tango twice case still pass; the first three proofs block): drop the count once rule; read `\d{1,2}(?:am|pm)` as a time only next to a time word (at, by, before, after, from, to, until, till, around, between, and, or). The doubled digit shape and the pairs shape are left as accepted (misspellings and one title word).
Open from round 1, still pass old and new: `F50 mawgood, tawsil 2 le 3 ayam, 16,500 EGP.`, `el F50 mawgood fel 43.`, `mawgood ya basha, 16,500 geneh, tawsil youm.` (FRANCO_WORDS :89 has no shop words: mawgood, tawsil, fel, youm).

## 5. NOT_A_TITLE_WORD is a block list against an open class. RULED OUT on the demo titles, UNCONFIRMED on the real catalogue, low, not blocking
What: the list (:352) holds the gate's own cue, place, size, address, currency, number, unit, month, tier and count words, and it works: with "Nike Total 90" or "Nike Air Max 90" added, `Delivery to Alex total 90.` and `Shipping to Alex max 90.` block (90 read). But CUE_AMOUNT lets up to three filler words sit between a cue and the number, so any title word that reads as a filler hides the number: with "Nike From 90" `Delivery from 90.` passes (old blocks 90), with "Under 90 Boots" `Delivery under 90.` passes, with "Puma Future 7" `Delivery fee future 7.` passes, with "New Balance Furon v7" `The fee is v 7.` passes. "adidas X 15" is refused (x is a count title word). No real boot title I know puts a preposition before its number, and I did not open arena/real.
Fix: the round 1 one, a test over `store.titles()` that asserts no lead is in NOT_A_TITLE_WORD or in a short list of English prepositions and adverbs (from, under, over, around, about, approx, starting, now, extra, another, within), so a new product cannot open it later.

## Adjacent, one line each, not blocking
- `We have Vapor 17 pairs in 43.` passes old and new: STOCK_COUNT (:429) needs left, remaining, in stock or available after the unit word; "N pairs" alone is never a count.
- `Only Superfly 11 in stock.` and `Only Vapor 17 available.` pass new (old blocks both): the builder's call that "available" and "in stock" name the boot; with "only" or "بس" or "bs" before the title word the sentence reads as a count, so keeping the number in that one shape would close it (round 1 item 3, left open by the builder).
- `Phantom 6 جوز بس`, `Phantom 6 حبات بس`, `Phantom 6 goz bs` pass old and new: جوز and goz (pair) are count words nowhere in the gate.
- A newline between the model number and the tail (`Vapor 17\n,400`) strips; the phone shows two lines, so left.

## Cleared (RULED OUT, block in new)
All 18 round 1 item 1 shapes (blank, thin, no break, tab, two spaces, Braille blank, combining low line, both apostrophes, Arabic comma after a space with Western, Eastern and Persian digits, Franco), plus narrow no break space with and without a comma, a zero width joiner before the comma, mathematical bold digits in the tail, grave accent (EMPHASIS turns it into a space), U+066C and U+066B (western_digits maps them), `Vapor 17 000 EGP`. Thousands after a model: `Vapor 17 thousand`, `thousands`, `K`, `17k.` (now caught by model_thousands rather than by luck), `el vapor 17k`, `Superfly 11k.`, `ألف`, `الف`, `ألف جنيه`. Round 1 item 2 shapes: `Only Vapor 17 pairs left in 43.`, `Phantom 6 pieces left.`, `Phantom 6 left in stock.`, `فاضلين بس`, `fadlin bs`, `fadleen bs`, `units left`, a no break space before pairs. Titles with a cue lead (Total 90, Air Max 90, X 15) are refused. Script: an Arabic reply to "Do you have the F50?" is refused; `aywa el f50 mawgood b 16,500 geneh`, `ya basha el vapor mawgood ya basha.`, `el vapor mawgood w el superfly mawgood.` and `sha22a? la, mawgood fel ma7al.` are refused as Franco; a Franco reply to a customer who wrote "EU42" or "9am" passes in new and old alike (by design, no change).

No server or watcher was started by this round. The vite preview processes running on ports 4320 and 4330 to 4333 belong to the Ascent Platform session's scratchpad and were not touched.
