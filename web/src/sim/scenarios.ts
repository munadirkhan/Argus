/* Simulated sessions for the REPLAY mode.
 *
 * "markets" and "code" are scripted to show where Argus is headed: watching
 * the apps you work in, not just the files. They are labelled SIMULATED in the
 * UI, use illustrative figures, and Argus never trades -- it researches.
 * "research" is different: a recording of a real live run (see
 * scripts/record_replay.py), timing compressed, nothing invented.
 */
import type { ArgusEvent, Tier } from "../lib/types";
import recorded from "../../mock/recorded-research.json";

export type Timed = ArgusEvent & { t_offset_ms: number };
export interface Scenario {
  id: string;
  name: string;
  blurb: string;
  kind: "simulated" | "recorded";
  events: Timed[];
}

const MODEL: Record<Tier, string> = {
  watcher: "nvidia/Nemotron-3_5-Lightning",
  planner: "nvidia/Nemotron-3-Ultra-550b-a55b",
  executor: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
};
const PRICE: Record<Tier, [number, number]> = { watcher: [0.06, 0.24], planner: [1, 3], executor: [0.06, 0.24] };

function script(prefix: string, build: (s: ReturnType<typeof dsl>) => void): Timed[] {
  const s = dsl(prefix);
  build(s);
  return s.events;
}

function dsl(prefix: string) {
  const events: Timed[] = [];
  let t = 0;
  const push = (e: ArgusEvent) => {
    events.push({ ...(e as object), t_offset_ms: Math.round(t) } as Timed);
  };
  const api = {
    events,
    at(ms: number) { t = ms; return api; },
    wait(ms: number) { t += ms; return api; },
    emit(e: ArgusEvent) { push(e); return api; },
    think(tier: Tier, note: string) { push({ type: "agent.thinking", tier, model: MODEL[tier], note }); return api; },
    use(tier: Tier, pin: number, pout: number) {
      const [a, b] = PRICE[tier];
      push({ type: "usage", tier, model: MODEL[tier], prompt_tokens: pin, completion_tokens: pout,
        cost_usd: (pin * a + pout * b) / 1e6, cumulative_cost_usd: 0 });
      return api;
    },
    say(role: "user" | "assistant", id: string, text: string) {
      push({ type: "agent.message", id: `${prefix}_${id}`, role, text, streaming: false, done: true });
      return api;
    },
    step(plan: string, id: string, status: "running" | "done" | "failed") {
      push({ type: "agent.step", plan_id: `${prefix}_${plan}`, id, status });
      return api;
    },
    tool(id: string, name: string, args: Record<string, unknown>, ms: number, summary: string, detail = "") {
      push({ type: "tool.call", id: `${prefix}_${id}`, name, args });
      t += ms;
      push({ type: "tool.result", id: `${prefix}_${id}`, ok: true, summary, detail });
      return api;
    },
  };
  return api;
}

/* ------------------------------------------------------------------ MARKETS */
const MARKETS_ROOT = "C:/Users/demo/desk";
const EARNINGS_DOC = `# NVDA — earnings watch

> Simulated session · illustrative · research notes, not investment advice.

**The short version:** the print matters less than the guide. Last quarter the stock moved on data-center revenue and next-quarter guidance, not on headline EPS — watch those two lines first.

## What the market will be watching
1. **Data-center revenue** — the segment that carried the last beat, and the one analysts model most closely.
2. **Gross margin** — how it holds up while new systems ramp.
3. **Next-quarter guidance** — historically a bigger mover than the quarter itself.
4. **Supply commentary** — any sign that demand is outrunning what can ship.

## What moved the stock last time
- A beat on the headline numbers that the market had largely priced in.
- Guidance that set the tone for the next leg — see the release and call transcript [1][2].

## Questions to answer before the call
- Is data-center growth still accelerating, or flattening?
- Did margin guidance change, and why?
- What did management say about next year's capacity?

## Sources
1. NVIDIA investor relations — prior-quarter earnings release
2. Earnings-call transcript coverage (financial press)
3. Consensus-estimate summaries (financial data sites)
`;

const markets = script("mk", (s) => {
  s.at(0).emit({ type: "session.state", runtime: "local", status: "connected", cwd: MARKETS_ROOT, label: "simulated" })
    .emit({ type: "fs.tree", root: MARKETS_ROOT, nodes: [
      { path: `${MARKETS_ROOT}/watchlist.csv`, dir: false, bytes: 2140 },
      { path: `${MARKETS_ROOT}/journal/2026-10.md`, dir: false, bytes: 6210 },
    ] })
    .at(500).emit({ type: "activity", source: "market", app: "Chart", title: "NVDA · 15m",
      market: { symbol: "NVDA", price: 187.42, change: 1.84, interval: "15m" }, focus: true })
    .at(3600).emit({ type: "activity", source: "browser", app: "Browser", title: "NVIDIA Investor Relations — upcoming earnings call",
      url: "investor.nvidia.com/events",
      lines: [
        { text: "Upcoming events", tone: "hl" },
        { text: "Quarterly financial results conference call" },
        { text: "Webcast · Investor Relations" },
        { text: "Prior-quarter results and CFO commentary", tone: "dim" },
      ], focus: true })
    .at(6800).emit({ type: "fs.tree", root: MARKETS_ROOT, nodes: [
      { path: `${MARKETS_ROOT}/watchlist.csv`, dir: false, bytes: 2140 },
      { path: `${MARKETS_ROOT}/journal/2026-10.md`, dir: false, bytes: 6210 },
      { path: `${MARKETS_ROOT}/earnings-watch.md`, dir: false, bytes: 0 },
    ] })
    .at(7600).think("watcher", "Observing workspace").wait(700).use("watcher", 1180, 41)
    .wait(300).emit({ type: "watcher.observation", id: "mk_obs1", confidence: 0.88,
      observation: "You've had NVDA open for twenty minutes, the earnings-call page up, and you just created an empty earnings-watch.md.",
      suggestion: "Want me to pull what the market is watching into this call and write it up in earnings-watch.md?",
      dismissible: true })
    .wait(4200).say("user", "m1", "Go ahead.")
    .wait(300).think("planner", "Decomposing request").wait(1100).use("planner", 2240, 310)
    .emit({ type: "agent.plan", id: "mk_plan", steps: [
      { id: "s1", title: "Search what analysts are watching into the call", status: "pending" },
      { id: "s2", title: "Read last quarter's earnings release", status: "pending" },
      { id: "s3", title: "Write the brief to earnings-watch.md", status: "pending" },
    ] })
    .wait(200).step("plan", "s1", "running").think("executor", "Calling tools").wait(500).use("executor", 1650, 72)
    .tool("t1", "tavily_search", { query: "NVIDIA earnings preview what analysts are watching" }, 2300,
      "6 sources · reuters.com, cnbc.com, nasdaq.com")
    .wait(300).use("executor", 4300, 96).step("plan", "s1", "done")
    .wait(200).step("plan", "s2", "running").think("executor", "Calling tools").wait(500)
    .tool("t2", "fetch_url", { url: "https://investor.nvidia.com/news/prior-quarter-results" }, 1700,
      "investor.nvidia.com · 18,204 chars")
    .wait(300).use("executor", 9100, 140).step("plan", "s2", "done")
    .wait(200).step("plan", "s3", "running").think("planner", "Writing earnings-watch.md").wait(2600).use("planner", 15800, 1260)
    .tool("t3", "write_file", { path: "earnings-watch.md" }, 150, "1.6 KB written to earnings-watch.md")
    .emit({ type: "artifact.write", path: `${MARKETS_ROOT}/earnings-watch.md`, kind: "md", bytes: 1618, preview: EARNINGS_DOC })
    .step("plan", "s3", "done")
    .wait(300).think("planner", "Synthesising result").wait(900).use("planner", 3100, 64)
    .say("assistant", "m2", "The brief is in earnings-watch.md. Watch data-center revenue and next-quarter guidance first — that's what moved the stock last time, not the headline EPS.");
});

/* --------------------------------------------------------------------- CODE */
const CODE_ROOT = "C:/Users/demo/desk-dashboard";
const BROKEN = [
  "export function Watchlist() {",
  "  const quotes = useQuotes(symbols);",
  "  return (",
  '    <ul className="watchlist">',
  "      {quotes.data.map((q) => (",
  "        <Row key={q.symbol} quote={q} />",
  "      ))}",
  "    </ul>",
  "  );",
  "}",
];
const FIXED = `export function Watchlist() {
  const quotes = useQuotes(symbols);
  // quotes.data is undefined until the first fetch resolves.
  if (quotes.isLoading) return <WatchlistSkeleton rows={symbols.length} />;
  return (
    <ul className="watchlist">
      {(quotes.data ?? []).map((q) => (
        <Row key={q.symbol} quote={q} />
      ))}
    </ul>
  );
}
`;

const code = script("cd", (s) => {
  s.at(0).emit({ type: "session.state", runtime: "local", status: "connected", cwd: CODE_ROOT, label: "simulated" })
    .emit({ type: "fs.tree", root: CODE_ROOT, nodes: [
      { path: `${CODE_ROOT}/src/Watchlist.tsx`, dir: false, bytes: 1312 },
      { path: `${CODE_ROOT}/src/api/quotes.ts`, dir: false, bytes: 884 },
      { path: `${CODE_ROOT}/src/App.tsx`, dir: false, bytes: 640 },
      { path: `${CODE_ROOT}/package.json`, dir: false, bytes: 702 },
    ] })
    .at(400).emit({ type: "activity", source: "editor", app: "Editor", title: "src/Watchlist.tsx",
      lines: BROKEN.map((text) => ({ text, tone: "code" as const })), startLine: 38, focus: true })
    .at(2200).emit({ type: "activity", source: "terminal", app: "Terminal", title: "npm run dev", lines: [
      { text: "$ npm run dev", tone: "dim" },
      { text: "  VITE v6.4  ready in 412 ms", tone: "ok" },
      { text: "  ➜  Local:   http://localhost:5173/" },
      { text: "  GET /api/quotes 200 · 38ms", tone: "dim" },
    ], focus: true })
    .at(4400).emit({ type: "activity", source: "terminal", app: "Terminal", title: "npm run dev", lines: [
      { text: "$ npm run dev", tone: "dim" },
      { text: "  VITE v6.4  ready in 412 ms", tone: "ok" },
      { text: "  [hmr] src/Watchlist.tsx", tone: "dim" },
      { text: "✗ TypeError: Cannot read properties of undefined (reading 'map')", tone: "err" },
      { text: "    at Watchlist (src/Watchlist.tsx:42:21)", tone: "err" },
      { text: "    at renderWithHooks (react-dom.development.js)", tone: "dim" },
    ], focus: true })
    .at(4500).emit({ type: "activity", source: "editor", app: "Editor", title: "src/Watchlist.tsx",
      lines: BROKEN.map((text) => ({ text, tone: "code" as const })), startLine: 38, errorLine: 4 })
    .at(5400).think("watcher", "Observing workspace").wait(600).use("watcher", 1420, 38)
    .wait(300).emit({ type: "watcher.observation", id: "cd_obs1", confidence: 0.93,
      observation: "Your dev server just threw a TypeError at Watchlist.tsx:42 — quotes.data is undefined on the first render.",
      suggestion: "Want me to trace it and patch Watchlist.tsx?", dismissible: true })
    .wait(3600).say("user", "m1", "Go ahead.")
    .wait(300).think("planner", "Decomposing request").wait(1000).use("planner", 2480, 260)
    .emit({ type: "agent.plan", id: "cd_plan", steps: [
      { id: "s1", title: "Read src/Watchlist.tsx and src/api/quotes.ts", status: "pending" },
      { id: "s2", title: "Write the fix to src/Watchlist.tsx", status: "pending" },
    ] })
    .wait(200).step("plan", "s1", "running").think("executor", "Calling tools").wait(500).use("executor", 1900, 66)
    .tool("t1", "read_file", { path: "src/Watchlist.tsx" }, 300, "src/Watchlist.tsx · 48 lines")
    .wait(200).tool("t2", "read_file", { path: "src/api/quotes.ts" }, 300, "src/api/quotes.ts · 31 lines")
    .wait(300).use("executor", 3600, 120).step("plan", "s1", "done")
    .wait(200).step("plan", "s2", "running").think("planner", "Writing src/Watchlist.tsx").wait(2000).use("planner", 6400, 420)
    .tool("t3", "write_file", { path: "src/Watchlist.tsx" }, 150, "1.4 KB written to src/Watchlist.tsx")
    .emit({ type: "artifact.write", path: `${CODE_ROOT}/src/Watchlist.tsx`, kind: "code", bytes: 1388, preview: FIXED })
    .emit({ type: "activity", source: "editor", app: "Editor", title: "src/Watchlist.tsx — patched by Argus",
      lines: FIXED.trimEnd().split("\n").map((text) => ({ text, tone: "code" as const })), startLine: 38 })
    .step("plan", "s2", "done")
    .wait(600).emit({ type: "activity", source: "terminal", app: "Terminal", title: "npm run dev", lines: [
      { text: "  [hmr] src/Watchlist.tsx updated", tone: "dim" },
      { text: "  GET /api/quotes 200 · 41ms", tone: "dim" },
      { text: "✓ no errors · watchlist rendered 12 rows", tone: "ok" },
    ], focus: true })
    .wait(300).think("planner", "Synthesising result").wait(800).use("planner", 2200, 58)
    .say("assistant", "m2", "Patched Watchlist.tsx: the quotes query is undefined until the first fetch resolves, so it now renders a skeleton until then. The dev server reloaded clean.");
});

/* ----------------------------------------------------------------- RESEARCH */
const research = (recorded as Timed[]).map((e) => ({ ...e }));

/* ------------------------------------------------------------------ MONTAGE */
function chain(...parts: Timed[][]): Timed[] {
  const out: Timed[] = [];
  let offset = 0;
  parts.forEach((p) => {
    const end = Math.max(...p.map((e) => e.t_offset_ms));
    p.forEach((e) => out.push({ ...e, t_offset_ms: e.t_offset_ms + offset } as Timed));
    offset += end + 3500;
  });
  return out;
}

export const SCENARIOS: Record<string, Scenario> = {
  montage: {
    id: "montage", name: "Montage", kind: "simulated",
    blurb: "Markets, then code, then the recorded research run — back to back.",
    events: chain(markets, code, research),
  },
  markets: { id: "markets", name: "Markets", kind: "simulated", blurb: "Argus watches a chart and preps an earnings brief.", events: markets },
  code: { id: "code", name: "Code", kind: "simulated", blurb: "Argus catches a crash and patches it.", events: code },
  research: { id: "research", name: "Research", kind: "recorded", blurb: "A real live run, recorded.", events: research },
};
