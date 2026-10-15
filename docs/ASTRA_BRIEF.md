# Brief for Astra — ARGUS, round 2

You are picking up a working hackathon project. Read this entire brief before
writing any code, then read `docs/worklog/CORE.md`, `docs/EVENT_CONTRACT.md`,
`docs/SENSOR_CONTRACT.md` and `docs/TOOL_CONTRACT.md`.

You own three jobs, in this priority order:

1. **The terminal sensor**: Argus watches a dev server's output and offers to
   fix crashes. This makes the "Code" scene a live capability. **Ship this first.**
2. **The browser**: a browser-tab sensor (Argus knows what page the user is
   reading) plus a `browse` tool (Argus can drive a headless browser to read
   pages the simple fetcher can't).
3. **The UI**: carry the existing interface forward.

Do all three completely: code, tests, docs, worklog, PR. Don't stop at a
prototype, and don't ask for permission on things this brief already decides.

---

## 0. What ARGUS is, and what already works

An always-on agent that lives on your computer. It watches what you're doing,
speaks up unprompted when it can genuinely help ("Working on something secret,
sir?"), then does real work: searches the live web, reads your files, reasons,
and writes the result back to your disk. The name is Argus Panoptes, the
hundred-eyed giant who never slept.

It runs on **NVIDIA Nemotron via Nebius Token Factory**, routed three ways:

| Tier | Model | Job |
|---|---|---|
| Watcher | Nemotron 3.5 Lightning, reasoning off | always-on, decides whether to speak (~$0.00007 a look) |
| Oracle | Nemotron 3 Ultra 550B, reasoning on | plans, writes the final document or fix, replies |
| Hands | Nemotron 3 Nano 30B, reasoning off | executes steps with tools |

**Working today, live and tested** (7 offline test suites, all passing):
- Watcher: diffs the workspace and peeks into new files. **Live, it only sees
  the filesystem** — that is what your sensors change.
- Agent: plan → execute with tools → Ultra writes the file → short reply.
  Grounded in Token Factory's live model catalogue.
- Tools (`core/tools/`): `tavily_search`, `fetch_url`, `read_file` (PDFs too),
  `write_file`, `list_dir`, `shell` (opt-in). File tools are confined to the
  workspace.
- Hard spend cap (`ARGUS_BUDGET_USD`, default $10), persisted and enforced
  before every model call.
- **The sensor socket, ready for you:** `core/sensors/base.py`, the registry, and
  the server/watcher wiring. A sensor's events reach the UI, its `context()`
  goes into every watcher look, and an `alert()` wakes the watcher instantly.
  `POST /sense/<name>` forwards pushes (from an extension) to `receive()`.
- When the agent fixes code, the writer replaces the named code file verbatim.
  When it searches or reads a page, that shows up in the UI's browser window.
- UI (`web/`): finished v1. Do not redesign it. See section 5.

---

## 1. Setup

You need your **own** keys. That's the point of you running this: it spends
your credits, not ours.
- Nebius Token Factory key: tokenfactory.nebius.com → API keys. The hackathon
  credits come from Devpost Resources (activation code) + the Nebius Builder
  Program — $25 each.
- Tavily key: tavily.com (free tier, no card).

Windows (PowerShell; it doesn't support `&&`, so run one line at a time):
```powershell
cd Argus
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # then put NEBIUS_API_KEY and TAVILY_API_KEY in .env
$env:ARGUS_WATCH_ROOT = "C:\path\to\a\scratch-folder"   # the folder Argus watches
.\.venv\Scripts\python.exe -m core.server                # core on http://localhost:7600
```
In a second terminal:
```powershell
cd Argus\web
npm install
npm run dev                    # UI on http://localhost:5173
```
macOS/Linux: same, with `.venv/bin/python` and `export ARGUS_WATCH_ROOT=...`.

- **No key?** Set `ARGUS_FAKE=1` before starting the core: scripted models, real
  tools, real websocket.
- The UI has two modes. **LIVE** is the real core. **SIMULATE** plays scripted
  sessions (`web/src/sim/scenarios.ts`) plus one recording of a real run.
- Port is **7600**, not 8787, because 8787 is commonly taken by other apps.
- Health: `curl localhost:7600/health` shows bound models, tools, sensors,
  spend and the cap.

Tests must all pass before any PR:
```powershell
.\.venv\Scripts\python.exe scripts\test_agent_offline.py
.\.venv\Scripts\python.exe scripts\test_watcher_offline.py
.\.venv\Scripts\python.exe scripts\test_server_offline.py
.\.venv\Scripts\python.exe scripts\test_budget_offline.py
.\.venv\Scripts\python.exe scripts\test_writer_offline.py
.\.venv\Scripts\python.exe scripts\test_sensors_offline.py
.\.venv\Scripts\python.exe scripts\test_tools.py
cd web; npx tsc --noEmit -p .
```

---

## 2. Boundaries, git, worklog

You may create and edit files **only** here:
- `web/` — all of it. You now own the UI.
- `core/sensors/` — everything **except** `base.py` and `registry.py`.
- `core/tools/` — everything **except** `base.py`, `registry.py`, `_workspace.py`.
- `extension/` — new; the browser extension lives here.
- `docs/worklog/WEB.md` — your log.
- `requirements.txt` — append only, for packages you need (e.g. `playwright`).

Everything else is the core lane: agent, router, watcher, server, prompts,
contracts, scripts/, README. If you need a change there, describe it in your
PR and in `WEB.md` under **Needs from core**. Don't make it yourself.

The four contract files are frozen. Additive changes go through the PR.

Git: work on `feat/web`. Pull `main` first (`git pull origin main`). Small
commits. Open a PR `feat/web` → `main` per job (three PRs), with screenshots.
Never commit `.env`, `.argus_spend.json`, `node_modules`, or logs.

Worklog: read `docs/worklog/CORE.md` at the start of every session. Append to
`docs/worklog/WEB.md` before every PR, newest entry first, four lines, format
in `docs/worklog/README.md`.

---

## 3. Job 1 — the terminal sensor (do this first)

**Goal:** a developer runs their dev server through Argus. When it crashes,
Argus notices within ~2 seconds, says what broke and where, and on "Proceed"
reads the file and writes the fix. The UI's terminal window shows the real
output with the error in red.

### 3a. `core/sensors/terminal_log.py`  (exports `SENSOR`, `name = "terminal"`)

**A wrapper that makes any command watchable.** The same module, run as a
script, runs a command and tees its output:
```
python -m core.sensors.terminal_log run -- npm run dev
python -m core.sensors.terminal_log run -- node dev.js
```
- Runs the command as a subprocess. On Windows `npm` is `npm.cmd`: resolve
  with `shutil.which`, or use `shell=True` when the first token isn't found.
- Streams stdout+stderr to the console unchanged, **and** appends to
  `<workspace>/.argus/terminal.log`, with ANSI escape codes stripped in the log.
  Workspace = `ARGUS_WATCH_ROOT`, else the current directory. Create `.argus/`.
- Writes a header line `$ <command>` when it starts and `[exit <code>]` when
  the process ends. Exits with the child's exit code. Ctrl+C stops the child.
- `.argus/` starts with a dot, so the watcher's file scan ignores it. Only this
  sensor reads it. That's intended.

**The sensor tails logs:**
- Sources: `<workspace>/.argus/terminal.log`, plus any paths in `ARGUS_LOGS`
  (separated by `os.pathsep`; this is explicit opt-in, so they may be outside
  the workspace).
- Track a byte offset per file. First time you see a file, start **at the end**
  (don't replay old history), but load the last 25 lines into context.
- Handle truncation and rotation (size < offset → start from 0), partial lines
  (buffer until newline), `utf-8` with `errors="replace"`, and ANSI codes.
- Do file reads in `asyncio.to_thread`. `interval = 0.5`.

**Classify every line into a `tone`:**
- `err`: `Error`, `Exception`, `Traceback`, `FATAL`, `panic:`, `npm ERR!`,
  `Uncaught`, `✗`/`×`/`✘`, `FAILED`, `ERR_...`, `[exit N]` with N ≠ 0. Stack
  frames that follow an error (`    at foo (file.js:12:5)`, Python
  `  File "x.py", line 3`) are also `err`.
- `warn`: `warn`, `warning`, `deprecated` (case-insensitive).
- `ok`: `ready in`, `compiled`, `✓`/`✔`, `listening on`, `Local:`, `[exit 0]`.
- `dim`: the `$ cmd` header and blank-ish noise. Everything else: no tone.

**Emit** one `activity` per poll when there are new lines:
`source: "terminal"`, `app: "Terminal"`, `title` = the command from the latest
`$ ` header (else the file name), `lines` = the last 12 lines with tones,
`focus: true` only if the new lines contain an error.

**`context()`**: `Log: <file>` followed by the last 25 lines, error lines
prefixed `!! `. Max ~1,500 characters.

**`alert(event)`**: true only for a **new** error. The signature is the first
`err` line, normalized: strip timestamps, hex addresses and durations, but
keep `file:line`. Remember the last 20 signatures. The same signature may alert
again only after the log has shown an `ok` line since (fixed, then broken
again).

### 3b. Fixture: a real crash to demo

Create `core/sensors/fixtures/buggy-app/`, with no dependencies and runnable
with plain `node`:
- `dev.js`: prints realistic dev-server start lines (`ready in 412 ms`,
  `Local: http://localhost:5173/`), waits ~1.5s, then requires `./watchlist.js`
  and renders it with a quotes object whose `data` is `undefined` on first
  load. This throws a **real** `TypeError: Cannot read properties of undefined
  (reading 'map')` with a real stack pointing at `watchlist.js:<line>`.
  Catch nothing; let it crash with a non-zero exit.
- `watchlist.js`: ~30 lines; the bug is `quotes.data.map(...)`.
- `README.md`: how to run it under the wrapper.

Add a script `core/sensors/fixtures/seed_buggy_app.py` that copies the app
into a target folder (default `../desk-dashboard` next to the repo), so the
watched workspace is a clean copy you can break and fix repeatedly.

### 3c. Tests: `core/sensors/tests/test_terminal_log.py`

A plain script in the style of `scripts/test_*_offline.py` (prints
PASS/FAIL, exits non-zero on failure). Cover: start-at-end, tailing new lines,
partial-line buffering, truncation, ANSI stripping, classification of every
pattern above, stack frames inherit `err`, alert dedupe and re-alert after
`ok`, `context()` length cap, and the wrapper (writes the log, writes header
and exit line, preserves exit code, using a tiny Python child process so it
runs anywhere).

### 3d. Acceptance (do it and put the screenshots in the PR)

1. Seed the buggy app into a folder and start the core with
   `ARGUS_WATCH_ROOT` pointing at it.
2. UI in LIVE mode. Run the app through the wrapper.
3. Within ~2 seconds: the terminal window appears with the TypeError in red
   and the eyes turn to it, then the watcher's prophecy names the error and
   the file and line.
4. Click PROCEED. The agent reads `watchlist.js`, Ultra writes the fixed file,
   and the Chronicle shows INSCRIBED.
5. Run the app again: clean start, green line in the terminal window.
6. `/health` shows `"sensors": ["terminal", ...]`.

If step 3 or 4 misbehaves because of watcher or agent prompts, don't edit
`core/prompts.py`. Write down exactly what happened under **Needs from core**
in `WEB.md`, with the event log (see 5e for how to save one).

---

## 4. Job 2 — the browser

### 4a. Browser-tab sensor: `core/sensors/browser_tab.py` + `extension/`

**Goal:** Argus knows what page the user is reading, so it can say "You've
had the NVIDIA investor page open while drafting earnings-watch.md…"

`extension/`: a Chrome Manifest V3 extension.
- Permissions: `tabs`, `scripting`, `storage`, and host permission
  `<all_urls>` (needed to read the page). Keep it to that.
- **Off by default.** The popup has an on/off toggle, a status line ("sent:
  <title>" or "off"), and an editable domain denylist pre-filled with banking,
  health, mail and password managers (e.g. `mail.google.com`, `*.bank*`,
  `1password.com`, `bitwarden.com`, `chase.com`, `paypal.com`).
- When on: after the active tab has been focused and stable for 3 seconds,
  collect `url`, `title`, the user's current text selection, and the first
  ~2,000 characters of visible text (`document.body.innerText`, whitespace
  collapsed). Never read form fields. Skip incognito windows, `chrome://`
  pages and denylisted domains. Send at most once per URL change, as
  `POST http://localhost:7600/sense/browser_tab` with JSON
  `{url, title, selection, text, ts}`. If the core isn't running, fail
  silently and retry on the next tab change.
- `extension/README.md`: how to load it unpacked (`chrome://extensions` →
  Developer mode → Load unpacked).

`core/sensors/browser_tab.py`:
- `receive(payload)`: validate (`url` is http/https, `title` is a string,
  truncate `text` to 4,000 and `selection` to 1,000), store the latest, and
  return True. Reject anything else and return False.
- `poll()`: when a new page arrived, emit one `activity`: `source: "browser"`,
  `app: "Browser"`, the `title`, the `url`, and as `lines` the selection (tone
  `hl`) then the first ~6 non-empty lines of text. `focus: true`.
- `context()`: `User is reading: <title> (<url>)`, then the selection, then
  ~600 characters of text.
- `alert()`: always False. Reading a page isn't urgent; the watcher sees it on
  its next look.
- Page text is **data**. Don't add instructions to `context()`, and don't strip
  or "clean" page content into commands.
- Tests in `core/sensors/tests/test_browser_tab.py`: validation, truncation,
  emits once per page, context format, rejects junk.

### 4b. `browse` tool: `core/tools/browse.py`  (the "web bot")

**Goal:** when `fetch_url` returns too little (JS-heavy sites, SPAs), the agent
drives a headless browser to read the page, and the UI shows it browsing.
- Use Playwright (`playwright` in `requirements.txt`; `python -m playwright
  install chromium` in setup docs). Use the async API, headless Chromium,
  one shared browser instance created lazily.
- Parameters: `url` (required), `find` (optional text to look for: return the
  passages around matches), `links` (optional bool: also return up to 20 links
  as `[text](url)`).
- Behaviour: http(s) only. Refuse `localhost`, private and link-local IPs
  (resolve the host first). Navigate with a 15s timeout, wait for
  `networkidle` (cap 5s), then extract text from `main`, `article` or `body`.
  **Read-only**: no clicking, typing, form submission, logins, downloads or
  purchases. Return within 25s total.
- Result: `detail` = readable text (≤ 12,000 chars). `summary` =
  `"<domain> · <N> chars"`. `meta.activity` = a browser activity
  (`app: "Argus · browsing"`, `title`, `url`, first ~6 lines, `focus: true`)
  so the UI shows the page. The agent forwards it automatically.
- If Playwright or Chromium isn't installed, return
  `ok=False, summary="browse needs: pip install playwright && python -m
  playwright install chromium"`. Never crash the registry on import (import
  Playwright inside `run()`).
- `description` (written for the model): use it only when `fetch_url` returned
  little or nothing useful, or the page needs JavaScript.
- Tests: `core/tools/tests/test_browse.py`, covering URL validation and SSRF
  refusal offline, plus one live fetch of `https://example.com` when
  Playwright is installed (skip otherwise).

---

## 5. Job 3 — the UI (`web/`)

You inherit a finished v1. **Keep its design language exactly.** Polish and
extend; don't redesign.

### 5a. Map

| File | What it is |
|---|---|
| `src/App.tsx` | layout: header, tape, left column (Oracles, Tribute), center (orb zone + Chronicle), right (Archive) |
| `src/scene/Panoptes.tsx` | the 3D orb: 100 eyes (react-three-fiber), armillary rings, grid, bloom. Eyes follow the cursor, turn to the watched window, and stare when Argus speaks |
| `src/lib/store.ts` | zustand store; `ingest(event)` is the single reducer for every contract event |
| `src/lib/connection.ts` | live websocket (port 7600), simulated replay engine, accept/dismiss/speak |
| `src/lib/layout.ts` | `frame` (where the orb sits, measured from the DOM) and `gaze` (where the eyes look) |
| `src/lib/types.ts` | contract types, incl. `activity` |
| `src/components/Sight.tsx` | the HUD "sight windows": chart, terminal, editor, browser, files; the beam to the orb |
| `src/components/Chronicle.tsx` | messages, plan, tool rows, inscriptions, composer |
| `src/components/Prophecy.tsx` | the watcher speaking (the hero moment) |
| `src/components/Oracles.tsx`, `Tribute.tsx` | routing HUD and spend vs cap |
| `src/components/Archive.tsx` | workspace tree + document/code viewer |
| `src/components/Tape.tsx` | ticker tape: real event wire in LIVE, illustrative quotes in SIMULATE |
| `src/sim/scenarios.ts` | simulated sessions + the recorded research run (`mock/recorded-research.json`) |
| `src/styles.css` | all styling; tokens at the top |

### 5b. Design rules (non-negotiable)
- Dark only. Palette tokens in `:root`: void, gold, amber, ember, terracotta,
  bone, ash. Fonts: Cinzel (display, tracked caps), Cormorant Garamond (Argus's
  voice, documents), JetBrains Mono (data). Hairline gold borders, corner
  brackets, Greek-key rule in panel headers. Amber means "Argus is doing
  something"; don't use it for decoration.
- Motion 150–450ms ease-out; nothing bounces. Never animate CSS `filter: blur`
  over the WebGL canvas (it tanks frame rate). Keep 60fps at 1920×1080.
- Must look right at 1920×1080 (the video) and at 1280×720 (the in-app preview).
- **Honesty:** LIVE never shows invented data. SIMULATE is always labeled
  (pill + "SIMULATED FEED · ILLUSTRATIVE"). Argus never trades, shows no P&L,
  and market research says "not investment advice".

### 5c. UI work, in order
1. **Live terminal polish.** Your sensor feeds the existing terminal window.
   Make it handle long lines and bursts, keep the newest line visible, and
   flash the error line once when it arrives.
2. **Senses panel.** Show the core's sensors (from `/health` → `sensors`) as
   small indicators, e.g. a row of eye glyphs labeled TERMINAL / BROWSER /
   FILES under the Oracles. Each lights amber for ~2s whenever that source
   emits an `activity`, and stays dim gold when idle.
3. **Keyboard.** When a prophecy is open, Enter = Proceed and Esc = Not now.
   Focus the composer with `/`. Show these as small hints on the buttons.
4. **Session recorder.** Shift+R toggles recording in LIVE mode: keep the raw
   events (with `ts`) from the websocket, and on stop download
   `argus-session.jsonl`. Then
   `python scripts/record_replay.py argus-session.jsonl web/mock/recorded-code.json`
   turns it into a replay. Record the Job 1 acceptance run this way, and add it
   to `scenarios.ts` as **"Code (recorded)"**, `kind: "recorded"`, alongside the
   simulated Code scene. Put it in the Montage in place of the simulated one.
   (`record_replay.py` anonymizes the workspace path from the first `fs.tree`.)
5. **Recording mode for the video.** `?record=1` hides the mouse cursor,
   disables the composer placeholder text, and starts with the eyes idling.
6. Anything else that makes it feel more alive **within** the rules above, at
   your judgment.

### 5d. Don't
Add auth, settings pages, a light theme, a landing page, mobile layouts, or
any model calls from the browser. Don't add new runtime dependencies to `web/`
unless they're clearly worth it, and say why in the PR.

### 5e. Saving an event log for a bug report
Use the recorder from 5c.4, or connect a small websocket client to
`ws://localhost:7600/ws`. The server replays its full history to every new
connection.

---

## 6. Definition of done

- Job 1: `test_terminal_log.py` passes, the acceptance in 3d works end to end
  on a real crash, and the screenshots are in the PR.
- Job 2: `test_browser_tab.py` and `test_browse.py` pass. With the extension
  on, switching tabs shows the page in the browser window within ~4s. The
  agent uses `browse` on a JS-heavy page, and the window shows it browsing.
- Job 3: every item in 5c is done; `npx tsc --noEmit -p .` is clean; no console
  errors; screenshots at 1920×1080 and 1280×720.
- All core test suites still pass (section 1). Worklog updated. Three PRs open.
