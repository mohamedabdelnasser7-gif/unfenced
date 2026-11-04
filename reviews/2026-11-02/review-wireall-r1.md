# Review: wireall, round 1
*Created: 2026-11-02. Last updated: 2026-11-02.*

[Reviewer]
Scope: unfenced branch wireall, 85bf10f..a92230e (4 commits), against DECISIONS 59, 51, 56, 20, 53, 57. Full level (customer data).
Files checked: 14 in the diff, plus arena/good.py, arena/grow.py owner helpers, engine/exam.py, engine/lessons.py and morning.py exam callers, kit/switch.py, sales/loop.py pause.
Suite: 2619 tests, OK (2 skipped), 77 s, on the pack copy.

Verdict: ISSUES (3 medium, 2 low, test gaps). No blocker, no high.

## What holds (proved)

1. Pause: kit/turn.py:258 checks the switch after saving the message and before any model call; no live sender for a built agent exists besides turn(). Removing the check fails test_a_paused_agent_sends_nothing (mutant killed).
2. Fail closed: a model fault, the per situation cap, an unreadable judge, a judge error in the rerun and a cap in the rerun all hold the lesson; every exam caller (engine/lessons.py:834, morning.py:664 and 925) turns a raise into could_not_run. Mutants T1, T2, T17, G1, G5, G11 killed.
3. Blend: owner_cards and blend pass only labels and numbers; no want, buy_trigger or example line reaches the model ask or the saved card. Mutants that add want or examples (M12, M12b) or copy every style key (M4) are killed.
4. Owner scope of the blend holds for a linked real-cards folder, a linked card, another owner, no marker and no plug owner (M6, M7, M20 killed).
5. No dashes and no drift words in the added lines.

## Findings

1. MEDIUM [reflection/turn_exam.py:207-240] The exam's "good" situations never check the good result. They pass when any clean reply goes out; the judge runs on "never" situations only, and its "not reached" is ignored (test_not_reaching_the_good_result_is_no_never_fail pins this). Failing scenario (probe p1_good_part.py): a built agent with no practice win; the agent calls its tool and then answers everyone "Sorry, we cannot help with that today."; the judge says not reached, nothing broken. The page correction "Tell every customer we cannot help today." passes and goes live at once as a 50/50 hotfix (state trying, share 0.5). With practice wins the Arena rerun holds it, so the gap is every agent before its first practice win.
   Fix: judge the good situations too, and fail a lesson when a good situation the agent reached without the line is not reached with it (the counted Examiner already runs both sides), so one turn limits never cause a false fail. Add a test with the unhelpful agent above.

2. MEDIUM, security, CONFIRMED [arena/practice.py:286-288, arena/gate.py:216-222] practice --cards takes any folder with no owner check, plays the cards whole (want, buy_trigger, examples go into the customer prompt) and saves each card whole as the persona of every match in the agent's arena-matches.jsonl. The flag is old, but the new TurnGate now replays those saved personas into the customer model at every exam of that agent (every night lesson, every page correction). Failing scenario (probe p2_cards_flag.py, made up demo cards standing in for real ones): owner A's agent practises with --cards pointing at owner B's agents/real-cards; exit 0; 83 card lines saved whole in A's agent folder; a later gate rerun put 12 of B's example lines into A's customer prompts. This breaks item 51 (never across owners) and item 59 (no real line moves) by a manual path. Severity medium: it needs an operator to pass the flag; no code calls it.
   Fix: refuse --cards unless the folder resolves inside the agent's own owner folder (grow.owner_of plus check_owner, dev and inode walk), and make TurnGate skip a past win whose persona is not made_up (or keep only behaviour fields when saving a persona from a real card). Test both.

3. MEDIUM [reflection/morning.py:2674-2687] An agent built on a running page is not wired into that page: live_morning reads agents/ once at start. Failing scenario (probe p4_live_build.py): Quick start builds stock_watcher on the live Morning; the folder and exam.json are written, but the page has no plug, no Pull and no exam for it, and a correction is refused "No plug for stock_watcher in this repo"; after a restart all three appear. Item 59 says every door with no hand work.
   Fix: after a successful Build, add the agent to the running page (plugs, lessons, trials, built, exams through night.agent_exam), or read with_built on each Agents page request. Test: build on a live page, then correct and pause it without a restart.

4. LOW, security, CONFIRMED [arena/madeup.py:231-234] The worry and why labels are checked by shape only (lower case letters, four words). Probe p3_labels.py: a card with worry "Ahmed Hassan" and why_unwinnable "Nasr City" sends "ahmed hassan" and "nasr city" to the model, and "nasr city" is saved as the practice card's why_unwinnable when the model writes none. Cards made by arena/cards.py only carry recipe worry names, so this needs a hand made or foreign card in real-cards.
   Fix: keep a label only when it is a known kind (the recipe's worry names when the owner folder has the recipe, plus "no budget"), else "other".

5. LOW [reflection/turn_exam.py:227] tools_called reads expect "no_tools", which situations_from never sets, so "a situation that expects no tool got none" (docstring line 19) never runs. Fix: set it for good and never situations, or drop the line from the docstring.

6. LOW [reflection/turn_exam.py:199, 236] Result.calls counts the agent's calls only; judge calls are left out, so the night's exam call count is low (the clean test run makes 7 calls and reports 6). The exam's calls are not counted against the day cap file either (same as the Sales exam). Fix: count judge calls in did["calls"].

## Tests that stay green with the guard removed (mutant sweep, 57 of 74 run)

Survivors: T18 (the exam runs outside demo_store: nothing pins that an exam never reaches the real store with Shopify keys; the most important gap), M5 (check_owner dropped from owner_cards: an owner folder inside the repo is not refused), T16 (binding count=False), T15b and T14 (binding's exam folder and agent name checks), M2, M3, M3b (why label raw, any shape label), M8 (card size cap), M10 (MAX_REAL cap; the demo set has exactly 8), M21 (unwinnable must be a bool), T4, T13 (hand keeps lessons not yet kept), G8, G9, G10 (rerun judge not counted against the cap, its cap handler, facts flag). Also no test refuses Build when the exam answer cannot be read (quickstart.py:527-529).
Not run (stopped at the token cap): K5, W1, MO1 to MO5, N1 to N4, Q1 to Q3, PR1, PR2.

## Rules check

Copy rules on the new page and report lines: plain, no dashes. Secrets: none in the diff. Deploy: none. Other reviewer tier rules not relevant.

## Notes for the caller

Probes and runner: scratch/rv-wireall1/probes and scratch/rv-wireall1/scripts/mut.py. The scratch copies rv-wireall1/head, base and work come from git archive and include the tracked arena/real folder: delete them when done (work may hold one mutant left applied by the stop). Not checked: whether demo_store's KEEP_OUT covers every key find_order and delivery read.
