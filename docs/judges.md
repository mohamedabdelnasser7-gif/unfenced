# For judges
*Created: 2026-10-31. Last updated: 2026-11-05 (Build starts no Arena run).*

Every model this project calls is a Meta model: Muse Spark on the Meta Model API, or Muse Spark Open on Baseten. You do not need to connect any other account. The store name is made up; the products and prices are real; the practice customers are built from real chats with names, numbers and addresses removed.

## Setup

1. Python 3 with its standard library is all you need. Nothing to install. We test on Python 3.14.
2. Clone the repo and run every command below from its root folder.

## Add your own key

1. Copy the example file: `cp .env.example .env`
2. Open `.env` and put your Meta Model API key after `META_API_KEY=`. That one key runs everything on Muse Spark.
3. `.env` is in `.gitignore`, so git never picks it up. Please do not commit it.

Which key runs what:

| Keys in `.env` | Where the calls go |
|---|---|
| `META_API_KEY` only | Muse Spark on the Meta Model API |
| `BASETEN_API_KEY` only | Muse Spark Open on Baseten |
| Both | Baseten first. If Baseten times out, cannot be reached, is busy or answers with a server error, that same call goes to the Meta Model API, and the log names the switch by host name only |
| Neither | Nothing is called. The run prints one line that points you to the recorded replay below |

Keys can also come from your shell environment; a value there wins over `.env`. The code never prints a key.

## Open the page

```
python3 -m unfenced
```

This serves the page on your own machine and prints the address to open. Ctrl+C stops it. On a fresh clone it first makes an empty database at `data/ascent.db`, which git ignores. It takes the same options as `python3 -m reflection.morning`; `python3 -m unfenced arena` and `python3 -m unfenced night` hand off to the Arena and to one night study. A night study started by hand holds the night lock while it runs: it does not start while the scheduled night or a Run reflection runs on the same database, and they wait for it.

It also adds one example agent to Agents, the Family Dinner Planner, built in Quick start: it plans a week of family dinners and a grocery list. Its work touches allergies and food restrictions, so it starts at the high risk level: it passes the Arena at 16 of 20, and one broken never line fails it. Like every agent it starts with zero lessons and no saved run, so you can run the Arena on it and train it right away. It is added once, and never over an agent of yours with the same name.

## Run the Arena, then Train

1. Open the page, then Agents. Pick an agent made on the page, or make one on New agent with your key. Build starts no Arena run, so you can add your data first.
2. On its Arena tab, press Run the Arena. It plays new matches against made-up customers, then the gate, and the page shows them as it plays. Only a run that passes unlocks Connect.
3. If the run does not pass, the card under it shows won N of M and the main reasons it lost; press Train to reflect on the matches that run lost, or type your own fix in the correction box under it, then press Run the Arena again.

Train is the learning step: it writes every lesson it finds in those matches and tests each one on a full exam before it can reach a real customer, and the page shows each lesson and its exam result as it goes. It is slow on purpose: it studies at high effort, because an agent that answers fast misses things. Stop lets the lesson in its exam finish and keeps the rest for tonight. Training never unlocks Connect; only the next run can. Your own fix takes the same exam, and the box is open any time. Run reflection, on the agent's Overview, is the same study on the real customer chats it lost.

Run the Arena, Train and Run reflection use your model key and count toward the same daily model call cap. With no key Run reflection points you to the recorded replay below. None of them starts while a night runs on the same database (the scheduled night, one started by hand or another agent's reflection), and only one of them runs on an agent at a time. If you stop the page while it reflects, the next press takes the lock back once that page has stopped. The Sales agent has the same track: it plays on a copy of the page's database, and only a lesson that passed the gate and the full exam reaches the database itself.

## Chat with the Sales agent

Open Agents, then Sales. The Try Sales box sits on its page. Write to it the way a customer would, about a product, a size or delivery, and the Sales agent answers on the demo store with your own model key, using the lessons its database has kept (none on a fresh clone). No real order or message goes out, and these chats never count for the gate, the exam or Connect. Start over opens a new chat. Each answer counts toward the same daily model call cap as the Arena.

Every other agent on Agents, the personal assistant, the Family Dinner Planner and any agent you build, has the same chat on its Live tab: it answers with its own tools on sample data, nothing is sent, and Use my version under a draft sends your rewrite as a correction. Ask the assistant "summarize my emails for today" or paste an email.

With no key in `.env`, the box says so and points you to the recorded replay below.

## Connect to WhatsApp

The Connect button on an agent's page stays locked until a full Arena run on the page's own database has passed its gate. The run seals what it saved, so a result written or changed by hand never unlocks it. The quick run below never unlocks it. Once Connect is on, Pull takes the agent off WhatsApp again.

To see it unlock, press Run the Arena on the agent's Arena tab until a run passes. The same full run for the Sales agent from the command line, on the page's database (`data/ascent.db`, which `python3 -m unfenced` makes empty on a fresh clone), then the page on it:

```
python3 -I arena/run.py --db data/ascent.db
python3 -m unfenced
```

The full run uses many more model calls than the quick one. Answering real WhatsApp messages also needs a WhatsApp Business number and its settings (the `WHATSAPP_` values read in `channels/whatsapp.py`), which this setup does not include.

## Open console

Every agent's page has an Open console link. The console shows how that agent's loop ran, read only from what the engine already saved: the newest Arena run and its matches, the lessons and their exams, the corrections, the night reports and the live chats. Press a row to see what the agent saw, what it decided and the raw record. Anything that was never saved for that turn says so.

## Quick Arena run

```
python3 -I arena/run.py --quick
```

The Arena plays practice customers against the Sales agent and then runs a small gate. By default they are the cards built from cleaned real chats in `arena/real/cards` (names, numbers and addresses removed); `--cards demo/personas/cards` plays the made-up set instead. The quick run is one round with one training match and a gate of one match, and it stops at 80 model calls at most. Its files go to `data/arena-quick`, which git ignores. It ends with a short report: what each match ended on, the gate result and the calls used. Exit code 0 means the gate passed, 1 means it did not, 2 means it did not run (the line above it says why).

The full run drops `--quick` and names a folder for its files with `--state` (options at the top of `arena/run.py`).

## Agents of one kind learning together

```
python3 -I demo/make_loop_state.py
```

This writes a made-up owner to `data/demo-loop`: two Sales style agents of one kind, a support agent, a few made-up chats and one lesson the first agent kept. It prints three night commands. With a key, run them in order: the first two grow practice customers from their lost chats, each of its own kind, and the last finds its sibling's kept lesson, adapts it and holds it for a yes, since it has no exam to try it through yet.

## No key: the recorded replay

```
python3 -I recorded/play.py
```

This prints a recorded Arena run and a recorded Sales chat from `recorded/arena-run.json` and `recorded/sales-chat.json`. It needs no key and opens no network connection. Each file carries its provenance: when it was recorded, the command that made it, and a trace with one entry per model call (who asked, the host, the model id, start and end times, and the answer).

The recording shipped today was made with scripted stand-in models on the made-up customers, and both the files and the replay say SCRIPTED at the top. It shows the shape of a run, not what Muse Spark says, and it is recorded again after the measured run on the cleaned real cards. A real recording comes from the same recorder with a key:

```
python3 -I recorded/record.py
```

## Tests

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t .
```

The tests use no key and make no network call.
