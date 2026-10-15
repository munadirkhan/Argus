"""Discovers and runs sensors. Owned by the core lane."""
from __future__ import annotations
import asyncio, importlib, pkgutil, time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .base import Sensor

_SKIP = {"base", "registry", "tests", "fixtures"}
MAX_CONTEXT = 4000


def discover() -> list[Sensor]:
    found: list[Sensor] = []
    for mod in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if mod.name in _SKIP or mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"{__package__}.{mod.name}")
        except Exception as e:
            print(f"[sensors] skipped {mod.name}: {e}")
            continue
        s = getattr(m, "SENSOR", None)
        if isinstance(s, Sensor) and s.name:
            found.append(s)
        else:
            print(f"[sensors] {mod.name} has no valid SENSOR export")
    return found


class Sensors:
    def __init__(self, sensors: list[Sensor] | None = None) -> None:
        self.sensors = discover() if sensors is None else sensors
        self._next: dict[str, float] = {}

    @property
    def names(self) -> list[str]:
        return [s.name for s in self.sensors]

    def context(self) -> str:
        """Everything the sensors currently see, for the watcher's prompt."""
        parts = []
        for s in self.sensors:
            try:
                c = (s.context() or "").strip()
            except Exception:
                c = ""
            if c:
                parts.append("[%s]\n%s" % (s.name, c[:1500]))
        return "\n\n".join(parts)[:MAX_CONTEXT]

    async def tick(self, emit: Callable[[dict], Awaitable[Any]],
                   on_alert: Callable[[Sensor, dict], Awaitable[Any]]) -> int:
        """Poll every sensor that is due. Returns how many events were emitted."""
        now = time.monotonic()
        emitted = 0
        for s in self.sensors:
            if now < self._next.get(s.name, 0):
                continue
            interval = 1.0 if s.interval is None else float(s.interval)
            self._next[s.name] = now + max(0.2, interval)
            try:
                events = await asyncio.wait_for(s.poll(), timeout=3.0)
            except Exception as e:
                print(f"[sensors] {s.name} poll failed: {type(e).__name__}: {e}")
                self._next[s.name] = now + 5.0      # back off instead of spamming
                continue
            for ev in events or []:
                if not isinstance(ev, dict) or ev.get("type") != "activity":
                    continue
                await emit(ev)
                emitted += 1
                try:
                    wake = s.alert(ev)
                except Exception:
                    wake = False
                if wake:
                    await on_alert(s, ev)
        return emitted

    async def run_forever(self, emit, on_alert, period: float = 0.25) -> None:
        while True:
            try:
                await self.tick(emit, on_alert)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[sensors] tick failed: {e}")
            await asyncio.sleep(period)


if __name__ == "__main__":
    ss = Sensors()
    print("%d sensor(s): %s" % (len(ss.sensors), ", ".join(ss.names) or "(none)"))
