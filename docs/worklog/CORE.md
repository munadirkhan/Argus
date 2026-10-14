# Core lane worklog
<!-- Written ONLY by the core lane (agent loop, router, watcher, companion, server). -->
<!-- Newest entry at top. Append only. -->

### 2026-10-14 01:05 — core
**Did:** Built the whole backend. Router (`core/models.py`), agent loop
(`core/agent.py`), watcher (`core/watcher.py`), websocket server
(`core/server.py`). All three offline test suites pass with no API key.
**Affects web:** The real server is runnable NOW without any key —
`ARGUS_FAKE=1 python -m core.server` serves live contract events at
`ws://localhost:8787/ws`. Point the live toggle at that instead of the mock
replay once your components are up; it exercises the same code path the demo
will. `GET /health` reports bound models, tools and spend.
**Needs from web:** the six tools in `core/tools/`. The registry currently
discovers zero, so every `tool.call` comes back `ok:false, "unknown tool"`.
Build `list_dir` and `write_file` first — the demo script calls those.
**Watch out:** `fs.tree` is emitted by the watcher on startup and on every
change, not on request. Expect it unprompted.

### 2026-10-12 23:20 — core
**Did:** Scaffolded repo. Froze `docs/EVENT_CONTRACT.md` and
`docs/TOOL_CONTRACT.md`. Generated `web/mock/events.json` (32-event scripted
demo session). Added `scripts/verify_nebius.py`.
**Affects web:** Build against the mock; it is the exact demo narrative we film.
**Needs from web:** nothing yet.
**Watch out:** Both contracts are frozen. Raise changes in a PR, don't edit.
