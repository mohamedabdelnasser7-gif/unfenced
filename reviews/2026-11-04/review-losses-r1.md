# Review losses round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Full, reviewer at max, 7d613cf..1705018. Filed by root from the hand back. Probes: scratchpad rvl1/probes. Suite 3734 OK. Mutant sweep 68 valid, 48 killed.

Verdict: FIX FIRST (2 blocking, 1 drift, 3 minor, test gaps)

1. BLOCKING, kit/send_check.py _counted_thing and _duration_range (TIME_UNIT_THEN): loosened amount rules pass wrong prices, discounts and fees base refused (single digit plus thousands word or "and a half", grand, bucks, quid, percent, بالمية; fee ranges after a time word; "a day or 50"). Same prices_in feeds the fact check and the exam.
2. BLOCKING, engine/fast.py _plain_number_word: the note guard passes spelled prices, discounts and stock counts (charge, quote, less, back, around, we have). Reaches Arena quick notes and live Sales fast notes.
3. DRIFT, dead code: reflection/fast.py AgentNotes, CASE_SOURCE, notes_for; channels/whatsapp.py built_fast and its sweep; kit/turn.py turn(fast=) reached only from the Arena. No live channel calls kit/turn.turn.
4. MINOR, send_check said order number hides a total in Arabic word order ("اجمالي طلبك 2500").
5. MINOR, STOCK_COUNT misses an availability word after the number after الكمية.
6. MINOR, unconfirmed, arena/run.py known words for a built agent come from the demo catalogue (fails closed).
Test gaps: range lower bound, earlier line time word, TIME_UNIT_THEN 3 digits, raw 0, lone "1." list, guard "for" lead, refused drafts on a replied turn, fast_note non-string guard, AgentNotes source, quick_notes never_for and known words, rounds one-table check.

Ruled out: refused drafts escaped on pages; customer text in drafts (agent replies only; but see red team item 8 on quoting); notes crossing customers or agents; notes reaching gate matches; a note failure blocking a reply.
