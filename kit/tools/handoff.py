"""handoff: a team member takes over the chat.

Sends a note to OPERATOR_WHATSAPP, marks the chat with_person (the agent then waits),
and tells the customer in their own language and script that a team member is taking
over. When no part of the note reaches the team (WhatsApp refused it, for example with
131047 after a quiet day), the chat stays with the agent and the customer is told a team
member will reply (TEAM_WILL_REPLY), so no chat waits on a person nobody told (red team
t261028j F3). The result then ends the turn.

The note: a short Egyptian Arabic summary the model writes, labelled as the agent's
reading, then the customer's messages since the last reply they got, word for word and
in order. A voice note shows as its transcript, a photo as [صورة]. When this turn created
an order, the note names it, with its total (review t261028j round 2, finding 2). Only the last
MAX_NOTE_MESSAGES show, with one line counting the earlier ones, and older ones drop out
until the note fits in MAX_NOTE_PARTS parts, so a flood of messages cannot become a flood
of sends to the team phone (red team t261028j F2). A note longer than MAX_PART is sent in
parts. Each part's WhatsApp message id is saved with the chat
(Chats.save_note), so the team member's reply to any part reaches this customer
(channels/whatsapp.py).
"""
import json
import logging

from kit import env
from kit.model import EFFORT_REPLY
from kit.send_check import DASHES, detect_script, style_problems
from kit.tools import draft_order, voice_note

log = logging.getLogger("kit.tools.handoff")

NAME = "handoff"
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Hand the chat to a team member. Use it when the customer is angry, asks for a person, "
        "wants to cancel, or when you are unsure. The customer is told a team member is taking over."),
    "parameters": {
        "type": "object",
        "properties": {"reason": {"type": "string", "description": "One short line on why, in English."}},
        "required": ["reason"],
        "additionalProperties": False,
    },
}}

TAKING_OVER = {
    "arabic": "حد من الفريق هيكمل معاك دلوقتي.",
    "franco": "7ad mn el team hykamel m3ak delwa2ty.",
    "english": "A team member is taking over this chat now.",
}

# The customer's line when the note reached no one on the team. Pending Mohamed's yes (28 Oct).
TEAM_WILL_REPLY = {
    "arabic": "حد من الفريق هيرد عليك هنا في أقرب وقت.",
    "franco": "7ad mn el team hayrod 3aleek hena f a2rab wa2t.",
    "english": "A team member will reply to you here soon.",
}
NOT_REACHED = ("No one on the team could be reached, so the chat stays with you. The customer was told a team "
               "member will reply. Keep helping with what you can.")

SUMMARY_PROMPT = (
    "You write for the store team. Summarise this customer chat in Egyptian Arabic, in Arabic letters, "
    "in three short lines at most: what the customer wants, what was already said, and why a person is "
    "needed. No dashes, no greetings.")

# The note to the operator says plainly that the summary is the model's reading of customer messages.
SUMMARY_LABEL = "ملخص لرسايل العميل، كتبه الإيجنت من الشات:"
NO_SUMMARY = "(مفيش ملخص)"
NOTE_HEAD = "محادثة محتاجة حد من الفريق"
WAITING_LABEL = "رسايل العميل اللي مستنية رد، زي ما بعتها بالظبط:"
HOW_TO_REPLY = "اعمل ريبلاي على الرسالة دي وردك هيوصل للعميل زي ما كتبته. ريبلاي بكلمة رجّع بيرجّع الشات للإيجنت."
PHOTO = "[صورة]"
VOICE = "[فويس، تفريغ الإيجنت]"
VOICE_NOT_HEARD = "[فويس، مقدرناش نسمعه]"
NOT_OPENED = "[رسالة مقدرناش نفتحها]"
ORDER_MADE = "العميل أكد اوردر برقم {order}، والإجمالي {total} جنيه."
NEW_MESSAGE_HEAD = "رسالة جديدة من العميل وهو مع الفريق"
EARLIER = "رسايل أقدم مش ظاهرة هنا: {n}"
MAX_NOTE_MESSAGES = 20
MAX_NOTE_PARTS = 3

# WhatsApp takes at most 4096 characters in a text body. Parts stay under MAX_PART,
# counted in UTF-16 units (an emoji is two), which is never less than the character count.
MAX_PART = 4000
PART_ROOM = 12  # room for the "(1/2)" line in front of each part


def check(args, ctx):
    reason = args.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return False, "Give a short reason for the handoff."
    if len(reason) > 300:
        return False, "Keep the reason to one short line."
    return True, ""


def customer_script(ctx):
    """The script of the customer's latest words in this chat, Egyptian Arabic if none."""
    if ctx.message is not None and detect_script(ctx.message.text):
        return detect_script(ctx.message.text)
    for s in reversed(ctx.chats.steps(ctx.chat_id)):
        if s["role"] == "user" and detect_script(s["content"] or ""):
            return detect_script(s["content"])
    return "arabic"


def summary(ctx, reason):
    lines = []
    for m in ctx.chats.messages(ctx.chat_id, last=20):
        if m["role"] in ("user", "assistant") and m.get("content"):
            who = "Customer" if m["role"] == "user" else "Agent"
            lines.append(f"{who}: {m['content']}")
    chat = "\n".join(lines) or "(no text)"
    try:
        out = ctx.model.chat([
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": f"Reason for handoff: {reason}\n\nChat:\n{chat}"},
        ], effort=EFFORT_REPLY)
        text = DASHES.sub(",", (out.get("content") or "").strip())
    except Exception:
        log.exception("summary failed")
        text = ""
    if text and style_problems(text):
        log.warning("summary failed the style check; sending the reason only")
        text = ""
    if text:
        return text
    reason_line = f"السبب: {DASHES.sub(',', reason)}"
    return NO_SUMMARY if style_problems(reason_line) else reason_line


def _transcript(steps):
    """The voice_note text in these steps (one message's tool results), or ""."""
    for s in steps:
        if s["role"] == "tool" and s["name"] == voice_note.NAME:
            try:
                out = json.loads(s["content"] or "")
            except ValueError:
                continue
            if isinstance(out, dict) and out.get("ok") and isinstance(out.get("text"), str) and out["text"].strip():
                return out["text"].strip()
    return ""


def _hear_now(ctx):
    """The transcript of this turn's voice note: heard already this turn, or heard now. "" if it cannot be."""
    heard = ctx.cache.get(voice_note.NAME)
    if heard is None:
        try:
            if voice_note.check({}, ctx)[0]:
                heard = voice_note.run({}, ctx)
        except Exception:
            log.exception("the voice note could not be heard for the note")
    if isinstance(heard, dict) and heard.get("ok") and isinstance(heard.get("text"), str):
        return heard["text"].strip()
    return ""


def _is_reply(step):
    """A reply the customer got: an assistant step with words and no tool call (the agent's or a person's)."""
    return step["role"] == "assistant" and bool((step["content"] or "").strip()) and not step["tool_calls"]


def waiting(ctx):
    """The customer's messages since the last reply they got, oldest first, as the note shows them.

    The last one is this turn's message. Lines sent after it in this turn (a photo that
    could not be opened) do not count as a reply to it. Each message is its text word for
    word; a photo adds PHOTO in front, a voice note shows as its transcript after VOICE.
    For this turn's message, photos that could not be opened and a voice note that could
    not be fetched still show.
    """
    steps = ctx.chats.steps(ctx.chat_id)
    users = [i for i, s in enumerate(steps) if s["role"] == "user"]
    if not users:
        return []
    start = 0
    for i in range(users[-1] - 1, -1, -1):
        if _is_reply(steps[i]):
            start = i + 1
            break
    picked = [i for i in users if i >= start]
    out = []
    for k, i in enumerate(picked):
        s = steps[i]
        now = k == len(picked) - 1 and ctx.message is not None
        kinds = [m.get("kind") for m in (s["media"] or [])]
        marks = [PHOTO] * kinds.count("image")
        if now:  # this turn's photos that could not be opened, unless the step already has their marks
            unopened = sum(1 for m in s["media"] or [] if m.get("kind") == "image" and m.get("opened") is False)
            marks += [PHOTO] * max(0, int(getattr(ctx.message, "rejected_images", 0) or 0) - unopened)
        text = s["content"] or ""
        if "audio" in kinds or (now and getattr(ctx.message, "audio_failed", False)):
            end = picked[k + 1] if k + 1 < len(picked) else len(steps)
            heard = _transcript(steps[i + 1:end])
            if not heard and now:
                heard = _hear_now(ctx)
            marks.append(f"{VOICE} {heard}" if heard else VOICE_NOT_HEARD)
        line = " ".join(marks + ([text] if text else []))
        out.append(line or NOT_OPENED)
    return out


def note_text(ctx, customer, reason):
    """The note for the team member: the labelled summary, the waiting messages word for word, how to reply."""
    msgs = waiting(ctx)
    made = draft_order.created(ctx.chats.steps(ctx.chat_id))
    order = [ORDER_MADE.format(order=made["order"], total=made["total"])] if made else []
    head = [NOTE_HEAD, f"العميل: {customer}"] + order + [SUMMARY_LABEL, summary(ctx, reason)]
    shown = msgs[-MAX_NOTE_MESSAGES:]
    while True:
        hidden = len(msgs) - len(shown)
        parts = list(head)
        if msgs:
            parts += ["", WAITING_LABEL] + ([EARLIER.format(n=hidden)] if hidden else []) + ["\n\n".join(shown)]
        note = "\n".join(parts + ["", HOW_TO_REPLY])
        if len(shown) <= 1 or len(split(note)) <= MAX_NOTE_PARTS:
            return note
        shown = shown[1:]


def units(text):
    """Length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def _hard_split(line, limit):
    out, cur, n = [], [], 0
    for ch in line:
        w = units(ch)
        if n + w > limit:
            out.append("".join(cur))
            cur, n = [], 0
        cur.append(ch)
        n += w
    if cur:
        out.append("".join(cur))
    return out


def split(text, limit=MAX_PART):
    """Text in parts under limit UTF-16 units each, cut at line ends where it can.

    More than one part: each starts with a "(1/2)" line. One part comes back as is.
    """
    if units(text) < limit:
        return [text]
    room = limit - PART_ROOM
    parts, cur = [], ""
    for line in text.split("\n"):
        pieces = _hard_split(line, room - 1) if units(line) >= room else [line]
        for piece in pieces:
            joined = f"{cur}\n{piece}" if cur else piece
            if units(joined) < room:
                cur = joined
            else:
                if cur:
                    parts.append(cur)
                cur = piece
    if cur:
        parts.append(cur)
    return [f"({i}/{len(parts)})\n{p}" for i, p in enumerate(parts, 1)]


def sent_id(resp):
    """The message id in a WhatsApp send response: {"messages": [{"id": "wamid..."}]}. "" if none."""
    msgs = resp.get("messages") if isinstance(resp, dict) else None
    first = msgs[0] if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict) else {}
    mid = first.get("id")
    return mid if isinstance(mid, str) else ""


def tell_operator(ctx, operator, note):
    """Send the note in parts, at most MAX_NOTE_PARTS, and save each part's id with the chat.
    Returns the parts sent."""
    sent = 0
    parts = split(note)
    if len(parts) > MAX_NOTE_PARTS:
        log.warning("a note came to %d parts; only the first %d are sent", len(parts), MAX_NOTE_PARTS)
    for part in parts[:MAX_NOTE_PARTS]:
        try:
            resp = ctx.send(operator, part)
        except Exception:
            log.exception("could not message the operator")
            break
        sent += 1
        mid = sent_id(resp)
        if mid:
            ctx.chats.save_note(mid, ctx.chat_id, operator)
        else:
            log.warning("a note part came back with no message id; a reply to it cannot reach the customer")
    return sent


def pass_on(ctx, operator):
    """A customer message that arrives while a person has the chat: sent to the team member
    word for word, with its id saved, so a reply to it reaches the customer as well."""
    msgs = waiting(ctx)
    if not msgs:
        return 0
    note = "\n".join([NEW_MESSAGE_HEAD, f"العميل: {ctx.message.customer_id}", "", msgs[-1], "", HOW_TO_REPLY])
    return tell_operator(ctx, operator, note)


def run(args, ctx):
    reason = args["reason"].strip()
    customer = ctx.message.customer_id if ctx.message is not None else ctx.chats.get(ctx.chat_id)["customer_id"]
    operator = env.get("OPERATOR_WHATSAPP")
    parts = 0
    if operator:
        parts = tell_operator(ctx, operator, note_text(ctx, customer, reason))
    else:
        log.warning("OPERATOR_WHATSAPP is not set; the handoff was not sent to a person")
    if operator and not parts:
        log.error("no part of the handoff note reached the team; the chat stays with the agent")
        line = TEAM_WILL_REPLY[customer_script(ctx)]
        ctx.send(customer, line)
        ctx.sent.append(line)
        return {"ok": False, "customer_told": True, "operator_told": False, "turn_over": True,
                "feedback": NOT_REACHED}
    ctx.chats.set_stage(ctx.chat_id, "with_person")
    line = TAKING_OVER[customer_script(ctx)]
    ctx.send(customer, line)
    ctx.sent.append(line)  # the loop saves it after this tool's result, keeping the step order valid
    return {"ok": True, "next_stage": "with_person", "customer_told": True, "operator_told": parts > 0}
