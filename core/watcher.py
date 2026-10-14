"""The watcher: ARGUS noticing things without being asked.

This is the Jarvis moment, and it is mostly an exercise in restraint. The
watcher scans the workspace on an interval, diffs it against the last scan, and
only when something concrete changed does it ask the cheap model whether a
competent colleague would actually say something.

It runs on Nemotron 3.5 Lightning: 1M context at $0.06/M input, which is what
makes "always on" affordable. A full scan-and-consider cycle costs a fraction
of a cent, so this can run every 20 seconds for hours.
"""
from __future__ import annotations
import asyncio, itertools, os, time
from dataclasses import dataclass, field

from . import events
from .agent import extract_json
from .bus import EventBus
from .models import BudgetExceeded, ModelRouter
from .prompts import WATCHER_SYSTEM

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
             "dist", "build", ".idea", ".vscode", ".pytest_cache"}
MAX_FILES = 400


@dataclass
class Snapshot:
    taken_at: float
    files: dict = field(default_factory=dict)      # path -> (mtime, size)

    def diff(self, previous: "Snapshot | None"):
        """Return (added, modified, removed) path lists."""
        if previous is None:
            return [], [], []
        added, modified = [], []
        for p, (mt, sz) in self.files.items():
            prev = previous.files.get(p)
            if prev is None:
                added.append(p)
            elif prev[0] != mt or prev[1] != sz:
                modified.append(p)
        removed = [p for p in previous.files if p not in self.files]
        return added, modified, removed


def scan(root: str) -> Snapshot:
    """Cheap recursive scan of a workspace."""
    files: dict = {}
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            files[full.replace("\\", "/")] = (int(st.st_mtime), st.st_size)
            if len(files) >= MAX_FILES:
                return Snapshot(time.time(), files)
    return Snapshot(time.time(), files)


def rel(path: str, root: str | None) -> str:
    """relpath that never raises: on Windows it fails across drives."""
    if not root:
        return os.path.basename(path)
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


PEEK_FILES = 4
PEEK_CHARS = 700
PEEK_MAX_BYTES = 5_000_000
TEXT_EXTS = {".md", ".txt", ".py", ".js", ".ts", ".tsx", ".json", ".csv", ".yaml",
             ".yml", ".toml", ".html", ".tex", ".rst", ".ipynb"}


def peek(path: str) -> str | None:
    """First few hundred characters of a file, so the watcher knows what it is
    looking at -- dated notes full of open questions read very differently
    from a fresh blank page. None means 'not something we can peek into'."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size == 0:
        return ""
    if size > PEEK_MAX_BYTES:
        return None
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            pages = PdfReader(path).pages
            text = (pages[0].extract_text() or "") if len(pages) else ""
        elif ext in TEXT_EXTS:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read(PEEK_CHARS * 2)
        else:
            return None
    except Exception:
        return None
    return " ".join(text.split())[:PEEK_CHARS]


def human_size(n: int) -> str:
    if n == 0:
        return "empty"
    if n < 1024:
        return "%d bytes" % n
    if n < 1024 * 1024:
        return "%.0f KB" % (n / 1024)
    return "%.1f MB" % (n / (1024 * 1024))


def describe_changes(added, modified, removed, limit: int = 12,
                     root: str | None = None, sizes: dict | None = None) -> str:
    """Plain-text change summary for the model.

    Sizes matter: "notes.md (empty)" next to two new PDFs is the signal that
    someone is about to write something, and filenames alone hide it.
    """
    def name(p: str) -> str:
        shown = rel(p, root)
        if sizes and p in sizes:
            shown += " (%s)" % human_size(sizes[p])
        return shown

    parts = []
    for label, paths in (("added", added), ("modified", modified), ("removed", removed)):
        if paths:
            shown = [name(p) for p in paths[:limit]]
            more = "" if len(paths) <= limit else " (+%d more)" % (len(paths) - limit)
            parts.append("%s: %s%s" % (label, ", ".join(shown), more))
    return "\n".join(parts)


class Watcher:
    def __init__(self, router: ModelRouter, bus: EventBus, root: str,
                 interval: float = 20.0, cooldown: float = 120.0,
                 min_changes: int = 1) -> None:
        self.router = router
        self.bus = bus
        self.root = os.path.abspath(root)
        self.interval = interval
        self.cooldown = cooldown
        self.min_changes = min_changes
        self.previous: Snapshot | None = None
        self.last_spoke_at = 0.0
        self.dismissed: set[str] = set()
        self.pending: dict[str, dict] = {}
        self.seen: dict[str, dict] = {}         # every observation ever made
        self._ids = itertools.count(1)
        self.enabled = True

    def dismiss(self, obs_id: str) -> None:
        self.dismissed.add(obs_id)
        self.pending.pop(obs_id, None)

    async def emit_tree(self, snap: Snapshot) -> None:
        nodes = [{"path": p, "dir": False, "bytes": sz}
                 for p, (_mt, sz) in sorted(snap.files.items())[:200]]
        await self.bus.emit(events.fs_tree(self.root, nodes))

    async def tick(self) -> dict | None:
        """One scan-and-consider cycle. Returns the observation if it spoke."""
        snap = scan(self.root)
        added, modified, removed = snap.diff(self.previous)
        first_scan = self.previous is None
        self.previous = snap

        if first_scan:
            await self.emit_tree(snap)
            return None

        changes = len(added) + len(modified) + len(removed)
        if changes:
            await self.emit_tree(snap)
        if changes < self.min_changes:
            return None
        if time.time() - self.last_spoke_at < self.cooldown:
            return None

        return await self.consider(added, modified, removed)

    async def consider(self, added, modified, removed) -> dict | None:
        """Ask the cheap model whether this is worth interrupting for."""
        r = self.router.for_tier("watcher")
        await self.bus.emit(events.agent_thinking("watcher", r.model_id, "Observing workspace"))

        files = self.previous.files if self.previous else {}
        sizes = {p: sz for p, (_mt, sz) in files.items()}
        summary = describe_changes(added, modified, removed, root=self.root, sizes=sizes)
        inventory = "\n".join(
            "- %s (%s)" % (rel(p, self.root), human_size(sz))
            for p, sz in sorted(sizes.items())[:60])
        peeks = []
        for p in (added + modified)[:PEEK_FILES]:
            excerpt = peek(p)
            if excerpt is not None:
                peeks.append("--- %s ---\n%s" % (rel(p, self.root), excerpt or "(empty)"))
        user = ("Today: %s\nWorkspace: %s\n\nRecent changes:\n%s\n\nCurrent files:\n%s"
                % (time.strftime("%Y-%m-%d"), self.root, summary or "(none)", inventory))
        if peeks:
            user += "\n\nOpening lines of the new or changed files:\n" + "\n\n".join(peeks)

        try:
            msg, u = await self.router.complete(
                "watcher",
                [{"role": "system", "content": WATCHER_SYSTEM},
                 {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                max_tokens=300, temperature=0.4,
            )
        except BudgetExceeded as e:
            self.enabled = False                # go quiet; do not retry every tick
            await self.bus.emit(events.error("watcher paused: %s" % e, fatal=False))
            return None
        except Exception as e:
            await self.bus.emit(events.error("watcher: %s" % e, fatal=False))
            return None

        await self.bus.emit(events.usage(
            u["tier"], u["model"], u["prompt_tokens"], u["completion_tokens"],
            u["cost_usd"], u["cumulative_cost_usd"]))

        parsed = extract_json(getattr(msg, "content", "") or "") or {}
        if not parsed.get("speak"):
            return None

        observation = str(parsed.get("observation", "")).strip()
        suggestion = str(parsed.get("suggestion", "")).strip()
        if not observation or not suggestion:
            return None

        try:
            confidence = float(parsed.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        obs_id = "obs_%d" % next(self._ids)
        self.last_spoke_at = time.time()
        self.pending[obs_id] = {"observation": observation, "suggestion": suggestion}
        self.seen[obs_id] = self.pending[obs_id]
        await self.bus.emit(events.watcher_observation(
            obs_id, observation, suggestion, confidence))
        return {"id": obs_id, "observation": observation, "suggestion": suggestion,
                "confidence": confidence}

    async def run_forever(self) -> None:
        while True:
            try:
                if self.enabled:
                    await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await self.bus.emit(events.error("watcher tick: %s" % e, fatal=False))
            await asyncio.sleep(self.interval)
