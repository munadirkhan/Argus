/* The core's settings, as the Sanctum sees them. */
import { API } from "./connection";
import { desktop } from "./desktop";
import { useTheme } from "./themes";

export type Tier = "watcher" | "planner" | "executor";

export interface Settings {
  theme: string;
  models: Record<Tier, string | null>;
  thinking: Record<Tier, boolean | null>;
  budget_usd: number | null;
  voice: { name: string | null; speed: number | null };
  watcher: { enabled: boolean; interval: number; cooldown: number };
  persona: { address: string; tone: "casual" | "butler" | "formal"; length: "short" | "normal" | "detailed" };
}

export interface ModelInfo {
  id: string;
  region: string;
  price_in: number | null;
  price_out: number | null;
  description: string;
  context: number | null;
  modality: string;
}

export interface Skill { name: string; when: string; text: string }
export interface Routine { id: string; name: string; time: string; days: string[]; prompt: string; enabled: boolean; last_run: string }

export interface SettingsView {
  settings: Settings;
  themes: string[];
  catalogue: ModelInfo[];
  automatic: Record<Tier, string>;
  bound: Record<Tier, string>;
  spend_usd: number;
  budget_usd: number;
  budget_default: number;
  speaker: { engine: string | null; voice: string; speed: number; voices: string[] };
  memory: string[];
  memory_file: string;
  skills: Skill[];
  routines: Routine[];
  fs_scope: string;
  workspace: string;
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(API + path, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export const settingsApi = {
  get: () => call<SettingsView>("GET", "/settings"),
  async put(patch: Partial<Record<keyof Settings, unknown>>) {
    const v = await call<SettingsView>("PUT", "/settings", patch);
    desktop?.notifySettings?.();
    return v;
  },
  memory: (facts: string[]) => call<{ ok: boolean; memory: string[] }>("PUT", "/memory", { facts }),
  skill: (s: { name: string; when: string; steps: string; old_name?: string }) =>
    call<{ ok: boolean; skills: Skill[] }>("PUT", "/skill", s),
  deleteSkill: (name: string) => call<{ ok: boolean }>("DELETE", "/skill?name=" + encodeURIComponent(name)),
  routine: (r: { name: string; time: string; days: string[]; prompt: string; enabled: boolean; old_name?: string }) =>
    call<{ ok: boolean; routines: Routine[] }>("PUT", "/routine", r),
  deleteRoutine: (name: string) => call<{ ok: boolean }>("DELETE", "/routine?name=" + encodeURIComponent(name)),
  runRoutine: (name: string) => call<{ ok: boolean; error?: string }>("POST", "/routine/run", { name }),
};

/** Pull the theme from the core (on connect, and when the other window changes it). */
export async function syncSettings() {
  try {
    const v = await settingsApi.get();
    if (v.settings.theme !== useTheme.getState().name) useTheme.getState().set(v.settings.theme);
  } catch {
    /* core not reachable: keep the cached theme */
  }
}
desktop?.onSettings?.(() => void syncSettings());
