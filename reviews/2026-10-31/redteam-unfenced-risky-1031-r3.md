# Red team round 3: unfenced risky tier
*Created: 2026-10-31. Last updated: 2026-10-31.*

Fix bbdd166 on e6372b4. Paper plus a private copy (rt-copy, git archive of bbdd166), run with python3 -I. No live call; no .env, data or private-data opened; fake data only. Scripts: scratchpad review-unfenced-risky-r3/rt-attacks v0 to v5, plus the r2 a1 to a5 rerun. Nothing I started is left running.

## Round 2 fixes: all confirmed fixed (a1 to a5 reran against bbdd166)
R2-1 arena/factcheck.py:300-336,396: comma, colon and Arabic ،؛ asides in every order now FAIL (v1). R2-2 mbox.py:110: attached message gone. R2-3 mbox.py:72,146: Arabic Outlook block cut. R2-4 reflection/fast.py:86-152: 48 passing paraphrases down to 21, mostly allowed topics. R2-5 env.py:16,32: comment after a quote cut. R2-7 send_check.py:305, factcheck.py:198: "Vapor 17 EGP" now FAILs, Arabic-comma thousands read right.

## New findings (all low)
R3-1 CONFIRMED low. assistant/mbox.py:110-124, _parts. A multipart/digest child that declares an explicit Content-Type: text/plain is yielded as a leaf, so a stranger's mail forwarded in that part reaches the model as the user's words (v2). Same class as R2-2, which the fix meant to close. Low: it needs the untrusted text inside a Sent digest, which users rarely send. message/rfc822, message/partial, external-body, attachment, filename= and filename*= are all skipped right. Fix: also skip the subparts of a multipart/digest.

R3-2 CONFIRMED low. engine/fast.py:380-392, _capitalised. The name rule is evaded three ways (v3): a lowercase copy ("ask ahmed"), a sentence-initial name, and any Arabic name (isupper is false for Arabic), so for the Arabic customer base it does nothing. Low: a first name is not a figure, promise, discount or date.

R3-3 CONFIRMED low. reflection/fast.py:86-152. Paraphrases that still pass (v3): "the price holds", "stands as is", "nothing to add or extra for the courier or shipping", "ships right away", "by the time they travel", "stand behind every pair", "sort it out if it doesn't fit", "knock a bit off". Long tail, one layer.

R3-4 CONFIRMED low, correctness. arena/factcheck.py:198-205, kit/send_check.py:305. "Vapor 17k", "Vapor 17 thousand" or "Vapor 17 الف EGP" (a wrong boot price near 17000) passes: MODEL_NUMBER_END keeps the 17, but prices_in reads no amount from the k or word forms (v0). Pre-existing; the fix comment ("Vapor 17k are amounts") overclaims.

## Ruled out
- western_digits (send_check.py): clearly wrong Arabic-comma prices are caught; the only pass is the pre-existing cross-product one (20000 accepted for the Vapor Elite because it is the Superfly price), which repeats with a plain comma (v0, v1). No new bypass.
- Sweep stop at the limit (reflection/fast.py:292): sound. 22 repo tests pass, the loop is bounded, deferred endings keep their note for the next sweep, a failing limit never crashes it (v5). The one shared LIMIT_KEY is a by-design spend cap.
- Quote and forward headers (mbox.py:72): "Forwarded message", "Begin forwarded message", "مرسل:", a tatweel or diacritic in a keyword, and a "wrote" line with no colon are each unrecognized alone, but a recognized header (From:, من:, إلى:, الموضوع:) in the same block cuts the body, and the attacker does not set the client's quoting. An end-to-end inline forward leaked nothing (v2). Coverage note only.
- env quoting (kit/env.py:32): no crash, no leak; `"x"#nospace` keeps the quotes and comment, pre-existing, fails closed (v4).
- U2 (extra named only in the customer's turn): still passes, now also when the reply names the boot in another sentence (v1). Out of scope per root.
- is_sent: no new wrongly-Sent path (v2, a3).
