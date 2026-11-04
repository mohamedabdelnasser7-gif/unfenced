"""A practice match of an agent Quick start built, as a case its night study reads (new,
2026-11-02; the live cases work, map item A9). arena/learn.py does this for the Sales agent; this
file does it for any built agent, from its own plug, with no name of its own in the code.

The match is written into the engine's log (engine/log.py) under the agent's plug, one row a
turn, under the case id "arena-<agent>-<match id>". Each row is a declared action of the plug: the
plug actions the turn took (the turn's "actions", arena/practice.py), else the plug's reply action
when it declares one, else its first action (the agent's own writing). Each row's detail holds what
arrived (the person's line, or none when the agent wrote first), the agent's output, the tools it
ran and its failed send checks; the last row holds the verdict and its quote, as learn.py writes.

Every row says "arena": true and "history": true, exactly as learn.py marks a Sales case, so it
never counts in a trial (engine/trial.py), never gets a fast note (engine/fast.py), never makes the
agent live on the Morning page (reflection/morning.py) and never counts in its results. The night
study still reads it, which is the point: a practice loss can become a lesson. These rows go into
the agent's own database, the one its night runs on: a built agent has no study between practice
rounds, so its night is where its practice is read.

Two ways in. learner(db, plug) is the learn hook arena/practice.py Practice takes, for a practice run
that has the database: each lost training match is written as it is judged. from_folder(db, plug,
folder) is what the night runs first (reflection/night.py): every training match the agent saved in
its folder, won or lost, not written yet. The study needs cases that ended good and not good before
it looks for a pattern, and a new agent has no live cases, so its practice wins are written too,
each closing with the plug's good result. Gate matches never are: only training ids are read here
(decision 104's Train on a run's lost gate matches is the page's step, not this night read).

A practice match has no result tool, so a lost case closes on the plug's first bad deciding
result, as its last row (or ending its action when the result ends one), and settles at once
whatever the time. No timer settles a case (DECISIONS item 66), so a plug with no bad result
leaves its lost cases pending; Build always names one. A turn's own outcome is kept on its row only when the plug
declares it as ending that action and it is not a deciding result: only the verdict decides.

The source: when the plug's case names its source, the case id is it; when each row names it, the
practice card's id, so matches against one made-up person share a source.

An off topic match (arena/scope.py) has "kind": "scope" on every row, so the study writes from it only its
general decline line, never a refusal of a topic (engine/study.py, see 9).
"""
import calendar
import json
import re
import time
from pathlib import Path

from engine.log import Log
from engine.plug import CASE

DAY = 86400.0
TURN_SECONDS = 60.0
REPLY = "reply"
TRAINING = re.compile(r"(\d{8}T\d{6})-r\d+-t\d+")  # arena/run.py training match ids
MAX_MATCHES_BYTES = 10_000_000


def case_id(agent, match_id):
    return f"arena-{agent}-{match_id}"


def bad_result(plug):
    """The first bad deciding result of the plug that comes on its own, or None."""
    for name in plug.decides.bad:
        if plug.results[name].after is None:
            return name
    return None


def actions_of(plug, turn):
    """The declared plug actions a turn took, in order and once each; else the reply action or the
    plug's first action."""
    took = []
    for a in turn.get("actions") or []:
        if isinstance(a, str) and a in plug.actions and a not in took:
            took.append(a)
    if took:
        return took
    return [REPLY] if REPLY in plug.actions else [next(iter(plug.actions))]


def _closing(plug, won):
    """How a case closes: ("result", name) for a deciding result that comes on its own, ("act",
    action, name) for one that ends an action, or None when a loss has no bad result to close on."""
    if won:
        good = plug.decides.good
        after = plug.results[good].after
        return ("result", good) if after is None else ("act", after, good)
    bad = bad_result(plug) or next(iter(plug.decides.bad), None)
    if bad is None:
        return None
    after = plug.results[bad].after
    return ("result", bad) if after is None else ("act", after, bad)


def _write(db, plug, match, judged, match_id, now, won):
    from reflection import PLUG as SALES
    if plug.agent == SALES.agent:
        raise ValueError("the Sales agent's matches become cases through arena/learn.py")
    log = Log(db, plug)
    case = case_id(plug.agent, match_id)
    if log.case(case):
        return None
    turns = match.get("turns") or []
    if not turns:  # nothing played at all: one row of the plug's first action carries the verdict
        turns = [{}]
    closing = _closing(plug, won)
    deciders = {plug.decides.good, *plug.decides.bad}
    rows = sum(len(actions_of(plug, t)) for t in turns)
    start = now - (rows + 1) * TURN_SECONDS  # its closing row decides it: every row just before now
    stage = plug.stages[0] if plug.stages else None
    source = None if plug.source.known_by == CASE else f"arena-{match.get('card') or match_id}"
    base = {"arena": True, "history": True, "practice": True, "match": match_id, "card": match.get("card"),
            "worry": match.get("worry"), "made_up": match.get("made_up") is True}
    if match.get("off_scope"):  # an off topic match: the study writes only its decline line from it
        from engine.study import SCOPE
        base["kind"] = SCOPE
    at, step = start, 0
    for i, t in enumerate(turns):
        took = actions_of(plug, t)
        for k, action in enumerate(took):
            step += 1
            detail = dict(base)
            if k == 0:
                detail.update(customer=t.get("customer"), reply=" ".join(t.get("replies") or []),
                              tools=list(t.get("tools") or []), actions=list(t.get("actions") or []))
                if t.get("failed"):
                    detail["failed_checks"] = t["failed"]
            if i == len(turns) - 1 and k == len(took) - 1:
                detail["verdict"] = judged.get("why")
                detail["quote"] = judged.get("quote")
            outcome = t.get("outcome") if k == len(took) - 1 else None
            declared = plug.results.get(outcome) if isinstance(outcome, str) else None
            # a turn's outcome never decides a case: only the verdict's closing row does
            result = outcome if declared is not None and declared.after == action and outcome not in deciders else None
            log.act(case, action, result=result, stage=stage, step=step, detail=detail, at=at, source=source)
            at += TURN_SECONDS
    if closing is not None and closing[0] == "result":
        log.result(case, closing[1], stage=stage, step=step + 1, detail=dict(base), at=at)
    elif closing is not None:
        log.act(case, closing[1], result=closing[2], stage=stage, step=step + 1, detail=dict(base), at=at,
                source=source)
    return case


def to_case(db, plug, match, judged, match_id, *, now=None):
    """Write one lost practice match into the log under plug. Returns its case id; refuses a won
    match and a correct close (decision 105). A case already written (the same agent and match id) is
    left as it is."""
    if judged.get("won") or judged.get("close"):
        raise ValueError("only a lost match becomes a case")
    now = time.time() if now is None else float(now)
    _write(db, plug, match, judged, match_id, now, False)
    return case_id(plug.agent, match_id)


def learner(db, plug):
    """learn(m, judged, mid) for arena/practice.py Practice (and arena/run.py Arena): each lost
    training match of this agent becomes a case in db."""
    return lambda m, judged, mid: to_case(db, plug, m, judged, mid)


def _run_time(match_id):
    """The time a practice match was played, from its id (arena/run.py: "<run>-r<n>-t<k>", the run
    a UTC stamp), or None when the id is not a training match's."""
    got = TRAINING.fullmatch(match_id) if isinstance(match_id, str) else None
    if got is None:
        return None
    try:
        return calendar.timegm(time.strptime(got.group(1), "%Y%m%dT%H%M%S"))
    except ValueError:
        return None


def from_folder(db, plug, folder, *, until=None):
    """Every training match the agent played in practice and saved in its folder
    (arena-matches.jsonl, arena/practice.py), won or lost, written as a case under plug, timed when
    it was played: a win closes with the plug's good result, a loss as to_case writes it. The night
    study needs both sides to find a pattern (engine/study.py), and a new agent has no live cases
    yet. Gate matches are left out (only training ids are read, TRAINING), and so is any match
    of another agent or played at or after until, and an off topic match the agent won (arena/scope.py):
    it declined, so it never reached the good result a win closes with; a lost one is written. A correct
    close (close_win, decision 105) is written neither good nor bad: no offer met that person's need, so it
    is no pattern of a sale and no loss. A case already written is left as it is. Returns
    {"written", "won", "lost"} counts of the cases written now."""
    from arena import run as run_mod
    out = {"written": 0, "won": 0, "lost": 0}
    path = Path(folder) / run_mod.MATCHES_FILE
    try:
        if path.is_symlink() or not path.is_file():
            return out
        if path.stat().st_size > MAX_MATCHES_BYTES:  # said in the night's report, never silent
            return dict(out, skipped=f"{run_mod.MATCHES_FILE} is over {MAX_MATCHES_BYTES // 1_000_000} MB, "
                                     "so no practice was read")
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    until = time.time() if until is None else float(until)
    for line in lines:
        try:
            m = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(m, dict) or m.get("agent") != plug.agent or not isinstance(m.get("won"), bool) \
                or not isinstance(m.get("turns"), list):
            continue
        if m.get("off_scope") and m["won"]:  # an off topic win never reached the good result (arena/scope.py)
            continue
        if m.get("close_win") is True:  # a correct close: neither a good case nor a loss (decision 105)
            continue
        played = _run_time(m.get("id"))
        if played is None or played >= until:
            continue
        judged = {"won": m["won"], "why": m.get("why"), "quote": m.get("quote")}
        try:
            wrote = _write(db, plug, m, judged, m["id"], played + TURN_SECONDS, m["won"])
        except (ValueError, TypeError, AttributeError):
            continue  # a line the log cannot take is skipped, never half a night
        if wrote is not None:
            out["written"] += 1
            out["won" if m["won"] else "lost"] += 1
    return out
