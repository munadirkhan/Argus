import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useArgus } from "../lib/store";
import { approve } from "../lib/connection";
import { EyeGlyph } from "./Ornament";

function host(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Argus asking before something it can't take back -- or handing you the
 *  browser to sign in. Nothing final happens until you answer. */
export default function ApprovalCard() {
  const a = useArgus((s) => s.approval);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!a) return;
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [a]);
  const left = a ? Math.max(0, Math.round((a.deadline - Date.now()) / 1000)) : 0;
  const handoff = a?.kind === "handoff";

  return (
    <div className="prophecy-anchor approval-anchor">
      <AnimatePresence>
        {a && (
          <motion.div
            key={a.id}
            className={`prophecy approval ${handoff ? "handoff" : ""}`}
            role="alertdialog"
            aria-label={a.title}
            initial={{ opacity: 0, y: 26, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 14 }}
            transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <span className="corner tl" />
            <span className="corner tr" />
            <span className="corner bl" />
            <span className="corner br" />
            <div className="kicker">
              <EyeGlyph size={22} lit />
              <span className="label" style={{ letterSpacing: ".46em" }}>
                {handoff ? "YOUR TURN" : "ARGUS ASKS"}
              </span>
              <EyeGlyph size={22} lit />
            </div>
            <div className="seen">{a.title}</div>
            {a.detail && <pre className="approval-detail">{a.detail}</pre>}
            <div className="actions">
              <button className="btn-accept" onClick={() => approve(a.id, true)}>
                {handoff ? "DONE" : "ALLOW"}
              </button>
              <button className="btn-dismiss" onClick={() => approve(a.id, false)}>
                {handoff ? "CANCEL" : "DENY"}
              </button>
            </div>
            <div className="conf">
              {a.url ? `${host(a.url)} · ` : ""}
              {handoff ? "ARGUS NEVER SEES YOUR PASSWORD" : "NOTHING HAPPENS UNTIL YOU SAY SO"} · {Math.floor(left / 60)}:
              {String(left % 60).padStart(2, "0")} LEFT
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
