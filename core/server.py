"""ARGUS websocket server.

Serves the event contract at ws://host/ws. One Session owns the bus, router,
registry, agent and watcher; every connected client sees the same stream, which
is what lets you open the UI on a second screen during a demo.

Run:  python -m core.server            (or: uvicorn core.server:app --port 7600)
"""
from __future__ import annotations
import asyncio, json, os, sys, time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import events
from .agent import Agent
from .bus import EventBus
from .models import ModelRouter
from .tools.registry import Registry
from .watcher import Watcher, scan
from .sensors.registry import Sensors

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

WATCH_ROOT = os.environ.get("ARGUS_WATCH_ROOT", os.getcwd())
WATCH_INTERVAL = float(os.environ.get("ARGUS_WATCH_INTERVAL", "20"))
WATCH_COOLDOWN = float(os.environ.get("ARGUS_WATCH_COOLDOWN", "120"))
PORT = int(os.environ.get("PORT", "7600"))
USE_FAKE = os.environ.get("ARGUS_FAKE", "").lower() in ("1", "true", "yes")
LEDGER_PATH = os.environ.get(
    "ARGUS_SPEND_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".argus_spend.json"))


class Session:
    """Everything one ARGUS instance needs."""

    def __init__(self, root: str, runtime: str = "local", label: str = "") -> None:
        self.root = os.path.abspath(root)
        self.runtime = runtime
        self.label = label or os.path.basename(self.root) or "this machine"
        self.bus = EventBus()
        self.registry = Registry()

        if USE_FAKE:
            from .fake import FakeClient
            from .demo_script import DEMO_SCRIPT
            self.router = ModelRouter(api_key="fake",
                                      client_factory=FakeClient.factory(DEMO_SCRIPT))
        else:
            # Real money: persist spend so the cap survives restarts.
            self.router = ModelRouter(ledger_path=LEDGER_PATH)

        # Tools read their confinement root from the environment; make it the
        # exact folder the watcher observes.
        os.environ["ARGUS_WATCH_ROOT"] = self.root
        self.agent = Agent(self.router, self.registry, self.bus, workspace=self.root)
        self.watcher = Watcher(self.router, self.bus, self.root,
                               interval=WATCH_INTERVAL, cooldown=WATCH_COOLDOWN)
        self.sensors = Sensors()
        self.watcher.context_fn = self.sensors.context
        self._agent_lock = asyncio.Lock()
        self._watch_task: asyncio.Task | None = None
        self._sense_task: asyncio.Task | None = None
        self.ready = False

    async def start(self) -> None:
        await self.router.resolve()
        print("[argus] model routing:\n" + self.router.describe(), flush=True)
        print("[argus] sensors: %s" % (", ".join(self.sensors.names) or "(none)"), flush=True)
        self.ready = True
        await self.bus.emit(events.session_state(
            self.runtime, "connected", self.root, self.label))
        self._watch_task = asyncio.create_task(self.watcher.run_forever())
        self._sense_task = asyncio.create_task(
            self.sensors.run_forever(self.bus.emit, self.on_sensor_alert))

    async def on_sensor_alert(self, sensor, event: dict) -> None:
        """A sensor saw something urgent (e.g. a stack trace). Wake the watcher
        now rather than at its next tick -- unless ARGUS is mid-task or has
        spoken too recently to interrupt again."""
        if not self.watcher.enabled or self._agent_lock.locked():
            return
        if time.time() - self.watcher.last_spoke_at < self.watcher.cooldown:
            return
        bad = [l.get("text", "") for l in event.get("lines") or [] if l.get("tone") == "err"]
        reason = "%s reported: %s" % (sensor.name, (bad[0] if bad else event.get("title", ""))[:160])
        asyncio.create_task(self.watcher.consider([], [], [], reason=reason))

    async def stop(self) -> None:
        for task in (self._watch_task, self._sense_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def handle_client_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "user.message":
            text = str(msg.get("text", "")).strip()
            if text:
                asyncio.create_task(self._run_agent(text))
        elif kind == "user.dismiss":
            obs_id = str(msg.get("id", ""))
            if obs_id:
                self.watcher.dismiss(obs_id)
        elif kind == "user.accept":
            obs_id = str(msg.get("id", ""))
            # Accept works even after a dismiss: the user is allowed to change
            # their mind, and an accept must never silently do nothing.
            pending = self.watcher.pending.pop(obs_id, None) or self.watcher.seen.get(obs_id)
            if pending:
                goal = ("You noticed: %s\nYou offered: %s\nThe user said yes -- do it."
                        % (pending["observation"], pending["suggestion"]))
                asyncio.create_task(self._run_agent(goal, display="Go ahead."))
            else:
                await self.bus.emit(events.error(
                    "Couldn't find observation %r to act on." % obs_id, fatal=False))
        else:
            await self.bus.emit(events.error("unknown client message: %r" % kind))

    async def _run_agent(self, text: str, display: str | None = None) -> None:
        if self._agent_lock.locked():
            await self.bus.emit(events.error(
                "Still working on the previous request.", fatal=False))
            return
        async with self._agent_lock:
            was_enabled = self.watcher.enabled
            self.watcher.enabled = False          # do not interrupt itself
            try:
                await self.agent.run(text, display=display)
            except Exception as e:
                await self.bus.emit(events.error(
                    "%s: %s" % (type(e).__name__, e), fatal=False))
            finally:
                # Re-baseline: what ARGUS just wrote is not the user's activity,
                # and the watcher must not comment on its own work.
                self.watcher.previous = scan(self.watcher.root)
                self.watcher.last_spoke_at = time.time()
                await self.watcher.emit_tree(self.watcher.previous)
                self.watcher.enabled = was_enabled


app = FastAPI(title="ARGUS")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

session = Session(WATCH_ROOT)


@app.on_event("startup")
async def _startup() -> None:
    await session.start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await session.stop()


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "ready": session.ready,
        "runtime": session.runtime,
        "root": session.root,
        "tools": sorted(session.registry.tools),
        "sensors": session.sensors.names,
        "models": {t: session.router.for_tier(t).model_id
                   for t in ("watcher", "planner", "executor")},
        "spend_usd": round(session.router.spend.total_usd, 6),
        "budget_usd": session.router.budget_usd,
        "remaining_usd": round(session.router.remaining_usd, 6),
        "clients": session.bus.subscriber_count,
    }


@app.get("/artifact")
async def artifact(path: str) -> dict:
    """Full text of a file the agent wrote, for the UI's document viewer.
    Same confinement as the file tools: nothing outside the workspace."""
    from .tools._workspace import OutsideWorkspace, resolve
    try:
        full = resolve(path)
    except OutsideWorkspace as e:
        return {"ok": False, "error": str(e)}
    if not os.path.isfile(full):
        return {"ok": False, "error": "not found"}
    with open(full, encoding="utf-8", errors="replace") as f:
        text = f.read(400_000)
    return {"ok": True, "path": full.replace("\\", "/"), "text": text}


@app.post("/sense/{name}")
async def sense(name: str, payload: dict) -> dict:
    """Push data to a sensor (e.g. a browser extension reporting the active
    tab). The sensor decides what to keep; nothing here is trusted as
    instructions -- it is context the watcher reads."""
    sensor = next((s for s in session.sensors.sensors if s.name == name), None)
    if sensor is None:
        return {"ok": False, "error": "no sensor named %r" % name}
    try:
        accepted = bool(sensor.receive(payload))
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    return {"ok": accepted}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()

    async def pump() -> None:
        async for event in session.bus.subscribe(replay=True):
            await websocket.send_text(json.dumps(event))

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                await session.handle_client_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()


def main() -> None:
    import uvicorn
    if not USE_FAKE and not os.environ.get("NEBIUS_API_KEY"):
        print("NEBIUS_API_KEY is not set. Either put it in .env, or run with "
              "ARGUS_FAKE=1 to use the scripted demo model.", file=sys.stderr)
    print("[argus] watching %s" % WATCH_ROOT, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
