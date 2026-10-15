"""Base type for ARGUS sensors. Owned by the core lane -- do not edit in the web lane.

A sensor watches one part of the user's world -- a dev server's log, the tab
they're reading -- and reports it as `activity` events (docs/EVENT_CONTRACT.md).
The core lane polls sensors, forwards their events to the UI, feeds their
context to the watcher, and wakes the watcher immediately on an alert.

Contract: docs/SENSOR_CONTRACT.md. One sensor = one file in core/sensors/,
exporting SENSOR. The registry finds it; nothing else needs to change.
"""
from __future__ import annotations
from typing import Any


class Sensor:
    name: str = ""
    interval: float = 1.0          # seconds between polls

    async def poll(self) -> list[dict[str, Any]]:
        """New `activity` payloads since the last poll ([] if nothing changed).

        Payload shape, without the envelope:
          {"type": "activity", "source": "terminal", "app": "Terminal",
           "title": "npm run dev", "lines": [{"text": "...", "tone": "err"}],
           "focus": True}
        Must not raise. Must return within ~2 seconds.
        """
        return []

    def context(self) -> str:
        """What this sensor sees right now, as plain text for the watcher's
        prompt (e.g. the last 20 log lines). Keep it under ~1,500 chars."""
        return ""

    def receive(self, payload: dict[str, Any]) -> bool:
        """Data pushed to this sensor over HTTP (POST /sense/<name>), e.g. by a
        browser extension. Store it and report it from the next poll(). Return
        False to reject the payload. Default: sensor does not accept pushes."""
        return False

    def alert(self, event: dict[str, Any]) -> bool:
        """Should this event wake the watcher now instead of at its next tick?
        Default: any line with tone "err". Override to be smarter, and make sure
        the same error does not alert twice."""
        return any(l.get("tone") == "err" for l in event.get("lines") or [])
