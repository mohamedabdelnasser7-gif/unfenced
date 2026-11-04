# Red team round 2, unfenced-marketing-1031 and unfenced-assistant2-1031
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team (Fable 5.1), fix diffs. Saved by root. Scripts: scratchpad rt-mkas2/.

## Marketing
1. BLOCKING, medium. The overlap trigger (handover.py:78 to 82) with the sliding window (night.py:203, default_days 117 to 121) refuses almost every later note on daily runs: 1 of 5 stored. FIXED by root in 7c2a1e8: one note per Cairo night (night_of, noon to noon, UNIQUE), and no note again on cases already handed over. 2100 OK.
Ruled out: NaN, inf or reversed windows (run() forces until > since, wall clock); PartError holding every line (fail closed).

## Assistant (not reachable: keep_finished has no caller)
2. Medium. Names outside structured fields leak (Bahaa, بهاء شلبي, a signature without a sign-off: CEO, Northwind). Sent to the assistant round 2 builder.
3. Medium. arena/clean.py:214 to 217 FLOOR is quadratic on digit runs (20000 digits 4 s). Sent to the feed builder (owns clean.py): \d{1,3}.
Ruled out: nested and odd-key PII (allow-list), digits by dates, link and hard-link attacks on the files, deep or huge lines.
