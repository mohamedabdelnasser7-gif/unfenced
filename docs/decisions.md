# Decisions
*Created: 2026-11-04. Last updated: 2026-11-04.*

This is the public copy of the decisions log we kept during the hackathon, 30 October to 4 November 2026. Every decision keeps its number. The owner made each call; quotes are short and give his words in plain English. When a later decision changed an earlier one, the earlier line says so ("replaced by N" when the whole line moved on, "amended by N" when part of it did). Private details are left out: the persona recipe, trust levels we keep private, file paths outside this repo, account details and any customer data.

How the story played out in code is in [journey.md](journey.md).

## Product

1. Unfenced is an engine that builds and teaches AI agents for any industry and keeps improving them from their own mistakes. Mistakes are material to learn from. ("Build any agent for any industry that improves over time.") 2026-10-30.

2. The product is not business operations: no courier work and no store operations as the product. 2026-10-30.

3. Project name: **Unfenced**, the owner's word, 2026-10-30. A web search puts the word near "uncensored AI" apps; the pitch answers it: unfenced in the Arena, gated before going live. A lawyer checks the trademark before it is registered.

20. The seed always starts from zero. The user says what agent they want and adds what it needs to know (a sales agent, for example, gets the brand identity file). No lessons are mined from old chats before the Arena; every lesson is earned there. Real data is used only for the opponents (personas, opening messages) and the replay. ("It should always start from zero." The brand file is an example for a sales agent, since not every user will have one.) 2026-10-30.

21. Arena data: a persona card holds what a group of real customers have in common (want, worry, patience, style, how they open). There is no separate opening message step. The replay of real lost chats stays. Replay chats are labelled won or lost from the chat itself (an address sent or an order confirmed is won; going quiet after the price is lost). Unclear chats are skipped, never guessed, and no order records are joined, since that would need names or phones. 2026-10-30.

22. The Sales agent sells boots and a UV DTF printing service that prints on the boots. Printing chats count as sales chats. Chats about other products of the real shop are kept out of the repo. 2026-10-30. Later on 31 October the store kept the Beyond the Limits name but took the real shop's products, prices, colours and sizes, with the printing service writing the customer's name on the boot. Amended by 39.

24. Building an agent has two modes, Quick start and Brainstorm. Quick start takes the user's request plus what the agent needs to know. In Brainstorm the user talks the idea through until the plan is agreed, then the build starts. In both, the Arena starts from zero (20). Brainstorms are kept under one case id and can feed the engine later, but only after cleaning: a user's own words never leave their account, only patterns seen across many users are used, and users can choose to keep brainstorms for 30 days only. For the hackathon Brainstorm is a README note, with no engine behind it. 2026-10-30. The mode lines are amended by 58 and 64; the privacy and data rules stay.

26. Strict win rule: an Arena match is won only when the agent's draft_order really placed the order after the customer said yes. A yes or an address alone is no win, and an agent that says "order confirmed" with no order fails the order fact check. The practice customer gives a made-up name and address when asked. Why: a review found that an agent that lied could still win when the customer said yes. 2026-10-31.

## Layers, in this order

4. **Arena** (layer 1) builds the agent from a seed (core identity plus learned lessons). Meta models spar: one plays customer personas built from real chats with names, numbers and places removed, until the Sales agent wins. Then it replays real old chats and tries to close them, and goes live at its trust level. Every new lesson also passes through here. 2026-10-30.

5. **Deployment** (layer 2): the agent sells live on WhatsApp and saves no lesson mid chat. For the demo the owner chats live on the test number, then sends a message that beats it. No weak or rigged agent. 2026-10-30.

6. The third layer (first called learning, renamed Reflection in 31) starts after a sale did not close or a customer went quiet, never mid chat. It has two speeds linked by one case id: a fast note, one "try this instead" for the next chat only, which expires and is never saved as a lesson; and the night study, with a sales track (lessons) and a marketing track (a short note to the Marketing agent). 2026-10-30.

7. The order is fixed: Arena, then Deployment, then Reflection, and Reflection sends lessons back to the Arena. 2026-10-30.

## Gate and approvals

8. **Eval gate**: a new lesson takes the exam plus the Arena replay before it can be used. 2026-10-30. "Arena replay" here means rerunning the persona matches the agent already won, so a new lesson cannot break them (arena/gate.py). Replaying real lost chats stays the Arena's last step before going live. 2026-10-31.

9a. Before going live, a lesson earned in the Arena that passes the gate is used in the next Arena round: low risk on its own, high risk after the user's yes on the Morning page. The Canary (10) starts on live chats after go live. 2026-10-31.

27. The eval gate reports each lesson's effect as counts beside pass or fail: the cases it fixed and the cases it broke, shown on the Morning page. The idea came from a base against tuned comparison at a hackathon workshop. 2026-10-31. Amended by 75.

9. Low risk lessons that pass start on their own as a Canary; high risk ones wait for the user's yes on the **Morning page**. ("Accepted lessons get published automatically, without waiting for a human to approve every one.") 2026-10-30.

10. **Canary**: a lesson is tried on a share of chats and compared with the old way, then kept, pulled or paused on its own. Lessons are never rewritten. 2026-10-30.

## Trust levels

18. The trust level is set per industry and per agent, not one number in the engine. Sales agent: 7 of 10 persona matches won to go live ("sales is not something risky, so it would be 7"). A second demo agent was planned as a coding agent, then replaced on 31 October by the daily assistant. No level for the Marketing agent (19). 2026-10-30. Amended by 84 for agents built in Quick start.

19. In the demo the Marketing agent is only mentioned as the one that receives the night note. Nothing more is built or shown for it. 2026-10-30.

## Agents and names

11. The **Sales agent** is agent 1 and does the whole job for a store like this one, service included: order status, size exchange and delivery questions. The **Marketing agent** is agent 2. 2026-10-30.

12. The Sales agent never jokes; humour goes to marketing as a note. 2026-10-30.

13. Demo store: **Beyond the Limits**. No real customer is in the repo. 2026-10-30.

## Build

14. All agents run on Meta models: Muse Spark Open on Baseten for live work and the Arena, Muse Wonder on the Meta Model API for night work. 2026-10-30.

15. Repo: unfenced, renamed from ascent-learning-agents, the repo opened for the hackathon. What is new is marked clearly. 2026-10-30.

16. No new web framework: the existing plain Python server already answers Meta at once. A public tunnel is added for the live demo. 2026-10-30.

17. Kept out of the public repo: tuned prompts, trust thresholds, the persona recipe and any raw chat text. License: all rights reserved, with a copyright notice in the owner's name. 2026-10-30. The Sales agent's instructions file (sales/instructions.md) is public, since judges run the real agent and it holds no customer data. 2026-10-31. Amended by 23 for chat text and by 63 for the Sales level.

23. Cleaned real chat lines (names, numbers and addresses removed) may go into the public repo; only the original lines stay out. Risk said once: the cleaner still misses rare cases, and anything public is licensed to the organizers forever. 2026-10-30.

28. Nothing we built goes missing ("I really don't want what we achieved to be missing from the repo or the demo"). Every working part stays in the repo, tested, listed in the README under "Also built" and kept out of the demo story: the courier webhook (an optional result source), the importer, the delivery zone cards, the reply humanizer, the Marketing plug and the simulated week scores. A docs page holds the ideas from the owner's brainstorm, written fresh with nothing private. With the same yes, the eval gate adds a McNemar check on the fixed and broken counts (27), and an order gets a "name to print" field. 2026-10-31.

29. The public repo uses the real customer cards, cleaned (names, phones, addresses removed), for the Arena and for judges to see; no made-up cards ("we will use real cards for both"). Risk said once: the cleaner can miss a rare surname or a number written in words. Builders never open the raw data. 2026-10-31. This replaced an earlier call the same day to keep the cleaned cards private; the extra privacy scan it named is dropped in 40.

30. For every agent, both sides of its Arena keep feeding on real data, and this is a headline point: the real work each deployed agent does is cleaned and turned into new practice cases, and the practice side that beats it comes back more often. The opponent gets harder while the agent earns lessons, so every deployed agent gets stronger over time. Examples: new real sales chats become new customer cards; the daily assistant's real days become new simulated days. ("Not only the sales agent, I am talking generally.") 2026-10-31.

31. The third layer is renamed **Reflection**: fast reflection (the quick "try this instead") and night reflection (the night study). The layers are Arena, Deployment, Reflection. The README says how it differs from the Reflexion research method: our lessons pass the Arena and the gate before use, and nothing is saved mid chat. 2026-10-31.

32. Decision 30 runs through Reflection: Deployment does the real work, Reflection reads it at night, picks the cases worth practising (lost, quiet, hard; easy wins skipped), cleans them, marks won or lost (unclear skipped) and sends the Arena both lessons and new practice cases. Then the agent goes back to Deployment. Same for every agent. 2026-10-31.

33. Already agreed and built before 31 October, listed so they are kept: replies in Egyptian Arabic, English and Franco; voice notes and photos read, replies in text; the order found by WhatsApp number; a model timeout reply; the bare price check and reply rules in the instructions; the plain yes lock; a cash on delivery risk flag; a lesson that copies customer words always waits for a yes; the 50 situation exam; the trial stop rule; trial levels and Accept high risk with auto off; the engine holds no business words; the Morning page design. Also: the printing service is at most 25% of practice customers, and the Arena call cap is raised from 300. Muse Spark on the Meta Model API is the fallback when Baseten fails. 2026-10-31. One line (no mention of the old repo in the README) is amended by 60.

34. Names for people: the **user** builds the agent, approves lessons and flips the switches on the Morning page; the **team** takes chats the agent hands off; the **customer** is the business's customer. 2026-10-31.

35. The Morning page is light and never turns into unfinished work for the user. It shows only what truly needs a yes, nothing breaks if a day is skipped (a lesson with no answer stays off), and there are no daily tasks, quotas, counters of what is left or nagging. Good or Fix marking of replies is dropped. Parked: whether the README mentions a light way to get daily feedback from the user. 2026-10-31.

36. Personal assistant (the second demo agent): email sorting and drafts (nothing goes out without the user's yes), calendar booking without clashes plus prep notes, follow ups from promises, a morning brief, and modes (Focused, Rushed, Off) learned from corrections. Its Arena plays a simulated day won in code (no urgent mail missed, no clash, nothing sent without yes, promises become tasks, mode respected, no hidden email instruction followed). Lessons come only from the user's corrections. The README says it becomes more personal to the user over time and could later handle more of the user's life (spending, ideas), each new topic in its own file. The reasoning point behind it (a model adapts inside one chat and forgets in the next; Unfenced keeps what worked) stays open and out of the README until it is settled. 2026-10-31.

37. Personal assistant setup, before the Arena: when the user asks for an assistant, Unfenced replies in its own words with two aims: learn more about the user, and ask to connect their email. It reads the mail to build a picture of how the user works and uses it to pick starting modes and seed the simulated days. Other people's messages stay in the user's account; only patterns about the user are kept. Email is offered as the main connection and never required. 2026-10-31.

38. The text Unfenced or its agents say to a user is never locked: replies are written each time from an intent, not fixed wording. Fixed text stays only where code needs an exact check, such as the order summary the customer says yes to. The demo's email step uses an uploaded mailbox export; a live mail connection is next. 2026-10-31.

## Out, and why

- Production hosting and other hosted services: later, after the hackathon.
- A per case intent router: never agreed.
- Outside sources as ideas (books, other brands): dropped for the hackathon. Instagram and Messenger: dropped, WhatsApp only.
- A nightly prompt rewrite: it clashes with "lessons are never rewritten".
- A weak bot then witty bot demo: against 5 and 12.
- Older models from other providers: against 14.
- Old names for the layers that drifted during planning are not used.

## Open at the time

- Zero failed checks on top of 7 of 10 for the Sales agent (recommended, not decided).
- The Baseten call cap: raised (33).

## Later decisions

39. The catalogue comes from the real chats: the latest drop with the prices the shop quoted. Payment stays cash on delivery with no deposit step, although the real chats show a deposit first. Everything else stays real (model names, prices, sizes, colourways, printing at 400 EGP for two prints, one on each shoe); only two things change: the store is called Beyond the Limits, and customer info is removed. Amends 22. 2026-10-31. Amended by 105 (payment offers).

40. No second privacy scan on the cleaned cards and replay ("no need for a second scan", repeated after the risk was said once). The first cleaning stays, and no customer info goes in the repo. 2026-10-31.

41. Each finished piece is committed and pushed to the repo right after it passes the full suite and the checks. One commit per piece, noreply author, no trailers. Making the repo public stays the owner's call. 2026-10-31.

42. A measured Arena run on real keys, within the 1,000 call cap, on the hackathon credits, also recorded for the no key replay. The key handling code and the WhatsApp sweep get the full review and red team before the repo goes public. 2026-10-31.

43. The cleaned cards and replay sit in arena/real/. In that folder only, the drift check skips its old demo catalogue words, since there they are real customers' own questions. Real store names stay refused, and mentions of other stores read "another store". 2026-10-31.

44. "Hotfix" is the shown name for fast reflection in the README and its pictures: a dashed line from Reflection back to Deployment that changes the next chat only. Night reflection keeps its name; code names stay. 2026-10-31.

45. README pictures use the Floating planes style, with smaller card subtext. Each stage is a tight stack of cards, to show many agents on one engine. The Deployment card says "live with real data", and the bottom line reads "One engine. Sales agent, personal assistant, and more...". Other pictures each get the look that fits what they show. 2026-10-31.

46. A live agent keeps working the whole time. The Arena practises on its own copy and database, and the live agent changes only through a lesson that passed the eval gate (live first as a Canary on a small share of chats) or a hotfix. The loop picture shows Canary as its own dashed arrow from the eval gate to Deployment, labelled "canary, for live agents", and a dashed line from Reflection to the eval gate. 2026-10-31.

Decisions 47 to 52 were agreed together on 2026-10-31 ("Go for all"), from the owner's point that some lessons should make the Arena stronger and others should fix live agents, and his question of how agents of the same kind get smarter too.

47. Two lines leave Reflection. To the Arena: lessons plus new practice cases, so the Arena gets harder and every agent that comes out of it is stronger. To the eval gate: lessons for live agents, which then go out as a canary.

48. Decision 30 is built for the Sales agent the way the assistant has it: Reflection turns new real chats into cleaned practice customers each night (lost, quiet and hard ones; easy wins and unclear chats skipped), and a practice customer that beats the agent comes back more often.

49. Agents learn from each other: the night study reads the lessons other agents kept, rewrites the ones that fit, and each goes through this agent's own eval gate (engine/study.py).

50. A lesson that fails the eval gate is a mistake too: it goes back into Reflection with what it broke, so the next try avoids it. It still never goes live.

51. A new agent of a kind the owner already runs starts with zero lessons (20) but faces the Arena its siblings made harder. Practice customers built from one owner's real work are shared only among that owner's agents, never across owners, even cleaned. Amended by 79.

52. Fixes to round 3 checks that had become too strict: the price check keeps an add-on's price when an add-on word sits next to the amount (more, extra, plus, زيادة); the hotfix note name check lets catalogue and place words through.

53. No hand-off to the team in this build ("we can remove this feature for now since it was for the old repo"). The team note, the relay, the "team member is taking over" line and the model's hand-off tool go. The agent always keeps the chat, and a chat it could not save is still recorded as lost, so Reflection and the Arena learn from it. The repo names hand-off as a later feature: a person's reply in a handed off chat would become a human hotfix. Replies never quote the customer. 2026-11-01. Amended by 57 and confirmed for built agents by 72.

54. A chat ends after quiet, not after a day ("Reflection does not know when the chat ends"). After 30 minutes with no customer message the agent sends one line, once per chat, in the customer's language, saying the chat closes in 30 minutes and they can write anytime. After 30 more quiet minutes the chat closes; a closed chat with no order goes to the hotfix at once and to that night's Reflection, and a later message starts a new chat. Pull on the agent page is a real pause switch. Approved lines in Arabic, Franco and English live in sales/quiet.py. A chat found long quiet after a restart closes with no notice; a notice due while running always goes out. 2026-11-01.

55. The README has a section "Built before the hackathon": the visual design comes from the owner's own design system, made in October 2026 before the hackathon (bone, ink, volt for the one action, sage, Outfit, white cards, glass bars, squircle cards, phone tab bar and desktop island). Today and Agents, Quick start and the three day sample were built on it during the hackathon. 2026-11-01.

56. A correction the user sends on an agent page is a hotfix that starts at once on a 50/50 split. It takes the short exam first, and a high risk line still waits for a yes. It never waits behind a lesson already on trial, and the other half keeps the agent as it was, so each night Reflection compares the two halves before it is kept or pulled. 2026-11-01.

57. Amends 53: when the agent cannot send a safe reply it sends nothing, no fixed line. The chat keeps its stage and counts as lost if it ends with no order. 2026-11-01.

58. Amends 24 (the two mode lines only). **Quick start**: someone who wants an agent talks with Unfenced in a calm chat, never pushy or heavy. The chat draws out what the agent needs (its work, who it serves, a good result, its limits, files such as the brand file). Unfenced writes the plug as one card for a yes, and the Arena trains it from zero. There are no fixed questions and no fixed text: Unfenced guesses the rest from what the user wrote, shows the card at once, asks only what a wrong guess would get wrong, then says the user can add or change anything before it builds. **Brainstorm**: someone with a rough idea talks it through until it is solid; when the plan is an agent, Brainstorm builds it straight away. For the hackathon Brainstorm is "coming soon" with one README line. 2026-11-01.

59. Every agent Build makes is wired through every door like Sales, with no hand work. Build also writes the agent's exam (situations from the card's good result and never lines) and its practice people; the Arena, the eval gate, the night study and the pause switch take any agent. Practice people for a new agent take their behaviour from the owner's cleaned real cards (how they open, patience, language mix, when they go quiet, what worries them) and their want from the new agent's card. No real line, name or number moves, and only within one owner (51). 2026-11-02.

60. Amends 33's line on the old repo. The README names the working repo: days one to four were built in ascent-learning-agents (public, created 27 October) and moved here on 31 October as the first commit; work since is committed here step by step. No code in it predates 27 October. 2026-11-02.

61. Confirms 23, 40 and 43: the public cards keep their cleaned example lines, and the README says the personas are made from real customers' behaviour. Risk said once: the customers never agreed, and data law enforcement in Egypt is starting; not legal advice. 2026-11-02.

62. Builds on 47, 49, 51 and 24. The Arena line out of Reflection makes two things stronger: the opponent and the next agent of the same kind. A running agent never goes back into the Arena (46); it improves through the gate and the Canary. A new agent of the same kind from another owner gets patterns seen across many owners, never one owner's practice people. 2026-11-02. Amended by 83.

63. Amends 17 and 58 for one number: the README names the Sales agent's level, 7 of 10 practice matches won, and says each sector gets its own level. Other real levels and the persona recipe stay private. 2026-11-02. The line keeping the cross-owner pool as "next" is replaced by 83.

64. Amends 24 and 58 (the Brainstorm line only). Quick start is for when you just want an agent: your own words, one card, build. Brainstorm turns an idea into a full plan in the engine's own shape (case, stages, good result and harm, actions, risk, exam, trial), then builds from it. 2026-11-02.

65. A person who writes again after their chat closed continues the same case id: the new talk is saved under it as talk 2, talk 3, each with its own result and its own Reflection. 2026-11-02.

66. A late result closes its case, under the same case id, in one of three ways: the tool's webhook reports it; Unfenced asks the tool's API when there is no webhook; or a person marks it on the morning page or in an uploaded sheet. No timer closes a case: until a result comes it stays pending, out of every count and lesson. The plug names which events are good and which bad, with no days. 2026-11-02. Amended by 67.

67. Amends 66 for the Sales agent: Sales stays decided by the order (placed is good, closed with no order is not). Delivery results (delivered, refused) arrive the same three ways and feed the night study as a second signal, never deciding a case, a pattern or a gate. 2026-11-02. Amended by 73.

68. Quick start takes the case from the user. The card shows "One case is", the good result and the bad result, and the user can change any of them before Build. A user may paste or upload a few real past cases: personal info is removed first, and they become the first practice people, exam situations and the real reference outcome. With no examples, practice people are made up from the card. 2026-11-02.

69. A deployed agent has one kind of case. To add another kind of work, the agent page starts Quick start with that agent's tools and data, making a sibling agent with its own case, exam and Arena while the live agent keeps working. One agent with several case kinds is next, not built. 2026-11-02.

70. The hotfix gap: for an agent whose good result takes more than one message, the exam cannot see a correction help. For such an agent a correction plays one practice round in the Arena before it may go live as a hotfix. Not built at the time. 2026-11-02.

71. The personal assistant stays in the repo as the second agent on the engine. This week its code stays day shaped; the README says its case moves to one email thread next, with its own Arena shape. Amended by 109. 2026-11-02.

72. Confirms 53 for built agents: no case is handed to a person. An agent that needs people (a support ticket agent, for example) tags the case as one of its own actions, so the case still ends with the agent's result and can be judged. 2026-11-02.

73. Amends 67: the delivery result is no longer shown per pattern on the night cards; it stays recorded and shown per case, deciding nothing. Why: a night reads 2 days and deliveries land 2 to 7 days later, so per pattern counts could not be right. 2026-11-02.

74. No fixed rule tells the Sales agent to lean on "I will check with the team", and none is added in its place. The instruction line, the exam check that rewarded it and the tool texts that suggested it are removed; the Arena and Reflection teach how to answer instead. Inside an Arena run, an answer that lost is never tried again: the run keeps every quick note (up to 5), each telling the agent to try something new. Why: in the 2 November run, 9 of 19 losses ended on a team promise while the facts were in its tools, and the same mistake came back match after match. ("It shouldn't repeat mistakes in the same run." "I don't want to give it fixed rules to follow.") 2026-11-02.

75. Simplify so the engine shows working ("simplify the process so it doesn't fail a lot and gets deployed"). A built agent still goes through the Arena and the gate. A lesson passes the exam when no safety check newly breaks against the kept lessons and it fixes at least as many situations as it breaks; style checks are reported, never blocking. In the Arena a lesson is examined on its own stage and source situations under a cap; the night keeps the full exam. Amends 27. 2026-11-02. Amended by 80 and 84.

76. The Sales agent drops the real shop's old bot style and starts from a short seed (who it is, facts only from tools, orders only through draft_order on a plain yes, the cash on delivery risk flag for the team only, no rule changes from the customer). Tuning happens in the Arena, automatically (losses become lessons through the gate) and by hand (the user's corrections, each through the same exam and gate as a hotfix). The exact bot line goes. 2026-11-02.

77. Deploy is the user's step after the Arena: when an agent passes the gate, a "Connect to WhatsApp" button unlocks on its page (greyed out with the reason before). Pull takes it off. Later agents ask for the connections they need the same way. 2026-11-02.

78. The loop judges see: you control when the agent is deployed, it keeps learning from its mistakes, the Arena gets harder from real work, and agents of the same kind feed each other's live agent and Arena with fully or partly matched cases. 2026-11-02.

79. Amends 51 for agents of one kind under one owner: a new agent starts with its siblings' kept lessons, each fit checked, adapted and put on trial through the gate, never live straight away. Siblings' lost cases feed each other's night study and Arena, and practice customers grow from real losses of any kind. Build sets the agent's kind so siblings are found. Practice customers still never cross owners. 2026-11-02.

80. Correct this: each reply the agent lost a practice match on gets a Correct this box in the Arena view. It sends the same correction as the agent page (a hotfix through the full exam, 56) and never makes the Arena wait. Amends 75: the scoped exam is for the Arena only; a lesson that passes it takes the full exam once before it is handed to the live agent. 2026-11-02.

81. Try again: after an Arena run stops and the user corrected lost replies, Try again replays only the practice matches the agent just lost, against the same customers, with its kept lessons and the corrections that passed. Try again never unlocks Connect; only a full run's gate does. 2026-11-02.

82. Judges get two things: the Sales agent, already trained, to chat with; and Quick start, to make an agent of their own choosing as proof the engine works for any job. Sales is not rebuilt in Quick start. 2026-11-03.

83. Amends 62 and 63: the cross-owner pool is built for the hackathon, medium size. Kept lessons and lost cases of any agent kind become clean patterns (no names, numbers, prices, places or customer words, checked in code after the model writes them) in one pool per kind. A pattern is shared only once it is seen at 2 or more owners. New agents of that kind start with them and running agents get new ones, each on trial through the gate and the Canary. Each owner's Arena builds fresh practice customers from lost case patterns; one owner's real practice customers still never cross. The console says "learned from N owners". ("It should be general, not one owner only.") 2026-11-04.

84. Amends 18 and 75 for agents built in Quick start. Before Build the user picks how risky the job is: low (5 of 10 practice gate wins to go live), medium (7 of 10) or high (8 of 10 and zero failed safety checks). The agent's kind suggests one. After the first Arena result the page shows the score against the level, and the user keeps, lowers or raises it. A built agent studies its lost matches between rounds and stops at the level, after 2 rounds with no gain, or at 3 rounds. Lowering never skips safety. 2026-11-04. Amended by 85.

85. Amends 84 for the Arena's shape, for any agent. Low and medium: up to 2 rounds of 10 practice and 10 test matches. High: up to 3 rounds of 10 practice and 20 test matches, passing at 16 of 20 with zero failed safety checks, with a day call cap of 1,500 for that run only (others keep 1,000). Every practice and test customer is a different person, test customers stay the same run to run, and they are never studied. 2026-11-04.

86. Next, not built: a business makes agents that manage the business, linked to each other, each still learning through its own gate. It goes everywhere the next items are told. 2026-11-04.

87. A stock install has one owner, so "learned from N owners" never shows. No made-up demo owners are seeded; the README and the video explain the pool instead. 2026-11-04.

88. Old branches: the off-topic customer branch (scopeguard) is kept and merged after its fixes, and its made-up off-topic customer replaces one of the 10 practice matches. Three other branches are dropped. 2026-11-04. Amended by 89.

89. Amends 88, for any agent: no fixed off-topic questions. Each run the practice customer model reads the agent's card and writes one ask outside its work; the practice judge scores it with the exam's off-topic rules (decline briefly, do not answer, bring the customer back), and an ask the judge reads as on topic voids the match. With no model key the match is skipped, never faked. A loss becomes a case like any other. Next, not built: a live check on every real reply. 2026-11-04.

90. A red team finding (a training line relabelled as a test match could hide that a customer trained, so the fixed test set could be stacked) is fixed, not accepted: each match line is tied to the seal key. 2026-11-04.

91. After its last review round, the off-topic branch gets its three blockers fixed by one builder before merge, then a quick check. 2026-11-04.

92. The sample days leave the judges' path; a learning button on the agent's page replaces them. It runs that agent's night now with the real model on the real database (study the losses, write a lesson, exam, trial) and says plainly it is the learning step. With no key it says so and points to a real recording. 2026-11-04.

93. The learning button is named "Run reflection". 2026-11-04.

94. Every agent is told its exam rules up front: the engine passes the checks it is examined on (style, script, amounts, tools) into that agent's instructions, for any agent. Why: a live timed exam passed 3 of 53 situations (37 style, 9 script failures) on rules the instructions never named. 2026-11-04.

95. Run reflection wording: the running line is "Reflecting: reading lost chats, then writing a lesson, then the exam", and with no key "Reflection needs a model key. Watch a recorded reflection run instead." The button stays "Run reflection". 2026-11-04.

96. The Sales agent must reach deployment, and no user is left stuck. Run the Arena works for Sales too and saves its losses where Run reflection reads them. A stuck card names the next step. We run the real loop on Sales on our key until the gate passes; that run is the recording for judges with no key. ("All this time the Sales agent stayed in the Arena and never went to deployment.") 2026-11-04. The buttons are replaced by 102.

97. Reflection stays slow on purpose: it studies at high effort on the study route (Muse Wonder), unlike the fast live reply, because "the AI gets things wrong when it tries to reply fast". Run reflection runs the same deep study as the night, never a cut down version. 2026-11-04.

98. No cap on lessons in the study. The night writes and examines every lesson it finds until 09:00 Cairo; what is not done by then, or when the day call cap is hit, is queued and goes first the next night. Daytime Run reflection runs to the end with the call cap as the only hard limit, plus a Stop button that queues the rest. 2026-11-04.

99. The Arena path on the agent's page while it is not live: a status line with gate progress, a track with one highlighted next step, live lessons and exam results while Run reflection runs, "Ready to connect" when the gate passes, and the Stop button. 2026-11-04. The track is replaced by 102.

100. While Run reflection runs, or any time in the Arena, the user can type a fix or addition in the correction box; it joins the run as one more lesson and takes the same exam. They can also correct an existing lesson: the edit is a new version that takes the exam and, if it passes, replaces the old one on its trial. The old line stays in history. 2026-11-04.

101. The Arena gate follows the real customer mix: every customer type that can buy plays at its real share of real chats, no one type plays more than 3 of 10 gate matches, and every gate match is new. Why: the held-out cards were scaled up to fill the gate, so one rare type (10 of 300 chats) played about 98% of it. 2026-11-04.

102. The Arena track is two steps: Train (a short practice round, then Reflection on its losses, shown live), then Take the gate (the full run and the only way to unlock Connect). Run reflection stays for real customer chats only. Replaces the track in 99 and the buttons in 96. 2026-11-04. Replaced by 104.

103. Every agent gets the automatic hotfix: after a lost chat with a real customer, a quick note for that customer's next chat; after a lost practice match, a quick note for the rest of that Arena run. One shared path for every agent, under the same note guard. 2026-11-04.

104. The Arena track is Arena first: "Run the Arena" (the full run, new matches, the mix from 101) is the first step, and a pass unlocks Connect. On a fail the page shows won N of M, the main reasons it lost, and two fixes: Train (Reflection on that run's lost matches, live, with Stop) and the correction box. Then Run the Arena again. Replaces 102. 2026-11-04.

105. Store offers, for every agent. Why: the real shop's order rate is very low, and the gate asked for 7 of 10 from a mix the shop itself rarely wins. Each store's offers are data, not code: one line each (what it is, its terms, when it applies). The user gives them at Build; a connected store's real discounts, payment methods and stock are read first and confirmed. The agent sees offers only through the store tool, and the send check refuses any offer or amount the tool did not give. Practice customers keep their real voices and worries, but whether they can buy comes from the store's offers: a card an offer covers can buy, and a win is a sale; a card no offer covers wins on a correct close (no made-up offer, the nearest real option, polite, door left open), and Reflection never studies a correct close as a loss. The gate stays 7 of 10 on the real mix; the store's old rate shows as a report line. Beyond the Limits gets 3 month interest free installments through valU, free delivery on every order, 5% off for card payment, free name printing on Elite pairs, and 10% off the cheaper pair of a second pair. One offer per order (the one that saves the customer most), with free delivery on top. Amends 39. The wiring must be proven end to end, from Build to Reflection. 2026-11-04.

106. No rename. The built-in agent keeps the name sales. A judge can build their own sales agent under another name, and its kind stays sales so it learns beside ours. If a judge's agent would take an existing name, the Build chat says so before Build is pressed. 2026-11-04.

107. Sample data for any agent: when the data a job needs is missing (stock numbers, orders, emails), the engine makes sample data that fits the job, and the page labels it plainly as sample data. The page still asks to connect the real source, and real data replaces the sample once connected. Beyond the Limits gets sample stock per size under the same label, since the real shop's stock is not in the chats. 2026-11-04.

108. Pre-order for an out of stock size, a store rule for any agent. A store can let a customer order a size that is out of stock with a down payment share now and the rest on delivery. The rule is store data next to the offers, the agent reads it only through the store tool, and it is not an offer, so the order still takes its one offer. Beyond the Limits: 20% down payment, the rest on delivery, delivery within 7 days for a pre-order. The send check refuses a pre-order, a down payment or a pre-order delivery time the store data did not give; the order keeps the pre-order mark, the down payment and the rest; practice customers who want an out of stock size can buy through it; and the fact check accepts "out of stock, can be pre-ordered". 2026-11-04.

109. The personal assistant practises on the case Arena, like an agent made in Quick start, not on simulated days. One case is one request from the user or one email thread, through to a done result: a reply draft for the user's yes, a meeting booked with no clash, a promise turned into a dated task, or a morning brief. A made-up user asks for things, and the judge reads the assistant's card: its good and bad results and its never lines. Its page runs Run the Arena, Train, corrections and the exam on that path, at the risk level Quick start sets for its card (medium, 7 of 10). Its email and calendar tools read its demo mailbox and calendar, labelled as sample data; nothing it has can send, and the calendar books nothing that clashes or breaks the user's rules. It has no live channel here, so a pass unlocks nothing and the page never offers Connect. The simulated days stay for the night and the command line. The owner: "it should be working in arena for the tasks that will face like the meal prep". Amends 71. 2026-11-04.

111. A clear mistake teaches from one case: a broken never line or a failed fact check can make a lesson on its own, without the 5 cases from 3 sources floor or the gap test; the lesson still passes the exam, the gate and a trial before it is kept. Softer patterns keep the 75% chance with 5 cases from 3 sources on each side. ("Each lesson should be considered, not only when they are 3"; the owner left the exact rule to us.) 2026-11-04.
