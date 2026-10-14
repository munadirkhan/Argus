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
| **Watcher** | Nemotron 3.5 Lightning | 1M context at $0.06/M input. Runs every 20s, holds the whole workspace, costs **$1.62 for an 8-hour day**. |
| **Planner** | Nemotron 3 Ultra 550B | The reasoning moment. Decomposes the request, then synthesises the finding. Used twice per task, never in the hot loop. |
| **Executor** | Nemotron 3 Nano 30B | Fast, cheap, high-volume tool calling. Does the actual work. |

This is not three models for show. The watcher *has* to be cheap because it
never stops; the planner *has* to be strong because it's the moment that makes
the product feel intelligent. The routing is forced by the shape of the problem.

A complete task — observation, two Ultra calls, six tool calls, the artifact —
costs about **$0.05**.

### Model IDs are resolved, not hardcoded

Published sources disagree on the casing of Nemotron IDs, and the tiers live in
different Token Factory regions (Nano and Lightning in `eu-north1`, Super and
Ultra in `us-central1`), so one base URL 404s on half the catalogue.

`core/models.py` queries `/v1/models` in both regions at startup and binds each
tier to the best family actually available, with an explicit fallback chain. If
Ultra is unavailable it degrades to Super rather than crashing.

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

Open `http://localhost:8787/health` to see which models got bound.

**With no API key at all**, the whole stack still runs against a scripted model:

```bash
ARGUS_FAKE=1 python -m core.server
```

### Tests

No API key or network needed for any of these:

```bash
python scripts/test_agent_offline.py      # plan/execute/synthesise, tool dispatch
python scripts/test_watcher_offline.py    # diffing, restraint, cooldown, cost
python scripts/test_server_offline.py     # websocket contract end to end
python scripts/verify_nebius.py           # probes the live API (needs a key)
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

## License

MIT — see [LICENSE](LICENSE).
