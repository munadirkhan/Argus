"""Base types for AURA tools. Owned by the core lane — do not edit in the web lane."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    summary: str                                  # one line, rendered in the UI
    detail: str = ""                              # full text, fed to the model
    meta: dict[str, Any] = field(default_factory=dict)

    def for_model(self, limit: int = 8000) -> str:
        """What the model actually sees."""
        if not self.ok:
            return f"ERROR: {self.summary}"
        body = self.detail or self.summary
        if len(body) > limit:
            body = body[:limit] + f"\n...[truncated, {len(body) - limit} chars omitted]"
        return body


class Tool:
    """Subclass this, set the four class attrs, implement run(). Export as TOOL."""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    dangerous: bool = False

    async def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        """OpenAI-style function definition handed to Nemotron."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
