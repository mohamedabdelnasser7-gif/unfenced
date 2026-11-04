# Review round 1, unfenced-marketing-1031 and unfenced-assistant2-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max). Saved by root; status reported until root checks each item. Suites 2085 and 2070 OK; both branches merged together 2096 OK. Files: scratchpad rv-mkas1/.

## Marketing: FIX FIRST
1. MEDIUM, CONFIRMED (root saw engine/handover.py:107 to 110). An unusable spotter answer (bad JSON, {}, no l1, cut fence) reads as no kind, so a joke line is written and set to trying. Fix: no declared kind and no none for l1 raises PartError, so the line is held.
2. MEDIUM, CONFIRMED (root saw night.py:202). UNIQUE(from, to, until) with until = time.time() on the CLI, so two runs write two notes. Fix: refuse a note whose window overlaps an earlier row for the same from and to, or key on the Cairo date.
3. LOW. Overlapping windows resend the same note; covered by 2.
4. LOW, unconfirmed. Spotter batches 20 cases, so one planted case could tag others; impact only a guarded note.
Mutants 20 of 30 killed. Gaps: left-out case, tie between kinds, blind view, past 20 cases, plug-risk guard.

## Assistant: FIX FIRST
1. MEDIUM, CONFIRMED. clean_day (assistant/arena.py:181 to 219) leaves calendar location and notes, reply_to, from_name, snippet, hidden promise text and the day hidden block raw. Fix: rebuild the day from an allow-list of keys and types, clean every string left.
2. MEDIUM, CONFIRMED. clean() runs with no names, so surnames and a signature company survive. Fix: pass names from address local parts and display names.
3. LOW to MEDIUM, CONFIRMED (root saw arena.py:157). keep_finished open(a) follows a link, file 0644. Fix: O_NOFOLLOW, O_APPEND, 0600, folder 0700, as arena/personas._write.
4. LOW. No caller of keep_finished; docstring should say it waits for the live runner.
5. LOW. Prep notes sit outside the poison and mode checks.
6. LOW. take_finished drops a row added between read and unlink; a crash in practice_days stops main() before save().
7. Decision: item 37 says other people messages stay in the user account, and the pool keeps cleaned bodies of other people emails.
Mutants 25 of 34 killed. Gaps: two rows in one file, cc and calendar with addresses, style and seed kept, prep size limits, prep for every meeting.

## Both
night.py merges with one docstring conflict: keep both paragraphs. A test_hand_over subtest failed once under a narrowed pattern; full run passes.
