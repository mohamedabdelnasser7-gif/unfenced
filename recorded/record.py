"""Write the recordings the no-key replay plays (recorded/play.py): one quick Arena run and one
Sales chat, each with a trace of every model call (who asked, the route, the model id, when it
started and ended, and what came back) as provenance.

    python3 -I recorded/record.py            a real run on the model key in env or .env
    python3 -I recorded/record.py --scripted  no key, no model call: the scripted models below
        [--out DIR]                           where the two files go (default: this folder)

The Arena run is the quick run (arena/run.py --quick: one training match, a gate of one match,
at most QUICK_CALLS model calls), with its call count in a throwaway folder so a recording never
spends the day's shared cap. The Sales chat is the real Sales agent (sales/loop.py, through
arena/match.py on the demo store with no Shopify keys) answering three fixed customer lines.

A scripted recording says so in its file: "scripted": true and a label that starts SCRIPTED.
Its models are ScriptedSeller and ScriptedBuyer, copies of the test fakes that pass the Arena's
win rule (tests/fake_model.py Seller and Buyer), so it shows the shape of a run and nothing about
the model. Root records the real one with a key.
"""
import argparse
import copy
import datetime
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # run by its path under -I
    sys.path.insert(0, str(ROOT))

from arena import factcheck, match as match_mod, run as run_mod, verdict  # noqa: E402

HERE = Path(__file__).resolve().parent
ARENA_FILE, SALES_FILE = "arena-run.json", "sales-chat.json"
FORMAT = 1
SCRIPTED_LABEL = ("SCRIPTED: made by recorded/record.py --scripted with scripted stand-in models. "
                  "No model was called; this shows the shape of a run, not what Muse Spark says.")
REAL_LABEL = "Recorded from a real run of recorded/record.py on Muse Spark (routes and model ids in the trace)."

PRICE = "The Mercurial Vapor 17 Elite is 16,500 EGP."
BUY = "ok I'll take it. Demo Buyer, 12 Tahrir St, Dokki, Giza"
ORDER = {"items": [{"product": "Nike Mercurial Vapor 17", "tier": "Elite", "size": "43", "quantity": 1}],
         "name": "Demo Buyer", "governorate": "Giza", "address": "12 Tahrir St, Dokki"}
SALES_LINES = ("How much is the Mercurial Vapor 17 Elite?", BUY, "yes")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _say(text):
    return {"role": "assistant", "content": text}


def _tool_call(name, args, n):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call_{n}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


class ScriptedSeller:
    """A stand-in Sales agent model (tests/fake_model.py Seller): gives the price, moves to ordering
    on "take it", drafts the order, shows the summary and places it on a plain yes."""
    route_name, model_name = "scripted", "scripted-seller"

    def __init__(self):
        self.n = 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.n += 1
        names = [t["function"]["name"] for t in tools or []]
        last = messages[-1]
        if last["role"] == "tool":
            res = json.loads(last["content"] or "null") or {}
            if res.get("next_stage") == "ordering":
                return _tool_call("draft_order", ORDER, self.n)
            if res.get("step") == "summary":
                return _say(f"Your order: Mercurial Vapor 17 Elite size 43 x1, total {res['total']} EGP with delivery. "
                            "Confirm?")
            if res.get("step") == "created":
                return _say(f"Thanks, order {res['order']} is placed.")
            return _say(PRICE)
        text = (last.get("content") or "").strip().casefold()
        if text == "yes":
            code = next((json.loads(m["content"]).get("code") for m in reversed(messages)
                         if m["role"] == "tool" and '"code"' in (m["content"] or "")), None)
            if code:
                return _tool_call("draft_order", {**ORDER, "confirm": code}, self.n)
        if "take it" in text:
            if "draft_order" in names:
                return _tool_call("draft_order", ORDER, self.n)
            return _tool_call("switch_stage", {"to": "ordering"}, self.n)
        return _say(PRICE)


class ScriptedBuyer:
    """A stand-in customer model (tests/fake_model.py Buyer): asks the price, buys, says yes."""
    route_name, model_name = "scripted", "scripted-buyer"

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if len(messages) == 2:
            return _say(SALES_LINES[0])
        return _say("yes" if "Confirm?" in (messages[-1].get("content") or "") else BUY)


class FixedLines:
    """The Sales chat's customer: the fixed lines after the opening, then it leaves. No model."""
    route_name, model_name = "fixed", "fixed-customer-lines"

    def __init__(self, lines):
        self.lines = list(lines)

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        return _say(self.lines.pop(0) if self.lines else match_mod.LEAVE)


class Traced:
    """Wraps a model and keeps one trace entry per call: role, route, model id, start, end and the
    answer (or the error, which kit/model.py keeps free of keys). The request is not kept."""

    def __init__(self, inner, role, trace):
        self.inner, self.role, self.trace = inner, role, trace

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        entry = {"n": len(self.trace) + 1, "role": self.role, "effort": effort, "started": now()}
        self.trace.append(entry)
        try:
            out = self.inner.chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)
        except Exception as e:
            entry.update(route=self._route(), model=self._model(), ended=now(), error=f"{type(e).__name__}: {e}")
            raise
        entry.update(route=self._route(), model=self._model(), ended=now(), output=copy.deepcopy(out))
        return out

    def _route(self):
        return getattr(self.inner, "last_route", None) or getattr(self.inner, "route_name", None) or "unknown"

    def _model(self):
        return getattr(self.inner, "last_model", None) or getattr(self.inner, "model_name", None) or "unknown"


def _head(kind, scripted, trace):
    used = sorted({(t["role"], t.get("route"), t.get("model")) for t in trace}, key=lambda x: tuple(map(str, x)))
    return {"format": FORMAT, "kind": kind, "scripted": bool(scripted),
            "label": SCRIPTED_LABEL if scripted else REAL_LABEL, "recorded_at": now(),
            "command": "python3 -I recorded/record.py" + (" --scripted" if scripted else ""),
            "models": [{"role": r, "route": rt, "model": m} for r, rt, m in used]}


def record_arena(agent_model, customer_model, *, scripted, cards_dir=run_mod.DEFAULT_CARDS):
    """The quick Arena run, traced. Returns the recording dict."""
    trace = []
    cards = run_mod.load_cards(cards_dir)
    with tempfile.TemporaryDirectory() as tmp:
        calls = run_mod.Calls(Path(tmp) / run_mod.CALLS_FILE, run_mod.DEFAULT_CAP, limit=run_mod.QUICK_CALLS)
        arena = run_mod.Arena(cards, agent_model=Traced(agent_model, "agent", trace),
                              customer_model=Traced(customer_model, "customer", trace), calls=calls,
                              trust=dict(run_mod.QUICK_TRUST), matches=1, rounds=1, state=tmp)
        rep = arena.run()
        path = Path(tmp) / run_mod.MATCHES_FILE
        matches = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] \
            if path.is_file() else []
    rep.pop("stuck", None)  # its file sat in the throwaway folder
    return {**_head("arena", scripted, trace), "report": rep, "matches": matches, "trace": trace}


def record_sales(agent_model, *, scripted, cards_dir=run_mod.DEFAULT_CARDS):
    """One Sales chat on the fixed customer lines, traced. Returns the recording dict."""
    trace = []
    cards = run_mod.load_cards(cards_dir)
    card = next(c for c in cards if run_mod.can_buy(c))
    m = match_mod.play(card, agent_model=Traced(agent_model, "agent", trace),
                       customer_model=FixedLines(SALES_LINES[1:]), opening=SALES_LINES[0],
                       checker=factcheck.check, stop=verdict.closed)
    judged = verdict.judge(m)
    m.update(won=judged["won"], why=judged["why"], quote=judged["quote"])
    return {**_head("sales", scripted, trace), "customer": "fixed lines, no model", "chat": m, "trace": trace}


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv=None, *, agent_model=None, customer_model=None):
    ap = argparse.ArgumentParser(prog="recorded/record.py", description="Record the Arena run and Sales chat the replay plays.")
    ap.add_argument("--scripted", action="store_true", help="no key, no model call: scripted stand-ins, labelled so")
    ap.add_argument("--out", default=str(HERE), help="the folder for arena-run.json and sales-chat.json")
    args = ap.parse_args(argv)
    if args.scripted:
        agent_model, customer_model, sales_model = ScriptedSeller(), ScriptedBuyer(), ScriptedSeller()
    else:
        from kit import env, model as model_mod
        if agent_model is None or customer_model is None:
            env.load()
            if not model_mod.has_key():
                print(model_mod.NO_KEY_LINE, file=sys.stderr)
                return 2
        agent_model = agent_model or model_mod.Model()
        customer_model = customer_model or model_mod.Model()
        sales_model = agent_model
    try:
        arena = record_arena(agent_model, customer_model, scripted=args.scripted)
        sales = record_sales(sales_model, scripted=args.scripted)
    except (run_mod.Refused, OSError, ValueError) as e:
        print(f"Not recorded: {e}", file=sys.stderr)
        return 2
    out = Path(args.out)
    write(out / ARENA_FILE, arena)
    write(out / SALES_FILE, sales)
    print(f"Recorded {len(arena['trace'])} Arena calls and {len(sales['trace'])} Sales chat calls in {out}"
          + (" (scripted)" if args.scripted else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
