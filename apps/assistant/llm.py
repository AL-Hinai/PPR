"""The language model behind the assistant, ported from Roaa's LLM layer.

Two providers:

- ``openai`` talks to anything that serves ``POST /chat/completions`` the OpenAI way
  (DeepSeek, OpenAI, a gateway). Standard library only, so PythonAnywhere needs no
  extra package. Streamed: prose is yielded as it is written.
- ``offline`` needs no model at all. It searches the dossier and returns the most
  relevant passages, so the drawer still works on a deployment without an API key
  (and the test-suite runs without the network).

Two details from Roaa are load-bearing: streamed tool-call arguments arrive in
fragments keyed by ``index`` and must be joined before decoding, and token usage is
only reported on a stream when ``stream_options.include_usage`` is set.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from django.conf import settings
from django.utils.translation import gettext as _


class LlmUnavailable(Exception):
    """The model could not be reached or answered with something unusable."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Message:
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str = ""

    def as_wire(self) -> dict:
        wire: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            wire["content"] = self.content or None
            wire["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                }
                for call in self.tool_calls
            ]
        if self.tool_call_id:
            wire["tool_call_id"] = self.tool_call_id
        return wire


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict

    def as_wire(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.prompt_tokens + other.prompt_tokens, self.completion_tokens + other.completion_tokens)


@dataclass(frozen=True)
class Completion:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)

    def as_message(self) -> Message:
        return Message(role="assistant", content=self.text, tool_calls=self.tool_calls)


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Finished:
    completion: Completion


# --------------------------------------------------------------------- OpenAI-compatible

class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, config: dict | None = None):
        self.config = config or settings.ASSISTANT
        self.model = self.config["MODEL"]

    def stream(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = ()) -> Iterator[TextDelta | Finished]:
        payload: dict = {
            "model": self.model,
            "messages": [m.as_wire() for m in messages],
            "temperature": self.config.get("TEMPERATURE", 0.2),
            "stream": True,
            # Without this the final usage frame is never sent.
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = [t.as_wire() for t in tools]

        text = ""
        usage = Usage()
        parts: dict[int, dict] = {}
        for frame in self._frames(payload):
            if frame.get("usage"):
                raw = frame["usage"]
                usage = Usage(int(raw.get("prompt_tokens") or 0), int(raw.get("completion_tokens") or 0))
            choices = frame.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                text += delta["content"]
                yield TextDelta(delta["content"])
            for call in delta.get("tool_calls") or []:
                part = parts.setdefault(call.get("index", 0), {"id": "", "name": "", "arguments": ""})
                if call.get("id"):
                    part["id"] = call["id"]
                function = call.get("function") or {}
                if function.get("name"):
                    part["name"] = function["name"]
                if function.get("arguments"):
                    part["arguments"] += function["arguments"]

        calls = tuple(
            ToolCall(id=p["id"] or f"call_{i}", name=p["name"], arguments=_arguments(p["arguments"]))
            for i, p in sorted(parts.items())
        )
        yield Finished(Completion(text=text, tool_calls=calls, usage=usage))

    def _frames(self, payload: dict) -> Iterator[dict]:
        url = self.config["BASE_URL"].rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.config['API_KEY']}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.config["TIMEOUT"])  # noqa: S310 - configured URL
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode(errors="replace")
            raise LlmUnavailable(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LlmUnavailable(str(exc)) from exc
        with response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue


def _arguments(raw: str) -> dict:
    try:
        decoded = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise LlmUnavailable(f"tool arguments were not JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise LlmUnavailable("tool arguments were not an object")
    return decoded


# --------------------------------------------------------------------------- offline

class OfflineProvider:
    """No model: search the dossier for the question and show the best passages.

    It drives the same agent loop and the same tools as a real model, which is
    what makes it useful as a test double as well as a fallback.
    """

    name = "offline"
    model = ""

    def stream(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = ()) -> Iterator[TextDelta | Finished]:
        question = next((m.content for m in reversed(messages) if m.role == "user"), "")
        last = messages[-1] if messages else None
        if last is None or last.role != "tool":
            yield Finished(Completion(tool_calls=(ToolCall("offline-1", "search_documents", {"query": question}),)))
            return
        try:
            result = json.loads(last.content)
        except json.JSONDecodeError:
            result = {}
        text = self._compose(result)
        yield TextDelta(text)
        yield Finished(Completion(text=text))

    def _compose(self, result: dict) -> str:
        lines = [_("Offline mode: no language model is configured, so these are the most relevant passages "
                   "from the dossier rather than a written answer.")]
        if result.get("error"):
            lines += ["", result["error"]]
            return "\n".join(lines)
        hits = result.get("hits") or []
        if not hits:
            lines += ["", _("No passage in the dossier matched the question. Try the exact term used in the "
                            "documents (dossiers are usually in English).")]
            return "\n".join(lines)
        for hit in hits[:5]:
            lines += ["", f"**{hit['title']}** [{hit['sequence']}/{hit['path']} p.{hit['page']}]", f"> {hit['snippet']}"]
        return "\n".join(lines)


def provider():
    """The configured provider; offline when no API key is set."""
    config = settings.ASSISTANT
    if config["PROVIDER"] == "offline" or not config["API_KEY"]:
        return OfflineProvider()
    return OpenAICompatibleProvider(config)
