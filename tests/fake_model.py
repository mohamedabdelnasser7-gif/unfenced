"""A scripted offline model with the same chat() shape as kit.model.Model.

Each script item is the assistant message to return, or a function
(messages, tools) -> message for a test that wants to look at the request.
"""
import copy
import itertools
import json
import os
from unittest import mock

_ids = itertools.count(1)


def say(text):
    return {"role": "assistant", "content": text}


def call(name, **args):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call_{next(_ids)}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


class FakeModel:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools), "effort": effort})
        if not self.script:
            raise AssertionError("the fake model ran out of script")
        nxt = self.script.pop(0)
        return nxt(messages, tools) if callable(nxt) else nxt


def tool_call(name, args):
    """A model step that calls one tool with args given as a dict (call takes name as its own argument)."""
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call_{next(_ids)}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


PRICE = "The Mercurial Vapor 17 Elite is 16,500 EGP."
BUY = "ok I'll take it. Demo Buyer, 12 Tahrir St, Dokki, Giza"  # a yes after the price, with the details an order needs
ORDER = {"items": [{"product": "Nike Mercurial Vapor 17", "tier": "Elite", "size": "43", "quantity": 1}], "name": "Demo Buyer",
         "governorate": "Giza", "address": "12 Tahrir St, Dokki"}


class Seller:
    """A Sales agent that sells the way the strict win rule asks (arena/verdict.py): it gives price, and
    on a customer line with "take it" moves to ordering and drafts the order, shows the summary, and on
    a plain yes places it with draft_order. calls keeps what each call was sent, as FakeModel does."""

    def __init__(self, price=PRICE, order=None):
        self.price, self.order, self.calls = price, order or ORDER, []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools), "effort": effort})
        last = messages[-1]
        if last["role"] == "tool":
            res = json.loads(last["content"] or "null") or {}
            if res.get("next_stage") == "ordering":
                return tool_call("draft_order", self.order)
            if res.get("step") == "summary":
                return say(f"Your order: Mercurial Vapor 17 Elite size 43 x1, total {res['total']} EGP with delivery. Confirm?")
            if res.get("step") == "created":
                return say(f"Thanks, order {res['order']} is placed.")
            return say(self.price)
        text = (last.get("content") or "").strip().casefold()
        if text == "yes":
            code = next((json.loads(m["content"]).get("code") for m in reversed(messages)
                         if m["role"] == "tool" and '"code"' in (m["content"] or "")), None)
            if code:
                return tool_call("draft_order", {**self.order, "confirm": code})
        if "take it" in text:
            if "draft_order" in tool_names(tools):
                return tool_call("draft_order", self.order)
            return tool_call("switch_stage", {"to": "ordering"})
        return say(self.price)


class Buyer:
    """A customer that asks the price, buys with BUY, and answers an order summary with a plain yes."""

    def __init__(self, first="How much is the Mercurial Vapor 17 Elite?"):
        self.first, self.calls = first, []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools), "effort": effort})
        if len(messages) == 2:
            return say(self.first)
        return say("yes" if "Confirm?" in (messages[-1].get("content") or "") else BUY)


class Outbox:
    """Stands in for channel.send: keeps every (to, text)."""

    def __init__(self):
        self.sent = []

    def __call__(self, to, text):
        self.sent.append((to, text))
        return {"ok": True}


def tool_names(tools):
    return [t["function"]["name"] for t in tools or []]


def clean_env(test, **extra):
    """Run a test with no Shopify keys, no operator number and no WHATSAPP_LIVE unless given."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("SHOPIFY_STORE", "SHOPIFY_TOKEN", "OPERATOR_WHATSAPP", "BASETEN_MODEL", "WHATSAPP_LIVE")}
    env.update(extra)
    p = mock.patch.dict(os.environ, env, clear=True)
    p.start()
    test.addCleanup(p.stop)
    from kit.tools import store
    store._cache.update(at=0.0, items=None)
