"""A plug: what one agent declares, in one JSON file, so the engine can learn from its work.

The engine keeps no list of its own. It takes only the actions, results, causes and
stages a plug declares, and refuses the rest, so a new agent needs a new plug file
and no change to the engine.

Keys (unknown keys are refused, so a typo never passes quietly):
  agent    the agent's name: lowercase letters, digits and _, starting with a letter, at most 41
           characters (AGENT_NAME, the pool's kind in arena/grow.py takes the same).
  kind     optional, the kind of agent, named as agent is (default: the agent's name). Agents of
           one kind that one owner runs share the practice cases their real work grew
           (arena/grow.py, DECISIONS item 51).
  owner    optional, the owner's name, named as agent is. The agent shares its owner's practice
           cases only when the folder above its own holds owner.json naming the same owner
           (arena/grow.py owner_of); with no owner, or another, its own folder is its owner's.
  about    optional, one plain line on what the agent does.
  case     one plain line: what one case is for this agent.
  fields   tags for the field the agent works in. Lessons carry them, so an agent can
           later borrow a lesson from another agent in the same field.
  stages   the stages a case moves through. A lesson is tagged with some of them, or "all".
  actions  name: one plain line. What the agent does in a case. Each action is saved
           with the ids of the lessons it was given.
  results  name: {speed, after, about, shows_in_days}.
           speed fast: shows within a day. speed slow: the real result, days later.
           shows_in_days: optional, [least, most], about how long the result takes to show. Only
           shown and used by the simulator to time its made-up results; no day count ever settles
           a case or a trial (DECISIONS item 66). Older plugs carry it, and it still loads.
           after: the action this fast result ends; it is saved in the same row. A result
           without after (every slow one) comes on its own and attaches by case.
  causes   name: one plain line. Causes of a bad result that are not the agent's fault.
  source   {about, known_by}: what one source of a case is (who or what a case comes
           from), one plain line, and how the log knows it. known_by case: the case id
           names its source, so the log keeps the case id as the source of every row.
           known_by row: each action is saved with its source, and a result that comes on
           its own takes the source its case already has.
  harm     {results, about, serious}: the fast results that count as harm while a lesson is on
           trial (the stop rule). At least one, each a declared fast result. about,
           optional: one plain line, for example on harm that has no result yet. serious,
           optional: declared results, fast or slow, so serious that one case with a
           lesson on trial and one of them pings the person on the trial's card.
  decides  {good, bad}: the results that settle a case for a trial. good: the one that
           is good. bad: a list of the others, maybe empty. Each a declared result, fast
           or slow, none named twice. A case with none of them is pending, whatever its age,
           until one comes (study.settle, DECISIONS item 66): from a tool's webhook
           (channels/), from a tool's API on the night run (reflection/late.py), or
           from a person on the morning page or in an uploaded sheet. No timer closes a case.
  second_signal  optional, {good, bad}: results that follow a good case and are kept on
           it, never deciding it (DECISIONS item 66, Mohamed's call B): a fast result decides the
           case, and a slow one that comes days later shows how it held. good: one declared result; bad: a
           list, maybe empty; none of them named in decides, none named twice. A good case with
           none of them yet is still settled good and counted; the tool's webhook, its API
           and the morning page can add one, once a case, and it stays on that case. No
           pattern is counted by it (DECISIONS item 73): a night reads 2 days and it lands later.
  risk     {high: {about, words, patterns, tools}, low: {about}}: what is high risk in
           this business. words and patterns are {group: [...]}, so a match names its
           group. The code check looks for the words, patterns and tool names first; the
           judge reads the two about lines; unsure counts as high.
  trial    {fast, careful, holdback, worst_cost}: the two trial levels, fast and careful,
           both required, each {share, days}: a new trial gives the lesson in this share of
           cases (more than 0 and under 1) for this many days (a whole number, 1 or more).
           The owner sets them here in setup, and this file is their only home: the engine
           has no default for them. Which level a new trial takes is not set here: the
           level switch in the database decides it, careful until a person flips it
           (engine/switches.py).
           holdback: the share of cases that keep the old way after a trial keeps a
           lesson, so a lesson that does nothing is caught later; at least 0 and under 1,
           default 0.05 (1 in 20). worst_cost: the worst likely cost a kept lesson may
           have, as a share of cases that could lose the good result (0.02 is about 2 in
           100); 0 to 1, default 0.02. A person can move it for one lesson.
  slot     the line the lessons sit under in the agent's prompt.
  hands_over  optional, {agent: {about, kinds}}: the kinds of pattern in this agent's lost
           cases that are a matter for another agent, not for this one's lessons, and which
           agent each goes to (engine/handover.py). agent: the receiving agent's name, never
           this agent. about, optional: one plain line on what that agent can act on. kinds:
           {name: one plain line}, at least one; a kind name goes to one agent only.
"""
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

FAST, SLOW = "fast", "slow"
ALL = "all"  # the stage tag of a lesson that fits every stage
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
AGENT_NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")  # agent, kind and owner: a file name part in arena/grow.py
KEYS = {"agent", "kind", "owner", "about", "case", "fields", "stages", "actions", "results", "causes", "source", "harm",
        "decides", "risk", "trial", "slot", "exam", "hands_over", "second_signal"}
REQUIRED = {"agent", "case", "actions", "results", "causes", "source", "harm", "decides", "risk", "trial", "slot"}
LEVELS_WHY = "the owner sets both trial levels here, fast and careful, each {share, days}"
WHY = {  # what a missing key is for, said in the refusal
    "source": "what one source of a case is, and how the log knows it",
    "harm": "the fast results that count as harm while a lesson is on trial",
    "decides": "the results that settle a trial, and which one is good",
    "trial": LEVELS_WHY,
}
CASE, ROW = "case", "row"  # how the log knows a case's source
RESULT_KEYS = {"speed", "shows_in_days", "after", "about"}
HIGH_KEYS = {"about", "words", "patterns", "tools"}
FAST_LEVEL, CAREFUL = "fast", "careful"  # the two trial levels; careful is the switch's default
LEVEL_NAMES = (FAST_LEVEL, CAREFUL)
HOLDBACK, WORST_COST = 0.05, 0.02
GONE = {  # keys an older plug may still carry, refused with what replaced them, by where they sat
    "the plug": {"low_per_night": "there is no nightly cap; a low risk lesson goes on trial with no yes"},
    "trial": {k: "a trial's share and days sit in its two levels, fast and careful, each {share, days}"
              for k in ("share", "days")},
}


@dataclass(frozen=True)
class Result:
    name: str
    speed: str
    shows_in_days: tuple | None  # (least, most), or None when the plug gives none
    after: str | None
    about: str


@dataclass(frozen=True)
class Source:
    about: str
    known_by: str  # CASE or ROW


@dataclass(frozen=True)
class Harm:
    results: tuple
    about: str
    serious: tuple = ()


@dataclass(frozen=True)
class Decides:
    good: str
    bad: tuple


@dataclass(frozen=True)
class Risk:
    high_about: str
    low_about: str
    words: tuple     # (group, word) pairs
    patterns: tuple  # (group, regular expression) pairs
    tools: tuple


@dataclass(frozen=True)
class Level:
    share: float  # the share of cases given the lesson, more than 0 and under 1
    days: int     # how long the trial runs, whole days


@dataclass(frozen=True)
class Exam:
    """A plug's exam: the situations file (a path inside the plug's folder) and the names of the
    checks the agent's own code runs on what it did."""
    situations: Path
    checks: tuple


@dataclass(frozen=True)
class HandOver:
    """One receiving agent of a plug's hands_over: its name, what it can act on, and the kinds
    of pattern that go to it ({name: one plain line})."""
    agent: str
    about: str
    kinds: dict


@dataclass(frozen=True)
class Plug:
    agent: str
    case: str
    fields: tuple
    stages: tuple
    actions: dict
    results: dict
    causes: dict
    source: Source
    harm: Harm
    decides: Decides
    risk: Risk
    levels: dict  # {"fast": Level, "careful": Level}
    slot: str
    about: str = ""
    trial_holdback: float = HOLDBACK
    trial_worst_cost: float = WORST_COST
    exam: Exam | None = None  # the plug's exam (engine/exam.py); None when it has none
    kind: str = ""  # the kind of agent; the agent's name when the plug names none
    owner: str = ""  # the owner's name (arena/grow.py owner_of); empty when the plug names none
    hands_over: tuple = ()  # HandOver, one per receiving agent (engine/handover.py); () for none
    second_signal: Decides | None = None  # results kept on a good case, never deciding it

    def late(self):
        """The results a webhook, a tool's API or a person may add to a case later, as
        (deciding, second): the deciding results when one of them is slow (else ()), and the second
        signal's results (else ())."""
        deciding = (self.decides.good, *self.decides.bad)
        slow = any(self.results[r].speed == SLOW for r in deciding)
        second = () if self.second_signal is None else (self.second_signal.good, *self.second_signal.bad)
        return (deciding if slow else ()), second

    def action(self, name):
        """The action's line; ValueError when this plug does not declare it."""
        if name not in self.actions:
            raise ValueError(f"{self.agent} declares no action {name!r}")
        return self.actions[name]

    def level(self, name):
        """The Level of that name; ValueError when it is not fast or careful."""
        if name not in self.levels:
            raise ValueError(f"a trial level is {FAST_LEVEL} or {CAREFUL}, not {name!r}")
        return self.levels[name]

    def result(self, name):
        """The Result; ValueError when this plug does not declare it."""
        if name not in self.results:
            raise ValueError(f"{self.agent} declares no result {name!r}")
        return self.results[name]

    def cause(self, name):
        if name not in self.causes:
            raise ValueError(f"{self.agent} declares no cause {name!r}")
        return self.causes[name]

    def stage_tags(self, tags):
        """Sorted unique stage tags, each a declared stage or "all"; ValueError otherwise."""
        found = sorted({t.strip() for t in tags if isinstance(t, str) and t.strip()})
        if not found:
            raise ValueError("a lesson needs at least one stage tag")
        bad = [t for t in found if t != ALL and t not in self.stages]
        if bad:
            raise ValueError(f"{self.agent} declares no stage {bad[0]!r}")
        return found


def load(path):
    """Read a plug file. ValueError names the first thing wrong in it."""
    with open(Path(path), encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: not JSON: {e}") from None
    return from_dict(data, folder=Path(path).resolve().parent)


def from_dict(d, folder=None):
    """folder: where the plug file sits; the exam's situations path is read from there."""
    if not isinstance(d, dict):
        raise ValueError("a plug is one JSON object")
    _gone(d, "the plug")
    _keys(d, KEYS, REQUIRED, "the plug", WHY)
    agent = _name(d["agent"], "agent", AGENT_NAME)
    stages = tuple(_name(s, "stage") for s in _list(d.get("stages", []), "stages"))
    if ALL in stages:
        raise ValueError(f'"{ALL}" is kept for lessons that fit every stage')
    actions = _named_lines(d["actions"], "actions", empty=False)
    results = {}
    for name, r in _dict(d["results"], "results", empty=False).items():
        results[_name(name, "result")] = _result(name, r, actions)
    causes = _named_lines(d["causes"], "causes", empty=True)
    trial = _dict(d["trial"], "trial", empty=True)
    _gone(trial, "trial")
    _keys(trial, {*LEVEL_NAMES, "holdback", "worst_cost"}, set(LEVEL_NAMES), "trial",
          {name: LEVELS_WHY for name in LEVEL_NAMES})
    levels = {name: _level(trial[name], name) for name in LEVEL_NAMES}
    holdback = _number(trial.get("holdback", HOLDBACK), "trial holdback")
    worst = _number(trial.get("worst_cost", WORST_COST), "trial worst_cost")
    if not 0 <= holdback < 1:
        raise ValueError("trial holdback is at least 0 and under 1")
    if not 0 <= worst <= 1:
        raise ValueError("trial worst_cost is from 0 to 1")
    return Plug(agent=agent, case=_line(d["case"], "case"),
                fields=tuple(sorted({_name(f, "field") for f in _list(d.get("fields", []), "fields")})),
                stages=stages, actions=MappingProxyType(actions), results=MappingProxyType(results),
                causes=MappingProxyType(causes), source=_source(d["source"]), harm=_harm(d["harm"], results),
                decides=_decides(d["decides"], results), risk=_risk(d["risk"]),
                levels=MappingProxyType(levels), slot=_line(d["slot"], "slot"),
                about=_line(d["about"], "about") if "about" in d else "",
                trial_holdback=float(holdback), trial_worst_cost=float(worst),
                exam=_exam(d["exam"], folder) if "exam" in d else None,
                kind=_name(d["kind"], "kind", AGENT_NAME) if "kind" in d else agent,
                owner=_name(d["owner"], "owner", AGENT_NAME) if "owner" in d else "",
                hands_over=_hands_over(d["hands_over"], agent) if "hands_over" in d else (),
                second_signal=_second(d["second_signal"], results, d["decides"]) if "second_signal" in d else None)


def _hands_over(v, agent):
    """The optional hands_over key: {receiving agent: {about, kinds: {name: line}}}."""
    out, seen = [], set()
    for name, h in _dict(v, "hands_over", empty=False).items():
        to = _name(name, "hands_over agent")
        if to == agent:
            raise ValueError("hands_over: an agent hands over to another agent, never to itself")
        where = f"hands_over {to!r}"
        h = _dict(h, where, empty=False)
        _keys(h, {"about", "kinds"}, {"kinds"}, where)
        kinds = _named_lines(h["kinds"], f"{where} kinds", empty=False)
        twice = sorted(seen & set(kinds))
        if twice:
            raise ValueError(f"{where}: the kind {twice[0]!r} goes to one agent only")
        seen |= set(kinds)
        out.append(HandOver(to, _line(h["about"], f"{where} about") if "about" in h else "", MappingProxyType(kinds)))
    return tuple(out)


def _exam(e, folder):
    """The optional exam key: {"situations": a relative path inside the plug's folder, "checks": [names]}."""
    e = _dict(e, "exam", empty=False)
    _keys(e, {"situations", "checks"}, {"situations", "checks"}, "exam")
    where = e["situations"]
    if not isinstance(where, str) or not where.strip():
        raise ValueError("exam situations is a path to a JSON file")
    rel = Path(where)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("exam situations is a path inside the plug's folder: not absolute, no ..")
    checks = tuple(_name(c, "exam check") for c in _list(e["checks"], "exam checks"))
    if not checks:
        raise ValueError("exam checks names at least one check")
    if len(set(checks)) != len(checks):
        raise ValueError("exam checks: a check named twice")
    return Exam(situations=(Path(folder) / rel) if folder is not None else rel, checks=checks)


def _level(v, name):
    """One trial level: {share, days}, both given."""
    where = f"trial {name}"
    v = _dict(v, where, empty=False)
    _keys(v, {"share", "days"}, {"share", "days"}, where)
    share = _number(v["share"], f"{where} share")
    if not 0 < share < 1:
        raise ValueError(f"{where} share is more than 0 and under 1")
    days = v["days"]
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError(f"{where} days: a whole number, 1 or more")
    return Level(float(share), days)


def _gone(d, where):
    for key in sorted(set(d) & set(GONE[where])):
        raise ValueError(f"{where}: {key!r} is no longer a key: {GONE[where][key]}")


def _result(name, r, actions):
    where = f"result {name!r}"
    r = _dict(r, where, empty=False)
    _keys(r, RESULT_KEYS, {"speed"}, where)
    speed = r["speed"]
    if speed not in (FAST, SLOW):
        raise ValueError(f"{where}: speed is {FAST} or {SLOW}")
    shows = None
    if "shows_in_days" in r:  # optional, shown only (DECISIONS item 66); checked when given
        days = _list(r["shows_in_days"], f"{where} shows_in_days")
        if len(days) != 2:
            raise ValueError(f"{where}: shows_in_days is [least, most]")
        least, most = (_number(x, f"{where} shows_in_days") for x in days)
        if not 0 <= least <= most:
            raise ValueError(f"{where}: shows_in_days needs 0 <= least <= most")
        if speed == FAST and most > 1:
            raise ValueError(f"{where}: a fast result shows within a day")
        if speed == SLOW and most <= 1:
            raise ValueError(f"{where}: a slow result takes more than a day")
        shows = (float(least), float(most))
    after = r.get("after")
    if after is not None:
        if after not in actions:
            raise ValueError(f"{where}: after names no declared action")
        if speed == SLOW:
            raise ValueError(f"{where}: a slow result comes on its own and attaches by case")
    return Result(name, speed, shows, after,
                  _line(r["about"], f"{where} about") if "about" in r else "")


def _source(s):
    s = _dict(s, "source", empty=False)
    _keys(s, {"about", "known_by"}, {"about", "known_by"}, "source")
    if s["known_by"] not in (CASE, ROW):
        raise ValueError(f"source: known_by is {CASE} (the case id names its source) or {ROW} "
                         "(each action is saved with its source)")
    return Source(_line(s["about"], "source about"), s["known_by"])


def _harm(h, results):
    h = _dict(h, "harm", empty=False)
    _keys(h, {"results", "about", "serious"}, {"results"}, "harm")
    names = _list(h["results"], "harm results")
    if not names:
        raise ValueError("harm: at least one fast result counts as harm")
    for name in names:
        if _declared(name, results, "harm").speed != FAST:
            raise ValueError(f"harm: {name!r} is a slow result; harm is a fast result, seen within a day")
    _once(names, "harm")
    serious = _list(h.get("serious", []), "harm serious")
    for name in serious:
        _declared(name, results, "harm serious")
    _once(serious, "harm serious")
    return Harm(tuple(names), _line(h["about"], "harm about") if "about" in h else "", tuple(serious))


def _decides(d, results):
    d = _dict(d, "decides", empty=False)
    _keys(d, {"good", "bad"}, {"good", "bad"}, "decides")
    names = [d["good"], *_list(d["bad"], "decides bad")]
    for name in names:
        _declared(name, results, "decides")
    _once(names, "decides")
    return Decides(names[0], tuple(names[1:]))


def _second(d, results, decides):
    """The optional second_signal key: {good, bad}, declared results that decides does not name."""
    d = _dict(d, "second_signal", empty=False)
    _keys(d, {"good", "bad"}, {"good", "bad"}, "second_signal")
    names = [d["good"], *_list(d["bad"], "second_signal bad")]
    for name in names:
        _declared(name, results, "second_signal")
    _once(names, "second_signal")
    deciding = {decides["good"], *decides["bad"]}
    for name in names:
        if name in deciding:
            raise ValueError(f"second_signal: {name!r} decides a case already; a second signal never does")
    return Decides(names[0], tuple(names[1:]))


def _declared(name, results, where):
    if not isinstance(name, str) or name not in results:
        raise ValueError(f"{where}: {name!r} is not a declared result")
    return results[name]


def _once(names, where):
    if len(set(names)) != len(names):
        raise ValueError(f"{where}: a result named twice")


def _risk(r):
    r = _dict(r, "risk", empty=False)
    _keys(r, {"high", "low"}, {"high", "low"}, "risk")
    high = _dict(r["high"], "risk high", empty=False)
    _keys(high, HIGH_KEYS, {"about"}, "risk high")
    low = _dict(r["low"], "risk low", empty=False)
    _keys(low, {"about"}, {"about"}, "risk low")
    words = tuple((group, _line(w, f"risk word in {group!r}"))
                  for group, ws in _groups(high.get("words", {}), "risk words") for w in ws)
    patterns = []
    for group, ps in _groups(high.get("patterns", {}), "risk patterns"):
        for p in ps:
            try:
                re.compile(_line(p, f"risk pattern in {group!r}"))
            except re.error as e:
                raise ValueError(f"risk pattern {p!r}: {e}") from None
            patterns.append((group, p))
    tools = tuple(_name(t, "risk tool") for t in _list(high.get("tools", []), "risk tools"))
    return Risk(high_about=_line(high["about"], "risk high about"), low_about=_line(low["about"], "risk low about"),
                words=words, patterns=tuple(patterns), tools=tools)


def _groups(v, what):
    """{group: [line, ...]} as (group, lines) pairs, each group a name."""
    return [(_name(g, f"{what} group"), _list(lines, f"{what} {g!r}")) for g, lines in _dict(v, what, empty=True).items()]


def _keys(d, allowed, required, where, why=None):
    extra = sorted(set(d) - allowed)
    if extra:
        raise ValueError(f"{where}: unknown key {extra[0]!r}")
    missing = sorted(required - set(d))
    if missing:
        what = (why or {}).get(missing[0])
        raise ValueError(f"{where}: missing {missing[0]!r}" + (f": {what}" if what else ""))


def _name(v, what, rx=NAME):
    if not isinstance(v, str) or not rx.fullmatch(v):
        raise ValueError(f"{what} {v!r}: lowercase letters, digits and _, starting with a letter"
                         + (", at most 41 characters" if rx is AGENT_NAME else ""))
    return v


def _line(v, what):
    if not isinstance(v, str) or not v.strip() or "\n" in v or "\r" in v:
        raise ValueError(f"{what}: one line of text")
    return v.strip()


def _list(v, what):
    if not isinstance(v, list):
        raise ValueError(f"{what}: a list")
    return v


def _dict(v, what, *, empty):
    if not isinstance(v, dict) or (not empty and not v):
        raise ValueError(f"{what}: an object" + ("" if empty else " with at least one entry"))
    return v


def _number(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{what}: a number")
    return v


def _named_lines(v, what, *, empty):
    return {_name(k, what): _line(line, f"{what} {k!r}") for k, line in _dict(v, what, empty=empty).items()}
