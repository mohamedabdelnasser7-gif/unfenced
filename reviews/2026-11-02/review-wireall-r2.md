# Review wireall round 2
*Created: 2026-11-02. Last updated: 2026-11-02.*

Reviewer Opus max, fix diff a92230e..eaecc37. Filed by root from the hand back (the agent could not write report files). Stopped at its cap with the mutant sweep 22 of 73; progress note in the session scratchpad PROGRESS-ae2525105011fe086.md.

Verdict: ISSUES, 1 medium, 5 low, no blocker.

Round 1 status: Medium 1 fixed (new hole, finding 1); Medium 2 and red team 1 fixed for another owner's folder (leftovers 2 and 3, fixed in aeea08b); Medium 3 fixed; red team 2 fixed; red team 3 partly fixed (finding 4). demo_store KEEP_OUT ruled out: only SHOPIFY_STORE plus SHOPIFY_TOKEN open the real store.

1. MEDIUM reflection/turn_exam.py:313-318, 358-371. The counted Examiner caches a "not reached" verdict on the run without the line, so one false negative from the judge switches good_model_judged off for that situation until the kept set changes. Fix: cache only "reached"; otherwise answer that good situation again without the line and count its calls.
2. LOW arena/practice.py:182. Owner cards under data/ refused. Fixed in aeea08b.
3. LOW security arena/run.py:216-226. Linked card files followed. Fixed in aeea08b.
4. LOW security. RecursionError still uncaught in kit/turn.py read_card and card_tools (built() catches Refused only), and owner.json has no size cap. grow.owner_name fixed in aeea08b.
5. LOW turn_exam.py:323-326. Pairs lean one way: the good judge can add "broke" but never "fixed". Counts are shown only.
6. LOW turn_exam.py:24-28. Agents whose good result needs more than one message read "not reached" on both sides, so the good check never fires before the first practice win. Options: an exam judge question on moving toward or away from the good result, or one practice round before a correction may go live as a hotfix. His call.
7. Test gaps: run.past_wins RecursionError (arena/run.py:749); G6 `_before` raising (fail open if changed); G7; G8 baseline fault cache drop.

Still open from round 1: low 4 labels by shape only; low 5 no_tools never set; low 6 judge calls not counted; T18 exam inside demo_store not pinned.
