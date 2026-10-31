"""The Arena loop and its gate (new, 2026-10-30; DECISIONS items 4, 7, 14, 17, 18).

    python3 -I arena/run.py --cards DIR --matches N [--rounds 5] [--held-out persona-03,persona-07]
        [--trust FILE] [--customer-prompt FILE] [--cap 1000] [--state DIR] [--db PATH]
        [--replay FILE [--replay-max 10]] [--fact-checks on|off] [--seed 0] [--json]

Each round: N training matches, each card drawn by its arena_weight from the cards the agent may
train on, then the gate: the agent's trust level of matches (its "matches") drawn the same way
from the held-out cards that can buy, which never train it (their losses go nowhere). The gate
passes at the level's "wins". With no --held-out, the held-out cards are a seeded share of the
cards that can buy, spread over their worries; a card that will not buy is never a gate match.
With --db the Sales agent plays every match with that database's kept lessons handed, as the
exam hands them, so the gate tests the agent with what it has learned, not the bare seed. A lost training match becomes a case the night study reads (arena/learn.py)
when --db names the Sales agent's database. Every agent starts from zero and earns its lessons
in the Arena (DECISIONS item 20), so a database holding a lesson sourced from history rows (a
business's past imported by reflection/importer.py) is refused: see history_lessons.

Trust levels are per agent and stay out of the repo (DECISIONS item 17): --trust names a JSON file
outside it, shaped like {"sales": {"matches": 4, "wins": 3, "zero_failed_checks": true}} (stand-in
numbers, not a real level). With none, the public placeholder below asks every gate match won. zero_failed_checks (on unless the level says
false; --fact-checks overrides it): a match with any failed fact check is lost (arena/verdict.py).

The loop stops on a pass, at the model call cap, at a model that does not answer (that match is
dropped as a capped one is, never counted as lost; the report names the error), or after
NO_GAIN_ROUNDS rounds in a row with no more gate wins than the best round before; then the stuck point is written next to the database
(or in --state) as arena-<agent>-<time>.json, an item for the Morning page. between(round), when
given (a library hook, for the night study between rounds), runs before each round after the first.

--replay names the persona build's replay.jsonl (outside the repo): once the gate passes, the
Sales agent replays up to --replay-max real lost chats, each from the customer's real opening
against the persona card with the chat's worry (arena/replay.py), scored with the same fact
checks and verdict and counted against the same cap. A lost replay becomes a case too. The demo
replays the set built from the made-up chats only.

Model calls: every call of the agent and of the customer counts against the cap a day (Cairo
day), default 1000, saved in arena-calls.json after each call under a lock (arena-calls.lock), so
the count holds across runs and two runs at once share one cap. A count file that is there but
cannot be read, or holds no whole count for today, counts as the cap reached (Calls.problem says
why, and so does the report) until it is fixed or removed, so a broken count never starts at 0.
Every match is saved in arena-matches.jsonl with its verdict: the past wins the eval gate
reruns (arena/gate.py). Both files sit next to the agent's database (--db), with the stuck
item, so the gate reads that agent's own wins and nothing else. --state names their folder
only for a run with no database (its wins feed no gate); one of the two is needed.
"""
import argparse
import datetime
import fcntl
import json
import os
import random
import re
import sys
import time
import zoneinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I
    sys.path.insert(0, str(ROOT))

from arena import factcheck, match as match_mod, paths, replay as replay_mod, verdict  # noqa: E402

AGENT = "sales"
DEFAULT_CARDS = ROOT / "demo" / "personas" / "cards"
CALLS_FILE, MATCHES_FILE = "arena-calls.json", "arena-matches.jsonl"
DEFAULT_CAP = 1000
DEFAULT_ROUNDS = 5
NO_GAIN_ROUNDS = 2
HELD_OUT_SHARE = 0.3
PUBLIC_TRUST = {"matches": 10, "wins": 10, "zero_failed_checks": True}
TZ = "Africa/Cairo"
PASSED, CAP, STUCK, ROUNDS, MODEL_ERROR = "passed", "cap", "stuck", "rounds", "model_error"


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

    def __init__(self, path, cap=DEFAULT_CAP, day=None):
        self.path, self.cap = Path(path), int(cap)
        if self.cap < 1:
            raise Refused("--cap must be at least 1")
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
        except ValueError:
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
        return Counted()


def load_cards(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise Refused(f"no cards folder at {folder}")
    cards = []
    for p in sorted(folder.glob("persona-*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
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


def split(cards, held_out=None, share=HELD_OUT_SHARE, seed=0):
    """(training cards, held-out cards). held_out: card ids; else a seeded share of the cards that
    can buy, one card a worry in a seeded worry order, then a second round, so the gate is spread
    over worries. A card that will not buy is never held out by the draw: the gate only plays cards
    that can buy (Arena.gate_cards), so a held-out card that cannot would only be lost to training."""
    ids = [c["id"] for c in cards]
    if held_out:
        unknown = sorted(set(held_out) - set(ids))
        if unknown:
            raise Refused(f"held-out cards not found: {', '.join(unknown)}")
        held = set(held_out)
    else:
        winnable = [c for c in cards if can_buy(c)]
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
    def __init__(self, cards, *, agent_model, customer_model, calls, trust=None, prompt=match_mod.GENERIC_PROMPT,
                 prompt_file=None, held_out=None, matches=10, rounds=DEFAULT_ROUNDS, fact_checks=None, seed=0,
                 learn=None, between=None, lessons=None, state, reports=None, now=time.time):
        """prompt_file: where the customer prompt was read from (None for the generic one), saved
        with each match beside the prompt's fingerprint, so the eval gate can read it again."""
        self.train, self.held = split(cards, held_out, seed=seed)
        self.gate_cards = [c for c in self.held if can_buy(c)]  # a card that will not buy is no test of the agent
        self.calls = calls
        self.agent_model, self.customer_model = calls.model(agent_model), calls.model(customer_model)
        self.trust = trust or dict(PUBLIC_TRUST)
        self.facts = self.trust.get("zero_failed_checks", True) if fact_checks is None else bool(fact_checks)
        self.prompt, self.matches, self.rounds, self.seed = prompt, int(matches), int(rounds), seed
        self.prompt_sha = match_mod.prompt_sha(prompt)
        self.prompt_file = None if prompt_file is None else str(prompt_file)
        self.learn, self.between, self.lessons = learn, between, lessons
        self.halt, self.error = CAP, ""  # why the last match was dropped: the cap, or a model error
        self.state = Path(state)
        self.reports = Path(reports) if reports is not None else self.state
        self.now = now
        self.run_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now()))
        self.rng = random.Random(f"draw:{seed}:{self.run_id}")
        if self.matches < 1 or self.rounds < 1:
            raise Refused("--matches and --rounds must be at least 1")

    def play(self, card, match_id, *, opening=None, lessons=None, replay=None):
        """One match and its verdict, saved; None when the cap stopped it (the match is dropped).
        replay: the replay chat's id, saved on the match."""
        try:
            m = match_mod.play(card, agent_model=self.agent_model, customer_model=self.customer_model,
                               prompt=self.prompt, lessons=lessons or self.lessons, seed=match_id,
                               opening=opening, checker=factcheck.check, stop=verdict.closed)
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

    def run(self):
        rounds, best, flat, stopped = [], None, 0, ROUNDS
        for r in range(1, self.rounds + 1):
            if r > 1 and self.between is not None:
                self.between(r - 1)
            one = {"round": r, "training": {"played": 0, "won": 0, "cases": []},
                   "gate": {"played": 0, "won": 0, "lost": []}}
            rounds.append(one)
            for k in range(1, self.matches + 1):
                card = draw(self.train, self.rng)
                out = self.play(card, f"{self.run_id}-r{r}-t{k:02d}")
                if out is None:
                    return self._report(rounds, self.halt)
                m, judged = out
                one["training"]["played"] += 1
                one["training"]["won"] += judged["won"]
                if not judged["won"] and self.learn is not None:
                    one["training"]["cases"].append(self.learn(m, judged, m["id"]))
            for k in range(1, self.trust["matches"] + 1):
                card = draw(self.gate_cards, self.rng)
                out = self.play(card, f"{self.run_id}-r{r}-g{k:02d}")
                if out is None:
                    return self._report(rounds, self.halt)
                m, judged = out
                one["gate"]["played"] += 1
                one["gate"]["won"] += judged["won"]
                if not judged["won"]:
                    one["gate"]["lost"].append({"card": m["card"], "why": judged["why"], "quote": judged["quote"]})
            wins = one["gate"]["won"]
            if wins >= self.trust["wins"]:
                return self._report(rounds, PASSED)
            flat = flat + 1 if best is not None and wins <= best else 0
            best = wins if best is None else max(best, wins)
            if flat >= NO_GAIN_ROUNDS:
                stopped = STUCK
                break
        return self._report(rounds, stopped)

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
        rep = {"agent": AGENT, "run": self.run_id, "stopped": stopped, "trust": self.trust, "fact_checks": self.facts,
               "training_cards": [c["id"] for c in self.train], "held_out_cards": [c["id"] for c in self.held],
               "rounds": rounds, "calls": {"day": self.calls.day, "used": self.calls.count, "cap": self.calls.cap}}
        if self.calls.problem:
            rep["calls"]["problem"] = self.calls.problem
        if stopped == MODEL_ERROR:
            rep["error"] = self.error
        if stopped == STUCK:
            rep["stuck"] = self.stuck_item(rounds)
        return rep

    def stuck_item(self, rounds):
        """The stuck point as a Morning page item, written next to the database."""
        last = rounds[-1]["gate"]
        item = {"agent": AGENT, "kind": "arena_stuck", "at": self.now(), "run": self.run_id,
                "rounds": len(rounds), "gate_won": last["won"], "gate_played": last["played"],
                "needs": self.trust["wins"], "lost": last["lost"][:3],
                "line": f"The Arena is stuck: {last['won']} of {last['played']} held-out matches won after "
                        f"{len(rounds)} rounds, {self.trust['wins']} needed, no gain in the last {NO_GAIN_ROUNDS}."}
        self.reports.mkdir(parents=True, exist_ok=True)
        path = self.reports / f"arena-{AGENT}-{self.run_id}.json"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        item["file"] = path.name
        return item


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
        except ValueError:
            continue
        if isinstance(m, dict) and m.get("won") is True and m.get("turns"):
            out.append(m)
    return out


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
    if rep.get("error"):
        lines.append(f"  stopped by a model error: {rep['error']}; that match was dropped, not counted as lost")
    c = rep["calls"]
    lines.append(f"  model calls on {c['day']}: {c['used']} of {c['cap']}")
    if c.get("problem"):
        lines.append(f"  {c['problem']}; it counts as the cap reached until it is fixed or removed")
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
    if rep.get("stuck"):
        lines.append(f"  stuck point for the Morning page: {rep['stuck']['file']}")
    return "\n".join(lines)


def main(argv=None, *, agent_model=None, customer_model=None):
    ap = argparse.ArgumentParser(prog="arena/run.py", description="The Arena: persona matches and the gate.")
    ap.add_argument("--cards", default=str(DEFAULT_CARDS))
    ap.add_argument("--matches", type=int, default=10, help="training matches a round")
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    ap.add_argument("--held-out", default="", help="card ids held out, comma separated")
    ap.add_argument("--trust", default=None, help="the trust levels file, outside the repo")
    ap.add_argument("--customer-prompt", default=None, help="the tuned customer prompt, outside the repo")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="model calls a day")
    ap.add_argument("--state", default=None, help="the folder for the call count and the matches, for a run with no --db")
    ap.add_argument("--db", default=None, help="the Sales agent's database: lost training matches become cases")
    ap.add_argument("--replay", default=None, help="the persona build's replay.jsonl, outside the repo")
    ap.add_argument("--replay-max", type=int, default=replay_mod.MAX_REPLAYS, help="real lost chats to replay")
    ap.add_argument("--fact-checks", choices=("on", "off"), default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    db = None
    try:
        cards = load_cards(args.cards)
        if args.replay_max < 1:
            raise Refused("--replay-max must be at least 1")
        planned = replay_mod.plan(replay_mod.load(args.replay), cards, args.replay_max) if args.replay else None
        trust = load_trust(args.trust)
        prompt = match_mod.load_prompt(args.customer_prompt)
        if args.db and args.state:
            raise Refused("--state is for a run with no database; with --db the Arena keeps its files next to it")
        if not (args.db or args.state):
            raise Refused("name --db (the Sales agent's database) or --state (a folder for a run with no database)")
        state = state_dir(args.db) if args.db else Path(args.state)
        if paths.inside_repo(state) and not paths.within(state, paths.DATA):
            raise Refused("the Arena's files would sit inside the repo, where real chat lines and the trust level"
                          " could be committed; keep --db or --state outside it or under data/ (DECISIONS item 17)")
        calls = Calls(state / CALLS_FILE, args.cap)
        if agent_model is None or customer_model is None:
            from kit import env, model as model_mod
            env.load()
            agent_model = agent_model or model_mod.Model()
            customer_model = customer_model or model_mod.Model()
        learn, lessons = None, None
        if args.db:
            from kit.db import Db
            from arena import learn as learn_mod
            from reflection.exam import _Lessons
            from reflection.lessons import Lessons as SalesLessons
            if not Path(args.db).is_file():
                raise Refused(f"no database at {args.db}")
            db = Db(args.db)
            mined = history_lessons(db)
            if mined:
                raise Refused(f"the database at {args.db} holds {len(mined)} lesson{'s' if len(mined) > 1 else ''} "
                              f"sourced from history rows (lesson {', '.join(map(str, mined[:10]))}"
                              f"{' and more' if len(mined) > 10 else ''}). Every agent starts from zero and earns "
                              "its lessons in the Arena (DECISIONS item 20): start from a database with no lesson "
                              "mined from imported history")
            learn = lambda m, judged, mid: learn_mod.to_case(db, m, judged, mid)  # noqa: E731
            lessons = _Lessons(SalesLessons(db), None)  # the agent's kept lessons, handed as the exam hands them
        arena = Arena(cards, agent_model=agent_model, customer_model=customer_model, calls=calls, trust=trust,
                      prompt=prompt, held_out=[x for x in args.held_out.split(",") if x.strip()],
                      prompt_file=Path(args.customer_prompt).expanduser().resolve() if args.customer_prompt else None,
                      matches=args.matches, rounds=args.rounds,
                      fact_checks=None if args.fact_checks is None else args.fact_checks == "on", seed=args.seed,
                      learn=learn, lessons=lessons, state=state)
        rep = arena.run()
        if planned is not None:
            rep["replay"] = (arena.replay(*planned) if rep["stopped"] == PASSED
                             else {"not_run": "the persona gate has not passed"})
            rep["calls"]["used"] = calls.count
            if calls.problem:
                rep["calls"]["problem"] = calls.problem
    except (Refused, match_mod.PromptRefused, OSError, ValueError, RecursionError) as e:
        print(f"Not run: {e}", file=sys.stderr)
        return 2
    finally:
        if db is not None:
            db.close()
    print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else text(rep))
    return 0 if rep["stopped"] == PASSED else 1


if __name__ == "__main__":
    sys.exit(main())
