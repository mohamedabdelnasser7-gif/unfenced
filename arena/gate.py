"""The eval gate (new, 2026-10-30; DECISIONS item 8): a new lesson takes the exam, then an Arena
rerun of past won matches with the lesson handed, before it can be used.

Gate(examiner, ...) has the examiner's own shape, callable(text, stages) -> engine.exam.Result,
so it goes where the exam goes: reflection/night.py sales_exam, which the night study and the
Morning page both use. wrap() hands them a Fresh, which builds a new Gate for each exam from the
past wins and the call count as they are then. The exam runs first and stops at its first fail,
as before. When it passes, each past win that can be rerun (pick: arena/run.py past_wins, newest
first, at most MAX_RERUNS) is played again: the same persona, the customer's same first line, the
same customer prompt (by its fingerprint saved with the match), the persona model going on from
there and the Sales agent with the new lesson handed first. An agent Quick start built takes the same
gate (TurnGate, wrap_turn; DECISIONS item 59): its past wins are the practice matches arena/practice.py
saved in its own folder, each played again with arena/practice.py play (the practice customer prompt,
by its fingerprint) and judged by arena/good.py against the agent's card, the call count the one
beside the database its practice runs share. A past win that is now lost is a
regression and holds the lesson (no regression on past wins), with an "arena" row naming the
match, the verdict and the turn it quotes. The rerun stops at its first loss. A rerun the model
call cap stops, or a model that does not answer (arena/match.py VOID), holds the lesson too (fail
closed, as an exam that could not run), with a row that says which.

A correction's practice round (DECISIONS item 70). A correction a user sends on a built agent's page
takes the exam and the rerun above (FreshTurn.correction). For an agent whose good result can take
more than one message, the exam's good check reads "not reached" on both sides and cannot see a
correction help, so the correction then plays one practice round before it may go live as a
hotfix (CorrectionRound): ROUND_MATCHES fresh practice matches (arena/practice.py play, the
customer model writing every line, the correction handed first), each judged by arena/good.py
against the agent's card. It passes only when every match is won. A loss holds the correction
with a "practice round" row naming the match; the cap, a model that does not answer or practice
customers that cannot be had hold it too (fail closed). The round needs_round when the agent's
case starts with the agent, when it has no practice win yet (nothing shows its good result fits
one message), or when any of its wins was reached after the first turn. An agent whose every win
was reached at the first turn keeps the exam only hotfix. The round writes no match to
arena-matches.jsonl, no Morning item and no case, and makes no pair.

A past win is skipped, never rerun, when it failed a fact check when it was played (won with the
fact checks off), when it has no prompt fingerprint, or when the prompt it was played with cannot
be had again (the generic prompt by its fingerprint, else the file saved with the match, read
again and refused unless its fingerprint is the same). Each skipped win is an "arena skipped" row
that passes, and skipped_note() says it in one plain line for the night report and the page.

The counts (DECISIONS item 27, engine/exam.py Pair): the result keeps the exam's pairs and adds
one for each rerun the verdict judged, right before (it was a win) and right after only when it
is won again. So a rerun can add to "broke", never to "fixed"; a rerun that never got judged (no
persona card, the cap, a model error) is no pair, and it still holds the lesson as above.
"""
from pathlib import Path

from engine import exam as engine_exam
from arena import factcheck, match as match_mod, run as run_mod, verdict
from kit.model import ModelError

PART = "arena"
SKIPPED = "arena skipped"
CHECK = engine_exam.RERUN  # "arena_rerun": a held lesson's line reads "failed the Arena rerun of past wins"
MAX_RERUNS = 5
ROUND_PART = "practice round"
ROUND_CHECK = engine_exam.ROUND  # "practice_round": a held correction's line reads "failed the practice round"
ROUND_MATCHES = 2
FAILED_CHECKS = "it failed a fact check when it was played"
NO_PROMPT = "it was saved with no customer prompt fingerprint"
PROMPT_GONE = "the customer prompt it was played with is not available (moved, changed or refused)"


def _prompt_of(win, prompts=None):
    """The customer prompt a win was played with, or None when it cannot be had again. prompts: {sha:
    prompt} known by fingerprint alone (the generic one when None)."""
    sha = win.get("prompt_sha")
    known = {match_mod.GENERIC_SHA: match_mod.GENERIC_PROMPT} if prompts is None else prompts
    if sha in known:
        return known[sha]
    path = win.get("prompt_file")
    if not isinstance(path, str) or not path:
        return None
    try:
        text = match_mod.load_prompt(path)
    except (match_mod.PromptRefused, OSError, ValueError):
        return None
    return text if match_mod.prompt_sha(text) == sha else None


def pick(wins, most=MAX_RERUNS, prompts=None):
    """The past wins to rerun, newest first, at most `most`: ([(win, prompt)], [(win, why skipped)])."""
    reruns, skipped = [], []
    for win in reversed(wins):
        if len(reruns) >= most:
            break
        prompt = None
        if any(isinstance(t, dict) and t.get("failed") for t in win.get("turns") or []):
            why = FAILED_CHECKS
        elif not isinstance(win.get("prompt_sha"), str) or not win["prompt_sha"]:
            why = NO_PROMPT
        else:
            prompt = _prompt_of(win, prompts)
            why = None if prompt is not None else PROMPT_GONE
        if why is None:
            reruns.append((win, prompt))
        else:
            skipped.append((win, why))
    return reruns, skipped


def skipped(result):
    """{why: [match ids]} of the past wins a gate result skipped."""
    out = {}
    for r in getattr(result, "rows", None) or []:
        if r.part == SKIPPED:
            out.setdefault(r.why, []).append(r.name)
    return out


def skipped_note(got):
    """One plain line on the skipped past wins, from a gate result or {why: count or ids}; "" for none."""
    counts = skipped(got) if hasattr(got, "rows") else dict(got or {})
    counts = {why: len(n) if isinstance(n, (list, set, tuple)) else int(n) for why, n in counts.items()}
    counts = {why: n for why, n in counts.items() if n > 0}
    if not counts:
        return ""
    total = sum(counts.values())
    parts = "; ".join(f"{n} because {why}" for why, n in sorted(counts.items()))
    return f"The Arena rerun skipped {total} past win{'' if total == 1 else 's'}: {parts}."


class Gate:
    prompts = None  # the customer prompts known by fingerprint alone: the generic one

    def __init__(self, examiner, *, wins, agent_model, customer_model, calls, kept=None, fact_checks=True,
                 max_reruns=MAX_RERUNS):
        self.examiner, self.kept, self.calls = examiner, kept, calls
        self.reruns, self.skipped = pick(wins, max_reruns, self.prompts)
        self.wins = [w for w, _ in self.reruns]
        self.agent_model, self.customer_model = calls.model(agent_model), calls.model(customer_model)
        self.facts = fact_checks

    def _play(self, past, persona, prompt, text, tags):
        """One past win played again with the new lesson handed first: the match, arena/match.py shape."""
        from reflection.exam import _Lessons
        return match_mod.play(persona, agent_model=self.agent_model, customer_model=self.customer_model,
                              prompt=prompt, lessons=_Lessons(self.kept, (text, tuple(tags))),
                              seed=past.get("id"), opening=match_mod.first_line(past), checker=factcheck.check,
                              stop=verdict.closed)

    def _judge(self, m):
        return verdict.judge(m, facts=self.facts)

    def __call__(self, text, tags):
        result = self.examiner(text, tags)
        if not result.passed:
            return result
        rows, before = list(result.rows), self.calls.taken
        pairs = list(getattr(result, "pairs", None) or [])  # the exam's, then one a rerun judged
        rows += [engine_exam.Row(None, str(w.get("id")), SKIPPED, True, "", why) for w, why in self.skipped]
        for i, (past, prompt) in enumerate(self.reruns, 1):
            persona = past.get("persona")
            if not isinstance(persona, dict):
                rows.append(engine_exam.Row(i, str(past.get("id")), PART, False, CHECK, "its persona card was not saved"))
                break
            try:
                m = self._play(past, persona, prompt, text, tags)
            except run_mod.CapReached:
                m = None
            if m is None or self.calls.reached:
                why = (f"{self.calls.problem}; it counts as the cap reached" if self.calls.problem
                       else "the Arena call cap is reached")
                rows.append(engine_exam.Row(None, "", PART, False, engine_exam.NOT_RUN, why))
                break
            if m.get("ended") == match_mod.VOID:
                rows.append(engine_exam.Row(None, "", PART, False, engine_exam.NOT_RUN,
                                            f"a model error stopped the rerun: {m.get('error') or ''}"))
                break
            try:
                judged = self._judge(m)
            except run_mod.CapReached:
                rows.append(engine_exam.Row(None, "", PART, False, engine_exam.NOT_RUN, "the Arena call cap is reached"))
                break
            except ModelError as e:  # a model judge that did not answer: no verdict, so the lesson is held
                rows.append(engine_exam.Row(None, "", PART, False, engine_exam.NOT_RUN,
                                            f"a model error stopped the rerun: {match_mod.plain(str(e))}"))
                break
            q = judged["quote"]
            why = "" if judged["won"] else f"was won, now lost: {judged['why']} (turn {q['turn']}, {q['who']}: {q['text']})"
            rows.append(engine_exam.Row(i, str(past.get("id")), PART, judged["won"], "" if judged["won"] else CHECK, why))
            pairs.append(engine_exam.Pair(f"rerun {past.get('id')}", True, bool(judged["won"])))  # won before: a past win
            if not judged["won"]:
                break
        n_arena = sum(r.part == PART for r in rows[len(result.rows):])
        passed = all(r.passed for r in rows) and n_arena == len(self.reruns)
        return engine_exam.Result(passed=passed, rows=rows, calls=int(result.calls) + self.calls.taken - before,
                                  pairs=pairs)


class Fresh:
    """The examiner with the Arena rerun after it, built fresh for each exam: every call reads the
    past wins and the call count again (gate()), so a page or a night that stays open reruns the
    wins saved after it opened and counts against the cap as it stands. With no past win yet the
    examiner runs alone (nothing to rerun). calls: a call count already open (the Arena's own,
    between rounds, arena/rounds.py), so the rerun takes from the run's count; else a new count on
    the file next to the database, read as it is at each exam."""

    def __init__(self, examiner, kept, *, state, agent_model=None, customer_model=None, cap=run_mod.DEFAULT_CAP,
                 calls=None):
        self.examiner, self.kept, self.state, self.cap = examiner, kept, state, cap
        self.agent_model, self.customer_model = agent_model, customer_model
        self.calls = calls

    def gate(self):
        """A Gate on the past wins as they are now, or None when there is none."""
        wins = run_mod.past_wins(self.state)
        if not wins:
            return None
        if self.agent_model is None or self.customer_model is None:
            from kit import model as model_mod
            self.agent_model = self.agent_model or model_mod.Model()
            self.customer_model = self.customer_model or model_mod.Model()
        calls = self.calls if self.calls is not None else run_mod.Calls(self.state / run_mod.CALLS_FILE, self.cap)
        return Gate(self.examiner, wins=wins, agent_model=self.agent_model, customer_model=self.customer_model,
                    calls=calls, kept=self.kept)

    def __call__(self, text, tags):
        g = self.gate()
        return self.examiner(text, tags) if g is None else g(text, tags)


class TurnGate(Gate):
    """The gate for an agent Quick start built (kit/turn.py): its past practice wins played again with
    arena/practice.py play and judged by arena/good.py against its card."""

    def __init__(self, examiner, *, agent, judge_model, **kw):
        from arena import practice
        self.agent, self.prompts = agent, {practice.PROMPT_SHA: practice.PROMPT}
        super().__init__(examiner, **kw)
        self.judge_model = self.calls.model(judge_model)

    def _play(self, past, persona, prompt, text, tags):
        from arena import practice
        from reflection import turn_exam
        first = match_mod.first_line(past)
        lessons = turn_exam.hand(self.kept, (text, tuple(tags)), self.agent.stage.name, first)
        return practice.play(self.agent, persona, agent_model=self.agent_model, customer_model=self.customer_model,
                             seed=past.get("id"), lessons=lessons, opening=first)

    def _judge(self, m):
        from arena import good
        return good.judge(m, self.agent.card, self.judge_model, facts=self.facts, plug=self.agent.plug)


def _won_at(win):
    """The turn a past win reached the good result at (its quote), or None when that cannot be read."""
    q = win.get("quote")
    n = q.get("turn") if isinstance(q, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) else None


def needs_round(agent, wins):
    """Does a correction for this built agent play a practice round before it may go live? Yes when its
    case starts with the agent, when it has no practice win yet, or when any win was reached after the
    first turn (or at a turn that cannot be read). No only when every win was reached at the first turn."""
    from arena import good
    if good.case_of(agent.card)["starts"] == "agent":
        return True
    if not wins:
        return True
    return any(_won_at(w) != 1 for w in wins)


class CorrectionRound:
    """One practice round for a correction (DECISIONS item 70): ROUND_MATCHES fresh practice matches
    with the correction handed first, on the agent's practice customers (arena/madeup.py for_agent:
    the saved ones, else new ones), the held out ones that can reach the good result first. Every
    model is taken from calls. Writes no match, no item and no case."""

    def __init__(self, *, agent, folder, kept, agent_model, customer_model, judge_model, calls,
                 matches=ROUND_MATCHES, fact_checks=True):
        self.agent, self.folder, self.kept, self.calls = agent, Path(folder), kept, calls
        self.agent_model, self.customer_model = calls.model(agent_model), calls.model(customer_model)
        self.judge_model = calls.model(judge_model)
        self.matches, self.facts = int(matches), fact_checks

    def cards(self):
        """The practice customers the round plays, in order: the held out ones that can reach the good
        result, then the rest that can, each once, repeated when there are fewer than the matches."""
        from arena import madeup
        cards, _ = madeup.for_agent(self.folder, self.agent.name, self.agent.card, self.customer_model,
                                    madeup.owner_cards(self.folder))
        winnable = [c for c in cards if run_mod.can_buy(c)]
        try:
            held = [c["id"] for c in run_mod.split(cards)[1] if run_mod.can_buy(c)]
        except run_mod.Refused:
            held = []
        order = [c for c in winnable if c["id"] in held] + [c for c in winnable if c["id"] not in held]
        return [order[i % len(order)] for i in range(self.matches)] if order else []

    def _not_run(self, why):
        return engine_exam.Row(None, "", ROUND_PART, False, engine_exam.NOT_RUN, why)

    def _cap(self):
        return self._not_run(f"{self.calls.problem}; it counts as the cap reached" if self.calls.problem
                             else "the Arena call cap is reached")

    def rows(self, text, tags):
        """The round's rows: one a match played, stopping at the first loss, or one NOT_RUN row."""
        from arena import good, practice
        from reflection import turn_exam
        try:
            cards = self.cards()
        except run_mod.CapReached:
            return [self._cap()]
        except ModelError as e:
            return [self._not_run(f"a model error stopped the practice round: {match_mod.plain(str(e))}")]
        except (run_mod.Refused, OSError, ValueError, RecursionError) as e:
            return [self._not_run(f"the practice customers could not be had: {match_mod.plain(str(e))}")]
        if not cards:
            return [self._not_run("no practice customer can reach the good result")]
        rows = []
        for i, card in enumerate(cards, 1):
            about = " ".join(str(x) for x in card.get("want") or [] if isinstance(x, str))
            lessons = turn_exam.hand(self.kept, (text, tuple(tags)), self.agent.stage.name, about)
            try:
                m = practice.play(self.agent, card, agent_model=self.agent_model, customer_model=self.customer_model,
                                  seed=f"correction-{i}", lessons=lessons)
            except run_mod.CapReached:
                m = None
            if m is None or self.calls.reached:
                rows.append(self._cap())
                break
            if m.get("ended") == match_mod.VOID:
                rows.append(self._not_run(f"a model error stopped the practice round: {m.get('error') or ''}"))
                break
            try:
                judged = good.judge(m, self.agent.card, self.judge_model, facts=self.facts, plug=self.agent.plug)
            except run_mod.CapReached:
                rows.append(self._cap())
                break
            except ModelError as e:  # a judge that did not answer: no verdict, so the correction is held
                rows.append(self._not_run(f"a model error stopped the practice round: {match_mod.plain(str(e))}"))
                break
            q = judged["quote"]
            why = "" if judged["won"] else f"lost: {judged['why']} (turn {q['turn']}, {q['who']}: {q['text']})"
            rows.append(engine_exam.Row(i, str(card.get("id")), ROUND_PART, bool(judged["won"]),
                                        "" if judged["won"] else ROUND_CHECK, why))
            if not judged["won"]:
                break
        return rows

    def __call__(self, result, text, tags):
        """result (the exam and rerun, passed) with the round's rows added; passed only when every match
        was played and won."""
        before = self.calls.taken
        rows = self.rows(text, tags)
        played = [r for r in rows if r.part == ROUND_PART and r.situation is not None]
        passed = bool(result.passed) and all(r.passed for r in rows) and len(played) == self.matches
        return engine_exam.Result(passed=passed, rows=list(result.rows) + rows,
                                  calls=int(result.calls) + self.calls.taken - before,
                                  pairs=list(getattr(result, "pairs", None) or []))


class FreshTurn(Fresh):
    """Fresh for a built agent: the past wins are its own practice wins in its folder (state), the call
    count the one beside the database (reports) that its practice runs share. correction() is what a
    correction on the agent's page takes: the same, then the practice round when needs_round."""

    def __init__(self, examiner, kept, *, agent, state, reports, judge_model=None, **kw):
        super().__init__(examiner, kept, state=Path(state), **kw)
        self.agent, self.reports, self.judge_model = agent, Path(reports), judge_model

    def _wins(self):
        return [w for w in run_mod.past_wins(self.state) if w.get("agent") == self.agent.name]

    def _models(self):
        if self.agent_model is None or self.customer_model is None or self.judge_model is None:
            from kit import model as model_mod
            self.agent_model = self.agent_model or model_mod.Model()
            self.customer_model = self.customer_model or model_mod.Model()
            self.judge_model = self.judge_model or model_mod.Model()

    def _calls(self):
        return self.calls if self.calls is not None else run_mod.Calls(self.reports / run_mod.CALLS_FILE, self.cap)

    def gate(self):
        wins = self._wins()
        if not wins:
            return None
        self._models()
        return TurnGate(self.examiner, agent=self.agent, judge_model=self.judge_model, wins=wins,
                        agent_model=self.agent_model, customer_model=self.customer_model, calls=self._calls(),
                        kept=self.kept)

    def correction(self, text, tags):
        """A correction's gate: the exam and the rerun, then, when they pass and needs_round, the
        practice round (CorrectionRound)."""
        result = self(text, tags)
        if not result.passed or not needs_round(self.agent, self._wins()):
            return result
        self._models()
        return CorrectionRound(agent=self.agent, folder=self.state, kept=self.kept, agent_model=self.agent_model,
                               customer_model=self.customer_model, judge_model=self.judge_model,
                               calls=self._calls())(result, text, tags)


def wrap_turn(examiner, kept, *, agent, state, reports, agent_model=None, customer_model=None, judge_model=None,
              cap=run_mod.DEFAULT_CAP):
    """A built agent's examiner with the Arena rerun of its past practice wins after it (FreshTurn):
    state, the agent's folder (arena-matches.jsonl, arena/practice.py); reports, the folder beside the
    database (arena-calls.json)."""
    return FreshTurn(examiner, kept, agent=agent, state=state, reports=reports, agent_model=agent_model,
                     customer_model=customer_model, judge_model=judge_model, cap=cap)


def wrap(examiner, kept, *, db, agent_model=None, customer_model=None, cap=run_mod.DEFAULT_CAP):
    """The examiner with the Arena rerun after it (Fresh), reading the past wins next to the
    agent's database (db, its path; arena/run.py state_dir: the matches, the call count and the
    stuck item live there, never in a shared temp folder) at each exam; the examiner as it is when
    db is None (an in-memory database has no folder)."""
    if db is None or str(db) == ":memory:":
        return examiner
    return Fresh(examiner, kept, state=run_mod.state_dir(db), agent_model=agent_model, customer_model=customer_model,
                 cap=cap)
