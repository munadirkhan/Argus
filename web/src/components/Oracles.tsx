import { AnimatePresence, motion } from "framer-motion";
import { useArgus } from "../lib/store";
import { NUMERAL, prettyModel, tokens, usd } from "../lib/format";
import type { Tier } from "../lib/types";
import { Panel } from "./Ornament";

const ROLE: Record<Tier, { name: string; why: string }> = {
  watcher: { name: "THE WATCHER", why: "never sleeps · reasoning off · 1M context" },
  planner: { name: "THE ORACLE", why: "plans & writes · reasoning on" },
  executor: { name: "THE HANDS", why: "acts with tools · reasoning off" },
};

export default function Oracles() {
  const tiers = useArgus((s) => s.tiers);
  const active = useArgus((s) => s.activeTier);

  return (
    <Panel num="I" title="THE ORACLES" meta="NEMOTRON ROUTING" glow={!!active}>
      <div className="oracles">
        {(["watcher", "planner", "executor"] as Tier[]).map((t) => {
          const s = tiers[t];
          const on = active === t;
          return (
            <div key={t} className={`tier ${on ? "active" : ""}`}>
              {on && <motion.span layoutId="tier-flare" className="flare" transition={{ type: "spring", stiffness: 260, damping: 30 }} />}
              <div className="top">
                <span className="numeral">{NUMERAL[t]}</span>
                <span className="role">{ROLE[t].name}</span>
                <span className="status">
                  <span className={`dot ${on ? "live" : ""}`} />
                  {on ? "ACTIVE" : s.calls ? "AT REST" : "DORMANT"}
                </span>
              </div>
              <div className="model">{prettyModel(s.model)}</div>
              <div className="why">{ROLE[t].why}</div>
              <AnimatePresence>
                {on && s.note && (
                  <motion.div
                    className="note"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.25 }}
                  >
                    {s.note}…
                  </motion.div>
                )}
              </AnimatePresence>
              <div className="stats">
                <span>calls<b>{s.calls}</b></span>
                <span>tokens<b>{tokens(s.tokensIn + s.tokensOut)}</b></span>
                <span>spent<b>{usd(s.cost, 4)}</b></span>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
