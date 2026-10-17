import { create } from "zustand";
import type { ActivityEvent, ArgusEvent, Mood, SentAttachment, Source, StepStatus, Tier } from "./types";
import { terminalRows, type TerminalRow } from './terminal';

export interface Sight extends ActivityEvent {
  at: number;
  rows?: TerminalRow[];
}
export interface WireItem {
  id: number;
  text: string;
  tone: "gold" | "amber" | "ember" | "bone";
}

let wireId = 0;
const wire = (text: string, tone: WireItem["tone"] = "bone"): WireItem => ({ id: ++wireId, text, tone });

export interface TierState {
  model: string;
  active: boolean;
  note: string;
  calls: number;
  tokensIn: number;
  tokensOut: number;
  cost: number;
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "err";
  summary?: string;
  detail?: string;
}

export interface Observation {
  id: string;
  observation: string;
  suggestion: string;
  confidence: number;
  state: "pending" | "accepted" | "dismissed";
}

export interface Artifact {
  path: string;
  kind: string;
  bytes: number;
  preview: string;
  at: number;
}

export type Entry =
  | { kind: "message"; id: string; role: "user" | "assistant"; text: string; attachments?: SentAttachment[] }
  | { kind: "plan"; id: string }
  | { kind: "tool"; id: string }
  | { kind: "observation"; id: string }
  | { kind: "artifact"; id: string; path: string }
  | { kind: "error"; id: string; message: string };

const emptyTier = (model: string): TierState => ({
  model,
  active: false,
  note: "",
  calls: 0,
  tokensIn: 0,
  tokensOut: 0,
  cost: 0,
});

const DEFAULT_MODELS: Record<Tier, string> = {
  watcher: "nvidia/Nemotron-3_5-Lightning",
  planner: "nvidia/Nemotron-3-Ultra-550b-a55b",
  executor: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
};

interface State {
  sensors: string[] | null;
  senseAt: Partial<Record<Source, number>>;
  recording: boolean;
  setSensors: (names: string[]) => void;
  setRecording: (active: boolean) => void;
  conn: "connecting" | "live" | "offline" | "replay";
  source: "live" | "replay";
  session: { runtime: string; status: string; cwd: string; label: string } | null;
  entries: Entry[];
  plans: Record<string, { id: string; steps: { id: string; title: string; status: StepStatus }[] }>;
  tools: Record<string, ToolCall>;
  observations: Record<string, Observation>;
  prophecy: string | null; // observation currently demanding attention
  tiers: Record<Tier, TierState>;
  activeTier: Tier | null;
  totalCost: number;
  budget: number;
  artifacts: Artifact[];
  selectedArtifact: string | null;
  tree: { root: string; nodes: { path: string; dir: boolean; bytes: number }[] };
  touched: Record<string, number>; // path -> when it last changed
  busy: boolean;
  lastEventAt: number;
  sight: Partial<Record<Source, Sight>>; // latest thing seen per source
  focus: Source | null; // where the eyes are pointed
  wire: WireItem[]; // ticker-tape feed of what just happened
  scenario: string | null; // simulated session being played, if any
  setScenario: (s: string | null) => void;

  ingest: (e: ArgusEvent) => void;
  reset: () => void;
  setConn: (c: State["conn"]) => void;
  setSource: (s: State["source"]) => void;
  setBudget: (b: number) => void;
  setModels: (m: Partial<Record<Tier, string>>) => void;
  resolveObservation: (id: string, how: "accepted" | "dismissed") => void;
  selectArtifact: (path: string) => void;
}

let uid = 0;
const nid = () => `e${++uid}`;

const initial = () => ({
  sensors: null,
  senseAt: {} as Partial<Record<Source, number>>,
  session: null,
  entries: [] as Entry[],
  plans: {},
  tools: {},
  observations: {},
  prophecy: null,
  tiers: {
    watcher: emptyTier(DEFAULT_MODELS.watcher),
    planner: emptyTier(DEFAULT_MODELS.planner),
    executor: emptyTier(DEFAULT_MODELS.executor),
  },
  activeTier: null,
  totalCost: 0,
  artifacts: [] as Artifact[],
  selectedArtifact: null,
  tree: { root: "", nodes: [] },
  touched: {},
  busy: false,
  sight: {} as Partial<Record<Source, Sight>>,
  focus: null as Source | null,
  wire: [] as WireItem[],
  lastEventAt: 0,
});

export const useArgus = create<State>((set, get) => ({
  recording: false,
  setSensors: (sensors) => set({ sensors }),
  setRecording: (recording) => set({ recording }),
  conn: "connecting",
  source: "live",
  budget: 10,
  ...initial(),

  reset: () => set({ ...initial() }),
  setConn: (conn) => set({ conn }),
  setSource: (source) => set({ source }),
  setBudget: (budget) => set({ budget }),
  setModels: (m) =>
    set((s) => {
      const tiers = { ...s.tiers };
      (Object.keys(m) as Tier[]).forEach((t) => {
        if (m[t]) tiers[t] = { ...tiers[t], model: m[t]! };
      });
      return { tiers };
    }),

  resolveObservation: (id, how) =>
    set((s) => {
      const o = s.observations[id];
      if (!o) return {};
      return {
        observations: { ...s.observations, [id]: { ...o, state: how } },
        prophecy: s.prophecy === id ? null : s.prophecy,
      };
    }),

  selectArtifact: (path) => set({ selectedArtifact: path }),
  scenario: null,
  setScenario: (scenario) => set({ scenario }),

  ingest: (e) => {
    const s = get();
    const now = Date.now();
    switch (e.type) {
      case "session.state": {
        const moved = s.session && s.session.cwd !== e.cwd;
        set({
          session: { runtime: e.runtime, status: e.status, cwd: e.cwd, label: e.label },
          // A new workspace starts a fresh baseline: its files aren't "changes".
          ...(moved ? { tree: { root: "", nodes: [] }, sight: {}, focus: null, touched: {} } : {}),
        });
        break;
      }

      case "watcher.observation": {
        if (s.observations[e.id]) break;
        set({
          observations: {
            ...s.observations,
            [e.id]: {
              id: e.id,
              observation: e.observation,
              suggestion: e.suggestion,
              confidence: e.confidence,
              state: "pending",
            },
          },
          prophecy: e.id,
          entries: [...s.entries, { kind: "observation", id: e.id }],
        });
        break;
      }

      case "agent.message": {
        const existing = s.entries.findIndex((x) => x.kind === "message" && x.id === e.id);
        const entry: Entry = { kind: "message", id: e.id, role: e.role, text: e.text, attachments: e.attachments };
        const entries =
          existing >= 0 ? s.entries.map((x, i) => (i === existing ? entry : x)) : [...s.entries, entry];
        const patch: Partial<State> = { entries };
        if (e.role === "user") {
          patch.busy = true;
          // A request arriving while a prophecy is open means it was taken up.
          if (s.prophecy) {
            const o = s.observations[s.prophecy];
            patch.observations = { ...s.observations, [s.prophecy]: { ...o, state: "accepted" } };
            patch.prophecy = null;
          }
        } else if (e.done) {
          patch.busy = false;
          patch.activeTier = null;
        }
        set(patch);
        break;
      }

      case "agent.plan":
        set({
          plans: { ...s.plans, [e.id]: { id: e.id, steps: e.steps } },
          entries: [...s.entries, { kind: "plan", id: e.id }],
        });
        break;

      case "agent.step": {
        const p = s.plans[e.plan_id];
        if (!p) break;
        set({
          plans: {
            ...s.plans,
            [e.plan_id]: { ...p, steps: p.steps.map((st) => (st.id === e.id ? { ...st, status: e.status } : st)) },
          },
        });
        break;
      }

      case "agent.thinking": {
        const tiers = { ...s.tiers };
        (Object.keys(tiers) as Tier[]).forEach((t) => (tiers[t] = { ...tiers[t], active: t === e.tier }));
        tiers[e.tier] = { ...tiers[e.tier], model: e.model, note: e.note, active: true };
        set({ tiers, activeTier: e.tier });
        break;
      }

      case "usage": {
        const t = s.tiers[e.tier];
        const tiers = {
          ...s.tiers,
          [e.tier]: {
            ...t,
            model: e.model,
            active: false,
            calls: t.calls + 1,
            tokensIn: t.tokensIn + e.prompt_tokens,
            tokensOut: t.tokensOut + e.completion_tokens,
            cost: t.cost + e.cost_usd,
          },
        };
        set({
          tiers,
          activeTier: s.activeTier === e.tier ? null : s.activeTier,
          totalCost: Math.max(s.totalCost, e.cumulative_cost_usd),
        });
        break;
      }

      case "tool.call":
        set({
          tools: { ...s.tools, [e.id]: { id: e.id, name: e.name, args: e.args, status: "running" } },
          entries: [...s.entries, { kind: "tool", id: e.id }],
        });
        break;

      case "tool.result": {
        const t = s.tools[e.id];
        if (!t) break;
        set({
          tools: {
            ...s.tools,
            [e.id]: { ...t, status: e.ok ? "ok" : "err", summary: e.summary, detail: e.detail },
          },
        });
        break;
      }

      case "artifact.write": {
        const art: Artifact = { path: e.path, kind: e.kind, bytes: e.bytes, preview: e.preview, at: now };
        const norm = (p: string) => p.split("\\").join("/").toLowerCase();
        const known = s.tree.nodes.some((n) => norm(n.path) === norm(e.path));
        const nodes = known
          ? s.tree.nodes.map((n) => (norm(n.path) === norm(e.path) ? { ...n, bytes: e.bytes } : n))
          : [...s.tree.nodes, { path: e.path, dir: false, bytes: e.bytes }];
        set({
          tree: { ...s.tree, nodes },
          artifacts: [art, ...s.artifacts.filter((a) => a.path !== e.path)],
          selectedArtifact: e.path,
          touched: { ...s.touched, [e.path]: now },
          entries: [...s.entries, { kind: "artifact", id: nid(), path: e.path }],
        });
        break;
      }

      case "fs.tree": {
        const prev = new Map(s.tree.nodes.map((n) => [n.path, n.bytes]));
        const touched = { ...s.touched };
        if (s.tree.root) {
          e.nodes.forEach((n) => {
            if (!prev.has(n.path) || prev.get(n.path) !== n.bytes) touched[n.path] = now;
          });
        }
        // In live mode the filesystem is what Argus sees: surface new and
        // changed files as a "files" sight so the HUD shows it looking.
        // Any earlier snapshot -- even an empty folder -- is a baseline to diff against.
        const changed = s.tree.root
          ? e.nodes.filter((n) => !prev.has(n.path) || prev.get(n.path) !== n.bytes)
          : [];
        const patch: Partial<State> = { tree: { root: e.root, nodes: e.nodes }, touched };
        if (changed.length) {
          patch.senseAt = { ...s.senseAt, files: now };
          const rel = (p: string) => p.split("\\").join("/").replace(e.root.split("\\").join("/") + "/", "");
          patch.sight = {
            ...s.sight,
            files: {
              type: "activity", source: "files", app: "Workspace", title: `${changed.length} file${changed.length > 1 ? "s" : ""} changed`,
              lines: changed.slice(0, 8).map((n) => ({
                text: `${prev.has(n.path) ? "~" : "+"} ${rel(n.path)}  ${n.bytes === 0 ? "empty" : (n.bytes / 1024).toFixed(1) + " KB"}`,
                tone: prev.has(n.path) ? "warn" : "ok",
              })),
              focus: true, at: now,
            },
          };
          patch.focus = "files";
          patch.wire = [...s.wire, wire(`FILES · ${changed.length} changed`, "gold")].slice(-40);
        }
        set(patch);
        break;
      }

      case "activity": {
        const rows = e.source === 'terminal' ? terminalRows(s.sight.terminal?.rows ?? [], e.lines, now) : undefined;
        const sight = { ...s.sight, [e.source]: { ...e, at: now, rows } };
        set({
          sight,
          senseAt: { ...s.senseAt, [e.source]: now },
          focus: e.focus ? e.source : s.focus,
          wire: [...s.wire, wire(`${e.app.toUpperCase()} · ${e.title}`, e.lines?.some((l) => l.tone === "err") ? "ember" : "bone")].slice(-40),
        });
        break;
      }

      case "error":
        set({ entries: [...s.entries, { kind: "error", id: nid(), message: e.message }],
          activeTier: null, busy: false,
          tiers: Object.fromEntries(Object.entries(s.tiers).map(([key, tier]) => [key, { ...tier, active: false }])) as Record<Tier, TierState>,
        });
        break;
    }
    const w = wireFor(e);
    set((st) => ({ lastEventAt: now, wire: w ? [...st.wire, w].slice(-40) : st.wire }));
  },
}));

const TIER_NAME: Record<Tier, string> = { watcher: "WATCHER", planner: "ORACLE", executor: "HANDS" };

function wireFor(e: ArgusEvent): WireItem | null {
  switch (e.type) {
    case "usage": {
      const tok = e.prompt_tokens + e.completion_tokens;
      const k = tok >= 1000 ? (tok / 1000).toFixed(1) + "k" : String(tok);
      return wire(`${TIER_NAME[e.tier]} · ${k} tok · $${e.cost_usd.toFixed(4)}`, e.tier === "planner" ? "amber" : "gold");
    }
    case "watcher.observation":
      return wire("THE WATCHER SPEAKS", "amber");
    case "tool.call": {
      const a = e.args as Record<string, unknown>;
      const arg = String(a.query ?? a.path ?? a.url ?? "").split("/").pop()?.slice(0, 40) ?? "";
      return wire(`${e.name.toUpperCase()} · ${arg}`, "bone");
    }
    case "artifact.write":
      return wire(`INSCRIBED · ${e.path.split("/").pop()}`, "amber");
    case "error":
      return wire(`ERROR · ${e.message.slice(0, 50)}`, "ember");
    default:
      return null;
  }
}

export function moodOf(s: Pick<State, "prophecy" | "activeTier" | "busy">): Mood {
  if (s.prophecy) return "gaze";
  if (s.activeTier === "planner") return "deliberate";
  if (s.activeTier === "executor") return "act";
  if (s.activeTier === "watcher") return "observe";
  return "idle";
}

if (import.meta.hot) import.meta.hot.accept(() => window.location.reload());
