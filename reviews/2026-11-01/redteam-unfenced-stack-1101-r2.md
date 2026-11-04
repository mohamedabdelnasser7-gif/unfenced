# Red team round 2: unfenced, stack fix diff 180d599..d6c4517
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team, short, saved by root from the hand-back. Proofs: session scratchpad probe_r2.py, probe2_r2.py. No critical, high or medium.

Ruled out: tool grant and variants (other keys, actions, stages, needs spelled like tools, card.json edits from the page); rate-then-save swaps of line, stage or risk (classify takes no stage; a changed line fails closed); structural hand-off (hands_over dropped, no hand-off tool, with_person inert); Build cap reset by draft edit, Start over or parallel posts (single thread server).

1. LOW, CONFIRMED. reflection/quickstart.py:90-118 names_a_person wording gaps: letter-spaced "h a n d o f f", Cyrillic look-alikes (NFKC does not fold), all Franco, promises with no hand-over verb ("a teammate will reply", "a human will get back to you", "a colleague will continue"), split across card fields. Only a false promise in text; the agent has no way to hand off. Fix: a "who will reply, respond, get back, follow up, continue" branch, a Franco who-set, fold look-alike letters before matching.
