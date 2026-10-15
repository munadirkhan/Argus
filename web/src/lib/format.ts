export function prettyModel(id: string): string {
  const m = id.toLowerCase();
  if (m.includes("lightning")) return "Nemotron 3.5 Lightning";
  if (m.includes("ultra")) return "Nemotron 3 Ultra · 550B";
  if (m.includes("super")) return "Nemotron 3 Super · 120B";
  if (m.includes("nano")) return "Nemotron 3 Nano · 30B";
  return id.split("/").pop() ?? id;
}

export function usd(n: number, digits = 4): string {
  return "$" + n.toFixed(digits);
}

export function tokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 10_000) return Math.round(n / 1000) + "k";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

export function bytes(n: number): string {
  if (n === 0) return "empty";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / (1024 * 1024)).toFixed(1) + " MB";
}

export function basename(p: string): string {
  return p.replace(/\\/g, "/").split("/").pop() ?? p;
}

export function relative(p: string, root: string): string {
  const a = p.replace(/\\/g, "/");
  const r = root.replace(/\\/g, "/").replace(/\/$/, "");
  return a.toLowerCase().startsWith(r.toLowerCase() + "/") ? a.slice(r.length + 1) : a;
}

export const NUMERAL: Record<string, string> = { watcher: "I", planner: "II", executor: "III" };
