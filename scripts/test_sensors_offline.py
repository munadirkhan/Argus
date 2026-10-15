"""Sensor socket tests, offline. Run:  python scripts/test_sensors_offline.py"""
import asyncio, json, os, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent
from core.bus import EventBus
from core.fake import FakeClient, Turn
from core.models import ModelRouter
from core.sensors.base import Sensor
from core.sensors.registry import Sensors
from core.tools.base import Tool, ToolResult
from core.tools.registry import Registry
from core.watcher import Watcher, scan


def check(label, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- %s" % detail) if detail and not cond else ""))
    return bool(cond)


ERR = {"type": "activity", "source": "terminal", "app": "Terminal", "title": "npm run dev",
       "lines": [{"text": "TypeError: x is undefined", "tone": "err"},
                 {"text": "    at Watchlist (src/Watchlist.tsx:42:21)", "tone": "err"}], "focus": True}
OK = {"type": "activity", "source": "terminal", "app": "Terminal", "title": "npm run dev",
      "lines": [{"text": "ready in 412 ms", "tone": "ok"}]}


class FakeLog(Sensor):
    name = "fake_terminal"
    interval = 0.0

    def __init__(self, batches):
        self.batches = list(batches)
        self.seen = []

    async def poll(self):
        if not self.batches:
            return []
        b = self.batches.pop(0)
        self.seen += b
        return b

    def context(self):
        return "\n".join(l["text"] for ev in self.seen for l in ev.get("lines", []))[-500:]


class Broken(Sensor):
    name = "broken"
    interval = 0.0

    async def poll(self):
        raise RuntimeError("sensor blew up")

    def context(self):
        raise RuntimeError("context blew up")


class StubSearch(Tool):
    name = "tavily_search"
    description = "search"
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    async def run(self, query):
        return ToolResult(ok=True, summary="2 sources · nvidia.com", detail="[1] A\n[2] B",
                          meta={"answer": "Ultra is live.", "citations": [
                              {"n": 1, "title": "Nemotron 3 Ultra", "url": "https://nvidia.com/x", "domain": "nvidia.com", "score": 1},
                              {"n": 2, "title": "Token Factory", "url": "https://nebius.com/y", "domain": "nebius.com", "score": 1}]})


async def main():
    ok = True

    print("=== registry tick ===")
    log = FakeLog([[OK], [ERR], [], [OK, OK]])
    ss = Sensors([log, Broken()])
    sent, alerts = [], []

    async def emit(e):
        sent.append(e)

    async def on_alert(s, e):
        alerts.append((s.name, e))

    for _ in range(4):
        await ss.tick(emit, on_alert)
        await asyncio.sleep(0.21)          # the registry polls at most every 0.2s
    ok &= check("activity forwarded", len(sent) == 4, len(sent))
    ok &= check("only the error alerted", len(alerts) == 1 and alerts[0][0] == "fake_terminal", alerts)
    ok &= check("broken sensor contained", True)
    ctx = ss.context()
    ok &= check("context gathered", "TypeError" in ctx and "[fake_terminal]" in ctx, ctx[:80])
    ok &= check("broken context skipped", "broken" not in ctx)
    ok &= check("non-activity payloads dropped",
                await Sensors([FakeLog([[{"type": "nonsense"}]])]).tick(emit, on_alert) == 0)

    print("\n=== watcher reads the senses ===")
    sink = []
    router = ModelRouter(api_key="fake", sink=None) if False else ModelRouter(
        api_key="fake", client_factory=FakeClient.factory({"lightning": [Turn(text=json.dumps({
            "speak": True, "confidence": 0.93,
            "observation": "Your dev server threw a TypeError at Watchlist.tsx:42.",
            "suggestion": "Want me to trace it and patch Watchlist.tsx?"}))]}, sink=sink))
    bus = EventBus()
    ws = tempfile.mkdtemp()
    w = Watcher(router, bus, ws, cooldown=0)
    w.previous = scan(ws)
    w.context_fn = ss.context
    obs = await w.consider([], [], [], reason="fake_terminal reported: TypeError: x is undefined")
    sent_prompt = sink[0].calls[0]["messages"][1]["content"] if sink and sink[0].calls else ""
    ok &= check("prompt includes the terminal", "TypeError" in sent_prompt and "other senses" in sent_prompt)
    ok &= check("prompt says why it woke", "You were woken because" in sent_prompt)
    ok &= check("watcher spoke about the error", obs is not None and "TypeError" in obs["observation"])
    ok &= check("thinking note names the trigger",
                any(e["type"] == "agent.thinking" and e["note"].startswith("Noticed:") for e in bus.history()))

    print("\n=== server gating ===")
    os.environ["ARGUS_FAKE"] = "1"
    os.environ["ARGUS_WATCH_ROOT"] = ws
    os.environ["TAVILY_API_KEY"] = ""
    from core import server
    sess = server.Session(ws)
    calls = []

    async def fake_consider(*a, **k):
        calls.append(k.get("reason", ""))

    sess.watcher.consider = fake_consider
    sess.watcher.last_spoke_at = 0
    await sess.on_sensor_alert(log, ERR)
    await asyncio.sleep(0.01)
    ok &= check("alert wakes the watcher", len(calls) == 1 and "TypeError" in calls[0], calls)
    sess.watcher.last_spoke_at = time.time()
    await sess.on_sensor_alert(log, ERR)
    await asyncio.sleep(0.01)
    ok &= check("cooldown suppresses repeat alerts", len(calls) == 1)
    sess.watcher.last_spoke_at = 0
    async with sess._agent_lock:
        await sess.on_sensor_alert(log, ERR)
        await asyncio.sleep(0.01)
    ok &= check("no interruptions mid-task", len(calls) == 1)
    sess.watcher.enabled = False
    await sess.on_sensor_alert(log, ERR)
    await asyncio.sleep(0.01)
    ok &= check("disabled watcher stays quiet", len(calls) == 1)

    print("\n=== live web reading shows in the browser window ===")
    script = {"ultra": [Turn(text=json.dumps({"steps": [{"title": "Search", "kind": "act"}]})), Turn(text="Done.")],
              "nano": [Turn(tool_calls=[("tavily_search", {"query": "nemotron ultra"})]), Turn(text="found it")]}
    bus = EventBus()
    r2 = ModelRouter(api_key="fake", client_factory=FakeClient.factory(script))
    await r2.resolve()
    reg = Registry()
    reg.tools = {"tavily_search": StubSearch()}
    await Agent(r2, reg, bus, workspace=ws).run("check ultra")
    acts = [e for e in bus.history() if e["type"] == "activity"]
    ok &= check("browser activity emitted", len(acts) == 1 and acts[0]["source"] == "browser", acts)
    if acts:
        ok &= check("shows the query and real results",
                    "nemotron ultra" in acts[0]["title"] and acts[0]["lines"][0]["text"].startswith("[1] Nemotron"))

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
