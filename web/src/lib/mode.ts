/* Where this hub is running, and whether it can go live.
 *
 *   live       a core is (or should be) running next to it -- the normal case
 *   hosted     the public web build (Vercel): a replay only. It never calls
 *              localhost, so a visitor's browser never asks about local access
 *   needs-key  the desktop app on a machine with no Nebius key yet: it plays
 *              the replay and offers to open the key file instead of a dead screen
 */
import { create } from "zustand";
import { desktop } from "./desktop";

export type Mode = "live" | "hosted" | "needs-key";

export const HOSTED = import.meta.env.VITE_ARGUS_HOSTED === "1";
export const REPO_URL = "https://github.com/munadirkhan/Argus";

export const useMode = create<{ mode: Mode; set: (m: Mode) => void }>((set) => ({
  mode: HOSTED ? "hosted" : "live",
  set: (mode) => set({ mode }),
}));

/** Decide once at startup. */
export async function detectMode(): Promise<Mode> {
  if (HOSTED) return "hosted";
  if (!desktop) return "live";
  try {
    const s = await desktop.getSetup();
    const mode: Mode = s.needsKey ? "needs-key" : "live";
    useMode.getState().set(mode);
    return mode;
  } catch {
    return "live";
  }
}

/** Desktop only: try to start the core now that a key may be in .env. */
export async function goLive(): Promise<{ ok: boolean; needsKey: boolean }> {
  if (!desktop) return { ok: false, needsKey: false };
  return desktop.goLive();
}
