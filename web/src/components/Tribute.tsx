import { motion } from "framer-motion";
import { useArgus } from "../lib/store";
import { usd } from "../lib/format";
import { Panel } from "./Ornament";

const COLORS = { watcher: "#efe4cc", planner: "#ff8a2a", executor: "#d6a04c" } as const;
const WATCH_CALLS_8H = 3 * 60 * 8; // one look every 20 seconds

export default function Tribute() {
  const total = useArgus((s) => s.totalCost);
  const budget = useArgus((s) => s.budget);
  const tiers = useArgus((s) => s.tiers);

  const used = budget > 0 ? Math.min(1, total / budget) : 0;
  const sum = tiers.watcher.cost + tiers.planner.cost + tiers.executor.cost || 1;
  const perLook = tiers.watcher.calls ? tiers.watcher.cost / tiers.watcher.calls : 0;

  return (
    <Panel num="II" title="TRIBUTE" meta="SPEND · HARD CAP">
      <div className="tribute">
        <div className="big">{usd(total, 4)}</div>
        <div className="cap">
          of {usd(budget, 2)} cap · {(used * 100).toFixed(used < 0.01 ? 3 : 1)}% used · refused before it is sent
        </div>
        <div className="bar">
          {(["watcher", "planner", "executor"] as const).map((t) => (
            <motion.span
              key={t}
              style={{ background: COLORS[t], boxShadow: `0 0 10px ${COLORS[t]}` }}
              animate={{ width: `${Math.max(used > 0 ? 0.6 : 0, (tiers[t].cost / sum) * used * 100)}%` }}
              transition={{ duration: 0.6 }}
            />
          ))}
        </div>
        <div className="legend">
          <span><i style={{ background: COLORS.watcher }} />watcher</span>
          <span><i style={{ background: COLORS.planner }} />oracle</span>
          <span><i style={{ background: COLORS.executor }} />hands</span>
        </div>
        <div className="foot">
          {perLook > 0 ? (
            <>
              Worst case, a full 8-hour day of watching: <b>≈ {usd(perLook * WATCH_CALLS_8H, 2)}</b>
              <br />
              one look every 20s at {usd(perLook, 5)} each — and nothing at all while nothing changes
            </>
          ) : (
            <>
              Measured live: a full 8-hour day of watching costs <b>≈ $0.10</b> at most
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}
