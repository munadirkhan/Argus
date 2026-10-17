/* The bridge to the Electron shell (desktop/preload.js). In a plain browser it
 * is null and every desktop feature quietly switches off. */

export type OrbSide = "left" | "right";

export interface DesktopBridge {
  platform: string;
  /** Bring the hub forward (from the floating orb). */
  openHub(): void;
  /** Floating orb drag: the main process follows the cursor between start/end. */
  orbDrag(phase: "start" | "end"): void;
  /** Grow the floating orb into orb + card, or shrink back. Resolves to the side the card opens on. */
  orbExpand(expanded: boolean): Promise<OrbSide>;
  /** Fired by the global push-to-talk hotkey. Returns an unsubscribe. */
  onVoiceToggle(cb: () => void): () => void;
  /** Fired when the orb's card side changes (orb dragged across the screen centre). */
  onOrbSide(cb: (side: OrbSide) => void): () => void;
  /** Fired when the floating orb window is shown or hidden. */
  onOrbVisible(cb: (visible: boolean) => void): () => void;
  /** The global hotkeys that actually registered (another app may own the first choice). */
  getHotkeys(): Promise<{ hub: string | null; talk: string | null }>;
  /** Whether the core is waiting for a Nebius key in .env. */
  getSetup(): Promise<{ needsKey: boolean }>;
  /** Open .env in an editor (created from .env.example if missing). Never reads it back. */
  openKeyFile(): Promise<boolean>;
  /** Re-check .env and start the core; the windows reload when it comes up. */
  goLive(): Promise<{ ok: boolean; needsKey: boolean }>;
}

/** "CommandOrControl+Alt+J" -> "Ctrl+Alt+J" (or ⌘ on macOS). */
export function keyLabel(accel: string | null): string | null {
  if (!accel) return null;
  const mac = desktop?.platform === "darwin";
  return accel.replace("CommandOrControl", mac ? "⌘" : "Ctrl").replace("Space", "Space");
}

let cached: Promise<{ hub: string | null; talk: string | null }> | null = null;
export function hotkeys() {
  if (!desktop) return Promise.resolve({ hub: null, talk: null });
  cached ??= desktop.getHotkeys().catch(() => ({ hub: null, talk: null }));
  return cached;
}

export const desktop: DesktopBridge | null =
  typeof window !== "undefined" ? ((window as unknown as { argusDesktop?: DesktopBridge }).argusDesktop ?? null) : null;

/** The floating orb window loads the same app with #orb. */
export const ORB_MODE = typeof window !== "undefined" && window.location.hash === "#orb";
