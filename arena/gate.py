"""The eval gate (new, 2026-10-30; DECISIONS item 8): a new lesson takes the exam, then an Arena
rerun of past won matches with the lesson handed, before it can be used.

Gate(examiner, ...) has the examiner's own shape, callable(text, stages) -> engine.exam.Result,
so it goes where the exam goes: reflection/night.py sales_exam, which the night study and the
Morning page both use. wrap() hands them a Fresh, which builds a new Gate for each exam from the
past wins and the call count as they are then. The exam runs first and stops at its first fail,
as before. When it passes, each past win that can be rerun (pick: arena/run.py past_wins, newest
first, at most MAX_RERUNS) is played again: the same persona, the customer's same first line, the
same customer prompt (by its fingerprint saved with the match), the persona model going on from
there and the Sales agent with the new lesson handed first. A past win that is now lost is a
regression and holds the lesson (no regression on past wins), with an "arena" row naming the
match, the verdict and the turn it quotes. The rerun stops at its first loss. A rerun the model
call cap stops, or a model that does not answer (arena/match.py VOID), holds the lesson too (fail
closed, as an exam that could not run), with a row that says which.

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
from engine import exam as engine_exam
from arena import factcheck, match as match_mod, run as run_mod, verdict

PART = "arena"
SKIPPED = "arena skipped"
CHECK = engine_exam.RERUN  # "arena_rerun": a held lesson's line reads "failed the Arena rerun of past wins"
MAX_RERUNS = 5
FAILED_CHECKS = "it failed a fact check when it was played"
NO_PROMPT = "it was saved with no customer prompt fingerprint"
PROMPT_GONE = "the customer prompt it was played with is not available (moved, changed or refused)"


def _prompt_of(win):
    """The customer prompt a win was played with, or None when it cannot be had again."""
    sha = win.get("prompt_sha")
    if sha == match_mod.GENERIC_SHA:
        return match_mod.GENERIC_PROMPT
    path = win.get("prompt_file")
    if not isinstance(path, str) or not path:
        return None
    try:
        text = match_mod.load_prompt(path)
    except (match_mod.PromptRefused, OSError, ValueError):
        return None
    return text if match_mod.prompt_sha(text) == sha else None


def pick(wins, most=MAX_RERUNS):
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
            prompt = _prompt_of(win)
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
    def __init__(self, examiner, *, wins, agent_model, customer_model, calls, kept=None, fact_checks=True,
                 max_reruns=MAX_RERUNS):
        self.examiner, self.kept, self.calls = examiner, kept, calls
        self.reruns, self.skipped = pick(wins, max_reruns)
        self.wins = [w for w, _ in self.reruns]
        self.agent_model, self.customer_model = calls.model(agent_model), calls.model(customer_model)
        self.facts = fact_checks

    def __call__(self, text, tags):
        result = self.examiner(text, tags)
        if not result.passed:
            return result
        from reflection.exam import _Lessons
        rows, before = list(result.rows), self.calls.taken
        pairs = list(getattr(result, "pairs", None) or [])  # the exam's, then one a rerun judged
        rows += [engine_exam.Row(None, str(w.get("id")), SKIPPED, True, "", why) for w, why in self.skipped]
        for i, (past, prompt) in enumerate(self.reruns, 1):
            persona = past.get("persona")
            if not isinstance(persona, dict):
                rows.append(engine_exam.Row(i, str(past.get("id")), PART, False, CHECK, "its persona card was not saved"))
                break
            try:
                m = match_mod.play(persona, agent_model=self.agent_model, customer_model=self.customer_model,
                                   prompt=prompt, lessons=_Lessons(self.kept, (text, tuple(tags))),
                                   seed=past.get("id"), opening=match_mod.first_line(past), checker=factcheck.check,
                                   stop=verdict.closed)
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
            judged = verdict.judge(m, facts=self.facts)
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
    examiner runs alone (nothing to rerun)."""

    def __init__(self, examiner, kept, *, state, agent_model=None, customer_model=None, cap=run_mod.DEFAULT_CAP):
        self.examiner, self.kept, self.state, self.cap = examiner, kept, state, cap
        self.agent_model, self.customer_model = agent_model, customer_model

    def gate(self):
        """A Gate on the past wins as they are now, or None when there is none."""
        wins = run_mod.past_wins(self.state)
        if not wins:
            return None
        if self.agent_model is None or self.customer_model is None:
            from kit import model as model_mod
            self.agent_model = self.agent_model or model_mod.Model()
            self.customer_model = self.customer_model or model_mod.Model()
        return Gate(self.examiner, wins=wins, agent_model=self.agent_model, customer_model=self.customer_model,
                    calls=run_mod.Calls(self.state / run_mod.CALLS_FILE, self.cap), kept=self.kept)

    def __call__(self, text, tags):
        g = self.gate()
        return self.examiner(text, tags) if g is None else g(text, tags)


def wrap(examiner, kept, *, db, agent_model=None, customer_model=None, cap=run_mod.DEFAULT_CAP):
    """The examiner with the Arena rerun after it (Fresh), reading the past wins next to the
    agent's database (db, its path; arena/run.py state_dir: the matches, the call count and the
    stuck item live there, never in a shared temp folder) at each exam; the examiner as it is when
    db is None (an in-memory database has no folder)."""
    if db is None or str(db) == ":memory:":
        return examiner
    return Fresh(examiner, kept, state=run_mod.state_dir(db), agent_model=agent_model, customer_model=customer_model,
                 cap=cap)
