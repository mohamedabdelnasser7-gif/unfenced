# Red team round 1, unfenced-realcards-1101
*Created: 2026-11-01. Last updated: 2026-11-01.*

Red team (Fable 5.1), diff da0cea2..a6b537e. Saved by root; reported until checked. Scripts: scratchpad rt-realcards1/.
1. MEDIUM, CONFIRMED. arena/run.py:544 to 547 unlinks <db>.arena before checking it is not the live file: --db X where X links to X.arena deletes the live db. Fix: resolve both and refuse same file before any unlink.
2. LOW, CONFIRMED. run.py:546 to 552: a link planted at <db>.arena after the unlink makes the copy the live db; the copy is 0644 and stays on disk with every live chat. Fix: os.open O_CREAT|O_EXCL|O_NOFOLLOW 0600 as arena/personas.py:120.
3. LOW, CONFIRMED. tests/real_guard.py:34 to 35 compares path text: case, links, dir_fd, child process, file: URI bypass. Fix: compare dev and inode of the path and its parents; name the rest out of scope.
4. LOW, CONFIRMED. arena/rounds.py:133 to 136: a clash card can name the wrong live lesson by id. Fix: match by text or ids at or below the copy max.
5. LOW, unconfirmed. run.py:414: sqlite3.Error (database locked) from hand_live ends the run in a traceback. Fix: catch it, note it on the round.
Ruled out: links planted before the run, the live path twice, WAL and journal, crash between copy and hand, the same lesson twice, copy tampering, high risk without a yes, real_guard outside tests.
