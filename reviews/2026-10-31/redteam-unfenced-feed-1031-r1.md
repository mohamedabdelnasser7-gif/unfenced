# Red team unfenced-feed-1031, round 1
*Created: 2026-10-31. Last updated: 2026-10-31.*

Target: arena/grow.py (new) and its wiring in arena/run.py, arena/personas.py, reflection/night.py, engine/plug.py (pr.diff, 7 files). Attacks on paper and in a private copy of the pack (arena/real, .env and data folders left out of the copy), python3 -I, fake chats, fake people, fake numbers only. No live system touched, no server started. Proof scripts: scratch/redteam-feed-1031-private/exp_clean.py, exp_clean2.py, exp_gate_owner_tmp.py.

Checklist used: _system/security/redteam/ai-and-agents.md (items 5, 6, 8, 14, 16) and the cross-owner steps of access-control.md. Method: ~/.claude/skills/vibe-check/references/security-method.md.

## Short version
1. CONFIRMED, medium: the cleaner runs with no names for real chats, so a surname off the first-name list survives into the pool, the tagger prompt and card example lines (F1).
2. CONFIRMED, medium: grown cards land in the held-out gate set, so the measured Arena score is taken on cards grown from the agent's own real chats and the gate set moves night to night (F2).
3. CONFIRMED, medium: the owner boundary is inferred from folder layout; a flat layout shares one pool across owners and lists their agents to each other (F3).
4. CONFIRMED, low: Pool.save follows a planted symlink at the .tmp name and makes the owner folder 0755; the repo's own safe writer is not used (F4).
5. CONFIRMED, low: a failing practice step kills the night's report after the lessons went in (F5); poisoned pool values crash the Arena with a traceback (F6).
6. Four more lows (F7 to F10), one unconfirmed (F11), and the cleared list at the end.

## Findings

### F1. Real chats are cleaned with an empty name seed. CONFIRMED, medium
What: the persona build seeds Cleaner with every sender's display name, so a full name is masked wherever it is typed. grow.py seeds nothing: `cleaner = Cleaner()` (grow.py:321) and `cleaner.chat(chat.names)` with `chat.names` always empty, because real_chats builds `hist.Chat(source, key=chat_id, place=0, messages=msgs)` with no names, no phone, no typed_phones (grow.py:297). It reads only `id` from chats (grow.py:281-283), not `customer_id`, and reads `tool_calls` (grow.py:286) but never uses them, though every draft_order call carries the typed `name`, `address` and `phone` (kit/tools/draft_order.py:43-46, 73-76).
How found: code reading, then fake chats through grow's own path (Cleaner() + personas.turns_of) beside a seeded cleaner.
Proof (fake people): a bare reply "[a made up full name]" to "ممكن الاسم؟" came out `[name] [surname]`; the later bare "[surname] معاك تاني، الاوردر اتأخر" stayed whole; the store's "اهلا [a made up full name]" kept the surname. Latin lowercase "karim tawfik mansour" came out `[name] tawfik [name]`; "Tawfik Mansour هيستلم" kept Tawfik. With the same names seeded, every one of those was `[name]`. First names, phones (spaced and plain), the address and names after a cue were masked in both runs. cards.example_ok accepts "[surname] معاك تاني، الاوردر اتأخر" (4 words, no placeholder), so the line is eligible as a card example.
Impact: the surviving word reaches the pool file (owner folder, 0600), the tagger prompt on Baseten (grow.py:342, tag.py:143), the card's example lines (cards.py:106-123), the Arena customer prompt (match.py:130 `$examples`), match transcripts and, on a lost match, the agent's own log as a case (learn.py:44-45), which the night study and the Morning page read. Nightly and automatic, no person in between. The leak class is rare or off-list surnames and names typed without a cue; the common cases held.
Severity after reachability: medium (every real customer, every night; the leaked word is a surname, not a phone or address).
Fix (smallest): in real_chats select `customer_id` too and, per chat, collect the `name`, `address` and `phone` arguments of every draft_order tool call from `tool_calls`; build the Chat with `phone=customer_id`, `names={name...}`, `typed_phones={customer_id, phone...}`; in grow() build `Cleaner(all names of the night)` once and keep `cleaner.chat(chat.names)`. Add a test with a two-word name typed once after a cue and once bare.

### F2. Grown cards enter the gate, and the gate set moves. CONFIRMED, medium
What: run.py puts the pool's cards into `cards` (run.py:661-662, `grow.deck`) before `Arena.__init__` splits them (run.py:285). With no `--held-out`, `split()` holds out a seeded share of every card that can buy (run.py:214-250); lost chats make winnable cards, so `grown-*` cards qualify. The ids and worries present change the seeded draw, so the same seed holds out different cards once the pool grows, and the held-out count grows with the card count.
How found: code reading, then run.split on 5 fake base cards plus 2 fake grown cards.
Proof: seed 0 with no pool held out persona-01 and persona-03; seed 0 with the pool held out persona-03 and grown-size; seed 1 held out grown-price and grown-size (both gate cards grown).
Impact: the gate, the measured Arena score and the pass that lets lessons through (PASSED, run.py:366-367; arena/gate.py reruns), is taken on practice customers grown from the chats the night study already turned into lessons for the same agent, and on a set that changes night to night, so scores are not comparable across days. Anyone who can message the shop shapes those cards (worry, wants, example lines) within 48 hours (F8). Decision "only training losses add weight, gate matches never do" holds for weights; it does not keep grown cards out of the gate.
Severity after reachability: medium.
Fix (smallest): in split(), never hold out a card whose id starts with `grown-` (or that carries `grown`): `winnable = [c for c in cards if can_buy(c) and not c["id"].startswith("grown-")]`, and leave `--held-out` as the explicit override. One line plus a test.

### F3. The owner is whatever folder sits above the agent's; a flat layout shares across owners. CONFIRMED, medium
What: owner_of returns `folder.parent` whenever `folder/plug.json` exists (grow.py:79-82); siblings() globs `*/plug.json` under that parent (grow.py:91-101); check_owner only refuses a folder inside the repo outside data/ (grow.py:104-108). Nothing says who the owner is. Two owners' agents laid out as `<root>/ownera_sales/plug.json` and `<root>/ownerb_sales/plug.json` get one owner (`<root>`), one pool and each other's agent names.
How found: code reading, then two fake agent folders (the repo's sales plug with agent and kind changed) under one scratch parent.
Proof: `owner_of` gave the same parent for both; `for_state` gave the same `practice-sales.json`; `siblings` listed both agents; an item added by A was read back by B's pool.
Impact: cleaned real-chat turns and agent names cross owners when the operator lays agents out flat, which is the natural layout for "several agents on one machine". The same holds for `personas.py --state` naming another owner's folder (personas.py:499-505). Not reachable by a customer; by the operator's layout. DECISIONS item 51 promises "never across owners"; the code cannot tell owners apart.
Severity after reachability: medium.
Fix (smallest): an owner marker. owner_of uses the parent only when it holds an `owner.json` (or the plug names `owner` and the parent's marker matches); otherwise the agent's own folder is the owner and the night says so. siblings() counts a plug only when its owner matches.

### F4. Pool.save writes through a planted link and makes a 0755 folder. CONFIRMED, low
What: save() writes a fixed name `<pool>.tmp` with `write_text` (grow.py:182-183), which follows a symlink, then chmods (grow.py:185) and renames the link over the pool (grow.py:186). `mkdir(parents=True)` makes the owner folder with the default mode (grow.py:181). The repo's own writer does it right: arena/personas.py:114-128 `_write` opens a random temp name with `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600` and makes folders 0700 (personas.py:139, 145).
Proof: a symlink `practice-sales.json.tmp` pointing outside the owner folder: save() returned, the outside file held the pool item, the pool path became a symlink and the next load refused it ("the pool file is a link"), so the pool is also lost. A fresh owner folder came out 0755 under umask 022; the file 0600.
Impact: needs write access inside the owner folder, the same trust the pool itself has, so the reach is small: a sibling process or a mistake, not a stranger.
Severity after reachability: low.
Fix: reuse personas._write (move it to arena/paths.py or a small kit helper) and make the folder 0700.

### F5. A failing practice step kills the night's report. CONFIRMED, low
What: night.py calls `grow.night(...)` bare (reflection/night.py:523-527), after the lessons went into the database and before `save(rep, args.db)`. grow.night catches only hist.Refused and grow.Refused around the recipe and the pool (grow.py:372-377); Calls, the Tagger, the Db, grow(), rebuild() and save() (grow.py:378-392) are unguarded.
Proof: pool.save() on a read-only owner folder raised PermissionError; nothing in grow.night or night.py catches it.
Impact: the night's report, with `rep["snapshot"]` (the rollback command for what the night changed) is never written or printed; the exit is a traceback. Triggers are operational (permissions, disk, a corrupt steps row: `_media` catches ValueError only, grow.py:302-304), not a customer.
Severity after reachability: low.
Fix: wrap the call in night.py in `try/except Exception as e: rep["practice"] = {"kind": ..., "stopped": f"failed: {type(e).__name__}"}` so the report always saves; same inside grow.night around save().

### F6. Poisoned pool values crash the Arena with a traceback. CONFIRMED, low
What: _capped_ok accepts any pattern string up to 20,000 characters (grow.py:208-211) and _Caps compiles it (grow.py:229); _card_ok does not check `chats` (grow.py:203-205) and deck() does `int(c.get("chats") or 1)` (grow.py:252-253); `arena_weight` may be Infinity or NaN. run.main catches Refused, PromptRefused, OSError, ValueError and RecursionError only (run.py:716-718). Pool.__init__ never checks the file's `kind` against the pool's (grow.py:130-140).
Proof: pattern "(" raised re.PatternError and `chats: 1e999` raised OverflowError, both outside the except list; Infinity made every base weight NaN (draw() then falls back to uniform, so the shares and caps are gone); NaN was accepted; a file saying `kind: marketing` loaded as the sales pool.
Impact: needs pool-file write access (same trust as F4).
Severity after reachability: low.
Fix: in _capped_ok try `re.compile` and drop a bad entry; in _card_ok require `chats` a whole number 1 or more and `arena_weight` finite (`math.isfinite`); refuse a file whose `kind` differs.

### F7. Loss weight has no cap. CONFIRMED, low
What: weight is `1 + 3 * losses`, never capped or decayed (grow.py:144-145, 56). After 33 losses one card is drawn 100 times as often as a fresh card on its side; after 100, 301 times. Training narrows to one customer while the sides and caps still hold. The counts also survive a card rebuild under the same id (grown-<worry>), so an old streak follows a new card.
Fix: cap the multiplier (for example at 10) and reset a card's row when the pool is rebuilt and the card's group changed.

### F8. Cheap lost chats fill the pool. CONFIRMED (by design limits), low
What: a chat that asked a price and went quiet 48 hours is lost (label.py:190) and kept. One phone number gives one root chat (kit/chats.py:108-116), so each number is one pool item; 50 join a night (grow.py:58) and the pool keeps the newest 500 (grow.py:59, 134, 166). The grown side's draw share follows its chat count (grow.py:252-258). A wave of price-askers, bots or a competitor with numbers shapes the grown cards' worries, wants and example lines; the caps and the unwinnable share hold, so weights cannot pass them. With F2 fixed this touches training only.
Fix: cap what one night may add to a share of the pool (for example 10 percent) and keep a lost chat only with 2 or more customer messages; a Morning line naming what joined would let a person see a wave.

### F9. seen is trimmed to 5000, so a chat can join twice. CONFIRMED, low
What: `seen` keeps the last 5000 ids (grow.py:60, 135, 180); an older chat that gets a new message is read again and can be added a second time. Fix: keep seen ids with the pool items, or make the item id the chat id and skip a duplicate on add.

### F10. A plug kind the plug accepts, the pool refuses, and the Arena stops. CONFIRMED, low
What: engine/plug.py:66 NAME has no length cap; grow.py:63 KIND allows 41 characters. A longer kind passes the plug, Pool raises Refused (a ValueError) and run.main prints "Not run" for the whole Arena (run.py:716-718); the night reports "stopped". Fix: one regex for both (import KIND into plug.py or give NAME the same cap).

### F11. Eight words of model-written text in the customer prompt. UNCONFIRMED, low
What: `want` and `buy_trigger` are free text the tagger writes after reading the customer's (cleaned) lines, cut to 8 words and 120 characters and cleaned (tag.py:89-99); they become "You want $want" in the Arena customer prompt (match.py:58, 122). A customer could plant a phrase the tagger echoes. Not run against a model here; the bound is tight. Note only; a word list check on wants would close it.

## Notes, not findings
- personas.py `--state` opens the pool in the folder named (personas.py:502, `grow.Pool(args.state, ...)`) while run.py walks up to the owner (`grow.for_state`, run.py:661); the same path means two different pools when the folder holds a plug.json. One line: use `grow.for_state(args.state).items`.
- real_chats reads every step of the chat before `until` with no lower bound (grow.py:286-287) and one phone number is one root chat forever, so a long customer's whole history is tagged once (8000 characters head and tail) and never read again.
- The Arena (run.py:715-716) and the night both save the pool with no lock; two processes on one day can drop each other's rows. The decision covers nights only.

## Cleared (RULED OUT)
- Path or link tricks through kind or chat content: KIND regex (grow.py:63, 118) and plug NAME (engine/plug.py:66, 241) allow no slash or dot; chat ids are uuids; the pool file name comes from kind only. The defenders' AcrossOwners tests cover `../sales`, `sales/x`, a pool path in another folder and a symlinked pool file (tests/test_arena_grow.py:256-282).
- Links followed: the cleaner masks links to `[link]` (clean.py:153); nothing in grow, tag or cards fetches; example_ok rejects any placeholder (cards.py:99).
- Weights past the caps through losses: deck() re-holds each side's share and runs cap_wants after the loss weights (grow.py:259-267); the defenders' CapsHeld tests cover it (reported, not rerun).
- Gate or replay matches adding weight: record() runs in the training loop only (run.py:352-353), not the gate (run.py:355-365) or replay (run.py:376-398).
- Tool calls or tool results in the pool or the prompt: only user text and non-empty assistant text become turns (grow.py:290-296); style_of returns numbers only (cards.py:58-70).
- SQL: parametrised throughout real_chats (grow.py:281-287).
- Tagger instructions from chat text: the chat travels as a JSON data message under the recipe's system prompt (tag.py:140-145); worry is a closed set, patience and no_budget typed (tag.py:77-92).
- Arabic worry names collapsing every grown id to `grown-other`: recipe names are ASCII lowercase letters and spaces (recipe.py:41, 99), so grown_id (grow.py:214-217) stays distinct; winnable and unwinnable ids never collide (an unwinnable worry has no winnable card; no budget gets its own suffix).
- Secrets: no key printed anywhere on this path; tagger errors carry type names only (tag.py:146-149); the night refuses before running without keys.
- Live reach: no server, no live probe, no account touched; the pack's arena/real, .env and data folders were never opened.

## Order of fixes
F1 and F2 first (both small, both nightly and customer-reachable), then F3 (design, owner marker), then F4 to F6 together (one safe writer, a guarded night step, three value checks). F7 to F10 as a cleanup commit.
