# Red team round 1, unfenced-marketing-1031 and unfenced-assistant2-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Red team (Fable 5.1, max), read-only plus fake-data probes. Saved by root; status reported until root checks each item. Scripts: scratchpad rt-mkas1/.

## Marketing
Ruled out: case text in the note (NoteWriter sees only kind, about and counts), names or numbers past guard (engine/risk.py:273, 308), HTML or ids on the Morning page (reflection/morning.py:1150, 1886).
1. LOW, unconfirmed (paper). sort() is a same-model gate on customer-derived text with no source floor (engine/study.py:495 to 506, engine/handover.py:96). A crafted chat could push a joke into a sales lesson or hold back a real one. Fix: an affirmative sort holds the line for a yes. Not blocking.

## Assistant
1. BLOCKING, medium. clean_day cleans only subject, body, title and text; other fields (preview, snippet, reply) pass with name, phone, email and address. assistant/arena.py:180 to 221 (loop :209). Fix: clean every string value; allow only ids and checked YYYY-MM-DD dates.
2. BLOCKING, medium. take_finished: a deeply nested day raises RecursionError past the except at arena.py:241; practice_days() runs unwrapped at reflection/night.py:546 before save(), so the night report is lost, and the file is never removed, so every later night crashes. Fix: broad except per line, cap line length and count, quarantine the file on failure.
3. LOW. _clean_text keeps any YYYY-MM-DD run, so up to 8 digits pass the number cleaner (arena.py:167 to 178, ISO_DATE :73). Fix: clean first, put back only real calendar dates.
Ruled out: a send path from prep notes (tool-less, user-only, no text logged); ReDoS in arena/clean.py. Minor: prep_facts topic match can pull other threads' snippets into user-only facts.
Reach: keep_finished has no caller yet; fix 1 and 2 before wiring it.
