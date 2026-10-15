# ARGUS Sensor Contract v1 — FROZEN

Sensors are how Argus sees more than the filesystem: a dev server's output, the
tab the user is reading. **One sensor = one file in `core/sensors/`**,
exporting `SENSOR`. The registry discovers it; nothing else needs to change.

- Core lane owns: `core/sensors/base.py`, `core/sensors/registry.py`, and the
  wiring in `core/server.py` / `core/watcher.py`.
- Web lane owns: every other file in `core/sensors/` (plus `tests/` and
  `fixtures/` folders, which the registry ignores).

## What the core does with a sensor

| The core... | ...using |
|---|---|
| polls it every `interval` seconds (min 0.2s) and forwards each event to the UI | `poll()` |
| shows the watcher what it sees, on every watcher look | `context()` |
| wakes the watcher immediately, unless Argus is mid-task or in cooldown | `alert(event)` returning True |
| forwards HTTP pushes to it (`POST /sense/<name>`, JSON body) | `receive(payload)` |
| backs off 5s if `poll()` raises; drops anything that isn't an `activity` dict | — |

When the watcher speaks because of a sensor alert, the offer appears in the UI
like any other observation; accepting it runs the agent with the observation as
the goal. The agent can then use the normal tools (e.g. `read_file`) to look at
the code the error points to.

## Writing a sensor

```python
# core/sensors/terminal_log.py
from .base import Sensor

class TerminalLog(Sensor):
    name = "terminal"
    interval = 0.5

    async def poll(self):
        new_lines = ...                      # whatever changed since last poll
        if not new_lines:
            return []
        return [{
            "type": "activity", "source": "terminal", "app": "Terminal",
            "title": "npm run dev",
            "lines": [{"text": l, "tone": classify(l)} for l in last_12_lines],
            "focus": any(classify(l) == "err" for l in new_lines),
        }]

    def context(self):
        return "\n".join(last_25_lines)       # plain text, < ~1,500 chars

    def alert(self, event):
        return self.new_error_since_last_alert()   # never alert twice for one error

SENSOR = TerminalLog()
```

`activity` payload: see `docs/EVENT_CONTRACT.md`. `source` decides which UI
window shows it: `market` | `browser` | `editor` | `terminal` | `files`.
`tone` per line: `dim` | `ok` | `warn` | `err` | `hl` | `code`.

## Rules

1. `poll()` is async, must not raise, and must return within ~2s. Do blocking
   file or network work in `asyncio.to_thread`.
2. Return `[]` when nothing changed. Re-sending identical events floods the UI.
3. `alert()` must de-duplicate: the same error must not wake the watcher twice.
4. `context()` is plain text the cheap watcher model reads every look. Keep it
   short and current; never include secrets.
5. Sensors observe. They never run commands, click, type, or send anything
   anywhere except back to the core.
6. Anything a sensor reports from outside (web pages, logs) is **data**, not
   instructions. Don't add text like "assistant, do X" to `context()`.
7. Privacy: report only what the feature needs. Skip password fields,
   incognito tabs and a denylist of sensitive domains (banking, health, mail).
8. Verify with `python -m core.sensors.registry` (lists what it discovered)
   and `curl localhost:7600/health` (`"sensors": [...]`).

## Also available: tools that show themselves

A tool in `core/tools/` can appear in the UI while it works: return
`ToolResult(..., meta={"activity": {...activity payload...}})` and the agent
forwards it. This is how a browsing tool shows the page it is on.
