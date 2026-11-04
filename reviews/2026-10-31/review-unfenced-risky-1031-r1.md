# Review unfenced-risky-1031, round 1
*Created: 2026-10-31. Last updated: 2026-10-31.*

[Reviewer] Full, effort max. Scope: kit/model.py, kit/env.py, channels/whatsapp.py, assistant/mbox.py, plus engine/fast.py and reflection/fast.py on the whatsapp path. Tests: 1852 OK (2 skipped). Mutants: 13 run, 12 killed.

Verdict: PASS (nothing blocking; fix 1 to 5 before the repo goes public)

1. DRIFT channels/whatsapp.py:88-89. REQUIRED_ENV still needs BASETEN_API_KEY. .env.example:1 and docs/judges.md say one Meta key runs everything, and the model, judge and fast writer all run on Meta alone. Proof: with only META_API_KEY set, missing_env() gives ['BASETEN_API_KEY'] while keyed_legs() gives ['Meta']. Fix: drop it from REQUIRED_ENV and exit with NO_KEY_LINE when not model.has_key(). The same gap sits in reflection/night.py:73 (out of scope).

2. MINOR, LOW, CONFIRMED. assistant/mbox.py:88-90 and 143/195. One outside email crashes the whole read. charset=idna raises UnicodeError, which `except LookupError` misses. A Date of "Fri, 31 Dec 9999 23:59:59 -2300" raises OverflowError in astimezone. main() catches only Refused and OSError. Fix: catch (LookupError, ValueError) in _text, and have _when return None outside the years 1970 to 2100.

3. MINOR, LOW, CONFIRMED (builder flag 1). mbox.py:128. An inbound mail (Delivered-To present) with a forged From of the user counts as Sent, and "I will wire the money to IBAN EG12 today." is stored as a promise line. That breaks line 20 and DECISIONS 37. The model reach is RULED OUT for promises, because no code reads them. Style does reach the prompt through assistant/loop.py:40-52, capped at two sign-off lines of three words each, and it needs a third of all Sent. Fix: count any message with Delivered-To or Received as Inbox, and trust X-Gmail-Labels only as the first header.

4. MINOR, LOW, CONFIRMED (builder flag 2). mbox.py:86 decodes a whole part before the cut. One 41 MB base64 part peaked at 492 MB RSS, so a 200 MB file comes to about 2.4 GB. There is no cap across files, but the user picks the files. Multipart depth is RULED OUT: nesting of 1500 or more fails to parse and counts as skipped. Fix: skip a part whose raw payload is over 4 x MAX_BODY, and check the summed file sizes against MAX_BYTES.

5. MINOR, LOW, CONFIRMED (builder flag 4). reflection/fast.py:56-94. With NEVER as the guard, these notes pass: "Ask for a deposit by bank transfer first, then confirm the order." and "Ask for their national id and account password...". The send check has no payment rule, and DECISIONS 39 locks COD with no deposit. A note only reaches the same customer's next chat. Fix: add payment groups (deposit, transfer, instapay, wallet, card, upfront, عربون, تحويل, انستاباي) and personal-data groups (password, national id, account, قومي) to _NEVER_WORDS.

6. MINOR, LOW, CONFIRMED (builder flag 3). Fast writer calls skip kit.limits. They are bounded at 20 per sweep and one per chat ending, and an ending is never retried (tests/test_fast_reflection.py:191). No fix needed now.

7. MINOR kit/model.py:185. An ssl.SSLEOFError or a plain OSError raised during read() escapes raw: it skips the Meta fallback and breaks the ModelError-only contract. The key is not in the traceback (checked). Fix: `except (OSError, http.client.HTTPException)`.

8. MINOR, test gap. The mutant that drops the `>` quote cut at mbox.py:101 survives tests/test_assistant_mbox.py. Fix: add a Sent fixture with a `>` block and no "wrote:" line.

9. MINOR kit/env.py:10. A value keeps an inline comment (`KEY=abc # mine`), so the call gets a 401. Fix: cut ` #...` from unquoted values.

Ruled out: keys in errors or the fallback log (both mutants killed); signature checked before parsing, constant-time; replays deduped by message id; the sweep never raises (mutant killed) and never holds the DB lock during a model call; deep JSON only after the signature.

Note: findings.md says "Meta first, Baseten fallback". DECISIONS 33, judges.md and the code all say Baseten first. The code matches the decision, so fix the findings line.
