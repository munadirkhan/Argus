/* Colour themes. One palette drives both the CSS (as custom properties on
 * <html>) and the 3D scene, so the eye, the orb and every panel change
 * together. The choice lives in the core's settings, so the hub and the
 * floating orb always agree; localStorage only paints the first frame right. */
import { create } from "zustand";

export interface Palette {
  label: string;
  blurb: string;
  void: string;   // the background
  bone: string;   // text, the eyes' sclera
  ash: string;    // quiet text
  gold: string;   // lines, frames, the eye rims
  goldDim: string;
  amber: string;  // the glow: irises, rings, light
  ember: string;  // alarms, errors
  iris: string;   // the iris's dark body
  glow: string;   // hottest highlight
  panel: string;  // panel tint (r,g,b)
  grid: string;   // floor grid cells
}

export const THEMES: Record<string, Palette> = {
  panoptes: {
    label: "Panoptes", blurb: "Black-figure gold and ember. The original.",
    void: "#050407", bone: "#efe4cc", ash: "#a3968a", gold: "#d6a04c", goldDim: "#8f6a35",
    amber: "#ff8a2a", ember: "#ec5a2c", iris: "#5a1c0a", glow: "#ffd29a", panel: "20,14,11", grid: "#4a2610",
  },
  "arc-reactor": {
    label: "Arc Reactor", blurb: "Cold cyan and white. A workshop in Malibu.",
    void: "#03060a", bone: "#e6f3ff", ash: "#8aa3b8", gold: "#6fc8ff", goldDim: "#3c6f8f",
    amber: "#2ec5ff", ember: "#ff5a6a", iris: "#08304a", glow: "#bdf0ff", panel: "8,16,24", grid: "#0e3550",
  },
  hades: {
    label: "Hades", blurb: "Blood red and bone. The underworld keeps the lights low.",
    void: "#070304", bone: "#f0dcd6", ash: "#a88c88", gold: "#d0544a", goldDim: "#7a2e28",
    amber: "#ff3b2f", ember: "#ffb02e", iris: "#4a0606", glow: "#ffb3a8", panel: "22,8,8", grid: "#4a1010",
  },
  olympus: {
    label: "Olympus", blurb: "Marble, silver and storm-light. Very clean, very smug.",
    void: "#06070a", bone: "#f4f5f8", ash: "#9aa0ad", gold: "#c9ced8", goldDim: "#6b717d",
    amber: "#a9c4ff", ember: "#ff7a6b", iris: "#26324a", glow: "#ffffff", panel: "14,16,20", grid: "#2a3140",
  },
  nyx: {
    label: "Nyx", blurb: "Violet night and starlight magenta.",
    void: "#05030a", bone: "#ece2ff", ash: "#9a8fb3", gold: "#b48cff", goldDim: "#5e4790",
    amber: "#d65cff", ember: "#ff5c8a", iris: "#2a0a4a", glow: "#f2c8ff", panel: "14,8,22", grid: "#2e1450",
  },
  gorgon: {
    label: "Gorgon", blurb: "Venom green. Don't look it in the eye.",
    void: "#030604", bone: "#e2f2e4", ash: "#8aa38f", gold: "#7fd18a", goldDim: "#3d6b45",
    amber: "#39ff7a", ember: "#ffcf3a", iris: "#0a3a18", glow: "#c8ffd8", panel: "8,18,10", grid: "#103a1c",
  },
};

const KEY = "argus.theme";

function rgb(hex: string) {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

function paint(name: string) {
  const p = THEMES[name] ?? THEMES.panoptes;
  const r = document.documentElement.style;
  const set: Record<string, string> = {
    "--void": p.void, "--bone": p.bone, "--ash": p.ash, "--gold": p.gold, "--gold-dim": p.goldDim,
    "--amber": p.amber, "--ember": p.ember, "--terracotta": p.goldDim,
    "--void-rgb": rgb(p.void), "--bone-rgb": rgb(p.bone), "--gold-rgb": rgb(p.gold),
    "--amber-rgb": rgb(p.amber), "--ember-rgb": rgb(p.ember), "--panel-rgb": p.panel,
    "--gold-faint": `rgba(${rgb(p.gold)},0.16)`, "--line": `rgba(${rgb(p.gold)},0.15)`,
    "--line-strong": `rgba(${rgb(p.gold)},0.4)`, "--amber-soft": `rgba(${rgb(p.amber)},0.16)`,
  };
  for (const [k, v] of Object.entries(set)) r.setProperty(k, v);
  document.documentElement.dataset.theme = name;
  if (!document.documentElement.classList.contains("orb-mode")) document.body.style.background = p.void;
}

let initial = "panoptes";
try {
  initial = localStorage.getItem(KEY) || "panoptes";
} catch {
  /* fine */
}
if (!THEMES[initial]) initial = "panoptes";

export const useTheme = create<{ name: string; palette: Palette; set: (name: string) => void }>((set) => ({
  name: initial,
  palette: THEMES[initial],
  set: (name) => {
    if (!THEMES[name]) return;
    try {
      localStorage.setItem(KEY, name);
    } catch {
      /* fine */
    }
    paint(name);
    set({ name, palette: THEMES[name] });
  },
}));

paint(initial);
