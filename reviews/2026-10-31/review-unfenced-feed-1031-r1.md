# Review round 1, unfenced-feed-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on c359f80..df37745 (arena/grow.py new, arena/run.py, arena/personas.py, arena/cards.py, engine/plug.py, reflection/night.py, tests/test_arena_grow.py). Saved by root; status reported until root checks each item. Suite in the copy: 1966 OK.

**Verdict: FIX FIRST.** 4 blocking, 2 drift, 3 minor.

1. BLOCKING, CONFIRMED medium. Real customer names reach the pool file and the tagger prompt (grow.py:321, :340, :286, :297). real_chats builds chats with no names and drops the draft_order name from tool_calls; Cleaner() gets no names, so a full name with no cue word passes. Probe rv-feed1/p5.py. Fix: collect names from name-taking tool calls into Chat.names, build Cleaner(names), test a no-cue full name.
2. BLOCKING. A chat can end up never read (grow.py:322 to 339; kit/chats.py:108 to 116). One chat per customer per channel forever, so a repeat customer's later talks are never read; unclear states other than OPEN are marked final though often mid-chat (handed to a person at night); leftovers past MAX_NEW or a cap fall out of the window. Probe p1.py. Fix: track by last step read, mark only settled states (won, lost, NO_PRICE), keep pending ids and read them first next night.
3. BLOCKING. The measured gate moves and leaks as the pool grows (run.py:661 to 662, 285, 214 to 249; grow.py:259 to 266). Grown cards join before split, so the held-out set changes with each new card and a trained card can become a gate card; loss weights also reach gate draws. Probe p3.py. Fix: split base cards first and keep the split fixed (or save held ids), never hold out a card with training plays, draw gate cards at pre-loss weights.
4. BLOCKING. After reweighting, the printing cap (item 33) and the unwinnable share hold on the whole deck, not on training draws (grow.py:259 to 267; run.py:51 to 58). Probe: printing 0.249 of the deck but 0.374 of training draws. Fix: apply weights, side shares and cap_wants to training cards after the split, and separately to gate cards; test the training-draw share.
5. DRIFT. Loss counts attach to whatever card later carries a persona-NN id, and never fade (cards.py:179; grow.py:144 to 145). Weight 1 + 3 x lost has no cap or decay. Fix: key losses by a stable group key (worry plus why_unwinnable); cap or decay needs Mohamed's call.
6. DRIFT. Owners told apart only by folder layout; the two --state flags mean different folders (grow.py:79 to 82; personas.py:499 to 505 vs run.py:661). Two single-agent owners side by side share one pool (probe p6.py). Fix: an explicit owner marker before a parent folder is shared, else the agent's own folder; one --state meaning.
7. MINOR. Imported history chats and branch chats can be read as real chats (grow.py:281 to 283). Fix: AND channel NOT LIKE 'history:%', pin both filters with tests.
8. MINOR, CONFIRMED low. Pool write follows a link at the .tmp path and is world-readable until chmod; mkdir uses umask; a grow error escapes night.main before the report is saved (grow.py:179 to 187; night.py:523 to 527). Fix: os.open O_CREAT|O_EXCL|O_NOFOLLOW 0600, mkdir 0o700, wrap the step into rep["practice"]["stopped"], check style shape in _item_ok.
9. MINOR. Mutant sweep 56 run, 41 killed, 15 survived: m47 (practice.save skipped), m52 to m54 (personas folding off), m25, m26, m17, m44, m16, m28, m29, m31, m33, m40, m08, m09. Equivalent or near: m42, m12, m37. Fix: a test per behaviour.

Checked and fine: a kind cannot name a path; a pool path or link to another owner is refused; a pool inside the repo outside data/ is refused; gate and replay matches never record a loss; the tagger gets cleaned turns only; the call cap is shared; no --recipe reads no chat; no secrets.

Probes: scratchpad rv-feed1/ (p1, p3, p4, p5, p6, mut.py).
