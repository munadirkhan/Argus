import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useArgus, type Sight } from "../lib/store";
import { frame, gaze } from "../lib/layout";
import type { Source } from "../lib/types";
import { EyeGlyph } from "./Ornament";

/* "What Argus sees": the apps it is watching, as HUD windows either side of
   the orb. The window it is focused on glows, and the eyes turn toward it. */

const LEFT: Source[] = ["market", "editor"];
const RIGHT: Source[] = ["browser", "terminal", "files"];

function latest(sight: Partial<Record<Source, Sight>>, group: Source[]): Sight | null {
  return group.map((g) => sight[g]).filter(Boolean).sort((a, b) => b!.at - a!.at)[0] ?? null;
}

/* ---------------------------------------------------------------- market */
type Candle = { o: number; h: number; l: number; c: number };

function seeded(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

function useMarket(symbol: string, base: number) {
  const rnd = useMemo(() => seeded([...symbol].reduce((a, c) => a + c.charCodeAt(0), 7) * 9973), [symbol]);
  const [candles, setCandles] = useState<Candle[]>(() => {
    const out: Candle[] = [];
    let p = base * 0.965;
    for (let i = 0; i < 40; i++) {
      const o = p;
      const drift = (rnd() - 0.42) * base * 0.006;
      const c = o + drift;
      out.push({ o, c, h: Math.max(o, c) + rnd() * base * 0.003, l: Math.min(o, c) - rnd() * base * 0.003 });
      p = c;
    }
    const scale = base / out[out.length - 1].c; // land the series on the quoted price
    return out.map((k) => ({ o: k.o * scale, c: k.c * scale, h: k.h * scale, l: k.l * scale }));
  });
  const ticks = useRef(0);
  useEffect(() => {
    const id = window.setInterval(() => {
      ticks.current++;
      setCandles((cs) => {
        const next = cs.slice();
        const last = { ...next[next.length - 1] };
        last.c += (rnd() - 0.47) * base * 0.0016;
        last.h = Math.max(last.h, last.c);
        last.l = Math.min(last.l, last.c);
        next[next.length - 1] = last;
        if (ticks.current % 9 === 0) {
          next.push({ o: last.c, c: last.c, h: last.c, l: last.c });
          next.shift();
        }
        return next;
      });
    }, 420);
    return () => window.clearInterval(id);
  }, [base, rnd]);
  return candles;
}

function MarketView({ s }: { s: Sight }) {
  const m = s.market!;
  const candles = useMarket(m.symbol, m.price);
  const last = candles[candles.length - 1].c;
  const first = candles[0].o;
  const chg = ((last - first) / first) * 100 + m.change - ((m.price - first) / first) * 100;
  const hi = Math.max(...candles.map((c) => c.h));
  const lo = Math.min(...candles.map((c) => c.l));
  const W = 300, H = 104, pad = 4;
  const y = (v: number) => pad + (1 - (v - lo) / (hi - lo || 1)) * (H - pad * 2);
  const cw = (W - 40) / candles.length;
  const up = chg >= 0;
  const book = useMemo(() => {
    const rows = [];
    for (let i = 4; i >= 1; i--) rows.push({ side: "ask", px: last + i * 0.05, sz: 120 + ((i * 37) % 9) * 41 });
    for (let i = 1; i <= 4; i++) rows.push({ side: "bid", px: last - i * 0.05, sz: 140 + ((i * 53) % 7) * 46 });
    return rows;
  }, [Math.round(last * 20)]);
  const maxSz = Math.max(...book.map((b) => b.sz));
  return (
    <div className="mkt">
      <div className="mkt-head">
        <span className="sym">{m.symbol}</span>
        <span className="px">{last.toFixed(2)}</span>
        <span className={up ? "chg up" : "chg dn"}>{up ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}%</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="candles" preserveAspectRatio="none">
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={0} x2={W - 40} y1={H * f} y2={H * f} className="gridline" />
        ))}
        {candles.map((c, i) => {
          const x = i * cw + cw / 2;
          const rising = c.c >= c.o;
          return (
            <g key={i} className={rising ? "cu" : "cd"}>
              <line x1={x} x2={x} y1={y(c.h)} y2={y(c.l)} />
              <rect x={x - cw * 0.32} width={cw * 0.64} y={Math.min(y(c.o), y(c.c))} height={Math.max(1, Math.abs(y(c.o) - y(c.c)))} />
            </g>
          );
        })}
        <line x1={0} x2={W - 40} y1={y(last)} y2={y(last)} className="lastline" />
        <rect x={W - 39} y={y(last) - 7} width={38} height={14} className="tag" />
        <text x={W - 20} y={y(last) + 3.5} className="tagtext">{last.toFixed(2)}</text>
      </svg>
      <div className="book">
        {book.map((b, i) => (
          <div key={i} className={`lvl ${b.side}`}>
            <span className="depth" style={{ width: `${(b.sz / maxSz) * 100}%` }} />
            <span>{b.px.toFixed(2)}</span>
            <span>{b.sz}</span>
          </div>
        ))}
      </div>
      <div className="feedtag">{m.interval ?? "15m"} · SIMULATED FEED · ILLUSTRATIVE</div>
    </div>
  );
}

/* ----------------------------------------------------- terminal / editor */
function TerminalView({ s }: { s: Sight }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [s.at]);
  return (
    <div className="term terminal-output" ref={ref} tabIndex={0} aria-label="Terminal output">
      {(s.rows ?? []).map((l) => (
        <div key={l.id} className={`tl ${l.tone ?? ""} ${l.tone === 'err' && Date.now() - l.arrivedAt < 500 ? 'arrived' : ''}`}>
          {l.text}
        </div>
      ))}
      <span className="cursor">▌</span>
    </div>
  );
}

const KW = /\b(export|function|const|return|if|import|from|await|async)\b/g;
function codeHtml(text: string) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc
    .replace(/(\/\/.*)$/, '<i class="cm">$1</i>')
    .replace(/(&quot;|")(.*?)("|&quot;)/g, '<i class="st">"$2"</i>')
    .replace(KW, '<i class="kw">$1</i>');
}

function EditorView({ s }: { s: Sight }) {
  const start = s.startLine ?? 1;
  return (
    <div className="code">
      {(s.lines ?? []).map((l, i) => (
        <div key={`${s.at}-${i}`} className={`cl ${s.errorLine === i ? "bad" : ""}`}>
          <span className="ln">{start + i}</span>
          <span dangerouslySetInnerHTML={{ __html: codeHtml(l.text) }} />
        </div>
      ))}
    </div>
  );
}

function BrowserView({ s }: { s: Sight }) {
  return (
    <div className="browser">
      <div className="url">⌂ {s.url}</div>
      <div className="btitle">{s.title}</div>
      {(s.lines ?? []).map((l, i) => (
        <div key={i} className={`bl ${l.tone ?? ""}`}>{l.text}</div>
      ))}
      <div className="skel" /><div className="skel short" /><div className="skel" />
      <motion.div className="readbar" initial={{ top: "30%" }} animate={{ top: ["30%", "88%", "30%"] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }} />
    </div>
  );
}

function FilesView({ s }: { s: Sight }) {
  return (
    <div className="term">
      {(s.lines ?? []).map((l, i) => (
        <div key={`${s.at}-${i}`} className={`tl ${l.tone ?? ""}`}>{l.text}</div>
      ))}
    </div>
  );
}

const VIEW: Record<Source, (p: { s: Sight }) => React.JSX.Element> = {
  market: MarketView, browser: BrowserView, terminal: TerminalView, editor: EditorView, files: FilesView,
};

function Window({ s, side, focused }: { s: Sight; side: "left" | "right"; focused: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const View = VIEW[s.source];
  useLayoutEffect(() => {
    if (!focused || !ref.current) return;
    const b = ref.current.getBoundingClientRect();
    gaze.x = b.left + b.width / 2;
    gaze.y = b.top + b.height * 0.4;
    gaze.side = side;
    gaze.until = Date.now() + 6500;
  }, [focused, s.at, side]);
  return (
    <motion.div
      ref={ref}
      key={s.source}
      className={`sight ${side} ${focused ? "watched" : ""}`}
      initial={{ opacity: 0, x: side === "left" ? -24 : 24, scale: 0.97 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
    >
      <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
      <div className="sight-bar">
        <span className="dots"><i /><i /><i /></span>
        <span className="app">{s.app.toUpperCase()}</span>
        <span className="stitle">{s.title}</span>
        {focused && (
          <span className="watching"><EyeGlyph size={14} lit /> WATCHING</span>
        )}
      </div>
      <div className="sight-body"><View s={s} /></div>
    </motion.div>
  );
}

function Beam({ side }: { side: "left" | "right" | null }) {
  const [, force] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => force((n) => n + 1), 500);
    return () => window.clearInterval(id);
  }, []);
  const zone = document.querySelector(".orb-zone")?.getBoundingClientRect();
  const win = side ? document.querySelector(`.sight.${side}`)?.getBoundingClientRect() : null;
  if (!zone || !win || !frame.r) return null;
  const x1 = frame.cx - zone.left;
  const y1 = frame.cy - zone.top;
  const x2 = (side === "left" ? win.right : win.left) - zone.left;
  const y2 = win.top + win.height * 0.4 - zone.top;
  return (
    <svg className="beam" width={zone.width} height={zone.height}>
      <defs>
        <linearGradient id="beamg" x1={x1} y1={y1} x2={x2} y2={y2} gradientUnits="userSpaceOnUse">
          <stop offset="0" style={{ stopColor: "var(--amber)" }} stopOpacity="0.9" />
          <stop offset="1" style={{ stopColor: "var(--bone)" }} stopOpacity="0.15" />
        </linearGradient>
      </defs>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="url(#beamg)" strokeWidth="1.2" className="beam-line" />
      <circle cx={x2} cy={y2} r="3" style={{ fill: "var(--amber)" }} className="beam-dot" />
    </svg>
  );
}

export default function SightWindows() {
  const sight = useArgus((s) => s.sight);
  const focus = useArgus((s) => s.focus);
  const left = latest(sight, LEFT);
  const right = latest(sight, RIGHT);
  const focusSide: "left" | "right" | null =
    focus && LEFT.includes(focus) ? "left" : focus && RIGHT.includes(focus) ? "right" : null;
  return (
    <>
      <AnimatePresence>
        {left && <Window key={"L" + left.source} s={left} side="left" focused={focus === left.source} />}
      </AnimatePresence>
      <AnimatePresence>
        {right && <Window key={"R" + right.source} s={right} side="right" focused={focus === right.source} />}
      </AnimatePresence>
      {(left || right) && <Beam side={focusSide} />}
    </>
  );
}
