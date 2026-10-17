# Devpost — Additional info (step 3)

Paste-ready. Four fields marked **YOU** need facts only you have.
Ratings are drafted from what we actually measured; change any number you
disagree with, but keep the specifics — they are what make the answer credible.

---

**Upload a file** — optional. Skip it, or zip `web/evidence/` (screenshots of
the real crash-to-fix run). Under 35 MB either way.

**Submitter Type** → `Team`

**Organization Name** → `N/A`

**Submitter Country of Residence** → **YOU**

**Canada province** → **YOU** (`N/A` if neither of you lives in Canada)

**Which track** → `Personal AI`

**Is your project new or existing prior to August 26, 2026?** → `New`

**If existing, explain…** → leave blank (it is new; first commit Oct 12, 2026)

**Public code repository**

```
https://github.com/munadirkhan/Argus
```

**Working demo URL** → **YOU / pending** — see the note at the bottom.

---

**Which model(s) did you use, and why did you choose that size/variant?**

```
Three Nemotron variants, one per stage, because the product forces the split:

• NVIDIA-Nemotron-3-Nano-30B-A3B — the executor. Every tool call goes through
  it. We needed something fast and cheap enough to run dozens of times per
  task, and Nano's tool calling was reliable in our tests.

• Nemotron-3_5-Lightning (exact API id; the docs write it "Nemotron 3.5
  Lightning") — the always-on watcher. It looks at the workspace
  every 20 seconds and decides whether to speak. 1M context lets it hold the
  whole workspace plus terminal output, and at $0.06/M input a single look
  costs about $0.00007 — which is the only reason "always-on" is affordable
  at all. A worst-case 8-hour day of watching is about $0.10.

• Nemotron-3-Ultra-550b-a55b — the planner and writer. Used twice per task,
  never in the hot loop: once to decompose the request, once to write the
  finished document or code fix. This is where reasoning earns its tokens.

We did not pick sizes by benchmark score. Each tier's constraint picked it:
the watcher must be cheap because it never stops, the writer must be strong
because its output is the thing the user actually reads.

We also resolve model IDs at startup from /v1/models rather than hardcoding
them, and fall back down a chain (Ultra → Super → Nano), so an unavailable
model degrades instead of crashing.
```

**How would you rate Nemotron's output quality for your use case? (1–10)**

```
8

What worked well:
• Tool calling was reliable on all four variants we tested (Nano, Super,
  Ultra, Lightning). We probed every one before building on it, and none of
  them produced malformed tool calls in our runs. This was the single
  biggest risk in the project and it just worked.
• Ultra's long-form writing is genuinely good. Asked to produce a research
  note from PDFs plus live search results, it led with the finding that
  contradicted the user's own stale notes — which is exactly the judgement
  we wanted and the hardest thing to prompt for.
• Instruction-following on format held up: "reply with the complete file and
  nothing else" produced clean output we could write straight to disk.

Where it fell short:
• Lightning with reasoning ON could not do our watcher task. Its reasoning
  spilled into the answer and broke JSON — 600 tokens and 2.8s of unusable
  output for a task it does in 25 tokens and 0.8s with reasoning off. The
  fix exists (chat_template_kwargs) but we only found it by probing.
• Negation drift: asked about current model availability, the agent would
  conclude "X is not available" from sources that simply did not mention X.
  We had to add an explicit rule that absence of evidence is not evidence of
  absence, plus inject ground-truth platform facts.
• Prompt-level limits did not hold. "Use at most two searches per step" was
  ignored often enough that we moved the cap into code.
```

**Did you fine-tune, prompt-engineer, or use Nemotron out of the box?**

```
Out of the box, with heavy prompt engineering and no fine-tuning.

Our approach, in order of how much it mattered:

1. Role-split prompts. Each stage has its own system prompt (planner,
   executor, writer, watcher) in one file, so prompts can be tuned without
   touching loop logic. Most of the quality work happened here.

2. Reasoning switched per tier, measured not assumed. We probed all four
   models on our real watcher task and set enable_thinking per stage:
   off for the watcher and executor, on for the planner/writer.

3. Ground truth injected as first-hand fact. The agent is told, as
   authoritative, which models the live Token Factory catalogue returned and
   which ones it is itself running on — outranking anything it reads on the
   web. This fixed a class of confidently-wrong answers.

4. Structure instead of instruction, wherever a rule mattered. Writing is
   deterministic: the model returns the document, our code saves it. The
   search cap is enforced by removing the tool after two uses. The spend cap
   refuses the call before it is sent. If a behaviour has to hold, we stopped
   asking the model nicely and made it structural.

5. JSON mode for the watcher's speak/stay-quiet decision, with a tolerant
   parser (prose and code fences stripped) and a fail-quiet default.
```

**How did Nemotron's performance compare to other models you've used?**

```
We did not run a controlled head-to-head, so we will not claim one. What we
can report is the comparison we did run, between Nemotron variants on our
own task, and our qualitative read against prior agent work.

Measured, same prompt, same task (the watcher's JSON speak/stay-quiet call):
  Lightning, reasoning on   invalid JSON   600 tokens   2.8s
  Lightning, reasoning off  valid JSON      25 tokens   0.8s
  Nano, reasoning off       valid JSON      27 tokens   0.7s
  Ultra, reasoning off      valid JSON      22 tokens   0.3s
Ultra was the fastest to first token of the four despite being the largest,
which we did not expect.

Qualitatively, versus other hosted models we have built agents against:
• Tool calling felt on par with the frontier hosted APIs — a working OpenAI
  tool-call loop needed no Nemotron-specific handling.
• The cost structure is the real differentiator. An always-on watcher is not
  viable at frontier per-token prices; at Lightning's price it is. The whole
  project, every experiment included, cost $0.26.
• Ultra's long-form synthesis was competitive for our use. The gap we felt
  was in resisting confident negation, where we had to add guardrails.
```

**Which Nebius platform capabilities were most valuable, and how?**

```
Nebius Token Factory serverless inference, via the OpenAI-compatible endpoint.
We did not provision GPUs, containers or dedicated endpoints — for an agent
that idles most of the day and bursts for ~20 seconds, serverless per-token
billing is the right shape, and avoiding fixed GPU cost is what makes an
always-on assistant affordable.

Specifically:
• OpenAI-compatible API. We used the standard openai Python SDK pointed at
  https://api.tokenfactory.us-central1.nebius.com/v1/ with AsyncOpenAI. Our
  tool-calling loop, JSON mode and streaming assumptions all worked
  unchanged. Integration was hours, not days.
• /v1/models as a live catalogue. We query it at startup and bind each tier
  to the best model actually available, case-insensitively, with a fallback
  chain. This made the system resilient to catalogue changes and to the
  casing mismatch between the docs and the live API.
• Per-model routing within one provider and one key. Running three different
  model sizes against one endpoint is what let us build the three-tier
  design at all; we route per call with no extra infrastructure.
• Response usage accounting. Token counts on every response let us price
  each call in real time, show live spend in the UI, and enforce our own
  hard spending cap.

Scaling: entirely Nebius's. We never managed capacity. Rate limits were never
hit in our usage.
```

**How likely are you to recommend running Nemotron on Nebius? (1–10)**

```
9

The OpenAI-compatible endpoint plus a catalogue that spans Nano through Ultra
on one key is a genuinely good developer experience — we had a working
three-model agent the same day we got credentials, and never touched
infrastructure. For anything agent-shaped, where you want a cheap model in
the hot loop and a strong one for the hard step, having both behind one
endpoint at these prices is the main reason this project was possible.

The one point held back: there is no spending cap (see below). That is the
only thing we would hesitate about before recommending it to someone running
an autonomous loop unattended.
```

**Experience vs previous cloud or local dev environments? (1–10)**

```
8

Better than local: we got a 550B model's reasoning on a laptop project with
no GPU, no quantisation tradeoffs, no 40GB download, and no cold start. For
the always-on watcher, local inference would have meant a model resident in
memory all day; serverless meant paying $0.00007 per look and nothing while
idle.

Better than most hosted setups on time-to-first-call: OpenAI-compatible meant
no new SDK and no bespoke tool-call plumbing.

What cost us time, versus a mature provider:
• The live model IDs do not match the published ones (casing), so the first
  copy-pasted example 404s.
• Reasoning defaults are not surfaced where you need them, and the switch to
  turn them off is not in the model card.
• Regional availability was unclear from the docs; we wrote a probe script to
  find out empirically what was served where.
Each cost us an hour or two of guessing. None were hard once understood, and
all are documentation problems rather than platform problems.
```

**What additional features or improvements would have made it more effective?**

```
1. A hard spending cap, per project or per key. This is the biggest one. The
   billing docs confirm the card is charged once the balance is used up, and
   the only control is manual top-up. Agents loop; a bug can loop expensively
   and unattended. We built our own cap — refuse the call before sending,
   persist the ledger atomically, fail closed on a corrupt ledger — but every
   team building an agent on Token Factory is rebuilding this, and the
   platform is the right place for it. Even a soft "stop at $X" would do.

2. Make the live catalogue the source of truth, and keep the docs in sync.
   The cookbook shows nvidia/nvidia-nemotron-3-nano-30b-a3b; the API serves
   nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B. Also: include a region field per
   model in the /v1/models response so nobody has to probe for it.

3. Document reasoning control on the model card. The enable_thinking
   chat_template_kwarg materially changes output shape, latency and cost, and
   on one model it is the difference between working and not working for a
   JSON task. It deserves a line on every reasoning model's page, next to
   the note that response_format does not imply it.

4. Usage breakdown by model in the console. We can price calls ourselves from
   the usage field, but seeing spend split by model in the dashboard — the
   way our own UI does — would have made the three-tier design easier to
   tune.

5. A prompt-caching story for agent loops. Our executor resends a growing
   message list on every tool iteration; most of it is identical prefix.
```

**What do you most hope to see from the Nemotron team next?**

```
Two things.

First: keep investing in the small end. Nemotron 3.5 Lightning is the most
interesting model in the family for us, and not because of a benchmark — a
1M-context model cheap enough to run every 20 seconds, all day, unlocks a
product category (genuinely always-on local agents) that is simply not
economic at frontier prices. A model tuned specifically for "look at this
state and decide whether anything is worth acting on" would be used
constantly. Reliable structured output and strong instruction-following
matter far more than reasoning depth for that job.

Second: resistance to confident negation. The failure that cost us most was
the model concluding something does not exist because its sources did not
mention it. Calibrated "I don't know" from a small, fast model would be worth
more to agent builders than another point of reasoning benchmark.

Also, selfishly: keep tool calling as solid as it is. It was the one thing we
bet the architecture on, and it held.
```

**Did you use Tavily?** → `Yes`

```
Yes — a functional runtime call, not a wrapper. Two places:

• core/tools/tavily_search.py — the agent's web search. Advanced search depth
  with Tavily's synthesized answer, results deduplicated by normalised URL,
  returned as numbered citations so the writer cites sources as [1][2] and
  ends with a Sources list. The UI renders the real results live.
• core/tools/fetch_url.py — Tavily Extract is the primary reader for a page's
  full text, with a plain-HTTP strip as fallback so a Tavily outage degrades
  rather than blinds the agent.

Both run on every research task; the live demo in our video calls them.
```

**Builders & Brews — IRL city** → leave blank unless you attended one

**Age-of-majority checkbox** → tick (both of you)

**Not an employee of the Promotion Entities** → tick

**Which AI tools have you leveraged?**

```
Claude Code (Anthropic) — used as a pair programmer for the agent core:
the three-tier router, agent loop, watcher, websocket server, spend cap, the
3D interface, and the test suites. Also used to probe the Nemotron variants
and turn those measurements into architecture decisions.

OpenAI Codex — used by the second team member in parallel on a separate
branch for the terminal sensor, the browser extension and headless browse
tool, and UI work.

We ran the two agents in strictly separate directories against frozen
interface contracts (documented in docs/), with a shared worklog so each
could see what the other had changed. Their work merged with zero conflicts,
and the sensor plug-in socket one wrote was filled by sensors the other
wrote, discovered at runtime with no core changes.

NVIDIA Nemotron via Nebius Token Factory is the product itself, not a build
tool — Argus runs on Nemotron.
```

**Level of learning** → `Significant`

**Did you gain AI value for your career?** → `Yes`

---

## The one field still open: the demo URL

The rules require a URL to a working demo. Argus is local-first and judges
will not install a daemon, so the plan is to deploy the interface in SIMULATE
mode: a static Vite build, no backend, playing recordings of the real sessions
(including the actual crash-to-fix run). Judges click once and see the whole
thing; the README covers running it live.

`npm run build` already passes. Say the word and it goes up.
