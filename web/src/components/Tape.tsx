import { useEffect, useMemo, useState } from "react";
import { useArgus } from "../lib/store";

/* Ticker tape. In a simulated session it carries illustrative quotes plus the
   event wire; live, it carries ONLY real events -- no fake prices, ever. */

const QUOTES: [string, number][] = [
  ["NVDA", 187.42], ["AMD", 162.1], ["TSM", 204.6], ["AVGO", 341.2], ["ARM", 148.9],
  ["SMCI", 46.3], ["MU", 121.8], ["BTC", 112480], ["ETH", 4120], ["QQQ", 598.4],
];

function useQuotes(on: boolean) {
  const [q, setQ] = useState(() => QUOTES.map(([s, p]) => ({ s, p, d: 0 })));
  useEffect(() => {
    if (!on) return;
    const id = window.setInterval(() => {
      setQ((cur) => cur.map((x) => {
        const step = (Math.random() - 0.48) * x.p * 0.0012;
        return { ...x, p: x.p + step, d: x.d + (step / x.p) * 100 };
      }));
    }, 1400);
    return () => window.clearInterval(id);
  }, [on]);
  return q;
}

export default function Tape() {
  const source = useArgus((s) => s.source);
  const wire = useArgus((s) => s.wire);
  const tiers = useArgus((s) => s.tiers);
  const budget = useArgus((s) => s.budget);
  const sim = source === "replay";
  const quotes = useQuotes(sim);

  const items = useMemo(() => {
    const out: { k: string; text: string; tone: string }[] = [];
    if (sim) {
      out.push({ k: "simtag", text: "SIMULATED FEED · ILLUSTRATIVE", tone: "ember" });
      quotes.forEach((x) =>
        out.push({
          k: "q" + x.s,
          text: `${x.s} ${x.p >= 1000 ? x.p.toFixed(0) : x.p.toFixed(2)} ${x.d >= 0 ? "▲" : "▼"}${Math.abs(x.d).toFixed(2)}%`,
          tone: x.d >= 0 ? "gold" : "ember",
        })
      );
    } else {
      out.push({ k: "livetag", text: "LIVE WIRE", tone: "amber" });
      out.push({ k: "w", text: `WATCHER · ${tiers.watcher.model.split("/").pop()}`, tone: "bone" });
      out.push({ k: "p", text: `ORACLE · ${tiers.planner.model.split("/").pop()}`, tone: "bone" });
      out.push({ k: "e", text: `HANDS · ${tiers.executor.model.split("/").pop()}`, tone: "bone" });
      out.push({ k: "cap", text: `HARD CAP $${budget.toFixed(2)}`, tone: "gold" });
    }
    wire.slice(-14).forEach((w) => out.push({ k: "w" + w.id, text: w.text, tone: w.tone }));
    return out;
  }, [sim, quotes, wire, tiers, budget]);

  return (
    <div className="tape" aria-label="event wire">
      <div className="tape-track" style={{ animationDuration: `${Math.max(28, items.length * 3.2)}s` }}>
        {[0, 1].map((dup) => (
          <div className="tape-run" key={dup} aria-hidden={dup === 1}>
            {items.map((it) => (
              <span key={it.k + dup} className={`tape-item ${it.tone}`}>
                <i>◆</i>{it.text}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
