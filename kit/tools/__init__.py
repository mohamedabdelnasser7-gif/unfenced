"""The tool registry. One file per tool, each with its own checks.

Every tool module has:
  NAME
  DEFINITION, or definition(stage), an OpenAI-style function definition
  check(args, ctx) -> (passed, feedback), run before the tool does anything
  run(args, ctx) -> dict, the result the model reads
and may have NEEDS (the argument names it looks up by) with table(ctx) -> dict: every option it holds.
A call that leaves every NEEDS key out or blank gets table(ctx) instead of a refusal (Arena run
20261104T143545, cause 4: the agent asked the customer's area again and again and never quoted a fee),
so the model can answer from the whole table and ask for the key after.

A result may carry "next_stage". The agent's loop applies it, so stage changes
come from tool results, never from keyword rules.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from kit.tools import (calendar_tool, cod_risk, data, delivery, draft_order, find_order, mailbox, store, switch_stage,
                       voice_note)

log = logging.getLogger("kit.tools")

TOOLS = {m.NAME: m for m in (store, voice_note, delivery, draft_order, cod_risk, find_order, switch_stage, data,
                             mailbox, calendar_tool)}  # email and calendar: the personal assistant's demo mail and calendar

# Control tools are offered in every stage where the agent replies, on top of the stage's own list.
CONTROL = ("switch_stage",)

# The only tools whose results may add amounts to the send check. store: every price comes
# from the catalogue (Shopify or demo/catalogue.json), never from the model's arguments.
# delivery: fee, from the zone in the delivery data. draft_order: price per line from the
# catalogue, and subtotal, fee and total worked out in code from the catalogue and delivery data.
# find_order: the total of each of the customer's own past orders, from the store's own record
# (found by the chat's WhatsApp number, matched exactly in code), so a past order's real total
# passes. Its items carry no line price today. data: a price, fee, total or subtotal in the agent's own
# sample data (kit/sample.py), read from its file in code, rows made up at Build or added by the user,
# never from the model's arguments. cod_risk is for the team only and adds none.
# A new tool joins this list only in the PR that builds it, with a line here naming which of
# its keys (price, fee, total, subtotal) the server computes. A voice note or any other free
# text never adds an amount.
AMOUNT_TOOLS = ("store", "delivery", "draft_order", "find_order", "data")


@dataclass
class Context:
    """What a tool may use during one turn."""
    chat_id: str
    stage: Any                      # the chat's Stage (has .name, .tools, .moves_to)
    chats: Any                      # kit.chats.Chats
    model: Any                      # kit.model.Model or the fake model
    message: Any                    # channels.base.Message
    send: Callable[[str, str], Any] # send(to, text) on the customer's channel
    stages: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)  # per-turn results a tool keeps (the voice note, heard once)
    lesson_ids: set = field(default_factory=set)  # the lessons handed so far this turn; a tool's own rows keep them
    data: Any = None                # a Quick start agent's sample data (kit/sample.py), read by the data tool


def offered(stage):
    """Tool names the model may call in this stage: the stage's built tools, then control tools."""
    names = [n for n in stage.tools if n in TOOLS]
    return names + [n for n in CONTROL if n in TOOLS and stage.moves_to]


def definitions(stage):
    """The function definitions sent to the model for this stage, fresh every step."""
    out = []
    for name in offered(stage):
        mod = TOOLS[name]
        out.append(mod.definition(stage) if hasattr(mod, "definition") else mod.DEFINITION)
    return out


def _wants_table(mod, args):
    """True when mod has NEEDS and table, and the call leaves every NEEDS key out or blank (None or
    only spaces), so it gets every option (table) instead of a refusal."""
    needs = getattr(mod, "NEEDS", ())
    if not needs or not callable(getattr(mod, "table", None)):
        return False
    return all(args.get(k) is None or (isinstance(args.get(k), str) and not args.get(k).strip()) for k in needs)


def run(name, args, ctx):
    """Run one tool call from the model. Never raises; problems come back as feedback."""
    if name not in offered(ctx.stage):
        return {"ok": False, "feedback": f"The tool {name} is not available at this stage."}
    if not isinstance(args, dict):
        return {"ok": False, "feedback": "Tool arguments must be a JSON object."}
    mod = TOOLS[name]
    if _wants_table(mod, args):
        try:
            return mod.table(ctx)
        except Exception:  # a tool failure must not end the turn
            log.exception("tool %s failed to give its table", name)
            return {"ok": False, "feedback": f"The tool {name} failed."}
    passed, feedback = mod.check(args, ctx)
    if not passed:
        return {"ok": False, "feedback": feedback}
    try:
        return mod.run(args, ctx)
    except Exception:  # a tool failure must not end the turn
        log.exception("tool %s failed", name)
        return {"ok": False, "feedback": f"The tool {name} failed."}
