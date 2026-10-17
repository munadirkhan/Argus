# Devpost submission — working draft

Paste-ready. Character limits noted. Nothing here claims anything we have not
actually run; every number came from a real run on this machine.

---

## Step 1 — Project overview

**Project name** (60 char limit — 5 used)

```
Argus
```

**Elevator pitch** (200 char limit — 188 used)

```
An always-on agent that watches your real work, speaks up before you ask, then researches and writes the answer to your disk. Three NVIDIA Nemotron models on Nebius. About $0.10 a workday.
```

Alternates, if you want a different angle:

- *(169)* `Argus notices what you're working on and offers to help before you ask — then does the research and writes it to your disk. Three Nemotron tiers on Nebius Token Factory.`
- *(176)* `The hundred-eyed watchman, as software. Argus watches your files, terminal and browser, speaks when it can genuinely help, and does real work. Nemotron on Nebius, ~$0.10 a day.`

**Thumbnail** (3:2, max 5MB): crop a 1920×1080 screenshot of the orb with a
prophecy card open to 3:2 — `web/evidence/terminal/terminal-prophecy-1920.png`
is the strongest frame we have.

---

## Step 2 — Project details

### Inspiration

Assistants wait to be asked. That is the whole problem. By the time you have
written out what you want, you have already done the thinking that was the
hard part.

We wanted the opposite: something that is already watching, already has the
context, and speaks first — but only when it genuinely has something worth
saying. The myth gave us the name. Argus Panoptes was the hundred-eyed giant
who never slept, set to watch and never blink.

### What it does

Argus runs on your machine and watches what you are actually doing — the files
in your project, the output of your dev server, the page you are reading. Most
of the time it stays quiet. That restraint is the feature; an assistant that
interrupts constantly gets turned off.

When something concrete changes, a cheap model decides whether a competent
colleague would say something. If yes, Argus speaks first:

> *"You pulled two papers into refs/ and opened an empty notes.md. Want me to
> extract the key points into notes.md?"*

Say yes and it searches the live web, reads the PDFs off your disk, reasons over
both, and writes a finished document back to your filesystem — then tells you
the thing you did not want to hear:

> *"Your Dec 2025 notes are outdated: all four Nemotron 3 models are live on
> Token Factory today, not just Nano."*

It does the same for code. When our dev server threw a real `TypeError`, Argus
noticed in **1.15 seconds**, named `watchlist.js:24`, and on one click read the
file, wrote the fix, and the server restarted clean.

### How we built it

**Three Nemotron models, because the product forces it.** This is not model
roulette — each tier exists for a reason we can defend:

| Stage | Model | Why this one |
|---|---|---|
| **Watcher** | Nemotron 3.5 Lightning | Runs constantly. 1M context at $0.06/M input. A look costs **$0.00007**, so always-on is actually affordable. |
| **Oracle** | Nemotron 3 Ultra 550B | The reasoning moment: plans the work, then writes the final document or code fix. |
| **Hands** | Nemotron 3 Nano 30B | Fast, cheap, high-volume tool calling. |

**We measured reasoning instead of guessing.** All Nemotron 3 models reason by
default. We probed all four on the watcher's real JSON task
(`scripts/probe_reasoning.py`) and found Lightning *breaks* with thinking on —
its reasoning spills into the answer, producing invalid JSON in 600 tokens and
2.8s. With `chat_template_kwargs: {enable_thinking: false}` it returns valid
JSON in **25 tokens and 0.8s**. So Argus switches reasoning per tier: on for
the Oracle, off on the hot path.

**Model IDs are resolved, not hardcoded.** The live catalogue disagrees with
the published docs on casing — Nebius's own cookbook says
`nvidia/nvidia-nemotron-3-nano-30b-a3b`, the API serves
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. Argus queries `/v1/models` at startup,
binds each tier case-insensitively, and falls back down a chain, so an
unavailable Ultra degrades to Super instead of crashing.

**Argus knows what it is running on.** An early version confidently told us
Nemotron 3 Ultra was unavailable — while Ultra was writing the sentence. Now
the live Token Factory catalogue is injected as first-hand fact that outranks
any web page, and it correctly flags stale user notes instead.

**Two plug-in sockets, so it grows without surgery.** Tools
(`core/tools/`) and sensors (`core/sensors/`) are each one file per capability,
auto-discovered by a registry against a frozen contract. We built the sensor
socket on one side of the repo while the terminal and browser sensors were
written on the other; they dropped in and `/health` picked up both with **zero
changes to core code**.

**It cannot run away with your money.** Token Factory bills your card once the
balance is gone and offers no server-side cap, so the cap lives in the router:
every call is refused *before it is sent* once spend reaches `ARGUS_BUDGET_USD`.
The ledger is persisted atomically, survives restarts, and a corrupt ledger
fails closed.

**Safety we actually implemented, not just intended.** File tools are confined
to the workspace (`..`, absolute paths, other drives and symlinks out are all
refused, with tests). The headless browser is read-only behind a public-IP-only
proxy that re-validates every request, so redirects cannot reach your LAN. The
browser extension is off by default, ships a sensitive-domain denylist, and
strips form fields from both the selection and the page text.

### Challenges we ran into

- **Making it shut up.** The first watcher offered to help constantly. The fix
  was mostly prompt work plus cooldowns, and one structural insight: after
  Argus finishes a task it re-baselines, so it never comments on its own writes.
- **The writer kept drifting.** Asked to produce a document *and* call a tool,
  Ultra would sometimes skip the save, or "improve" its way into three extra
  files. We made writing deterministic: the model returns the document, the
  code saves it. One file, every time.
- **An agent that reads the web will confidently tell you things do not exist.**
  Absence of evidence kept becoming evidence of absence. Fixed with an explicit
  rule and first-hand platform facts.
- **Enforcing limits in prompts does not work.** "Use at most two searches" was
  ignored; the cap now lives in code, by removing the search tool after two uses.

### Accomplishments we're proud of

- The watcher spoke correctly on **3 of 3** runs for the research scenario and
  stayed quiet on routine edits.
- A real crash-to-fix cycle, end to end, in a real project: detection in 1.15s.
- **$0.26** of real spend built the entire project. A full task costs about
  $0.001–$0.05; a worst-case 8-hour day of watching is about **$0.10**.
- 12 test suites, including the unglamorous cases: a tool that raises, bad
  arguments, non-JSON model output, corrupt spend ledgers, and SSRF attempts.

### What we learned

Most of the quality is in restraint and in deciding what *not* to hand the
model. The three-tier split was forced by economics, and ended up being the
cleanest part of the design. And verifying a model's behaviour beats trusting
its documentation — the reasoning-toggle measurement changed the architecture.

### What's next

Sandboxed cloud sessions so Argus can work while the laptop is shut; a memory
of what you have already been told so it never repeats itself; and more
sensors — the socket is the whole point.

### Built with

```
nvidia-nemotron, nebius-token-factory, nemotron-3-ultra, nemotron-3-nano,
nemotron-3.5-lightning, tavily, python, fastapi, websockets, asyncio,
playwright, pypdf, react, typescript, three.js, react-three-fiber, vite,
zustand, framer-motion, chrome-extension
```

---

## Step 3 — Additional info

**Track:** see the note below — this needs a decision.

**Feedback on Nebius / NVIDIA tooling** (there is a $100 "Most Valuable
Feedback" prize and almost nobody fills this in properly — this is worth real
effort):

1. **The live catalogue disagrees with the docs on model ID casing.** The
   cookbook shows `nvidia/nvidia-nemotron-3-nano-30b-a3b`; `/v1/models` serves
   `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. A hardcoded ID from the docs 404s.
2. **Reasoning defaults are a trap for always-on workloads.** Nemotron 3.5
   Lightning with thinking on produced invalid JSON in 600 tokens and 2.8s on a
   task it handles in 25 tokens and 0.8s with thinking off. The
   `chat_template_kwargs: {enable_thinking: false}` switch is not discoverable
   from the model card, and `response_format: json_object` does not imply it.
3. **There is no spending cap.** Billing docs confirm the card is charged once
   the balance is used up, and the only lever is manual top-up. For agent
   workloads — which loop — a hard per-project cap would remove the single
   scariest thing about building on the platform. We had to build our own.
4. **Regional availability is hard to discover.** Published sources suggested
   models were split across `eu-north1` and `us-central1`; in practice all four
   Nemotron models served from `us-central1`. A per-model region field in the
   catalogue response would settle it.
5. **What worked well:** the OpenAI-compatible endpoint meant the agent loop
   worked unchanged, and native tool calling was reliable on all four Nemotron
   models — we tested every one before building on it.

---

## Decisions still open

### 1. Which track

The project now matches **Personal AI** almost word for word: always-on, local,
private, persistent, reusable skills (tools + sensors), carrying out tasks
across daily workflows. We originally picked **Best Apps and Agents** for its
explicit Ultra/Nano tiering language — which we also do.

Pick one. Our read: **Personal AI** is the stronger fit now that the sensors
exist, and our build is visibly not the "installed NemoClaw and put a UI on it"
submission that track will be full of.

### 2. The demo URL

The rules require a URL to a working demo. Argus is local-first, and judges
will not install a daemon. The fix: **deploy the web UI in SIMULATE mode** —
it is a static Vite build with no backend, and it plays the recorded real
sessions. Judges click, see the whole thing, and the README explains how to run
it live. `npm run build` already passes.

### 3. Before submitting

- [ ] 3-minute YouTube video (public, unlisted is not enough)
- [ ] Thumbnail cropped to 3:2
- [ ] Deploy the SIMULATE-mode UI, put the link in "Try it out"
- [ ] Repo link — already public with MIT at root
- [ ] **Submit Oct 29, not the 30th.** 24,000+ participants hit Devpost at once.
- [ ] After submitting: delete the Nebius API keys, then remove the card
