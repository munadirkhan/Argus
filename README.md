# ARGUS

An always-on AI agent that lives on your computer, notices what you're working
on, and does real research work about it without being asked.

Argus Panoptes was the hundred-eyed giant who never slept. This is the same idea
with a cost ceiling.

Built for the Nebius x NVIDIA Global AI Hackathon on **NVIDIA Nemotron** models
served through **Nebius Token Factory**.

---

## What it actually does

It watches your workspace. When something concrete changes — you pull two papers
into a folder and open an empty notes file — it decides whether a competent
colleague would say something. Almost always the answer is no, and it stays
quiet. When the answer is yes, it speaks first:

> *"You pulled two papers into refs/ and opened an empty notes.md. Want me to
> pull the current literature and draft that summary?"*

Say yes and it searches the live web, reads the PDFs off your actual disk,
reasons over both, and writes a finished document back to your filesystem — then
tells you the one thing you didn't want to hear:

> *"Written to notes.md. The June result your local paper builds on was
> superseded in August, so I'd check that before you go further."*

## Three Nemotron models, because the product requires it

| Stage | Model | Why this one |
|---|---|---|
| **Watcher** | Nemotron 3.5 Lightning | 1M context at $0.06/M input. Looks every 20s, but only calls the model when something changed. A look is ~1,000 tokens ($0.00007), so even a change every 20s for an **8-hour day is about $0.10**. |
| **Planner** | Nemotron 3 Ultra 550B | The reasoning moment. Decomposes the request, then synthesises the finding. Used twice per task, never in the hot loop. |
| **Executor** | Nemotron 3 Nano 30B | Fast, cheap, high-volume tool calling. Does the actual work. |

This is not three models for show. The watcher *has* to be cheap because it
never stops; the planner *has* to be strong because it's the moment that makes
the product feel intelligent. The routing is forced by the shape of the problem.

A complete task — observation, two Ultra calls, six tool calls, the artifact —
costs about **$0.05**.

### Reasoning is switched per tier — measured, not guessed

Every Nemotron 3 model reasons by default. That's exactly what you want from the
planner and exactly what you don't want in an always-on loop. We probed all four
models live (`scripts/probe_reasoning.py`) on the watcher's real JSON task:

| Model | Thinking on (default) | Thinking off |
|---|---|---|
| Lightning | **broken** — reasoning spills into the answer, invalid JSON, 600 tokens, 2.8s | valid JSON, **25 tokens, 0.8s** |
| Nano | valid, 199 tokens, 2.0s | valid, 27 tokens, 0.7s |
| Ultra | valid, reasoning kept in a separate field, 156 tokens | valid, 22 tokens, 0.3s |

So ARGUS sends `chat_template_kwargs: {enable_thinking: false}` to the watcher
and executor, and lets Ultra think. Deep reasoning where it pays; none on the
hot path.

### Model IDs are resolved, not hardcoded

The live catalogue doesn't match the published IDs: Nebius's own cookbook says
`nvidia/nvidia-nemotron-3-nano-30b-a3b`, the API serves
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. `core/models.py` queries `/v1/models`
at startup and binds each tier to the best family actually available,
case-insensitively, with an explicit fallback chain. If Ultra is unavailable it
degrades to Super rather than crashing.

### Measured live

| | |
|---|---|
| Watcher decision (Lightning) | **0.8s**, spoke 3/3 on the demo scenario, stayed quiet on routine edits |
| Full plan → execute → synthesise | **~2s, ~$0.001** |
| Always-on watcher, 8-hour day | **~$0.10** worst case (a change every 20s); $0 while nothing changes |

### It can't spend your money by accident

Token Factory bills your card once the account balance is used up and has no
server-side spending cap, so ARGUS enforces one. Every model call is refused
*before it is sent* once spend reaches `ARGUS_BUDGET_USD` (default $10). The
ledger is persisted atomically, so restarts don't reset it, and a corrupt ledger
fails closed. This matters because Argus acts on its own, all day, on a real key.

### It only answers to you

Argus can run shell commands and read your workspace, so the core is locked to
this machine and this hub:

- It listens on `127.0.0.1` only. Nothing else on your Wi-Fi can reach it.
- Every request — WebSockets included, which browsers don't protect with CORS —
  must come from the hub itself (Vite on localhost, or the desktop app's own
  `argus://app` origin) or the browser-tab extension. A web page you happen to
  visit can't drive it, read files through it, or plant attachments.
- The `Host` header must be loopback, which defeats DNS-rebinding tricks.
- Keys live only in `.env`, which git ignores. The public demo page is a
  replay: it never contacts a core, so it holds no key and can't spend one.

`python scripts/test_security_offline.py` attacks all of this and checks the
core is unreachable from your LAN address.

## Architecture

```
  Desktop app (Electron)            Browser extension
  ├─ hub: the full interface        └─ the tab you're reading
  └─ floating orb, tray, hotkeys            │
            │ websocket, one frozen event   │ POST /sense
            │ contract, 127.0.0.1 only      │
            └──────────────┬────────────────┘
                     Core (Python, your machine)
                     watcher · agent · tools · local Whisper
                           │ HTTPS
                     Nemotron on Nebius Token Factory · Tavily
```

| Module | Does |
|---|---|
| `core/models.py` | Tier resolution, per-region clients, cost accounting |
| `core/agent.py` | plan → execute → synthesise |
| `core/watcher.py` | Workspace diffing, deciding whether to speak |
| `core/server.py` | FastAPI websocket serving the event contract |
| `core/tools/` | The agent's reach: search, files, shell |
| `docs/EVENT_CONTRACT.md` | Frozen UI ↔ backend interface |
| `docs/TOOL_CONTRACT.md` | Frozen agent ↔ tools interface |

## Running it

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                 # add NEBIUS_API_KEY
python -m core.server
```

Open `http://localhost:7600/health` to see which models got bound.

**No key yet?** The desktop app opens anyway and plays a simulated session, with
**ADD KEY** (opens `.env` for you) and **GO LIVE** buttons.

**With no API key at all**, the whole stack still runs against a scripted model:

```bash
ARGUS_FAKE=1 python -m core.server
```

### On the desktop (the way to use it)

Windows: double-click **`Argus.cmd`**. Or `cd desktop && npm install && npm run build:web && npm start`.

Argus becomes a desktop app: the hub in its own window, and a **floating orb**
— the hundred-eyed sphere — that stays on top of whatever you're doing whenever
the hub isn't in front. Click the orb to open the hub. When Argus notices
something while you're in a browser or a video, a card slides out beside the
orb with the offer, and **Proceed** runs it without switching apps. Close the
hub and Argus keeps watching from the tray.

| Hotkey (from any app) | |
|---|---|
| `Ctrl+Alt+A` | show / hide the hub |
| `Ctrl+Alt+Space` | talk to Argus: press, speak, press again to send |

If another app owns a key, Argus takes the next free one and shows it in the tray.

Details: [`desktop/README.md`](desktop/README.md).

### Talking, attaching, showing it things

- **Voice** is transcribed **on this machine** with faster-whisper (Token Factory
  has no speech model, and your voice shouldn't leave your computer anyway). A
  spoken command transcribes in under a second on CPU. Push-to-talk only.
- **Attach anything**: the `+` menu, drag-and-drop onto the hub, or Ctrl+V for
  screenshots. Attached files are copied into `<workspace>/.argus/attachments/`,
  so Argus reads them with its normal workspace-confined tools — handing it a
  file never widens what it can reach. `@` references a workspace file in place.
- **Images** are read by **Nemotron 3.5 Super VL** on Token Factory: paste a
  screenshot of an error and Argus reads the stack trace off it. Vision calls go
  through the same spend cap as everything else.

### The interface in a browser

```bash
cd web && npm install && npm run dev      # http://localhost:5173
```

**LIVE** connects to the core on port 7600. **SIMULATE** plays labelled
sessions (markets, code) and a recording of a real research run, for when you
want to see the whole thing without spending tokens. Simulated sessions use
illustrative data; LIVE never does.

The public demo page is this interface built with `VITE_ARGUS_HOSTED=1`: replay
only, LIVE switched off, and it never contacts localhost.

To watch Argus notice something for real, point the core at a scratch folder
and drop the demo notes into it:

```bash
python scripts/seed_demo.py --reset      # then start the core with ARGUS_WATCH_ROOT at ../mark-ii
python scripts/seed_demo.py --drop       # Argus speaks within one watch interval
```

### Hands on the web: Argus's own browser

Argus has a browser of its own: a real, visible Chrome window with its own
profile (`~/.argus/browser`). It can open pages, click, type, pick options and
upload files, so it can fill in an application, work in an account or do any
multi-step job on a site. You can watch it and take over at any moment.

- **Sign-ins are yours.** When a site needs an account, Argus opens the sign-in
  page and hands you the window (a **YOUR TURN** card). You sign in, press
  **DONE**, and the profile stays signed in for next time. Argus never sees or
  types a password, one-time code, card, bank or ID number. Those fields are
  refused in code, not just in the prompt.
- **Nothing final without you.** Submit, apply, pay, post, delete, agree,
  upload: each one stops at an **ARGUS ASKS** card in the hub (and beside the
  orb, wherever you are) showing exactly what was filled in. No answer within
  five minutes means no.
- **Public internet only**, through the same DNS-pinning proxy as `browse`. A
  page can't point it at your router, your LAN or the Argus core.
- **For job applications**, put your details in `about-me.md` and your resume
  in the workspace. Argus fills forms from those and never invents answers;
  if something required is missing, it stops and asks.

### Your whole PC (optional)

Tick **Full PC access** in the tray (or set `ARGUS_FS_SCOPE=full`). The file
tools can then reach every drive: read anything, `find_files` across your home
folder ("find my resume"), and `open_path` to open a file or folder on screen.
Writing outside the watched folder asks first, and so does running a program.
SSH and cloud keys, browser profiles, Windows credential stores, `.env` files
and password vaults are refused in both modes.

### Look at my screen

Press **Ctrl+Alt+S** anywhere (or **Look at my screen** in the tray) and Argus
takes a snapshot of whatever screen your mouse is on, reads it with its vision
model, and answers what you're looking at -- a multiple-choice question, an
error, code, a form, something to decide. The answer slides out beside the orb
(and is spoken), you can copy it, and it joins the chat so "explain that" works
as a follow-up. One look, one vision call, no browsing -- the answer lands in
a few seconds. The orb removes itself from the shot first, so it's never in the
picture. (Not Ctrl+S: that's Save everywhere, and a global key would steal it.)

### The Sanctum (settings)

**SANCTUM** in the header (or **Ctrl+,**) opens every setting, applied as you
change it, with no restart and no editing files:

- **Appearance:** six colour themes (Panoptes, Arc Reactor, Hades, Olympus, Nyx,
  Gorgon) that repaint the panels, the hundred eyes and the floating orb together.
- **Voice:** on/off, which voice, speed, live preview.
- **Persona:** what Argus calls you; casual, butler or formal; short or detailed replies.
- **Minds:** any model on your Nebius account for each role (watcher, oracle,
  hands), priced live from the catalogue so the spending limit stays exact;
  thinking on/off per role. Unpriced models are refused.
- **Tribute:** the spending limit, with what's spent so far.
- **Watcher:** on/off, how often it looks, how long it stays quiet; the watched folder.
- **Reach:** full PC access, the floating orb, start with Windows.
- **Memory / Skills / Routines:** read, edit, add, delete, run now.

Settings live in `~/.argus/settings.json`, which no agent tool can write.

### Stop, any time

While Argus works, **INVOKE** becomes **STOP** (or press **Esc**); the orb's
"at work" card has one too. Stopping cancels the run wherever it is: mid
model call, mid browser action, or waiting on an approval card (which is
withdrawn). It also silences the voice, and Argus is ready for the next request
at once.

### Its voice

Argus speaks its replies, what it notices, and its questions for you. Speech
is generated **on this machine**: Nebius Token Factory has no speech models,
and cloud voices bill per character. With Kokoro installed it uses a British
male voice (`bm_george` by default; also `bm_lewis`, `bm_daniel`, `bm_fable`).
It's a Jarvis-style butler voice, not a copy of any actor. Without Kokoro it
falls back to Windows' built-in voice.

```bash
python scripts/setup_voice.py        # one time: kokoro-onnx + ~120 MB of model files
```

Mute it with **VOICE** in the header or **Speak replies** in the tray.
Starting to talk, sending a message or pressing stop cuts it off.

### Skills and routines

**Skills** are saved how-tos for jobs you hand Argus again and again, one
markdown file each in `~/.argus/skills`. It starts with *Apply to a job* and
*Morning briefing*. Teach it more in chat ("from now on, when I need a cover
letter, keep it to three paragraphs...") or edit the files. When a request
fits a skill, the steps doing the work follow it.

**Routines** are things Argus does on its own at set times (`~/.argus/routines.json`).
Out of the box: a spoken **morning briefing** on weekdays at 8:00, covering weather,
news that matters to you, and your job search. If the PC was asleep it catches up
within three hours. Change them in chat ("move my briefing to 7:30", "every
Friday at 5 sum up my week"), or use **Morning briefing now** in the tray.

**Steps only get the powers your request needs.** Every step may read and search.
Writing files, opening things on screen, using the browser or running commands
only happens when the planner, which sees nothing but your request, grants
it for that step. Text in a file or on a page ("download this", "open that")
can't hand a step new powers.

No tool can rewrite `~/.argus` (memory, skills, routines, browser profile).
Only you can, in chat or by editing the files, so a web page can't plant
instructions for later.

### It remembers you, and talks like you

Argus keeps a short file of facts about you (`~/.argus/memory.md`): your name,
what you're after, how you like things done. It adds a line when you tell it
something worth keeping, removes one when you ask it to forget, and never
stores passwords, codes, card or ID numbers. Open and edit the file whenever
you like. Questions about Argus itself, chat, and "do that" follow-ups are
answered directly from the conversation so far, not turned into a web
research job. It reads casual, typo-heavy, voice-to-text messages for what
you mean, and answers the same way.

### Sensors

Beyond the filesystem, Argus sees through sensors in `core/sensors/`, one file
each (contract: `docs/SENSOR_CONTRACT.md`). A sensor reports what the user's
apps show; the watcher reads it on every look, and an urgent event (a crash in
the dev server) wakes it immediately. Browser extensions push to
`POST /sense/<name>`.

### Tests

No API key or network needed for any of these:

```bash
python scripts/test_agent_offline.py      # plan/execute/synthesise, tool dispatch
python scripts/test_watcher_offline.py    # diffing, restraint, cooldown, cost
python scripts/test_server_offline.py     # websocket contract end to end
python scripts/test_budget_offline.py     # the spend cap holds
python scripts/test_writer_offline.py     # documents and code fixes land as one file
python scripts/test_sensors_offline.py    # sensor socket: forwarding, alerts, gating
python scripts/test_attach_voice_offline.py  # attachments can't escape; real speech → text, locally
python scripts/test_security_offline.py  # web pages and the LAN can't drive the core
python scripts/test_personal_offline.py  # full-PC access limits, memory, direct answers
python scripts/test_stop_offline.py      # stop cuts a run off mid-call, mid-approval
python scripts/test_routines_offline.py  # schedules, the briefing, skills taught in chat
python scripts/test_injection_offline.py # a document can't make a step act beyond what you asked
python scripts/test_settings_offline.py  # the Sanctum: validated, saved, applied live
python scripts/test_snap_offline.py      # look at my screen: one vision call, one answer
python core/tools/tests/test_web_hands.py # Argus's browser on a real form: refusals, approvals
cd desktop && npm test                    # the desktop app end to end (orb, card, voice, attach, no-key start)

python scripts/verify_nebius.py           # live: models, tool calling (needs a key)
python scripts/probe_reasoning.py         # live: thinking on/off per model
python scripts/live_smoke.py              # live: watcher + full agent loop
```

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NEBIUS_API_KEY` | — | Token Factory key |
| `TAVILY_API_KEY` | — | Web search |
| `ARGUS_WATCH_ROOT` | cwd | Directory the watcher observes |
| `ARGUS_WATCH_INTERVAL` | 20 | Seconds between scans |
| `ARGUS_WATCH_COOLDOWN` | 120 | Minimum seconds between interruptions |
| `ARGUS_FAKE` | — | `1` to run with the scripted model |
| `ARGUS_BUDGET_USD` | 10 | Hard spend cap, enforced before every call |
| `ARGUS_SPEND_FILE` | `.argus_spend.json` | Persistent spend ledger |
| `ARGUS_STT_MODEL` | `base.en` | Local Whisper model for voice (`tiny.en` faster, `small.en` more accurate) |
| `ARGUS_HOST` | `127.0.0.1` | Interface the core listens on. Change only on a network you trust |
| `ARGUS_ALLOWED_ORIGINS` | — | Extra comma-separated origins allowed to talk to the core |
| `ARGUS_FS_SCOPE` | `workspace` | `full` lets the file tools reach the whole PC (secrets stay off-limits) |
| `ARGUS_MEMORY_FILE` | `~/.argus/memory.md` | What Argus remembers about you |
| `ARGUS_VOICE` | `bm_george` | Kokoro voice for Argus's speech |
| `ARGUS_VOICE_SPEED` | `1.0` | Speaking rate |
| `ARGUS_BROWSER_PROFILE` | `~/.argus/browser` | Argus's own browser profile (your sign-ins) |
| `ARGUS_BROWSER_CHANNEL` | chrome → msedge → chromium | Which browser Argus drives |

## License

MIT — see [LICENSE](LICENSE).
