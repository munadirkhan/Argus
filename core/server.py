"""ARGUS websocket server.

Serves the event contract at ws://host/ws. One Session owns the bus, router,
registry, agent and watcher; every connected client sees the same stream, which
is what lets you open the UI on a second screen during a demo.

Run:  python -m core.server            (or: uvicorn core.server:app --port 8787)
"""
from __future__ import annotations
import asyncio, json, os, sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import events
from .agent import Agent
from .bus import EventBus
from .models import ModelRouter
from .tools.registry import Registry
from .watcher import Watcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

WATCH_ROOT = os.environ.get("ARGUS_WATCH_ROOT", os.getcwd())
WATCH_INTERVAL = float(os.environ.get("ARGUS_WATCH_INTERVAL", "20"))
WATCH_COOLDOWN = float(os.environ.get("ARGUS_WATCH_COOLDOWN", "120"))
PORT = int(os.environ.get("PORT", "8787"))
USE_FAKE = os.environ.get("ARGUS_FAKE", "").lower() in ("1", "true", "yes")


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
            self.router = ModelRouter()

        self.agent = Agent(self.router, self.registry, self.bus)
        self.watcher = Watcher(self.router, self.bus, self.root,
                               interval=WATCH_INTERVAL, cooldown=WATCH_COOLDOWN)
        self._agent_lock = asyncio.Lock()
        self._watch_task: asyncio.Task | None = None
        self.ready = False

    async def start(self) -> None:
        await self.router.resolve()
        print("[argus] model routing:\n" + self.router.describe(), flush=True)
        self.ready = True
        await self.bus.emit(events.session_state(
            self.runtime, "connected", self.root, self.label))
        self._watch_task = asyncio.create_task(self.watcher.run_forever())

    async def stop(self) -> None:
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
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
            pending = self.watcher.pending.pop(obs_id, None)
            if pending:
                asyncio.create_task(self._run_agent(pending["suggestion"]))
        else:
            await self.bus.emit(events.error("unknown client message: %r" % kind))

    async def _run_agent(self, text: str) -> None:
        if self._agent_lock.locked():
            await self.bus.emit(events.error(
                "Still working on the previous request.", fatal=False))
            return
        async with self._agent_lock:
            was_enabled = self.watcher.enabled
            self.watcher.enabled = False          # do not interrupt itself
            try:
                await self.agent.run(text)
            except Exception as e:
                await self.bus.emit(events.error(
                    "%s: %s" % (type(e).__name__, e), fatal=False))
            finally:
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
        "models": {t: session.router.for_tier(t).model_id
                   for t in ("watcher", "planner", "executor")},
        "spend_usd": round(session.router.spend.total_usd, 6),
        "clients": session.bus.subscriber_count,
    }


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
