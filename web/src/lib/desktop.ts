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
  /** Fired by the global push-to-talk shortcut (Ctrl+Alt+Space). Returns an unsubscribe. */
  onVoiceToggle(cb: () => void): () => void;
  /** Fired when the orb's card side changes (orb dragged across the screen centre). */
  onOrbSide(cb: (side: OrbSide) => void): () => void;
  /** Fired when the floating orb window is shown or hidden. */
  onOrbVisible(cb: (visible: boolean) => void): () => void;
}

export const desktop: DesktopBridge | null =
  typeof window !== "undefined" ? ((window as unknown as { argusDesktop?: DesktopBridge }).argusDesktop ?? null) : null;

/** The floating orb window loads the same app with #orb. */
export const ORB_MODE = typeof window !== "undefined" && window.location.hash === "#orb";
