"""The stop button: a run is cut off immediately, wherever it is -- mid model
call, mid tool, or waiting on an approval card -- and Argus is ready again.

Run:  python scripts/test_stop_offline.py
"""
import asyncio, json, os, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
WS = tempfile.mkdtemp(prefix="argus_stop_")
os.environ["ARGUS_WATCH_ROOT"] = WS
os.environ["ARGUS_MEMORY_FILE"] = os.path.join(WS, ".mem", "memory.md")
os.environ["ARGUS_FAKE"] = "1"
os.environ["TAVILY_API_KEY"] = ""

from core.agent import Agent                         # noqa: E402
from core.approvals import Approvals                 # noqa: E402
from core.tools.registry import Registry             # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + str(detail)[:200]) if detail and not cond else ""))
    ok &= bool(cond)


class Bus:
    subscriber_count = 1
    def __init__(self): self.events = []
    async def emit(self, e): self.events.append(e)
    def types(self): return [e["type"] for e in self.events]


class _Msg:
    def __init__(self, content, tool_calls=None): self.content, self.tool_calls = content, tool_calls


class _R:
    model_id = "stub"


class SlowRouter:
    """Plans two steps, then every executor call hangs (a slow model)."""
    catalogue_ids = []
    def for_tier(self, t): return _R()
    async def complete(self, tier, messages, **kw):
        usage = {"tier": tier, "model": "stub", "prompt_tokens": 1, "completion_tokens": 1,
                 "cost_usd": 0.0, "cumulative_cost_usd": 0.0}
        if "Decomposing" in json.dumps(messages)[:0] or kw.get("response_format"):
            return _Msg(json.dumps({"steps": [{"title": "Look around", "kind": "act"},
                                              {"title": "Think hard", "kind": "act"}]})), usage
        await asyncio.sleep(60)
        return _Msg("done"), usage


async def main():
    print("=== stop during a slow model call ===")
    bus = Bus()
    agent = Agent(SlowRouter(), Registry(), bus, workspace=WS)
    task = asyncio.create_task(agent.run("do a long thing"))
    await asyncio.sleep(0.4)
    t0 = time.monotonic()
    task.cancel()
    answer = await task
    took = time.monotonic() - t0
    check("stops immediately", took < 0.5, "%.2fs" % took)
    check("says it stopped", answer == "Stopped.")
    steps = [e for e in bus.events if e["type"] == "agent.step"]
    check("the running step is marked failed", steps[-1]["status"] == "failed" and steps[-1]["id"] == "s1", steps[-1])
    check("emits agent.stopped", "agent.stopped" in bus.types())
    last = [e for e in bus.events if e["type"] == "agent.message"][-1]
    check("final message closes the run in the UI", last["role"] == "assistant" and last["text"] == "Stopped.")
    check("the second step never started", not any(e.get("id") == "s2" and e.get("status") == "running" for e in steps))

    print("=== stop while an approval card is open ===")
    a = Approvals()
    bus2 = Bus()
    a.attach(bus2)
    waiting = asyncio.create_task(a.ask("confirm", 'Click "Submit"', timeout=300))
    await asyncio.sleep(0.05)
    waiting.cancel()
    try:
        await waiting
    except asyncio.CancelledError:
        pass
    check("the card is withdrawn", bus2.events[-1]["type"] == "agent.approval.resolved"
          and bus2.events[-1]["outcome"] == "cancelled", bus2.events[-1])
    check("nothing left pending", not a.pending)

    print("=== through the real server: user.stop ===")
    from fastapi.testclient import TestClient
    from core import server
    started = asyncio.Event()

    async def slow_run(goal, display=None, attachments=None):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await server.session.bus.emit({"type": "agent.stopped", "by": "user"})
            return "Stopped."

    with TestClient(server.app, base_url="http://127.0.0.1") as c:
        server.session.agent.run = slow_run
        with c.websocket_connect("ws://127.0.0.1/ws") as ws:
            ws.send_text(json.dumps({"type": "user.message", "text": "take forever"}))
            time.sleep(0.3)
            check("a run is in progress", server.session._agent_lock.locked())
            t0 = time.monotonic()
            ws.send_text(json.dumps({"type": "user.stop"}))
            while time.monotonic() - t0 < 5:
                e = json.loads(ws.receive_text())
                if e["type"] == "agent.stopped":
                    break
            took = time.monotonic() - t0
            check("user.stop cancels it within a second", e["type"] == "agent.stopped" and took < 1.0, "%.2fs" % took)
            time.sleep(0.2)
            check("ready for the next request", not server.session._agent_lock.locked())
            ws.send_text(json.dumps({"type": "user.stop"}))
            time.sleep(0.1)
            check("stop with nothing running is harmless", not server.session._agent_lock.locked())

    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")


asyncio.run(main())
sys.exit(0 if ok else 1)
