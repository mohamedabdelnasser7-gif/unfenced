"""One turn of an agent made by Quick start (new, 2026-11-01; DECISIONS item 58).

A new agent is a folder, <db folder>/agents/<name>/, holding the three files Quick start's Build
writes (reflection/quickstart.py):
  plug.json        passes engine/plug.py from_dict; its "agent" is the folder's name.
  instructions.md  its prompt, as written for the owner's yes.
  card.json        the card the owner said yes to: name, does, good, never, needs. Build also writes
                   agent, tools, level and at, and each need as {what, tool, connected}; a need reads
                   as its "what", and the rest is checked for shape and left alone.

load(folder) reads them, under size caps and with no link followed, into an Agent. turn() runs one
message from the person the agent serves, the way sales/loop.py runs a Sales turn, cut down to
what any agent has:

1. instructions.md is the system prompt. The lessons it has earned go under the plug's slot line
   (none in the Arena's first runs: every agent starts from zero, DECISIONS item 20).
2. The chat so far comes from kit/chats.py, so the tools read it the way they read a Sales chat.
3. Tools: only the ones the plug names (its high risk tools, the one list of tools a plug has)
   that exist in kit/tools, minus switch_stage, since a new agent has one stage. Quick start names
   what it connects by its own keys (reflection/quickstart.py TOOLS): QUICK_TOOLS reads those as the
   kit/tools files behind them, and whatsapp as the channel the chat is on, no tool. A name with no
   tool file is left out and listed in Agent.missing. At most MAX_TOOL_STEPS tool steps a turn
   and MAX_CALLS_PER_STEP calls a step, then the model must answer in words.
4. The send check: the full check (kit/send_check.py) when the plug declares a "reply" action, as
   the Sales plug does, so script, style, amounts from tools only, stock counts and links all
   hold; the house style part only (banned words, dashes, emoji, markdown) for any other agent,
   whose replies are not a store's answers to a customer. A failed reply is never sent: the model
   retries with the feedback, and after MAX_FAILED_CHECKS failed drafts no safe reply can be sent:
   nothing goes out and the turn ends "no_safe_reply", as sales/loop.py does. No chat goes to a
   person (DECISIONS items 53 and 57): there is no hand off to fall back on.
5. A model that does not answer ends the turn "model_error" with nothing sent.

send(to, text) is the only way out. The Arena passes a list's append, so a practice turn never
messages anyone; the tools run on the demo store with no Shopify keys (arena/match.py demo_store)
in a throwaway database.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine import plug as plug_mod
from engine.lessons import slot
from kit import send_check, tools
from kit.model import ModelError
from kit.tools import draft_order, store
from sales import loop
from sales.stages import Stage

log = logging.getLogger("kit.turn")

FILES = ("plug.json", "instructions.md", "card.json")
CARD_KEYS = ("name", "does", "good", "never", "needs")
BUILT_KEYS = ("agent", "tools", "level", "at")  # what Quick start's Build adds to the card (reflection/quickstart.py)
MAX_FILE_BYTES = {"plug.json": 200_000, "instructions.md": 40_000, "card.json": 20_000}
MAX_CARD_LINE = 600
MAX_CARD_ITEMS = 12
LEFT_OUT = ("switch_stage",)  # a new agent has one stage, so there is nowhere to move
# Quick start's tool keys (reflection/quickstart.py TOOLS) as the kit/tools files behind them;
# whatsapp is the channel the chat is on, so it needs no tool. store and delivery are the same name.
QUICK_TOOLS = {"orders": ("find_order", "draft_order"), "whatsapp": ()}
MAX_TOOL_STEPS = 4
MAX_CALLS_PER_STEP = 3
MAX_FAILED_CHECKS = 3
REPLY_ACTION = "reply"  # a plug with this action answers customers: the full send check applies
RETRY = loop.RETRY


class Refused(ValueError):
    """The agent folder cannot be read as an agent; the message says why."""


@dataclass(frozen=True)
class Agent:
    name: str
    folder: Path
    plug: object          # engine/plug.py Plug
    instructions: str
    card: dict            # name, does, good (strings), never, needs (lists of strings)
    tools: tuple          # the kit/tools names offered, in the plug's order
    missing: tuple        # tool names the plug names that no tool file has (or that are left out)
    stage: Stage
    full_check: bool


def _read(folder, name):
    p = folder / name
    if p.is_symlink() or not p.is_file():
        raise Refused(f"no {name} in the agent folder")
    if p.stat().st_size > MAX_FILE_BYTES[name]:
        raise Refused(f"{name} is over {MAX_FILE_BYTES[name]} bytes")
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise Refused(f"{name} could not be read as text") from None


def _line(v, what):
    if not isinstance(v, str) or not v.strip():
        raise Refused(f"card.json {what}: one plain line")
    if len(v) > MAX_CARD_LINE:
        raise Refused(f"card.json {what}: at most {MAX_CARD_LINE} characters")
    return " ".join(v.split())


def _lines(v, what):
    """A line or a list of lines, as a list; an empty list when v is empty. A need may be Quick
    start's {what, tool, connected}: it reads as its what."""
    if v in (None, "", []):
        return []
    items = [v] if isinstance(v, str) else v
    if not isinstance(items, list) or len(items) > MAX_CARD_ITEMS:
        raise Refused(f"card.json {what}: a line or a list of at most {MAX_CARD_ITEMS} lines")
    return [_line(x.get("what") if isinstance(x, dict) and what == "needs" else x, what) for x in items]


def read_card(text, agent=None):
    """card.json as {name, does, good, never, needs}: good is required, it decides the Arena. The keys
    Build adds (BUILT_KEYS) are allowed; its agent, when there, must be this agent."""
    try:
        d = json.loads(text)
    except ValueError:
        raise Refused("card.json is not JSON") from None
    if not isinstance(d, dict):
        raise Refused("card.json is one object")
    unknown = sorted(set(d) - set(CARD_KEYS) - set(BUILT_KEYS))
    if unknown:
        raise Refused(f"card.json has keys it should not: {', '.join(unknown)}")
    if agent is not None and "agent" in d and d["agent"] != agent:
        raise Refused(f"card.json names the agent {d['agent']}, but its folder is {agent}")
    return {"name": _line(d.get("name"), "name"), "does": _line(d.get("does"), "does"),
            "good": _line(d.get("good"), "good"), "never": _lines(d.get("never"), "never"),
            "needs": _lines(d.get("needs"), "needs")}


def tools_of(plug):
    """(offered, missing): the kit/tools names behind the tools the plug names, in its order (a Quick
    start key read through QUICK_TOOLS), and the names that have no tool file or are left out."""
    offered, missing = [], []
    for name in plug.risk.tools:
        for file in QUICK_TOOLS.get(name, (name,)):
            if file in tools.TOOLS and file not in LEFT_OUT:
                if file not in offered:
                    offered.append(file)
            elif file not in missing:
                missing.append(file)
    return tuple(offered), tuple(missing)


def load(folder):
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise Refused(f"no agent folder at {folder}")
    try:
        raw = json.loads(_read(folder, "plug.json"))
        p = plug_mod.from_dict(raw, folder)
    except ValueError as e:
        raise Refused(f"plug.json: {e}") from None
    if p.agent != folder.name:
        raise Refused(f"plug.json names the agent {p.agent}, but its folder is {folder.name}")
    instructions = _read(folder, "instructions.md").strip()
    if not instructions:
        raise Refused("instructions.md is empty")
    card = read_card(_read(folder, "card.json"), p.agent)
    offered, missing = tools_of(p)
    stage = Stage(p.stages[0] if p.stages else "all", card["name"], card["does"], offered, ())
    return Agent(name=p.agent, folder=folder, plug=p, instructions=instructions, card=card, tools=offered,
                 missing=missing, stage=stage, full_check=REPLY_ACTION in p.actions)


@dataclass
class TurnResult:
    outcome: str                  # replied, no_safe_reply or model_error
    reply: str | None = None
    failed: list = field(default_factory=list)  # [{check, why}] when the turn ended on failed checks


def system_prompt(agent, lessons=()):
    parts = [agent.instructions]
    picked = slot(agent.plug, list(lessons))
    if picked:
        parts.append(picked)
    return {"role": "system", "content": "\n\n".join(parts)}


def _check(agent, reply, customer_text, amounts, vocab, sizes, names, chats, chat_id):
    if not agent.full_check:
        problems = send_check.style_problems(reply)
        return (not problems), " ".join(dict.fromkeys(problems))
    return send_check.check(reply, customer_text, amounts, vocab, sizes, orders=loop.order_names(chats, chat_id),
                            links=loop.store_links(chats, chat_id), names=names)


def turn(agent, text, *, chats, chat_id, model, send, customer_id, lessons=(), message=None):
    """One message from the person the agent serves. send(to, text) is the only way out.
    message: the channels/base.py Message the tools may read (who wrote, a voice note); made from
    text when None."""
    from channels.base import Message
    msg = message or Message(channel="whatsapp", customer_id=customer_id, text=text)
    history = chats.messages(chat_id)
    chats.add_step(chat_id, "user", content=text or None)
    ctx = tools.Context(chat_id=chat_id, stage=agent.stage, chats=chats, model=model, message=msg, send=send,
                        stages={agent.stage.name: agent.stage})
    amounts, vocab, sizes, names = set(), frozenset(), frozenset(), frozenset()
    if store.NAME in agent.tools:
        try:
            amounts, vocab = set(store.price_points()), store.vocabulary()
            sizes, names = store.size_strings(), store.titles()
        except Exception:
            log.exception("store data unavailable; no price can pass the check this turn")
    convo = history + [{"role": "user", "content": text or "(empty message)"}]
    system = system_prompt(agent, lessons)
    failed = []
    try:
        while True:
            reply = _draft(ctx, system, convo, amounts)
            passed, feedback = _check(agent, reply, text, amounts, vocab, sizes, names, chats, chat_id)
            if passed and reply:
                send(customer_id, reply)
                chats.add_step(chat_id, "assistant", content=reply)
                return TurnResult("replied", reply)
            feedback = feedback or "The reply was empty. Write one."
            failed.append({"check": "send_check", "why": " ".join(feedback.split())[:300]})
            if len(failed) >= MAX_FAILED_CHECKS:  # no safe reply: nothing goes out (sales/loop.py)
                loop.drop_draft(chats, chat_id)
                return TurnResult("no_safe_reply", None, failed)
            convo.append({"role": "assistant", "content": reply})
            convo.append({"role": "user", "content": RETRY.format(feedback=feedback)})
    except ModelError as e:
        log.warning("the agent's model did not answer: %s", e)
        loop.drop_draft(chats, chat_id)
        return TurnResult("model_error")


def _draft(ctx, system, convo, amounts):
    """Model steps until it answers in words: the draft reply."""
    for step in range(MAX_TOOL_STEPS + 1):
        last = step == MAX_TOOL_STEPS
        defs = [] if last else tools.definitions(ctx.stage)
        out = ctx.model.chat([system] + convo, tools=defs or None)
        out = out if isinstance(out, dict) else {}
        calls = out.get("tool_calls") or []
        calls = [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
        if not calls or last:
            return (out.get("content") or "").strip()
        convo.append({"role": "assistant", "content": out.get("content"), "tool_calls": calls})
        ctx.chats.add_step(ctx.chat_id, "assistant", content=out.get("content"), tool_calls=calls)
        for i, call in enumerate(calls):
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = fn.get("name") if isinstance(fn.get("name"), str) else ""
            if i >= MAX_CALLS_PER_STEP:
                result = dict(loop.TOO_MANY_CALLS)
            else:
                result = tools.run(name, loop._arguments(fn.get("arguments")), ctx)
            body = json.dumps(result, ensure_ascii=False)
            call_id = call.get("id") if isinstance(call.get("id"), str) else ""
            convo.append({"role": "tool", "tool_call_id": call_id, "content": body})
            ctx.chats.add_step(ctx.chat_id, "tool", content=body, tool_call_id=call_id, name=name)
            if name in tools.AMOUNT_TOOLS:
                amounts |= send_check.amounts_in(result)
    return ""


def order_made(chats, chat_id):
    """The order a tool placed in this turn (draft_order created), or None."""
    try:
        return draft_order.created(chats.steps(chat_id))
    except Exception:
        log.exception("could not tell if this turn placed an order")
        return None
