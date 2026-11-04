"""One Sales agent turn: a customer message in, at most one checked reply out.

1. Load the chat and its stage. The agent always keeps the chat: no person takes it over
   (DECISIONS item 53).
2. Pick the lessons that fit (at most 8) and call the model with the instructions, the
   rules the send check holds every reply to (kit/send_check.py prompt_rules, in the check's
   own words, so the exam never fails a rule the agent was not shown), the lessons and only
   this stage's tools. Tools and stage are sent fresh every step.
   When the customer's last chat ended without an order, fast reflection's note for this
   chat (reflection/fast.py) goes last in the prompt, read once a turn before the first
   model call; it is not a lesson and its id never joins the lesson ids a row keeps.
   Right before the first model call, and only then, the channel's typing dots are asked for
   once (typing). A paused agent, a customer over a limit and a turn of fixed lines only make
   no model call, so they get no dots. A turn that ends with no safe reply still had them,
   since a reply was meant; it sends nothing else.
3. At most MAX_TOOL_STEPS tool steps, then the model must answer in words. At most
   MAX_CALLS_PER_STEP tool calls run in one step; the voice note is heard once per turn.
4. The send check runs on the reply. A failed reply is never sent: the model retries
   with the check's feedback. After 3 failed checks in a row in a chat, no safe reply can
   be sent: nothing goes to the customer, the chat stays with the agent, and the row
   no_safe_reply records the chat as lost for Reflection and the Arena (DECISIONS item 53).
   Both counts start again, so the agent answers the next message itself. A reply that
   passes starts the count again.
5. When the model is down, the customer gets one fixed line and the chat keeps its
   stage. Fixed lines are saved with the name FIXED. The model down and limit lines the
   loop sends itself, and a turn with no safe reply, drop any pending order summary, so an
   order is only confirmed after the model's own summary reply. The photo and voice lines do not drop
   it; a confirm still needs every message after the summary to be a plain yes, and a
   photo or voice mark never is. The MAX_MODEL_ERRORS-th model error in a row in a chat
   is no safe reply too, the same as after failed checks: no line goes out. A reply that
   passes starts the count again. A turn that crashes in code counts the same way
   (failed_turn): the same line, and the same count. Over a model call limit, the customer gets one fixed line,
   once per window. When the turn already created an order, the customer gets
   ORDER_PLACED (its number and total) instead of any of these lines, and also when there
   is no safe reply. ORDER_PLACED goes out once a turn.
6. Every outcome goes to the result log.
7. A paused agent (kit/switch.py) saves the message and sends nothing: no line, no row.

Photos go to the model as image parts in that turn's user message. SQLite keeps only their hash and type. A photo that could not be
opened and a voice note that could not be fetched (or were not downloaded, over a limit)
are saved as a mark with "opened": false, so a caption on them never reads as a plain
yes to an order summary (review t261028j finding 3).
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.lessons import slot
from sales import stages
from kit import limits as limits_mod
from kit import media, orders, send_check, switch, tools
from kit.chats import FIXED
from kit.model import ModelError
from kit.tools import draft_order, find_order, store
from reflection import PLUG

log = logging.getLogger("sales.loop")

INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8").strip()
MAX_TOOL_STEPS = 4
MAX_CALLS_PER_STEP = 3
MAX_FAILED_CHECKS = 3
MAX_MODEL_ERRORS = 2

PHOTO_NOT_OPENED = {
    "arabic": "مش قادر أفتح الصورة دي. ابعتها تاني صورة عادية وحجمها أقل من 5 ميجا.",
    "franco": "msh 2ader afta7 el sora di. momken teb3atha tany sora 3adeya w a2al mn 5 mega?",
    "english": "I can't open that photo. Please send it again as a normal photo under 5 MB.",
}
VOICE_NOT_HEARD = {
    "arabic": "مش قادر أسمع الفويس ده. ابعته تاني أو اكتبلي رسالتك.",
    "franco": "msh 2ader asma3 el voice da. momken teb3ato tany aw tektebli resaltak?",
    "english": "I can't play that voice note. Please send it again or type your message.",
}
LIMIT_LINE = {
    "arabic": "وصلنا رسايل كتير في وقت قصير، فمش هقدر أرد دلوقتي. ابعتلنا تاني كمان شوية.",
    "franco": "wasalna rasayel kteer f wa2t 2osayar, fa msh ha2dar arod delwa2ty. eb3atlna tany kman shwaya.",
    "english": "We got a lot of messages in a short time, so I can't answer right now. Please write again in a little while.",
}
MODEL_DOWN = {
    "arabic": "مش قادر أرد دلوقتي. ابعتلي رسالتك تاني كمان كام دقيقة.",
    "franco": "msh 2ader arod delwa2ty. momken teb3atli resaltak tany kman kam di2i2a?",
    "english": "I can't answer right now. Please write again in a few minutes.",
}
# When draft_order created the order and the same turn then hit a limit, a model error or a
# crash, this line goes instead of the limit or model down line, so the customer knows the
# order exists and does not order again (review t261028j finding 2).
ORDER_PLACED = {
    "arabic": "اوردرك اتسجل برقم {order}، والإجمالي {total} جنيه.",
    "franco": "el order bta3ak etsagel b ra2am {order}, w el egmaly {total} geneh.",
    "english": "Your order {order} is placed. The total is {total} EGP.",
}
PAUSED = "paused"   # the turn of a paused agent: the message is saved, nothing goes out
NOT_OPENED = {"opened": False}   # the media mark for a photo or voice note no one could open
VOICE_NOTE = "(The customer sent a voice note. Call voice_note to hear it.)"
PHOTO_ONLY = "(The customer sent a photo.)"
RETRY = "(Store check, not from the customer.) Your last reply was not sent. {feedback} Write the reply again."
TOO_MANY_CALLS = {"ok": False, "feedback": f"At most {MAX_CALLS_PER_STEP} tool calls run in one step. This one was not run."}


@dataclass
class TurnResult:
    chat_id: str
    # replied, no_safe_reply, limited, model_error or turn_failed; paused (no row) when the agent is paused
    outcome: str
    reply: str | None = None


@dataclass
class _Turn:
    ctx: tools.Context
    customer_text: str
    lessons: object = None
    amounts: set = field(default_factory=set)
    tool_steps: int = 0
    note: str = ""  # fast reflection's note for this chat, under its heading; "" when none

    @property
    def lesson_ids(self):
        """The ids of the lessons handed this turn. They live on the tools' context, so the rows a
        tool writes itself (draft_order's order_drafted and order_created) keep them too."""
        return self.ctx.lesson_ids


def system_prompt(stage, picked, note=""):
    """The instructions, the rules the send check holds every reply to (kit/send_check.py prompt_rules, the
    same words the check and the exam read), the stage note, the lessons in the slot the engine writes from
    the plug, then fast reflection's note for this chat when it has one."""
    parts = [INSTRUCTIONS, send_check.prompt_rules(), stages.note(stage)]
    lessons = slot(PLUG, picked)
    if lessons:
        parts.append(lessons)
    if note:
        parts.append(note)
    return {"role": "system", "content": "\n\n".join(parts)}


def fast_note(fast, chat_id):
    """Fast reflection's note for this chat's prompt, or "". Never raises: a note that cannot be
    read, or that is not text, is left out and the turn goes on. The one path every agent reads its
    note by (Sales here, a built agent's Arena quick notes in kit/turn.py)."""
    if fast is None:
        return ""
    try:
        got = fast.for_prompt(chat_id)
        return got if isinstance(got, str) else ""
    except Exception:
        log.exception("could not read the fast note; the turn goes on without it")
        return ""


def user_message(msg, stage):
    text = msg.text or ""
    if msg.audio:
        text = (text + "\n" + VOICE_NOTE).strip()
    images = msg.images
    if not images:
        return {"role": "user", "content": text or "(empty message)"}
    parts = [{"type": "text", "text": text or PHOTO_ONLY}]
    parts += [media.image_part(i.data, i.mime) for i in images]
    return {"role": "user", "content": parts}


def last_customer_text(chats, chat_id):
    for s in reversed(chats.steps(chat_id)):
        if s["role"] == "user" and (s["content"] or "").strip():
            return s["content"]
    return ""


def warn_size_prices():
    """At start: log a warning for each price or fee that is also a catalogue size number.

    After is, for or ب the send check reads a size number as a size, so where prices sit
    among the size numbers, a wrong price there can pass. Returns the numbers found.
    """
    try:
        found = send_check.size_number_amounts(store.price_points(), store.size_strings())
    except Exception:
        log.exception("store data unavailable; prices were not checked against size numbers")
        return []
    if found:
        log.warning("prices or fees that are also size numbers: %s. After is, for or ب the send check "
                    "reads these as sizes, so a wrong price there can pass.", ", ".join(map(str, found)))
    return found


def turn(msg, *, chats, model, lessons, results, send, limits=None, over=None, fast=None, typing=None):
    """Handle one customer message. send(to, text) sends on the customer's channel.

    limits: a kit.limits.Limits; every model call in the turn is counted against it.
    over: the limit the webhook already found reached; the turn then makes no model call.
    fast: fast reflection's notes (reflection.fast.FastNotes); left out, no note is read.
    typing: called with no arguments right before the first model call (the channel's typing
    dots); left out, none are shown. A failure there is logged and the turn goes on.
    """
    kept = [media.fingerprint("image", i.data, i.mime) for i in msg.images]
    kept += [dict(NOT_OPENED, kind="image") for _ in range(msg.rejected_images or 0)]
    if msg.audio:
        kept.append(media.fingerprint("audio", msg.audio, msg.audio_mime))
    elif msg.audio_failed:
        kept.append(dict(NOT_OPENED, kind="audio"))
    # the open chat and the customer's step in one transaction: a quiet close never comes in between
    chat_id, n = chats.receive(msg.channel, msg.customer_id, content=msg.text or None, media=kept or None,
                               message_id=msg.message_id or None)
    stage = stages.get(chats.stage(chat_id))
    history = chats.messages(chat_id, upto=n - 1)
    if switch.is_paused(PLUG.agent, db=chats.db):
        return TurnResult(chat_id, PAUSED)

    customer_text = msg.text or last_customer_text(chats, chat_id)
    who = limits_mod.key(msg.channel, msg.customer_id)
    if limits is not None:
        over = over or limits.over(who)
        model = limits.meter(model, who)
    if over:
        return _limited(chat_id, stage, msg, customer_text, over, chats=chats, results=results, send=send,
                        limits=limits)

    ctx = tools.Context(chat_id=chat_id, stage=stage, chats=chats, model=model, message=msg,
                        send=send, stages=stages.STAGES)
    t = _Turn(ctx=ctx, customer_text=customer_text, lessons=lessons)
    vocab, sizes, names = frozenset(), frozenset(), frozenset()
    try:
        t.amounts = set(store.price_points())
        vocab = store.vocabulary()
        sizes = store.size_strings()
        names = store.titles()
    except Exception:
        log.exception("store data unavailable; no price can pass the check this turn")

    script = send_check.detect_script(t.customer_text) or "arabic"
    fixed = []
    if msg.rejected_images:
        fixed.append(("photo_not_opened", PHOTO_NOT_OPENED[script]))
    if msg.audio_failed:
        fixed.append(("voice_not_heard", VOICE_NOT_HEARD[script]))
    n = None
    for _, line in fixed:
        send(msg.customer_id, line)
        n = chats.add_step(chat_id, "assistant", content=line, name=FIXED)
    if fixed and not (msg.text or msg.audio or msg.images):
        results.record(chat_id, "replied", step=n, stage=stage.name, detail={"fixed_reply": fixed[-1][0]})
        return TurnResult(chat_id, "replied", fixed[-1][1])

    convo = history + [user_message(msg, stage)]
    t.note = fast_note(fast, chat_id)  # read just before the first model call, once a turn
    _typing(typing)
    try:
        return _answer(t, convo, msg, vocab, sizes, names, results=results, send=send)
    except limits_mod.OverLimit as e:
        return _limited(chat_id, ctx.stage, msg, t.customer_text, e.which, chats=chats, results=results, send=send,
                        limits=limits)
    except ModelError as e:
        return _model_error(t, msg, e, results=results, send=send)


def _typing(typing):
    """The typing dots, once, right before the first model call. A courtesy: never stops the turn."""
    if typing is None:
        return
    try:
        typing()
    except Exception:
        log.warning("the typing dots failed", exc_info=True)


def _answer(t, convo, msg, vocab, sizes, names=frozenset(), *, results, send):
    ctx = t.ctx
    chat_id = ctx.chat_id
    while True:
        reply = _draft(t, convo)
        passed, feedback = send_check.check(reply, t.customer_text, t.amounts, vocab, sizes,
                                            orders=order_names(ctx.chats, chat_id),
                                            links=store_links(ctx.chats, chat_id), names=names)
        if passed:
            send(msg.customer_id, reply)
            n = ctx.chats.add_step(chat_id, "assistant", content=reply)
            ctx.chats.reset_failed_checks(chat_id)
            ctx.chats.reset_model_errors(chat_id)
            results.record(chat_id, "replied", step=n, stage=ctx.stage.name, lessons=t.lesson_ids,
                           detail={"tool_steps": t.tool_steps})
            return TurnResult(chat_id, "replied", reply)
        failed = ctx.chats.add_failed_check(chat_id, feedback)
        results.record(chat_id, "check_failed", stage=ctx.stage.name, lessons=t.lesson_ids,
                       detail={"reply": reply, "feedback": feedback})
        if failed >= MAX_FAILED_CHECKS:
            return _no_safe_reply(t, msg, results, send, {"by": "send_check", "in_a_row": failed})
        convo.append({"role": "assistant", "content": reply})
        convo.append({"role": "user", "content": RETRY.format(feedback=feedback)})


def _no_safe_reply(t, msg, results, send, detail):
    """No safe reply can be sent: nothing goes to the customer, unless this turn created an order,
    then ORDER_PLACED goes, saved as a fixed line (DECISIONS item 53, Mohamed's call 2026-11-01:
    no line of its own). The chat keeps its stage and stays with the agent; both counts start
    again, so the next message gets the agent's own reply. The row no_safe_reply counts as harm
    and marks the chat lost for Reflection and the Arena."""
    ctx = t.ctx
    drop_draft(ctx.chats, ctx.chat_id)
    made = order_made(ctx.chats, ctx.chat_id)
    line = step = None
    if made:
        line, step = _order_line(ctx.chats, ctx.chat_id, msg, t.customer_text, made, send)
    ctx.chats.reset_failed_checks(ctx.chat_id)
    ctx.chats.reset_model_errors(ctx.chat_id)
    results.record(ctx.chat_id, "no_safe_reply", step=step, stage=ctx.stage.name, lessons=t.lesson_ids,
                   detail={**detail, **({"order": made["order"]} if made else {})})
    return TurnResult(ctx.chat_id, "no_safe_reply", line)


def model_down_line(customer_text):
    return MODEL_DOWN[send_check.detect_script(customer_text) or "arabic"]


def _model_error(t, msg, error, *, results, send, by="model_error"):
    """The model did not answer: one fixed line, and the chat keeps its stage. The
    MAX_MODEL_ERRORS-th error in a row in this chat is no safe reply (_no_safe_reply).

    by: model_error, or turn_failed for a turn that crashed in code. Both share one count.
    """
    ctx = t.ctx
    drop_draft(ctx.chats, ctx.chat_id)
    n = ctx.chats.add_model_error(ctx.chat_id, str(error))
    made = order_made(ctx.chats, ctx.chat_id)
    if n >= MAX_MODEL_ERRORS:
        log.warning("%s, %d in a row, no safe reply: %s", by, n, error)
        return _no_safe_reply(t, msg, results, send, {"by": by, "in_a_row": n})
    if made:
        log.warning("%s, %d in a row, after order %s was created: %s", by, n, made["order"], error)
        line, step = _order_line(ctx.chats, ctx.chat_id, msg, t.customer_text, made, send)
    else:
        log.warning("%s, %d in a row, the customer was asked to write again: %s", by, n, error)
        line = model_down_line(t.customer_text)
        send(msg.customer_id, line)
        step = ctx.chats.add_step(ctx.chat_id, "assistant", content=line, name=FIXED)
    detail = {"in_a_row": n, **({"order": made["order"]} if made else {})}
    results.record(ctx.chat_id, by, step=step, stage=ctx.stage.name, lessons=t.lesson_ids, detail=detail)
    return TurnResult(ctx.chat_id, by, line)


def failed_turn(msg, *, chats, model, results, send, limits=None, kind="text"):
    """A turn crashed in code. It counts like a model error: the customer gets the MODEL_DOWN
    line, and the MAX_MODEL_ERRORS-th failure in a row (crashes and model errors together)
    is no safe reply.

    The customer's message is saved first if the crash came before that (kind: text, image
    or audio, as the message came in). Nothing is sent when a reply already went out after
    the customer's last message, or while the agent is paused. Returns a TurnResult, or None
    when nothing was sent.
    """
    if msg.message_id and not chats.saved(msg.message_id):
        chat_id, _ = chats.receive(msg.channel, msg.customer_id, content=msg.text or None,
                                   media=[{"kind": kind}] if kind in ("image", "audio") else None,
                                   message_id=msg.message_id)
    else:
        chat_id = chats.open(msg.channel, msg.customer_id)
    if switch.is_paused(PLUG.agent, db=chats.db):
        return None
    stage = stages.get(chats.stage(chat_id))
    steps = chats.steps(chat_id)
    last_user = max((s["n"] for s in steps if s["role"] == "user"), default=0)
    if any(s["n"] > last_user and s["role"] == "assistant" and not s["tool_calls"] and (s["content"] or "").strip()
           for s in steps):
        return None
    if limits is not None:
        model = limits.meter(model, limits_mod.key(msg.channel, msg.customer_id))
    ctx = tools.Context(chat_id=chat_id, stage=stage, chats=chats, model=model, message=msg,
                        send=send, stages=stages.STAGES)
    t = _Turn(ctx=ctx, customer_text=msg.text or last_customer_text(chats, chat_id))
    return _model_error(t, msg, "the turn failed in code", results=results, send=send, by="turn_failed")


def _limited(chat_id, stage, msg, customer_text, which, *, chats, results, send, limits):
    """Over a model call limit: one fixed line, once per window, and no model call. When this
    turn created an order, ORDER_PLACED goes instead, and the limit line is still due next time."""
    drop_draft(chats, chat_id)
    made = order_made(chats, chat_id)
    if made:
        line, _ = _order_line(chats, chat_id, msg, customer_text, made, send)
        results.record(chat_id, "limited", stage=stage.name,
                       detail={"limit": which, "told": False, "order": made["order"]})
        return TurnResult(chat_id, "limited", line)
    line = None
    if limits is None or limits.notice_due(limits_mod.key(msg.channel, msg.customer_id), which):
        line = LIMIT_LINE[send_check.detect_script(customer_text) or "arabic"]
        send(msg.customer_id, line)
        chats.add_step(chat_id, "assistant", content=line, name=FIXED)
    results.record(chat_id, "limited", stage=stage.name, detail={"limit": which, "told": line is not None})
    return TurnResult(chat_id, "limited", line)


def order_made(chats, chat_id):
    """The draft_order result that created an order in this turn (after the customer's last
    message, draft_order.created), or None. Never raises: on an error the usual line goes out."""
    try:
        return draft_order.created(chats.steps(chat_id))
    except Exception:
        log.exception("could not tell if this turn created an order")
    return None


def order_names(chats, chat_id):
    """The order names a tool gave in this turn (after the customer's last message): the order
    draft_order created and each order find_order found. The send check reads them as order
    numbers, so "اوردرك اتسجل برقم #1001، والإجمالي 1958 جنيه." passes (review t261028j round 3,
    note 1). Never raises: on an error no name is given and the check reads every #number."""
    names = set()
    try:
        steps = chats.steps(chat_id)
        last_user = max((s["n"] for s in steps if s["role"] == "user"), default=0)
        for s in steps:
            if s["n"] <= last_user or s["role"] != "tool" or s["name"] not in (draft_order.NAME, find_order.NAME):
                continue
            out = json.loads(s["content"] or "null")
            if not (isinstance(out, dict) and out.get("ok") is True):
                continue
            if s["name"] == draft_order.NAME:
                found = [out] if out.get("step") == "created" else []
            else:
                found = out.get("orders") if isinstance(out.get("orders"), list) else []
            names.update(o["order"] for o in found
                         if isinstance(o, dict) and isinstance(o.get("order"), str) and o["order"].strip())
    except Exception:
        log.exception("could not read this turn's order names")
        return set()
    return names


def store_links(chats, chat_id):
    """The image links the store tool gave in this chat, any turn: the image of each item in a
    store result that ran (ok true). The send check lets a reply carry only these links
    (kit/send_check.py rule 6). Only a store result counts, never the customer's text or another
    tool's. Never raises: on an error no link is given, so every link is refused."""
    links = set()
    try:
        for s in chats.steps(chat_id):
            if s["role"] != "tool" or s["name"] != store.NAME:
                continue
            out = json.loads(s["content"] or "null")
            if not (isinstance(out, dict) and out.get("ok") is True and isinstance(out.get("items"), list)):
                continue
            links.update(i["image"] for i in out["items"]
                         if isinstance(i, dict) and store._image(i.get("image")))
    except Exception:
        log.exception("could not read the store links in this chat")
        return set()
    return links


def _placed(customer_text, made):
    """ORDER_PLACED in the customer's script, with the order's number and total."""
    order = str(made["order"])
    total = made["total"]
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        total = f"{total:,}"
    return ORDER_PLACED[send_check.detect_script(customer_text) or "arabic"].format(
        order=order if order.startswith("#") else "#" + order, total=total)


def _order_line(chats, chat_id, msg, customer_text, made, send):
    """Send ORDER_PLACED in the customer's script and save it as a fixed line, once a turn: when
    it already went out in this turn, nothing is sent again. Returns (line, step)."""
    line = _placed(customer_text, made)
    told = _told(chats, chat_id, line)
    if told is not None:
        return line, told
    send(msg.customer_id, line)
    return line, chats.add_step(chat_id, "assistant", content=line, name=FIXED)


def _told(chats, chat_id, line):
    """The step of the fixed line `line` sent after the customer's last message, or None. Never raises."""
    try:
        steps = chats.steps(chat_id)
        last_user = max((s["n"] for s in steps if s["role"] == "user"), default=0)
        return next((s["n"] for s in steps if s["n"] > last_user and s["role"] == "assistant"
                     and s["name"] == FIXED and s["content"] == line), None)
    except Exception:
        log.exception("could not tell if the order line already went out")
        return None


def _arguments(raw):
    """Tool arguments as a dict, or None. Some servers send a JSON string, others an object."""
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _draft(t, convo):
    """Run model steps until it answers in words. Returns the draft reply."""
    ctx = t.ctx
    for step in range(MAX_TOOL_STEPS + 1):
        last = step == MAX_TOOL_STEPS
        picked = _lessons(t)
        defs = [] if last else tools.definitions(ctx.stage)
        out = ctx.model.chat([system_prompt(ctx.stage, picked, t.note)] + convo, tools=defs or None)
        calls = out.get("tool_calls") or []
        calls = [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
        if not calls or last:
            return (out.get("content") or "").strip()
        t.tool_steps += 1
        call_msg = {"role": "assistant", "content": out.get("content"), "tool_calls": calls}
        convo.append(call_msg)
        ctx.chats.add_step(ctx.chat_id, "assistant", content=out.get("content"), tool_calls=calls)
        for i, call in enumerate(calls):
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = fn.get("name") if isinstance(fn.get("name"), str) else ""
            if i >= MAX_CALLS_PER_STEP:
                result = dict(TOO_MANY_CALLS)
            else:
                result = tools.run(name, _arguments(fn.get("arguments")), ctx)
            body = json.dumps(result, ensure_ascii=False)
            call_id = call.get("id") if isinstance(call.get("id"), str) else ""
            convo.append({"role": "tool", "tool_call_id": call_id, "content": body})
            ctx.chats.add_step(ctx.chat_id, "tool", content=body, tool_call_id=call_id, name=name)
            if name in tools.AMOUNT_TOOLS:
                t.amounts |= send_check.amounts_in(result)
            if name == "voice_note" and result.get("ok"):
                t.customer_text = result.get("text", "")
            _apply_stage(t, result)
    return ""


def _lessons(t):
    """Lessons for the stage the chat is in now; it can change mid-turn. The engine picks them for
    this chat's reply and adds their ids to the turn's set, which every result row of the turn keeps."""
    if t.lessons is None:
        return []
    return t.lessons.hand(t.ctx.chat_id, "reply", t.ctx.stage.name, t.customer_text, t.lesson_ids)


def _apply_stage(t, result):
    nxt = result.get("next_stage") if isinstance(result, dict) else None
    if nxt in stages.STAGES:
        t.ctx.chats.set_stage(t.ctx.chat_id, nxt)
        t.ctx.stage = stages.STAGES[nxt]


def drop_draft(chats, chat_id):
    """Drop the chat's pending order summary. After a fixed line (model down, limit) or no safe
    reply the customer may never have seen the summary, so a confirm needs a new one. Never raises."""
    try:
        orders.Book(chats.db).drop_draft(chat_id)
    except Exception:
        log.exception("could not drop the pending order summary")
