# The ideas behind Unfenced
*Created: 2026-10-31. Last updated: 2026-11-01.*

Unfenced is an engine that builds AI agents for any industry and keeps improving them from their own mistakes. The engine is the product. The Sales agent for Beyond the Limits is one example of what runs on it: Sales agent, personal assistant, and more...

This page holds the ideas behind the engine and where they came from. Most came out of long brainstorm sessions while we built it. Some came from public research and open repos, named below where they did. Where an idea is not built yet, it says planned.

## Mistakes are material

A sale that did not close, a customer who went quiet, a reply that failed a check: each one is a case the engine can study. The agent is not built to fear mistakes. It is built to turn each one into a tested lesson.

The Arena makes this literal. The agent starts with zero lessons and loses its early practice matches. Each lost match goes to the night study, and the lessons it earns there are what let it win later.

## Never the same mistake twice

A lesson keeps what a mistake taught. It is one line, and it keeps its source: the cases behind it. A lesson is never rewritten. A better lesson retires the old one, and the old one stays on record.

This follows an idea from Agent Workflow Memory: add new memory and retire the old, instead of editing it. A study on summarised agent memory, The Compaction Cliff in Long-Running AI Agent Memory (arXiv 2608.22752), adds a reason. It found that rules fade each time a memory is summarised. Unfenced never summarises or rewrites lessons.

## Tested before use

A lesson changes how a live agent talks to real customers. One wrong lesson could repeat a mistake across many chats. So every new lesson passes the Arena and the eval gate before any agent uses it.

- The eval gate gives the lesson the exam, 50 situations, and reruns the practice matches the agent already won, so a new lesson cannot break them.
- It reports the cases the lesson fixed and the cases it broke, beside pass or fail, with a McNemar test on those counts. The idea came from a hackathon workshop that compared a base model with a tuned one.
- A lesson that passes goes live first as a canary: it runs on a share of chats and is compared with the old way. It is kept, pulled or paused on its own.
- Low risk lessons start on their own. High risk lessons wait for the user's yes on the Morning page.

## Nothing saved mid chat

In Deployment the agent saves no lesson while a chat is running. Reflection reads the chat after it ends.

The reason is poisoning. A customer could try to teach the agent something inside a chat. MemForm (arXiv 2610.14431) tested six models and found that what agents save to memory can be poisoned in all of them. So a lesson needs at least three different people behind it, and a lesson that copies a customer's words always waits for a yes.

There is one fast path, the hotfix. After a chat that did not close, fast reflection can write one "try this instead" note for that customer's next chat only. The note expires after that chat and is never saved as a lesson.

## Reflection is not Reflexion

Reflexion is a research method with an open repo. After a try, the agent writes a note to itself about what went wrong and reads it on the next try. The note is used at once, and the signal is instant: a test passing or failing, or the agent judging its own answer.

Reflection, the third layer of Unfenced, differs in two ways:

1. Lessons pass the Arena and the eval gate before use.
2. Nothing is saved mid chat.

It also waits for the real result, such as an order placed or a customer gone quiet, instead of an instant pass or fail. And it runs at two speeds: the hotfix, and night reflection. Night reflection has a sales track, which writes lessons, and a marketing track, which sends a short note to the Marketing agent.

We read other open projects on agent memory and self improvement too: Letta, mem0, LangMem, A-MEM, ExpeL, Voyager, Dynamic Cheatsheet, ACE, ReasoningBank and DSPy. Most of them learn from instant signals and let the agent change its own memory. A few ideas carried over. Dynamic Cheatsheet and Letta keep a fast part apart from a slow one, as our two speeds do. LangMem keeps facts apart from learned memory; in Unfenced, prices come from the catalogue and are checked in code, and lessons cover how the agent handles a chat. Voyager turns skills that work into code; we plan the same for lessons that keep winning. We built our own engine rather than use one of these.

## Both sides of the Arena grow on real data

The Arena has two sides: the agent, and the simulated side that tries to beat it. For every agent, both sides keep feeding on real data.

Deployment does the real work. Night reflection reads it and picks the cases worth practising: lost, quiet and hard ones. Easy wins are skipped. It cleans them, marks each won or lost, and skips the unclear ones. Then it sends the Arena two things: the agent's lessons, and new practice cases. A practice case that beats the agent comes back more often. So the opponent gets harder while the agent earns lessons, and every deployed agent gets stronger over time.

Research backs the need for this. Mind the Sim2Real Gap in User Simulation for Agentic Tasks (arXiv 2603.11245) compared simulated users with real people and found the simulated ones too cooperative, so agents scored higher against them than against humans. Real data keeps the simulated side closer to real customers.

For the personal assistant this is built: real days become new simulated days, and a day that beats it is drawn more often. For the Sales agent this is built too: each night, lost real chats are cleaned and become new practice customers, and the ones that beat it come back more often.

## Agents learn from each other

The night study also reads the lessons other agents kept. It rewrites the ones that fit in its own words, and each one goes through this agent's own eval gate. This is built.

A new agent of a kind the user already runs still starts with zero lessons. But it faces an Arena its siblings have made harder. Practice customers built from one user's real work are shared only among that user's agents, never across users, even cleaned.

## Failed lessons are material too

A lesson that fails the eval gate is a mistake as well. It goes back into Reflection with what it broke, so the next try is written to avoid it. The failed lesson is never rewritten and never goes live on its own. This is built.

## Hand-off to a person, as a human hotfix (planned)

In this build the agent keeps every chat. When it cannot send a safe reply, it sends nothing and answers the next message itself. The chat still counts as lost, so Reflection and the Arena learn from it.

We plan a hand-off to a person for later. A person's reply in a handed off chat would become a human hotfix: a "try this instead" from someone who knows the store, tested the way every correction is. It is not built.

## Daily feedback from the user (planned)

We plan a light way to hear from the user each day, for example one short message they can answer or ignore. Their answer would feed Reflection.

It has to stay light. The Morning page shows only what needs a yes. Nothing breaks if a day is skipped: a lesson with no answer simply stays off.

## Where the personal assistant goes next

The personal assistant sorts email, drafts replies, books meetings without clashes, turns promises into tasks and writes a morning brief. Nothing goes out without the user's yes. It becomes more personal to the user over time.

Next, it can handle anything in the user's life, such as money and spending, emails and ideas. Each new topic gets its own file the moment it opens. The demo reads an uploaded mailbox export; a live email connection comes next.
