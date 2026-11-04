# Red team round 3, unfenced-feed-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Red team (Fable 5.1) on head 8fd4dc0, fake data through the arena modules. Saved by root; status reported until root checks each item. Scripts: scratchpad rt-feed-r3/.

Reruns: value guards hold (1e308, NaN, inf, 2**53+1 refused); the run-2 stop is fixed; the owner folder link attack is ruled out (path resolved, folder 0700, file 0600). Names partly reopened.

## New holes
1. BLOCKING (red team call), MEDIUM, from ordinary customer chats. Names reach pool.items and the tagger prompt in 4 lost-chat shapes with no order:
   - clean.py:712: name_shaped refuses any Arabic word starting with ا (not ال), so surnames like اسكندر beside a [name] leak. Fix: drop that exclusion, keep the ال and verb checks.
   - clean.py:785 to 786: the beside rule crosses only spaces, so a comma, emoji or newline between first name and surname leaks the surname. Fix: use the loose gap.
   - clean.py:713: a lowercase Franco surname leaks when the message has any capital. Fix: decide lower per token for neighbours.
   - A bare surname with no cue anywhere in a lost chat still leaks (round 2 hole 2, second half).
2. LOW, not blocking. grow.py:383 _repeats_a_repeat catches repeated groups only; a group-free `a*a*...a*b` passes _capped_ok and hangs decks(). Needs a pool write. Fix: refuse more than 3 unbounded quantifiers, or match under a timeout.
3. LOW to MEDIUM, not blocking. run.py:279 reuses the saved split with no never= set; one --held-out run trains the saved gate cards, and the next run holds trained cards in the gate. Fix: pass never= trained ids on reuse and redraw on Refused.
