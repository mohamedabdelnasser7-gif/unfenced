"""The simulator: made-up cases for one agent, written into the engine's log through the
engine's own API (Log.act and Log.result), so the night study can be shown on data whose
causes are known. Fake the data, never the code: the study that reads them is the real one.

It is plug driven and knows no agent. A scenario file says what one case looks like, the
traits a case can have, how often a case ends good and what is planted; the plug says which
names exist, how long each deciding result takes to show and how a source is known. Every
name is checked against the plug, so a scenario cannot write what the plug did not declare.

A case's deciding result is drawn once its last step is written, and comes at a time inside
the window the plug gives that result. One that comes on its own is saved with Log.result.
One that ends an action, a fast result, is saved with Log.act on that action, with no stage,
step or lessons: it is how the case ended, not a step the lessons can reach.

Every row is labelled: its detail carries "simulated": true, and every case id and every
source starts with "sim-". The same scenario and seed give the same log, row for row.

Scenario keys (unknown keys are refused):
  name     lowercase letters, digits and _; case ids are sim-<name>-0001 and on, oldest first.
  agent    the plug's agent; a scenario for another agent is refused.
  about    optional, one plain line.
  seed     a whole number, the default seed.
  start    the first day, YYYY-MM-DD, UTC.
  days     the cases start over this many days. The log ends there: a deciding result due
           later is not written, so its case is still pending, as on the night of the study.
  cases    how many cases.
  steps    [{action, result, stage, hours, detail}]: one case's actions in turn, each with the
           fast result the plug says ends it, hours after the case starts. A deciding result
           is never a step: the simulator writes it.
  traits   {name: {step, values: {value: {share, detail}}}}: each case draws one value of each
           trait by share, and the value's detail joins that step's detail. A list of details
           gives one drawn at random.
  rate     the chance a settled case ends good.
  rates    [{when, rate}]: the first that matches a case gives its chance instead.
  outside  [{when, cause, rate}]: a case that matches the first one gets this chance, and its
           deciding result carries the cause, one of the plug's causes outside the agent. A
           case that gets no deciding result carries it on its last step instead, so it is
           left out all the same.
  groups   [{name, cases, rate, detail, sources}]: this many cases, drawn at random, with
           their own chance and detail ({step: {...}}). sources: how many different sources
           the group's cases come from, in turn; only for a plug whose rows name their source.
  sources  {pool, name}: for a plug whose rows name their source, every other case comes from
           one of pool sources, sim-<scenario name>-<name>-<n>. Refused when the case id
           names the source: there one case is one source.
  stamp    {weekday: {step, key}}: the case's weekday, mon to sun, in that step's detail.
  bad      optional: which not good deciding result a case that ends not good gets; the
           first of the plug's by default. With none declared, it gets no deciding result:
           it is pending until the longest deciding window has passed since its last step,
           then not good, as the night study settles it.
  lift     optional [{lesson, trait, value, follows}]: how a case reacts to a lesson it was
           given, the true effect a run with lessons plants (sim/score.py). A case handed the
           lesson line, at the trait's step or before it, takes that value of the trait with
           the chance follows (1 by default; the same case always gets the same answer). Its
           detail and its chance of ending good then follow the new value, as rates and
           outside say. Without lessons handed, a lift changes nothing. The line must be one
           of the script's candidate lines, the lines a night can write; any other is refused.
  script   read by sim/scripted.py, not here.
A when is {trait: value, day: n, weekday: name}, each also a list; every key must match.
day counts from 0 on the start day. An outside rule comes first, then a group, then rates.
"""
import calendar
import copy
import hashlib
import heapq
import json
import math
import random
import re
import time
from pathlib import Path

from engine.log import Log
from engine.plug import CASE
from engine.study import BAD, GOOD, LEFT_OUT, PENDING

DAY, HOUR = 86400, 3600
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LABEL = "simulated"
PREFIX = "sim-"
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
KEYS = {"name", "agent", "about", "seed", "start", "days", "cases", "steps", "traits", "rate", "rates", "outside",
        "groups", "sources", "stamp", "bad", "lift", "script"}
LIFT_KEYS = {"lesson", "trait", "value", "follows"}
REQUIRED = {"name", "agent", "seed", "start", "days", "cases", "steps", "rate"}


def load(path):
    """A scenario file as a dict; it is checked against a plug when simulated."""
    with open(Path(path), encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: not JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a scenario is one JSON object")
    return data


def simulate(db, plug, scenario, *, seed=None, lessons=None, hand_from=None, nights=(), night=None, until=None):
    """Write the scenario's cases into the log under the plug. Returns the manifest: what was
    planted in each case and how it stands at the end, the truth a test reads the study against.

    Rows are written in time, one by one. lessons: the agent's engine Lessons. Each action at
    or after hand_from (the first day when None), by the action's own time, is then handed its
    lessons through Lessons.hand at that time and saved with their ids, and the scenario's lift
    says how the case reacts. A case that started before hand_from is handed its lessons from
    its first action at or after it, as a running case is in the engine. nights: times; night(t) runs before any row at or after t, so what a
    night writes is what later actions are handed. until: where the log ends, the scenario's
    end by default and never before it; a deciding result due at or after it is not written."""
    sc = check(plug, scenario)
    seed = sc["seed"] if seed is None else _whole(seed, "seed", least=0)
    rng = random.Random(seed)
    start = calendar.timegm(time.strptime(sc["start"], "%Y-%m-%d"))
    end = start + sc["days"] * DAY
    until = end if until is None else _number(until, "until")
    if until < end:
        raise ValueError("until: at or after the scenario's end")
    hand_from = start if hand_from is None else _number(hand_from, "hand_from")
    if lessons is not None and lessons.agent != plug.agent:
        raise ValueError("lessons: the plug's own agent")
    nights = [_number(t, "a night") for t in nights]
    if nights and not callable(night):
        raise ValueError("nights: give night, what runs each night")
    steps = sc["steps"]
    span = max(s["hours"] for s in steps) * HOUR
    n = sc["cases"]
    starts = sorted(rng.uniform(start, end - span) for _ in range(n))
    member = {}
    for g in sc["groups"]:
        free = [i for i in range(n) if i not in member]
        for rank, i in enumerate(sorted(rng.sample(free, g["cases"]))):
            member[i] = (g, rank)
    deciders = (plug.decides.good, *plug.decides.bad)
    longest = max(plug.results[r].shows_in_days[1] for r in deciders)
    bad = sc.get("bad") or (plug.decides.bad[0] if plug.decides.bad else None)
    plans = []
    for i, at in enumerate(starts):
        traits, picks = {}, {}
        for name, t in sc["traits"].items():
            traits[name] = _draw(rng.random(), t["values"])
            picks[name] = rng.random()
        u_good, u_delay, u_source = rng.random(), rng.random(), rng.random()
        group, rank = member.get(i, (None, 0))
        p = {"id": f"{PREFIX}{sc['name']}-{i + 1:04d}", "at": at, "traits": traits, "picks": picks, "group": group,
             "day": int((at - start) // DAY), "weekday": WEEKDAYS[time.gmtime(at).tm_wday], "u_good": u_good,
             "u_delay": u_delay, "last": max([at] + [at + s["hours"] * HOUR for s in steps]), "source": None,
             "given": set(), "lifted": {}, "left": len(steps), "deciding": None, "cause": None, "written": False,
             "marked": False}
        p["details"] = _details(sc, p)
        if plug.source.known_by != CASE:
            pool = f"{PREFIX}{sc['name']}-{sc['sources']['name']}"
            if group is not None and group.get("sources"):
                p["source"] = f"{pool}-{group['name']}-{rank % group['sources'] + 1}"
            else:
                p["source"] = f"{pool}-{int(u_source * sc['sources']['pool']) + 1}"
        plans.append(p)
    events = [(p["at"] + s["hours"] * HOUR, i, k) for i, p in enumerate(plans) for k, s in enumerate(steps)]
    events += [(t, -1, k) for k, t in enumerate(nights)]  # a night comes before any row at its time
    heapq.heapify(events)
    log = Log(db, plug)
    rows = 0
    while events:  # one at a time, oldest first; a deciding result joins when its case's last step is written
        when, i, k = heapq.heappop(events)
        if i < 0:
            night(when)
            continue
        p = plans[i]
        if k == len(steps):
            _decide(log, plug, p, when)
            p["written"], rows = True, rows + 1
            continue
        s = steps[k]
        given = set()
        if lessons is not None and when >= hand_from and s["stage"] is not None:
            picked = lessons.hand(p["id"], s["action"], s["stage"], _text(p["details"][k]), given, now=when)
            _lift(sc, seed, p, k, [x["text"] for x in picked])
        p["given"] |= given
        p["left"] -= 1
        last = not p["left"]
        if last:  # how the case ends, read once every lift has had its step
            rate, cause = _chance(sc, p)
            p["deciding"] = plug.decides.good if p["u_good"] < rate else bad
            p["cause"] = cause
            p["marked"] = p["deciding"] is None and cause is not None  # no deciding row to carry it
        kw = {"lessons": sorted(given), "result": s["result"], "stage": s["stage"], "step": k + 1,
              "detail": dict(p["details"][k], **{LABEL: True}), "at": when}
        if last and p["marked"]:
            kw["cause"] = p["cause"]
        if p["source"] is not None:
            kw["source"] = p["source"]
        log.act(p["id"], s["action"], **kw)
        rows += 1
        if last and p["deciding"] is not None:
            least, most = plug.results[p["deciding"]].shows_in_days
            due = p["last"] + (least + p["u_delay"] * (most - least)) * DAY
            if due < until:
                heapq.heappush(events, (due, i, len(steps)))
    cases = []
    for p in plans:
        if p["written"]:
            status = LEFT_OUT if p["cause"] else (GOOD if p["deciding"] == plug.decides.good else BAD)
        elif p["last"] + longest * DAY > until:  # no deciding row yet: pending until the window has passed
            status = PENDING
        else:
            status = LEFT_OUT if p["marked"] else BAD
        cases.append({"id": p["id"], "source": p["id"] if p["source"] is None else p["source"],
                      "group": None if p["group"] is None else p["group"]["name"], "traits": p["traits"],
                      "day": p["day"], "weekday": p["weekday"], "deciding": p["deciding"] if p["written"] else None,
                      "cause": p["cause"] if p["written"] or p["marked"] else None, "status": status,
                      "given": sorted(p["given"]), "lifted": p["lifted"]})
    return {"agent": plug.agent, "scenario": sc["name"], "seed": seed, "since": float(start), "until": float(until),
            "end": float(end), "rows": rows, "cases": cases}


def _decide(log, plug, p, when):
    """Write the case's deciding result at its time, with its cause: on its own with
    Log.result, or with Log.act on the action it ends, as the outcome and not a step."""
    kw = {"cause": p["cause"], "detail": {LABEL: True}, "at": when}
    after = plug.results[p["deciding"]].after
    if after is None:
        log.result(p["id"], p["deciding"], **kw)
        return
    if p["source"] is not None:
        kw["source"] = p["source"]
    log.act(p["id"], after, result=p["deciding"], **kw)


def _details(sc, p):
    """Each step's detail for a case: the step's own, then each trait's value, the group's, the stamp."""
    details = [dict(s["detail"]) for s in sc["steps"]]
    for name, t in sc["traits"].items():
        details[t["step"]].update(_pick(p["picks"][name], t["values"][p["traits"][name]]["detail"]))
    if p["group"] is not None:
        for k, d in p["group"]["detail"].items():
            details[k].update(d)
    for what, where in sc["stamp"].items():
        details[where["step"]][where["key"]] = p["weekday"]
    return details


def _chance(sc, p):
    """(the chance the case ends good, the cause outside the agent or None): an outside rule
    first, then the group, then rates, then the scenario's rate."""
    rate, cause = sc["rate"], None
    for r in sc["rates"]:
        if _match(r["when"], p["traits"], p["day"], p["weekday"]):
            rate = r["rate"]
            break
    if p["group"] is not None and p["group"].get("rate") is not None:
        rate = p["group"]["rate"]
    for r in sc["outside"]:
        if _match(r["when"], p["traits"], p["day"], p["weekday"]):
            rate, cause = r["rate"], r["cause"]
            break
    return rate, cause


def _lift(sc, seed, p, k, lines):
    """The case reacts to the lesson lines handed at step k: each lift whose line was handed at
    its trait's step or before it moves the trait to its value, when the case follows it. A
    trait moves once; the manifest keeps the value drawn before."""
    for r in sc["lift"]:
        trait = r["trait"]
        if r["lesson"] not in lines or k > sc["traits"][trait]["step"] or trait in p["lifted"]:
            continue
        if p["traits"][trait] == r["value"] or _unit(f"{seed}|{p['id']}|{trait}") >= r["follows"]:
            continue
        p["lifted"][trait] = p["traits"][trait]
        p["traits"][trait] = r["value"]
        p["details"] = _details(sc, p)


def _unit(key):
    """A number from 0 to 1 fixed by the key, the same on every run."""
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") / 2 ** 64


def _text(detail):
    """A step's words, as the lessons are matched against them."""
    return " ".join(v for v in detail.values() if isinstance(v, str))


def check(plug, sc):
    """The scenario checked against the plug, with every optional key filled in; ValueError names
    the first thing wrong."""
    if not isinstance(sc, dict):
        raise ValueError("a scenario is one JSON object")
    extra = sorted(set(sc) - KEYS)
    if extra:
        raise ValueError(f"the scenario: unknown key {extra[0]!r}")
    missing = sorted(REQUIRED - set(sc))
    if missing:
        raise ValueError(f"the scenario: missing {missing[0]!r}")
    out = copy.deepcopy(sc)
    if sc["agent"] != plug.agent:
        raise ValueError(f"the scenario is for {sc['agent']!r}, not {plug.agent!r}")
    _name(sc["name"], "name")
    _whole(sc["seed"], "seed", least=0)
    try:
        time.strptime(sc["start"], "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("start: a day as YYYY-MM-DD") from None
    days = _number(sc["days"], "days")
    if days <= 0:
        raise ValueError("days: more than 0")
    _whole(sc["cases"], "cases", least=1)
    out["steps"] = _steps(plug, sc["steps"])
    if max(s["hours"] for s in out["steps"]) * HOUR >= days * DAY:
        raise ValueError("steps: one case must fit inside the days")
    out["traits"] = _traits(sc.get("traits", {}), len(out["steps"]))
    _rate(sc["rate"], "rate")
    out["rates"] = [_rule(plug, r, out["traits"], f"rates {n}", cause=False)
                    for n, r in enumerate(_list(sc.get("rates", []), "rates"))]
    out["outside"] = [_rule(plug, r, out["traits"], f"outside {n}", cause=True)
                      for n, r in enumerate(_list(sc.get("outside", []), "outside"))]
    by_row = plug.source.known_by != CASE
    out["groups"] = [_group(g, len(out["steps"]), by_row) for g in _list(sc.get("groups", []), "groups")]
    if len({g["name"] for g in out["groups"]}) != len(out["groups"]):
        raise ValueError("groups: a name used twice")
    if sum(g["cases"] for g in out["groups"]) > sc["cases"]:
        raise ValueError("groups: more cases than the scenario has")
    if by_row:
        src = sc.get("sources")
        if not isinstance(src, dict):
            raise ValueError(f"sources: {plug.agent} saves each action with its source, so give {{pool, name}}")
        _keys(src, {"pool", "name"}, {"pool", "name"}, "sources")
        _whole(src["pool"], "sources pool", least=1)
        _name(src["name"], "sources name")
    elif "sources" in sc:
        raise ValueError(f"sources: for {plug.agent} the case id names the source, so one case is one source")
    stamp = _dict(sc.get("stamp", {}), "stamp")
    _keys(stamp, {"weekday"}, set(), "stamp")
    for what, where in stamp.items():
        _dict(where, f"stamp {what}")
        _keys(where, {"step", "key"}, {"step", "key"}, f"stamp {what}")
        _step_index(where["step"], len(out["steps"]), f"stamp {what}")
        _name(where["key"], f"stamp {what} key")
    out["stamp"] = stamp
    if sc.get("bad") is not None and sc["bad"] not in plug.decides.bad:
        if not plug.decides.bad:
            raise ValueError(f"bad: {plug.agent} declares no not good deciding results, so a case that does not "
                             "end good gets none")
        raise ValueError(f"bad: {sc['bad']!r} is not one of {plug.agent}'s not good deciding results")
    out["lift"] = _lifts(sc.get("lift", []), out["traits"], _candidate_lines(sc.get("script")))
    return out


def _candidate_lines(script):
    """The lesson line of each of the script's candidates (sim/scripted.py), stripped."""
    cands = script.get("candidates", []) if isinstance(script, dict) else []
    return {c["lesson"].strip() for c in (cands if isinstance(cands, list) else [])
            if isinstance(c, dict) and isinstance(c.get("lesson"), str)}


def _lifts(lifts, traits, lines):
    out, seen = [], set()
    for n, r in enumerate(_list(lifts, "lift")):
        where = f"lift {n}"
        _dict(r, where)
        _keys(r, LIFT_KEYS, LIFT_KEYS - {"follows"}, where)
        line = r["lesson"]
        if not isinstance(line, str) or not line.strip() or "\n" in line or "\r" in line:
            raise ValueError(f"{where}: lesson is one line of text")
        if line.strip() not in lines:
            raise ValueError(f"{where}: lesson is not one of the script's candidate lines, so no night writes it")
        if r["trait"] not in traits:
            raise ValueError(f"{where}: {r['trait']!r} is not a trait")
        if r["value"] not in traits[r["trait"]]["values"]:
            raise ValueError(f"{where}: trait {r['trait']!r} has no value {r['value']!r}")
        follows = _rate(r.get("follows", 1), f"{where} follows")
        if (line.strip(), r["trait"]) in seen:
            raise ValueError(f"{where}: the same lesson and trait twice")
        seen.add((line.strip(), r["trait"]))
        out.append({"lesson": line.strip(), "trait": r["trait"], "value": r["value"], "follows": follows})
    return out


def _steps(plug, steps):
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps: a list with at least one step")
    out = []
    for n, s in enumerate(steps):
        where = f"step {n}"
        _dict(s, where)
        _keys(s, {"action", "result", "stage", "hours", "detail"}, {"action", "result", "hours"}, where)
        plug.action(s["action"])
        if plug.result(s["result"]).after != s["action"]:
            raise ValueError(f"{where}: {s['result']!r} does not end the action {s['action']!r}")
        if s["result"] in (plug.decides.good, *plug.decides.bad):
            raise ValueError(f"{where}: {s['result']!r} decides a case, so the simulator writes it; it is never a step")
        stage = s.get("stage")
        if stage is not None and stage not in plug.stages:
            raise ValueError(f"{where}: {plug.agent} declares no stage {stage!r}")
        hours = _number(s["hours"], f"{where} hours")
        if hours < 0:
            raise ValueError(f"{where}: hours is 0 or more")
        out.append({"action": s["action"], "result": s["result"], "stage": stage, "hours": hours,
                    "detail": _dict(s.get("detail", {}), f"{where} detail")})
    return out


def _traits(traits, n_steps):
    out = {}
    for name, t in _dict(traits, "traits").items():
        where = f"trait {name!r}"
        _name(name, "trait")
        if name in ("day", "weekday"):
            raise ValueError(f"{where}: day and weekday are kept for when")
        _dict(t, where)
        _keys(t, {"step", "values"}, {"step", "values"}, where)
        _step_index(t["step"], n_steps, where)
        values = _dict(t["values"], f"{where} values")
        if not values:
            raise ValueError(f"{where}: at least one value")
        for value, v in values.items():
            _dict(v, f"{where} value {value!r}")
            _keys(v, {"share", "detail"}, {"share"}, f"{where} value {value!r}")
            if _number(v["share"], f"{where} share") <= 0:
                raise ValueError(f"{where}: a share is more than 0")
            detail = v.get("detail", {})
            for d in detail if isinstance(detail, list) else [detail]:
                _dict(d, f"{where} value {value!r} detail")
            if isinstance(detail, list) and not detail:
                raise ValueError(f"{where} value {value!r}: a detail list needs at least one")
        out[name] = {"step": t["step"], "values": {k: {"share": v["share"], "detail": v.get("detail", {})}
                                                    for k, v in values.items()}}
    return out


def _rule(plug, r, traits, where, *, cause):
    _dict(r, where)
    keys = {"when", "rate", "cause"} if cause else {"when", "rate"}
    _keys(r, keys, keys, where)
    if cause:
        plug.cause(r["cause"])
    _rate(r["rate"], f"{where} rate")
    when = _dict(r["when"], f"{where} when")
    for k, v in when.items():
        wanted = v if isinstance(v, list) else [v]
        if k == "day":
            for d in wanted:
                _whole(d, f"{where} day", least=0)
        elif k == "weekday":
            bad = [w for w in wanted if w not in WEEKDAYS]
            if bad:
                raise ValueError(f"{where}: weekday is one of {', '.join(WEEKDAYS)}")
        elif k in traits:
            bad = [x for x in wanted if x not in traits[k]["values"]]
            if bad:
                raise ValueError(f"{where}: trait {k!r} has no value {bad[0]!r}")
        else:
            raise ValueError(f"{where}: {k!r} is not a trait, day or weekday")
    return dict(r)


def _group(g, n_steps, by_row):
    _dict(g, "group")
    _keys(g, {"name", "cases", "rate", "detail", "sources"}, {"name", "cases"}, "group")
    where = f"group {_name(g['name'], 'group name')!r}"
    _whole(g["cases"], f"{where} cases", least=1)
    if g.get("rate") is not None:
        _rate(g["rate"], f"{where} rate")
    detail = {}
    for k, d in _dict(g.get("detail", {}), f"{where} detail").items():
        idx = int(k) if isinstance(k, str) and k.isdigit() else k
        _step_index(idx, n_steps, f"{where} detail")
        detail[idx] = _dict(d, f"{where} detail {k}")
    if "sources" in g:
        if not by_row:
            raise ValueError(f"{where}: the case id names the source here, so one case is one source")
        _whole(g["sources"], f"{where} sources", least=1)
    return {"name": g["name"], "cases": g["cases"], "rate": g.get("rate"), "detail": detail,
            "sources": g.get("sources")}


def _draw(u, values):
    """The value whose share holds u, a number from 0 to 1."""
    total = sum(v["share"] for v in values.values())
    edge = 0.0
    for name, v in values.items():
        edge += v["share"] / total
        if u < edge:
            return name
    return name


def _pick(u, detail):
    if isinstance(detail, list):
        return detail[min(int(u * len(detail)), len(detail) - 1)]
    return detail


def _match(when, traits, day, weekday):
    for k, v in when.items():
        wanted = v if isinstance(v, list) else [v]
        have = day if k == "day" else weekday if k == "weekday" else traits.get(k)
        if have not in wanted:
            return False
    return True


def _keys(d, allowed, required, where):
    extra = sorted(set(d) - allowed)
    if extra:
        raise ValueError(f"{where}: unknown key {extra[0]!r}")
    missing = sorted(required - set(d))
    if missing:
        raise ValueError(f"{where}: missing {missing[0]!r}")


def _name(v, what):
    if not isinstance(v, str) or not NAME.match(v):
        raise ValueError(f"{what} {v!r}: lowercase letters, digits and _, starting with a letter")
    return v


def _dict(v, what):
    if not isinstance(v, dict):
        raise ValueError(f"{what}: an object")
    return v


def _list(v, what):
    if not isinstance(v, list):
        raise ValueError(f"{what}: a list")
    return v


def _number(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{what}: a number")
    return v


def _whole(v, what, *, least):
    if isinstance(v, bool) or not isinstance(v, int) or v < least:
        raise ValueError(f"{what}: a whole number, {least} or more")
    return v


def _rate(v, what):
    if not 0 <= _number(v, what) <= 1:
        raise ValueError(f"{what}: a chance from 0 to 1")
    return v


def _step_index(v, n_steps, what):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < n_steps:
        raise ValueError(f"{what}: step is a step number from 0 to {n_steps - 1}")
    return v
