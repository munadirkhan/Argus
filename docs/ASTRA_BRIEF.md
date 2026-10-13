# Brief for Astra — AURA frontend

You are building the **entire frontend** for a hackathon project called AURA.
Read this whole brief before writing code.

## Hard boundaries (do not violate)

- You work **only inside `web/`**. Never create or edit files outside `web/`.
  Another agent owns `core/` and `docs/`. Touching them causes merge conflicts.
- Work on branch **`feat/web`**. Never commit to `main`.
- `docs/EVENT_CONTRACT.md` is **frozen**. Build against it exactly. If you think
  it needs a change, say so in the PR description — do not edit the file.

## What AURA is

An always-on AI agent that lives on your computer. It watches what you're
working on and *proactively* offers to help — then does real work: searches the
live web, reads your actual local files, reasons over them, and writes a
finished document back to your disk.

The emotional target is **Jarvis**. It notices you're building something and
says "Working on something secret, sir?" — then goes and does the research.

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

## Do not build

Auth. Settings. Dark/light toggle (dark only). Mobile layout. Onboarding.
A landing page. Tests. Any backend, API route, or model call — if you find
yourself writing a fetch to an LLM, you are out of scope.
