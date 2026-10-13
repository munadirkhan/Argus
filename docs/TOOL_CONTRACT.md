# AURA Tool Contract v1 — FROZEN

How the agent loop (core lane) and the tools (web lane) stay decoupled.

**One tool = one file in `core/tools/`.** The registry auto-discovers them.
The agent loop never imports a tool directly, and a tool never imports the
agent loop. Neither lane edits the other's files.

- Core lane owns: `core/tools/base.py`, `core/tools/registry.py`
- Web lane owns: every other file in `core/tools/`

## Writing a tool

```python
# core/tools/tavily_search.py
from .base import Tool, ToolResult

class TavilySearch(Tool):
    name = "tavily_search"
    description = "Search the live web for current information."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 5) -> ToolResult:
        ...
        return ToolResult(
            ok=True,
            summary=f"{len(hits)} results",      # one line, shown in UI
            detail="\n".join(...),                # full text, for the model
            meta={"urls": [...]},                 # optional, structured
        )

TOOL = TavilySearch()      # module MUST export `TOOL`
```

`parameters` is JSON Schema and is handed straight to the model as a function
definition — so write the descriptions for the *model*, not for a human.

## Rules

1. `run()` is async and must never raise. Catch everything and return
   `ToolResult(ok=False, summary="<what went wrong>")`.
2. `run()` must return within 30s. Enforce your own timeout.
3. `summary` is one short line — it renders in the UI as a collapsed row.
   `detail` is what the model reads. Keep `detail` under ~8k characters.
4. No printing, no logging to stdout — stdout is the websocket transport.
5. Read config from env vars only. Never hardcode a key.
6. Destructive tools (`write_file`, `shell`) set `dangerous = True` so the
   loop can gate them.

## Tools to build (web lane owns all of these)

| name | notes |
|---|---|
| `tavily_search` | Tavily API. **$3,000 track prize — make this excellent.** |
| `fetch_url` | Fetch a page, strip to readable text. |
| `read_file` | Read local file. PDF → text if it ends in `.pdf`. |
| `write_file` | `dangerous = True` |
| `list_dir` | Respect `.gitignore`-style excludes, cap depth. |
| `shell` | `dangerous = True`. Timeout 20s, capture stdout+stderr. |

`read_file` handling PDFs matters — the demo reads two PDFs off disk.
