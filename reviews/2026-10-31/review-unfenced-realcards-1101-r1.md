# Review round 1, unfenced-realcards-1101
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer (Opus, max), diff da0cea2..a6b537e. Saved by root; reported until checked. Suite 2190 OK. Mutants 17 of 30 killed. Files: scratchpad rv-realcards1/.

Verdict FIX FIRST.
1. MEDIUM, CONFIRMED. run.py:541 with engine/study.py:220: the copy is rebuilt from live each run, so item 50 memory of failed lessons is wiped; a lesson refused in run 1 can pass and go live in run 2. Fix: carry failed, untried, waiting lessons and their exam rows from the old copy into the new one.
2. MEDIUM, test gap. rounds.py:139 to 145: hand_live risk and yes branches untested (code correct in probe). Fix: tests for high risk with live Accept off, on, run out, and low risk with trial False.
3. LOW. tests/real_guard.py:25 to 36 path strings (case, /System/Volumes/Data, links, file: URI). Fix: dev and inode of the path and parents.
4. LOW. run.py:826: sqlite3.Error from a locked live db ends the run with no report. Fix: catch it, note not handed, live busy.
5. STALE. docs/judges.md:37 says made-up customers; recorded/arena-run.json is from the made-up set; run.py:731 help says outside the repo.
6. MINOR test gaps: replay.load REAL_REPLAY end to end, a second repo replay.jsonl, RealRead as Exception, side files, pulled and agent checks.
7. MINOR latent: source and clash ids are copy ids in hand_live; cannot run today.
Ruled out: anything but a gate-passed lesson reaching live; the copy being the live file (links, WAL); partial writes; the hook outside tests; samefile bypass except a hard link.
