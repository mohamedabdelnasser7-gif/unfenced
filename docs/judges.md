# For judges
*Created: 2026-10-31. Last updated: 2026-11-02.*

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
