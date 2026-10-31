"""The night runner: one night study of one agent on its real cases. A person runs it; it is
not scheduled.

    python3 -m reflection.night [--plug sales/plug.json] [--days N] [--db PATH] [--json]

It opens the agent's database (data/ascent.db unless --db names another), loads the agent's
plug and every other plug in the repo (<folder>/plug.json), and runs the engine's night study
(engine/study.py) once over the last N days with the Meta model parts: the proposer and the
tagger on the study route (Muse Wonder on the Meta Model API, or Muse Spark Open with
META_STUDY_ROUTE=open), and the fit check, the adapter and the risk judge on Muse Spark Open
(reflection/study.py, reflection/judge.py). The other agents' plugs are given, so the study also
reads their cases and kept lessons. The idea part, on the study route too, gives at most 3
ideas a night: lessons with no past cases behind them, each going the normal way to a trial.

N comes from the plug unless --days gives it: twice the longest time the plug's deciding
results take to show, so a case acted on early in the window has had time to settle.

Before the study it runs the night's trial check (engine/trial.py): each lesson on trial is
kept, pulled or paused on its own cases, serious results ping, and lessons waiting their turn
start on the stages that came free. The study then writes the night's new lessons. For the
Sales agent, whose plug names an exam (reflection/exam.py), each new lesson that would start its
trial takes the exam first, on Muse Spark Open: a fail holds it, waiting for a yes, and its card
names the first fail; the report counts the exam's runs, model calls and held lessons. Each card
whose lesson took the gate with its counts names, under it, the cases it fixed and broke and
McNemar's p-value (engine/exam.py; reported only, pass or fail stays the gate's). Last, it
takes the night's snapshot of the agent's lessons (reflection/snapshots.py); the report names
it, what changed since the night before, and the command that rolls back to it.

A lesson the gate failed goes back into Reflection (DECISIONS item 50): its exam row keeps every
failed check with why and the cases it broke (engine/exam.py), and the next night's study gives
the proposer and the idea part this agent's failed lines with what each broke, so the next try
is a different line (engine/study.py, step 5). A line close to a failed one waits for a yes, its
card naming the failed line. The failed lesson itself is never rewritten and never goes live on
its own: it still waits for a yes on the Morning page.

It prints the night's report in plain lines (--json prints it as data) and saves the whole
report as JSON next to the database, as night-<agent>-<time>.json (data/ is gitignored).
The report's links tie each new lesson back to where it came from: every case that had its
pattern (all of them, where the lesson's source line names the first 20), or the other
agent's kept lesson it was adapted from, and which agents the night read and which it did not.
They also name each lesson of the report a person brought back (on the morning page or in a
rollback) with the pulled lesson it was brought back from. The report lists fast reflection's
notes on the night's cases (engine/fast.py, fast_notes), each by the case id the night read it
under; a note is never a lesson, so a lesson from that case still goes the night's way.

The night also hands over (engine/handover.py, DECISIONS items 6, 12 and 19): for a plug that
names hands_over (the Sales agent's names the Marketing agent), the night's lost and quiet cases
are read for the kinds of pattern that are the receiving agent's matter, and at most one short
note a night goes to it, only from a kind seen in at least 3 sources. The spotter and the note
writer are on the study route; the writer never sees a case. Every line the night would write as
a lesson is sorted first, so a kind like a joke is handed over and never becomes a lesson. The
note is saved where the receiving agent reads it (handover.received) and the report shows it as one
quiet line; nothing waits for a yes.

For the personal assistant, the night first sends its Arena new practice days (DECISIONS items
30, 32; assistant/arena.py take_finished): each day the user lived and finished that is worth
practising (the user corrected something, or the code found a missed urgent item, a clash or
another miss) is cleaned and joins the Arena's pool in the assistant's folder; easy days are
skipped. The report counts them as practice_days.
Then it takes the new mode step (assistant/newmode.py,
DECISIONS item 36): the day's moments that fit no mode, kept in the assistant's folder
(--assistant-state, data/assistant unless named, the Arena's folder), may become one mode card
after the Arena plays the user's past days (the real days in that folder's pool) without and with
it. The card is a data file next to the database, mode-assistant-<time>.json; the report names it
as mode_card (None when the night wrote none), and the Morning page shows it for the user's yes,
rename or drop. The Arena's calls count against its daily cap; a model that does not answer, or
the cap, stops the step with no card and the report names why (mode_card_stopped).

For the Sales agent, and any agent of its kind, the night then grows its practice customers
(arena/grow.py, DECISIONS items 30, 32, 47, 48, 51): the window's new real chats, labelled from
the chat itself, the lost and hard ones cleaned and tagged with the persona recipe (--recipe, a
private file outside the repo), join the owner's pool, shared by that owner's agents of the same
kind only, so tomorrow's Arena faces them. The tagger's calls count against the Arena's daily cap.
The report names the counts as practice (practice.stopped says why, with no recipe given too, or
the step's error by its type when it failed: the report is still saved).

It refuses to start without the keys its parts need and names the missing variable. It
never prints a key: a part that fails is named in the notes by its plain reason only.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from engine import exam as engine_exam
from engine import plug as plug_mod
from engine import handover
from engine.fast import FastNotes
from engine.lessons import TRYING
from engine.lessons import Lessons as EngineLessons
from engine.study import SHOWN, Study
from engine.trial import Trials
from kit import env
from kit import model as model_mod
from kit.db import DEFAULT_PATH, Db
from reflection import PLUG as SALES
from reflection import judge as judge_mod
from reflection import snapshots
from reflection import study as parts

ROOT = Path(__file__).resolve().parent.parent
DAY = 86400.0
DEFAULT_PLUG = ROOT / "sales" / "plug.json"


class Refused(Exception):
    """The night cannot run as asked; the message names what is missing, never a value."""


MODEL_KEYS = "META_API_KEY or BASETEN_API_KEY"


def missing_keys():
    """The env names the night still needs. The fit check, the adapter and the judge take either
    model key (kit/model.py keyed_legs), so META_API_KEY alone runs them; the study route needs
    its own key too, META_API_KEY on wonder, the default. MODEL_KEYS when neither model key is set."""
    try:
        route = parts.study_route()
    except model_mod.ModelError as e:
        raise Refused(str(e)) from None
    missing = []
    if route.key_env != model_mod.OPEN.key_env and not env.get(route.key_env):
        missing.append(route.key_env)
    if not model_mod.has_key() and not missing:  # META_API_KEY named above is either key already
        missing.append(MODEL_KEYS)
    return missing


def default_days(plug):
    """Twice the longest time a deciding result of the plug takes to show; at least one day."""
    deciding = (plug.decides.good, *plug.decides.bad)
    longest = max(plug.results[name].shows_in_days[1] for name in deciding)
    return max(1.0, 2.0 * float(longest))


class LinkedStudy(Study):
    """The engine's night study, keeping on each winning candidate the id of every case that
    had its pattern, so the report can link each new lesson to all of its cases."""

    def _find(self, plug, cases, known, texts, notes, failed=None):
        found = super()._find(plug, cases, known, texts, notes, failed=failed)
        for rec, _cand, _sample, with_ in found["winners"]:
            rec["cases_with"] = [c.id for c in with_]
        return found


def links(rep, others=(), lessons=None):
    """Each new lesson of the night with what it links back to, and the agents read.
    lessons: one per card, {lesson_id, state, from_agent, cases, from_lesson, waits_for}: the agent whose
    cases or lesson it came from, every case that had its pattern there, and the kept lesson it
    was adapted from (None for a lesson found on cases), and the trials it waits its turn behind.
    agents_read: this agent, then each
    other agent read. agents_not_read: agents in the log with no plug given, and plugs given
    but not read. brought_back: {lesson_id, from_lesson} for each lesson the report names (a
    card, a trial checked, a trial started from its turn) that a person brought back, from the
    engine's back_links(); empty without lessons."""
    found = {}
    for rec in rep["candidates"] + [c for a in rep["across"] for c in a["candidates"] + a["lessons"]]:
        if rec.get("lesson_id") is not None:
            found[rec["lesson_id"]] = rec
    lessons_out = []
    for card in rep["cards"]:
        origin = card["from"] or {}
        rec = found.get(card["lesson_id"], {})
        lessons_out.append({"lesson_id": card["lesson_id"], "state": card["state"],
                            "from_agent": origin.get("agent", rep["agent"]),
                            "cases": list(rec.get("cases_with", origin.get("cases", []))),
                            "from_lesson": origin.get("lesson"), "waits_for": list(card.get("waits_for") or [])})
    read = [rep["agent"]] + [a["agent"] for a in rep["across"]]
    not_read = set(rep["unread"]) | {o.agent for o in others if o.agent not in read}
    return {"lessons": lessons_out, "agents_read": read, "agents_not_read": sorted(not_read),
            "brought_back": _brought_back(rep, lessons)}


def _brought_back(rep, lessons):
    if lessons is None:
        return []
    checked = rep.get("trials") or {"trials": [], "started": []}
    named = {c["lesson_id"] for c in rep["cards"]} | {t["lesson_id"] for t in checked["trials"]} | set(
        checked["started"])
    out = []
    for lid in sorted(named):
        came = lessons.back_links(lid)["from"]
        if came is not None:
            out.append({"lesson_id": lid, "from_lesson": came})
    return out


def other_plugs(plug, root=ROOT):
    """Every other agent's plug in the repo: <folder>/plug.json, one per agent."""
    out = []
    for path in sorted(Path(root).glob("*/plug.json")):
        other = plug_mod.load(path)
        if other.agent != plug.agent:
            out.append(other)
    return out


def night(db, plug, *, days=None, until=None, others=None, judge=None, proposer=None, tagger=None, fit=None,
          adapter=None, ideas=None, exam=None, spotter=None, note_writer=None):
    """Run one night study over [until - days, until). Parts left out are the Meta ones, except
    the idea part: main() gives the Meta one; left out here, the night asks for no ideas, so a
    night run with scripted parts never reaches a model for ideas. exam: makes the gate before a
    trial from the night's lessons, exam(lessons) -> callable(text, stages) -> engine.exam.Result;
    main() gives the Sales agent's when its plug has an exam; left out, no exam runs, so a night
    with scripted parts never reaches a model for it either. spotter and note_writer: the hand
    over track's parts (engine/handover.py); main() gives the Meta ones; left out, nothing is
    handed over and no line is sorted.
    The trial check runs first, at until. Returns the study's report, with the runner's own
    window line, the links and the trial check ("trials") added."""
    days = default_days(plug) if days is None else float(days)
    if not days > 0:
        raise Refused("--days must be more than 0")
    until = time.time() if until is None else float(until)
    since = until - days * DAY
    judge = judge_mod.Judge() if judge is None else judge
    if plug.agent == SALES.agent:
        # The Sales agent's own bindings move a database made before the engine into its tables.
        from reflection.lessons import Lessons
        from reflection.results import Results
        Results(db)
        lessons = Lessons(db, judge=judge)
    else:
        lessons = EngineLessons(db, plug, judge=judge)
    counted = None
    if exam is not None:
        counted = lessons.examiner = Counted(exam(lessons))
    checked = Trials(db, plug, lessons=lessons).check(until)
    others = other_plugs(plug) if others is None else others
    hand = (handover.Track(db, plug, spotter=spotter, writer=note_writer, others=others)
            if spotter is not None and note_writer is not None and plug.hands_over else None)
    study = LinkedStudy(db, plug, proposer=proposer or parts.Proposer(), tagger=tagger or parts.Tagger(),
                        fit=fit or parts.FitCheck(), adapter=adapter or parts.Adapter(),
                        others=others, lessons=lessons, ideas=ideas, hand_over=hand)
    rep = study.run(since, until, now=until)
    rep["days"] = days
    rep["parts"]["judge"] = _judge_label(judge)
    rep["trials"] = checked
    rep["links"] = links(rep, study.others, lessons)
    rep["snapshot"] = snapshots.after_night(db, plug.agent, until)
    # Fast reflection's notes on the night's cases, by the same case id (engine/fast.py): none is a
    # lesson, and a lesson from these cases still goes the night's own way.
    rep["fast_notes"] = FastNotes(db, plug).linked(study.log.window(since, until), now=until)
    rep["exam"] = None if counted is None else {"runs": counted.runs, "calls": counted.calls, "held": counted.held}
    if counted is not None and counted.skipped:
        rep["exam"]["skipped"] = {why: len(ids) for why, ids in sorted(counted.skipped.items())}
    for card in rep["cards"]:  # the gate's counts on each card whose lesson took a counted gate
        eff = engine_exam.effect_of(lessons.exam_of(card["lesson_id"])) if card.get("lesson_id") is not None else None
        if eff is not None:
            card["gate"] = eff
    return rep


class Counted:
    """The night's examiner, counting its runs, the model calls they made and the lessons held.
    One that raises counts as held: the engine holds its lesson (engine/lessons.py). skipped: the
    past wins the Arena rerun skipped ({why: match ids}, arena/gate.py), each counted once."""

    def __init__(self, examiner):
        self.examiner, self.runs, self.calls, self.held = examiner, 0, 0, 0
        self.skipped = {}

    def __call__(self, text, stages):
        self.runs += 1
        try:
            result = self.examiner(text, stages)
        except Exception:
            self.held += 1
            raise
        self.calls += int(result.calls)
        self.held += not result.passed
        from arena import gate
        for why, ids in gate.skipped(result).items():
            self.skipped.setdefault(why, set()).update(ids)
        return result


def sales_exam(plug, db=None):
    """The exam main() gives the night: the Sales agent's examiner on Muse Spark Open, when the plug
    is the Sales agent's and names an exam; None otherwise (another agent's exam has no binding yet).
    db: the agent's database path; the Arena wins the gate reruns are the ones saved next to it."""
    if plug.exam is None or plug.agent != SALES.agent:
        return None
    from reflection import exam as exam_mod
    from arena import gate  # the eval gate: the exam, then the Arena rerun of past wins (DECISIONS item 8)
    # count=True: the gate also counts the cases each lesson fixed and broke (DECISIONS item 27)
    return lambda lessons: gate.wrap(exam_mod.Examiner(plug, kept=lessons, model=model_mod.Model(), count=True),
                                     lessons, db=db)


def _judge_label(judge):
    try:
        m = judge.model
        return f"{m.route.name} {m.model_id}"
    except Exception:
        return type(judge).__name__


ASSISTANT = "assistant"  # the agent whose night takes the new mode step (assistant/newmode.py AGENT)


def assistant_state(value=None):
    """The assistant's folder, resolved: data/assistant unless named; refused inside the repo
    outside data/, as the assistant's Arena refuses it (its moments are the user's own words)."""
    from arena import paths
    state = Path(value or paths.DATA / ASSISTANT).expanduser().resolve()
    if paths.inside_repo(state) and not paths.within(state, paths.DATA):
        raise Refused("the assistant's folder sits inside the repo outside data/")
    return state


def practice_days(state):
    """The assistant's finished days worth practising, cleaned, join its Arena's pool; returns the counts."""
    from assistant import arena as assistant_arena
    return assistant_arena.take_finished(state)


def new_mode(db_path, state):
    """The assistant's new mode step: at most one mode card next to the database, from the kept
    moments, tested in the Arena on the real days in the folder's pool. Returns (the card's path
    or None, why the step stopped or None)."""
    from arena import run as arena_run
    from assistant import arena as assistant_arena
    from assistant import newmode
    calls = arena_run.Calls(Path(state) / arena_run.CALLS_FILE, arena_run.DEFAULT_CAP)
    made = []

    def play(day, added):
        if not made:  # the model only when a day is played
            made.append(calls.model(model_mod.Model()))
        return assistant_arena.play_day(day, model=made[0], added=added)[2]["won"]

    try:
        card = newmode.night(state, assistant_arena.Pool(state).real, play, reports=Path(db_path).resolve().parent)
    except (model_mod.ModelError, arena_run.CapReached) as e:
        return None, type(e).__name__
    return card, None


def save(rep, db_path):
    """The report as JSON next to the database. Returns the file's path."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(rep["window"]["until"]))
    path = Path(db_path).resolve().parent / f"night-{rep['agent']}-{stamp}.json"
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def text(rep, plug):
    """The night's report as plain lines."""
    w = rep["window"]
    good = plug.decides.good
    d = rep["decided"]
    lines = [f'Night study of {rep["agent"]}, {_day(w["since"])} to {_day(w["until"])} ({_n(rep["days"])} days)',
             "  parts: " + "; ".join(f"{k} {v}" for k, v in rep["parts"].items()),
             f'  read {rep["read"]["cases"]} cases: settled {d["good"] + d["bad"]} ({d["good"]} {good}, {d["bad"]} not, '
             f'{d["past_window"]} of them past their window), pending {rep["pending"]}, '
             f'left out {rep["left_out"]["count"]}, not counted' + _causes(rep["left_out"])]
    lines.extend(_trial_lines(rep["trials"]))
    if rep.get("exam"):
        e = rep["exam"]
        lines.append(f'  exam before a trial: lessons examined {e["runs"]}, held {e["held"]}, model calls {e["calls"]}')
        if e.get("skipped"):
            from arena import gate
            lines.append("  " + gate.skipped_note(e["skipped"]))
    lines.append(f'  candidates {len(rep["candidates"])}')
    for c in rep["candidates"]:
        lines.append(f'    - "{c["pattern"]}": {c["verdict"]}; ' + _numbers(c, good))
    lines.append(f'  lesson cards {len(rep["cards"])}')
    for card in rep["cards"]:
        came = f' (adapted from {card["from"]["agent"]})' if card["from"] else ""
        if card.get("idea"):
            came = f' ({card["idea"]["whose"]} idea, {card["idea"]["sure"]})'
        lines.append(f'    - "{card["change"]}"{came}: {_state(card)}')
        if card.get("gate"):
            lines.append("      " + engine_exam.effect_line(card["gate"]))
    if rep.get("ideas"):
        lines.append(f'  ideas {len(rep["ideas"])}')
        lines.extend(f'    - "{i["idea"]}": ' + (f'lesson {i["lesson_id"]}' if i["lesson_id"] is not None else i["why"])
                     for i in rep["ideas"])
    for a in rep["across"]:
        r = a["read"]
        lines.append(f'  from {a["agent"]}: read {r["cases"]} cases ({r["good"]} good, {r["bad"]} not, '
                     f'{r["pending"]} pending); candidates {len(a["candidates"])}, kept lessons asked {len(a["lessons"])}')
    if rep["unread"]:
        lines.append("  not read, no plug given: " + ", ".join(rep["unread"]))
    lk = rep["links"]
    lines.append(f'  links {len(lk["lessons"]) + len(lk["brought_back"])}')
    lines.extend(f"    - {_link(link)}" for link in lk["lessons"])
    lines.extend(f'    - lesson {b["lesson_id"]}: brought back from lesson {b["from_lesson"]} by a person'
                 for b in lk["brought_back"])
    lines.append("  agents read: " + ", ".join(lk["agents_read"]) + "; not read: " +
                 (", ".join(lk["agents_not_read"]) or "none"))
    lines.extend(_fast_lines(rep.get("fast_notes") or []))
    lines.extend("  " + handover.line(n) for n in (rep.get("hand_over") or {}).get("notes", []))
    lines.append("  " + switches_line(rep["switches"]))
    lines.extend(_snapshot_lines(rep["snapshot"]))
    if rep["notes"]:
        lines.append("  notes:")
        lines.extend(f"    - {n}" for n in rep["notes"])
    return "\n".join(lines)


def _trial_lines(checked):
    """The night's trial check as plain lines: each trial's state and why, each ping, and the
    lessons that started from their turn."""
    lines = [f'  trials checked {len(checked["trials"])}']
    lines.extend(f'    - lesson {e["lesson_id"]} "{e["line"]}": {e["status"]}. {e["why"]}' for e in checked["trials"])
    for p in checked["pings"]:
        lines.append(f'  ping: lesson {p["lesson_id"]}, case {p["case"]}, row {p["row"]}: {p["result"]}')
    if checked["started"]:
        lines.append("  started from their turn: lesson " + ", ".join(str(i) for i in checked["started"]))
    return lines


def _fast_lines(notes):
    """Fast reflection's notes on the night's cases, each by its case id; nothing when none."""
    if not notes:
        return []
    lines = [f"  fast notes on the night's cases {len(notes)} (none is a lesson; the case id links each "
             "to the cases read above)"]
    for n in notes:
        said = f'"{n["text"]}"' if n["text"] is not None else f'no note ({n["why"]})'
        lines.append(f'    - case {n["case"]}: {said}, {n["state"]}')
    return lines


def _snapshot_lines(snap):
    """The night's snapshot and how to roll back to it, then what changed since the night before.
    The command names the plug and the database main() ran with, else the agent's name."""
    cmd = snapshots.command(snap["plug"], snap["night"], snap.get("db"))
    return [f'  snapshot of the night of {snap["night"]}: {snapshots.size(snap["lessons"], snap["live"])}, hash '
            f'{snap["hash"][:snapshots.SHORT]}; to roll back to it: {cmd}',
            "  " + snapshots.diff_text(snap["changes"], snap["since"])]


def _link(link):
    """One link as a plain line: the lesson, its state and where it came from."""
    if link["state"] == TRYING:
        state = "on trial"
    elif link.get("waits_for"):
        state = "waits its turn"
    else:
        state = "waits for a yes"
    if link["from_lesson"] is not None:
        came = f'adapted from {link["from_agent"]} lesson {link["from_lesson"]}'
    else:
        ids = link["cases"]
        more = f" and {len(ids) - SHOWN} more (all in the saved report)" if len(ids) > SHOWN else ""
        came = f'from {link["from_agent"]} cases {", ".join(ids[:SHOWN])}{more}'
    return f'lesson {link["lesson_id"]} ({state}): {came}'


def _numbers(c, good):
    w, wo = c["with"], c["without"]
    return (f'with it {w["good"]} of {w["cases"]} {good} ({w["sources"]} sources), without it {wo["good"]} of '
            f'{wo["cases"]} ({wo["sources"]} sources); chance it is better {_pct(c["chance"])}')


def switches_line(sw):
    """The two switches as the night read them, in one plain line."""
    acc = sw["accept_high"]
    if acc["on"]:
        high = f'on, turned on by {acc["by"]}' + (f', until {_when(acc["until"])}' if acc["until"] else "")
    elif acc["ran_out"]:
        high = f'off, its days ran out on {_when(acc["until"])}'
    else:
        high = "off"
    return (f'trial level {sw["level"]}: {round(sw["share"] * 100)}% of cases for {sw["days"]} days; '
            f'Accept high risk {high}')


def _when(t):
    return time.strftime("%d %b %Y %H:%M UTC", time.gmtime(t))


def _state(card):
    """The card's lesson state in one line. A lesson under Accept high risk is named that way,
    with who switched it on, never as a person's yes."""
    accept = ("Accept high risk" + (f' (switched on by {card["accept_high_by"]})' if card.get("accept_high_by") else "")
              if card.get("accept_high") else None)
    if card["state"] == "trying":
        return (f'on trial at the {card["level"]} level' if card.get("level") else "on trial") + (
            f", started under {accept}" if accept else "")
    close = _close_words(card)
    if card.get("exam"):  # the close words stay when the exam fails too (review gatefb round 2, finding 4)
        return (f'waits for a yes: {card["exam"]}' + (f" ({close})" if close else "")
                + "; a person's Yes on its card starts it anyway")
    if close:
        return f"waits for a yes ({close})"
    if card.get("replace"):
        r = card["replace"]
        return f'waits for a yes: replace lesson {r["lesson_id"]} "{r["line"]}"?'
    if card.get("waits_for"):
        return "waits its turn behind lesson " + ", ".join(str(i) for i in card["waits_for"]) + (
            f"; it waits under {accept} and starts with no yes only if the switch is still on at its turn, "
            "else it waits for a yes" if accept else "")
    return f'waits for a yes ({card["risk"]} risk: {card["risk_why"]})'


def _close_words(card):
    """The words naming the pulled or failed line a card's lesson comes close to; "" for none."""
    if card.get("close_to_pulled"):
        return f'close to the pulled line "{card["close_to_pulled"]}"'
    if card.get("close_to_failed"):  # DECISIONS item 50: close to a line the eval gate failed
        return f'close to the line "{card["close_to_failed"]}", which failed the eval gate'
    return ""


def _pct(x):
    n = round(x * 100)
    return "over 99%" if n >= 100 else f"{n}%"


def _n(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def _day(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _causes(left):
    """The plug's causes the left-out cases carry, by name with a count: the plug's words, not ours.
    Not every cause is outside the agent (a plug may leave out a miss its user did not correct)."""
    by = left.get("by_cause") or {}
    return (" (" + ", ".join(f"{k} {v}" for k, v in sorted(by.items())) + ")") if by else ""


def main(argv=None, *, until=None):
    """until: the window's end, the clock when left out (tests give a fixed one)."""
    ap = argparse.ArgumentParser(description="One night study of one agent on its real cases, with the Meta parts.")
    ap.add_argument("--plug", default=str(DEFAULT_PLUG), help="the agent's plug file (default: the Sales agent's)")
    ap.add_argument("--days", type=float, default=None, help="the window in days (default: from the plug)")
    ap.add_argument("--db", default=str(DEFAULT_PATH), help="the agent's database (default: data/ascent.db)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--assistant-state", default=None,
                    help="the personal assistant's folder: moments, modes and past days (default: data/assistant)")
    ap.add_argument("--recipe", default=None,
                    help="the persona recipe, outside the repo: real chats become practice customers (arena/grow.py)")
    args = ap.parse_args(argv)
    env.load()
    try:
        missing = missing_keys()
    except Refused as e:
        print(f"Not run: {e}.", file=sys.stderr)
        return 2
    if missing:
        print("Not run: missing in .env: " + ", ".join(missing), file=sys.stderr)
        return 2
    if not Path(args.db).is_file():
        print(f"Not run: no database at {args.db}. The Sales agent makes it when it first runs.", file=sys.stderr)
        return 2
    plug = plug_mod.load(args.plug)
    try:
        state = assistant_state(args.assistant_state) if plug.agent == ASSISTANT else None
    except Refused as e:
        print(f"Not run: {e}.", file=sys.stderr)
        return 2
    db = Db(args.db)
    try:
        rep = night(db, plug, days=args.days, until=until, ideas=parts.Ideas(), exam=sales_exam(plug, args.db),
                    spotter=parts.Spotter(), note_writer=parts.NoteWriter())
    except Refused as e:
        print(f"Not run: {e}.", file=sys.stderr)
        return 2
    finally:
        db.close()
    rep["snapshot"]["plug"] = args.plug  # the rollback command names what this run was given
    if Path(args.db).resolve() != DEFAULT_PATH.resolve():
        rep["snapshot"]["db"] = args.db
    if state is not None:
        rep["practice_days"] = practice_days(state)
        card, stopped = new_mode(args.db, state)
        rep["mode_card"] = None if card is None else str(card)
        if stopped:
            rep["mode_card_stopped"] = stopped
    # ---- practice customers from the window's real chats (arena/grow.py; DECISIONS items 30, 48, 51)
    from arena import grow
    if grow.kind_of(plug) == grow.DEFAULT_KIND:
        try:
            rep["practice"] = grow.night(args.db, plug, args.recipe, rep["window"]["since"], rep["window"]["until"])
        except Exception as e:  # the lessons went in already: the report and its rollback line are still saved
            rep["practice"] = {"kind": grow.kind_of(plug), "stopped": f"failed: {type(e).__name__}"}
    # ---- end of the practice step
    path = save(rep, args.db)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(text(rep, plug))
        if rep.get("practice_days"):
            p = rep["practice_days"]
            print(f"  new practice days for the Arena: {p['added']} added, {p['easy']} easy days skipped")
        if rep.get("mode_card"):
            print(f"  a new mode card waits on the Morning page: {rep['mode_card']}")
        if rep.get("practice"):
            print("  " + grow.line(rep["practice"]))
        print(f"  saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
