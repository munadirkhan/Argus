// Mirrors docs/EVENT_CONTRACT.md (v1). Server -> client events.

export type Tier = "watcher" | "planner" | "executor";
export type StepStatus = "pending" | "running" | "done" | "failed";

interface Envelope {
  v?: number;
  seq?: number;
  ts?: number;
  t_offset_ms?: number; // mock replay only
}

export type ArgusEvent = Envelope &
  (
    | { type: "session.state"; runtime: "local" | "sandbox"; status: string; cwd: string; label: string }
    | {
        type: "watcher.observation";
        id: string;
        confidence: number;
        observation: string;
        suggestion: string;
        dismissible: boolean;
      }
    | { type: "agent.message"; id: string; role: "user" | "assistant"; text: string; streaming: boolean; done: boolean }
    | { type: "agent.plan"; id: string; steps: { id: string; title: string; status: StepStatus }[] }
    | { type: "agent.step"; plan_id: string; id: string; status: StepStatus }
    | { type: "agent.thinking"; tier: Tier; model: string; note: string }
    | { type: "tool.call"; id: string; name: string; args: Record<string, unknown> }
    | { type: "tool.result"; id: string; ok: boolean; summary: string; detail?: string }
    | { type: "artifact.write"; path: string; kind: string; bytes: number; preview: string }
    | { type: "fs.tree"; root: string; nodes: { path: string; dir: boolean; bytes: number }[] }
    | {
        type: "usage";
        tier: Tier;
        model: string;
        prompt_tokens: number;
        completion_tokens: number;
        cost_usd: number;
        cumulative_cost_usd: number;
      }
    | { type: "error"; message: string; fatal: boolean }
    | ActivityEvent
  );

/** What the user is doing, as Argus sees it (additive to contract v1). */
export type Source = "market" | "browser" | "editor" | "terminal" | "files";
export type Tone = "dim" | "ok" | "warn" | "err" | "hl" | "code";
export interface ActivityEvent {
  type: "activity";
  source: Source;
  app: string;
  title: string;
  url?: string;
  lines?: { text: string; tone?: Tone }[];
  market?: { symbol: string; price: number; change: number; interval?: string };
  errorLine?: number; // editor: highlight this line (0-based index into lines)
  startLine?: number; // editor: number of the first line shown
  focus?: boolean; // the eyes should turn to it
}

export type Mood = "idle" | "observe" | "deliberate" | "act" | "gaze";
