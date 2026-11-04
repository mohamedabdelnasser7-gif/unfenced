"""data: the rows an agent made by Quick start works from when it has no real connection for them.

The rows are the agent's sample data (kit/sample.py): made up at Build to fit its card, each marked
made up, plus any the user added, marked as theirs. kit/turn.py offers this tool to an agent whose
folder has sample data and hands the rows over in the turn's Context (data). Search words narrow the
rows; an empty query gives them all, up to MAX_ROWS.
"""
import json
import re

from kit import sample

NAME = "data"
MAX_ROWS = 60
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Look up the records your work reads (products and stock, tickets, leads, briefs, whatever this agent "
        "works from). They are sample data: most rows are made up for practice, some may be added by the user; "
        "each row says which. Use only what the rows say. Leave query empty to get every row."),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Short search words, or empty."}},
        "additionalProperties": False,
    },
}}


def check(args, ctx):
    extra = set(args) - {"query"}
    if extra:
        return False, f"Unknown arguments: {', '.join(sorted(extra))}. Only query is allowed."
    q = args.get("query", "")
    if not isinstance(q, str) or len(q) > 100:
        return False, "query must be a short string, 100 characters at most."
    return True, ""


def run(args, ctx):
    data = getattr(ctx, "data", None)
    if not data:
        return {"ok": False, "feedback": "This agent has no data yet."}
    rows = sample.rows_of(data)
    words = [w for w in re.findall(r"\w+", (args.get("query") or "").lower()) if len(w) > 1]
    note = None
    if words:
        hits = [r for r in rows if all(w.rstrip("s") in _hay(r) for w in words)]
        hits = hits or [r for r in rows if any(w.rstrip("s") in _hay(r) for w in words)]
        if hits:
            rows = hits
        else:
            note = "Nothing matched the search, so these are every row."
    out = {"ok": True, "about": data["what"], "data": sample.LABEL, "rows": rows[:MAX_ROWS]}
    if len(rows) > MAX_ROWS:
        out["note"] = f"Only the first {MAX_ROWS} rows; search to narrow them."
    if note:
        out["note"] = note
    return out


def _hay(row):
    return json.dumps(row, ensure_ascii=False).lower()
