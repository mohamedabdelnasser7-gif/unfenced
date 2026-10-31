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

The call carries the API key, so it goes through kit.net and never follows a redirect: urllib's
default opener follows a 302 on a POST as a GET and keeps the Authorization header.
"""
import http
import json
import typing
import urllib.error
import urllib.request

from kit import env, net

ENDPOINT = "https://inference.baseten.co/v1/chat/completions"
DEFAULT_MODEL = "meta-models/muse-spark-open-1026"
CHANGELOG_MODEL = "meta-models/muse-spark-open"

META_ENDPOINT = "https://api.meta.ai/v1/chat/completions"
WONDER_MODEL = "muse-wonder-1.0"

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


class ModelError(Exception):
    """The model call failed. The message never holds the key."""


def _phrase(code):
    try:
        return http.HTTPStatus(code).phrase
    except ValueError:
        return "error"


class Model:
    def __init__(self, api_key=None, model_id=None, endpoint=None, timeout=90, opener=None, route=OPEN):
        self.route = route
        self._key = api_key if api_key is not None else env.get(route.key_env)
        self.model_id = model_id or env.get(route.model_env, route.default_model)
        self.endpoint = endpoint or route.endpoint
        self.timeout = timeout
        self._open = opener or net.open_once

    def body(self, messages, tools=None, effort=EFFORT_REPLY, max_tokens=1500):
        if self.route.efforts and effort not in self.route.efforts:
            raise ModelError(f"{self.route.name} takes reasoning effort {', '.join(self.route.efforts)} only")
        body = {
            "model": self.model_id,
            "messages": messages,
            self.route.max_field: max_tokens,
            "reasoning_effort": effort,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body

    def chat(self, messages, tools=None, effort=EFFORT_REPLY, max_tokens=1500, whole=False):
        """Send one request. Returns the assistant message dict (content and maybe tool_calls).
        whole: an answer the host cut off at max_tokens is an error, not a shorter answer.
        Reasoning tokens count against max_tokens, so a long think can cut the answer."""
        name = self.route.name
        if not self._key:
            raise ModelError(f"{self.route.key_env} is not set")
        data = json.dumps(self.body(messages, tools, effort, max_tokens)).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, method="POST", headers={
            "Authorization": "Bearer " + self._key,
            "Content-Type": "application/json",
        })
        # Each raise sits outside its except block, so the ModelError keeps no link to the
        # original error: its __context__ would hold the request (key header, customer text).
        failed = None
        try:
            with self._open(req, timeout=self.timeout) as r:
                out = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Only the status. The body can echo the request (customer text) or more, so it is never read.
            failed = f"{name} answered {e.code} {_phrase(e.code)}"
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            failed = f"{name} call failed: {type(e).__name__}"
        if failed is not None:
            raise ModelError(failed)
        try:
            choice = out["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            failed = f"{name} answer had no message"
        if failed is not None:
            raise ModelError(failed)
        # finish_reason values from dev.meta.ai/docs/api-reference/chat-completions/schemas (read 29 Oct)
        reason = choice.get("finish_reason") if whole and isinstance(choice, dict) else None
        if reason == "length":
            raise ModelError(f"{name} answer was cut off at {int(max_tokens)} tokens")
        if reason == "content_filter":
            raise ModelError(f"{name} answer was stopped by its content filter")
        return message
