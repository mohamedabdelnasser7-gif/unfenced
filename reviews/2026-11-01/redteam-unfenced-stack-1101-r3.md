# Red team round 3: unfenced, stack fix diff d6c4517..f1e51ab
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team, short, saved by root from the hand-back. Proof: session scratchpad probe_r3.py (old_qs/ holds d6c4517). No hand-off exists in the agent; every item is a false promise in text. All LOW.

Ruled out: the 8 round 2 lines; hidden characters, U+2028, minus sign, Greek, Armenian, small caps (all fold); slow inputs (linear, 97 ms at the 80 KB cap); spaced join on innocent lines ("S M L", "L.E.", "P.S.").

1. CONFIRMED, regression. reflection/quickstart.py:110,130-141: every hand pattern now needs an object; "hand off to the owner", "Transfer to a human", "Pass to someone from our team", "Use the hand off tool" pass (refused at d6c4517). Fix: hand verb plus who with no object.
2. CONFIRMED. :174-178,192: any earlier negation word clears the clause ("It never guesses prices and the owner will reply to you", "If the bot cannot help a human will take over", Arabic and Franco too). Fix: negation counts only with no and, but, or "when" between it and the verb.
3. CONFIRMED. :179,189: a comma, Arabic comma, parenthesis or line break inside one promise hides it ("The owner, Mohamed, will reply to you"); a literal tab in the plug JSON too. Fix: match the whole field as well.
4. CONFIRMED. Spellings: "ha ndoff", "hand o ff", "hand·off", "hand0ff", Franco "7awwel", "hawel", "ba3t", "sallim", "lel manager".
5. CONFIRMED, false refusals. :169-172: "The team shirt is red.", "The owner is Kamel." refused (Franco red, rd, kamel); :140 "Our team will contact you to confirm the address" refused; "Handing the chat to the owner is never done" refused. Fix: Franco verbs only with a Franco object.
6. UNCONFIRMED, design limit: finite word lists ("We will get back to you", "Type HUMAN to talk to a real person", "الشات هيتحول لموظف"). The prompt line is the real guard. Mohamed's call.

Status (root, 2026-11-01 ~21:20): fixed in session at 85bf10f (reviewer items 1 and 2, red team items 1, 2, 3, 5); red team 4 and 6 accepted as word-list limits, the guard is structural (no hand-off tool). Still refused, accepted: "Never, ever hand off the chat", "Hand the chat to the owner? Never." (cost one Build press). Merged to main 85bf10f.
