"""A chat ends after quiet (DECISIONS item 54). No model call: a tick the channel runs in its sweep
thread (channels/whatsapp.py), with a clock tests can set.

- Quiet is counted from the last customer or agent step in the chat (and from the quiet notice,
  and from a resume of the agent, whichever came last).
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
- The customer's next message starts a new chat on the same customer_id (kit/chats.py): the same
  case, its next talk, so each close and its result belong to that one talk (DECISIONS item 65).
- A paused agent (kit/switch.py) sends no notice and closes no chat.
- A chat whose notice was already due when this process started (it went quiet before a restart or
  an upgrade) closes at the first tick, silently, with its result as above: no customer gets a
  message about a chat that went quiet long ago. A notice that falls due while the process runs
  always goes out, however late the tick comes (a slow fast reflection sweep shares its thread),
  and the chat closes CLOSE_AFTER after it (DECISIONS item 54, 2026-11-01).
- The tick works from one view of the open chats, and a notice send can take seconds. So the
  notice and the close each hold to that view inside their own write (kit/chats.py mark_notice,
  close): a chat whose customer wrote meanwhile, or has a message accepted from the webhook and
  not saved yet, is left alone. The close, its check for an order and its result are one step
  under the database lock, so no turn saves a step or an order in between.
"""
import logging

from kit import limits as limits_mod
from kit import send_check, switch
from kit.chats import FIXED
from reflection import PLUG
from sales.loop import last_customer_text

log = logging.getLogger("sales.quiet")

NOTICE_AFTER = 30 * 60  # quiet seconds before the notice
CLOSE_AFTER = 30 * 60   # quiet seconds after the notice before the chat closes
START_GRACE = 5 * 60    # a notice due this close before the start still goes out after a quick restart
CLOSED = "chat_closed"
NOTICE = {
    "arabic": "المحادثة دي هتتقفل كمان 30 دقيقة. ابعتلي في أي وقت ونكمل.",
    "franco": "el mo7adsa di hatet2efel kman 30 di2i2a. eb3atli f ay wa2t w nkamel.",
    "english": "This chat closes in 30 minutes. Write anytime to keep going.",
}


def notice_line(customer_text):
    return NOTICE[send_check.detect_script(customer_text or "") or "arabic"]


def tick(*, chats, results, send, channel, now=None, limits=None, agent=PLUG.agent, started=None):
    """One pass over the open chats on a channel. send(to, text) is the channel's send. started is
    when this process started (channels/whatsapp.py App): a notice due more than START_GRACE before
    then is not sent and the chat closes silently; None means every due notice goes out.
    Returns [(chat_id, "notice" or "closed")] for what it did."""
    now = chats.clock() if now is None else now
    if switch.is_paused(agent, db=chats.db):
        return []
    resumed = switch.resumed_at(agent, db=chats.db) or 0
    done = []
    for ch in chats.open_chats(channel):
        if ch["last"] is None or ch.get("waiting"):  # a message from the customer is on its way in
            continue
        since = max(ch["last"], ch["notice_at"] or 0, resumed)
        quiet = now - since
        if ch["notice_at"] is None:
            if quiet < NOTICE_AFTER:
                continue
            if started is not None and since + NOTICE_AFTER < started - START_GRACE:  # due well before the start
                if _close(ch, chats, results, now, quiet):
                    done.append((ch["id"], "closed"))
            elif _notice(ch, chats, send, channel, limits, now):
                done.append((ch["id"], "notice"))
            continue
        came_back = ch["last_customer"] is not None and ch["last_customer"] > ch["notice_at"]
        if quiet >= (NOTICE_AFTER + CLOSE_AFTER if came_back else CLOSE_AFTER):
            if _close(ch, chats, results, now):
                done.append((ch["id"], "closed"))
    return done


def _notice(ch, chats, send, channel, limits, now):
    """Send the notice once. The chat counts it as tried whatever happens, so it is never sent
    twice; False when another tick marked it first or the chat moved since the tick's view."""
    if not chats.mark_notice(ch["id"], now, last_n=ch.get("last_n")):
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


def _close(ch, chats, results, now, quiet=NOTICE_AFTER + CLOSE_AFTER):
    """Close the chat if it is as the tick saw it, and give it chat_closed unless it holds an order,
    all under one hold of the database lock (kit/db.py is one connection behind one lock). quiet is
    the quiet seconds recorded: the real ones on a silent close, the notice and the close after it otherwise."""
    with chats.db.tx():
        if not chats.close(ch["id"], now, last_n=ch.get("last_n")):
            return False
        if not any(r["outcome"] == PLUG.decides.good for r in results.for_chat(ch["id"])):  # this talk's order
            results.record(ch["id"], CLOSED, stage=ch["stage"], at=now, detail={"quiet_minutes": int(quiet // 60)})
    return True
