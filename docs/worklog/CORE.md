# Core lane worklog
<!-- Written ONLY by the core lane (agent loop, router, watcher, companion, server). -->
<!-- Newest entry at top. Append only. -->

### 2026-10-14 (night) — core
**Did:** Shipped UI v1 in `web/` (now yours — see the rewritten `docs/ASTRA_BRIEF.md`).
Built the sensor socket: `core/sensors/{base,registry}.py`, `docs/SENSOR_CONTRACT.md`,
server polling + `POST /sense/<name>`, watcher reads `context()`, `alert()` wakes it.
Agent: browser activity for live searches/reads; tools can show themselves via
`meta.activity`; writer replaces code files verbatim when a plan step names one.
**Affects web:** port is 7600 (was 8787). `/health` now has `"sensors"`. Contract gained
`activity` + `user.accept` (additive).
**Needs from web:** Jobs 1–3 in the brief: terminal sensor first, then browser, then UI.
**Watch out:** the registries skip `tests/` and `fixtures/` folders and `_`-prefixed files.

### 2026-10-14 (later) — core
**Did:** Built all six tools in `core/tools/` (tavily_search, fetch_url, read_file w/ PDF,
write_file, list_dir, shell). File tools are confined to the workspace; shell is off unless
`ARGUS_ALLOW_SHELL=1`. Agent now carries real tool output between steps and Ultra writes the
final document. Full demo runs live end to end (`scripts/live_demo.py`, demo workspace from
`scripts/seed_demo.py`).
**Affects web:** `artifact.write.path` is now absolute; `preview` up to 4000 chars.
Accepting an observation is `{"type":"user.accept","id":"obs_N"}` (new client message).
**Needs from web:** nothing — UI v1 is being built in the core lane. Do not start UI work
until it lands on main.
**Watch out:** do not rebuild the tools. Known issue: the watcher's offer is sometimes weak
("fill in notes.md") and the run then skips the web check — prompt tuning, in progress.

### 2026-10-14 — core
**Did:** Went live on Nebius. All 4 Nemotron models confirmed, all do native
tool calling. Added per-tier reasoning switch (thinking OFF for watcher and
executor, ON for planner) and a persistent hard spend cap (`ARGUS_BUDGET_USD`,
default $10). Watcher now speaks 3/3 on the demo scenario in ~0.8s live.
**Affects web:** `usage` events from the planner now carry more completion
tokens (Ultra's reasoning is billed). Budget exhaustion arrives as a normal
`error` event ("Spend cap reached...") — please render it calmly, not as a
crash. Watcher observations are now one short sentence + a "Want me to...?"
offer, so the ObservationCard can be sized for that.
**Needs from web:** still the tools. `tavily_search`, `read_file` (with PDF),
`write_file` are now the critical path — the model side is proven.
**Watch out:** all Nemotron models are served in us-central1; ignore the old
"different regions" note. Never commit `.env` or `.argus_spend.json`.

### 2026-10-14 01:05 — core
**Did:** Built the whole backend. Router (`core/models.py`), agent loop
(`core/agent.py`), watcher (`core/watcher.py`), websocket server
(`core/server.py`). All three offline test suites pass with no API key.
**Affects web:** The real server is runnable NOW without any key —
`ARGUS_FAKE=1 python -m core.server` serves live contract events at
`ws://localhost:7600/ws`. Point the live toggle at that instead of the mock
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
