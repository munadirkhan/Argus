"""Turn a real run's event log (scripts/last_run.jsonl, written by
live_demo.py) into a replay the UI can play back.

The research replay in the UI is a RECORDING of a live run, not a script:
same events, same text, same document. Only three things change -- local
paths are anonymised, spend is rebased to start at $0, and idle gaps longer
than MAX_GAP are compressed so the replay doesn't sit waiting on the network.

    python scripts/record_replay.py [in.jsonl] [out.json]
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "last_run.jsonl")
DST = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "web", "mock", "recorded-research.json")
MAX_GAP = 2.2          # seconds
ACCEPT_PAUSE = 3.2     # the human reading the offer before clicking
ANON_ROOT = "C:/Users/demo/mark-ii"


def main():
    events = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
    root = next((e["root"] for e in events if e["type"] == "fs.tree"), "")
    root_fwd = root.replace("\\", "/")

    def anon(v):
        if isinstance(v, str):
            return v.replace("\\", "/").replace(root_fwd, ANON_ROOT) if root_fwd else v
        if isinstance(v, list):
            return [anon(x) for x in v]
        if isinstance(v, dict):
            return {k: anon(x) for k, x in v.items()}
        return v

    out, t, prev_ts, base_cost = [], 0.0, None, None
    out.append({"type": "session.state", "runtime": "local", "status": "connected",
                "cwd": ANON_ROOT, "label": "recorded live", "t_offset_ms": 0})
    for e in events:
        ts = e.get("ts")
        if prev_ts is not None and ts is not None:
            t += min(MAX_GAP, max(0.0, ts - prev_ts))
        prev_ts = ts
        if e["type"] == "agent.message" and e["role"] == "user":
            t += ACCEPT_PAUSE
        if e["type"] == "usage":
            if base_cost is None:
                base_cost = e["cumulative_cost_usd"] - e["cost_usd"]
            e["cumulative_cost_usd"] = round(e["cumulative_cost_usd"] - base_cost, 6)
        clean = {k: v for k, v in anon(e).items() if k not in ("v", "seq", "ts")}
        clean["t_offset_ms"] = int(t * 1000) + 400
        out.append(clean)

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    leaked = root_fwd and any(root_fwd in json.dumps(e) for e in out)
    print("wrote %s: %d events, %.1fs, path leak: %s" % (DST, len(out), t, bool(leaked)))


if __name__ == "__main__":
    main()
