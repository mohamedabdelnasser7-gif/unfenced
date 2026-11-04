# Review round 2, unfenced-realcards-1101
*Created: 2026-11-01. Last updated: 2026-11-01.*

[Reviewer] Opus, max. Scope: the fix diff ccca5e5..b2cb546 (802 lines) plus what it calls and what calls it: arena/run.py arena_copy, _failed_untried, _carry, main; arena/rounds.py hand_live, _live_id, Between._gate; engine/study.py item 50 readers; tests/real_guard.py. Brief carried only the fix diff and the round 1 findings. Files checked: 9. Everything ran on the pack copy. I added a fake arena/real stub there (2 empty persona cards, an empty replay.jsonl and summary.json) so that test_no_real_reads and test_arena_replay pass at baseline. The repo's arena/real was never opened.

Verdict: PASS. No blocking or medium finding is left. Three new LOW findings and some test gaps are small fixes the session can make.

## Round 1 items
1. Reviewer 1 and red team: item 50 carry. FIXED. The no-carry mutant is killed, and the round 1 probe p1 now shows run 2 proposing 0 and passing 0. Duplicates are skipped and the exam rows are carried. A locked or non-database old copy: see new findings 1 and 2.
2. Reviewer 2: hand_live risk and yes paths. FIXED. All four mutants (trial for an untried lesson, high risk without Accept, Accept past its expiry, low risk never starting) are killed by the HandLive tests.
3. Reviewer 3 and red team 3: real_guard dev and inode. PARTLY. Every round 1 spelling is now blocked (p2 probe and the red team guard probe). One new bypass: see new finding 3.
4. Reviewer 4 and red team 5: busy live database. FIXED. Mutants on the except, the note and live_id are killed. A wording issue: see new finding 4.
5. Reviewer 5: stale judges.md:37 and the --replay help. FIXED. A grep finds no other stale wording.
6. Reviewer 6: minor test gaps. FIXED. The replay tests now cover the cleaned set end to end and a second replay file in the repo. Side files are tested, and the mutants that hand a pulled lesson or another agent's lesson are killed.
7. Reviewer 7 and red team 4: copy ids. FIXED. Putting back the round 1 code for clashes and for the source is killed.
8. Red team 1: the copy name is the live file. FIXED. All 3 mutants are killed, and the p3 scenarios refuse.
9. Red team 2: O_EXCL, O_NOFOLLOW and 0600. FIXED. Putting back the whole fix is killed. Each layer on its own survives because another layer catches the same case (see Mutants).

## New findings
1. LOW, CONFIRMED. arena/run.py:583 to 584 and 637 to 640. Nothing stops two Arena runs on the same --db at once, and the docstring promises a refusal that cannot happen. The copy is in WAL mode (kit/db.py:25), and WAL readers never block. So _failed_untried reads the other run's open copy, and arena_copy then unlinks it. Probe tools/probes.py p1 (a RESERVED lock) and tools/p_excl.py (an EXCLUSIVE lock): neither is refused. Run A's writes land in a file that no longer has a name, its failed lines are lost to the carry, and both runs can hand the same words live. hand_live has no check by words, so the probe made 2 live rows from one lesson.
   Fix: hold an flock on <db>.arena.lock for the whole run and refuse a second run. Optionally, skip in hand_live when live already holds a lesson of that agent with the same words that is not pulled.
2. LOW, CONFIRMED. arena/run.py:637 to 646. The old copy is unlinked before the new copy is built. When the backup then fails (live unreadable as a database, as in probe p2), the old copy's failed lines are gone and a 0 byte copy is left behind. The next good run carries nothing, which brings back round 1 finding 1 for that case. The R1 no-live mutant survives for the same reason.
   Fix: build the new copy under a temp name with O_EXCL, carry into it, and os.replace it over the old copy only when that succeeds. Add a test with a broken live file.
3. LOW, CONFIRMED (test-only guard). tests/real_guard.py:63. abspath collapses ".." as text. With a link L pointing to arena/real/cards, the path L/../replay.jsonl opens the real file, but under_real returns False for it and for its file: form (tools/p_guard.py). The docstring does not list this as out of scope.
   Fix: use os.path.realpath in place of abspath before the text check and the walk, and add that path to the test.
4. MINOR. arena/rounds.py:270 catches every sqlite3.Error and labels it "live busy". That includes errors from the copy side and schema or integrity errors. arena/run.py:775 prints only the first 3 notes and the study's notes come first, so the busy note can drop out of the text report, while the lesson line at :771 still says "handed on".
   Fix: catch OperationalError for busy, and put the live status on the lesson line.

## Mutants
58 in total, run one at a time with a 30 s cap: 29 killed and 29 survived. Of the survivors, 16 are equivalent and 13 are test gaps.

Equivalent (16), with the reason:
- R2: 8 single layers (EXCL, NOFOLLOW, both, the open mode, fchmod, the islink check, the replaced check, the copy-is-live check) and the post-check pair. Another layer catches each one, and the post checks fire only in a race.
- C3 and C6 (the trial and yes filters). A failed lesson with a trial or a yes needs a person; the Arena gives neither, and lessons that came from live are skipped by the words check.
- H4. The copy's trigger forbids a source from the same agent.
- H6. The study never writes a line that is already a lesson.
- G6, G7, G8. The parent walk already covers these.

Test gaps (13):
- R1: the no-live refusal.
- C5: the passed filter. It is hidden because GOOD went on trial.
- C7: the locked branch. It is unreachable under WAL (finding 1).
- C9: the tables check.
- C10 and C11: the dedup, and the dedup by agent. No test has a failed line that live also holds.
- C13: source_lesson_id. The test lesson has no source, so the assertion checks nothing.
- C14: the order of the carried lessons.
- H1, H2, H3: the order in _live_id. No test has a pulled lesson and a standing one with the same words.
- G4: the file://host form.
- G5: unquote. The test's "%20" path has no space in it.

Files: spec.json, spec2.json, sweep1.txt, sweep2.txt and tools/ in the same folder. No server or watcher was started, and the worktree is unchanged.
