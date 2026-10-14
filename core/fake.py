"""A scripted stand-in for the Nebius client, shaped like the OpenAI SDK.

Lets the whole agent loop be built and tested with no API key and no network.
Swap it in via ModelRouter(client_factory=FakeClient.factory(script)).
"""
from __future__ import annotations
import json, itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# --- response shapes mirroring the OpenAI SDK ---------------------------
@dataclass
class _Fn:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Fn
    type: str = "function"


@dataclass
class _Message:
    content: str | None = None
    tool_calls: list[_ToolCall] | None = None
    role: str = "assistant"


@dataclass
class _Choice:
    message: _Message
    finish_reason: str = "stop"


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int = 0


@dataclass
class _Response:
    choices: list[_Choice]
    usage: _Usage


@dataclass
class _Model:
    id: str


@dataclass
class _ModelList:
    data: list[_Model]


# --- scripting ----------------------------------------------------------
@dataclass
class Turn:
    """One scripted model response."""
    text: str | None = None
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)  # (name, args)
    prompt_tokens: int = 1200
    completion_tokens: int = 180

    def build(self, counter: itertools.count) -> _Response:
        tcs = [
            _ToolCall(id=f"tc_{next(counter)}", function=_Fn(name=n, arguments=json.dumps(a)))
            for n, a in self.tool_calls
        ] or None
        return _Response(
            choices=[_Choice(_Message(content=self.text, tool_calls=tcs))],
            usage=_Usage(self.prompt_tokens, self.completion_tokens,
                         self.prompt_tokens + self.completion_tokens),
        )


# Catalogue the fake reports, mimicking the real split across regions.
# Mirrors the live catalogue as probed on 2026-10-14: all four Nemotron models
# are served in both regions, alongside non-Nemotron models we must not pick.
_LIVE = ["nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "nvidia/Nemotron-3-Ultra-550b-a55b",
         "nvidia/Nemotron-3_5-Lightning", "nvidia/nemotron-3-super-120b-a12b",
         "meta/llama-3.3-70b", "deepseek-ai/DeepSeek-V4.1-Flash"]
FAKE_CATALOGUE = {"us": list(_LIVE), "eu": list(_LIVE)}


class FakeClient:
    """Mimics AsyncOpenAI closely enough for ModelRouter."""

    def __init__(self, region: str, script: dict[str, Iterable[Turn]] | None = None,
                 catalogue: dict[str, list[str]] | None = None) -> None:
        self.region = region
        self._catalogue = catalogue or FAKE_CATALOGUE
        self._script = {k: list(v) for k, v in (script or {}).items()}
        self._cursor: dict[str, int] = {}
        self._ids = itertools.count(1)
        self.calls: list[dict[str, Any]] = []
        self.models = self._Models(self)
        self.chat = self._Chat(self)

    @classmethod
    def factory(cls, script: dict[str, Iterable[Turn]] | None = None,
                catalogue: dict[str, list[str]] | None = None,
                sink: list["FakeClient"] | None = None) -> Callable[[str, str], "FakeClient"]:
        def make(region: str, api_key: str) -> FakeClient:
            c = cls(region, script, catalogue)
            if sink is not None:
                sink.append(c)
            return c
        return make

    class _Models:
        def __init__(self, outer: "FakeClient") -> None:
            self._o = outer

        async def list(self) -> _ModelList:
            return _ModelList([_Model(i) for i in self._o._catalogue.get(self._o.region, [])])

    class _Chat:
        def __init__(self, outer: "FakeClient") -> None:
            self.completions = FakeClient._Completions(outer)

    class _Completions:
        def __init__(self, outer: "FakeClient") -> None:
            self._o = outer

        async def create(self, **kwargs: Any) -> _Response:
            o = self._o
            o.calls.append(kwargs)
            model = kwargs.get("model", "")
            # Pick the script bucket by family name found in the model id.
            bucket = next((f for f in ("ultra", "super", "nano", "lightning")
                           if f in model.lower()), "default")
            turns = o._script.get(bucket) or o._script.get("default") or []
            i = o._cursor.get(bucket, 0)
            if i < len(turns):
                o._cursor[bucket] = i + 1
                return turns[i].build(o._ids)
            return Turn(text="(fake: script exhausted)").build(o._ids)
