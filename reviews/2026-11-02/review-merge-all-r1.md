# Review merge-all round 1 (reviewer, max)
*Created: 2026-11-02. Last updated: 2026-11-02.*

Branch merge-all 44c3bc1..f52819d. Verdict FAIL: 1 blocker, 1 high, 3 medium, 3 low. Suite 2849 OK. Round 2 fixes of branch late (16def32, 8323a67, 77c9a81) hold, each pinned by a test that fails on revert. Sweep 34 mutants, 28 killed. Probes in the session scratchpad review-merge-all/rv1.

1. BLOCKER kit/turn.py:241-242, :88. A customer facing built agent whose card connects orders or delivery but not whatsapp or store loses the amount, link and script checks. Fix: add orders and delivery to FULL_CHECK_TOOLS, a test per tool. Status: fixed in beec697 (branch examdays), also red team low 1.
2. HIGH arena/run.py:409-411. The run's quick note is handed to every match, gate and replay too, so the trust gate can pass on a note the live agent never gets. Fix: training loop only; test that gate and replay carry none.
3. MEDIUM reflection/quickstart.py:248. The tag exemption reopens hand overs ("Tag the chat urgent and the owner will take over"), against decision 72. Fix: a tag clause skips only verbs that act on the tag; take over, answer, reply, respond, continue stay refused.
4. MEDIUM arena/rounds.py:85-87, :150-151. A correction already live as a hotfix when the run starts is never handed; only ones added after the start are. Fix: drop the added_at filter.
5. MEDIUM reflection/quickstart.py:615 with arena/match.py:175-186. Build's background practice runs demo_store in a thread; demo_store changes the process environment and logging, so an overlap with a correction round can leave the page process without Shopify keys and with logging off. Fix: one process lock around demo_store, or a child process.
6. LOW arena/learn_built.py:82-86. Closing a lost case on a bad result with after set is right for the study, but adds one made up action to read counts; no test covers that branch. Fix: a test.
7. LOW reflection/scheduler.py:199-210. A manual night with --limit and stdin from /dev/null kills itself at once. Fix: watch stdin only when it is a pipe.
8. LOW arena/learn_built.py:176. Past 10 MB the night reads no practice and does not say so. Fix: name the cap in the report.

Held: practice rows never count live (trials, fast notes, results, the Morning live list skip history rows); cross branch seams clean; the live db is read only from a run; rewrite bound and cap pinned.
