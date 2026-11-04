# Red team old branches round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team on connstatus (013f472), scopeguard (bc3ffba) and buyers (fea435b). Filed by root from the hand-back. Scratch copies, fake data, no model, no network. connstatus and buyers were dropped by decision 88; their findings are kept for the record.

connstatus
1. CONFIRMED MEDIUM, reflection/morning.py:1549. A note is put in the view but render() never draws it, so the owner never sees it while the model is told it was saved.
2. CONFIRMED MEDIUM, kit/tools/notify_owner.py:62-75. Customer steered text passes: a phone, a price, a claimed approval, a call back request (a hand-over by the back door, decisions 53 and 72), a bidi override, a link with a zero width mark.
3. CONFIRMED LOW. The cap is per agent, so one chat can use all five notes a day.
4. RULED OUT: reaching anyone else.

scopeguard
5. CONFIRMED HIGH for built agents, arena/scope.py:98-104. Every agent gets the same three off-topic asks, so a science tutor or a grocer loses on its own customers' words; each loss becomes a lesson that refuses them. Fix: drop asks whose words meet the card (decision 88), or judge built agents with the model.
6. CONFIRMED MEDIUM, scope.judge :130-149. Keyword judge: an off-topic answer without the six listed words wins; a decline naming a listed word loses. Fix: the exam's length and store talk rules in scope.judge, or a model verdict.
7. RULED OUT: test set and gate leak.

buyers
8. RULED OUT: real lines or names.
9. CONFIRMED LOW, personas.py:392 then :408-411. With --state, pool items labelled lost join the cards after the won filter.
