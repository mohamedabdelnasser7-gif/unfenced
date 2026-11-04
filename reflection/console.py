"""The console, /console?agent=<name> on the page server (reflection/morning.py, reflection/pages.py):
the technical view of one agent's loop, read only from what the engine already writes. Nothing here
changes a lesson; the one answer it takes (an operator correction) goes through Morning.correct.

    the bar      the loop as tabs (ALL STAGES, ARENA, DEPLOYMENT, REFLECTION), the running stage marked:
                 the stage of the newest record of the last RECENT seconds, or the Arena while a Try
                 again runs (Morning.trying)
    the cards    Arena win rate of the newest run's matches, the newest exam with its safety and
                 "hidden from the agent", lessons kept and on trial, model calls against the caps
    the views    ALL STAGES: one timeline of every record, tagged by stage, newest last. ARENA: the
                 newest run's matches, or the lesson exams with their failed situations. DEPLOYMENT:
                 the live turns from the chats store, its lessons in play from the trace. REFLECTION:
                 the night reports, exams and lessons as a log, beside the lessons table.
    writes.json  the same records as JSON as they were saved, on every tab
    Corrections  every correction, tagged user or operator, with its status and exam

A row opens the side panel (row=<key>): Saw, Decided, Raw. What the engine did not save says
NOT_SAVED and is never filled in. A lost match, a failed exam situation or a flagged live turn shows
the customer message, the agent reply, why, and the Operator correction box (POST /console/correct).

Sources: the newest Arena item (Morning.read_arena) and its run's matches (arena-matches.jsonl, its
tail only), the Try again item, lesson_exams, lessons (held: engine.lessons.wants_yes_ids), the night
reports (Morning.read_reports), chats and steps (real channels only) with the trace rows, the latest
connection rows and the Calls file (arena/run.py CALLS_FILE).

The page has one inline script, allowed by its hash in this page's own CSP (csp()): every POLL_MS it
fetches the same address with the X-Poll header and swaps the [data-live] parts, never the side panel,
keeping a scrolled pane at the bottom when it was there. With no script the page works and does not refresh.
"""
import base64
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from engine import exam as exam_mod
from engine import lessons as lessons_mod
from engine.lessons import KEPT, PULLED, TRYING, WAITING
from kit import connections as conn_mod
from kit import sample as sample_mod

NOT_SAVED = "not saved for this turn"
RECENT = 600            # seconds: a record this new marks its stage as running
MATCH_TAIL = 1_000_000  # bytes read from the end of arena-matches.jsonl
MAX_JSON = 64 * 1024 * 1024  # bytes; a bigger saved file is skipped
SHOWN = 300             # records on the timeline and in writes.json, the newest
RAW_CUT = 4000          # characters of one record's JSON shown in writes.json
CHATS = 40              # live chats read, the newest
POLL_MS = 4000
FULL_CAP = 400          # arena/rounds.py FULL_CAP: model calls one lesson's full exam may take
OPERATOR = "operator"   # who a correction sent here is saved as (Morning.correct by=)
STAGES = {"A": "ARENA", "D": "DEPLOYMENT", "R": "REFLECTION"}
VIEWS = (("all", "ALL STAGES"), ("arena", "ARENA"), ("deploy", "DEPLOYMENT"), ("reflect", "REFLECTION"))
VIEW_STAGE = {"arena": "A", "deploy": "D", "reflect": "R"}
SUBS = {"all": ("all", "A", "D", "R"), "arena": ("m", "e")}
FILTERS = ("all", "bad", "ok")
PANES = ("saw", "dec", "raw")
ROW = re.compile(r"^(?:m\.[\w-]{1,80}|e\.\d{1,9}(?:\.\d{1,4})?|t\.[\w-]{1,64}\.\d{1,6}|l\.\d{1,9})$")
_JSON_KEY = re.compile(r'(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)')
_JSON_NUM = re.compile(r'(:\s)(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?|true|false|null)(?=,?$)', re.M)


def h(v):
    from reflection import morning as mo
    return mo.h(v)


# ---- what the engine saved ------------------------------------------------------------------------

def collect(m, agent, now=None):
    """Everything the console shows for one agent, read from what the engine wrote: a dict of the
    cards' numbers, the rows of each view and records, the timeline: each {key, stage, at, seq, text,
    raw, row}, at the saved time (None when none was saved), row the side panel key or None."""
    now = time.time() if now is None else now
    out = {"agent": agent, "now": now, "records": [], "matches": [], "exams": [], "turns": [], "lessons": [],
           "corrections": [], "problems": []}
    rec = _Records(out["records"])
    _arena(m, agent, out, rec)
    _db(m, agent, out, rec)
    _nights(m, agent, rec)
    out["calls"] = _calls(m, now)
    sample = getattr(m, "sample_data", None)  # a built agent's sample data, in the card's words
    out["sample"] = sample_mod.words(sample(agent)) if callable(sample) else ""
    out["gate"] = m.gate(agent) if agent in m.plugs else None
    out["records"].sort(key=lambda r: (r["sort"], r["seq"]))
    out["running"] = running(m, agent, out["records"], now)
    return out


class _Records:
    def __init__(self, into):
        self.into = into

    def add(self, stage, at, text, raw, row=None, sort=None):
        self.into.append({"key": row or f"r{len(self.into)}", "stage": stage, "at": _num(at), "seq": len(self.into),
                          "text": text, "raw": raw, "row": row, "sort": _num(sort if sort is not None else at) or 0})


def running(m, agent, records, now):
    """The stage running now: the Arena while a Try again runs, else the stage of the newest record of
    the last RECENT seconds, else None."""
    trying = getattr(m, "trying", None)
    if trying is not None and trying(agent):
        return "A"
    fresh = [r for r in records if r["at"] is not None and 0 <= now - r["at"] <= RECENT]
    return max(fresh, key=lambda r: (r["at"], r["seq"]))["stage"] if fresh else None


def _arena(m, agent, out, rec):
    items, problems = m.read_arena()
    out["problems"] += problems
    item = items.get(agent)
    out["arena"] = item
    if item is None or m.reports is None:
        return
    raw = _read_json(m.reports / item["file"])
    start = _run_start(item["run"])
    folder = m.reports if agent == _sales() else m.reports / "agents" / agent
    for i, x in enumerate(_matches(folder / "arena-matches.jsonl", item["run"])):
        x = _match_row(x, item["run"])
        out["matches"].append(x)
        rec.add("A", None, f"match {x['id']} {'won' if x['won'] else 'lost'}"
                + (f": {x['why']}" if x["why"] else ""), x["raw"], row=f"m.{x['id']}", sort=start)
    rec.add("A", item["at"], f"Arena run {item['run']} saved: {item['line']}", raw if raw is not None
            else {"file": item["file"], "saved": NOT_SAVED})
    retry = item.get("retry")
    if retry:
        said = ", ".join(f"{r['card']} {r['result'].replace('_', ' ')}" for r in retry.get("results") or [])
        rec.add("A", retry.get("at"), f"Try again saved: {said or 'nothing played'}", retry)


def _sales():
    from reflection import PLUG
    return PLUG.agent


def _run_start(run):
    try:
        return datetime.strptime(str(run), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _matches(path, run):
    """The matches of one run, from the tail of the matches file, in the order they were written."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - MATCH_TAIL))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    if size > MATCH_TAIL and lines:
        lines = lines[1:]  # the first line read may be cut
    out = []
    for line in lines:
        try:
            x = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(x, dict) and str(x.get("id") or "").startswith(f"{run}-"):
            out.append(x)
    return out


def _match_row(x, run):
    mid = str(x.get("id"))
    rest = mid[len(run) + 1:]
    kind = "gate" if re.match(r"^r\d+-g\d+$", rest) else "replay" if rest.startswith("replay-") else "training"
    turns = [t for t in x.get("turns") or [] if isinstance(t, dict)]
    quote = x.get("quote") if isinstance(x.get("quote"), dict) else {}
    checks = [c for t in turns for c in (t.get("checks") or []) if c]
    failed = [c for t in turns for c in (t.get("failed") or []) if c]
    return {"id": mid, "kind": kind, "won": x.get("won") is True, "why": str(x.get("why") or ""),
            "persona": _card_id(x), "worry": str(x.get("worry") or ""),
            "opening": str(x.get("opening") or ""), "turns": turns, "quote": quote,
            "check": str((failed or checks or [""])[0]) if (failed or checks) else "", "raw": x}


def _card_id(x):
    """The practice customer's card id: the match's card, or the id of the card saved as persona."""
    for v in (x.get("card"), x.get("persona")):
        if isinstance(v, dict):
            v = v.get("id")
        if isinstance(v, str) and v:
            return v
    return ""


def _db(m, agent, out, rec):
    with m.db.tx() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        held = lessons_mod.wants_yes_ids(c) if "lessons" in tables else set()
        lessons = [dict(r) for r in c.execute("SELECT * FROM lessons WHERE agent = ? ORDER BY id", (agent,))] \
            if "lessons" in tables else []
        exams = [dict(r) for r in c.execute("SELECT * FROM lesson_exams WHERE agent = ? ORDER BY at, lesson_id",
                                            (agent,))] if "lesson_exams" in tables else []
        chats, steps, traces = [], {}, {}
        if agent == _sales() and {"chats", "steps"} <= tables:
            chats = [dict(r) for r in c.execute(
                "SELECT * FROM chats WHERE substr(channel, 1, 8) != 'history:' ORDER BY updated_at DESC, id LIMIT ?",
                (CHATS,))]
            for ch in chats:
                steps[ch["id"]] = [dict(r) for r in c.execute("SELECT * FROM steps WHERE chat_id = ? ORDER BY n",
                                                             (ch["id"],))]
                traces[ch["id"]] = [dict(r) for r in c.execute(
                    "SELECT * FROM trace WHERE agent = ? AND case_id = ? ORDER BY id", (agent, ch["id"]))] \
                    if "trace" in tables else []
    conns = conn_mod.history(m.db, agent)
    texts = {les["id"]: les["text"] for les in lessons}
    by_id = {}
    for les in lessons:
        status = _status(les, held)
        row = {"id": les["id"], "text": les["text"], "source": les.get("source") or "", "status": status,
               "state": les["state"], "added_at": les["added_at"], "risk": les.get("risk"),
               "why": risk_reason(les.get("risk_why")) if les.get("risk") == "high" else "", "raw": les}
        by_id[les["id"]] = row
        out["lessons"].append(row)
        rec.add("R", les["added_at"], f"lesson {les['id']} added ({status.lower()}): {les['text']}", les,
                row=f"l.{les['id']}")
        if les["state"] == PULLED and les.get("pulled_at"):
            rec.add("R", les["pulled_at"], f"lesson {les['id']} pulled: {les.get('pulled_why') or ''}",
                    {"id": les["id"], "state": les["state"], "pulled_at": les["pulled_at"],
                     "pulled_why": les.get("pulled_why")}, row=f"l.{les['id']}")
    sits = _situations(m.plugs.get(agent))
    out["sits"], out["situations"] = sits, list(sits)
    for ex in exams:
        fails = exam_mod.fails_of(ex)
        parts = _parts(ex.get("parts"))
        got, total = sum(p[0] for p in parts.values()), sum(p[1] for p in parts.values())
        row = {"lesson": ex["lesson_id"], "text": texts.get(ex["lesson_id"], ""), "passed": bool(ex["passed"]),
               "parts": parts, "got": got, "total": total, "at": ex["at"], "calls": ex.get("calls"),
               "fails": [dict(f, title=_title(sits, f.get("situation"), f.get("name"))) for f in fails], "raw": ex}
        out["exams"].append(row)
        said = "passed" if row["passed"] else f"held on {(fails[0].get('check') if fails else '') or 'a check'}"
        rec.add("R", ex["at"], f"exam for lesson {ex['lesson_id']} {said}" + (f", {got} of {total}" if total else ""),
                ex, row=f"e.{ex['lesson_id']}")
        if ex["lesson_id"] in by_id:
            by_id[ex["lesson_id"]]["exam"] = row
    for les in out["lessons"]:
        if lessons_mod.HOTFIX_SOURCE in les["source"]:
            raw = les["raw"]
            out["corrections"].append({"id": les["id"], "text": les["text"], "status": les["status"],
                                       "by": OPERATOR if raw.get("yes_by") == OPERATOR else "user",
                                       "at": les["added_at"], "exam": les.get("exam")})
    for ch in chats:
        for t in _turns(ch, steps.get(ch["id"]) or [], traces.get(ch["id"]) or [], texts):
            out["turns"].append(t)
            what = ("flagged: " + t["why"]) if t["flagged"] else (t["replies"][-1] if t["replies"] else "no reply")
            rec.add("D", t["at"], f"chat {ch['id'][:8]} turn {t['n']}: {what}", t["raw"], row=t["key"])
    out["turns"].sort(key=lambda t: (t["at"] or 0, t["key"]))
    for cn in conns:
        rec.add("D", cn["at"], f"{'connected to' if cn['on'] else 'pulled from'} {cn['channel']}: {cn['why']}", cn)
    out["conns"] = conns


def risk_reason(risk_why):
    """Why a high risk lesson waits, from its risk_why as the engine saved it (engine/risk.py classify,
    reasons joined by "; ", never rewritten): "high risk: money (fee, refund)". The code check's
    "group: mark" lines go under their group (a pattern by its group alone), a core mark and the judge's
    answer by name. Nothing saved: NOT_SAVED."""
    lines = [x.strip() for x in str(risk_why or "").split("; ") if x.strip()]
    if not lines:
        return f"high risk: {NOT_SAVED}"
    groups, out = {}, []
    for x in lines:
        group, _, mark = x.partition(": ")
        if not mark:
            out.append(x)
        elif group == "core":
            out.append(mark)
        elif group == "judge":
            out.append(f"judge {mark.removesuffix(', counted as high')}")
        else:
            if group not in groups:
                groups[group] = []
                out.append(group)  # shown with spaces: personal_data is "personal data"
            if not (mark.startswith("/") and mark.endswith("/")) and mark not in groups[group]:
                groups[group].append(mark)
    said = [(x.replace("_", " ") + (f" ({', '.join(groups[x])})" if groups[x] else "")) if x in groups else x
            for x in dict.fromkeys(out)]
    return "high risk: " + ", ".join(said)


def _status(les, held):
    if les["state"] == KEPT:
        return "KEPT"
    if les["state"] == TRYING:
        return "TRIAL"
    if les["state"] == WAITING:
        return "HELD" if les["id"] in held else "WAITING"
    return "PULLED"


def _parts(v):
    try:
        got = json.loads(v or "{}")
    except (TypeError, ValueError):
        return {}
    out = {}
    for k, p in (got.items() if isinstance(got, dict) else []):
        if isinstance(p, list) and len(p) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in p):
            out[str(k)] = (p[0], p[1])
    return out


def _situations(plug):
    """{situation id: the situation} of the agent's exam, {} when it has none or it cannot be read."""
    ex = getattr(plug, "exam", None)
    if ex is None:
        return {}
    try:
        return {s["id"]: s for s in exam_mod.load(ex.situations, plug.stages)}
    except (ValueError, OSError, TypeError, KeyError):
        return {}


def _title(sits, sid, name):
    s = sits.get(sid) if isinstance(sid, int) else None
    return str((s or {}).get("title") or name or "")


def _turns(chat, steps, traces, texts):
    """A chat's turns: each customer step with the steps after it, up to the next customer step."""
    out, cur = [], None
    for st in steps:
        if st["role"] == "user":
            cur = {"n": st["n"], "steps": [st]}
            out.append(cur)
        elif cur is not None:
            cur["steps"].append(st)
    turns = []
    for i, t in enumerate(out):
        end = out[i + 1]["n"] if i + 1 < len(out) else None
        rows = [r for r in traces if isinstance(r.get("step"), int) and r["step"] >= t["n"]
                and (end is None or r["step"] < end)]
        ids = []
        for r in rows:
            try:
                got = json.loads(r.get("lessons") or "[]")
            except ValueError:
                got = []
            ids += [x for x in got if isinstance(x, int) and x not in ids]
        replies, calls, results, events, refused, why = [], [], [], [], [], ""
        flag_at = None
        for st in t["steps"][1:]:
            if st["role"] == "assistant":
                if st.get("tool_calls"):
                    try:
                        calls += json.loads(st["tool_calls"])
                    except ValueError:
                        calls.append(st["tool_calls"])
                if st.get("content"):
                    replies.append(st["content"])
                    flag_at = None
            elif st["role"] == "tool":
                results.append({"name": st.get("name"), "content": st.get("content")})
            elif st["role"] == "event":
                try:
                    ev = json.loads(st.get("content") or "null")
                except ValueError:
                    ev = st.get("content")
                events.append(ev)
                if isinstance(ev, dict) and ("check_failed" in ev or "model_error" in ev):
                    said = ev.get("check_failed") or ev.get("model_error")
                    refused.append(said if isinstance(said, str) else json.dumps(said, ensure_ascii=False))
                    flag_at, why = st["n"], refused[-1]
        outcomes = [r.get("result") for r in rows if r.get("result")]
        flagged = flag_at is not None or "no_safe_reply" in outcomes
        if flagged and not why:
            why = "no safe reply was sent"
        check = "FLAGGED" if flagged else "REFUSED, REWRITTEN" if refused else "SENT" if replies else "NO REPLY"
        key = f"t.{chat['id']}.{t['n']}"
        turns.append({"key": key, "chat": chat["id"], "channel": chat["channel"], "n": t["n"],
                      "at": t["steps"][0]["at"], "customer": t["steps"][0].get("content") or "", "replies": replies,
                      "calls": calls, "results": results, "events": events, "refused": refused, "check": check,
                      "flagged": flagged, "why": why, "lessons": [(x, texts.get(x, "")) for x in ids],
                      "trace": rows, "raw": {"chat": chat["id"], "steps": t["steps"], "trace": rows}})
    return turns


def _nights(m, agent, rec):
    reps, _ = m.read_reports()
    for name, rep in reps:
        if rep.get("agent") != agent:
            continue
        window = rep.get("window") if isinstance(rep.get("window"), dict) else {}
        read = rep.get("read") if isinstance(rep.get("read"), dict) else {}
        trials = (rep.get("trials") or {}).get("trials") if isinstance(rep.get("trials"), dict) else None
        said = [f"read {read['cases']} chats" if isinstance(read.get("cases"), int) else None,
                f"{len(trials)} trials" if isinstance(trials, list) else None]
        rec.add("R", window.get("until"), f"night report {name}: " + (", ".join(s for s in said if s) or "saved"), rep)


def _calls(m, now):
    """The Calls file: {day, calls, cap, today}, today False when the count is of another day; None
    with no file."""
    if m.reports is None:
        return None
    got = _read_json(m.reports / "arena-calls.json")
    if not isinstance(got, dict) or not isinstance(got.get("calls"), int):
        return None
    from arena import run
    return {"day": str(got.get("day") or ""), "calls": got["calls"], "cap": got.get("cap"),
            "today": got.get("day") == run.today()}


def _read_json(path):
    try:
        if Path(path).stat().st_size > MAX_JSON:
            return None
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---- the page ---------------------------------------------------------------------------------------

CSS = """:root{--bg:#0c0e12;--panel:#13161c;--panel2:#181c23;--line:#252a33;--fg:#d6dae1;--dim:#7d8592;--white:#f3f5f8;
--green:#3ecf7a;--greenbg:#123222;--red:#ff5d5d;--redbg:#3a1618;--amber:#f0b44a;--blue:#5aa2ff;--bluebg:#15243d;--violet:#b796ff;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;
padding:14px max(16px,env(safe-area-inset-right,0px)) 14px max(16px,env(safe-area-inset-left,0px))}
a{color:inherit;text-decoration:none}
.mono,code,pre,.json,.log{font-family:ui-monospace,Menlo,Consolas,monospace}
button,textarea{font:inherit;color:inherit}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;margin-bottom:12px}
.crumb{color:var(--dim)}.crumb b{color:var(--white);font-weight:600}.crumb a:hover{color:var(--white)}
.loop{display:flex;flex-wrap:wrap;gap:4px;font-size:11px;letter-spacing:.06em}
.loop a{padding:2px 9px;border:1px solid var(--line);border-radius:4px;color:var(--dim);display:flex;align-items:center;gap:6px}
.loop a .dot{width:6px;height:6px;border-radius:50%;background:var(--line)}
.loop a.run .dot{background:var(--green);box-shadow:0 0 0 3px #3ecf7a33}
.loop a.sel{color:var(--white);border-color:var(--dim);background:var(--panel2)}
.bar .r{margin-left:auto;color:var(--dim)}
.menu{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--line)}
.menu nav{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.menu a{padding:4px 10px;border-radius:4px;color:var(--dim)}
.menu a:hover{color:var(--white)}
.menu a.sel{color:var(--white);background:var(--panel2);border:1px solid var(--line)}
.menu .tm a{font-size:14px}
.menu .pick span{color:var(--dim);font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin-right:4px}
.menu .pick a{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.flash{margin:0 0 12px;padding:8px 12px;border:1px solid var(--blue);border-radius:6px;color:var(--white);background:var(--bluebg)}
.flash a{text-decoration:underline}
.shell{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:12px;align-items:start}
.main{display:flex;flex-direction:column;gap:12px;min-width:0}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}
.card .lb{display:flex;justify-content:space-between;gap:6px;color:var(--dim);font-size:12px}
.card .big{font-size:22px;font-weight:600;color:var(--white);margin:4px 0 2px}
.card .sub{color:var(--dim);font-size:12px}
.chip{font-size:11px;padding:1px 7px;border-radius:999px;white-space:nowrap;align-self:flex-start;background:var(--panel2);color:var(--dim)}
.chip.ok{background:var(--greenbg);color:var(--green)}.chip.bad{background:var(--redbg);color:var(--red)}.chip.run{background:var(--bluebg);color:var(--blue)}
.spark{width:100%;height:26px;display:block;margin-top:4px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;min-width:0}
.ph{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line)}
.ph h2{font-size:14px;font-weight:600;color:var(--white);margin:0}
.ph .n{color:var(--dim)}
.ph .tools{margin-left:auto;display:flex;flex-wrap:wrap;gap:6px}
.seg{display:flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg a{padding:3px 9px;color:var(--dim)}.seg a.on{background:var(--panel2);color:var(--white)}
.tbl{overflow:auto;max-height:380px}
table{border-collapse:collapse;width:100%;font:inherit}
th{position:sticky;top:0;background:var(--panel);text-align:left;font-weight:500;color:var(--dim);font-size:12px;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
td.sit{white-space:normal;min-width:220px}
td.sit small.why{display:block;margin-top:3px;font-size:11px;color:var(--red)}
.sline{grid-column:1/-1;margin:0;color:var(--dim);font-size:12px}
tr.sel td{background:#1a2230}
tr:hover td{background:var(--panel2)}
td.dim,.dim{color:var(--dim)}
tr.sub td.sit{padding-left:26px}
.cat{font-size:11px;padding:1px 7px;border-radius:4px;background:var(--panel2);border:1px solid var(--line)}
.cat.safe{border-color:#4a3a1a;color:var(--amber)}
.badge{font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;letter-spacing:.03em;background:var(--panel2);color:var(--dim)}
.badge.ok{background:var(--greenbg);color:var(--green)}.badge.bad{background:var(--redbg);color:var(--red)}.badge.run{background:var(--bluebg);color:var(--blue)}
td.act a{color:var(--blue)}td.act.fix a{color:var(--red)}
.json{font-size:12px;line-height:1.5;padding:8px 14px;height:260px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.json .k{color:var(--blue)}.json .s{color:var(--green)}.json .n{color:var(--amber)}.json .c{color:var(--dim)}
.log{font-size:12px;padding:8px 14px;max-height:380px;overflow:auto}
.log div{white-space:pre-wrap;word-break:break-word}
.log .t{color:var(--dim)}
.log a:hover{background:var(--panel2)}
.tg{display:inline-block;width:92px;font-size:10.5px;text-align:center;border-radius:3px;margin-right:6px;padding:0 4px}
.tg.A{background:var(--bluebg);color:var(--blue)}.tg.D{background:var(--greenbg);color:var(--green)}.tg.R{background:#2a2140;color:var(--violet)}
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.split>div{min-width:0}.split>div+div{border-left:1px solid var(--line)}
.stats{display:flex;flex-wrap:wrap;gap:6px 16px;padding:8px 14px;border-bottom:1px solid var(--line);color:var(--dim);font-size:12px}
.stats b{color:var(--white);font-weight:500}.stats b.ok{color:var(--green)}
.empty{padding:12px 14px;color:var(--dim)}
.clist{padding:12px 14px;display:flex;flex-direction:column;gap:10px}
.corr{border:1px solid var(--line);border-radius:6px;padding:9px 11px;background:var(--panel2);display:flex;flex-direction:column;gap:5px}
.corr .top{display:flex;align-items:center;gap:8px}
.corr .id{font-weight:600;color:var(--white)}
.corr .on{color:var(--dim);font-size:12px}
.corr .ex{color:var(--dim);font-size:12px}
.corr .top .chip{margin-left:auto}
.src{font-size:10.5px;padding:0 6px;border-radius:4px;border:1px solid var(--line);color:var(--dim)}
.src.op{border-color:var(--violet);color:var(--violet)}
.route{font-size:12px;color:var(--dim);border:1px dashed var(--line);border-radius:6px;padding:8px 10px;margin:0 14px 14px}
.route b{color:var(--amber);font-weight:500}
.drawer{position:fixed;inset:0 0 0 auto;width:min(560px,100vw);background:var(--panel);border-left:1px solid var(--line);
display:flex;flex-direction:column;z-index:20;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
.dh{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--line)}
.dh b{color:var(--white)}.dh a{margin-left:auto;color:var(--dim);padding:2px 8px;border:1px solid var(--line);border-radius:4px}
.dtabs{display:flex;gap:6px;padding:10px 14px;border-bottom:1px solid var(--line)}
.dtabs a{padding:3px 10px;border:1px solid var(--line);border-radius:4px;color:var(--dim)}
.dtabs a.on{background:var(--panel2);color:var(--white);border-color:var(--dim)}
.dbody{overflow:auto;padding:12px 14px;flex:1;display:flex;flex-direction:column;gap:10px}
.box{border:1px solid var(--line);border-radius:6px}
.box h4{margin:0;padding:6px 10px;color:var(--white);font-weight:500;font-size:13px}
.box>div{padding:4px 12px 10px;white-space:pre-wrap;word-break:break-word}
.box .ns{color:var(--amber)}
.box.bad>div{color:var(--red)}.box.ok>div{color:var(--green)}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:12px}
.fixbox{padding:12px 14px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:9px;background:#191317}
.bub{max-width:85%;padding:7px 10px;border-radius:10px;border:1px solid var(--line);white-space:pre-wrap;word-break:break-word}
.bub span{display:block;font-size:11px;color:var(--dim);margin-bottom:2px}
.bub.cu{align-self:flex-start;background:var(--panel2)}
.bub.ag{align-self:flex-end;background:#2a1719;border-color:#5a2a2d}
.jd{border-left:3px solid var(--red);padding:2px 10px;color:var(--red);font-size:12px}
.fixbox form{display:flex;flex-direction:column;gap:9px}
.fixbox label{display:flex;flex-direction:column;gap:5px;color:var(--dim);font-size:12px}
.fixbox textarea{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:7px 9px;min-height:70px;resize:vertical}
.fixrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.fixrow .n{color:var(--dim);font-size:12px}
.send{all:unset;cursor:pointer;text-align:center;background:var(--blue);color:#06101f;font-weight:600;border-radius:6px;padding:7px 14px;margin-left:auto}
@media (max-width:980px){.shell{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}
.split{grid-template-columns:1fr}.split>div+div{border-left:0;border-top:1px solid var(--line)}}
@media (max-width:520px){.bar .r{margin-left:0}}
"""

SCRIPT = """(function(){
var low=function(e){return e.scrollHeight-e.scrollTop-e.clientHeight<8};
document.querySelectorAll('.scroll').forEach(function(e){e.scrollTop=e.scrollHeight});
function tick(){
fetch(location.href,{headers:{'X-Poll':'1'},credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.text():null}).then(function(t){
if(!t)return;
var d=new DOMParser().parseFromString(t,'text/html');
document.querySelectorAll('[data-live]').forEach(function(el){
var n=d.querySelector('[data-live="'+el.getAttribute('data-live')+'"]');
if(!n||n.innerHTML===el.innerHTML)return;
var s=[];el.querySelectorAll('.scroll').forEach(function(x){s.push([low(x),x.scrollTop])});
el.innerHTML=n.innerHTML;
el.querySelectorAll('.scroll').forEach(function(x,i){var k=s[i];x.scrollTop=(!k||k[0])?x.scrollHeight:k[1]});
});
}).catch(function(){}).then(function(){setTimeout(tick,""" + str(POLL_MS) + """)});
}
setTimeout(tick,""" + str(POLL_MS) + """);
})();"""


def _sha(text):
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


CSP = (f"default-src 'none'; style-src 'sha256-{_sha(CSS)}'; script-src 'sha256-{_sha(SCRIPT)}'; connect-src 'self'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


def csp():
    """The console's own policy: its one style and its one script, by hash; fetch only to this server."""
    return CSP


def state_of(query, agent):
    """The console's address read and checked: {view, sub, f, row, pane}, each one of its known values."""
    def one(name, allowed, default):
        got = (query.get(name) or [""])[0]
        return got if got in allowed else default
    view = one("view", [v for v, _ in VIEWS], "all")
    subs = SUBS.get(view, ())
    sub = one("sub", subs, subs[0] if subs else "")
    row = (query.get("row") or [""])[0]
    return {"agent": agent, "view": view, "sub": sub, "f": one("f", FILTERS, "all"),
            "row": row if ROW.match(row) else "", "pane": one("pane", PANES, "")}


def href(st, day=None, **change):
    s = dict(st, **change)
    q = [("agent", s["agent"]), ("view", s["view"])]
    q += [(k, s[k]) for k in ("sub", "f", "row", "pane") if s.get(k)]
    if day is not None:
        q.append(("day", day))
    return "/console?" + "&amp;".join(f"{k}={h(v)}" for k, v in q)


def back_of(st, day=None):
    """Where the operator correction returns: this console, same view and row (not escaped)."""
    return href(st, day).replace("&amp;", "&")


def menu_html(agent, agents, day=None):
    """The app's top menu (Today, Agents, Console, LOCKS "App pages") and the agent picker: one link
    per agent, the one shown marked. Links only, so the page keeps its one script."""
    q = f"?day={h(day)}" if day is not None else ""
    d = f"&amp;day={h(day)}" if day is not None else ""
    items = (f'<a href="/{q}">Today</a><a href="/agents{q}">Agents</a>'
             f'<a class="sel" href="/console?agent={h(agent)}{d}" aria-current="page">Console</a>')
    picks = "".join(f'<a class="sel" href="/console?agent={h(a)}{d}" aria-current="true">{h(a)}</a>' if a == agent
                    else f'<a href="/console?agent={h(a)}{d}">{h(a)}</a>' for a in (agents or [agent]))
    return (f'<div class="menu"><nav class="tm" aria-label="Main">{items}</nav>'
            f'<nav class="pick" aria-label="Agent"><span>agent</span>{picks}</nav></div>')


def render(data, st, *, token=None, flash=None, day=None, name=None, flash_html=None, agents=None):
    """The whole console page. data: collect(); st: state_of(); token: the page token (None: no form)."""
    from reflection import morning as mo
    agent = st["agent"]
    title = name or mo.name_of(agent)
    run = data["running"]
    tabs = "".join(
        f'<a class="{" ".join(c for c in ("sel" if v == st["view"] else "", "run" if (run and (v == "all" or VIEW_STAGE.get(v) == run)) else "") if c)}" '
        f'href="{href(st, day, view=v, sub="", f="all")}"{" aria-current=page" if v == st["view"] else ""}><span class="dot"></span>{w}</a>'
        for v, w in VIEWS)
    chip = _state_chip(data)
    q = f"?day={h(day)}" if day is not None else ""
    bar = (f'<span class="crumb"><a href="/agents{q}">Agents</a> / <a href="/agents/{h(agent)}{q}"><b>{h(agent)}</b></a> / Console</span>'
           f'<nav class="loop" aria-label="Loop stages">{tabs}</nav>{chip}'
           f'<span class="r mono">{h(_stamp(data["now"], date=True))} Cairo</span>')
    flash_part = ""
    if flash_html:
        flash_part = f'<p class="flash" role="status">{flash_html}</p>'
    elif flash:
        flash_part = f'<p class="flash" role="status">{h(flash)}</p>'
    drawer = drawer_html(data, st, token=token, day=day) if st["row"] else ""
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<title>{h(title)} console</title><style>{CSS}</style></head><body>',
        menu_html(agent, agents, day), f'<header class="bar" data-live="bar">{bar}</header>', flash_part,
        '<div class="shell"><div class="main">',
        f'<div class="cards" data-live="cards">{cards_html(data)}</div>',
        f'<section class="panel" data-live="view">{view_html(data, st, day)}</section>',
        '<section class="panel"><div class="ph"><h2 class="mono">writes.json</h2><span class="n">what the engine '
        'wrote, as it saved it, on every tab</span></div>'
        f'<div data-live="writes"><div class="json scroll">{writes_html(data)}</div></div></section>',
        f'</div><aside class="panel" aria-label="Corrections" data-live="corr">{corrections_html(data)}</aside></div>',
        drawer, f"<script>{SCRIPT}</script></body></html>"])


def _state_chip(data):
    run = data["running"]
    if run is None:
        return '<span class="chip">Idle</span>'
    newest = [r for r in data["records"] if r["stage"] == run and r["at"] is not None]
    when = f" | {_stamp(newest[-1]['at'])}" if newest else ""
    return f'<span class="chip run">{STAGES[run].capitalize()}{h(when)}</span>'


def _stamp(t, date=False):
    from reflection import morning as mo
    d = mo._cairo(t)
    if d is None:
        return ""
    return f"{d:%Y-%m-%d %H:%M:%S}" if date else f"{d:%m-%d %H:%M:%S}"


def cards_html(data):
    out = []
    matches = data["matches"]
    item = data.get("arena")
    if matches:
        won = sum(1 for x in matches if x["won"])
        pct = round(won * 100 / len(matches))
        big, sub = f"{pct}%", f"{won} won of {len(matches)} practice matches, run {item['run']}"
    elif item:
        big, sub = "none", f"run {item['run']}: its matches are not in the matches file"
    else:
        big, sub = "none", "No saved Arena run yet"
    gate = data.get("gate") or {}
    if data["running"] == "A":
        chip = '<span class="chip run">Running</span>'
    elif gate.get("passed"):
        chip = '<span class="chip ok">Gate passed</span>'
    elif item:
        chip = '<span class="chip bad">Gate not passed</span>'
    else:
        chip = '<span class="chip">No run</span>'
    out.append(f'<div class="card"><div class="lb"><span>Arena win rate</span>{chip}</div><div class="big">{h(big)}</div>'
               f'<div class="sub">{h(sub)}</div>{_spark(matches)}</div>')
    exams = data["exams"]
    if exams:
        ex = exams[-1]
        from reflection.exam import SAFETY
        bad = [f.get("check") for f in ex["fails"] if f.get("check") in SAFETY]
        chip = '<span class="chip ok">Passed</span>' if ex["passed"] else '<span class="chip bad">Held</span>'
        big = f"{ex['got']} / {ex['total']}" if ex["total"] else ("passed" if ex["passed"] else "held")
        safety = f"safety failed on {', '.join(dict.fromkeys(bad))}" if bad else "safety held" if ex["passed"] \
            else "safety not the cause"
        sub = f"lesson {ex['lesson']} | {safety} | hidden from the agent"
    else:
        chip, big, sub = '<span class="chip">None yet</span>', "none", "No exam has run yet | hidden from the agent"
    out.append(f'<div class="card"><div class="lb"><span>Exam gate</span>{chip}</div><div class="big">{h(big)}</div>'
               f'<div class="sub">{h(sub)}</div></div>')
    ls = data["lessons"]
    kept = sum(1 for x in ls if x["status"] == "KEPT")
    trial = sum(1 for x in ls if x["status"] == "TRIAL")
    held = sum(1 for x in ls if x["status"] == "HELD")
    live = sum(1 for c in data["corrections"] if c["status"] in ("KEPT", "TRIAL"))
    out.append(f'<div class="card"><div class="lb"><span>Lessons</span><span class="chip run">{trial} on trial</span>'
               f'</div><div class="big">{kept} kept</div><div class="sub">corrections live: {live} | held: {held}</div></div>')
    calls = data.get("calls")
    if calls and calls["today"]:
        cap = calls["cap"] if isinstance(calls["cap"], int) else None
        at_cap = cap is not None and calls["calls"] >= cap
        chip = '<span class="chip bad">At cap</span>' if at_cap else '<span class="chip ok">Under cap</span>'
        big = str(calls["calls"])
        sub = (f"of {cap} a day" if cap else "the day's cap not saved") + f" | full exam cap {FULL_CAP} a lesson"
    else:
        chip, big = '<span class="chip">None today</span>', "0"
        sub = f"No calls counted today | full exam cap {FULL_CAP} a lesson"
    out.append(f'<div class="card"><div class="lb"><span>Model calls today</span>{chip}</div><div class="big">{h(big)}</div>'
               f'<div class="sub">{h(sub)}</div></div>')
    if data.get("sample"):  # a built agent's sample data, the card's own line
        out.append(f'<p class="sline mono">{h(data["sample"])}</p>')
    return "".join(out)


def _spark(matches):
    """Win rate by round of the newest run (training rounds, then the gate), as a line."""
    rounds = {}
    for x in matches:
        m = re.search(r"-r(\d+)-", x["id"])
        if m:
            rounds.setdefault(int(m.group(1)), []).append(x["won"])
    pts = [sum(v) / len(v) for _, v in sorted(rounds.items())]
    if len(pts) < 2:
        return ""
    line = " ".join(f"{i * 120 / (len(pts) - 1):.1f},{24 - p * 22:.1f}" for i, p in enumerate(pts))
    return (f'<svg class="spark" viewBox="0 0 120 26" preserveAspectRatio="none" role="img" aria-label="Win rate by round">'
            f'<polyline fill="none" stroke="#3ecf7a" stroke-width="1.6" points="{line}"/></svg>')


def _seg(st, day, name, items):
    return '<div class="seg">' + "".join(
        f'<a class="{"on" if st[name] == v else ""}" href="{href(st, day, **{name: v})}">{h(w)}</a>' for v, w in items) + "</div>"


def _line(r, st, day):
    t = _stamp(r["at"]) if r["at"] is not None else ""
    text = h(r["text"])
    if r["row"]:
        text = f'<a href="{href(st, day, row=r["row"], pane="")}">{text}</a>'
    return f'<div><span class="t">{h(t) or "--"}</span> <span class="tg {r["stage"]}">{STAGES[r["stage"]]}</span>{text}</div>'


def view_html(data, st, day):
    v = st["view"]
    if v == "arena":
        return arena_html(data, st, day)
    if v == "deploy":
        return deploy_html(data, st, day)
    if v == "reflect":
        return reflect_html(data, st, day)
    recs = [r for r in data["records"] if st["sub"] in ("all", "") or r["stage"] == st["sub"]][-SHOWN:]
    seg = _seg(st, day, "sub", (("all", "All"), ("A", "Arena"), ("D", "Deployment"), ("R", "Reflection")))
    body = "".join(_line(r, st, day) for r in recs) or '<div class="t">Nothing saved yet.</div>'
    return (f'<div class="ph"><h2>All stages</h2><span class="n">the loop as one timeline: Arena, Deployment, '
            f'Reflection, newest last</span><div class="tools">{seg}</div></div><div class="log scroll">{body}</div>')


def _badge(ok, yes="PASSED", no="FAILED"):
    return f'<span class="badge {"ok" if ok else "bad"}">{yes if ok else no}</span>'


def _act(st, day, key, bad):
    return (f'<td class="act{" fix" if bad else ""}"><a href="{href(st, day, row=key, pane="")}">'
            f'{"Correct" if bad else "View"}</a></td>')


def _keep(ok, f):
    return f == "all" or (f == "ok") == ok


def arena_html(data, st, day):
    item = data.get("arena")
    n = f"run {item['run']}" if item else "no saved run"
    exam_n = len(_situations_count(data))
    seg = _seg(st, day, "sub", (("m", "Matches"), ("e", f"Exam ({exam_n})" if exam_n else "Exam")))
    filt = _seg(st, day, "f", (("all", "All"), ("bad", "Failed"), ("ok", "Passed")))
    rows = []
    if st["sub"] == "e":
        head = "<tr><th>Lesson</th><th>Situation</th><th>Check</th><th>Ran</th><th>Status</th><th></th></tr>"
        for ex in reversed(data["exams"]):
            key = f"e.{ex['lesson']}"
            if _keep(ex["passed"], st["f"]) or ex["fails"]:
                parts = ", ".join(f"{k} {a} of {b}" for k, (a, b) in ex["parts"].items())
                rows.append(f'<tr class="{"sel" if st["row"] == key else ""}"><td class="mono">{ex["lesson"]}</td>'
                            f'<td class="sit">{h(ex["text"])}</td><td class="dim">{h(parts)}</td>'
                            f'<td class="mono">{h(_stamp(ex["at"]))}</td><td>{_badge(ex["passed"], no="HELD")}</td>'
                            f'{_act(st, day, key, False)}</tr>')
            if st["f"] == "ok":
                continue
            from reflection.exam import SAFETY
            for f in ex["fails"]:
                if not isinstance(f.get("situation"), int):
                    continue
                k = f"e.{ex['lesson']}.{f['situation']}"
                safe = " safe" if f.get("check") in SAFETY else ""
                rows.append(f'<tr class="sub{" sel" if st["row"] == k else ""}"><td class="mono">#{f["situation"]}</td>'
                            f'<td class="sit">{h(f.get("title") or f.get("name"))}</td><td><span class="cat{safe}">'
                            f'{h(f.get("check"))}</span></td><td></td><td>{_badge(False)}</td>{_act(st, day, k, True)}</tr>')
        empty = "No exam has run yet."
    else:
        head = "<tr><th>Match</th><th>Customer</th><th>Kind</th><th>Check</th><th>Result</th><th></th></tr>"
        for x in reversed(data["matches"]):
            if not _keep(x["won"], st["f"]):
                continue
            key = f"m.{x['id']}"
            check = f'<span class="cat">{h(x["check"])}</span>' if x["check"] else ""
            rows.append(f'<tr class="{"sel" if st["row"] == key else ""}"><td class="mono">{h(x["id"])}</td>'
                        f'<td class="sit">{h(x["persona"])}{" | " + h(x["worry"]) if x["worry"] else ""}</td>'
                        f'<td class="dim">{x["kind"]}</td><td>{check}</td>'
                        f'<td>{_badge(x["won"], "WON", "LOST")}</td>{_act(st, day, key, not x["won"])}</tr>')
        empty = "No match of this run is saved." if item else "No saved Arena run yet."
    body = (f'<div class="tbl"><table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>' if rows
            else f'<p class="empty">{empty}</p>')
    return (f'<div class="ph"><h2>Arena</h2><span class="n">{h(n)}</span><div class="tools">{seg}{filt}</div></div>'
            + body)


def _situations_count(data):
    return data.get("situations") or []


def deploy_html(data, st, day):
    conns = data.get("conns") or []
    latest = {}
    for c in conns:
        latest[c["channel"]] = c
    live = [ch for ch, c in latest.items() if c["on"]]
    chan = (f'<b class="ok">Connected: {h(", ".join(live))}</b>' if live else "<b>Not live on any channel</b>")
    from reflection import morning as mo
    today = mo._cairo(data["now"])
    turns = data["turns"]
    on_day = [t for t in turns if (mo._cairo(t["at"]) or today).date() == today.date()] if today else []
    refused = sum(len(t["refused"]) for t in on_day)
    kept = sum(1 for x in data["lessons"] if x["status"] == "KEPT")
    corr = sum(1 for c in data["corrections"] if c["status"] in ("KEPT", "TRIAL"))
    gate = (data.get("gate") or {}).get("said") or ""
    stats = (f'<div class="stats"><span>channel {chan}</span><span>turns today <b>{len(on_day)}</b></span>'
             f'<span>send check refused today <b>{refused}</b></span><span>lessons live <b>{kept} + {corr} corrections</b></span>'
             f'<span>gate <b>{h(gate)}</b></span></div>')
    rows = []
    for t in reversed(turns):
        bad = t["flagged"]
        if not _keep(not bad, st["f"]):
            continue
        last = t["replies"][-1] if t["replies"] else t["customer"]
        lessons = " ".join(str(i) for i, _ in t["lessons"]) or NOT_SAVED
        cls = "bad" if bad else "run" if t["refused"] else "ok" if t["replies"] else ""
        rows.append(f'<tr class="{"sel" if st["row"] == t["key"] else ""}"><td class="mono">{h(t["chat"][:8])} #{t["n"]}'
                    f'<br><span class="dim">{h(_stamp(t["at"]))}</span></td><td class="sit">{h(last)}</td>'
                    f'<td class="mono">{h(lessons)}</td><td><span class="badge {cls}">{h(t["check"])}</span></td>'
                    f'{_act(st, day, t["key"], bad)}</tr>')
    filt = _seg(st, day, "f", (("all", "All"), ("bad", "Flagged"), ("ok", "Sent")))
    body = (f'<div class="tbl"><table><thead><tr><th>Chat</th><th>Last message</th><th>Lessons in play</th><th>Check</th>'
            f'<th></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>' if rows
            else '<p class="empty">No live turn saved yet.</p>')
    return (f'<div class="ph"><h2>Deployment</h2><span class="n">real chats from the chats store</span>'
            f'<div class="tools">{filt}</div></div>{stats}{body}')


def reflect_html(data, st, day):
    recs = [r for r in data["records"] if r["stage"] == "R"][-SHOWN:]
    log = "".join(_line(r, st, day) for r in recs) or '<div class="t">Nothing saved yet.</div>'
    ls = data["lessons"]
    count = {s: sum(1 for x in ls if x["status"] == s) for s in ("KEPT", "TRIAL", "HELD")}
    rows = []
    for x in reversed(ls):
        key = f"l.{x['id']}"
        cls = {"KEPT": "ok", "TRIAL": "run", "HELD": "bad"}.get(x["status"], "")
        rows.append(f'<tr class="{"sel" if st["row"] == key else ""}"><td class="mono"><a href="{href(st, day, row=key, pane="")}">'
                    f'{x["id"]}</a></td><td class="sit"><a href="{href(st, day, row=key, pane="")}">{h(x["text"])}</a>'
                    + (f'<small class="why">{h(x["why"])}</small>' if x.get("why") else "")
                    + f'</td><td class="dim">{h(_short(x["source"]))}</td><td><span class="badge {cls}">{x["status"]}</span></td></tr>')
    table = (f'<div class="tbl"><table><thead><tr><th>ID</th><th>Lesson</th><th>From</th><th>Status</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>' if rows else '<p class="empty">No lessons yet.</p>')
    return ('<div class="ph"><h2>Reflection</h2><span class="n">night reports, exams and every lesson</span></div>'
            f'<div class="split"><div><div class="stats"><span>Study log</span></div><div class="log scroll">{log}</div></div>'
            f'<div><div class="stats"><span>Lessons</span><span>kept <b>{count["KEPT"]}</b></span><span>trial '
            f'<b>{count["TRIAL"]}</b></span><span>held <b>{count["HELD"]}</b></span></div>{table}</div></div>')


def _short(source, n=60):
    s = str(source or "")
    return s if len(s) <= n else s[:n - 3] + "..."


def corrections_html(data):
    chips = {"KEPT": ("ok", "Live"), "TRIAL": ("ok", "Live"), "HELD": ("bad", "Held"), "WAITING": ("run", "Waiting"),
             "PULLED": ("", "Pulled")}
    out = []
    for c in reversed(data["corrections"]):
        cls, said = chips.get(c["status"], ("", c["status"]))
        ex = c.get("exam")
        if ex is None:
            exam = "exam: not saved"
        else:
            parts = ", ".join(f"{k} {a} of {b}" for k, (a, b) in ex["parts"].items())
            exam = ("exam passed" if ex["passed"] else "exam held") + (f" | {parts}" if parts else "")
        out.append(f'<div class="corr"><div class="top"><span class="id mono">L{c["id"]}</span>'
                   f'<span class="src{" op" if c["by"] == OPERATOR else ""}">{c["by"]}</span>'
                   f'<span class="on mono">{h(_stamp(c["at"]))}</span><span class="chip {cls}">{said}</span></div>'
                   f'<div dir="auto">"{h(c["text"])}"</div><div class="ex">{h(exam)}</div></div>')
    body = "".join(out) or '<p class="dim">No correction yet.</p>'
    return ('<div class="ph"><h2>Corrections</h2><span class="n">from the user and the operator</span></div>'
            f'<div class="clist">{body}</div><div class="route">Each one runs the <b>full exam</b> before it goes '
            'live. Users write them on the Arena screen or the agent page; the operator writes them here from any '
            'lost match, failed exam situation or flagged live turn.</div>')


def writes_html(data):
    out = []
    for r in data["records"][-SHOWN:]:
        t = _stamp(r["at"]) if r["at"] is not None else "time not saved"
        text = json.dumps(r["raw"], ensure_ascii=False, indent=2, default=str)
        cut = ""
        if len(text) > RAW_CUT:
            cut, text = f"\n... cut here, {len(text)} characters in all", text[:RAW_CUT]
        out.append(f'<div><span class="c">// {h(t)} {STAGES[r["stage"]].lower()}: {h(_short(r["text"], 120))}</span>'
                   f'<pre>{_hl(text)}{h(cut)}</pre></div>')
    return "".join(out) or '<span class="c">// nothing saved yet</span>'


def _hl(text):
    """JSON text, escaped, with keys, strings and numbers marked for colour."""
    s = h(text)
    s = _JSON_KEY.sub(r'<span class="k">\1</span>\2', s)
    s = _JSON_NUM.sub(r'\1<span class="n">\2</span>', s)
    return s


# ---- the side panel ---------------------------------------------------------------------------------

def find(data, key):
    """(kind, the row) for a side panel key, or (None, None)."""
    kind = key[:1]
    if kind == "m":
        return kind, next((x for x in data["matches"] if f"m.{x['id']}" == key), None)
    if kind == "t":
        return kind, next((t for t in data["turns"] if t["key"] == key), None)
    if kind == "l":
        return kind, next((x for x in data["lessons"] if f"l.{x['id']}" == key), None)
    if kind == "e":
        parts = key.split(".")
        ex = next((x for x in data["exams"] if str(x["lesson"]) == parts[1]), None)
        if ex is None or len(parts) == 2:
            return "e", ex
        f = next((f for f in ex["fails"] if str(f.get("situation")) == parts[2]), None)
        return ("s", {"exam": ex, "fail": f, "situation": data.get("sits", {}).get(f.get("situation")) if f else None}) \
            if f else (None, None)
    return None, None


def _box(title, body, cls="", raw=False):
    inner = body if raw else h(body)
    return f'<section class="box {cls}"><h4>{h(title)}</h4><div>{inner}</div></section>'


def _ns(title, what=""):
    return _box(title, f'<span class="ns">{NOT_SAVED}</span>' + (f"\n{h(what)}" if what else ""), raw=True)


def _json_box(title, obj):
    return _box(title, f"<pre>{_hl(json.dumps(obj, ensure_ascii=False, indent=2, default=str))}</pre>", raw=True)


def drawer_html(data, st, *, token=None, day=None):
    kind, x = find(data, st["row"])
    close = href(st, day, row="", pane="")
    if x is None:
        return (f'<aside class="drawer" aria-label="Row"><div class="dh"><b>Not found</b><a href="{close}">Close</a></div>'
                '<div class="dbody"><p class="dim">That row is not in what the engine saved now.</p></div></aside>')
    title, bad, fix, panes = _panel(kind, x, data)
    pane = st["pane"] or ("dec" if bad else "saw")
    tabs = "".join(f'<a class="{"on" if p == pane else ""}" href="{href(st, day, pane=p)}">{w}</a>'
                   for p, w in (("saw", "Saw"), ("dec", "Decided"), ("raw", "Raw")))
    box = fixbox(data, st, fix, token, day) if bad and fix else ""
    return (f'<aside class="drawer" aria-label="What the model saw and decided"><div class="dh"><b>{h(title)}</b>'
            f'<a href="{close}">Close</a></div>{box}<nav class="dtabs">{tabs}</nav>'
            f'<div class="dbody">{panes[pane]}</div></aside>')


def fixbox(data, st, fix, token, day):
    from reflection import morning as mo
    customer, reply, why = fix
    reply_html = h(reply) if reply else f'<span class="dim">{NOT_SAVED}</span>'
    form = ""
    if token:
        back = back_of(st, day)
        form = (f'<form method="post" action="/console/correct"><input type="hidden" name="token" value="{h(token)}">'
                f'<input type="hidden" name="back" value="{h(back)}"><input type="hidden" name="agent" value="{h(st["agent"])}">'
                f'<label>Operator correction<textarea name="line" maxlength="{mo.MAX_LEN}" dir="auto" required '
                'placeholder="What should the agent do instead?"></textarea></label><div class="fixrow"><span class="n">'
                'Full exam, then live. Nothing skips it.</span><button class="send" type="submit">Send correction</button>'
                '</div></form>')
    return (f'<div class="fixbox"><div class="bub cu"><span>Customer</span>{h(customer) or NOT_SAVED}</div>'
            f'<div class="bub ag"><span>Agent</span>{reply_html}</div><div class="jd">{h(why)}</div>{form}</div>')


def _panel(kind, x, data):
    """(title, bad, (customer, reply, why) for the fix box or None, {saw, dec, raw})."""
    if kind == "m":
        return _match_panel(x)
    if kind == "t":
        return _turn_panel(x)
    if kind == "s":
        return _sit_panel(x)
    if kind == "e":
        ex = x
        saw = _box("Lesson under exam", f"{ex['lesson']}: {ex['text']}") + _ns("The kept lessons beside it")
        dec = _box("Result", ("passed" if ex["passed"] else "held") + (f", {ex['got']} of {ex['total']}" if ex["total"] else ""),
                   "ok" if ex["passed"] else "bad")
        parts = "\n".join(f"{k}: {a} of {b}" for k, (a, b) in ex["parts"].items())
        if parts:
            dec += _box("Parts", parts)
        if ex["fails"]:
            dec += _box("Failed situations", "\n".join(f"#{f.get('situation')} {f.get('title') or f.get('name')}: "
                                                       f"{f.get('check')}, {f.get('why')}" for f in ex["fails"]), "bad")
        raw = _ns("Request and response of each situation") + _json_box("The saved exam row", ex["raw"])
        return f"Exam for lesson {ex['lesson']}", False, None, {"saw": saw, "dec": dec, "raw": raw}
    les = x
    saw = _box("Lesson", les["text"]) + _box("From", les["source"] or NOT_SAVED)
    dec = _box("Status", les["status"])
    if les.get("why"):  # a high risk lesson: why it waits, as its risk check saved it
        dec += _box("Why it waits" if les["status"] in ("HELD", "WAITING") else "Risk", les["why"], "bad")
    if les.get("exam"):
        ex = les["exam"]
        dec += _box("Exam", ("passed" if ex["passed"] else "held") + (f", {ex['got']} of {ex['total']}" if ex["total"] else ""),
                    "ok" if ex["passed"] else "bad")
    else:
        dec += _ns("Exam")
    raw = _json_box("The saved lesson row", les["raw"])
    return f"Lesson {les['id']}", False, None, {"saw": saw, "dec": dec, "raw": raw}


def _match_panel(x):
    turns = x["turns"]
    customer = "\n".join(f"turn {t.get('n')}: {t.get('customer') or ''}" for t in turns) or NOT_SAVED
    tools = "\n".join(f"turn {t.get('n')}: {', '.join(t.get('tools') or []) or 'none'}" for t in turns)
    saw = (_ns("Lessons in play") + _box("Customer message", customer)
           + _ns("Tool results", "Tools called, by name only:\n" + tools if tools else ""))
    replies = "\n".join(f"turn {t.get('n')}: {r}" for t in turns for r in (t.get("replies") or [])) or "no reply"
    checks = "\n".join(f"turn {t.get('n')}: {c}" for t in turns for c in (t.get("checks") or []) + (t.get("failed") or []))
    dec = (_ns("Tool calls", "Arguments are not saved; the names are under Saw.") + _box("Reply", replies)
           + (_box("Send check", checks, "bad") if checks else "")
           + _box("Judge", ("WON" if x["won"] else "LOST") + (f": {x['why']}" if x["why"] else ""), "ok" if x["won"] else "bad"))
    raw = _ns("Request and response") + _json_box("The saved match", x["raw"])
    fix = None
    if not x["won"]:
        q = x["quote"]
        turn = next((t for t in turns if t.get("n") == q.get("turn")), turns[-1] if turns else None)
        cust = (turn or {}).get("customer") or ""
        reply = " ".join((turn or {}).get("replies") or []) or (q.get("text") if q.get("who") == "agent" else "")
        fix = (cust, reply, f"LOST: {x['why']}" if x["why"] else "LOST")
    return (f"{x['id']} {x['persona']} | what the model saw and decided", not x["won"], fix,
            {"saw": saw, "dec": dec, "raw": raw})


def _turn_panel(t):
    lessons = "\n".join(f"{i}: {text or '(lesson text not found)'}" for i, text in t["lessons"])
    saw = ((_box("Lessons in play", lessons) if lessons else _ns("Lessons in play"))
           + _box("Customer message", t["customer"] or "(no text)"))
    saw += (_json_box("Tool results", t["results"]) if t["results"] else _box("Tool results", "no tool was called"))
    dec = _json_box("Tool calls", t["calls"]) if t["calls"] else _box("Tool calls", "none")
    if t["refused"]:
        dec += _box("Send check refused", "\n".join(t["refused"]), "bad")
    dec += _box("Reply sent" if t["replies"] else "Reply", "\n".join(t["replies"]) or "no reply was sent",
                "" if t["replies"] else "bad")
    raw = _ns("Request and response") + _json_box("The saved steps and trace rows", t["raw"])
    fix = (t["customer"], " ".join(t["replies"]), f"FLAGGED: {t['why']}") if t["flagged"] else None
    return (f"chat {t['chat'][:8]} turn {t['n']} | what the model saw and decided", t["flagged"], fix,
            {"saw": saw, "dec": dec, "raw": raw})


def _sit_panel(x):
    ex, f, s = x["exam"], x["fail"], x["situation"] or {}
    customer = "\n".join(str(tt.get("customer") or "") for tt in s.get("turns") or [] if isinstance(tt, dict))
    saw = (_box("Lesson under exam", f"{ex['lesson']}: {ex['text']}") + _ns("The kept lessons beside it")
           + _box("Customer message", customer or NOT_SAVED) + _ns("Tool results"))
    why = f"FAILED: {f.get('check')}" + (f". {f.get('why')}" if f.get("why") else "")
    dec = _ns("Tool calls") + _ns("Reply") + _box("Check", why, "bad")
    raw = _ns("Request and response") + _json_box("The saved failed row", f)
    if s:
        raw += _json_box("The situation", s)
    return (f"exam #{f.get('situation')} {f.get('title') or f.get('name') or ''} | lesson {ex['lesson']}", True,
            (customer, "", why), {"saw": saw, "dec": dec, "raw": raw})


def page(m, agent, query, *, token=None, flash=None, now=None, day=None, flash_html=None, agents=None):
    """The console for one agent, or None when the agent is not on the page."""
    if agent not in m.plugs:
        return None
    data = collect(m, agent, now)
    agents = [a for a in (agents or []) if a in m.plugs] or sorted(m.plugs)
    return render(data, state_of(query, agent), token=token, flash=flash, day=day, flash_html=flash_html, agents=agents)
