"""The Arena loop and its gate (new, 2026-10-30; DECISIONS items 4, 7, 14, 17, 18, 30, 48, 51).

    python3 -I arena/run.py --cards DIR --matches N [--rounds 5] [--held-out persona-03,persona-07]
        [--trust FILE] [--customer-prompt FILE] [--cap 1000] [--state DIR] [--db PATH]
        [--replay FILE [--replay-max 10]] [--fact-checks on|off] [--seed 0] [--json] [--quick]

Each round: N training matches, each card drawn by its arena_weight from the cards the agent may
train on, then the gate: the agent's trust level of matches (its "matches") drawn the same way
from the held-out cards that can buy, which never train it (their losses go nowhere). The gate
passes at the level's "wins". With no --held-out, the held-out cards are a seeded share of the
cards that can buy, spread over their worries; a card that will not buy is never a gate match.
With --db the Arena practises on its own copy of the Sales agent's database (DECISIONS item 46):
at the start of the run the live database is copied to <db>.arena beside it (arena_copy, replacing
the last run's copy, whose lessons that failed the eval gate and still wait come along with their
exam rows, DECISIONS item 50), and every case, lesson, exam and trial the run writes goes into the copy.
The live database changes only when a lesson passes the eval gate between rounds: that lesson
alone is written to it, as the night study writes one there (arena/rounds.py hand_live). Before
every match the Arena reads the live database, read only, for a correction the user typed there
that passed its exam and runs there as a hotfix, and hands it from that match on (arena/rounds.py
live_hotfixes and Pool.refresh). The
Sales agent plays every match with the database's kept lessons handed, as the exam hands them,
so the gate tests the agent with what it has learned, not the bare seed. A lost training match
becomes a case in the copy, for the night study between rounds (arena/learn.py). Every agent
starts from zero and earns its lessons in the Arena (DECISIONS item 20), so a database holding a
lesson sourced from history rows (a business's past imported by reflection/importer.py) is
refused: see history_lessons.

Trust levels are per agent and stay out of the repo (DECISIONS item 17): --trust names a JSON file
outside it, shaped like {"sales": {"matches": 4, "wins": 3, "zero_failed_checks": true}} (stand-in
numbers, not a real level). With none, the public placeholder below asks 7 of 10 gate matches won. zero_failed_checks (on unless the level says
false; --fact-checks overrides it): a match with any failed fact check is lost (arena/verdict.py).

The loop stops on a pass, at the model call cap, at a model that does not answer (that match is
dropped as a capped one is, never counted as lost; the report names the error), or after
NO_GAIN_ROUNDS rounds in a row with no more gate wins than the best round before; then the stuck point is written next to the database
(or in --state) as arena-<agent>-<time>.json, an item for the Morning page. between(round), when
given, runs before each round after the first. With --db and more than one round the CLI fills it
(arena/rounds.py, DECISIONS item 9a): the night study on the round's lost training matches, every
new lesson through the eval gate, and only the lessons that pass and may go ahead with no further
yes handed to the next round; its model calls take from the same cap, and a cap reached there stops
the run. The report gives each round's lessons proposed, passed, refused and handed on beside its
gate wins, and the same rows go to the Morning page in the run's item (arena_rounds, or the stuck
item when it got stuck). With no --db there is no step between rounds. With that step, each lost
training match also gets a quick note from the fast half of Reflection (arena/notes.py), held in
memory and handed in the run's next matches until the step between rounds has run; it is never a
lesson and never written to any database.

--replay names the persona build's replay.jsonl: once the gate passes, the Sales agent replays up
to --replay-max real lost chats, each from the customer's real opening against the persona card
with the chat's worry (arena/replay.py), scored with the same fact checks and verdict and counted
against the same cap. A lost replay becomes a case too. Cleaned real chat lines (names, numbers
and addresses removed) may sit in the repo (DECISIONS item 23): arena/real/replay.jsonl is the
cleaned replay set, beside the cleaned real cards. arena/replay.py load() takes that file and
refuses any other file inside the repo.

--cards defaults to the cleaned real cards (DEFAULT_CARDS, arena/real/cards; DECISIONS items 23
and 40). The made-up set is DEMO_CARDS (demo/personas/cards); the tests use it and never read
arena/real/.

Model calls: every call of the agent and of the customer counts against the cap a day (Cairo
day), default 1000, saved in arena-calls.json after each call under a lock (arena-calls.lock), so
the count holds across runs and two runs at once share one cap. A count file that is there but
cannot be read, or holds no whole count for today, counts as the cap reached (Calls.problem says
why, and so does the report) until it is fixed or removed, so a broken count never starts at 0.
Every match is saved in arena-matches.jsonl with its verdict: the past wins the eval gate
reruns (arena/gate.py). Both files sit next to the agent's database (--db), with the stuck
item, so the gate reads that agent's own wins and nothing else. --state names their folder
only for a run with no database (its wins feed no gate); one of the two is needed.

Both sides grow (items 30, 48, 51; arena/grow.py). The base cards are split first, and the held
ids are saved in the owner's pool of practice customers, so the gate keeps the same cards run
after run while the pool grows and while the base card ids and the seed stay; a card grown from
real chats is never held out, and a new split holds a card that has trained only when too few
have not (fixed_split). The cards grown from real chats then join the training cards only. In training
a card whose group beat the agent is drawn more often (per loss, grow.LOST_WEIGHT, at most
grow.MAX_COUNTED_LOSSES losses counted), and each side's
share and the capped wants are held on the training draws; the gate draws at the weights before
any loss, its capped wants held on its own. Each training match's result is counted in the pool,
practice-<kind>.json in the owner's state folder (grow.owner_of: the folder above the agent's
when its owner.json names the owner the plug names, else the agent's own). Agents of one kind
under one owner share the pool; a new one starts with zero lessons and faces the same customers.

--quick is the short run for judges (docs/judges.md): one round of one training match and a gate
of one match (QUICK_TRUST, in place of --trust), at most QUICK_CALLS model calls in this run on
top of the day's cap, its files under data/arena-quick unless --db or --state names a place.
With no model key in env or .env (META_API_KEY or BASETEN_API_KEY), the run prints one line
pointing to the recorded replay (recorded/play.py) and exits 2 before reading anything else.
"""
import argparse
import datetime
import fcntl
import functools
import json
import os
import random
import re
import sqlite3
import stat
import sys
import time
import zoneinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I
    sys.path.insert(0, str(ROOT))

from arena import factcheck, match as match_mod, paths, replay as replay_mod, verdict  # noqa: E402
from kit import seal  # noqa: E402
from reflection import history as hist  # noqa: E402

AGENT = "sales"
DEFAULT_CARDS = ROOT / "arena" / "real" / "cards"  # the cleaned real cards (DECISIONS items 23 and 40)
DEMO_CARDS = ROOT / "demo" / "personas" / "cards"  # the made-up set: the tests use it
CALLS_FILE, MATCHES_FILE = "arena-calls.json", "arena-matches.jsonl"
DEFAULT_CAP = 1000
DEFAULT_ROUNDS = 5
NO_GAIN_ROUNDS = 2
HELD_OUT_SHARE = 0.3
GROWN = "grown-"  # the id of a card grown from real chats (arena/grow.py): it trains, never takes the gate
PUBLIC_TRUST = {"matches": 10, "wins": 7, "zero_failed_checks": True}  # the Sales level, public (DECISIONS item 63)
TZ = "Africa/Cairo"
PASSED, CAP, STUCK, ROUNDS, MODEL_ERROR = "passed", "cap", "stuck", "rounds", "model_error"
# What play returns for a match it played but could not judge (arena/practice.py: the judge's answer could not
# be read twice): the run goes on, the match counts neither won nor lost, and the round counts it as unjudged.
UNJUDGED = "unjudged"
# --quick, the short run for judges (docs/judges.md): one round of one training match and a gate of
# one match, at most QUICK_CALLS model calls in the run, its files under the ignored data/ folder.
QUICK_TRUST = {"matches": 1, "wins": 1, "zero_failed_checks": True}
QUICK_CALLS = 80
QUICK_STATE = ROOT / "data" / "arena-quick"


class Refused(ValueError):
    pass


class CapReached(Exception):
    pass


def today():
    """The Cairo date, YYYY-MM-DD."""
    return datetime.datetime.now(zoneinfo.ZoneInfo(TZ)).strftime("%Y-%m-%d")


class Calls:
    """Model calls counted per Cairo day against a cap, saved after each call. Every take() locks
    the count's lock file (arena-calls.lock beside it), reads the count again, checks the cap and
    writes the new count to a temp file it then moves over the old one, so two runs on one file
    (the night and the Morning page, or two Arena runs) share one cap and a crash never leaves half
    a file. count is the day's count when last read; taken, the calls this object took. problem: why
the count file could not be read, when it could not; then every take() is refused as at the cap."""

    def __init__(self, path, cap=DEFAULT_CAP, day=None, limit=None):
        """limit: at most this many calls by this object (the quick run), on top of the day's cap."""
        self.path, self.cap = Path(path), int(cap)
        if self.cap < 1:
            raise Refused("--cap must be at least 1")
        self.limit = None if limit is None else int(limit)
        self.fixed_day = day
        self.day = day or today()
        self.lock = self.path.with_suffix(".lock")
        self.temp = self.path.with_name(self.path.name + ".tmp")
        self.reached, self.taken, self.problem = False, 0, None
        self.count = self._read()

    def _read(self):
        """The day's saved count: 0 with no file or a count of another day. A file that is there but
        cannot be read or has the wrong shape sets problem and reads as the cap (fail closed)."""
        self.problem = None
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        except OSError:
            self.problem = f"the call count file {self.path.name} cannot be opened"
        except (ValueError, RecursionError):
            self.problem = f"the call count file {self.path.name} is not a count the Arena wrote"
        else:
            if not isinstance(saved, dict) or not isinstance(saved.get("day"), str):
                self.problem = f"the call count file {self.path.name} is not a count the Arena wrote"
            elif saved["day"] != self.day:
                return 0
            elif isinstance(saved.get("calls"), bool) or not isinstance(saved.get("calls"), int) or saved["calls"] < 0:
                self.problem = f"the call count file {self.path.name} has no whole count of calls for {self.day}"
            else:
                return saved["calls"]
        return self.cap

    def take(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if self.limit is not None and self.taken >= self.limit:
                self.reached = True
                raise CapReached(f"the run's limit of {self.limit} model calls is reached")
            self.day = self.fixed_day or today()  # read at each call, so a run across Cairo midnight moves on with the file
            self.count = self._read()
            if self.problem:
                self.reached = True
                raise CapReached(f"{self.problem}; it counts as the cap reached until it is fixed or removed")
            if self.count >= self.cap:
                self.reached = True
                raise CapReached(f"the cap of {self.cap} model calls for {self.day} is reached")
            self.count += 1
            self.temp.write_text(json.dumps({"day": self.day, "calls": self.count, "cap": self.cap}), encoding="utf-8")
            os.replace(self.temp, self.path)
            self.taken += 1
        finally:
            os.close(fd)  # closing the file lets the lock go

    def model(self, inner):
        calls = self

        class Counted:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                calls.take()
                return inner.chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)

            def __getattr__(self, name):  # the route and model id a part names in its label
                return getattr(inner, name)
        return Counted()


def load_cards(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise Refused(f"no cards folder at {folder}")
    cards = []
    for p in sorted(folder.glob("persona-*.json")):
        if p.is_symlink() or not p.is_file() or p.resolve().parent != folder.resolve() or p.stat().st_nlink > 1:
            raise Refused(f"{p.name}: a card is a plain file in the cards folder, never a link")
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError) as e:
            raise Refused(f"{p.name}: {type(e).__name__}") from None
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or \
                not isinstance(c.get("arena_weight"), (int, float)):
            raise Refused(f"{p.name}: a card is an object with an id and an arena_weight")
        cards.append(c)
    if len(cards) < 2:
        raise Refused("the Arena needs at least 2 cards: one to train on and one held out")
    return cards


def can_buy(card):
    """A card that can buy: not told it will not buy in this chat."""
    return not card.get("unwinnable")


def split(cards, held_out=None, share=HELD_OUT_SHARE, seed=0, never=()):
    """(training cards, held-out cards). held_out: card ids; else a seeded share of the cards that
    can buy, one card a worry in a seeded worry order, then a second round, so the gate is spread
    over worries. A card that will not buy is never held out by the draw: the gate only plays cards
    that can buy (Arena.gate_cards), so a held-out card that cannot would only be lost to training.
    A card grown from real chats (grown-...) and a card in never (one that has trained) are never
    held out, by the draw or by name."""
    ids = [c["id"] for c in cards]
    never = set(never) | {i for i in ids if i.startswith(GROWN)}
    if held_out:
        unknown = sorted(set(held_out) - set(ids))
        if unknown:
            raise Refused(f"held-out cards not found: {', '.join(unknown)}")
        trained = sorted(set(held_out) & never)
        if trained:
            raise Refused(f"cards grown from real chats or that have trained never take the gate: {', '.join(trained)}")
        held = set(held_out)
    else:
        winnable = [c for c in cards if can_buy(c) and c["id"] not in never]
        if not winnable:
            raise Refused("no card can buy, so no gate match can be won; the Arena needs a card that can buy")
        n = min(max(1, round(share * len(cards))), len(winnable), len(cards) - 1)
        rng = random.Random(f"held:{seed}")
        by_worry = {}
        for c in sorted(winnable, key=lambda c: c["id"]):
            by_worry.setdefault(str(c.get("worry") or ""), []).append(c["id"])
        worries = sorted(by_worry)
        rng.shuffle(worries)
        for w in worries:
            rng.shuffle(by_worry[w])
        held = set()
        while len(held) < n:
            for w in worries:
                if by_worry[w] and len(held) < n:
                    held.add(by_worry[w].pop())
    train = [c for c in cards if c["id"] not in held]
    if not train:
        raise Refused("every card is held out; leave at least one to train on")
    out = [c for c in cards if c["id"] in held]
    if not any(can_buy(c) for c in out):
        raise Refused("no held-out card can buy, so no gate match can be won; hold out a card that can buy")
    return train, out


def fixed_split(cards, held_out, seed, pool):
    """split() of the base cards with the owner's pool (arena/grow.py), the held ids saved in the
    pool, so the gate stays the same set run after run while the pool grows. A saved split is used
    again while the base card ids and the seed are the same and none of its held cards played a
    training match itself (pool.trained_ids; another card of their worry may have); a saved split
    split() refuses (a held card trained in a --held-out run, or none can buy now) is drawn again.
    held_out names the gate for this run only: a card that has trained is refused, and the saved
    split stays as it was. A new split (draw_held) holds the
    cards that have not trained first and tops up from the least played, so it never shrinks or
    stops because every worry has trained."""
    if held_out:
        return split(cards, held_out, seed=seed, never={c["id"] for c in cards if pool.trained(c)})
    ids, saved = sorted({c["id"] for c in cards}), pool.split
    spent = set(pool.trained_ids) & set(ids)  # base cards that played a training match themselves
    if saved and saved["cards"] == ids and saved["seed"] == seed:
        try:
            return split(cards, saved["held"], seed=seed, never=spent)
        except Refused:
            pass
    held = draw_held(cards, seed, pool, spent=spent)
    new = {"cards": ids, "seed": seed, "held": held}
    if new != saved:
        pool.split = new
        pool.changed = True
    return split(cards, held, seed=seed)


def draw_held(cards, seed, pool, share=HELD_OUT_SHARE, spent=frozenset()):
    """The held ids of a new split, sorted: split()'s seeded draw over the cards that can buy and
    have not trained, then topped up to split()'s size from the cards that can buy and have
    trained, the least played first (grow.Pool.plays; a seeded order among equals). A card in
    spent (it played a training match itself) tops up last, only when no other card is left."""
    winnable = [c for c in cards if can_buy(c) and not c["id"].startswith(GROWN)]
    if not winnable:
        raise Refused("no card can buy, so no gate match can be won; the Arena needs a card that can buy")
    n = min(max(1, round(share * len(cards))), len(winnable), len(cards) - 1)
    trained = {c["id"] for c in winnable if pool.trained(c)} | set(spent)
    held = set()
    if len(trained & {c["id"] for c in winnable}) < len(winnable):
        held = {c["id"] for c in split(cards, None, share, seed, never=trained)[1]}
    rest = sorted((c for c in winnable if c["id"] not in held), key=lambda c: c["id"])
    random.Random(f"top-up:{seed}").shuffle(rest)
    rest.sort(key=lambda c: (c["id"] in spent, pool.plays(c)))
    held |= {c["id"] for c in rest[:n - len(held)]}
    return sorted(held)


def draw(cards, rng):
    weights = [max(0.0, float(c["arena_weight"])) for c in cards]
    if not any(weights):
        weights = [1.0] * len(cards)
    return rng.choices(cards, weights=weights)[0]


def load_trust(path, agent=AGENT):
    if path is None:
        return dict(PUBLIC_TRUST)
    p = Path(path).expanduser().resolve()
    if paths.inside_repo(p):
        raise Refused("the trust file sits inside the repo; keep it outside (DECISIONS item 17)")
    data = json.loads(p.read_text(encoding="utf-8"))
    level = data.get(agent) if isinstance(data, dict) else None
    if level is None:
        return dict(PUBLIC_TRUST)
    if not isinstance(level, dict):
        raise Refused(f"trust level for {agent}: an object with matches and wins")
    m, w = level.get("matches"), level.get("wins")
    whole = [isinstance(v, int) and not isinstance(v, bool) for v in (m, w)]  # true is no count of matches
    if not (all(whole) and 1 <= w <= m):
        raise Refused(f"trust level for {agent}: whole matches and wins, 1 <= wins <= matches")
    return {"matches": m, "wins": w, "zero_failed_checks": level.get("zero_failed_checks", True) is not False}


class Arena:
    agent = AGENT  # the name its report and Morning page item carry; arena/practice.py sets its own

    def __init__(self, cards, *, agent_model, customer_model, calls, trust=None, prompt=match_mod.GENERIC_PROMPT,
                 prompt_file=None, held_out=None, matches=10, rounds=DEFAULT_ROUNDS, fact_checks=None, seed=0,
                 learn=None, between=None, lessons=None, state, reports=None, now=time.time, pool=None,
                 before_match=None, notes=None):
        """prompt_file: where the customer prompt was read from (None for the generic one), saved
        with each match beside the prompt's fingerprint, so the eval gate can read it again.
        pool: the owner's practice pool (arena/grow.py), which counts each training match's result.
        before_match: called before every match (arena/rounds.py Pool.refresh: the live corrections).
        notes: the run's quick notes (arena/notes.py RunNotes): one written after each lost training
        match, every one of them handed in the next matches, dropped once the step between rounds has run."""
        if pool is None:
            self.train, self.held = split(cards, held_out, seed=seed)
            self.gate_cards = [c for c in self.held if can_buy(c)]  # a card that will not buy is no test of the agent
        else:  # the base cards split first, then the grown cards and the weights (arena/grow.py decks)
            from arena import grow
            _, self.held = fixed_split(cards, held_out, seed, pool)
            self.train, self.gate_cards = grow.decks(cards, pool, {c["id"] for c in self.held})
        self.calls = calls
        self.agent_model, self.customer_model = calls.model(agent_model), calls.model(customer_model)
        self.trust = trust or dict(PUBLIC_TRUST)
        self.quick = False  # main sets it for --quick: its item never unlocks Connect (Morning.gate)
        self.facts = self.trust.get("zero_failed_checks", True) if fact_checks is None else bool(fact_checks)
        self.prompt, self.matches, self.rounds, self.seed = prompt, int(matches), int(rounds), seed
        self.prompt_sha = match_mod.prompt_sha(prompt)
        self.prompt_file = None if prompt_file is None else str(prompt_file)
        self.learn, self.between, self.lessons = learn, between, lessons
        self.pool, self.before_match, self.notes = pool, before_match, notes
        self.halt, self.error = CAP, ""  # why the last match was dropped: the cap, or a model error
        self.state = Path(state)
        self.reports = Path(reports) if reports is not None else self.state
        self.now = now
        self.run_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now()))
        self.rng = random.Random(f"draw:{seed}:{self.run_id}")
        if self.matches < 1 or self.rounds < 1:
            raise Refused("--matches and --rounds must be at least 1")

    def play(self, card, match_id, *, opening=None, lessons=None, replay=None, training=False):
        """One match and its verdict, saved; None when the cap stopped it (the match is dropped).
        replay: the replay chat's id, saved on the match. training: a training match, the only kind
        handed the run's quick notes (the live agent never gets them, so the gate and the replay
        play without)."""
        if self.before_match is not None:
            self.before_match()
        try:
            m = match_mod.play(card, agent_model=self.agent_model, customer_model=self.customer_model,
                               prompt=self.prompt, lessons=lessons or self.lessons, seed=match_id,
                               opening=opening, checker=factcheck.check, stop=verdict.closed,
                               **(self._fast() if training else {}))
        except CapReached:
            self.halt = CAP
            return None
        if self.calls.reached:
            self.halt = CAP
            return None
        if m.get("ended") == match_mod.VOID:  # a model did not answer: dropped, never a loss
            self.halt, self.error = MODEL_ERROR, m.get("error") or ""
            return None
        judged = verdict.judge(m, facts=self.facts)
        m.update(id=match_id, won=judged["won"], why=judged["why"], quote=judged["quote"], persona=card,
                 prompt_sha=self.prompt_sha, prompt_file=self.prompt_file)
        if replay is not None:
            m["replay"] = replay
        self.state.mkdir(parents=True, exist_ok=True)
        with open(self.state / MATCHES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
        return m, judged

    def _fast(self):
        """The quick notes for match_mod.play (fast=, which it hands to loop.turn)."""
        return {} if self.notes is None else {"fast": self.notes}

    def run(self):
        rounds, best, flat, stopped = [], None, 0, ROUNDS
        for r in range(1, self.rounds + 1):
            if r > 1 and self.between is not None:
                got = self.between(r - 1)
                if isinstance(got, dict):  # arena/rounds.py: the night study and the gate on the round before
                    rounds[-1]["reflection"] = got
                if self.notes is not None:  # the study has read the lost matches its notes came from
                    dropped = self.notes.clear(r - 1)
                    if dropped:
                        rounds[-1]["training"].setdefault("notes", []).extend(dropped)
                if self.calls.reached:  # the cap came during the night study: stop here, nothing unchecked goes on
                    self.halt = CAP
                    return self._report(rounds, CAP)
            one ={"round": r, "training": {"played": 0, "won": 0, "cases": []},
                   "gate": {"played": 0, "won": 0, "lost": []}}
            rounds.append(one)
            for k in range(1, self.matches + 1):
                card = draw(self.train, self.rng)
                out = self.play(card, f"{self.run_id}-r{r}-t{k:02d}", training=True)
                if out is None:
                    return self._report(rounds, self.halt)
                if out is UNJUDGED:
                    one["training"]["unjudged"] = one["training"].get("unjudged", 0) + 1
                    continue
                m, judged = out
                one["training"]["played"] += 1
                one["training"]["won"] += judged["won"]
                if self.pool is not None:  # a practice customer that beats the agent comes back more often
                    self.pool.record(card, judged["won"])
                if not judged["won"] and self.learn is not None:
                    one["training"]["cases"].append(self.learn(m, judged, m["id"]))
                if not judged["won"] and self.notes is not None:  # the quick note, for the next matches
                    one["training"].setdefault("notes", []).append(self.notes.after_loss(m, judged, m["id"]))
            for k in range(1, self.trust["matches"] + 1):
                card = draw(self.gate_cards, self.rng)
                out = self.play(card, f"{self.run_id}-r{r}-g{k:02d}")
                if out is None:
                    return self._report(rounds, self.halt)
                if out is UNJUDGED:
                    one["gate"]["unjudged"] = one["gate"].get("unjudged", 0) + 1
                    continue
                m, judged = out
                one["gate"]["played"] += 1
                one["gate"]["won"] += judged["won"]
                if "failed_check" in judged:  # a built agent's verdict marks its safety checks (arena/practice.py)
                    one["gate"]["failed_checks"] = one["gate"].get("failed_checks", 0) + bool(judged["failed_check"])
                if not judged["won"]:
                    one["gate"]["lost"].append({"card": m["card"], "why": judged["why"], "quote": judged["quote"]})
            wins = one["gate"]["won"]
            if self._passed(one):
                return self._report(rounds, PASSED)
            flat = flat + 1 if best is not None and wins <= best else 0
            best = wins if best is None else max(best, wins)
            if flat >= NO_GAIN_ROUNDS:
                stopped = STUCK
                break
        return self._report(rounds, stopped)

    def _passed(self, one):
        """Did the round pass the gate? Its wins reach the trust level's (arena/practice.py adds its rule)."""
        return one["gate"]["won"] >= self.trust["wins"]

    def replay(self, planned, skipped=None):
        """The replay of real lost chats ([(entry, card, opening)], arena/replay.py plan): each
        played from its real opening against its card, judged and saved as a match; a lost one
        becomes a case when learn is set. Stops at the call cap."""
        out = {"played": 0, "won": 0, "lost": [], "cases": [], "skipped": dict(skipped or {}), "stopped": None}
        for entry, card, first in planned:
            got = self.play(card, f"{self.run_id}-replay-{entry['id']}", opening=first, replay=entry["id"])
            if got is None:
                out["stopped"] = self.halt
                if self.halt == MODEL_ERROR:
                    out["error"] = self.error
                break
            if got is UNJUDGED:
                out["unjudged"] = out.get("unjudged", 0) + 1
                continue
            m, judged = got
            out["played"] += 1
            out["won"] += judged["won"]
            if not judged["won"]:
                out["lost"].append({"chat": entry["id"], "card": m["card"], "why": judged["why"],
                                    "quote": judged["quote"]})
                if self.learn is not None:
                    out["cases"].append(self.learn(m, judged, m["id"]))
        return out

    def _report(self, rounds, stopped):
        rep = {"agent": self.agent, "run": self.run_id, "stopped": stopped, "trust": self.trust, "fact_checks": self.facts,
               "training_cards": [c["id"] for c in self.train], "held_out_cards": [c["id"] for c in self.held],
               "rounds": rounds, "calls": {"day": self.calls.day, "used": self.calls.count, "cap": self.calls.cap}}
        if self.calls.problem:
            rep["calls"]["problem"] = self.calls.problem
        if self.calls.limit is not None:
            rep["calls"]["run_limit"], rep["calls"]["run_used"] = self.calls.limit, self.calls.taken
        if stopped == MODEL_ERROR:
            rep["error"] = self.error
        if stopped == STUCK:
            rep["stuck"] = self.stuck_item(rounds)
        elif rounds and (stopped == PASSED or any("reflection" in r for r in rounds)):  # a round one pass unlocks Connect too
            rep["item"] = self.rounds_item(rounds, stopped)
        return rep

    @staticmethod
    def reflection_rows(rounds):
        """Each round's gate wins and, after it, its Reflection counts (arena/rounds.py), for the
        Morning page: [{round, gate_won, gate_played, reflection or None}]."""
        out = []
        for r in rounds:
            got = r.get("reflection")
            keep = None if got is None else {k: got.get(k) for k in (
                "after_round", "cases", "proposed", "passed", "refused", "waits_for_yes", "handed", "fixed", "broke",
                "calls", "stopped")}
            out.append({"round": r["round"], "gate_won": r["gate"]["won"], "gate_played": r["gate"]["played"],
                        "reflection": keep})
        return out

    def rounds_item(self, rounds, stopped):
        """The run's rounds with their Reflection counts as a Morning page item, written next to
        the database as the stuck item is (a run that got stuck writes that one, with the same rows)."""
        last = rounds[-1]["gate"]
        item = {"agent": self.agent, "kind": "arena_rounds", "at": self.now(), "run": self.run_id, "stopped": stopped,
                "rounds": len(rounds), "gate_won": last["won"], "gate_played": last["played"],
                "needs": self.trust["wins"], "quick": self.quick, "fact_checks": self.facts, "lost": last["lost"][:3],
                "reflection": self.reflection_rows(rounds),
                "line": f"The Arena ran {len(rounds)} round{'' if len(rounds) == 1 else 's'} and stopped, {stopped}: "
                        f"{last['won']} of {last['played']} held-out matches won in the last, {self.trust['wins']} needed."}
        return self._write_item(item)

    def stuck_item(self, rounds):
        """The stuck point as a Morning page item, written next to the database."""
        last = rounds[-1]["gate"]
        item = {"agent": self.agent, "kind": "arena_stuck", "at": self.now(), "run": self.run_id,
                "rounds": len(rounds), "gate_won": last["won"], "gate_played": last["played"],
                "needs": self.trust["wins"], "fact_checks": self.facts, "lost": last["lost"][:3],
                "line": f"The Arena is stuck: {last['won']} of {last['played']} held-out matches won after "
                        f"{len(rounds)} rounds, {self.trust['wins']} needed, no gain in the last {NO_GAIN_ROUNDS}."}
        if any("reflection" in r for r in rounds):
            item["reflection"] = self.reflection_rows(rounds)
        return self._write_item(item)

    def _write_item(self, item):
        """Write the item with the run's seal (kit/seal.py), keyed in the same folder, so Morning.gate
        can tell it from one written by hand."""
        self.reports.mkdir(parents=True, exist_ok=True)
        seal.sign(item, self.reports)
        path = self.reports / f"arena-{self.agent}-{self.run_id}.json"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        item["file"] = path.name
        return item


ARENA_SUFFIX = ".arena"
SIDE_FILES = ("-wal", "-shm", "-journal")


def _file_id(path):
    """(st_dev, st_ino) of the file at path, following links; None when there is none."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino


def _failed_untried(old):
    """The lessons of the last run's copy at old that failed the eval gate, never had a trial and
    still wait (DECISIONS item 50), each as ({column: value}, {exam column: value}), oldest first.
    Nothing to carry when old is not a regular file or not a database; Refused when it is a
    database that cannot be read now (another run holding it)."""
    try:
        st = os.lstat(old)
    except OSError:
        return []
    if not stat.S_ISREG(st.st_mode):
        return []
    try:
        c = sqlite3.connect(str(old), timeout=5)
        try:
            c.row_factory = sqlite3.Row
            have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"lessons", "lesson_exams"} <= have:
                return []
            tried = "AND l.id NOT IN (SELECT lesson_id FROM trials)" if "trials" in have else ""
            rows = c.execute("SELECT l.id FROM lessons l JOIN lesson_exams e ON e.lesson_id = l.id "
                             f"WHERE l.state = 'waiting' AND e.passed = 0 AND l.yes_at IS NULL {tried} "
                             "ORDER BY l.id").fetchall()
            out = []
            for r in rows:
                les = dict(c.execute("SELECT * FROM lessons WHERE id = ?", (r[0],)).fetchone())
                exam = dict(c.execute("SELECT * FROM lesson_exams WHERE lesson_id = ?", (r[0],)).fetchone())
                out.append((les, exam))
            return out
        finally:
            c.close()
    except sqlite3.OperationalError as e:
        raise Refused(f"the last run's copy at {old} could not be read ({e}); is another Arena run using it?") from None
    except sqlite3.DatabaseError:
        return []  # not a database: it holds no lesson to carry


def _carry(copy, carried):
    """Write the carried lessons into the new copy, each as a new lesson with its exam row, unless
    the copy already holds a lesson of that agent with the same words."""
    from engine import exam as exam_mod
    from engine import lessons as lessons_mod
    from kit.db import Db
    d = Db(str(copy))
    try:
        d.script(lessons_mod.SCHEMA)
        exam_mod.ensure(d)
        with d.tx() as c:
            les_cols = {r[1] for r in c.execute("PRAGMA table_info(lessons)")} - {"id", "source_lesson_id"}
            exam_cols = {r[1] for r in c.execute("PRAGMA table_info(lesson_exams)")} - {"lesson_id"}
            for les, exam in carried:
                if c.execute("SELECT 1 FROM lessons WHERE agent = ? AND text = ?",
                             (les["agent"], les["text"])).fetchone() is not None:
                    continue
                cols = [k for k in les if k in les_cols]
                new_id = c.execute(f"INSERT INTO lessons ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                   [les[k] for k in cols]).lastrowid
                cols = [k for k in exam if k in exam_cols]
                c.execute(f"INSERT INTO lesson_exams (lesson_id, {', '.join(cols)}) "
                          f"VALUES (?, {', '.join('?' * len(cols))})", [new_id, *(exam[k] for k in cols)])
    finally:
        d.close()


def arena_copy(db):
    """Copy the live database at db to the Arena's own, <db>.arena beside it, through SQLite's
    backup (a whole, consistent copy while the live agent keeps writing), replacing the last run's
    copy and its side files. Returns the copy's path. The live database is only read.

    Refused, before anything is removed, when the copy's name or one of its side files is the live
    database or one of its side files under another name (a link either way). The new copy is made
    as a new file (O_EXCL and O_NOFOLLOW, mode 0600), so a link planted at its name is never written
    through. The lessons of the last copy that failed the eval gate, never had a trial and still
    wait are carried into the new copy with their exam rows (DECISIONS item 50), so a line refused
    in one run is not written and passed in the next."""
    live = Path(db)
    copy = live.with_name(live.name + ARENA_SUFFIX)
    live_ids = {i for i in (_file_id(p) for p in (live, *(live.with_name(live.name + s) for s in SIDE_FILES)))
                if i is not None}
    if _file_id(live) is None:
        raise Refused(f"the database at {db} could not be copied for the Arena: no file there")
    olds = (copy, *(copy.with_name(copy.name + s) for s in SIDE_FILES))
    for p in olds:
        if _file_id(p) in live_ids:
            raise Refused(f"the Arena's copy {p} is the live database under another name; remove that link first")
    carried = _failed_untried(copy)
    for p in olds:
        if p.is_symlink() or p.exists():
            p.unlink()
    try:
        fd = os.open(copy, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as e:
        raise Refused(f"the Arena's copy {copy} could not be made as a new file: {e}") from None
    try:
        os.fchmod(fd, 0o600)
        made = os.fstat(fd)
        try:
            src = sqlite3.connect(f"{live.resolve().as_uri()}?mode=ro", uri=True)
            try:
                if _file_id(copy) != (made.st_dev, made.st_ino) or os.path.islink(copy):
                    raise Refused(f"the Arena's copy {copy} was replaced while it was made")
                if _file_id(live) == (made.st_dev, made.st_ino):
                    raise Refused(f"the Arena's copy {copy} is the live database under another name")
                dst = sqlite3.connect(str(copy))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            if carried:
                _carry(copy, carried)
        except sqlite3.Error as e:
            raise Refused(f"the database at {db} could not be copied for the Arena: {e}") from None
    finally:
        os.close(fd)
    return copy


def state_dir(db):
    """The Arena's folder for an agent: its database's own folder, as the night reports."""
    return Path(db).resolve().parent


STUDY_WINDOW = re.compile(r"night study of [^,]*, cases from (\d{1,2}) ([A-Za-z]{3}) (\d{4}) to (\d{1,2}) ([A-Za-z]{3}) (\d{4})")
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                                      "Dec"), 1)}


def _study_days(source):
    """(first day, last day) of the window a night study's source line names (engine/study.py
    writes "night study of <agent>, cases from 01 Oct 2026 to 03 Oct 2026: ..."), or None."""
    m = STUDY_WINDOW.match(source or "")
    if m is None:
        return None
    try:
        return tuple(datetime.date(int(m[3 * k + 3]), MONTHS[m[3 * k + 2]], int(m[3 * k + 1])) for k in (0, 1))
    except (KeyError, ValueError):
        return None


def history_lessons(db):
    """The ids of the lessons, any agent's and in any state, sourced from history rows: rows a
    business's past was imported as (reflection/importer.py; detail "history": true). An Arena case
    is marked "history" too, so a trial never counts it, but it says "arena": true and was earned
    in the Arena, so it is not one of them. A lesson is sourced from history rows when its source
    line names an imported case, when it is a night study's lesson ("night study of ...") whose
    window reaches a day with an imported row (the study read those cases even when its line
    names only the first few, or none, as an idea's does; a window that cannot be read counts as
    reaching them), or when it was adapted or borrowed from such a lesson."""
    with db.tx() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"trace", "lessons"} <= tables:
            return []
        rows = c.execute("SELECT case_id, at, detail FROM trace WHERE detail LIKE '%history%'").fetchall()
        lessons = c.execute("SELECT id, source, source_lesson_id FROM lessons ORDER BY id").fetchall()
    cases, days = set(), set()
    for case_id, at, detail in rows:
        try:
            d = json.loads(detail)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("history") is True and d.get("arena") is not True:
            cases.add(str(case_id))
            days.add(datetime.datetime.fromtimestamp(float(at), datetime.timezone.utc).date())
    if not cases:
        return []
    named = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(x) for x in sorted(cases)) + r")(?![\w-])")
    found = set()
    for lid, source, _ in lessons:
        source = source or ""
        window = _study_days(source) if source.startswith("night study of ") else False
        if named.search(source) or window is None or (window and any(window[0] <= d <= window[1] for d in days)):
            found.add(lid)
    grew = True
    while grew:  # a lesson adapted or borrowed from one of them carries it on
        grew = False
        for lid, _, from_id in lessons:
            if from_id in found and lid not in found:
                found.add(lid)
                grew = True
    return sorted(found)


def past_wins(state):
    """The won matches saved in state, oldest first."""
    path = Path(state) / MATCHES_FILE
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            m = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(m, dict) and m.get("won") is True and m.get("turns"):
            out.append(m)
    return out


def next_step(rep):
    """The next step of a run that stopped at the cap, in one line; "" otherwise. The quick run's own
    limit says to run without --quick; the day's cap says when the count starts again (Cairo
    midnight) and that --cap raises it. A count file that cannot be read has its own line."""
    c = rep.get("calls") or {}
    if rep.get("stopped") != CAP or c.get("problem"):
        return ""
    if c.get("run_limit") is not None and c.get("run_used", 0) >= c["run_limit"]:
        return (f"the quick run stops at {c['run_limit']} model calls; run it again without --quick for a full run "
                f"(the day's cap is {c['cap']})")
    try:
        reset = (datetime.date.fromisoformat(c["day"]) + datetime.timedelta(days=1)).isoformat()
    except (KeyError, TypeError, ValueError):
        reset = "the next Cairo day"
    return (f"the day's count of {c.get('cap')} model calls starts again at 00:00 Cairo time on {reset}; to go on "
            f"now, run again with a higher --cap (now {c.get('cap')})")


def text(rep):
    lines = [f"Arena run {rep['run']} for {rep['agent']}: stopped, {rep['stopped']}.",
             f"  trust level: {rep['trust']['wins']} of {rep['trust']['matches']} held-out matches; "
             f"fact checks {'on' if rep['fact_checks'] else 'off'}",
             f"  cards: {len(rep['training_cards'])} to train on, held out {', '.join(rep['held_out_cards'])}"]
    for r in rep["rounds"]:
        t, g = r["training"], r["gate"]
        lines.append(f"  round {r['round']}: training {t['won']} of {t['played']} won, {len(t['cases'])} cases to "
                     f"Reflection; gate {g['won']} of {g['played']} won")
        for lost in g["lost"][:3]:
            lines.append(f"    lost {lost['card']}: {lost['why']} (turn {lost['quote']['turn']}, "
                         f"{lost['quote']['who']}: \"{lost['quote']['text']}\")")
        if r.get("reflection") is not None:
            from arena import rounds as rounds_mod
            got = r["reflection"]
            lines.append("    Reflection " + rounds_mod.line(got))
            for one in got.get("lessons") or []:
                state = ("handed on" if one["handed"] else "passed, waits for a yes" if one["waits_for_yes"]
                         else "passed, not handed" if one["passed"] else f"refused: {one['why'] or 'failed the gate'}")
                counts = "" if not one.get("gate") else f" ({one['gate']['fixed']} fixed, {one['gate']['broke']} broke)"
                lines.append(f"      lesson {one['lesson_id']} ({one['risk']} risk): {state}{counts}")
            for note in (got.get("notes") or [])[:3]:
                lines.append(f"      note: {note}")
    if rep.get("error"):
        lines.append(f"  stopped by a model error: {rep['error']}; that match was dropped, not counted as lost")
    c = rep["calls"]
    lines.append(f"  model calls on {c['day']}: {c['used']} of {c['cap']}")
    if c.get("run_limit") is not None:
        lines.append(f"  quick run: {c['run_used']} of at most {c['run_limit']} model calls in this run")
    if c.get("problem"):
        lines.append(f"  {c['problem']}; it counts as the cap reached until it is fixed or removed")
    step = next_step(rep)
    if step:
        lines.append(f"  next: {step}")
    rp = rep.get("replay")
    if rp is not None and rp.get("not_run"):
        lines.append(f"  replay not run: {rp['not_run']}")
    elif rp is not None:
        skipped = "; ".join(f"{why} {n}" for why, n in sorted(rp["skipped"].items()))
        lines.append(f"  replay of real lost chats: {rp['won']} of {rp['played']} won, {len(rp['cases'])} cases to "
                     f"Reflection" + (f"; skipped: {skipped}" if skipped else "")
                     + ("; stopped at the model call cap" if rp["stopped"] == CAP else "")
                     + (f"; stopped by a model error: {rp.get('error', '')}" if rp["stopped"] == MODEL_ERROR else ""))
        for lost in rp["lost"][:3]:
            lines.append(f"    lost chat {lost['chat']} ({lost['card']}): {lost['why']} (turn {lost['quote']['turn']}, "
                         f"{lost['quote']['who']}: \"{lost['quote']['text']}\")")
    if rep.get("pool"):
        p = rep["pool"]
        lines.append(f"  practice customers grown from real chats: {p['grown_cards']} cards from {p['items']} chats"
                     + (f", shared by {', '.join(p['siblings'])}" if p["siblings"] else ""))
    if rep.get("stuck"):
        lines.append(f"  stuck point for the Morning page: {rep['stuck']['file']}")
    if rep.get("item"):
        lines.append(f"  rounds for the Morning page: {rep['item']['file']}")
    return "\n".join(lines)


def reflection_models():
    """The night study's Meta models between rounds, as reflection/night.py has them: the proposer,
    the tagger and the idea part on the study route, the fit check, the adapter and the risk judge on
    Muse Spark Open, the exam on Muse Spark Open, and the quick note's writer (arena/notes.py) on Muse
    Spark Open as fast reflection has it. Refused, naming the variable, when a key is missing."""
    from kit import model as model_mod
    from reflection import fast as fast_mod, judge as judge_mod, night, study as parts
    try:
        missing = night.missing_keys()
    except night.Refused as e:
        raise Refused(f"the night study between rounds cannot run: {e}") from None
    if missing:
        raise Refused("the night study between rounds needs " + ", ".join(missing) + " in env or .env")
    return {"study": model_mod.Model(timeout=parts.TIMEOUT, route=parts.study_route()),
            "open": model_mod.Model(timeout=judge_mod.TIMEOUT), "exam": model_mod.Model(),
            "notes": model_mod.Model(timeout=fast_mod.TIMEOUT, route=model_mod.OPEN)}


def quick_notes(plug, calls, model):
    """The run's quick notes (arena/notes.py) for the Sales agent: fast reflection's writer on model,
    each call taken from calls, with fast reflection's never marks and the demo store's own words."""
    from arena import notes as notes_mod
    from reflection import fast as fast_mod

    def known():  # the demo store's catalogue and places, read with no store keys, as the matches see it
        with match_mod.demo_store():
            return fast_mod.known()
    return notes_mod.RunNotes(plug, fast_mod.Writer(model=calls.model(model)), never=fast_mod.NEVER, known=known)


def main(argv=None, *, agent_model=None, customer_model=None, reflection=None):
    """reflection: for tests, the models of the step between rounds ({"study", "open", "exam"}) and
    optionally "examiner" (arena/rounds.py Between); a real run makes them (reflection_models)."""
    ap = argparse.ArgumentParser(prog="arena/run.py", description="The Arena: persona matches and the gate.")
    ap.add_argument("--cards", default=str(DEFAULT_CARDS), help="a folder of card files: plain files, no links")
    ap.add_argument("--matches", type=int, default=10, help="training matches a round")
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    ap.add_argument("--held-out", default="", help="card ids held out, comma separated")
    ap.add_argument("--trust", default=None, help="the trust levels file, outside the repo")
    ap.add_argument("--customer-prompt", default=None, help="the tuned customer prompt, outside the repo")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="model calls a day")
    ap.add_argument("--exam-cap", type=int, default=None, help="model calls one lesson's exam may take between rounds")
    ap.add_argument("--state", default=None, help="the folder for the call count and the matches, for a run with no --db")
    ap.add_argument("--db", default=None, help="the Sales agent's database: the Arena practises on its copy, <db>.arena beside it")
    ap.add_argument("--replay", default=None, help="the persona build's replay.jsonl: outside the repo, or the cleaned set arena/real/replay.jsonl")
    ap.add_argument("--replay-max", type=int, default=replay_mod.MAX_REPLAYS, help="real lost chats to replay")
    ap.add_argument("--fact-checks", choices=("on", "off"), default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quick", action="store_true", help="a short run for judges: one training match, a gate of one"
                    f" match, at most {QUICK_CALLS} model calls")
    args = ap.parse_args(argv)
    if args.quick:
        args.matches, args.rounds = 1, 1
        if not (args.db or args.state):
            args.state = str(QUICK_STATE)
    if agent_model is None or customer_model is None:
        from kit import env, model as model_mod
        env.load()
        if not model_mod.has_key():
            print(model_mod.NO_KEY_LINE, file=sys.stderr)
            return 2
    db, live = None, []
    try:
        cards = load_cards(args.cards)
        if args.replay_max < 1:
            raise Refused("--replay-max must be at least 1")
        if args.exam_cap is not None and args.exam_cap < 1:
            raise Refused("--exam-cap must be at least 1")
        planned = replay_mod.plan(replay_mod.load(args.replay), cards, args.replay_max) if args.replay else None
        trust = dict(QUICK_TRUST) if args.quick else load_trust(args.trust)
        prompt = match_mod.load_prompt(args.customer_prompt)
        if args.db and args.state:
            raise Refused("--state is for a run with no database; with --db the Arena keeps its files next to it")
        if not (args.db or args.state):
            raise Refused("name --db (the Sales agent's database) or --state (a folder for a run with no database)")
        state = state_dir(args.db) if args.db else Path(args.state)
        if paths.inside_repo(state) and not paths.within(state, paths.DATA):
            raise Refused("the Arena's files would sit inside the repo, where real chat lines and the trust level"
                          " could be committed; keep --db or --state outside it or under data/ (DECISIONS item 17)")
        calls = Calls(state / CALLS_FILE, args.cap, limit=QUICK_CALLS if args.quick else None)
        from arena import grow
        practice = grow.for_state(state, AGENT)  # the owner's practice customers, of this agent's kind
        if args.db and not Path(args.db).is_file():
            raise Refused(f"no database at {args.db}")
        made = agent_model is None or customer_model is None  # a real run: the models are made here
        between_models = None
        if args.db and args.rounds > 1:  # the night study and the gate between rounds (arena/rounds.py)
            if reflection is not None:
                between_models = dict(reflection)
            elif made:
                between_models = reflection_models()
            else:
                raise Refused("the step between rounds needs its models: give reflection with the agent's models")
        if made:
            agent_model = agent_model or model_mod.Model()
            customer_model = customer_model or model_mod.Model()
        learn, lessons, between, before_match, notes = None, None, None, None, None
        if args.db:
            from kit.db import Db
            from arena import learn as learn_mod, rounds as rounds_mod
            from reflection import PLUG as SALES_PLUG
            from reflection.exam import _Lessons
            from reflection.lessons import Lessons as SalesLessons
            db = Db(str(arena_copy(args.db)))  # the Arena's own copy; the live database is only read
            mined = history_lessons(db)
            if mined:
                raise Refused(f"the database at {args.db} holds {len(mined)} lesson{'s' if len(mined) > 1 else ''} "
                              f"sourced from history rows (lesson {', '.join(map(str, mined[:10]))}"
                              f"{' and more' if len(mined) > 10 else ''}). Every agent starts from zero and earns "
                              "its lessons in the Arena (DECISIONS item 20): start from a database with no lesson "
                              "mined from imported history")
            learn = lambda m, judged, mid: learn_mod.to_case(db, m, judged, mid)  # noqa: E731
            # the agent's kept lessons, handed as the exam hands them, then those passed between rounds
            live_path = args.db
            pool = rounds_mod.Pool(SalesLessons(db), hotfixes=lambda: rounds_mod.live_hotfixes(  # read only
                live_path, SALES_PLUG.agent))
            before_match = pool.refresh
            lessons = _Lessons(pool, None)
            if between_models is not None:
                exam_cap = rounds_mod.EXAM_CAP if args.exam_cap is None else args.exam_cap
                # a given exam (tests) brings its own full exam, or none; the real one runs the full exam before live
                full = between_models.pop("full", None if "examiner" in between_models else rounds_mod.full_examiner)
                examiner = between_models.pop("examiner", functools.partial(rounds_mod.real_examiner, cap=exam_cap))
                notes_model = between_models.pop("notes", None)  # the quick note's writer; none, no notes
                def live_lessons():  # opened at the first lesson that passes the gate, not before
                    live.append(Db(args.db))
                    return SalesLessons(live[0])
                between = rounds_mod.Between(db, SALES_PLUG, calls=calls, state=state, pool=pool,
                                             agent_model=agent_model, customer_model=customer_model,
                                             models=between_models, examiner=examiner, live=live_lessons,
                                             full=full)
                learn = between.learn
                if notes_model is not None:
                    notes = quick_notes(SALES_PLUG, calls, notes_model)
        arena = Arena(cards, agent_model=agent_model, customer_model=customer_model, calls=calls, trust=trust,
                      prompt=prompt, held_out=[x for x in args.held_out.split(",") if x.strip()],
                      prompt_file=Path(args.customer_prompt).expanduser().resolve() if args.customer_prompt else None,
                      matches=args.matches, rounds=args.rounds,
                      fact_checks=None if args.fact_checks is None else args.fact_checks == "on", seed=args.seed,
                      learn=learn, between=between, lessons=lessons, state=state, pool=practice,
                      before_match=before_match, notes=notes)
        arena.quick = bool(args.quick)
        rep = arena.run()
        if planned is not None:
            rep["replay"] = (arena.replay(*planned) if rep["stopped"] == PASSED
                             else {"not_run": "the persona gate has not passed"})
            rep["calls"]["used"] = calls.count
            if calls.problem:
                rep["calls"]["problem"] = calls.problem
        if practice.changed:
            practice.save()
        rep["pool"] = practice.summary()
    except (Refused, hist.Refused, match_mod.PromptRefused, OSError, ValueError, OverflowError, RecursionError) as e:
        print(f"Not run: {e}", file=sys.stderr)
        return 2
    finally:
        for d in [db] + live:
            if d is not None:
                d.close()
    print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else text(rep))
    return 0 if rep["stopped"] == PASSED else 1


if __name__ == "__main__":
    sys.exit(main())
