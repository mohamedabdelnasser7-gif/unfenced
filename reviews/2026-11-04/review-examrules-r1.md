# Review examrules round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Quick check, reviewer at high, d470fba..d4bda85 (decision 94). Filed by root from the hand-back. Scratch: rv-examrules1. Feedback strings unchanged on 14 replies (0 differences); no reply path missed; no secrets in the prompt; any agent.

Verdict: FIX FIRST

1. DRIFT, kit/send_check.py:196-210 prompt_rules leaves out four enforced rules: stock count (on the exam's SAFETY list), sympathy lines, banned words, links. Fix: constants shared by feedback and prompt; stock line only where the rule applies; tests; rerun the exam.
2. STALE, reflection/quickstart.py:96-99, 780. HOUSE_STYLE repeats the style in other words in every built agent's instructions and tells "no # headings", which the check does not enforce. Fix: drop it from finish_words, or build it from the constants without headings.
3. MINOR, test gap: no test pins the rules ahead of the lesson slot in kit/turn.py:335 and sales/loop.py:130 (two mutants survived). Fix: one order test per builder.
4. MINOR, kit/send_check.py:172. Agents with no customer channel are told "WhatsApp shows the ** as they are". Fix: cut it in prompt_rules for agents that are not full_check.
