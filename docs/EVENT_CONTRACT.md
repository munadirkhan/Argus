# ARGUS Event Contract v1  — FROZEN

Single source of truth between `core/` (backend) and `web/` (frontend).
**Do not change without both owners agreeing.** Add new `type`s freely; never
rename or repurpose existing fields.

Transport: one websocket, server→client JSON, one event per message.
Client→server only ever sends `user.message` and `user.dismiss`.

Every event has:

```json
{ "v": 1, "seq": 12, "ts": 1760300000.123, "type": "<name>", "...": "payload" }
```

`seq` is monotonic. Client may drop out-of-order events.

---

## Server → Client

### `session.state`
```json
{ "type":"session.state", "runtime":"local", "status":"connected",
  "cwd":"C:/Users/you/projects", "label":"Ryan's PC" }
```
`runtime`: `"local"` | `"sandbox"` · `status`: `"connected"` | `"connecting"` | `"degraded"`

### `watcher.observation`   ← the Jarvis moment
```json
{ "type":"watcher.observation", "id":"obs_7", "confidence":0.82,
  "observation":"You've opened three papers on diffusion sampling and started a blank notes file.",
  "suggestion":"Want me to pull the latest work on this and draft a summary?",
  "dismissible":true }
```

### `agent.message`
```json
{ "type":"agent.message", "id":"m_4", "role":"assistant",
  "text":"Working on something secret, sir?", "streaming":true, "done":false }
```
Stream by re-sending same `id` with the full text so far. `done:true` ends it.

### `agent.plan`
```json
{ "type":"agent.plan", "id":"plan_2", "steps":[
  {"id":"s1","title":"Search recent literature","status":"running"},
  {"id":"s2","title":"Read and extract claims","status":"pending"},
  {"id":"s3","title":"Write summary to disk","status":"pending"}]}
```
`status`: `pending` | `running` | `done` | `failed`

### `agent.step`
```json
{ "type":"agent.step", "plan_id":"plan_2", "id":"s1", "status":"done" }
```

### `agent.thinking`   ← drives the routing HUD
```json
{ "type":"agent.thinking", "tier":"planner",
  "model":"nvidia/Nemotron-3-Ultra-550b-a55b", "note":"Decomposing request" }
```
`tier`: `watcher` | `planner` | `executor`

### `tool.call` / `tool.result`
```json
{ "type":"tool.call", "id":"tc_9", "name":"tavily_search",
  "args":{"query":"diffusion sampling 2026"} }
{ "type":"tool.result", "id":"tc_9", "ok":true,
  "summary":"6 results", "detail":"..." }
```
Tool names: `read_file` `write_file` `list_dir` `shell` `tavily_search` `fetch_url`

### `artifact.write`
```json
{ "type":"artifact.write", "path":"C:/notes/diffusion-summary.md",
  "kind":"md", "bytes":4210, "preview":"# Diffusion sampling, Oct 2026\n\n..." }
```
`kind`: `md` | `code` | `json` | `txt`

### `fs.tree`
```json
{ "type":"fs.tree", "root":"C:/notes",
  "nodes":[{"path":"C:/notes/plan.txt","dir":false,"bytes":120}] }
```

### `usage`   ← drives the cost meter
```json
{ "type":"usage", "tier":"executor", "model":"nvidia/...nano-30b-a3b",
  "prompt_tokens":1840, "completion_tokens":210,
  "cost_usd":0.00016, "cumulative_cost_usd":0.0412 }
```

### `error`
```json
{ "type":"error", "message":"Sandbox timed out", "fatal":false }
```

### `activity`   (additive, 2026-10-14)
What the user is doing, as Argus sees it. Drives the "sight windows" in the UI.
Today only simulated sessions emit app-level activity; live mode surfaces file
changes via `fs.tree`.
```json
{ "type":"activity", "source":"terminal", "app":"Terminal", "title":"npm run dev",
  "lines":[{"text":"TypeError: ...","tone":"err"}], "focus":true }
```
`source`: `market` | `browser` | `editor` | `terminal` | `files` ·
`tone`: `dim` | `ok` | `warn` | `err` | `hl` | `code` · optional `market`,
`url`, `startLine`, `errorLine`.

---

## Client → Server

```json
{ "type":"user.message", "text":"summarize what I'm working on" }
{ "type":"user.message", "text":"read this", "attachments":[{"path":".argus/attachments/report.pdf"}] }   // additive
{ "type":"user.dismiss", "id":"obs_7" }
{ "type":"user.accept", "id":"obs_7" }   // run what the watcher offered (additive)
```

### Attachments (additive, 2026-10-18)
Files are uploaded first with `POST /attach?name=<file>` (raw body) and land in
`<workspace>/.argus/attachments/`. A `user.message` may then carry
`attachments: [{path}]`; the server accepts only paths that really exist in that
folder. The echoed user `agent.message` carries `attachments: [{path,name,bytes,kind}]`
(`kind`: `image` | `pdf` | `file`). Voice: `POST /transcribe` (raw audio body) →
`{ok, text, ms}`, transcribed locally.

### Who may connect (additive, 2026-10-18)
The core listens on `127.0.0.1` only and refuses any request (HTTP or WebSocket)
whose `Origin` isn't `http(s)://localhost|127.0.0.1|[::1][:port]`, `argus://app`
(the desktop app) or a browser extension, or whose `Host` isn't loopback. Requests
with no `Origin` (local programs) pass. A refused WebSocket closes with 1008 before
accept; a refused HTTP request gets 403. Add origins with `ARGUS_ALLOWED_ORIGINS`.
