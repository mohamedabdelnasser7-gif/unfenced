# Review crossowner round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at max, risky tier, 5d6e6d9..e68d121 against DECISIONS 83 (with 24, 51, 62, 63, 79). Filed by root from the hand-back. Suite 3180 OK; mutants 57 of 64 killed. Probes: scratchpad rv-crossowner1/probes (p1_clean.py, p2_threshold.py, mut.py).

Verdict: FIX FIRST

1. BLOCKING, arena/practice.py:452. Built agents practise through Practice, which calls run.Arena with no pool (run.py:385); only the Sales Arena (run.py:965) plays shared lost patterns. Fix: give Practice grow.for_state(folder, kind, shared_root=root_for(db)); test through practice.
2. BLOCKING, reflection/shared.py:112-115, 138. 25 probe lines pass the clean check: number words with no currency (fifty off, five k, bucks, Arabic and Franco forms, glued forms), shop names at sentence start or lowercase, places missing from the list, a phone in digit words, platform handles. Fix: refuse every number word in English, Arabic and Franco including glued forms; refuse Arabic script (the prompt asks for English); one sentence starting with a listed opener; refuse digit word runs and platform words.
3. DRIFT, shared.py:241, 399. Owner taken from plug.owner without owner.json, and the key hash includes the owner name, so renaming counts one owner twice. Fix: owner from grow.owner_name(owner_of(folder)) only; hash the key without the owner.
4. DRIFT, shared.py:164-181. Order and negation words count as small words, so opposite lessons join. Fix: keep them as content words.
5. DRIFT, quickstart.py:947. A stock install has one owner and one pool, so 2 owners never happen and "learned from N owners" never shows. Root call needed for the demo.
6. MINOR, engine/study.py:714. A pooled lesson pulled, brought back and kept, edited or copied by a sibling loses its pool source and is given back (owners 2 to 3). Fix: carry the pattern id through.
7. MINOR, reflection/night.py:676. The study's Writer is not on the day's cap; a failing writer is asked up to 5 times each run. Fix: wrap in Calls as grow.night does.
8. MINOR, shared.py:461. practice_cards has no but=owner, so an owner's Arena gets back its own patterns (tests/test_shared_arena.py:98 pins it, against the accepted call).
9. MINOR, shared.py:72, 248. MAX_FILE 5 MB is under the real maximum; an oversize or unreadable file reads empty and the next add() wipes the pool. Fix: refuse to write when the read failed.
10. MINOR, tests: mutants N01, T10, S31, T04, S37, S20, S25 survived; one test each.

Ruled out: raw owner ids stored; pooled lessons skipping the gate; shared cards in the go-live gate; real practice customers crossing owners; grow writer off the cap.
