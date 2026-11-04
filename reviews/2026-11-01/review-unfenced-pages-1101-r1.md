# Review round 1: unfenced, branch pages, 9c415df..16a8813
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Suite in copy: 2372 OK. Probes: session scratchpad rvpages1/probes (p1 to p5); tried fixes in rvpages1/fixc (its pages.py change breaks test_three_days.py:120; use finding 2's fix).

Verdict: FIX FIRST (2 medium, 8 low).

1. MEDIUM, hold_high bypass. reflection/morning.py:592-601 modify, 502-511 person_line, 639-661 edit: Modify on a Today card starts a high risk line on trial with no yes (held correction plus note "Be kind." starts trying; note "Offer 20% off to anyone who asks the price." starts trying). Fix: hold_high through person_line and edit, True from modify; say it waits for a yes; test a held correction plus Modify stays WAITING with yes_at None. (If Modify should count as the yes, that is his call.)
2. MEDIUM. reflection/pages.py:327-331 night_lines says "passed the exam" when the exam failed, could not run or never ran (reads item["gate"]). Fix: carry the exam row's passed flag (morning.py:1113 _item); keep test_three_days.py:120 green; tests with failing and raising examiner.
3. LOW. /correct still goes idea -> Lessons.add on ALL: waits behind any trial, takes the level's share. Must call Lessons.correct() (DECISIONS 56, branch handoff a736f21) keeping the exam result, hold_high and the source text pages.CORRECTED reads. Box copy "Goes to a hotfix now" untrue until then.
4. LOW. Sample day answers use the real clock (morning.py:2445-2446); dates go wrong from 2 Nov. Fix: pass the day's clock to ACTIONS.
5. LOW. Roll back (morning.py:618-634, pages.py:443-449) shows no plan, one click pulls; stale refusal uses CLI wording; no tests. Fix: show the steps, plain refusal, tests.
6. LOW. GET with more than 8 query fields and POST with two back fields drop the connection (morning.py:2410, 2445). Fix: 400.
7. LOW. Modify runs the exam before cheap refusals (same text, length). Fix: checks first.
8. LOW. Old A3 actions /idea and /edit still served (no hold, no exam). Fix: drop or route through correct().
9. LOW drift. night_lines up to 9 sentences per agent vs LOCKS "one line per agent". Fix: cap at two.
10. LOW, incomplete. Pull is a disabled button (DECISIONS 54 pause switch to wire).

Security RULED OUT: XSS (h() everywhere, CSP default-src none), CSRF (token, Origin, Host), open redirect via back, demo writing the real db, Live and demo mixing, start_turns on a held line.
Not done: mutant sweep, Chrome walk at 390 and 1440, page_css.py, arena/scripted.py and sim/three_days.py beyond tests.
