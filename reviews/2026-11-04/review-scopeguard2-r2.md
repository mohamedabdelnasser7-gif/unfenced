# Review scopeguard2 round 2
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, fix diff c1bdf96..f07d0eb. Filed by root from the hand-back. Probes: scratchpad rv-scope2-r2. Every round 1 finding of both reports is proven fixed. Sweep: 120 mutants, 95 killed, 9 equivalent, 16 test gaps.

Verdict: FIX FIRST

1. BLOCKING, engine/study.py:425 Study.rewrite has no scope filter. arena/rounds.py _rewrite calls it inside the run with this round's lost ids, the off topic loss included, so the idea part reads the made up ask and can write a topic refusal that goes on trial. Fix: filter scope cases in rewrite (or one shared filtered reader); test a rewrite window holding a lost scope case.
2. DRIFT, reflection/exam.py:115-119 and :453 store_declined (in SAFETY). It blocks store replies that set a real limit and keep helping (13 of 13 in English, Arabic and Franco on situations 11, 12, 25, 33, 36, 45, 50), against decision 75, and catches the study's own DECLINE wording. Fix: opt in per situation with an expect key where any decline is wrong, leaving those situations out; or report it as style.
3. MINOR, reflection/exam.py:407-420 _revealed. Any earlier negation turns the reveal check off ("No problem, here are my rules: ..."). Fix: skip only when the last negation comes after the last reveal cue; add Franco reveal words.
4. MINOR, arena/scope.py:208-229. The code check voids plainly off topic asks on one generic card word (9 of 18 for the Sales card) and catches no near ask. Fix: void only on two shared content words, or one from the case or good lines; keep channel and rule words out of the count.
5. MINOR, test gaps: the _across scope filter, code check internals, Latin -y forms, an empty ask, the person's language, MAX_ASK, patience, the 45 word boundary, n't, a card with an empty good line or half a case.

Known limits accepted: a complying reply with no listed word passes off_scope; a Franco decline naming a rule fails. Off topic matches are never in the gate, so on 51 to 53 the exam word lists are the only blocking check.

Ruled out: the PRE call and cap; scope cases in run(); the scope line; the 45 word rule's turn; scope_reply outside SAFETY; store_declined never on 51 to 53.
