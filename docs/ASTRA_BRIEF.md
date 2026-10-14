> **UPDATE 2026-10-14 — READ FIRST.** The core lane has already built **all six tools**
> (`core/tools/`) and is building the **first version of the UI** locally. Do NOT rebuild
> either. Read `docs/worklog/CORE.md` for the current state; your job will be to expand
> and polish the UI once it lands on `main`. Everything below is the original brief, kept
> for the design direction and boundaries.

# Brief for Astra — ARGUS frontend

You own two things in a hackathon project called ARGUS: the **entire frontend**,
and the **tools layer** the agent uses to touch the real world.
Read this whole brief before writing code.

## Hard boundaries (do not violate)

You may create and edit files in exactly these places:

- `web/` — everything. The whole frontend is yours.
- `core/tools/` — every file **except** `base.py` and `registry.py`, which
  another agent owns. Add new tool files freely; never edit those two.
- `docs/worklog/WEB.md` — append your entries here.

Never touch anything else. Another agent owns `core/` (agent loop, router,
watcher, companion, server) and all of `docs/` except your worklog. Editing
outside your lane is what causes merge conflicts.

- Work on branch **`feat/web`**. Never commit to `main`.
- `docs/EVENT_CONTRACT.md` and `docs/TOOL_CONTRACT.md` are **frozen**. Build
  against them exactly. If one needs a change, say so in the PR description —
  do not edit the file.

## Worklog — read and write this every session

Before you start: read `docs/worklog/CORE.md` to see what the other lane did.
Before you open a PR: append an entry to `docs/worklog/WEB.md`.

Format and rules are in `docs/worklog/README.md`. Four lines, newest at top,
append only, and never edit `CORE.md`. This is the only way the two lanes stay
in sync — neither agent can see the other's session.

## What ARGUS is

An always-on AI agent that lives on your computer. It watches what you're
working on and *proactively* offers to help — then does real work: searches the
live web, reads your actual local files, reasons over them, and writes a
finished document back to your disk.

The emotional target is **Jarvis**. It notices you're building something and
says "Working on something secret, sir?" — then goes and does the research.

The name is from Argus Panoptes, the hundred-eyed giant of Greek myth who
never slept — the all-seeing watchman. Let that inform the design: this is
something that is always quietly watching and occasionally speaks. Calm and
attentive, not busy or chattery. It should feel like it was awake the whole
time, not like it just woke up when you typed.

It runs on NVIDIA Nemotron models via Nebius Token Factory, in three tiers:
- **Watcher** — Nemotron 3.5 Lightning. Always on, cheap, huge context.
- **Planner** — Nemotron 3 Ultra 550B. Rare, expensive, the reasoning moment.
- **Executor** — Nemotron 3 Nano 30B. Fast, high-volume tool calls.

**Showing this routing on screen is a judged criterion.** It is not decoration.

## Stack (use exactly this — do not substitute)

- Next.js 15 (App Router) + TypeScript
- Tailwind CSS v4
- Framer Motion for animation
- `zustand` for state
- No component library. Hand-build it. No shadcn, no MUI.

## Build against the mock first

`web/mock/events.json` is a recorded 18-second demo session — the exact
narrative we'll film. Each event has `t_offset_ms` from stream start.

Build a replay harness (`web/lib/mockSocket.ts`) that emits these events on
their original timing and exposes the same interface the real websocket will.
A toggle switches between mock and live. **The entire UI must be buildable and
beautiful with zero backend running.** That is the point — you are not blocked.

## Screens

One screen. No navigation, no routing, no settings page, no login.

```
┌──────────────────────────────────────────────┬──────────────────┐
│                                              │  ROUTING HUD     │
│   CONVERSATION                               │  ┌────────────┐  │
│   - watcher observations (distinct, glowing) │  │ watcher    │  │
│   - user + assistant messages                │  │ planner  ● │  │
│   - plan with live step states               │  │ executor   │  │
│   - tool calls (collapsed, expandable)       │  └────────────┘  │
│                                              │  tokens · $cost  │
│                                              ├──────────────────┤
│                                              │  FILE TREE       │
│                                              │  + artifact      │
│                                              │    preview       │
└──────────────────────────────────────────────┴──────────────────┘
```

### Component list
- `ObservationCard` — the Jarvis moment. Must feel like the app *spoke first*.
  Visually distinct from chat. Accept / dismiss. This is the hero element.
- `MessageList` + `Message` — supports token streaming.
- `PlanTimeline` — steps with pending/running/done/failed. Animate transitions.
- `ToolCallRow` — collapsed one-liner, expands to args + result.
- `RoutingHUD` — three tiers; the active one lights up on `agent.thinking`.
  Show model name and live token counts.
- `CostMeter` — cumulative spend from `usage` events. Ticks up visibly.
- `FileTree` — from `fs.tree`.
- `ArtifactPreview` — renders `artifact.write` markdown. Should feel like a
  real document landing on disk.
- `RuntimeBadge` — "Local · Ryan's PC" vs "Sandbox". From `session.state`.

## Art direction

Dark, cinematic, restrained. Reference points: Linear, Arc, Vercel dashboards.
**Not** a generic AI chatbot — no bubbles, no bouncing-dots spinner, no purple
gradient on everything.

- Near-black base (`#08090A`-ish), layered surfaces, hairline borders
- One cold accent (electric cyan or ice blue). Use it sparsely — it should mean
  "the agent is doing something", not "this is a button"
- Typography: Inter or Geist. Tight tracking on headings. Real hierarchy.
- Motion: 150–250ms, ease-out. Things fade and settle; nothing bounces or
  springs. The watcher observation is the one place a slightly bigger,
  slower entrance is justified — it should feel like it *arrived*.
- Must look right at 1920×1080 — that's what gets screen-recorded.

Judging criterion: *"a complete, coherent product experience, not just a
technical proof of concept."* Polish is literally scored. Empty states,
loading states, and the moment before the agent speaks all matter.

## Definition of done

1. `npm run dev` renders the full mock session start to finish, unattended,
   and it looks good enough to film with no edits.
2. Every event type in the contract is handled and rendered.
3. Live/mock toggle in place, pointed at `ws://localhost:8787/ws` for live.
4. No console errors. Responsive down to 1280px (ignore mobile entirely).
5. PR from `feat/web` → `main` with 2–4 screenshots in the description.

---

# Part 2 — the tools layer (`core/tools/`)

Python. This is what gives the agent real-world reach: live web search, reading
files off the user's actual disk, writing documents back. The agent loop calls
these; you implement them.

**Read `docs/TOOL_CONTRACT.md` first.** It is frozen and it is precise: one tool
per file, subclass `Tool` from `core/tools/base.py`, export as `TOOL`, return a
`ToolResult`, never raise. The registry auto-discovers your files — you do not
register anything by hand.

Build these six:

| name | notes |
|---|---|
| `tavily_search` | Tavily API. **This is a $3,000 prize category — make it genuinely good, not a thin wrapper.** Handle rate limits, dedupe results, return clean citations in `meta`. |
| `fetch_url` | Fetch a page, strip nav/ads/scripts, return readable text. |
| `read_file` | Read local files. **Must handle PDFs** (`.pdf` → extracted text) — the demo reads two PDFs off disk. |
| `write_file` | `dangerous = True`. Create parent dirs. Return bytes written. |
| `list_dir` | Cap depth, skip `node_modules`/`.git`/`.venv`. |
| `shell` | `dangerous = True`. 20s timeout, capture stdout+stderr together. |

Verify your work with `python -m core.tools.registry` — it prints every tool it
discovered. If yours isn't listed, it won't load for the agent either.

Each tool gets its own test in `core/tools/tests/` proving it works against the
real API or filesystem. These are the only tests in the project; they matter
because the agent loop assumes tools are reliable.

## Do not build

Auth. Settings. Dark/light toggle (dark only). Mobile layout. Onboarding.
A landing page. Frontend tests. The agent loop, the model router, the watcher,
the websocket server, or any call to an LLM — all of that belongs to the other
lane. If you find yourself calling Nemotron, you are out of scope.
