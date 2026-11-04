# Red team, wireall round 1
*Created: 2026-11-02. Last updated: 2026-11-02.*

Target: branch wireall (85bf10f..a92230e), paper attacks only, read only. Spec: DECISIONS items 59 and 51. Checklist: _system/security/redteam/ai-and-agents.md items 5, 6, 9, 14 and 15, plus access-control for the owner boundary. No model call, no network, nothing written in the repo or worktree; arena/real contents and private-data not opened.

## Verdict
No critical or high. Three low findings in code, two low design notes, the five attack lines otherwise ruled out. Nothing here blocks the merge.

## Findings

### 1. practice --cards takes any folder, no owner check (low, CONFIRMED by reading)
Where: arena/practice.py:286-287 (`run.load_cards(args.cards)`), against arena/grow.py:198, which refuses a pool outside the owner folder.
Attack: `arena/practice.py --agent <owner A>/agents/x --cards <owner B>/real-cards` (or the repo's own arena/real/cards). The whole real cards, want, examples and all, play against A's agent and land in A's arena-matches.jsonl as `persona` and in the Morning item's quotes.
Reach: the operator's own shell, so a mistake, not a remote attack. Item 51 says never across owners; the pool enforces it, this flag does not.
Fix: refuse a --cards folder that is not inside `grow.owner_of(folder)` (paths.within), as Pool does, and refuse any folder inside the repo.

### 2. A built agent whose exam binding fails runs the night with no gate (low, CONFIRMED by reading)
Where: reflection/turn_exam.py:318 and :322 return None when `turn_mod.load(where)` is refused or the exam path is off; reflection/night.py:237-239 then sets no examiner and the engine starts trials untested.
Attack: push one never line in card.json past 600 characters, or point plug.json's exam at a subfolder. plug_mod.load still succeeds, so `night.main --plug agents/x/plug.json` runs; the report says exam None and every new lesson goes to trial with no exam.
Reach: a hand edit on the owner's disk, and built agents have no live sends yet, so the damage is lessons that practice hands untested. Fail open, where the Morning page in the same case fails closed (NO_EXAM).
Fix: when plug.exam is set but no binding can be made, return an examiner that always answers `exam.could_not_run(why)`, so every lesson is held with the reason; have night.main refuse a built plug whose folder does not load.

### 3. Deeply nested JSON in an agent folder crashes instead of being left out (low, CONFIRMED by reading)
Where: arena/madeup.py:276 catches OSError, ValueError and UnicodeDecodeError only; kit/turn.py:182 and :221 (Refused only); arena/run.py:749 (ValueError only).
Attack: a persona-01.json of 100 KB that is `[[[[...]]]]` twenty thousand deep passes the size check; json.loads raises RecursionError, which none of these catch. In real-cards it kills the practice run; the same shape as plug.json kills `built()`, so live_morning and the Sales night's other_plugs stop at start.
Reach: write access to the db folder. Denial of the page or the night, no data exposure.
Fix: add RecursionError to those except tuples.

### 4. Design notes (low, UNCONFIRMED, his call)
a. Built agents now feed and draw from the Sales night's cross agent read. reflection/night.py:200-207 adds built plugs to `others`; engine/study.py:528-531 then reads their cases and lessons as candidates for Sales, and Sales's for them. A line typed as a correction on a toy agent's page can be proposed to Sales. The fit check, adapter, Sales exam and trial stand in front, so this is a door, not a hole. Item 59 says every door like Sales; worth one yes from Mohamed that the night's read is meant too.
b. real-cards/ carries no owner mark (arena/madeup.py:262-282). The folder is trusted because owner.json and the plug agree; if owner.json is later pointed at a new owner and the folder is not replaced, the new owner's agents blend the old owner's behaviour. Fix: write {"owner": name} beside the cards and compare it with the marker.

## Ruled out, with what was checked
1. Real text into prompts, cards, exam, logs or pages. behaviour() (arena/madeup.py:237-259) reads only the named fields; worry and why come from the recipe's fixed worry list (arena/tag.py:86, arena/cards.py:128) and pass _label (madeup.py:231: four plain lowercase words, else "other"; casefold then an ASCII only match, so Arabic, digits, bidi marks and labels that smuggle words all read "other"). Numbers as strings, bools, NaN and infinities read as 0 or drop the card; opening keeps the three behaviour keys only; a card over 100 KB is skipped before it is read. The model ask holds labels, numbers and the new agent's own card (test_blend checks every real line against it). Saved cards carry `behaviour_from` ids and a hash. practice.text prints a count.
2. Cross owner. The owner folder is the parent only when owner.json and plug.owner agree (arena/grow.py:143-148); check_owner keeps it out of the repo; the real-cards folder and each card are refused as links; `real-cards` can never be an agent name (AGENT_NAME has no hyphen); built() refuses a linked agents/ folder; Build strips model written owner, kind and exam (reflection/quickstart.py:350); slug and _write_folder keep the folder under agents/; repo names are refused on the live page (quickstart.py:470); a built agent named like a repo agent is left out of the page and the night; the hand over target (marketing) is read before any built plug.
3. Gate and exam bypass. An exam file needs a non empty list (engine/exam.py:149) and sit passes only when rows equal situations; the checks list cannot be empty and an unknown name fails every situation (engine/plug.py:298, exam.py:194). A model error or the six call cap raises out of answer and fails the situation; an unreadable judge raises inside the check and fails it; a rerun stopped by the cap, VOID or a judge fault adds a NOT_RUN row and `n_arena == len(reruns)` holds the lesson (arena/gate.py:160-161). An examiner that raises is could_not_run on the page and held in the night (Counted). A planted arena-matches.jsonl can hold lessons or spend capped calls, never pass one, since the exam runs first. A missing wins file is nothing to rerun. A planted prompt_file is read only when its hash matches and its text goes nowhere.
4. Pause. turn() reads the switch after saving the message and before any model call or tool (kit/turn.py:258). Practice and the exam run in memory, so no switch reaches them, by design. No code outside practice and the exam calls turn(), so no built agent sends live yet. Note for the first live driver: the switch is read from `chats.db` and the page writes `self.db` (morning.py:685); they must be one database.
5. Quick start card text. slug strips path parts; situations are shaped in code (part, tool from the plug's list, never index checked, control and bidi characters stripped, 300 characters, 12 at most); the exam ask carries name, does, good, never and the tools only; `$` in card text cannot re template the customer prompt (safe_substitute once, _safe strips `$`). An empty never list gives an exam with no never check; that is the owner weakening their own gate.
