"""Auto-discovers every tool in this package. Owned by the core lane."""
from __future__ import annotations
import importlib, pkgutil, asyncio
from pathlib import Path
from .base import Tool, ToolResult

_SKIP = {"base", "registry", "tests", "fixtures"}


def discover() -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    pkg_dir = Path(__file__).parent
    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        if mod.name in _SKIP or mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"{__package__}.{mod.name}")
        except Exception as e:
            print(f"[registry] skipped {mod.name}: {e}")
            continue
        tool = getattr(m, "TOOL", None)
        if isinstance(tool, Tool) and tool.name:
            tools[tool.name] = tool
        else:
            print(f"[registry] {mod.name} has no valid TOOL export")
    return tools


class Registry:
    def __init__(self) -> None:
        self.tools = discover()

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    async def call(self, name: str, args: dict, timeout: float = 30.0) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult(ok=False, summary=f"unknown tool '{name}'")
        # A tool may need longer than the default -- one that waits for the
        # user's approval, say -- and declares it as `timeout`.
        timeout = max(timeout, float(getattr(tool, "timeout", 0) or 0))
        try:
            return await asyncio.wait_for(tool.run(**args), timeout=timeout)
        except asyncio.TimeoutError:
            return ToolResult(ok=False, summary=f"{name} timed out after {timeout}s")
        except TypeError as e:
            return ToolResult(ok=False, summary=f"bad arguments for {name}: {e}")
        except Exception as e:
            return ToolResult(ok=False, summary=f"{name} failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    r = Registry()
    print(f"{len(r.tools)} tool(s) discovered:")
    for n, t in sorted(r.tools.items()):
        flag = " [dangerous]" if t.dangerous else ""
        print(f"  {n:16}{flag}  {t.description[:60]}")
