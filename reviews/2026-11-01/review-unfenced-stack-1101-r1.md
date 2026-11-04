# Review round 1: unfenced, pages plus Quick start plus practice, b707973..180d599
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Stopped at 60 tool calls. Suite in copy 2537 OK. 70 mutants, 50 killed. Probes: session scratchpad review-stack-r1-rv/probes.

Verdict: FIX FIRST (2 medium, 4 low).

1. MEDIUM. reflection/morning.py:2690, engine/lessons.py:769 (2f7aeca): the live page's Judge (model call, 30 s timeout plus fallback) runs inside BEGIN IMMEDIATE for correct, modify, edit and idea; a second connection's write gets "database is locked" (5 s busy wait), so the live Sales agent's writes fail while the judge is slow. Fix: rate the line before page.one(), pass the result in; test the judge runs with in_transaction False.
2. MEDIUM. reflection/quickstart.py:216-219, kit/turn.py:136-147: every tool the model puts in risk.high.tools is kept; a card connecting only Store gives a turn that offers cod_risk, draft_order, find_order. Fix: plug tools are the connected tools only (QUICK_TOOLS), or turn reads card.json tools; test.
3. LOW. quickstart.py:83 NO_PERSON misses "hand off", "hand-off", "pass the chat to a team member", "transfer to a human" in instructions.md (DECISIONS 53). Fix: widen, apply to card fields, test each phrase.
4. LOW, unconfirmed. kit/turn.py:168: the full send check runs only with a "reply" action, which BUILD_PROMPT never asks for, so a Quick start WhatsApp agent gets only the style check (made-up prices and stock pass). Fix: full check when the card connects whatsapp, or clean_plug adds reply.
5. LOW. quickstart.py:340-349: Build presses limited only by the per-minute cap (about 600 calls an hour); the per-chat cap in the docstring is missing. Fix: cap Build calls per chat (3).
6. LOW, test gaps: quickstart size caps, draft cap, MAX_TURNS, link refusals, control-mark strip, built-name check, tmp cleanup, instructions hand-off check; pages.py:578 h() on the question; lessons.py:828 judge high hold; morning.py _demo env.load; kit/turn.py MAX_CALLS_PER_STEP and link refusal.

Earlier pages findings 1, 3, 4, 6, 7, 8, 10 proven by killed mutants; 2, 5, 9 have named tests, not mutated.
Ruled out: practice sends nothing real, no real order, no write outside the run folder; void on model error; made-up mark; stricter trust; Sales unchanged; Origin and token; escaping. DECISIONS 54, 56, 57 hold.
