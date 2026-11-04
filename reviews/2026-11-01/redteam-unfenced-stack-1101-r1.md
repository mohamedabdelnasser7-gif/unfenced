# Red team round 1: unfenced, pages plus Quick start plus practice, b707973..180d599
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team at max, paper plus local, saved by root from the hand-back. Proofs: session scratchpad proof_rt.py, proof_rt2.py. No critical, high or medium.

1. LOW, CONFIRMED (same as review r1 finding 2). reflection/quickstart.py:219 clean_plug, kit/turn.py:140-147 tools_of: model-declared tools in risk.high.tools are kept, so an agent gets tools the user never connected (proof: connected none, offered cod_risk, store, draft_order, find_order). Only practice reaches it today (demo store, in-memory db, sends to a list), so LOW; MEDIUM once a live runner ships. Fix: high tools = connected only; test.

Ruled out: writing outside agents/ or traversal; overwriting sales, assistant, marketing; symlink plants; hand-off or with_person in plug and instructions (variants refused); loose trial or high risk off; HTML or script in the card (h(), CSP none); a huge quickstart.json; model call burn (10 a minute shared); CSRF on Build and Send; practice sending a real message or order, calling an unnamed tool, writing outside the run folder, reading keys; gaming the good-line judge (booleans only, code checks first); high risk correction or Modify with no yes (earlier pages finding 1 closed); exam bypass; pausing another agent or cross origin; set_by tampering.
