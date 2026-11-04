# Review engfix round 2
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, fix commits 2b0faaf..a7dd41e. Filed by root from the reviewer's hand-back. Probes: scratchpad rv-engfix2/probes (p4 to p9, mut3.py); proven fix for finding 1 in rv-engfix2/m3/reflection/exam.py. Suite in copy: 3050 OK.

Verdict: ISSUES (1 blocking, 1 drift, 3 minor)

Earlier findings: B1 FIXED (p1 marks 60 of 60; old plug fails 159 tests). B2 PARTLY (reruns fixed, first run on the kept lessons still open, finding 1). D3 FIXED. S4 FIXED. M5/RT3 FIXED. M6 FIXED. RT1 FIXED (81 of 83, 2 ruled out). RT2 FIXED in the plug. RT4 FIXED. RT5 FIXED. Mutants: mut2 survivors E4, E5, N7 equivalent; mut3 85 run, 54 killed, 3 equivalent, 28 test gaps.

1. BLOCKING, reflection/exam.py:424 and :472. The first run on the kept lessons still grades an empty reply through the normal checks and is cached, so a lesson that invents an amount on that situation counts as "not new" and passes, for every lesson until the kept set changes. Probe p4. Fix: empty_raises=True on both runs on the kept lessons; in full mode do not cache a run with an ANSWER row. Add p4 as a test.
2. DRIFT, sales/plug.json (lines 66 to 155). The new patterns mark plain tone, order and size lessons high: English 40 of 43 probe lines, Arabic 10 of 16 (بلاش as "don't", اعرض على as "show to"), Franco 6 of 9. Breaks decision A for natural wording outside the tested set. Fix list: drop within and swear; fee skipped or covered and no fee charged not before talk, question, details, line, info, times, emojis, lines; added to every order and total brought down need a thing or money word; drop make sure they get, for sure, they'll get it, you'll be with them; three digit pattern only with separators between groups of 3; said or quoted needs 3+ digits or a money word; بلاش and balash free only at clause end or before ل/lel; drop اسرع وقت alone and عرض علي; add p5 lines to STAYS_LOW.
3. MINOR, sales/plug.json:107-121. "Agree to the price they ask for", "Add a water bottle as a thank you" and Arabic and Franco agree lines still unmarked. Fix: copy the two note guard patterns into the discount group plus وافق على السعر and wafe2 3ala el se3r.
4. MINOR, tests. 28 mutant survivors: whitespace only reply, three Franco amount patterns, 24 words without a line. Fix: one line per word and pattern table test, whitespace case in EmptyReruns.
5. MINOR, marketing/plug.json:75. "publish" marks "Publish in the evening" high. Keep publish_post, drop plain publish; promote to spend if root agrees.
