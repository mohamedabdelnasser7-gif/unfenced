"""Our one model client, over urllib (OpenAI-style chat completions), with two routes.

OPEN, the default for everything: Muse Spark Open on Baseten. Key BASETEN_API_KEY. Model id
BASETEN_MODEL from env, default "meta-models/muse-spark-open-1026", the id that worked in our
27 Oct tests. The Baseten changelog names it "meta-models/muse-spark-open".

WONDER, for the night study's proposer and tagger: Muse Wonder (preview) on the Meta Model API.
Key META_API_KEY. Model id META_STUDY_MODEL from env, default "muse-wonder-1.0". Meta's docs
(read 29 Oct 2026, dev.meta.ai/docs/protocols/chat-completions and /reasoning): POST to
https://api.meta.ai/v1/chat/completions in the OpenAI shape; max_completion_tokens is the field
(max_tokens is a deprecated alias); reasoning_effort "none" and logprobs answer HTTP 400. So this
route sends low, medium or high only, and never logprobs.

SPARK_META, the same Muse Spark family on the Meta Model API (DECISIONS item 33). Key
META_API_KEY. Model id META_MODEL from env, default "muse-spark-1.3" (intel 2026-10-26). It
takes the same body rules as WONDER. Which key runs what, for a route left at OPEN with no key
given in code (keyed_legs):
  only META_API_KEY        every call goes to Muse Spark on the Meta Model API
  only BASETEN_API_KEY     every call goes to Baseten
  both                     Baseten first; a Baseten timeout, network failure, 5xx or 429
                           sends that same call to the Meta Model API, logged by route name
  neither                  the call fails with NO_KEY; the recorded replay needs no key
A key given in code (api_key=) or another endpoint pins that one route, with no fallback.

The call carries the API key, so it goes through kit.net and never follows a redirect: urllib's
default opener follows a 302 on a POST as a GET and keeps the Authorization header.
"""
import http
import http.client
import json
import logging
import typing
import urllib.error
import urllib.request

from kit import env, net

log = logging.getLogger("kit.model")

ENDPOINT = "https://inference.baseten.co/v1/chat/completions"
DEFAULT_MODEL = "meta-models/muse-spark-open-1026"
CHANGELOG_MODEL = "meta-models/muse-spark-open"

META_ENDPOINT = "https://api.meta.ai/v1/chat/completions"
WONDER_MODEL = "muse-wonder-1.0"
SPARK_META_MODEL = "muse-spark-1.3"

NO_KEY = "no model key is set (META_API_KEY or BASETEN_API_KEY)"
REPLAY_COMMAND = "python3 -I recorded/play.py"
NO_KEY_LINE = (f"No model key is set: put META_API_KEY or BASETEN_API_KEY in .env (see .env.example), "
               f"or replay the recorded run with no key: {REPLAY_COMMAND}")
FALLBACK_CODES = frozenset({429})  # with every 5xx: the host is busy or down, so the other host may answer

EFFORT_REPLY = "medium"   # live replies to customers
EFFORT_STUDY = "high"     # the night study


class Route(typing.NamedTuple):
    """Where a call goes and the env names it reads. name is what an error calls the host."""
    name: str
    endpoint: str
    key_env: str
    model_env: str
    default_model: str
    max_field: str = "max_tokens"
    efforts: tuple = ()  # the reasoning efforts the host takes; empty: not checked


OPEN = Route("Baseten", ENDPOINT, "BASETEN_API_KEY", "BASETEN_MODEL", DEFAULT_MODEL)
WONDER = Route("Meta", META_ENDPOINT, "META_API_KEY", "META_STUDY_MODEL", WONDER_MODEL,
               max_field="max_completion_tokens", efforts=("low", "medium", "high"))
SPARK_META = Route("Meta", META_ENDPOINT, "META_API_KEY", "META_MODEL", SPARK_META_MODEL,
                   max_field="max_completion_tokens", efforts=("low", "medium", "high"))


class Leg(typing.NamedTuple):
    """One place a call can go: the route, its key and its model id."""
    route: Route
    key: str
    model_id: str


def keyed_legs():
    """The legs for a Muse Spark call from the keys in env, first try first (see the module note).
    With no key at all: one Baseten leg with no key, whose call fails with NO_KEY."""
    baseten, meta = env.get(OPEN.key_env), env.get(SPARK_META.key_env)
    spark_meta = Leg(SPARK_META, meta, env.get(SPARK_META.model_env, SPARK_META.default_model))
    if baseten:
        first = Leg(OPEN, baseten, env.get(OPEN.model_env, OPEN.default_model))
        return [first, spark_meta] if meta else [first]
    if meta:
        return [spark_meta]
    return [Leg(OPEN, "", env.get(OPEN.model_env, OPEN.default_model))]


def has_key():
    """True when a Muse Spark call has a key to go with (either host)."""
    return bool(env.get(OPEN.key_env) or env.get(SPARK_META.key_env))


class ModelError(Exception):
    """The model call failed. The message never holds the key."""


def _phrase(code):
    try:
        return http.HTTPStatus(code).phrase
    except ValueError:
        return "error"


class Model:
    def __init__(self, api_key=None, model_id=None, endpoint=None, timeout=90, opener=None, route=OPEN):
        keyed = route is OPEN and api_key is None and endpoint is None
        if keyed:  # the default Muse Spark call: the keys in env pick the host (keyed_legs)
            legs = keyed_legs()
            if model_id:
                legs[0] = legs[0]._replace(model_id=model_id)
        else:
            legs = [Leg(route, api_key if api_key is not None else env.get(route.key_env),
                        model_id or env.get(route.model_env, route.default_model))]
        self.route, self._key, self.model_id = legs[0]
        self.endpoint = endpoint or self.route.endpoint
        self.fallback = legs[1] if len(legs) > 1 else None
        self._no_key = NO_KEY if keyed else f"{route.key_env} is not set"
        self.timeout = timeout
        self._open = opener or net.open_once
        self.last_route = self.last_model = None  # who answered the last call, for a recorded trace

    def body(self, messages, tools=None, effort=EFFORT_REPLY, max_tokens=1500, leg=None):
        route, model_id = (leg.route, leg.model_id) if leg is not None else (self.route, self.model_id)
        if route.efforts and effort not in route.efforts:
            raise ModelError(f"{route.name} takes reasoning effort {', '.join(route.efforts)} only")
        body = {
            "model": model_id,
            "messages": messages,
            route.max_field: max_tokens,
            "reasoning_effort": effort,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body

    def chat(self, messages, tools=None, effort=EFFORT_REPLY, max_tokens=1500, whole=False):
        """Send one request. Returns the assistant message dict (content and maybe tool_calls).
        whole: an answer the host cut off at max_tokens is an error, not a shorter answer.
        Reasoning tokens count against max_tokens, so a long think can cut the answer.
        With a fallback leg, a first host that times out, cannot be reached, answers 5xx or 429
        sends the same call to the fallback; any other failure (a 4xx, a cut answer) does not."""
        self.last_route = self.last_model = None
        if not self._key:
            raise ModelError(self._no_key)
        first = Leg(self.route, self._key, self.model_id)
        message, failed, retry = self._send(first, self.endpoint, messages, tools, effort, max_tokens, whole)
        if failed is not None and retry and self.fallback is not None:
            nxt = self.fallback
            # Route names and status only. ERROR, not WARNING: the Arena and the exam quiet warnings
            # while a match runs (arena/match.py demo_store), and a switch of host must still show.
            log.error("%s; this call goes to %s", failed, nxt.route.name)
            message, again, _ = self._send(nxt, nxt.route.endpoint, messages, tools, effort, max_tokens, whole)
            failed = None if again is None else f"{failed}; {again}"
        if failed is not None:
            raise ModelError(failed)
        return message

    def _send(self, leg, endpoint, messages, tools, effort, max_tokens, whole):
        """One request to one leg. Returns (message, None, False) or (None, why, retry), and never
        raises from inside an except block: an error's __context__ would hold the request (key
        header, customer text). retry: the failure is one the fallback is for."""
        name = leg.route.name
        data = json.dumps(self.body(messages, tools, effort, max_tokens, leg=leg)).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, method="POST", headers={
            "Authorization": "Bearer " + leg.key,
            "Content-Type": "application/json",
        })
        failed, retry, out = None, False, None
        try:
            with self._open(req, timeout=self.timeout) as r:
                out = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Only the status. The body can echo the request (customer text) or more, so it is never read.
            failed = f"{name} answered {e.code} {_phrase(e.code)}"
            retry = e.code >= 500 or e.code in FALLBACK_CODES
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
            failed, retry = f"{name} call failed: {type(e).__name__}", True
        except ValueError as e:
            failed = f"{name} call failed: {type(e).__name__}"
        if failed is not None:
            return None, failed, retry
        try:
            choice = out["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            failed = f"{name} answer had no message"
        if failed is not None:
            return None, failed, False
        # finish_reason values from dev.meta.ai/docs/api-reference/chat-completions/schemas (read 29 Oct)
        reason = choice.get("finish_reason") if whole and isinstance(choice, dict) else None
        if reason == "length":
            return None, f"{name} answer was cut off at {int(max_tokens)} tokens", False
        if reason == "content_filter":
            return None, f"{name} answer was stopped by its content filter", False
        self.last_route, self.last_model = name, leg.model_id
        return message, None, False
