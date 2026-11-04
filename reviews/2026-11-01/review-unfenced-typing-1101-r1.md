# Review round 1: unfenced, branch typing, 9c415df..cf33adc
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Suite in copy: 2335 OK. Meta docs checked today (developers.facebook.com/docs/whatsapp/cloud-api/typing-indicators): body and endpoint at channels/whatsapp.py:287-289 match; dots end on reply or after 25 s; rule "only display a typing indicator if you are going to respond".

Verdict: FIX FIRST (2 blocking, 1 blocking test gap, 1 minor). Mutants: M1 drop the call, M2 dots when over, M3 dots after download, M4 timeout 600 survived; M5 to M8 killed.

1. BLOCKING. :292 typing uses timeout=self.timeout (20 s) on the single worker thread; a slow Graph can hold this and every queued reply up to about 40 s. Fix: TYPING_TIMEOUT = 3, timeout=min(self.timeout, TYPING_TIMEOUT), test pins it.
2. BLOCKING. :557-559 dots and read receipt go out before turn() decides to reply; turns that send nothing: with_person on main, a paused agent after the handoff rebase, a customer pushed over the limit inside the turn (loop.py:440). Root adds: after DECISIONS 57 a no-safe-reply turn also sends nothing. Fix: pass a typing callback into loop.turn, call once after the stage, pause and limit checks, before the model call; tests for no dots in each no-reply case.
3. BLOCKING (test bar). tests/test_whatsapp.py:433-458 test Graph.typing alone; add a worker test: typing once with the wamid before download, not when over, not when paused, reply still sent when typing returns False.
4. MINOR. :285 a non-string id raises TypeError outside the try; add isinstance check and 12345 to the odd ids.

Security: token in logs, id injection, limit counting, response size, HTTPError leak all RULED OUT. Rebase with handoff 4f502f9: merges clean.

Round 2: fix diff only; rerun M1 to M4 plus a mutant that drops the no-reply skip.
