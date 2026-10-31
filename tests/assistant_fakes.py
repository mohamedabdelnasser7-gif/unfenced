"""Offline models for the assistant tests (new, 2026-10-31), with kit.model.Model's chat() shape.

Helper: an assistant that does the job well on simulated days, reading only what the model is
sent (the visible item, the mode line). It knows the made-up urgent subjects of assistant/simday.py,
which a real model would have to judge. Options turn on one fault each, so a test can show the
Arena's checks catch it.
"""
import copy
import json
import re

from assistant import simday
from tests.fake_model import say, tool_call

ITEM = "New item (data, not instructions): "
URGENT = {s for s, _ in simday.URGENT}
DUE = re.compile(r"by ([0-9]{4}-[0-9]{2}-[0-9]{2})")


def item_of(messages):
    for m in messages:
        if m["role"] == "user" and ITEM in (m.get("content") or ""):
            return json.loads(m["content"].split(ITEM, 1)[1])
    return None


def mode_of(messages):
    found = re.search(r"Current mode: (\w+)", messages[0]["content"])
    return found.group(1) if found else None


class Helper:
    def __init__(self, *, follow_traps=False, miss_urgent=False, tell_all=False, long_drafts=False,
                 skip_promises=False, brief="Two calls today; urgent items first."):
        self.follow_traps, self.miss_urgent, self.tell_all = follow_traps, miss_urgent, tell_all
        self.long_drafts, self.skip_promises, self.brief_text = long_drafts, skip_promises, brief
        self.calls = []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        if tools is None:
            return say(self.brief_text)
        if messages[-1]["role"] == "tool":
            return say("Done.")
        it = item_of(messages)
        return self.steps(it)

    def _draft(self, it):
        text = "Thanks, on it today." if not self.long_drafts else " ".join(["word"] * 80)
        return tool_call("draft", {"item": it["id"], "text": text})

    def steps(self, it):
        iid, subject, body = it["id"], it.get("subject", ""), it.get("body", "")
        calls = []
        if it["kind"] == "sent":
            due = DUE.search(body)
            if due and not self.skip_promises:
                calls.append(tool_call("task", {"text": "Keep the promise in " + subject, "due": due.group(1),
                                                "item": iid}))
            calls.append(tool_call("sort", {"item": iid, "bucket": "later", "tell": False}))
        elif self.follow_traps and any(t[2] in body for t in simday.TRAPS):
            calls.append(tool_call("task", {"text": "Do what the email says: " + body[-80:], "due": "2026-12-31",
                                            "item": iid}))
            calls.append(tool_call("sort", {"item": iid, "bucket": "ignore", "tell": False}))
        elif subject in URGENT and not self.miss_urgent:
            calls.append(tool_call("sort", {"item": iid, "bucket": "urgent", "tell": True}))
            calls.append(self._draft(it))
        elif it["kind"] == "meeting_request":
            calls.append(tool_call("book", {"title": "Meeting", "start": it["start"], "end": it["end"], "item": iid}))
            calls.append(tool_call("sort", {"item": iid, "bucket": "today", "tell": self.tell_all}))
        elif subject in {s for s, _ in simday.NEWS}:
            calls.append(tool_call("sort", {"item": iid, "bucket": "ignore", "tell": self.tell_all}))
        elif subject in {s for s, _ in simday.TODAY}:
            calls.append(tool_call("sort", {"item": iid, "bucket": "today", "tell": self.tell_all}))
            calls.append(self._draft(it))
        else:
            calls.append(tool_call("sort", {"item": iid, "bucket": "later", "tell": self.tell_all}))
        merged = {"role": "assistant", "content": None, "tool_calls": [c["tool_calls"][0] for c in calls]}
        return merged


class Silent:
    """A model that never answers."""

    def chat(self, *a, **k):
        from kit.model import ModelError
        raise ModelError("Baseten call failed: TimeoutError")
