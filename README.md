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
fails closed. This matters most for the hosted demo, which runs on a real key.

## Architecture

```
  Web UI (Next.js)
  ├─ conversation + proactive observations
  ├─ routing HUD        ← live: which Nemotron, tokens, cost
  └─ artifact viewer
            │ websocket, one frozen event contract
      ┌─────┴─────┐
   Sandbox      Local companion
   (hosted)     (your real files)
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

**With no API key at all**, the whole stack still runs against a scripted model:

```bash
ARGUS_FAKE=1 python -m core.server
```

### The interface

```bash
cd web && npm install && npm run dev      # http://localhost:5173
```

**LIVE** connects to the core on port 7600. **SIMULATE** plays labelled
sessions (markets, code) and a recording of a real research run, for when you
want to see the whole thing without spending tokens. Simulated sessions use
illustrative data; LIVE never does.

To watch Argus notice something for real, point the core at a scratch folder
and drop the demo notes into it:

```bash
python scripts/seed_demo.py --reset      # then start the core with ARGUS_WATCH_ROOT at ../mark-ii
python scripts/seed_demo.py --drop       # Argus speaks within one watch interval
```

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

## License

MIT — see [LICENSE](LICENSE).
