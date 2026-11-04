# Red team round 2, unfenced-realcards-1101
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team (Fable 5.1), worktree wt-realcards head b2cb546, against fix.diff. Paper plus throwaway
harness on temp databases only (scratchpad rv-realcards2/harness.py, harness2.py); no live data, no
models. Nothing left running.

## Round 1 holes, rerun with variants

1. CLOSED (was MEDIUM). `--db X` that links to `X.arena` now refused before any unlink: arena/run.py:629
to 636 resolves live and its side files to (dev, ino) and refuses any copy name that resolves into that
set. Proven: symlink `--db`, a hard link copy to live, and a copy side file hard linked to live all
raise Refused with the live file untouched.

2. CLOSED (was LOW). Link planted at the copy name between the unlink (run.py:638 to 640) and the open:
the copy is made O_CREAT|O_EXCL|O_NOFOLLOW mode 0600 (run.py:642), then its fd inode is re checked
against the name (run.py:651 to 654). Proven: a symlink and a hard link both planted at that moment are
refused, live kept; the copy is a real 0600 file and a dangling link is replaced, never followed.

3. CLOSED, scope limited (was LOW). tests/real_guard.py now matches arena/real by (dev, ino) walking
parents (real_guard.py:66 to 75) and reads a `file:` URI as its path (_plain, real_guard.py:42). No
bypass found within scope: `file://host/path` folds to a path sqlite itself rejects, percent escapes
are unquoted on both sides, parents are matched by inode. The three documented out of scope items
(child process, dir_fd, a new os.link or os.symlink name) are unchanged and still out of scope.

4. CLOSED (was LOW). Clash and source now match the live lesson by (agent, words) via _live_id
(rounds.py:104, used at 126 to 132 and 150 to 154), not by a copy id. Inserts are parameterized and a
self clash is guarded. Residual is cosmetic only: with duplicate same text live lessons it picks the
newest not pulled one.

5. CLOSED (was LOW, unconfirmed). hand_live is wrapped in `except sqlite3.Error` in Between._gate, which
notes LIVE_BUSY and lets the run and report go on; kit/db.py tx re-raises the raw sqlite3 error and the
live open sits inside the same try, so a locked live is caught, not a traceback.

## What the fixes added

6. Carry cannot reach live: RULED OUT (live injection). A crafted old copy that plants a failed waiting
untried lesson is carried into the new copy (run.py:553, 589), but only with passed=0 (the select at
run.py:573 keeps e.passed=0), it is never in the study's rep["cards"], and hand_live refuses passed=0
(rounds.py:135). Proven: the crafted lesson lands in the new copy as waiting passed=0, and a direct
hand_live call raises ValueError with nothing written to the live database.

7. NEW, LOW, UNCONFIRMED (residual race). Between the fd inode re check (run.py:651) and the two by name
reopens, sqlite3.connect(str(copy)) at run.py:655 and _carry's Db(str(copy)) at run.py:662, the copy
name is resolved again. An attacker with write access to the live database's directory and a crafted
old copy who wins this very narrow race could have _carry write the carried rows into the live database
through a swapped name, planting a high risk waiting lesson a person might later approve. Not proven
(the window is well under a millisecond and O_EXCL plus the :651 check keep it narrow). Fix: do the
backup and carry on the verified descriptor (connect through /dev/fd/N, or reuse the one verified
connection for _carry) instead of reopening by name, or re-verify _file_id(copy) == made just before
_carry. Not blocking.

8. NEW, LOW, by design (availability). An attacker who can write the database's directory can stop every
Arena run two ways, both failing closed with exit 2 (caught at run.py:932), no data loss: hold the old
copy under a write lock so _failed_untried refuses (run.py:583 to 584), or link a live side file to the
copy so arena_copy refuses (run.py:635 to 636; proven for a live `-wal` symlink to the stale copy). Safe
direction; worth a note. Not blocking.

9. NEW, LOW, by design (integrity of learning). The same write access lets an attacker seed failed
waiting lessons for chosen good texts; a re proposal close to a failed line then waits for a person's
yes rather than auto passing, so those good lessons stay out of live until a human acts. Cannot inject
a passing lesson. More restrictive only. Not blocking.

## Verdict
All five round 1 holes CLOSED. Carry to live RULED OUT. Three new LOW residuals (one unconfirmed race,
two fail closed by design), none blocking. Shippable.
