# Review scopeguard2 round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, a27acac..c1bdf96 against decisions 85, 88, 89. Filed by root from the hand-back. Stopped at the 250K cap with 27 of 73 mutants run. Probes: scratchpad rv-scope2-r1.

Verdict: FIX FIRST

1. BLOCKING, arena/learn_built.py:164-205 (from_folder, run by the night). A won off topic match of a built agent is written as a case ending on the plug's good result, so the night learns from a result the agent never reached. Fix: skip saved matches with off_scope and won true; test expects written 0.
2. BLOCKING, arena/scope.py:184-186. The 45 word rule counts every agent reply: a long opener in a case the agent starts, or a long on topic answer after the person comes back, loses. Fix: apply it only to the reply to the ask, as the exam does; tests for both shapes.
3. DRIFT, reflection/quickstart.py:364-377. The scope line uses only the case input and output and leaves out does, so near neighbours (a wrong item ticket, a pastry caption) read as outside the work. Fix: build it from does plus the case, with the judge's boundary: requests people could fairly expect from this work are yours; decline only what has nothing to do with it.
4. DRIFT, reflection/exam.py:63 and 322-335. off_scope is a safety check but two of its parts are style (length, a store word), against decision 75; plain declines fail and a short poem passes. Fix: block only on the complied part; report length and the way back as style; widen the store words.
5. MINOR, reflection/console.py:53 keeps FULL_CAP 400; import rounds.FULL_CAP (440).
6. MINOR, arena/scope.py:60. No "when unsure" rule for on_topic. Fix: when unsure, on_topic is true.
7. MINOR, arena/scope.py:80. k % 10 plays two off topic matches at 20; decision 89 says match 10. Fix: k == EVERY.
8. MINOR, test gaps: cap checks around the writer and judge, an off topic match played as training, a keyed run plays the match, the judge retry, a judge error halting the run; morning and quick tests check source text, not behaviour.

Ruled out: no key never fakes it; never a test customer, gate, trust or pool; FULL_CAP 440 covers 424 calls; the Arabic prefix change misses no real case; injection is owner only; leaving off topic wins out of past wins and losses off the lost list is needed.
