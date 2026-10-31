"""Scripted model parts for the simulated scenarios: what a model would answer in the night
study, written in each scenario's script, so a run gives the same answers every time and
makes no model call. They only propose, tag, fit and rewrite; engine/study.py still counts
and decides everything, as it does with the real parts in reflection/study.py.

Each part is built from the scenarios of every agent in the run and answers by the agent it
is called for (a study also asks about the other agents' cases).

A scenario's script:
  candidates  [{pattern, helps, lesson, situation, stages, tag}]: what the proposer gives
              every night, whatever sample it reads. tag says how the tagger marks a case,
              reading only the steps it is shown:
                {key, is: value}   yes when a step's detail has key with that value;
                {key, has: words}  yes when a step's detail text under key holds the words;
                {key, lacks: words} yes when steps have key and none holds the words.
              Otherwise no, and a case with no step naming key gets no tag at all.
  adapt       {another agent's lesson line: {fit, lesson, situation, stages}}: the fit
              check's answer for this agent and the adapter's rewrite in its words. A line
              not listed fits "not".

judge_says_low is the scripted risk judge: low for every lesson, the worst case, so only
the code check and the counts stand between a bad source and a trial.
"""
import copy

from engine import risk

TAG_KINDS = ("is", "has", "lacks")


class _Scripts:
    def __init__(self, scenarios):
        self.by_agent = {}
        for sc in scenarios:
            script = sc.get("script") or {}
            self.by_agent[sc["agent"]] = {"candidates": list(script.get("candidates", [])),
                                          "adapt": dict(script.get("adapt", {}))}
        self.calls = []

    def script(self, agent):
        return self.by_agent.get(agent, {"candidates": [], "adapt": {}})


class Proposer(_Scripts):
    """proposer(plug, sample, limit, known, failed=()): the agent's scripted candidates, without
    their tags; failed lines (engine/study.py) change nothing in a script."""

    def __call__(self, plug, sample, limit, known, failed=()):
        self.calls.append({"agent": plug.agent, "sample": len(sample), "limit": limit, "known": list(known)})
        return [{k: copy.deepcopy(v) for k, v in c.items() if k != "tag"}
                for c in self.script(plug.agent)["candidates"]]


class Tagger(_Scripts):
    """tagger(plug, pattern, cases): {case key: True or False} by the candidate's tag rule."""

    def __call__(self, plug, pattern, cases):
        self.calls.append({"agent": plug.agent, "pattern": pattern, "cases": copy.deepcopy(cases)})
        rule = next((c.get("tag") for c in self.script(plug.agent)["candidates"] if c.get("pattern") == pattern),
                    None)
        if not isinstance(rule, dict):
            return {}
        out = {}
        for view in cases:
            got = tag(rule, view)
            if got is not None:
                out[view["id"]] = got
        return out


class Fit(_Scripts):
    """fit(plug, other, candidate): the script's answer for this agent, "not" for a line not listed."""

    def __call__(self, plug, other, cand):
        self.calls.append({"agent": plug.agent, "other": other.agent, "candidate": copy.deepcopy(cand)})
        entry = self.script(plug.agent)["adapt"].get(cand.get("lesson"))
        return entry.get("fit", "not") if isinstance(entry, dict) else "not"


class Adapter(_Scripts):
    """adapter(plug, other, candidate, fit): the script's rewrite in this agent's words, or None."""

    def __call__(self, plug, other, cand, fit):
        self.calls.append({"agent": plug.agent, "other": other.agent, "candidate": copy.deepcopy(cand), "fit": fit})
        entry = self.script(plug.agent)["adapt"].get(cand.get("lesson"))
        if not isinstance(entry, dict):
            return None
        return {k: copy.deepcopy(entry[k]) for k in ("lesson", "situation", "stages") if k in entry}


def parts(*scenarios):
    """The four scripted parts for a run over these scenarios: proposer, tagger, fit, adapter."""
    return Proposer(scenarios), Tagger(scenarios), Fit(scenarios), Adapter(scenarios)


def tag(rule, view):
    """One case's tag for a rule: True, False, or None when no step names the rule's key."""
    key = rule.get("key")
    kinds = [k for k in TAG_KINDS if k in rule]
    if not isinstance(key, str) or len(kinds) != 1:
        raise ValueError("a tag rule is {key, and one of is, has or lacks}")
    kind, want = kinds[0], rule[kinds[0]]
    seen = [s["detail"][key] for s in view["steps"] if isinstance(s.get("detail"), dict) and key in s["detail"]]
    if not seen:
        return None
    if kind == "is":
        return any(v == want for v in seen)
    held = any(isinstance(v, str) and want.casefold() in v.casefold() for v in seen)
    return held if kind == "has" else not held


def judge_says_low(text, high_about, low_about):
    """The scripted judge: low for everything. The code check runs before it."""
    return risk.LOW
