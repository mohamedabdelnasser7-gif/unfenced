# Red team crossowner round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Red team on branch crossowner (5d6e6d9..e68d121), scratch copy, fake data, no network. Filed by root from the hand-back. Harness: scratchpad mytest and harness (e2e.py, battery.py).

1. CONFIRMED HIGH, reflection/shared.py:110 to 115, root cause kit/send_check.py NUMBER_WORDS and MAGNITUDE_WORDS. Spelled English digit runs (zero to nine), several Franco tens and a currency word glued to letters pass check(), so a phone, price, order id or quantity spelled out crosses owners (e2e: a spelled phone pattern added at owner A was served to owner B). A lost case's Writer input is the customer's own turns (shared.py:442), so a stranger can steer it. Fix: fold spelled digit runs and Franco and Arabic number words to digits before the digit and amount test; add the missing Franco tens and the glued currency case.
2. CONFIRMED MEDIUM, shared.py:235 owner_hash, :325, :334. Owners are counted by name only (an HMAC of a free string), so one actor under two names reaches the 2-owner threshold and inflates "learned from N owners" (console.py:899). Fix: key owners to an id the system issues, not a self chosen string.
3. CONFIRMED LOW, shared.py:344 _pattern_ok. On load any two distinct 32 hex strings count as owners with no key check, so a hand edited pool file forges owners. Needs file write. Fix: verify owner hashes against the key on load, or sign the file.
4. LOW: up to four words can be copied from a customer chat (COPY_RUN 5).

Ruled out: names, emails, links, handles, addresses and places in Latin and Arabic; symlinked folder, pool or key; owner hash collision; pooled lessons kept with no trial (POOL gated, no gate waits for a person, high risk needs a yes); B's Arena playing A's real customers (cards carry only pattern text and a worry label, train only); writer cost (GIVE 5, GIVE_LOST 5, inside the day cap, deduped).
