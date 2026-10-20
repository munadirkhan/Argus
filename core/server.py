"""ARGUS websocket server.

Serves the event contract at ws://host/ws. One Session owns the bus, router,
registry, agent and watcher; every connected client sees the same stream, which
is what lets you open the UI on a second screen during a demo.

Run:  python -m core.server            (or: uvicorn core.server:app --port 7600)
"""
from __future__ import annotations
import asyncio, json, os, re, sys, time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from . import events
from .agent import Agent
from .bus import EventBus
from .models import ModelRouter
from .tools.registry import Registry
from .watcher import Watcher, scan
from . import attachments as attach_store, speaker, voice
from .models import set_active
from .approvals import APPROVALS
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
# Loopback only. The core can run shell commands and read the workspace, so
# nothing else on the network should be able to reach it. ARGUS_HOST=0.0.0.0
# opens it up -- only do that on a network you trust.
HOST = os.environ.get("ARGUS_HOST", "127.0.0.1")
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
        set_active(self.router)          # tools that need a model (vision) spend through it
        APPROVALS.attach(self.bus)       # tools that need the user's yes ask through it
        self.watcher = Watcher(self.router, self.bus, self.root,
                               interval=WATCH_INTERVAL, cooldown=WATCH_COOLDOWN)
        self.sensors = Sensors()
        self.watcher.context_fn = self.sensors.context
        self._agent_lock = asyncio.Lock()
        self._agent_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None
        self._sense_task: asyncio.Task | None = None
        self.ready = False

    async def start(self) -> None:
        await self.router.resolve()
        print("[argus] model routing:\n" + self.router.describe(), flush=True)
        print("[argus] sensors: %s" % (", ".join(self.sensors.names) or "(none)"), flush=True)
        print("[argus] vision: %s" % (self.router.vision[0] if self.router.vision else "(none)"),
              flush=True)
        if voice.available() and not USE_FAKE:
            # Load the speech model in the background so the first command is fast.
            asyncio.get_running_loop().run_in_executor(None, voice.warm)
        if not USE_FAKE:
            asyncio.get_running_loop().run_in_executor(None, speaker.warm)
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
            atts = self._known_attachments(msg.get("attachments"))
            if text or atts:
                shown = text or "Have a look at %s." % ", ".join(a["name"] for a in atts)
                goal = shown + attach_store.describe_for_agent(atts)
                asyncio.create_task(self._run_agent(goal, display=shown, attachments=atts))
        elif kind == "user.stop":
            # Cut the current run off right now: the task is cancelled wherever
            # it is (mid model call, mid tool, waiting on an approval card).
            task = self._agent_task
            if task and not task.done():
                task.cancel()
        elif kind == "user.approve":
            # The answer to an agent.approval card. Only a pending id counts.
            if not APPROVALS.resolve(str(msg.get("id", "")), msg.get("approved") is True):
                await self.bus.emit(events.error("That request has already been answered.", fatal=False))
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

    def _known_attachments(self, raw) -> list[dict]:
        """Only accept attachments that really exist in this workspace's
        attachment folder -- a client can't point the agent anywhere else."""
        out = []
        base = os.path.realpath(os.path.join(self.root, attach_store.SUBDIR))
        for a in (raw or [])[:20]:
            if not isinstance(a, dict):
                continue
            rel = str(a.get("path", "")).replace("\\", "/")
            full = os.path.realpath(os.path.join(self.root, rel))
            if os.path.dirname(full) == base and os.path.isfile(full):
                name = os.path.basename(full)
                out.append({"path": rel, "name": name, "bytes": os.path.getsize(full),
                            "kind": attach_store.kind_of(name)})
        return out

    async def _run_agent(self, text: str, display: str | None = None,
                         attachments: list[dict] | None = None) -> None:
        if self._agent_lock.locked():
            await self.bus.emit(events.error(
                "Still working on the previous request -- press stop to cut it off.", fatal=False))
            return
        async with self._agent_lock:
            self._agent_task = asyncio.current_task()
            was_enabled = self.watcher.enabled
            self.watcher.enabled = False          # do not interrupt itself
            try:
                await self.agent.run(text, display=display, attachments=attachments)
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


# Who may talk to the core. A web page you happen to visit can aim requests at
# localhost too, and WebSockets ignore CORS -- so every request is checked here:
#   Host    must be loopback (stops DNS rebinding: evil.com resolving to 127.0.0.1)
#   Origin  if a browser sent one, it must be this hub (Vite on localhost, the
#           desktop app's argus://app) or a browser extension (the tab sensor)
# Requests with no Origin come from local programs (curl, the terminal sensor,
# the desktop shell), which could already read the files directly.
ALLOWED_ORIGIN = re.compile(
    r"^(https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
    r"|argus://app"
    r"|chrome-extension://[a-p]{32}"
    r"|moz-extension://[0-9a-f-]{36})$")
EXTRA_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get("ARGUS_ALLOWED_ORIGINS", "").split(",") if o.strip()}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def refusal(headers: dict[str, str]) -> str | None:
    """Why a request must be refused, or None. Pure, so it can be tested."""
    if HOST in ("127.0.0.1", "localhost", "::1"):
        host = headers.get("host", "")
        name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        if name.lower() not in LOOPBACK_HOSTS:
            return "host"
    origin = headers.get("origin")
    if origin is not None:
        if origin.rstrip("/") not in EXTRA_ORIGINS and not ALLOWED_ORIGIN.match(origin):
            return "origin"
    elif headers.get("sec-fetch-site") == "cross-site":
        return "cross-site"
    return None


class LocalOnly:
    """ASGI guard in front of everything, WebSockets included."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            why = refusal(headers)
            if why:
                print(f"[argus] refused {scope['type']} {scope.get('path')}: {why} "
                      f"(origin={headers.get('origin')!r}, host={headers.get('host')!r})", flush=True)
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"text/plain")]})
                    await send({"type": "http.response.body", "body": b"Argus only talks to its own hub."})
                return
        await self.app(scope, receive, send)


app = FastAPI(title="ARGUS")
app.add_middleware(
    CORSMiddleware, allow_origin_regex=ALLOWED_ORIGIN.pattern, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(LocalOnly)  # added last = runs first

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
        "voice": voice.available(),
        "speaker": speaker.engine(),
        "vision": session.router.vision[0] if session.router.vision else None,
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


@app.post("/attach")
async def attach(request: Request, name: str = "attachment") -> dict:
    """Copy a file the user chose into <workspace>/.argus/attachments/.
    Body is the raw file bytes; ?name= is the original filename."""
    data = await request.body()
    try:
        rec = await asyncio.to_thread(attach_store.save, session.root, name, data)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except OSError as e:
        return {"ok": False, "error": "Could not save the file (%s)" % e.strerror}
    return {"ok": True, **rec}


@app.post("/transcribe")
async def transcribe(request: Request) -> dict:
    """Speech to text, on this machine. Body is the recorded audio."""
    data = await request.body()
    try:
        out = await voice.transcribe(data, request.headers.get("content-type", "audio/webm"))
    except voice.VoiceUnavailable as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **out}


@app.post("/speak")
async def speak(payload: dict) -> Response:
    """Text to speech, on this machine: Argus's voice. Body {"text", "voice"?};
    returns audio/wav."""
    text = str(payload.get("text", ""))[:4000]
    voice_name = payload.get("voice")
    if voice_name is not None and not (isinstance(voice_name, str) and re.fullmatch(r"[a-z]{2}_[a-z]{2,20}", voice_name)):
        return Response(status_code=400, content=b"bad voice name")
    try:
        audio, eng = await speaker.say(text, voice_name)
    except speaker.VoiceUnavailable as e:
        return Response(status_code=503, content=str(e).encode())
    return Response(content=audio, media_type="audio/wav", headers={"x-argus-voice": eng})


@app.get("/voice")
async def voice_info() -> dict:
    return {"engine": speaker.engine(), "voice": speaker.DEFAULT_VOICE, "voices": speaker.voices()}


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
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print(f"[argus] WARNING: listening on {HOST} -- other machines on this network can reach Argus.", flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
