"""One turn of an agent made by Quick start (new, 2026-11-01; DECISIONS item 58).

A new agent is a folder, <db folder>/agents/<name>/, holding the three files Quick start's Build
writes (reflection/quickstart.py):
  plug.json        passes engine/plug.py from_dict; its "agent" is the folder's name.
  instructions.md  its prompt, as written for the owner's yes.
  card.json        the card the user said yes to: name, does, good, never, needs, and from the
                   live cases work (DECISIONS item 68) bad, the bad result, and case, what one case
                   is: {input: what arrives, starts: "person" or "agent", output: what the agent
                   produces or does, ends: when the case is over}. Build also writes agent, tools,
                   level and at, and each need as {what, tool, connected}; a need reads as its "what",
                   and the rest is checked for shape and left alone. A card with no case is a chat
                   case, as every card was before.

load(folder) reads them, under size caps and with no link followed, into an Agent. turn() runs one
message from the person the agent serves, the way sales/loop.py runs a Sales turn, cut down to
what any agent has. With first=True the text is the case's input, not a person's message: the agent
writes first (a lead it follows up), and the input is saved under a frame line so later turns read it.

1. instructions.md is the system prompt. The lessons it has earned go under the plug's slot line
   (none in the Arena's first runs: every agent starts from zero, DECISIONS item 20).
2. The chat so far comes from kit/chats.py, so the tools read it the way they read a Sales chat.
3. Tools: card.json's tools, when Build wrote them, are the most the plug may name: a plug that
   names another is refused. Then only the ones the plug names (its high risk tools, the one list of tools a plug has)
   that exist in kit/tools, minus switch_stage, since a new agent has one stage. Quick start names
   what it connects by its own keys (reflection/quickstart.py TOOLS): QUICK_TOOLS reads those as the
   kit/tools files behind them, and whatsapp as the channel the chat is on, no tool. A name with no
   tool file is left out and listed in Agent.missing. At most MAX_TOOL_STEPS tool steps a turn
   and MAX_CALLS_PER_STEP calls a step, then the model must answer in words. A folder with sample data
   (kit/sample.py, sample-data.json: made up at Build, rows the user added) also offers the data tool
   (DATA_TOOL), and for one with the store tool and no Shopify keys the store reads its sample products.
4. The send check: the full check (kit/send_check.py) when the card connects whatsapp, store, orders
   or delivery (it talks to customers or quotes the store), so script, style, amounts from tools only
   and links all hold. For an agent Build made, the amounts rule reads only numbers that are prices or
   fees (a currency next to it, or a price word before it), never an order number, a ticket id, a
   postal code, a date, a time or a count, and the stock count rule holds only with the store tool;
   the Sales agent (sales/loop.py) keeps the whole check. A folder written by hand, whose card names no tools, keeps the older rule: the
   full check when the plug declares a "reply" action, as the Sales plug does. The house style part
   only (banned words, dashes, emoji, markdown) for any other agent, whose replies are not a store's
   answers to a customer: a ticket agent that names a refund amount is not held to store prices. A failed reply is never sent: the model
   retries with the feedback, and after MAX_FAILED_CHECKS failed drafts no safe reply can be sent:
   nothing goes out and the turn ends "no_safe_reply", as sales/loop.py does. No chat goes to a
   person (DECISIONS items 53 and 57): there is no hand off to fall back on.
5. Actions: a card with a case offers one more tool, take_action, whose action is one of the plug's
   declared actions other than reply (a tag such as "needs the team", a close). Nothing runs; the
   action and its short note are saved as a tool step and come back in TurnResult.actions, so the
   practice match and its judge see what the agent did beside what it wrote (DECISIONS item 72: a
   case that needs people ends with the agent's own tag, never a hand over).
6. A model that does not answer ends the turn "model_error" with nothing sent.
7. The pause switch (kit/switch.py, DECISIONS item 54): while the agent is paused the message is still
   saved, so the chat is whole when it resumes, and the turn ends "paused" with nothing sent and no
   model call, as sales/loop.py does for the Sales agent.

built(db_folder) reads every agent folder under <db folder>/agents/ that loads; the night and the
Morning page take these agents beside the repo's own (reflection/night.py other_plugs).

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
from kit import sample as sample_mod, send_check, switch, tools
from kit.model import ModelError
from kit.tools import draft_order, store
from sales import loop
from sales.stages import Stage

log = logging.getLogger("kit.turn")

FILES = ("plug.json", "instructions.md", "card.json")
AGENTS = "agents"  # <db folder>/agents/<name>/: where Quick start's Build writes an agent (reflection/quickstart.py)
PAUSED = "paused"
MAX_AGENTS = 50  # agent folders built() reads at most
CARD_KEYS = ("name", "does", "good", "never", "needs", "bad", "case")
BUILT_KEYS = ("agent", "tools", "kind", "level", "at")  # what Quick start's Build adds to the card (reflection/quickstart.py)
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
REPLY_ACTION = "reply"  # a hand-written folder's plug with this action answers customers: the full send check
FULL_CHECK_TOOLS = ("whatsapp", "store", "orders", "delivery")  # a card that connects one talks to customers or gives amounts: the full check
CHANNEL = "whatsapp"
CASE_KEYS = ("input", "starts", "output", "ends")
STARTS = ("person", "agent")  # who writes first in a case
DATA_TOOL = "data"  # kit/tools/data.py: the agent's sample data, offered when its folder has some
ACT_TOOL = "take_action"  # a case agent's declared actions (a tag, a close); runs nothing, is only recorded
MAX_ACT_NOTE = 200
FIRST = ("(A new case. You write first: nobody has written to you yet. The case you start from: {input}) "
         "Write your first message for this case.")
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
    acts: tuple = ()      # the declared actions take_action offers (a card with a case only)
    data: dict | None = None  # its sample data (kit/sample.py), read by the data tool and the store tool
    priced_only: bool = False  # the full check holds only prices and fees to the data (an agent Build made)
    stock: bool = True    # the full check's stock count rule (an agent with the store tool, or written by hand)


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


def read_case(v):
    """card.json case as {input, starts, output, ends}, or None when the card has none (a chat case)."""
    if v is None:
        return None
    if not isinstance(v, dict) or set(v) - set(CASE_KEYS):
        raise Refused("card.json case: {input, starts, output, ends}")
    if v.get("starts") not in STARTS:
        raise Refused("card.json case starts: person or agent")
    return {"input": _line(v.get("input"), "case input"), "starts": v["starts"],
            "output": _line(v.get("output"), "case output"), "ends": _line(v.get("ends"), "case ends")}


def card_tools(text):
    """The tools card.json says are connected (Build writes them), as a set, or None when it names none
    (a folder written by hand). A list of plain tool names, else Refused."""
    try:
        d = json.loads(text)
    except (ValueError, RecursionError):
        raise Refused("card.json is not JSON") from None
    if not isinstance(d, dict) or "tools" not in d:
        return None
    got = d["tools"]
    if not isinstance(got, list) or len(got) > MAX_CARD_ITEMS or not all(
            isinstance(t, str) and plug_mod.NAME.fullmatch(t) for t in got):
        raise Refused(f"card.json tools: a list of at most {MAX_CARD_ITEMS} tool names")
    return set(got)


def read_card(text, agent=None):
    """card.json as {name, does, good, never, needs}, with bad and case when the card has them: good is
    required, it decides the Arena. The keys Build adds (BUILT_KEYS) are allowed; its agent, when there,
    must be this agent. A card without bad or case reads exactly as before, so its fingerprint holds."""
    try:
        d = json.loads(text)
    except (ValueError, RecursionError):
        raise Refused("card.json is not JSON") from None
    if not isinstance(d, dict):
        raise Refused("card.json is one object")
    unknown = sorted(set(d) - set(CARD_KEYS) - set(BUILT_KEYS))
    if unknown:
        raise Refused(f"card.json has keys it should not: {', '.join(unknown)}")
    if agent is not None and "agent" in d and d["agent"] != agent:
        raise Refused(f"card.json names the agent {d['agent']}, but its folder is {agent}")
    card = {"name": _line(d.get("name"), "name"), "does": _line(d.get("does"), "does"),
            "good": _line(d.get("good"), "good"), "never": _lines(d.get("never"), "never"),
            "needs": _lines(d.get("needs"), "needs")}
    if d.get("bad") not in (None, ""):
        card["bad"] = _line(d["bad"], "bad")
    case = read_case(d.get("case"))
    if case is not None:
        card["case"] = case
    return card


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
    except (ValueError, RecursionError) as e:
        raise Refused(f"plug.json: {e}") from None
    if p.agent != folder.name:
        raise Refused(f"plug.json names the agent {p.agent}, but its folder is {folder.name}")
    instructions = _read(folder, "instructions.md").strip()
    if not instructions:
        raise Refused("instructions.md is empty")
    text = _read(folder, "card.json")
    card = read_card(text, p.agent)
    connected = card_tools(text)
    if connected is not None:  # the plug offers nothing the card the owner said yes to does not connect
        extra = sorted(set(p.risk.tools) - connected)
        if extra:
            raise Refused(f"plug.json names tools the card does not connect: {', '.join(extra)}")
    offered, missing = tools_of(p)
    data = sample_mod.read(folder)
    if data is not None and DATA_TOOL not in offered:  # the rows it works from with no real connection
        offered += (DATA_TOOL,)
    stage = Stage(p.stages[0] if p.stages else "all", card["name"], card["does"], offered, ())
    if connected is None:  # a folder written by hand: the older rule
        talks, priced_only, stock = REPLY_ACTION in p.actions, False, True
    else:  # an agent Build made: the amounts rule reads prices and fees only, the stock rule needs the store
        talks, priced_only, stock = bool(connected & set(FULL_CHECK_TOOLS)), True, "store" in connected
    acts = tuple(a for a in p.actions if a != REPLY_ACTION) if "case" in card else ()
    return Agent(name=p.agent, folder=folder, plug=p, instructions=instructions, card=card, tools=offered,
                 missing=missing, stage=stage, full_check=talks, acts=acts, data=data, priced_only=priced_only,
                 stock=stock)


def built(db_folder, most=MAX_AGENTS):
    """Every agent under <db_folder>/agents/ that loads, sorted by name: [Agent]. A folder that is a
    link, hidden (a Build still writing) or does not load is left out. None of them when agents/ is
    missing or a link."""
    base = Path(db_folder) / AGENTS
    if base.is_symlink() or not base.is_dir():
        return []
    out = []
    for folder in sorted(base.iterdir()):
        if len(out) >= most:
            break
        if folder.name.startswith(".") or folder.is_symlink() or not folder.is_dir() \
                or not plug_mod.AGENT_NAME.fullmatch(folder.name):
            continue
        try:
            out.append(load(folder))
        except Refused as e:
            log.warning("agent folder %s left out: %s", folder.name, e)
    return out


@dataclass
class TurnResult:
    outcome: str                  # replied, no_safe_reply, model_error or paused
    reply: str | None = None
    failed: list = field(default_factory=list)  # [{check, why}] when the turn ended on failed checks
    retried: list = field(default_factory=list)  # [{check, why}] of the drafts that failed before the reply went out
    actions: list = field(default_factory=list)  # [{action, note}] take_action recorded this turn


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
                            links=loop.store_links(chats, chat_id), names=names, priced_only=agent.priced_only,
                            stock=agent.stock)


PRACTICE_CHANNEL = "practice"
ORDER_FILES = ("find_order", "draft_order")  # they know the customer by the WhatsApp number


def practice_channel(agent):
    """The channel a practice or exam chat opens on: WhatsApp for a chat case (a card with no case) or an
    agent whose order tools know the customer by the WhatsApp number, else the practice channel."""
    if "case" not in agent.card or any(t in agent.tools for t in ORDER_FILES):
        return CHANNEL
    return PRACTICE_CHANNEL


def act_definition(agent):
    """The take_action tool for a case agent, or None when it declares no action to take."""
    if not agent.acts:
        return None
    lines = "; ".join(f"{a}: {agent.plug.actions[a]}" for a in agent.acts)
    return {"type": "function", "function": {
        "name": ACT_TOOL,
        "description": ("Take one of your declared actions in this case and say it in a short note (for a tag, "
                        "the tag). Nothing else runs; it is recorded as what you did. Your actions: " + lines),
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": list(agent.acts)},
            "note": {"type": "string", "description": "A short note on what you did, for a tag the tag itself."}},
            "required": ["action"], "additionalProperties": False}}}


def turn(agent, text, *, chats, chat_id, model, send, customer_id, lessons=(), message=None, first=False,
         channel=CHANNEL):
    """One message from the person the agent serves. send(to, text) is the only way out.
    message: the channels/base.py Message the tools may read (who wrote, a voice note); made from
    text when None. first: text is the case's input and the agent writes first (no person wrote).
    channel: the channel the Message names when none is given (the Arena passes its practice one)."""
    from channels.base import Message
    if first:
        text = FIRST.format(input=" ".join(str(text or "").split()))
    msg = message or Message(channel=channel, customer_id=customer_id, text=text)
    history = chats.messages(chat_id)
    chats.add_step(chat_id, "user", content=text or None)
    if switch.is_paused(agent.name, db=chats.db):  # saved above; nothing goes out while paused
        return TurnResult(PAUSED)
    ctx = tools.Context(chat_id=chat_id, stage=agent.stage, chats=chats, model=model, message=msg, send=send,
                        stages={agent.stage.name: agent.stage}, data=agent.data)
    items = sample_mod.store_items(agent.data) if store.NAME in agent.tools else []
    token = store.SAMPLE.set(items) if items else None  # its sample products when no Shopify keys are set
    try:
        return _turn(agent, text, ctx, history, chats, chat_id, send, customer_id, lessons, first)
    finally:
        if token is not None:
            store.SAMPLE.reset(token)


def _turn(agent, text, ctx, history, chats, chat_id, send, customer_id, lessons, first):
    amounts, vocab, sizes, names = set(), frozenset(), frozenset(), frozenset()
    if store.NAME in agent.tools:
        try:
            amounts, vocab = set(store.price_points()), store.vocabulary()
            sizes, names = store.size_strings(), store.titles()
        except Exception:
            log.exception("store data unavailable; no price can pass the check this turn")
    convo = history + [{"role": "user", "content": text or "(empty message)"}]
    system = system_prompt(agent, lessons)
    failed, acted = [], []
    said = "" if first else text  # the person's words the full check reads; a case input is not theirs
    try:
        while True:
            reply = _draft(ctx, system, convo, amounts, agent, acted)
            passed, feedback = _check(agent, reply, said, amounts, vocab, sizes, names, chats, chat_id)
            if passed and reply:
                send(customer_id, reply)
                chats.add_step(chat_id, "assistant", content=reply)
                return TurnResult("replied", reply, retried=list(failed), actions=list(acted))
            feedback = feedback or "The reply was empty. Write one."
            failed.append({"check": "send_check", "why": " ".join(feedback.split())[:300]})
            if len(failed) >= MAX_FAILED_CHECKS:  # no safe reply: nothing goes out (sales/loop.py)
                loop.drop_draft(chats, chat_id)
                return TurnResult("no_safe_reply", None, failed, actions=list(acted))
            convo.append({"role": "assistant", "content": reply})
            convo.append({"role": "user", "content": RETRY.format(feedback=feedback)})
    except ModelError as e:
        log.warning("the agent's model did not answer: %s", e)
        loop.drop_draft(chats, chat_id)
        return TurnResult("model_error")


def _draft(ctx, system, convo, amounts, agent=None, acted=None):
    """Model steps until it answers in words: the draft reply. A take_action call (a case agent's
    declared action) runs nothing: it is added to acted and the model reads that it was recorded."""
    act = act_definition(agent) if agent is not None else None
    for step in range(MAX_TOOL_STEPS + 1):
        last = step == MAX_TOOL_STEPS
        defs = [] if last else tools.definitions(ctx.stage) + ([act] if act else [])
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
            elif act is not None and name == ACT_TOOL:
                result = _act(agent, loop._arguments(fn.get("arguments")), acted)
            else:
                result = tools.run(name, loop._arguments(fn.get("arguments")), ctx)
            body = json.dumps(result, ensure_ascii=False)
            call_id = call.get("id") if isinstance(call.get("id"), str) else ""
            convo.append({"role": "tool", "tool_call_id": call_id, "content": body})
            ctx.chats.add_step(ctx.chat_id, "tool", content=body, tool_call_id=call_id, name=name)
            if name in tools.AMOUNT_TOOLS:
                amounts |= send_check.amounts_in(result)
    return ""


def _act(agent, args, acted):
    """One take_action call: recorded in acted when it names a declared action, else feedback."""
    args = args if isinstance(args, dict) else {}
    name = args.get("action")
    if name not in agent.acts:
        return {"ok": False, "feedback": f"Take one of your declared actions: {', '.join(agent.acts)}."}
    note = args.get("note")
    note = " ".join(note.split())[:MAX_ACT_NOTE] if isinstance(note, str) else ""
    if acted is not None:
        acted.append({"action": name, "note": note})
    return {"ok": True, "recorded": name}


def order_made(chats, chat_id):
    """The order a tool placed in this turn (draft_order created), or None."""
    try:
        return draft_order.created(chats.steps(chat_id))
    except Exception:
        log.exception("could not tell if this turn placed an order")
        return None
