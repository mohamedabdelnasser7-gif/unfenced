# Red team round 1: unfenced, branch pages 9c415df..16a8813 plus typing 9c415df..cf33adc
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team (Fable 5.1, max), saved by root from the hand-back. PoC: session scratchpad redteam-pages-r1/poc_modify.py. Paper and local attacks only.

1. CONFIRMED, MEDIUM. High risk hold bypass through Modify and the old /edit: engine/lessons.py:732, 745 hold only when hold_high is passed; only Morning.correct passes it (morning.py:609-610). modify (592-601) -> edit (660-666) -> person_line (502-511) -> lessons.add without hold_high, so a modified high risk line starts its trial with no Today yes. The assistant agent has no examiner, so there it starts with no exam either. Same as reviewer r1 finding 1. Fix: hold_high=True through person_line from modify and edit; test that it stays WAITING with yes_at None.
2. LOW, not reachable. Graph.typing raises TypeError on a non-string id (channels/whatsapp.py:285); parse only passes strings. Fix: isinstance guard (in the typing fix).

RULED OUT with controls: CSRF (Origin plus hmac token), DNS rebinding (Host check), back open redirect and CRLF (pages.py:115-120), stored XSS (h() everywhere, CSP default-src none), demo day writing the real db (temp copies), path traversal via day or --demo-days, /correct high risk hold, roll back plan code, typing id injection, typing token leak.
