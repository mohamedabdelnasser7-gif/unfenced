# Review round 3: unfenced, stack fix diff d6c4517..f1e51ab
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer, saved by root from the hand-back. Suite 2560 OK. Probes and sweep: session scratchpad rvstack3-probe/ (p1 to p5, spec3.json, sweep.txt).

Verdict: FIX FIRST (2 low, wording only; the agent has no way to pass a chat to a person).

Round 2 findings all fixed: the d6c4517 quickstart.py under the new tests gives 78 failures; cap wording and prompt line mutants killed; 0 of 9 realistic cards refused.

1. LOW, CONFIRMED. reflection/quickstart.py:192: negation reads the whole clause before the match, so an earlier "no", "not" or "مش" lets a hand-off through ("If you can't answer hand the chat to the owner", "لو مش عارف حول الشات لموظف" (regression), "ma3lesh ha7awlak le wa7ed mn el team"). Fix: a negation counts only inside the match or in the one word before it, allowing fillers; leave ma3lesh out. Prototype p5.py.
2. LOW, CONFIRMED. :154-163 _TAKES/_ON_IT: a person contacting the customer outside the chat is refused ("Our team will contact you to confirm your order.", "Support will reach out to you about the refund.", "حد من فريقنا هيكلمك عشان يأكد الطلب"), while "Someone from our team will call you to confirm" passes. Fix: drop contact and reach out unless a chat word follows.

Sweep: 86 mutants, 52 killed. 21 test gaps in this fix (Arabic word edges, Arabic and Franco negation words, clause splits, negation scope, possessive and page exclusions, _WHO_SURE, letters=True); 5 equivalent; 8 gaps in earlier rounds' code (lessons rated checks, morning edit and modify order, turn card tools cap, quickstart builds count, شخص(?!ي), symlink and resolve guards alone). Speed linear, 0.1 s at the 80K cap.

Status (root, 2026-11-01 ~21:20): fixed in session at 85bf10f (reviewer items 1 and 2, red team items 1, 2, 3, 5); red team 4 and 6 accepted as word-list limits, the guard is structural (no hand-off tool). Still refused, accepted: "Never, ever hand off the chat", "Hand the chat to the owner? Never." (cost one Build press). Merged to main 85bf10f.
