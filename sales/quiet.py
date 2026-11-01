"""A chat ends after quiet (DECISIONS item 54). No model call: a tick the channel runs in its sweep
thread (channels/whatsapp.py), with a clock tests can set.

- Quiet is counted from the last customer or agent step in the chat (and from the quiet notice,
  whichever came last).
- After NOTICE_AFTER quiet seconds the customer gets NOTICE once per chat, in the script of
  their last text (Egyptian Arabic when none can be told, like the other fixed lines). It goes
  through the channel's normal send (plain text, no reply-to) and is saved as a fixed line. A
  customer over a model call limit gets no notice (the limit line already told them to wait);
  a notice that could not be sent is not tried again. Either way the chat closes on time.
- After CLOSE_AFTER more quiet seconds the chat closes. A customer message in that window keeps
  it open; once it goes quiet again it closes after NOTICE_AFTER + CLOSE_AFTER quiet seconds,
  with no second notice.
- A chat that closes with no order gets the result chat_closed at once: the plug's bad deciding
  result, so the fast reflection sweep (reflection/fast.py) writes its note in the same sweep
  and that night's Reflection reads the chat as lost. A chat with an order closes with no row.
- The customer's next message starts a new chat on the same customer_id (kit/chats.py).
"""
import logging

from kit import limits as limits_mod
from kit import send_check
from kit.chats import FIXED
from reflection import PLUG
from sales.loop import last_customer_text

log = logging.getLogger("sales.quiet")

NOTICE_AFTER = 30 * 60  # quiet seconds before the notice
CLOSE_AFTER = 30 * 60   # quiet seconds after the notice before the chat closes
CLOSED = "chat_closed"
NOTICE = {
    "arabic": "المحادثة دي هتتقفل كمان 30 دقيقة. ابعتلي في أي وقت ونكمل.",
    "franco": "el mo7adsa di hatet2efel kman 30 di2i2a. eb3atli f ay wa2t w nkamel.",
    "english": "This chat closes in 30 minutes. Write anytime to keep going.",
}


def notice_line(customer_text):
    return NOTICE[send_check.detect_script(customer_text or "") or "arabic"]


def tick(*, chats, results, send, channel, now=None, limits=None):
    """One pass over the open chats on a channel. send(to, text) is the channel's send.
    Returns [(chat_id, "notice" or "closed")] for what it did."""
    now = chats.clock() if now is None else now
    done = []
    for ch in chats.open_chats(channel):
        if ch["last"] is None:
            continue
        quiet = now - max(ch["last"], ch["notice_at"] or 0)
        if ch["notice_at"] is None:
            if quiet >= NOTICE_AFTER and _notice(ch, chats, send, channel, limits, now):
                done.append((ch["id"], "notice"))
            continue
        came_back = ch["last_customer"] is not None and ch["last_customer"] > ch["notice_at"]
        if quiet >= (NOTICE_AFTER + CLOSE_AFTER if came_back else CLOSE_AFTER):
            if _close(ch, chats, results, now):
                done.append((ch["id"], "closed"))
    return done


def _notice(ch, chats, send, channel, limits, now):
    """Send the notice once. The chat counts it as tried whatever happens, so it is never sent
    twice; False only when another tick marked it first."""
    if not chats.mark_notice(ch["id"], now):
        return False
    if limits is not None and limits.over(limits_mod.key(channel, ch["customer_id"])):
        return True
    line = notice_line(last_customer_text(chats, ch["id"]))
    try:
        send(ch["customer_id"], line)
    except Exception:
        log.exception("could not send the quiet notice; the chat still closes on time")
        return True
    chats.add_step(ch["id"], "assistant", content=line, name=FIXED)
    return True


def _close(ch, chats, results, now):
    if not chats.close(ch["id"], now):
        return False
    if not results.query(case=ch["id"], result=PLUG.decides.good):
        results.result(ch["id"], CLOSED, stage=ch["stage"], at=now,
                       detail={"quiet_minutes": (NOTICE_AFTER + CLOSE_AFTER) // 60})
    return True
