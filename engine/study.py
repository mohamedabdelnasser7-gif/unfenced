"""The night study: one night's look at one agent's cases, to find what its actions did or
missed that went with a better or a worse real result, and to write each clear finding as
a lesson card through the agent's own lessons and risk check.

1. Read. Every case of the agent with a row in the window, each read up to the window's
   end (Log.window): its actions, the lessons each was given, fast and slow results, its
   source and causes.
2. Count first. How many rows of each result kind, how many cases ended good or not, how
   many are pending and how many are left out. A case is settled by its deciding result
   (the plug's decides), the last one it has. A case with none is pending, never a loss,
   whatever its age, and out of every count and lesson until its result comes (DECISIONS
   item 66): no timer settles a case. A late result comes from the tool's webhook, the tool's
   API on the night run or a person (reflection/late.py). A settled case with a cause (the plug lists the causes that
   are outside the agent) is left out of every pattern count and named with its cause.
3. Find patterns. A proposer reads a small sample of settled cases, half good and half
   not, and proposes up to LIMIT candidates: a plain pattern (something an action did or
   missed), whether it helps or hurts, the lesson line, its situation and stage tags. A
   tagger marks settled cases yes or no for each pattern, up to TAGGED of them, a seeded
   sample when there are more; it never sees a case's deciding result, nor anything logged
   after it, so it cannot mark by the answer. The proposer sees a case up to its deciding
   result too, and that result by name. Both are given to the study; the model versions
   live outside engine/. Neither sees a case id or a source: each case goes as a key, k1,
   k2 and so on for the proposer, and fresh seeded keys for each tagger call, mapped back in
   code, so a pattern cannot name a case the proposer saw.
4. The gap rule, counted in code; the model never decides the numbers. Each side, the
   cases with the pattern and the cases without, has a good rate read as Beta(1 + good,
   1 + not good), an even start. A candidate wins when the chance that the side it names
   is better is at least CHANCE, 75%, the bar decided for keeping an idea, so the study
   proposes what a trial could keep; and each side has at least MIN_CASES cases from at
   least MIN_SOURCES different sources, so one source with many cases cannot make a lesson
   alone. A tag that is not a plain yes or no leaves that case out of that pattern. With a
   few candidates a night one may pass by luck; it only starts a trial, and the trial's
   verdict on new cases decides.
5. Write. Each winner, strongest first, goes through Lessons.propose with its stage tags,
   a source line with the counts, and the texts of the cases the model read as sources, so
   copied words make it high. Risk decides: low goes on trial with no yes, as many a night
   as the study writes, at the trial level that applies (Lessons); high waits for a yes,
   unless Accept high risk is on (engine/switches.py), and then it goes on trial like a low
   one. One trial runs on a stage at a time, so a lesson whose stage is busy waits its turn.
   A line already among the agent's lessons is not written again: a live one is
   "already a lesson", a pulled one "pulled before". Lines are compared on their words
   alone, so case, accents, look alike letters and punctuation do not make a new line. A
   line close to a pulled one (the same words in any sequence, or a small rewording: CLOSE) is
   written but waits for a yes, with the pulled line named on its card, so a pulled line
   never comes back on its own, whatever the switches say.
   The source line names the counts and the first cases with the pattern.
   A lesson that failed the eval gate is a mistake too (DECISIONS item 50). While it is not live
   (it waits, or it was pulled after) and never had a trial (no person's yes took it on), its line
   counts like a pulled one: the same line is not written again ("failed the eval gate before")
   and a line close to it waits for a yes, its card naming the failed line; close here also
   means the two lines' content words are one inside the other or share NEAR_FAILED of them
   (_close). Such a line still takes the exam, so its card shows a fail too. The proposer and
   the idea part are given this agent's failed lines, the newest FAILED_GIVEN, each with what
   it broke (the first fail as one line of at most FIRST_FAIL_MAX characters, the failed checks
   with why, the cases it broke and the fixed and broken counts, from its exam row), so they
   write a different try for that pattern. A new try is a new lesson; the failed one is never rewritten
   and still waits for a person's yes. Inside an Arena run (arena/rounds.py) Study.rewrite asks the
   idea part for one new try of one failed lesson right away, given only that line and its earlier
   tries as failed, and writes it as an idea by the same rules.
6. Learn across agents. With a fit check and an adapter given, the study reads the other
   agents of the same database, in any field; the ones sharing a field come first, which
   only decides who gets the night's trial places. For each other agent it finds patterns
   on that agent's own cases and plug by the same rule, and takes its kept lessons. For
   each, the fit check answers fully, partly or not (anything else is not); for fully or
   partly the adapter rewrites it in this agent's words for its own stages, and
   Lessons.adapt writes it: its source line names the other agent and its cases or lesson,
   it passes this agent's own risk check and starts like any lesson the study writes. A
   kept lesson already adapted, in any state, is not asked again, and a line the other
   agent pulled is not brought over ("pulled before"). A write the lessons refuse is
   named on its candidate and the night goes on. Siblings come first (DECISIONS item 79):
   agents of this agent's kind that name the same owner (engine/plug.py kind and owner),
   so a new agent of a kind its owner already runs starts with what they kept. A
   sibling's line goes on trial only through this agent's eval gate: with no examiner
   on the lessons (Lessons.examiner) it waits for a yes and never starts a trial by itself.
   The shared pool comes next (DECISIONS item 83; reflection/shared.py), with a link given
   (shared): the lesson patterns of this agent's kind seen at 2 or more other owners, most
   owners first, at most LIMIT a night, each through the same fit check and adapter, and on
   trial only through this agent's eval gate as a sibling's line is (with no gate it waits
   for a yes). Its source line names the pattern and how many owners it was learned from,
   and a pattern taken before, in any state, is not asked again. The study also gives the
   pool this agent's kept lessons (the ones not from the pool), at most the link's give a
   night, each written up once; the pool keeps only clean patterns and hashed owners.
7. Ideas. With an idea part given, the study also asks for ideas: lessons with no past cases
   behind them, paths worth trying ("let's try this path"). The part reads the proposer's
   sample and the agent's lessons, and gives at most IDEAS (3) a night; any past the cap is
   named and dropped. The cap is on what the part may write, not on trials: each idea goes
   the normal way, through Lessons.propose with kind IDEA, so the risk check, the copy check
   on the cases the part read, the plug's stage check, the clash check, a yes when high and
   a trial at the level that applies, or its turn. A low risk idea starts its trial by
   itself; a high risk one waits for a yes. Ideas come after the night's patterns and the
   lessons from other agents, so a lesson with cases behind it takes a free stage first. A
   line already among the agent's lessons, or close to a pulled one, is treated as in 5. The
   counts never speak for an idea: its card says it has no past cases and is a try
   (idea_card), and only its trial decides.
8. Hand over. With a hand over track given (engine/handover.py) and a plug that names
   hands_over, the night's lost cases are also read for patterns that are another agent's
   matter: at most one short note a night per receiving agent, only from a kind seen in at
   least MIN_SOURCES sources. Every line the study would write as a lesson (in 5, 6 and 7) is
   sorted first: a line that is one of the plug's kinds is handed over and never written; a
   sort that fails holds the line for a yes.

run() returns the night's report as plain data: what was read and counted, each candidate
with its numbers, the cards written, what came from other agents, the two switches as they
read at the night's now, and notes on any part that failed. A failing part makes no lesson.
"""
import difflib
import math
import random
import re
import time
import unicodedata
from collections import Counter

from engine import exam as exam_mod
from engine import risk as risk_mod
from engine.lessons import DAY, IDEA, KEPT, MAX_LEN, PATTERN, PERSON, PULLED, WAITING, Lessons, meet, whose
from engine.log import Log
from engine.plug import SLOW

CHANCE = 0.75     # the chance the named side is better, decided item 7
MIN_CASES = 5     # cases on each side
MIN_SOURCES = 3   # different sources on each side
LIMIT = 5         # candidates the proposer may give
SAMPLE = 20       # settled cases the proposer reads
TAGGED = 200      # settled cases the tagger reads for each candidate
SHOWN = 20        # case ids a source line names
FULLY, PARTLY, NOT = "fully", "partly", "not"
GOOD, BAD, PENDING, LEFT_OUT = "good", "bad", "pending", "left out"
LESSON, KNOWN, FEW_CASES, FEW_SOURCES, NO_GAP = (
    "lesson", "already a lesson", "too few cases", "too few sources", "gap not clear")
PULLED_BEFORE = "pulled before"
NO_GATE = "a sibling's line waits for a yes: this agent has no eval gate to put it on trial through"
POOL = "pool"  # gated: a line from the shared pool across owners (see 6)
POOL_NO_GATE = "a line from the shared pool waits for a yes: this agent has no eval gate to put it on trial through"
LINEAGE = 50  # lessons a kept lesson's chain back to the pool is read through (_from_pool)
# the source line reflection/morning.py person_line gives an edited line: 'edited by <by> from lesson <id>: ...'
_EDITED_FROM = re.compile(r"^edited by .+? from lesson (\d+)")
HANDED = "handed over"  # a candidate that is another agent's matter (see 8)
FAILED_BEFORE = "failed the eval gate before"
FAILED_GIVEN = 10  # failed lines the proposer and the idea part are given a night, the newest
FAILS_GIVEN = 3   # failed checks given with each failed line
CLOSE = 0.85      # how close a line may come to a pulled one before it waits for a yes
NEAR_FAILED = 0.6  # for a failed line, the share of content words two lines may share before it waits
FIRST_FAIL_MAX = 300  # characters of a failed line's first fail given to the proposer and the idea part
# Small words left out when two lines' content words are compared (a failed line, see 5)
SMALL_WORDS = frozenset(
    "a an the and or but nor of in on at to for from by with into onto over under up down out off about "
    "is are was were be been being am do does did has have had it its this that these those them they "
    "their there then than as so if when while before after until each every all any some very just also "
    "always often ever too only first last more most less once again".split())
IDEAS = 3         # ideas the idea part may write a night. Not a cap on trials (call 1A): every
                  # low risk lesson still starts. Ideas have no cases behind them and one trial
                  # runs on a stage at a time, so more would only queue on the stages, ahead of
                  # later lessons that have cases, and lengthen the morning page.
NO_CASES = "no past cases: this is a try"  # how sure an idea's card is today


class HandedOver(ValueError):
    """A line the study would write is one of the plug's hands_over kinds (see 8): handed over to
    that agent, never written as a lesson here."""

    def __init__(self, to, kind):
        super().__init__(f"handed over to {to} ({kind}), not a lesson")
        self.to, self.kind = to, kind


class PartError(Exception):
    """A model part's own failure, in plain words that are safe to show: a note quotes it.
    Any other error is named by its type only."""


def _failed(e):
    return f"{type(e).__name__}: {e}" if isinstance(e, PartError) else type(e).__name__


def _label(part):
    """What a part says it runs on (its label), or its type's name."""
    try:
        label = getattr(part, "label", None)
    except Exception:  # a label that fails must not stop the night
        label = None
    return label if isinstance(label, str) and label else type(part).__name__


def chance_better(good_a, n_a, good_b, n_b):
    """The chance that side a's good rate is above side b's, each side read as
    Beta(1 + good, 1 + not good). Exact for whole counts: a sum of 1 + good_b terms."""
    a1, b1 = 1 + good_a, 1 + n_a - good_a
    a2, b2 = 1 + good_b, 1 + n_b - good_b
    b_wins = sum(math.exp(_lbeta(a1 + i, b1 + b2) - math.log(b2 + i) - _lbeta(1 + i, b2) - _lbeta(a1, b1))
                 for i in range(a2))
    return min(1.0, max(0.0, 1.0 - b_wins))


def _lbeta(a, b):
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


class _Case:
    """One case as the study reads it."""

    def __init__(self, key, case_id, rows, status, deciding, causes, source, text, cut=None):
        self.key, self.id, self.rows = key, case_id, rows
        self.cut = len(rows) if cut is None else cut  # the rows before the last deciding one
        self.status, self.deciding, self.causes = status, deciding, causes
        self.source, self.text = source, text


class Study:
    """One agent's night study. proposer(plug, sample, limit, known) gives candidates;
    tagger(plug, pattern, cases) gives {case key: True or False}; fit(plug, other, candidate)
    answers fully, partly or not; adapter(plug, other, candidate, fit) gives {lesson,
    situation, stages} in this agent's words. clash(plug, new, live), optional: True when a
    new lesson goes against a live one, False when not; each is {lesson, stages}. others:
    the plugs of the other agents in the same database. ideas(plug, sample, limit, known),
    optional: ideas with no past cases behind them, each {lesson, situation, stages}; at most
    idea_limit a night are written. When this agent has lessons that failed the eval gate (see 5),
    the proposer and the idea part are called with failed=[{lesson, first_fail, fails,
    broke_cases, fixed, broke}] too, and those lines are left out of known; with none, the call is
    as above."""

    def __init__(self, db, plug, *, proposer, tagger, fit=None, adapter=None, others=(), lessons=None,
                 judge=risk_mod.no_judge, limit=LIMIT, sample=SAMPLE, seed=0, clash=None, ideas=None,
                 idea_limit=IDEAS, hand_over=None, shared=None):
        self.db = db
        self.plug = plug
        self.log = Log(db, plug)
        self.lessons = Lessons(db, plug, judge=judge) if lessons is None else lessons
        if self.lessons.agent != plug.agent:
            raise ValueError("a study and its lessons belong to one agent")
        self.proposer, self.tagger, self.fit, self.adapter = proposer, tagger, fit, adapter
        self.clash = clash
        self.ideas, self.idea_limit = ideas, int(idea_limit)
        self.hand_over = hand_over  # engine/handover.py Track, or None for no hand over track (see 8)
        self.others = tuple(others)
        self.shared = shared  # reflection/shared.py Link, or None: the shared pool is not read (see 6)
        self.limit, self.sample, self.seed = int(limit), int(sample), seed
        self._failed_lines, self._given, self._given_ids = set(), [], set()  # this night's failed lines (see 5)

    def run(self, since, until, *, now=None):
        """One night's study of the cases touched in [since, until). now: when new lessons are
        added and their trials start; the clock when left out."""
        since, until = float(since), float(until)
        if not until > since:
            raise ValueError("the window ends after it starts")
        self._now = now
        at = time.time() if now is None else float(now)
        rep = {"agent": self.plug.agent, "window": {"since": since, "until": until}, "candidates": [], "dropped": [],
               "cards": [], "across": [], "ideas": [], "unread": [], "notes": [],
               "parts": {name: _label(part) for name, part in (("proposer", self.proposer), ("tagger", self.tagger),
                                                               ("fit", self.fit), ("adapter", self.adapter),
                                                               ("clash", self.clash), ("ideas", self.ideas))
                         if part is not None}}
        texts = _Texts(self.lessons)
        cases = _read(self.plug, self.log.window(since, until), until)
        rep.update(_counts(self.plug, cases))
        mine = self.lessons.mine()
        tries = self._failed_tries(mine)
        known = _known(mine, {t["lesson_id"] for t in tries})
        pulled = _pulled(mine) + [(_norm(t["lesson"]), t["lesson"]) for t in tries]
        self._failed_lines = {t["lesson"] for t in tries}
        rep["failed_given"] = [t["lesson_id"] for t in tries[:FAILED_GIVEN]]
        self._given_ids = set(rep["failed_given"])
        self._given = [{k: v for k, v in t.items() if k != "lesson_id"} for t in tries[:FAILED_GIVEN]]
        found = self._find(self.plug, cases, [les["text"] for les in mine if les["id"] not in self._given_ids],
                           texts, rep["notes"], failed=self._given)
        rep["dropped"] = found["dropped"]
        for rec, cand, sample, with_ in found["winners"]:
            if _norm(cand["lesson"]) in known:
                rec["verdict"] = known[_norm(cand["lesson"])]
                continue
            g1, n1 = rec["with"]["good"], rec["with"]["cases"]
            g0, n0 = rec["without"]["good"], rec["without"]["cases"]
            source = (f'night study of {self.plug.agent}, cases from {_day(since)} to {_day(until)}: '
                      f'"{cand["pattern"]}" {"helps" if cand["helps"] else "hurts"}; with it {g1} of {n1} ended '
                      f'{self.plug.decides.good}, without it {g0} of {n0}; {rec["with"]["sources"]} and '
                      f'{rec["without"]["sources"]} sources; chance it is better {round(rec["chance"] * 100)}%; '
                      f'cases with it: {_shown(with_)}')
            try:
                card = self._write(cand, source, [c.text for c in _unique(sample + with_)], rec, None, rep,
                                   close=_close(cand["lesson"], pulled, self._failed_lines))
            except HandedOver as e:  # another agent's matter (see 8): never a lesson here
                rec["verdict"], rec["handed_to"] = HANDED, {"agent": e.to, "kind": e.kind}
                continue
            rec["lesson_id"] = card["lesson_id"]
            known[_norm(cand["lesson"])] = KNOWN
        rep["candidates"] = found["candidates"]
        self._across(since, until, known, pulled, rep)
        self._ideas(cases, known, pulled, texts, rep, since, until)
        self._give_shared(rep)
        rep["hand_over"] = (None if self.hand_over is None else
                             self.hand_over.night(cases, texts, since, until, now=at, notes=rep["notes"]))
        rep["switches"] = self.lessons.switches.reading(at)
        return rep

    def _failed_tries(self, mine):
        """This agent's lessons that failed the eval gate and are not live (waiting, or pulled after),
        newest first, each as the parts read it (see 5) with its lesson_id. A failed lesson that
        ever had a trial (a person's yes started it or queued it) is not one: a person took it on,
        so pulled after its trial it is a pulled line like any other (review gatefb round 1,
        finding 3). Its first fail is one line of at most FIRST_FAIL_MAX characters."""
        out = []
        for les in reversed(mine):
            if les["state"] not in (WAITING, PULLED) or self._tried(les):
                continue
            row = self.lessons.exam_of(les["id"])
            if not row or row["passed"]:
                continue
            first = exam_mod.held_line(row)
            if row.get("why"):
                first = f'{first}: {row["why"]}'
            first = " ".join(first.split())[:FIRST_FAIL_MAX]
            eff = exam_mod.effect_of(row)
            out.append({"lesson_id": les["id"], "lesson": les["text"], "first_fail": first,
                        "fails": [{"case": _case_name(f), "check": f.get("check") or "", "why": f.get("why") or ""}
                                  for f in exam_mod.fails_of(row)[:FAILS_GIVEN]],
                        "broke_cases": exam_mod.broke_cases(row),
                        "fixed": None if eff is None else eff["fixed"], "broke": None if eff is None else eff["broke"]})
        return out

    def _tried(self, les):
        """The lesson ever had a trial: a trial row that started, or a person's yes that its exam
        does not still hold (an agent's lesson with a yes; a person's own line with a trial row)."""
        t = self.lessons.trial(les["id"])
        if t is not None and t.get("started_at") is not None:
            return True
        if les.get("yes_at") is None:
            return False
        return les.get("origin") != PERSON or t is not None

    def _ideas(self, cases, known, pulled, texts, rep, since, until):
        """The night's ideas, lessons with no past cases behind them, written after the patterns
        and the lessons from other agents. Each is named in rep["ideas"] as {idea, lesson_id,
        why}: why says what stopped one (the cap, a bad line, already a lesson, pulled before, a
        refused write). A failing part writes nothing."""
        if self.ideas is None:
            return
        plug = self.plug
        sample = self._pick([c for c in cases if c.status in (GOOD, BAD)])  # the proposer's sample
        try:
            raw = self.ideas(plug, [_view(plug, c, texts, blind=False) for c in sample], self.idea_limit,
                             [les["text"] for les in self.lessons.mine() if les["id"] not in self._given_ids],
                             **({"failed": self._given} if self._given else {}))
        except Exception as e:  # a failing idea part makes no lesson
            rep["notes"].append(f"{plug.agent}: the idea part failed ({_failed(e)}); no ideas")
            return
        if not isinstance(raw, list):
            rep["notes"].append(f"{plug.agent}: the idea part gave no list; no ideas")
            return
        source = (f"night study of {plug.agent}, cases from {_day(since)} to {_day(until)}: an idea to try, "
                  "with no past cases behind it")
        read = [c.text for c in sample]  # the copy check: an idea that copies a case's words is high
        for n, item in enumerate(raw):
            line = item.get("lesson") if isinstance(item, dict) else None
            rec = {"idea": line if isinstance(line, str) else repr(item)[:200], "lesson_id": None, "why": None}
            rep["ideas"].append(rec)
            if n >= self.idea_limit:
                rec["why"] = f"over the cap of {self.idea_limit} ideas a night"
                continue
            try:
                idea = _adapted(plug, item)
            except ValueError as e:
                rec["why"] = str(e)
                continue
            if _norm(idea["lesson"]) in known:
                rec["why"] = known[_norm(idea["lesson"])]
                continue
            try:
                card = self._write(idea, source, read, None, None, rep,
                                   close=_close(idea["lesson"], pulled, self._failed_lines), kind=IDEA)
            except ValueError as e:  # refused by the lessons
                rec["why"] = f"not written: {e}"
                continue
            rec["lesson_id"] = card["lesson_id"]
            known[_norm(idea["lesson"])] = KNOWN

    def rewrite(self, tries, since, until, *, now=None):
        """One new try of a lesson that failed the eval gate, in the same Arena run (arena/rounds.py;
        Mohamed 2026-11-02, "Yes now"). tries: the lesson's id, then the id of each earlier rewrite
        of it, every one failed. The idea part is asked for one line, given the cases in [since,
        until) as its sample and only these lines as failed, each with what it broke as in 5 (the
        situation and check it failed, the fixed and broken counts). The first line it gives that is
        new is written as an idea, as _ideas writes one: a line known or failed before is not
        written, and one close to a failed or pulled line waits for a yes. Returns {"idea": the line
        or None, "lesson_id": the new lesson or None, "card": its card or None, "why": what stopped
        it or None, "notes": [...]}. A failing idea part writes nothing."""
        since, until = float(since), float(until)
        self._now = now
        out = {"idea": None, "lesson_id": None, "card": None, "why": None, "notes": []}
        if self.ideas is None:
            out["why"] = "no idea part"
            return out
        plug = self.plug
        texts = _Texts(self.lessons)
        cases = _read(plug, self.log.window(since, until), until)
        mine = self.lessons.mine()
        every = self._failed_tries(mine)
        chain = [int(t) for t in tries]
        given = sorted((t for t in every if t["lesson_id"] in chain), key=lambda t: -chain.index(t["lesson_id"]))
        if not given:
            out["why"] = "no failed lesson to rewrite"
            return out
        known = _known(mine, {t["lesson_id"] for t in every})
        pulled = _pulled(mine) + [(_norm(t["lesson"]), t["lesson"]) for t in every]
        self._failed_lines = {t["lesson"] for t in every}
        self._given_ids = {t["lesson_id"] for t in given}
        self._given = [{k: v for k, v in t.items() if k != "lesson_id"} for t in given]
        sample = self._pick([c for c in cases if c.status in (GOOD, BAD)])
        try:
            raw = self.ideas(plug, [_view(plug, c, texts, blind=False) for c in sample], 1,
                             [les["text"] for les in mine if les["id"] not in self._given_ids], failed=self._given)
        except Exception as e:  # a failing idea part makes no rewrite
            out["why"] = f"the idea part failed ({_failed(e)})"
            return out
        if not isinstance(raw, list):
            out["why"] = "the idea part gave no list"
            return out
        source = (f"night study of {plug.agent}, cases from {_day(since)} to {_day(until)}: a rewrite of lesson "
                  f"{chain[0]}, which failed the eval gate ({given[0]['first_fail']}), with no past cases behind it")
        why = "the idea part gave no line"
        for item in raw:
            try:
                idea = _adapted(plug, item)
            except ValueError as e:
                why = str(e)
                continue
            out["idea"] = idea["lesson"]
            if _norm(idea["lesson"]) in known:
                why = known[_norm(idea["lesson"])]
                continue
            rep = {"cards": [], "notes": out["notes"]}
            try:
                card = self._write(idea, source, [c.text for c in sample], None, None, rep,
                                   close=_close(idea["lesson"], pulled, self._failed_lines), kind=IDEA)
            except ValueError as e:  # refused by the lessons, or another agent's matter
                why = f"not written: {e}"
                continue
            out.update(lesson_id=card["lesson_id"], card=card, why=None)
            return out
        out["why"] = why
        return out

    def _find(self, plug, cases, known, texts, notes, failed=None):
        """One agent's candidates with their numbers and verdicts, and the winners, strongest first.
        failed: this agent's failed lines for the proposer (see 5); None for another agent."""
        found = {"candidates": [], "dropped": [], "winners": []}
        settled = [c for c in cases if c.status in (GOOD, BAD)]
        if not any(c.status == GOOD for c in settled) or not any(c.status == BAD for c in settled):
            notes.append(f"{plug.agent}: no pattern search; it needs settled cases that ended good and not good")
            return found
        sample = self._pick(settled)
        try:
            raw = self.proposer(plug, [_view(plug, c, texts, blind=False) for c in sample], self.limit, list(known),
                                **({"failed": failed} if failed else {}))
        except Exception as e:  # a failing proposer makes no lesson
            notes.append(f"{plug.agent}: the proposer failed ({_failed(e)}); no candidates")
            return found
        if not isinstance(raw, list):
            notes.append(f"{plug.agent}: the proposer gave no list; no candidates")
            return found
        seen, winners = set(), []
        rng = random.Random(f"tag|{self.seed}|{plug.agent}")  # the tagger's samples and keys, drawn in turn
        for item in raw[:self.limit]:
            try:
                cand = _candidate(plug, item)
            except ValueError as e:
                found["dropped"].append({"agent": plug.agent, "candidate": repr(item)[:200], "why": str(e)})
                continue
            if _norm(cand["pattern"]) in seen:
                found["dropped"].append({"agent": plug.agent, "candidate": cand["pattern"],
                                         "why": "the same pattern as another candidate"})
                continue
            seen.add(_norm(cand["pattern"]))
            rec, with_ = self._count(plug, cand, settled, texts, notes, rng)
            found["candidates"].append(rec)
            if rec["verdict"] == LESSON:
                winners.append((rec, cand, sample, with_))
        found["winners"] = sorted(winners, key=lambda w: (-w[0]["chance"], -(w[0]["with"]["cases"] +
                                                                             w[0]["without"]["cases"])))
        return found

    def _count(self, plug, cand, settled, texts, notes, rng):
        """Tag the settled cases for the pattern (a seeded sample of TAGGED when there are more),
        then count both sides and apply the gap rule. The tagger gets fresh keys, longer than any
        read key, so it can never be handed one the proposer saw."""
        tagged = settled
        if len(settled) > TAGGED:
            picked = set(rng.sample(range(len(settled)), TAGGED))
            tagged = [c for n, c in enumerate(settled) if n in picked]
        low = 10 ** max(5, len(str(max(int(c.key[1:]) for c in settled))))
        by_key = {f"k{n}": c for n, c in zip(rng.sample(range(low, 10 * low), len(tagged)), tagged)}
        views = []
        for key, c in by_key.items():
            view = _view(plug, c, texts, blind=True)
            view["id"] = key
            views.append(view)
        try:
            tags = self.tagger(plug, cand["pattern"], views)
        except Exception as e:  # a failing tagger: every case is unknown, so no lesson
            notes.append(f"{plug.agent}: the tagger failed ({_failed(e)}); its cases count as unknown")
            tags = {}
        if not isinstance(tags, dict):
            tags = {}
        with_ = [c for k, c in by_key.items() if tags.get(k) is True]
        without = [c for k, c in by_key.items() if tags.get(k) is False]
        g1, g0 = (sum(c.status == GOOD for c in side) for side in (with_, without))
        n1, n0 = len(with_), len(without)
        s1, s0 = (len({c.source for c in side if c.source is not None}) for side in (with_, without))
        chance = chance_better(g1, n1, g0, n0) if cand["helps"] else chance_better(g0, n0, g1, n1)
        if min(n1, n0) < MIN_CASES:
            verdict = FEW_CASES
        elif min(s1, s0) < MIN_SOURCES:
            verdict = FEW_SOURCES
        elif chance < CHANCE:
            verdict = NO_GAP
        else:
            verdict = LESSON
        rec = {"pattern": cand["pattern"], "helps": cand["helps"], "lesson": cand["lesson"],
               "with": {"cases": n1, "good": g1, "sources": s1}, "without": {"cases": n0, "good": g0, "sources": s0},
               "tagged": len(tagged), "unknown": len(tagged) - n1 - n0, "chance": chance, "verdict": verdict,
               "lesson_id": None}
        return rec, with_

    def _pick(self, settled):
        """The proposer's sample: up to SAMPLE settled cases, half good and half not when there
        are enough, the same every time for the same cases and seed."""
        rng = random.Random(self.seed)
        good = [c for c in settled if c.status == GOOD]
        bad = [c for c in settled if c.status == BAD]
        rng.shuffle(good)
        rng.shuffle(bad)
        n_good = min(len(good), max(self.sample // 2, self.sample - len(bad)))
        out = good[:n_good] + bad[:min(len(bad), self.sample - n_good)]
        rng.shuffle(out)
        return out

    def _write(self, cand, source, sources, rec, origin, rep, *, source_lesson_id=None, close=None, kind=PATTERN,
               gated=False):
        """Write one lesson and add its card. close: the pulled line it comes close to; it then
        waits for a yes. gated: a sibling's line (see 6); with no examiner it waits for a yes. A lesson that goes against a live one waits for a yes too, its card
        asking "replace it?". kind: IDEA for one with no past cases behind it; its card carries
        idea_card. A lesson its exam held (Lessons(exam=...)) waits for a yes, its card's "exam"
        naming the first fail ("" when it passed or took no exam). Returns the card."""
        held = self._sort(cand, rep)  # raises HandedOver for another agent's matter (see 8)
        against = self._against(cand, rep)
        trial = close is None and against is None and not held
        if gated and trial and getattr(self.lessons, "examiner", None) is None:  # never live without the gate
            trial = False
            note = POOL_NO_GATE if gated == POOL else NO_GATE
            if note not in rep["notes"]:
                rep["notes"].append(note)
        failed_close = close is not None and close in self._failed_lines
        if close is not None:  # the yes asker sees which pulled or failed line it comes close to
            what = "a line that failed the eval gate" if failed_close else "a pulled line"
            source = f'{source}; close to {what}: "{close}"'
        if origin is None:
            lid = self.lessons.propose(cand["lesson"], cand["stages"], source=source, sources=sources, trial=trial,
                                       kind=kind, now=self._now)
        else:
            lid = self.lessons.adapt(cand["lesson"], cand["stages"], source=source, sources=sources,
                                     source_lesson_id=source_lesson_id, trial=trial, now=self._now)
        if against is not None:
            self.lessons.clash(lid, against["lesson_id"], now=self._now)
            against["with"] = lid
        les = self.lessons.get(lid)
        turn = self.lessons.waits_for(lid, self._now)
        tr = self.lessons.trial(lid)
        good = self.plug.decides.good
        card = {"lesson_id": lid, "state": les["state"], "risk": les["risk"], "risk_why": les["risk_why"],
                "situation": cand["situation"], "change": les["text"], "stages": les["stages"],
                "moves": {"result": good, "shows_in_days": _shows(self.plug, good)},
                "must_not_worsen": {"results": list(self.plug.harm.results), "about": self.plug.harm.about},
                "sure": rec["chance"] if rec else None,
                "cases": None if rec is None else {
                    "with": rec["with"]["cases"], "without": rec["without"]["cases"],
                    "total": rec["with"]["cases"] + rec["without"]["cases"],
                    "good_with": rec["with"]["good"], "good_without": rec["without"]["good"]},
                "source": les["source"], "from": origin, "close_to_pulled": None if failed_close else close,
                "close_to_failed": close if failed_close else None,
                "waits_for": turn, "replace": against,
                "level": None if tr is None else tr["level"],
                "accept_high": tr is not None and tr["accept_high"] is not None,
                "accept_high_by": None if tr is None or tr["accept_high"] is None else tr["accept_high"]["by"],
                "kind": les["kind"], "idea": idea_card(self.lessons, les) if les["kind"] == IDEA else None,
                "exam": exam_mod.held_line(self.lessons.exam_of(lid))}  # "" when it passed or took none
        rep["cards"].append(card)
        return card

    def _sort(self, cand, rep):
        """Raise HandedOver when the line is one of the plug's hands_over kinds (see 8). True when
        the sort failed, so the line waits for a yes; False when it is this agent's own."""
        if self.hand_over is None or not self.plug.hands_over:
            return False
        try:
            got = self.hand_over.sort(cand)
        except Exception as e:  # a failing sort holds the line for a yes
            rep["notes"].append(f"the hand over sort failed on a line ({_failed(e)}); it waits for a yes")
            return True
        if got is not None:
            raise HandedOver(*got)
        return False

    def _against(self, cand, rep):
        """The first live lesson on the candidate's stages that the clash check says it goes
        against, as {lesson_id, line, ask, sure}; None when none does or no check is given. An
        answer that is not True or False, or a failing check, counts as against, not sure."""
        if self.clash is None:
            return None
        new = {"lesson": cand["lesson"], "stages": list(cand["stages"])}
        for les in self.lessons.live(now=self._now):
            if not meet(cand["stages"], les["stages"]):
                continue
            try:
                answer = self.clash(self.plug, dict(new), {"lesson": les["text"], "stages": list(les["stages"])})
            except Exception as e:  # a failing clash check holds the lesson for a yes
                rep["notes"].append(f"the clash check failed on lesson {les['id']} ({_failed(e)}); counted as against")
                answer = None
            if answer is not False:
                return {"lesson_id": les["id"], "line": les["text"], "ask": "replace it?", "sure": answer is True}
        return None

    def _across(self, since, until, known, pulled, rep):
        """Learn from the other agents of the same database, in any field, the closest first."""
        others = [o for o in self.others if o.agent != self.plug.agent]
        given = {o.agent for o in others}
        rep["unread"] = [a for a in self.log.agents(since, until) if a != self.plug.agent and a not in given]
        if self.fit is None or self.adapter is None:
            rep["notes"].append("no fit check or adapter given; other agents were not read"
                                + ("" if self.shared is None else ", nor the shared pool"))
            return
        fields = set(self.plug.fields)
        linked = {les["source_lesson_id"] for les in self.lessons.mine() if les["source_lesson_id"] is not None}
        pool_read = False
        for other in sorted(others, key=lambda o: (not sibling(self.plug, o), -len(fields & set(o.fields)), o.agent)):
            gated = sibling(self.plug, other)
            if not gated and not pool_read:  # the shared pool right after the siblings (see 6)
                pool_read = True
                self._from_shared(known, pulled, rep)
            theirs = Lessons(self.db, other)
            texts = _Texts(theirs)
            cases = _read(other, self.log.window(since, until, agent=other.agent, plug=other), until)
            counts = _counts(other, cases)
            entry = {"agent": other.agent, "sibling": gated, "shared_fields": sorted(fields & set(other.fields)),
                     "read": {"cases": counts["read"]["cases"], "good": counts["decided"]["good"],
                              "bad": counts["decided"]["bad"], "pending": counts["pending"],
                              "left_out": counts["left_out"]["count"]},
                     "candidates": [], "lessons": [], "dropped": []}
            rep["across"].append(entry)
            their_lessons = theirs.mine()
            pulled_there = _pulled(their_lessons)
            found = self._find(other, cases, [les["text"] for les in their_lessons], texts, rep["notes"])
            entry["dropped"] = found["dropped"]
            for rec in found["candidates"]:
                rec.update(fit=None, why=None)
            entry["candidates"] = found["candidates"]
            for rec, cand, sample, with_ in found["winners"]:
                if _norm(cand["lesson"]) in {w for w, _ in pulled_there}:  # pulled there: never brought back here
                    rec["why"] = PULLED_BEFORE
                    continue
                ids = [c.id for c in with_]
                shown = _shown(with_)
                there = (f'"{cand["pattern"]}" {"helps" if cand["helps"] else "hurts"}; there with it '
                         f'{rec["with"]["good"]} of {rec["with"]["cases"]} ended {other.decides.good}, without it '
                         f'{rec["without"]["good"]} of {rec["without"]["cases"]}; chance it is better '
                         f'{round(rec["chance"] * 100)}%')
                public = {k: cand[k] for k in ("pattern", "lesson", "situation", "stages")}
                self._take(other, public, rec, rep, known, pulled + pulled_there, gated=gated,
                           sources=[c.text for c in _unique(sample + with_)],
                           source=lambda fit: f"adapted {fit} from {other.agent} cases {shown}: {there}",
                           origin={"agent": other.agent, "cases": ids})
            kept = [les for les in theirs.mine(KEPT) if les["id"] not in linked]
            for les in sorted(kept, key=lambda x: (-x["score"], x["id"]))[:self.limit]:
                rec = {"lesson": les["id"], "fit": None, "lesson_id": None, "why": None}
                entry["lessons"].append(rec)
                public = {"lesson": les["text"], "situation": "", "stages": les["stages"]}
                self._take(other, public, None, rep, known, pulled, sources=[], into=rec, source_lesson_id=les["id"],
                           gated=gated,
                           source=lambda fit, les=les: f'adapted {fit} from {other.agent} lesson {les["id"]}: '
                                                       f'"{les["text"]}"',
                           origin={"agent": other.agent, "lesson": les["id"]})
        if not pool_read:
            self._from_shared(known, pulled, rep)

    def _from_shared(self, known, pulled, rep):
        """The shared pool's lesson patterns of this agent's kind (see 6), each as a sibling's kept
        lesson is taken: the fit check, the adapter, then this agent's risk check and its eval gate
        (gated POOL); never a trial without the gate. rep["shared"]: what was read and taken."""
        if self.shared is None:
            return
        entry = rep["shared"] = {"read": 0, "lessons": [], "given": rep.get("shared", {}).get("given", [])}
        try:
            patterns = list(self.shared.lessons())
        except Exception as e:  # a pool that cannot be read makes no lesson; the night goes on
            rep["notes"].append(f"the shared pool was not read ({_failed(e)})")
            return
        entry["read"] = len(patterns)
        taken = {self.shared.pattern_of(les.get("source") or "") for les in self.lessons.mine()} - {None}
        other = _PoolAgent(self.plug, POOL_AGENT)
        for p in [p for p in patterns if p["id"] not in taken][:self.limit]:
            rec = {"pattern": p["id"], "owners": p["owners"], "fit": None, "lesson_id": None, "why": None}
            entry["lessons"].append(rec)
            public = {"lesson": p["text"], "situation": "", "stages": []}
            line = self.shared.source(p["id"], p["owners"])
            self._take(other, public, None, rep, known, pulled, sources=[], into=rec, gated=POOL,
                       source=lambda fit, line=line, text=p["text"]: f'adapted {fit} from the {line}: "{text}"',
                       origin={"agent": POOL_AGENT, "pool": p["id"], "owners": p["owners"]})

    def _give_shared(self, rep):
        """This agent's kept lessons into the shared pool (see 6): the ones that did not come from
        it (nor from a lesson that did, _from_pool), oldest first, at most the link's give a night
        that reach the writer. Each is written up
        once; what the pool drops is never kept. A writer that fails stops the giving for the night."""
        if self.shared is None:
            return
        entry = rep.setdefault("shared", {"read": 0, "lessons": [], "given": []})
        asked = 0
        for les in self.lessons.mine(KEPT):
            if asked >= self.shared.give or self._from_pool(les):
                continue
            try:
                got = self.shared.give_lesson(self.plug.agent, {"id": les["id"], "text": les["text"]})
            except Exception as e:  # the pool could not be written; the night goes on
                rep["notes"].append(f"the shared pool was not given lesson {les['id']} ({_failed(e)})")
                break
            asked += bool(got.get("asked"))
            if got.get("why") != "given before":
                entry["given"].append({"lesson": les["id"], "pattern": got.get("pattern"), "why": got.get("why")})
            if got.get("failed"):  # a writer that failed once is not asked again tonight
                break

    def _from_pool(self, les):
        """True when this lesson, or any lesson it came from, was taken from the shared pool: one
        brought back (lesson_returns), edited (its source names the lesson it was edited from) or
        copied from another agent's lesson (source_lesson_id) keeps its pool source, so the pool
        never counts this owner on a pattern it took. A chain longer than LINEAGE counts as from
        the pool (not given)."""
        with self.db.tx() as c:
            returns = c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lesson_returns'"
                                ).fetchone() is not None
            row = les
            for _ in range(LINEAGE):
                if self.shared.pattern_of(row.get("source") or "") is not None:
                    return True
                back = c.execute("SELECT from_id FROM lesson_returns WHERE lesson_id = ?",
                                 (row["id"],)).fetchone() if returns else None
                edited = _EDITED_FROM.match(row.get("source") or "")
                nxt = row.get("source_lesson_id") if row.get("source_lesson_id") is not None else \
                    back[0] if back is not None else int(edited.group(1)) if edited else None
                found = None if nxt is None else \
                    c.execute("SELECT id, source, source_lesson_id FROM lessons WHERE id = ?", (nxt,)).fetchone()
                if found is None:
                    return False
                row = dict(found)
        return True

    def _take(self, other, public, rec, rep, known, pulled, *, sources, source, origin, into=None,
              source_lesson_id=None, gated=False):
        """Ask the fit check and the adapter about one candidate or kept lesson of another agent,
        and write what fits. rec: the candidate's numbers there, or None for a kept lesson.
        pulled: the pulled lines an adapted line must not come close to without a yes. gated: a
        sibling's line (see 6), which starts a trial only through this agent's eval gate."""
        into = rec if into is None else into
        try:
            answer = self.fit(self.plug, other, dict(public))
        except Exception as e:  # a failing fit check is a no
            rep["notes"].append(f"the fit check failed on a {other.agent} candidate ({_failed(e)}); "
                                "counted as not")
            answer = NOT
        answer = answer if answer in (FULLY, PARTLY, NOT) else NOT
        into["fit"] = answer
        if answer == NOT:
            return
        try:
            raw = self.adapter(self.plug, other, dict(public), answer)
        except Exception as e:  # a failing adapter writes nothing
            rep["notes"].append(f"the adapter failed on a {other.agent} candidate ({_failed(e)}); "
                                "nothing written")
            into["why"] = "the adapter failed"
            return
        try:
            adapted = _adapted(self.plug, raw)
        except ValueError as e:
            into["why"] = f"the adapted lesson: {e}"
            return
        if _norm(adapted["lesson"]) in known:
            into["why"] = known[_norm(adapted["lesson"])]
            return
        try:
            card = self._write(adapted, source(answer), sources, rec, dict(origin, fit=answer), rep,
                               source_lesson_id=source_lesson_id, close=_close(adapted["lesson"], pulled,
                                                                                    self._failed_lines), gated=gated)
        except ValueError as e:  # refused by the lessons (a kept lesson pulled meanwhile, a bad line)
            into["why"] = f"not written: {e}"
            return
        into["lesson_id"] = card["lesson_id"]
        known[_norm(adapted["lesson"])] = KNOWN


POOL_AGENT = "shared_pool"  # reflection/shared.py POOL_AGENT: the name notes and links give the pool


class _PoolAgent:
    """The pool as the fit check and the adapter read the other side: an agent of this agent's own
    kind (its plug, read through) under the pool's name."""

    def __init__(self, plug, name):
        self._plug, self.agent = plug, name

    def __getattr__(self, name):
        return getattr(self._plug, name)


def sibling(plug, other):
    """Is other a sibling of plug: another agent of the same kind naming the same owner (DECISIONS
    items 51 and 79)? Agents that name no owner have no siblings."""
    return (other.agent != plug.agent and bool(plug.owner) and other.owner == plug.owner
            and (other.kind or other.agent) == (plug.kind or plug.agent))


class _Texts:
    """Lesson texts by id for one agent, read once each."""

    def __init__(self, lessons):
        self.lessons, self.seen = lessons, {}

    def __call__(self, lesson_id):
        if lesson_id not in self.seen:
            les = self.lessons.get(lesson_id)
            self.seen[lesson_id] = les["text"] if les else None
        return self.seen[lesson_id]


READ_DAYS = 7.0  # how far back a read looks when the plug gives no days


def read_days(plug):
    """How many days back a read of an agent's cases looks: the longest shows_in_days a deciding
    result of the plug gives, else READ_DAYS. Only how far back to read; it never settles a case
    (settle reads no days, DECISIONS item 66)."""
    days = [plug.results[r].shows_in_days for r in (plug.decides.good, *plug.decides.bad)]
    given = [d[1] for d in days if d is not None]
    return max(given) if given else READ_DAYS


def _shows(plug, name):
    """A result's shows_in_days as a list, or None when the plug gives none."""
    days = plug.results[name].shows_in_days
    return None if days is None else list(days)


def idea_card(lessons, les):
    """The card of an idea, a lesson with no past cases behind it: the idea, whose it is ("the
    agent's" or the person's), the result it must move and the days that result takes to show
    when the plug gives them (None when not), how many days until we know (its trial's days,
    plus the longest deciding window when every deciding result gives one; a late result is
    waited for, never timed out, DECISIONS item 66), what must not get worse, how sure today (NO_CASES) and its trial
    level. Once its trial starts these are the trial's, fixed at its start; before, the plug's
    and the level a trial would start with now."""
    plug = lessons.plug
    tr = lessons.trial(les["id"])
    if tr is not None and tr["days"] is not None:
        share, days, level = tr["share"], float(tr["days"]), tr["level"]
    else:
        share, days, level = lessons.level_now(les["id"])
    started = tr is not None and tr["good"] is not None
    good = tr["good"] if started else plug.decides.good
    deciders = (good, *(tr["bad"] if started else plug.decides.bad))
    windows = (tr["windows"] if started else None) or {
        r: _shows(plug, r) for r in deciders if r in plug.results}
    shows = windows.get(good) or (_shows(plug, good) if good in plug.results else None)
    given = [w for w in windows.values() if w is not None]
    return {"idea": les["text"], "whose": whose(les),
            "moves": {"result": good, "shows_in_days": None if shows is None else list(shows)},
            "know_in_days": days + (max(float(w[1]) for w in given) if given and len(given) == len(windows) else 0.0),
            "must_not_worsen": {"results": list(tr["harm"] if started else plug.harm.results),
                                "about": plug.harm.about},
            "sure": NO_CASES, "level": {"name": level, "share": share, "days": days}}


def settle(plug, rows, until):
    """One case from its rows, oldest first, read up to until: (status, its deciding result,
    the causes on its rows, the place of its last deciding row). Settled by its last deciding
    result; with none it is pending, never a loss, whatever its age (DECISIONS item 66: no timer
    closes a case; the webhook, the tool's API or a person brings its result, reflection/late.py),
    as a case with a row whose detail says "result_unknown" (history imported with no result file,
    reflection/importer.py) always was. A case with a cause outside the agent on any row is left
    out, settled or not: a settled one always was, and with no timer a case whose closing row
    names a cause and no deciding result would otherwise wait for ever and hold a trial's
    verdict. until is kept for the callers: rows after it are not read here, they are cut
    before."""
    deciders = (plug.decides.good, *plug.decides.bad)
    deciding = cut = None
    for i, r in enumerate(rows):
        if r["result"] in deciders:
            deciding, cut = r["result"], i
    causes = sorted({r["cause"] for r in rows if r["cause"]})
    if causes:
        status = LEFT_OUT
    elif deciding is None:
        status = PENDING
    else:
        status = GOOD if deciding == plug.decides.good else BAD
    return status, deciding, causes, cut


def _read(plug, window, until):
    """[_Case] from Log.window's {case id: rows}, keyed k1, k2 and so on as read."""
    out = []
    for n, (case_id, rows) in enumerate(window.items(), 1):
        status, deciding, causes, cut = settle(plug, rows, until)
        sources = [r["source"] for r in rows if r["source"] is not None]
        words = []
        for r in rows:
            _words(r["detail"], words)
        out.append(_Case(f"k{n}", case_id, rows, status, deciding, causes, sources[-1] if sources else None,
                         "\n".join(words), cut))
    return out


def _counts(plug, cases):
    """What one agent's study read, counted before anything else."""
    rows = [r for c in cases for r in c.rows]
    actions = Counter({name: 0 for name in plug.actions})
    actions.update(r["action"] for r in rows if r["action"] is not None)
    results = Counter({name: 0 for name in plug.results})
    results.update(r["result"] for r in rows if r["result"] is not None)
    given = Counter(i for c in cases for i in {i for r in c.rows for i in r["lessons"]})
    left = [c for c in cases if c.status == LEFT_OUT]
    return {"read": {"cases": len(cases), "rows": len(rows), "actions": dict(actions), "results": dict(results),
                     "lessons_given": dict(given)},
            "decided": {"good": sum(c.status == GOOD for c in cases), "bad": sum(c.status == BAD for c in cases)},
            "pending": sum(c.status == PENDING for c in cases),
            "left_out": {"count": len(left), "by_cause": dict(Counter(x for c in left for x in c.causes)),
                         "cases": [{"case": c.id, "result": c.deciding, "causes": c.causes} for c in left]}}


def _view(plug, case, texts, *, blind):
    """A case as the model parts read it: its key, never its id or source, and its steps up to
    its last deciding result, never that row or any after it. blind, for the tagger: no slow
    result either, and no deciding result by name."""
    steps = []
    for r in case.rows[:case.cut]:
        result = r["result"]
        if blind and result is not None and r["action"] is None:
            declared = plug.results.get(result)
            if declared is None or declared.speed == SLOW:
                continue
        step = {k: r[k] for k in ("action", "stage") if r[k] is not None}
        if result is not None:
            step["result"] = result
        if r["detail"] is not None:
            step["detail"] = r["detail"]
        given = [t for t in (texts(i) for i in r["lessons"]) if t]
        if given:
            step["lessons"] = given
        steps.append(step)
    view = {"id": case.key, "steps": steps}
    if not blind:
        view["deciding"] = case.deciding
        view["good"] = case.status == GOOD
    return view


def _candidate(plug, raw):
    """A proposer's candidate as {pattern, helps, lesson, situation, stages}; ValueError says what is wrong."""
    if not isinstance(raw, dict):
        raise ValueError("a candidate is an object")
    out = _adapted(plug, raw)
    out["pattern"] = _line(raw.get("pattern"), "pattern")
    if not isinstance(raw.get("helps"), bool):
        raise ValueError("helps: true or false")
    out["helps"] = raw["helps"]
    return out


def _adapted(plug, raw):
    """{lesson, situation, stages} for this plug; ValueError says what is wrong."""
    if not isinstance(raw, dict):
        raise ValueError("no lesson given")
    lesson = _line(raw.get("lesson"), "lesson")
    if len(lesson) > MAX_LEN:
        raise ValueError(f"lesson: {MAX_LEN} characters at most")
    if not isinstance(raw.get("stages"), list):
        raise ValueError("stages: a list")
    stages = plug.stage_tags(raw["stages"])
    situation = raw.get("situation")
    return {"lesson": lesson, "situation": _line(situation, "situation") if situation else "", "stages": stages}


def _line(v, what):
    if not isinstance(v, str) or not v.strip() or "\n" in v or "\r" in v:
        raise ValueError(f"{what}: one line of text")
    if len(v.strip()) > MAX_LEN:
        raise ValueError(f"{what}: {MAX_LEN} characters at most")
    return v.strip()


def _words(v, out):
    """Every text and number in a row's detail, in place, for the copy check."""
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        out.append(str(v))
    elif isinstance(v, dict):
        for x in v.values():
            _words(x, out)
    elif isinstance(v, list):
        for x in v:
            _words(x, out)


def _unique(cases):
    seen, out = set(), []
    for c in cases:
        if c.key not in seen:
            seen.add(c.key)
            out.append(c)
    return out


_TOKENS = re.compile(r"\w+|[^\w\s]")


def _norm(text):
    """A line's words and signs, in the risk check's one form: case, accents, look alike
    letters and sentence punctuation do not make a new line; a sign does (%, $, +, >, an
    emoji), so 10% and 10 stay two lines."""
    return " ".join(t for t in _TOKENS.findall(risk_mod.normalize(text, letters=True))
                    if t[0].isalnum() or t[0] == "_" or t in "%\u066a" or unicodedata.category(t)[0] == "S")


def _pulled(lessons):
    """[(words, line)] of the pulled lessons."""
    return [(_norm(les["text"]), les["text"]) for les in lessons if les["state"] == PULLED]


def _close(text, pulled, failed=()):
    """The pulled line this line comes close to, or None: the same words in any sequence (each
    word as many times), or a small rewording (a ratio of CLOSE or more). A line in failed (one
    that failed the eval gate, see 5) is also close when the two lines' content words (SMALL_WORDS
    left out) are one inside the other, or share NEAR_FAILED of all their content words: "Water
    beds early." and "Always water the beds early." come close to "Water the beds early in the
    morning." (review gatefb round 1, finding 4)."""
    words = _norm(text)
    same = sorted(words.split())
    for p in pulled:
        if sorted(p[0].split()) == same:
            return p[1]
    best = max(pulled, key=lambda p: difflib.SequenceMatcher(None, words, p[0]).ratio(), default=None)
    if best and difflib.SequenceMatcher(None, words, best[0]).ratio() >= CLOSE:
        return best[1]
    mine = _content(words)
    for p in pulled:
        if p[1] not in failed:
            continue
        theirs = _content(p[0])
        if mine and theirs and (mine <= theirs or theirs <= mine
                                or len(mine & theirs) / len(mine | theirs) >= NEAR_FAILED):
            return p[1]
    return None


def _content(words):
    """The content words of a line in _norm form: every word not in SMALL_WORDS."""
    return {w for w in words.split() if w not in SMALL_WORDS and w[0].isalnum()}


def _known(lessons, failed=()):
    """{line: why it is not written again}: pulled lines are "pulled before", the lines of the
    lessons named in failed (failed the eval gate, not live) "failed the eval gate before", the
    others "already a lesson"; a line both pulled or failed and standing is standing."""
    failed = set(failed)
    known = {_norm(les["text"]): PULLED_BEFORE for les in lessons if les["state"] == PULLED}
    known.update({_norm(les["text"]): FAILED_BEFORE for les in lessons if les["id"] in failed})
    known.update({_norm(les["text"]): KNOWN for les in lessons if les["state"] != PULLED and les["id"] not in failed})
    return known


def _case_name(fail):
    """A failed row kept on an exam row (engine/exam.py fails_of) as one plain case name."""
    if fail.get("situation") is None:
        return "the gate could not run"
    if fail.get("check") == exam_mod.RERUN:
        return f'rerun of past win {fail.get("name") or fail["situation"]}'
    if fail.get("check") == exam_mod.ROUND:
        return f'practice round match {fail["situation"]}' + (f' ({fail["name"]})' if fail.get("name") else "")
    name = fail.get("name")
    return f'situation {fail["situation"]}' + (f" ({name})" if name else "")


def line_known(lessons, text):
    """(lesson, why) for a line with the same words as one of lessons (the same rule as
    _known): a live or waiting one first, why KNOWN; else the newest pulled one, why
    PULLED_BEFORE; (None, None) for a new line. For a person's typed idea."""
    words = _norm(text)
    same = [les for les in lessons if _norm(les["text"]) == words]
    standing = [les for les in same if les["state"] != PULLED]
    if standing:
        return standing[0], KNOWN
    if same:
        return same[-1], PULLED_BEFORE
    return None, None


def _shown(cases):
    """The first SHOWN case ids, then how many more."""
    ids = [c.id for c in cases]
    return ", ".join(ids[:SHOWN]) + (f" and {len(ids) - SHOWN} more" if len(ids) > SHOWN else "")


def _day(t):
    return time.strftime("%d %b %Y", time.gmtime(t))
