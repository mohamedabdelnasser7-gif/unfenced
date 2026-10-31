"""The no-key replay: prints a recorded Arena run and a recorded Sales chat from the files in this
folder, with no model key and no network. Nothing here calls a model or opens a connection; it
reads two JSON files and prints them.

    python3 -I recorded/play.py [--arena FILE] [--sales FILE]

Each file carries its provenance (recorded/record.py writes it): whether it is scripted, when it
was recorded, the command, and a trace with one entry per model call (role, route, model id,
start, end, answer). A file without that is refused, so the replay never shows lines it cannot
trace. The shipped files are scripted until root records a real run; the replay says so first.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARENA_FILE, SALES_FILE = HERE / "arena-run.json", HERE / "sales-chat.json"
FORMAT = 1
TRACE_FIELDS = ("role", "route", "model", "started", "ended")
WIDTH = 160


class NotARecording(ValueError):
    pass


def load(path, kind):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise NotARecording(f"{path.name} could not be read ({type(e).__name__})") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("kind") != kind:
        raise NotARecording(f"{path.name} is not a recorded {kind} file this replay reads")
    trace = data.get("trace")
    if not isinstance(trace, list) or not trace or not isinstance(data.get("scripted"), bool) \
            or not data.get("recorded_at") or not data.get("label"):
        raise NotARecording(f"{path.name} has no provenance (label, recorded_at, scripted and a trace)")
    for t in trace:
        if not isinstance(t, dict) or any(not t.get(f) for f in TRACE_FIELDS) or not ("output" in t or "error" in t):
            raise NotARecording(f"{path.name} has a trace entry without its role, route, model, times and answer")
    return data


def short(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= WIDTH else text[:WIDTH - 3] + "..."


def head(data, title):
    tag = "SCRIPTED, not a model run" if data["scripted"] else "recorded from a real run"
    used = ", ".join(f"{m.get('role')} on {m.get('route')} ({m.get('model')})" for m in data.get("models", []))
    first, last = data["trace"][0], data["trace"][-1]
    return [f"{title} ({tag})", f"  {data['label']}",
            f"  recorded {data['recorded_at']} by: {data.get('command', 'unknown')}",
            f"  model calls in the trace: {len(data['trace'])}, {first['started']} to {last['ended']}",
            f"  models: {used or 'none named'}"]


def chat_lines(m):
    out = []
    for t in m.get("turns") or []:
        out.append(f"    customer: {short(t.get('customer'))}")
        for r in t.get("replies") or []:
            out.append(f"    agent:    {short(r)}")
        if t.get("tools"):
            out.append(f"      tools: {', '.join(t['tools'])}")
        for f in t.get("failed") or []:
            out.append(f"      failed check: {short(f)}")
    return out


def arena_lines(data):
    lines = head(data, "Arena run")
    rep = data.get("report") or {}
    trust = rep.get("trust") or {}
    lines.append(f"  stopped: {rep.get('stopped')}; gate asks {trust.get('wins')} of {trust.get('matches')} held-out "
                 "matches won")
    for m in data.get("matches") or []:
        result = "won" if m.get("won") else "lost"
        lines.append(f"  match {m.get('id')}: card {m.get('card')} (worry {m.get('worry')}), ended {m.get('ended')}, "
                     f"{result}: {m.get('why')}")
        lines += chat_lines(m)
    return lines


def sales_lines(data):
    lines = head(data, "Sales chat")
    m = data.get("chat") or {}
    lines.append(f"  customer: {data.get('customer', 'unknown')}; ended {m.get('ended')}, "
                 f"{'won' if m.get('won') else 'lost'}: {m.get('why')}")
    lines += chat_lines(m)
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(prog="recorded/play.py", description="Replay the recorded Arena run and Sales chat.")
    ap.add_argument("--arena", default=str(ARENA_FILE))
    ap.add_argument("--sales", default=str(SALES_FILE))
    args = ap.parse_args(argv)
    try:
        arena, sales = load(args.arena, "arena"), load(args.sales, "sales")
    except NotARecording as e:
        print(f"Not run: {e}", file=sys.stderr)
        return 2
    lines = ["Recorded replay: no key and no network. Nothing below is a live model call.", ""]
    lines += arena_lines(arena) + [""] + sales_lines(sales)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
