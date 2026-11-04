# Review round 1: unfenced, branch handoff, new parts abc8a36..5d60f6e
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Stopped at 60 tool calls; mutant sweep not run. Suite in copy: 2380 OK (2 skipped). Probes: session scratchpad rv-ho2 (p1_races, p4_olddb, p5_hotfix, p8_count3). Root reran p5 and p8 on wt-handoff: both confirmed.

Verdict: FIX FIRST (5 medium, 2 low).

1. MEDIUM. sales/quiet.py:52-63, kit/chats.py:156-165: tick works from one open_chats snapshot; close() checks only closed_at IS NULL. A chat that got a message during another chat's notice send (up to 20 s) is closed anyway; a message saved between open() and add_step lands in the closed chat. Fix: close(chat_id, at, last_seen) with NOT EXISTS newer user or assistant step inside the UPDATE; open plus user step in one transaction or add_step(user) refuses a closed chat; a test per race.
2. MEDIUM. sales/quiet.py:52, channels/whatsapp.py:455-498: a message accepted by the webhook but still in the worker queue does not count; a yes 5 s before close lands in a new chat with no history; a question 5 s before 30 min gets the notice. Fix: skip a chat whose customer has a pending seen_messages row; test accept, tick, work_one.
3. MEDIUM. kit/chats.py:71-99, sales/quiet.py:55-58: after the migration or any downtime the first tick sends the notice to every old open chat (3 days, 5 hours old), then closes them all. Bulk customer message at deploy (rule [deploy]). Fix: quiet already past NOTICE_AFTER plus CLOSE_AFTER (or several ticks past NOTICE_AFTER) closes silently; migration sets closed_at on old chats; test on an old-schema db.
4. MEDIUM. reflection/morning.py:769-775 vs engine/lessons.py:364-378: a high risk correction saved by correct() has yes_at set, so _card shows no Yes card and it waits forever (DECISIONS 56 says it waits for a yes on Today). Fix: one engine method for "held for a yes" used by approve SQL and _card; morning test.
5. MEDIUM, regression from 389983d. kit/send_check.py:539-542: "Only 3 pairs are in stock.", "Only 2 pieces are available.", "Hurry, 2 pairs are in stock.", "Only 2 pairs are now available." now pass (refused at abc8a36). Candidate fix in rv-ho2/fix1: optional (?:(?:are|is)\s+)? after the count noun in STOCK_COUNT's first branch; keeps "UK 8 is in stock.", "Option 2 is available.", "Your order has 2 pairs." passing. Suite not run on it.
6. LOW. Lessons.correct() and switch.pause()/resume() only called from tests; wire on the pages branch (already planned: pages finding 3 and 10).
7. LOW. test_send_refusal_carries_metas_error_code went with test_relay.py; Graph.send SendRefused from None with Meta's code and MAX_ERROR_BODY is untested. Move it to test_whatsapp.py.

Clean: 86 removed tests all belong to 53 (moved guards still exist); pause stops notice and close, quiet counts from resume; over-limit gets no notice; typing after pause and limit, 3 s; no hand-off path left; old handed_off rows read safely; lost not counted twice; Arena and recorded replay pass; sweep cost fine.
