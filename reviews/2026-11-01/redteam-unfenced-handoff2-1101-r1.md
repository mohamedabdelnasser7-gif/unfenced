# Red team round 1: unfenced, branch handoff, new parts abc8a36..5d60f6e
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team at max, paper plus local, saved by root from the hand-back. Proof script: session scratchpad redteam-handoff2-r1/attack_race.py. No critical or high.

1. MEDIUM, CONFIRMED. sales/quiet.py:84-90 (_close) and sales/loop.py:193-274 (turn): kit/db.py is one connection under an RLock, so each tx() is atomic but a turn is several. The sweep can close a chat after turn() opened it; the agent still replies in the closed chat, and if that turn makes an order the chat carries both order_created and chat_closed. Corrupts the lost signal for Reflection and the Arena; next message starts a new chat with the lost note. Same root as review finding 1. Fix: re-check newer user step and order_created inside the close tx; turn checks closed_at in the same tx as saving the user step (route to a fresh chat if closed); test that no chat_closed coexists with replied or order_created.
2. LOW, hardening. engine/lessons.py:315-321, 748, 765: Lessons.correct() skips the exam when no examiner and no exam result are given (tests/test_correction_hotfix.py starts a trial with no exam). Not reachable yet (only tests call correct()). High risk path safe. Fix: correct() fails closed without an exam result.

Ruled out: paused agent replying, sending a notice or closing; many notices; close hitting the wrong customer; hotfix note crossing customers (HMAC blocks spoofed from); order line twice; an unchecked line; faking a won chat; silencing another customer; typing leaking the token or stalling (3 s; residual: per-socket timeout, not attacker reachable); dots with no reply (by design); chat open forever (by design). Not re-audited: send_check amount and script logic.
