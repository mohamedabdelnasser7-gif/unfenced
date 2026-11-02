"""Fakes for the night study tests: a proposer, a tagger, a fit check and an adapter that
answer from a script, and a helper that writes one case to the log. No model, no network.

The tagger reads a mark in each step's detail, so a test knows exactly which cases have a
pattern; the study must still do every count itself.
"""
import copy

DAY = 86400
T0 = 1_800_000_000.0
SINCE, UNTIL = T0, T0 + 30 * DAY
NOW = UNTIL

EARLY = {"pattern": "The bed was watered early in the morning.", "helps": True,
         "lesson": "Water the beds early in the morning.", "situation": "Any bed on a warm day.",
         "stages": ["all"]}
MULCH = {"pattern": "The bed had no mulch on it.", "helps": False,
         "lesson": "Put mulch on a bed before watering it.", "situation": "A bare bed.",
         "stages": ["seedling"]}
TWICE = {"pattern": "The entry was checked twice before it was posted.", "helps": True,
         "lesson": "Check each entry twice before posting it.", "situation": "Any entry.",
         "stages": ["all"]}
MARKS = {EARLY["pattern"]: "early", MULCH["pattern"]: "bare", TWICE["pattern"]: "twice"}


def candidate(base, **changes):
    out = copy.deepcopy(base)
    out.update(changes)
    return out


class Proposer:
    """Gives the same candidates every time and keeps what it was shown."""

    def __init__(self, *candidates, fail=False):
        self.candidates = list(candidates)
        self.fail = fail
        self.calls = []

    def __call__(self, plug, sample, limit, known):
        self.calls.append({"agent": plug.agent, "sample": copy.deepcopy(sample), "limit": limit, "known": list(known)})
        if self.fail:
            raise RuntimeError("the proposer is down")
        return copy.deepcopy(self.candidates)


class Tagger:
    """Yes when a step's detail has the pattern's mark set, no when it is set false; no answer
    when no step names the mark. odd: the cases answered with something that is not true or
    false, as case keys or as a test on a case's view (the study gives the tagger fresh keys)."""

    def __init__(self, marks=MARKS, *, fail=False, odd=()):
        self.marks = dict(marks)
        self.fail = fail
        self.odd = odd if callable(odd) else (lambda view, keys=frozenset(odd): view["id"] in keys)
        self.calls = []

    def __call__(self, plug, pattern, cases):
        self.calls.append({"agent": plug.agent, "pattern": pattern, "cases": copy.deepcopy(cases)})
        if self.fail:
            raise RuntimeError("the tagger is down")
        key = self.marks[pattern]
        out = {}
        for view in cases:
            flags = [s["detail"][key] for s in view["steps"] if isinstance(s.get("detail"), dict) and key in s["detail"]]
            if flags:
                out[view["id"]] = bool(flags[0])
        for view in cases:
            if self.odd(view):
                out[view["id"]] = "yes"
        return out


class Fit:
    """Answers from a table by the candidate's lesson line; "not" when the line is not in it."""

    def __init__(self, answers=None, *, fail=False):
        self.answers = dict(answers or {})
        self.fail = fail
        self.calls = []

    def __call__(self, plug, other, cand):
        self.calls.append({"agent": plug.agent, "other": other.agent, "candidate": copy.deepcopy(cand)})
        if self.fail:
            raise RuntimeError("the fit check is down")
        return self.answers.get(cand["lesson"], "not")


class Adapter:
    """Rewrites a lesson line from a table; None when the line is not in it."""

    def __init__(self, lines=None, *, stages=("all",), fail=False):
        self.lines = dict(lines or {})
        self.stages = list(stages)
        self.fail = fail
        self.calls = []

    def __call__(self, plug, other, cand, fit):
        self.calls.append({"agent": plug.agent, "other": other.agent, "candidate": copy.deepcopy(cand), "fit": fit})
        if self.fail:
            raise RuntimeError("the adapter is down")
        line = self.lines.get(cand["lesson"])
        if line is None:
            return None
        return {"lesson": line, "situation": f"Adapted: {cand.get('situation', '')}".strip(), "stages": self.stages}


def case(log, cid, action, fast, slow=None, *, at=T0 + DAY, cause=None, stage=None, source=None, lessons=(),
         **detail):
    """One case: an action with its fast result, then maybe a slow result three days later."""
    kw = {"source": source} if source is not None else {}
    log.act(cid, action, result=fast, stage=stage, detail=detail or None, at=at, lessons=lessons, **kw)
    if slow:
        log.result(cid, slow, cause=cause, at=at + 3 * DAY)


def beds(log, *, early_good=8, early_bad=2, late_good=2, late_bad=8, prefix="bed", at=T0 + DAY, **detail):
    """Garden beds for the waterer: early or late watering, then grew or wilted."""
    note = detail.pop("note", None)
    n = 0
    for early, good, count in ((True, True, early_good), (True, False, early_bad),
                               (False, True, late_good), (False, False, late_bad)):
        for _ in range(count):
            n += 1
            case(log, f"{prefix}{n}", "water", "soaked", "grew" if good else "wilted", at=at, stage="seedling",
                 early=early, note=note or f"round {n}", **detail)
    return n


def entries(log, *, twice_good=8, twice_none=2, once_good=2, once_none=8, prefix="month", at=T0 + DAY):
    """Months of books for the ledger: checked twice or once, then balanced or unbalanced."""
    n = 0
    for twice, good, count in ((True, True, twice_good), (True, False, twice_none),
                               (False, True, once_good), (False, False, once_none)):
        for _ in range(count):
            n += 1
            case(log, f"{prefix}{n}", "post", "posted", "balanced" if good else "unbalanced", at=at, stage="open",
                 twice=twice, note=f"entry {n}")
    return n
