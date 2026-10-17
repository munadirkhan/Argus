import { AnimatePresence, motion } from "framer-motion";
import { useArgus } from "../lib/store";
import { accept, dismiss } from "../lib/connection";
import { EyeGlyph } from "./Ornament";

/** The watcher speaking unprompted. The one moment the UI is allowed to be loud. */
export default function Prophecy() {
  const id = useArgus((s) => s.prophecy);
  const o = useArgus((s) => (s.prophecy ? s.observations[s.prophecy] : null));
  const source = useArgus((s) => s.source);

  return (
    <div className="prophecy-anchor">
    <AnimatePresence>
      {id && o && (
        <motion.div
          key={id}
          className="prophecy"
          initial={{ opacity: 0, y: 26, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 14 }}
          transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
        >
          <motion.span
            className="sweep"
            initial={{ scaleX: 0, opacity: 1 }}
            animate={{ scaleX: 1, opacity: [1, 1, 0.35] }}
            transition={{ duration: 0.45, ease: "easeOut" }}
          />
          <span className="corner tl" />
          <span className="corner tr" />
          <span className="corner bl" />
          <span className="corner br" />
          <div className="kicker">
            <EyeGlyph size={22} lit />
            <span className="label" style={{ letterSpacing: ".46em" }}>ARGUS HAS NOTICED</span>
            <EyeGlyph size={22} lit />
          </div>
          <div className="seen">{o.observation}</div>
          <div className="offer">{o.suggestion}</div>
          <div className="actions">
            <button className="btn-accept" onClick={() => accept(o.id)}>
              PROCEED <kbd>↵</kbd>
            </button>
            <button className="btn-dismiss" onClick={() => dismiss(o.id)}>
              NOT NOW <kbd>Esc</kbd>
            </button>
          </div>
          <div className="conf">
            CONFIDENCE {o.confidence.toFixed(2)} · SPOKEN BY THE WATCHER · NEMOTRON 3.5 LIGHTNING
          </div>
        </motion.div>
      )}
    </AnimatePresence>
    </div>
  );
}
