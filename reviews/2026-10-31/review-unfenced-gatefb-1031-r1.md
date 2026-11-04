# Review round 1, unfenced-gatefb-1031
*Created: 2026-10-31. Last updated: 2026-10-31.*

Reviewer (Opus, max) on c359f80..709b72d (engine/exam.py, engine/study.py, reflection/night.py, reflection/study.py, arena/rounds.py, sim/scripted.py, arena/factcheck.py, engine/fast.py, reflection/fast.py and tests). Saved by root; status reported until root checks each item. Suite in the copy: 1975 OK.

**Verdict: FIX FIRST.** 1 blocking, 3 drift, 2 minor.

1. BLOCKING. The Morning page never names the failed line on a card close to one (reflection/morning.py:1191; sim/run.py:103, :143). _status reads only close_to_pulled; study.py:434 puts the line in close_to_failed. Fix: a close_to_failed branch in morning.py _status and sim/run.py ('It comes close to the line "X", which failed the eval gate.'), update text at morning.py:51 and :2026, a render test.
2. DRIFT, CONFIRMED low to medium. The add-on rule uses extras named anywhere in the reply even when its sentence names a boot or tier, so wrong boot prices pass again (arena/factcheck.py:320 to 324). Probes rvgfb1/scripts/addon_probe.py and two_extras.py, e.g. "The Vapor 17 Elite is 400 EGP more than the Pro. We can also print your name." passes (real gap 5,500). Fix tried on a copy: line 322 `for e in (here or extras_named(sentence, extras, items) or (backdrop if not sentence_boot else []))`; all price tests green; trade-off "The Vapor 17 Elite is 400 EGP extra." after "with printing?" is refused, as on base. Add tests.
3. DRIFT. _failed_tries treats a failed lesson a person said yes to as failed again once its trial is pulled (engine/study.py:240 to 246), against root's call. Probe study_probe.py. Fix: skip a failed lesson that ever had a trial; test.
4. DRIFT, CONFIRMED low. Small rewordings of a failed line pass the closeness rule ("Water beds early." ratio 0.63) and the prompt hands the failed line over word for word (study.py:757 to 768; reflection/study.py:37 to 39, 89 to 91). Gate still runs. Root call: add a word-overlap rule for failed lines (content words subset or superset, or overlap 0.6 or more).
5. MINOR. The first-word rule refuses ordinary notes whose opening verb the customer typed: 12 of 15 refused vs 2 on base (opener_probe.py; Recommend, Reply, Look, Think...). Round 3 set: 4 of 14 refused vs 9 on base. "Don" passes as an opener. Root call: at a sentence start, refuse a word only when the source wrote it with a capital outside its own sentence starts.
6. MINOR. Mutant sweep 57, 43 killed, 14 survived. Tests needed: S1 (pulled failed lesson), S3 (a passed waiting lesson given as failed), S10 and S11 (newest 10 cap and order), F3 (add-on fallback to the customer's line). Also E8 (_one_line on fails why), F12 (NO_LETTER_AFTER, "400 EGP moreover").

Ruled out: a failed lesson going live or skipping the Morning page; raw customer text reaching a prompt beyond what the gate stored (small gap: the rerun quote is not a copy-check source of the new try); "on us" and "final" whole-word refusals hold, including look-alike and hidden characters.

Scratch: scratchpad rvgfb1/ (base, head, fixc, scripts/).
