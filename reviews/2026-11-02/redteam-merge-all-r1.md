# Red team, round 1: branch merge-all (unfenced), diff 44c3bc1..f52819d
*Created: 2026-11-02.* Paper attacks on the read-only worktree, no live probes, no servers started.
Test script: scratch/review-merge-all/rt_person.py (python3 -I).
Paths are under wt-merge/.

## 1. Courier webhook and late result routes

1.1 Forged webhook. RULED OUT. channels/bosta.py:350 compares X-Bosta-Secret in constant time before any body byte; :357 body cap 64K; :366 JSON only; read_event :146-158 types every field. Without BOSTA_WEBHOOK_SECRET nothing lands.

1.2 Replayed webhook. RULED OUT. bosta.py:245-251 one key per delivery and result in bosta_seen, a 46 once per order in bosta_orders (:266-281, one transaction); results.py:116-123 writes the late result in one INSERT ... WHERE NOT EXISTS, so two writers still save one.

1.3 Attempt notes with the secret. LOW, UNCONFIRMED (needs the secret). bosta.py:246-247 puts the sender's own timeStamp in the dedupe key, so each new stamp on the same failed attempt sends one more WhatsApp line to OPERATOR_WHATSAPP (:292-300) and adds a bosta_seen row. Steps: hold the secret, POST state 47 code 3 for a real order with stamp 1, 2, 3... Fix: key an attempt by delivery, code and numberOfAttempts only, or at most N notes per order a day.

1.4 Guessed or reused c- reference. RULED OUT. reflection/late.py:93 HMAC of agent and case id under a random key kept in the database (:69-77); morning.py:1153-1160 accepts a reference only when it maps to exactly one case of that agent waiting now; the POST needs the page token anyway.

1.5 Sheet marks another agent's cases. RULED OUT. morning.py:1179 and :1202 resolve every row against that one agent's waiting cases; references are per agent (late.py:93).

1.6 Sheet size and parsing. RULED OUT. morning.py:2848 Content-Length under 64K checked before the read; sheet_fields :2746-2753 at most four parts, each once, no nested multipart; late_sheet :1183-1201 UTF-8, NUL check, at most 200 rows, nothing saved until the whole sheet passes.

1.7 CSRF on /late_mark and /late_sheet. RULED OUT. morning.py:2794-2797 Host and Origin must equal 127.0.0.1 or localhost with the server's port (exact set match, no prefix trick); :2861-2862 token compared with compare_digest; the back field passes pages.py:118-123 (_BACK regex, no scheme or netloc).

1.8 Order reference collision. LOW, UNCONFIRMED (no live rows for built agents today). late.py:89-92 takes detail.order from any row of the case as the reference, and norm_ref :96-102 accepts "c-..." as an order; a tool or model written order equal to another case's reference, or to a Sales order number, makes both unmarkable on the page ("names more than one case", morning.py:1142) and bosta.py:206-228 answers 404 for the real order. Fix: norm_ref refuses an order that starts with "c-"; case_for_order prefers the Sales match when the other agent's row is not tool written.

## 2. The night child process

2.1 Server killed mid night. RULED OUT, the guard holds. scheduler.py:170-171 pipe on stdin and a new session; :199-210 the watcher kills the group at EOF; :194-195 SIGALRM at the limit; the parent kills at the same limit :173-176. No other code sets signal.alarm (grep), so nothing cancels the child's alarm.

2.2 Stuck child. RULED OUT. child.wait(timeout) then killpg SIGKILL and wait :226-233.

2.3 Lock and record after a restart mid night. LOW, CONFIRMED (robustness, not security). The dead server's row stays RUNNING and its lock stays held; the next server reads locked for up to STALE 6h (:71, :324-330), then _stop_stale :319-322 marks the row STOPPED and _had :305-307 counts it, so that agent's night for that date never runs. Fix: _had ignores STOPPED rows, and STALE drops to LIMIT plus a few minutes.

2.4 Log file. LOW, CONFIRMED. _output :217-223 opens nights.log without O_NOFOLLOW and is_file follows links, so a link planted next to the database sends the child's output (it names cases) into any file the user can write. Fix: refuse when path.is_symlink() and add os.O_NOFOLLOW. Rotation runs only at child start (:219), so one 5h child can write past 5 MB: a note, not a finding.

## 3. Quick start Build (model output as attacker)

3.1 Practice without caps. RULED OUT. arena/practice.py:391 Calls with the day cap and QUICK_CALLS 40 set in code; quickstart.py:634 quick=True; kit/turn.py MAX_TOOL_STEPS and MAX_CALLS_PER_STEP are constants. Nothing the model writes reaches them.

3.2 Writes outside the agent folder. RULED OUT. quickstart.py:326-334 slug, :761-770 agents dir not a link and resolves in place, :781-796 hidden tmp folder then rename with a parent check; practice.py:382-387 refuses a folder inside the repo.

3.3 A tool to get past the send check. LOW, CONFIRMED (practice and exam only today). kit/turn.py:239-242 runs the full check only when card.json tools has whatsapp or store; those tools come from the model's needs[].tool (quickstart.py:356-361, :400-401). A card that connects orders and delivery only gets draft_order, find_order and the delivery fee tool (turn.py:202-213) under the house style check alone, so a reply may state any total, fee or link. Not reachable live: channels/ never imports kit.turn, so built agents run in the Arena and the exam only. Fix: talks = bool(connected & {whatsapp, store, orders, delivery}), or the full check whenever any tools.AMOUNT_TOOLS file is offered.

3.4 A declared action to get past the check. RULED OUT. turn.py:402-412 records the action and nothing else; the reply still passes _check :351; acts exclude reply :243.

3.5 names_a_person bypass. LOW, CONFIRMED. quickstart.py:238-253 is a regex list checked on the card, the plug JSON (:437) and the instructions (:714). Seven of nine hand over phrasings pass (rt_person.py): "Loop in a human when the ticket needs a decision, and let them finish the conversation", "Ask the shop owner to take it from here with the customer", "Our sales lead will jump on the call with you", "Share the thread with Mohamed so he can wrap it up with the client", "The supervisor wraps up the chat personally", and the Arabic "هخلي زميلي يتابع معاك الطلب", "هسيب الموضوع لمدير الفرع يكلمك". Caught: "Transfer the chat to a human", "Let a colleague continue the conversation". Impact: a built agent's prompt can promise a person takes over (DECISIONS 53); no hand over tool exists for built agents (turn.py doc line 38), so the harm is a false promise in practice, not a transfer. Fix: keep the regex as the fast path and ask the risk judge one question on Build ("does this hand a chat or a case to a person?"), or list it in docs/known-limits.md.

## 4. Practice cases in the engine log

4.1 A practice row counts as live. RULED OUT. arena/learn_built.py:106 marks every row arena, history and practice; excluded by engine/trial.py:263, engine/fast.py:229, morning.py:1249 (_live), results.py:107 (no late result), late.py:56 (never on the late list), bosta.py:223 (never matched by the webhook).

4.2 arena-matches.jsonl read by the night. RULED OUT, one note. learn_built.py:176 refuses a link and anything over 10 MB; :187-191 needs this agent's name, a bool won, a turns list and a training id (fullmatch); :95 skips a case already written; :68 keeps only declared actions. Note: card (:105) goes into source unchecked up to the file cap. Fix: str(card)[:64] with a fullmatch on the card id form.

4.3 Forged match id. RULED OUT. Must match \d{8}T\d{6}-r\d+-t\d+; a forged id equal to a later real one only makes the real match skip, and that attacker already owns the file.

## 5. Hotfix pick-up in an Arena run

5.1 A run writes to the live db. RULED OUT. arena/rounds.py:81 opens mode=ro by URI (as_uri quotes ? and #), timeout 1; ids come back negative :93 so they never match a lesson of the copy.

5.2 A pulled correction still handed. LOW, by design. rounds.py:117-121 keeps the last list while the live database is busy, a pulled one included, until the next good read. Fix: drop self.fixes after three busy refreshes in a row.

## Cleared
Forged and replayed webhooks, c- reference guessing, cross agent sheets, sheet size and multipart parsing, CSRF on both POSTs, server death and stuck child, practice caps, folder escapes, action based check bypass, practice rows in trials, fast notes, the live list, late results and the webhook, forged match ids, live db writes from a run.

## Verdict
PASS. No high or critical. Four low findings confirmed (2.3, 2.4, 3.3, 3.5), three low notes (1.3, 1.8, 5.2, 4.2 note). None reaches a customer or money today: built agents are not dispatched live in this diff.
