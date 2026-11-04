# Review of four old branches, round 1
*Created: 2026-11-04. Last updated: 2026-11-04.*

Reviewer at high on the own commits of scopeguard, connstatus, buyers and run4, with merge previews against levels and crossowner and DECISIONS 53, 72, 84, 85. Filed by root from the hand-back; root confirmed run4 with git cherry.

- run4: DROP. The same change is already on anyagent (90c02fc); git cherry marks it identical.
- buyers: DROP. With won only, lost chats are never tagged so the replay plays nothing; grown items skip the won filter; nothing calls the flag; buyer only cards soften the gate and go against the customer mix of decision 85.
- scopeguard: MERGE AFTER FIX. Nothing else does this. Conflicts with levels and crossowner in good.py, practice.py, run.py, quickstart.py; must use levels' pick(); a choice is needed between replacing practice match 10 and adding an 11th. The same off topic asks go to every kind, so a restaurant or tutoring agent would be taught to refuse its own work: skip any ask whose words appear in the card. Minor Arabic prefix false match. Off topic cards stay training only.
- connstatus: MERGE PART at most. Notes are saved but never shown on any page; it overlaps the tag action (decision 72) and handover notes with a weaker guard (no phone, name or number filter, customer text can steer it); its wording invites a hand over to a person (53, 72). The status helpers have no caller outside tests.

Merge order: main, anyagent, crossowner, levels, then scopeguard rebuilt on levels after its fixes; connstatus only if it is wired and guarded.
