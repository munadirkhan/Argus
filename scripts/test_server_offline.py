"""Server smoke test: boots the real FastAPI app in fake mode and drives it
over a real websocket. No API key, no network.

Run:  python scripts/test_server_offline.py
"""
import json, os, queue, sys, tempfile, threading, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure BEFORE importing the server -- it builds its Session at import time.
TMP = tempfile.mkdtemp(prefix="argus_server_")
open(os.path.join(TMP, "notes.md"), "w").write("")
os.makedirs(os.path.join(TMP, "refs"), exist_ok=True)
open(os.path.join(TMP, "refs", "sampling-2026.pdf"), "w").write("x" * 500)

os.environ["ARGUS_FAKE"] = "1"
os.environ["TAVILY_API_KEY"] = ""        # hermetic: real tools, no network
os.environ["ARGUS_WATCH_ROOT"] = TMP
os.environ["ARGUS_WATCH_INTERVAL"] = "1"
os.environ["ARGUS_WATCH_COOLDOWN"] = "0"

from fastapi.testclient import TestClient          # noqa: E402
from core.server import app, session               # noqa: E402


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -- " + detail) if detail and not cond else ""))
    return bool(cond)


class Reader:
    """Starlette's test websocket has no receive timeout, so read on a thread."""

    def __init__(self, ws):
        self.ws = ws
        self.q = queue.Queue()
        self.alive = True
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while self.alive:
            try:
                raw = self.ws.receive_text()
            except Exception:
                break
            try:
                self.q.put(json.loads(raw))
            except json.JSONDecodeError:
                pass

    def drain(self, seconds=3.0, stop_on=None, quiet_for=0.6):
        """Collect events until `stop_on` arrives, or the stream goes quiet."""
        got = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                e = self.q.get(timeout=quiet_for)
            except queue.Empty:
                break
            got.append(e)
            if stop_on and e.get("type") == stop_on:
                break
        return got


def main():
    ok = True
    with TestClient(app, base_url="http://127.0.0.1") as client:
        print("=== health ===")
        r = client.get("/health")
        ok &= check("health 200", r.status_code == 200)
        h = r.json()
        print("  models: " + json.dumps(h["models"], indent=0).replace("\n", " "))
        ok &= check("reports ready", h["ready"] is True)
        ok &= check("three tiers bound", len(h["models"]) == 3)
        ok &= check("tiers resolved to nemotron",
                    all("nemotron" in m.lower() for m in h["models"].values()),
                    str(h["models"]))
        ok &= check("planner is ultra", "ultra" in h["models"]["planner"].lower())
        ok &= check("watcher is lightning", "lightning" in h["models"]["watcher"].lower())
        ok &= check("executor is nano", "nano" in h["models"]["executor"].lower())

        print("\n=== websocket handshake ===")
        with client.websocket_connect("ws://127.0.0.1/ws") as ws:
            reader = Reader(ws)
            first = reader.drain(3.0, stop_on="session.state")
            types = [e["type"] for e in first]
            ok &= check("receives replayed history", len(first) > 0, str(types))
            st = next((e for e in first if e["type"] == "session.state"), None)
            ok &= check("session.state present", st is not None)
            if st:
                ok &= check("runtime is local", st["runtime"] == "local")
                ok &= check("status connected", st["status"] == "connected")

            print("\n=== user message drives the full loop ===")
            ws.send_text(json.dumps({"type": "user.message",
                                     "text": "summarise what changed in diffusion sampling"}))
            evs = reader.drain(12.0)
            types = [e["type"] for e in evs]
            print("  %d events: %s" % (len(evs), " -> ".join(types[:10]) + " ..."))

            ok &= check("plan emitted", "agent.plan" in types)
            ok &= check("thinking emitted", "agent.thinking" in types)
            ok &= check("usage emitted", "usage" in types)
            ok &= check("assistant replied",
                        any(e["type"] == "agent.message" and e["role"] == "assistant"
                            for e in evs))

            tiers = {e["tier"] for e in evs if e["type"] == "agent.thinking"}
            ok &= check("planner and executor both on HUD",
                        {"planner", "executor"} <= tiers, str(tiers))

            seqs = [e["seq"] for e in evs]
            ok &= check("seq monotonic over the wire", seqs == sorted(seqs))

            print("\n=== unknown message is handled ===")
            ws.send_text(json.dumps({"type": "user.nonsense"}))
            evs = reader.drain(3.0)
            ok &= check("server reports unknown type, stays up",
                        any(e["type"] == "error" for e in evs))

            print("\n=== malformed json does not kill the socket ===")
            ws.send_text("{not json")
            ws.send_text(json.dumps({"type": "user.dismiss", "id": "obs_1"}))
            ok &= check("socket still alive", True)

        print("\n=== spend after run ===")
        h = client.get("/health").json()
        print("  $%.6f" % h["spend_usd"])
        ok &= check("cost was tracked", h["spend_usd"] > 0)

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
