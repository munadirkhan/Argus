import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useArgus, type Entry } from "../lib/store";
import { speak } from "../lib/connection";
import { basename, bytes, relative } from "../lib/format";
import { EyeGlyph, Panel } from "./Ornament";

const VERB: Record<string, string> = {
  tavily_search: "SEARCH",
  fetch_url: "READ WEB",
  read_file: "READ",
  write_file: "INSCRIBE",
  list_dir: "SURVEY",
  shell: "INVOKE",
};
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"];

function argOf(name: string, args: Record<string, unknown>, root = ""): string {
  const v = args.query ?? args.path ?? args.url ?? args.command ?? Object.values(args)[0];
  if (v === undefined || v === null) return name === "list_dir" ? "workspace" : "";
  const s = root && typeof args.path === "string" ? relative(String(v), root) : String(v);
  return name === "tavily_search" ? `“${s}”` : s;
}

function Plan({ id }: { id: string }) {
  const plan = useArgus((s) => s.plans[id]);
  if (!plan) return null;
  return (
    <div className="plan">
      <div className="head">
        <span className="label">THE PLAN</span>
        <span className="mono-dim">· drawn by the Oracle</span>
      </div>
      {plan.steps.map((st, i) => (
        <div key={st.id} className={`step ${st.status}`}>
          <span className="n">{ROMAN[i] ?? i + 1}</span>
          <span className="mark" />
          <span className={st.status === "running" ? "shimmer" : ""}>{st.title}</span>
        </div>
      ))}
    </div>
  );
}

function Tool({ id }: { id: string }) {
  const t = useArgus((s) => s.tools[id]);
  const root = useArgus((s) => s.session?.cwd ?? "");
  const [open, setOpen] = useState(false);
  if (!t) return null;
  return (
    <div className={`tool ${t.status}`}>
      <div className="row" onClick={() => setOpen((o) => !o)} title="Show output">
        <span className="verb">{VERB[t.name] ?? t.name.toUpperCase()}</span>
        <span className="arg">{argOf(t.name, t.args, root)}</span>
        <span className={`res ${t.status === "running" ? "shimmer" : ""}`}>
          {t.status === "running" ? "working…" : t.summary}
        </span>
      </div>
      <AnimatePresence>
        {open && t.detail && (
          <motion.pre initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            {t.detail}
          </motion.pre>
        )}
      </AnimatePresence>
    </div>
  );
}

function Noticed({ id }: { id: string }) {
  const o = useArgus((s) => s.observations[id]);
  if (!o || o.state === "pending") return null;
  return (
    <div className="noticed">
      <span className="tag">{o.state === "accepted" ? "NOTICED · ACCEPTED" : "NOTICED · DISMISSED"}</span>
      {o.observation}
    </div>
  );
}

function Inscribed({ path }: { path: string }) {
  const art = useArgus((s) => s.artifacts.find((a) => a.path === path));
  const select = useArgus((s) => s.selectArtifact);
  return (
    <div className="inscribed" onClick={() => select(path)}>
      <EyeGlyph size={18} lit />
      <span className="label" style={{ letterSpacing: ".28em" }}>INSCRIBED</span>
      <span style={{ color: "var(--bone)" }}>{basename(path)}</span>
      <span className="mono-dim" style={{ marginLeft: "auto" }}>{art ? bytes(art.bytes) : ""} · open in archive →</span>
    </div>
  );
}

function Row({ e }: { e: Entry }) {
  switch (e.kind) {
    case "message":
      return e.role === "user" ? (
        <div className="msg-user">
          <div className="who">YOU</div>
          <div className="text">{e.text}</div>
        </div>
      ) : (
        <div className="msg-argus">
          <div className="who">
            <EyeGlyph size={18} lit />
            <span className="label">ARGUS</span>
          </div>
          <div className="text">
            <ReactMarkdown allowedElements={["p", "strong", "em", "code", "a"]} unwrapDisallowed>
              {e.text}
            </ReactMarkdown>
          </div>
        </div>
      );
    case "plan":
      return <Plan id={e.id} />;
    case "tool":
      return <Tool id={e.id} />;
    case "observation":
      return <Noticed id={e.id} />;
    case "artifact":
      return <Inscribed path={e.path} />;
    case "error":
      return <div className="err">{e.message}</div>;
  }
}

function Composer() {
  const [text, setText] = useState("");
  const busy = useArgus((s) => s.busy);
  const conn = useArgus((s) => s.conn);
  const note = useArgus((s) => (s.activeTier ? s.tiers[s.activeTier].note : ""));
  const can = conn === "live" && !busy && text.trim().length > 0;
  const submit = () => {
    if (!can) return;
    if (speak(text.trim())) setText("");
  };
  return (
    <div className="composer">
      <EyeGlyph size={20} lit={busy} />
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder={
          conn !== "live"
            ? "Argus is not connected — replay is read-only"
            : busy
              ? `Argus is at work${note ? ` — ${note.toLowerCase()}` : ""}…`
              : "Speak, and Argus will act…"
        }
        disabled={conn !== "live" || busy}
      />
      <button className="invoke" disabled={!can} onClick={submit}>
        INVOKE
      </button>
    </div>
  );
}

export default function Chronicle() {
  const entries = useArgus((s) => s.entries);
  const toolsVersion = useArgus((s) => Object.keys(s.tools).length + s.lastEventAt);
  const feed = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = feed.current;
    if (el && pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [entries.length, toolsVersion]);

  return (
    <Panel num="III" title="THE CHRONICLE" meta={`${entries.length} entries`} className="chronicle">
      <div
        className="feed"
        ref={feed}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {entries.length === 0 ? (
          <div className="empty">
            <div className="voice">The hundred eyes are open.</div>
            <div style={{ marginTop: 8, fontSize: 11 }}>Work as you normally would. Argus will speak when it has something worth saying.</div>
          </div>
        ) : (
          entries.map((e) => (
            <motion.div
              key={`${e.kind}-${e.id}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
            >
              <Row e={e} />
            </motion.div>
          ))
        )}
      </div>
      <Composer />
    </Panel>
  );
}
