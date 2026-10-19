"""Asking the user before Argus does something it can't take back.

A tool that is about to submit a form, upload a file, or hand the browser over
for a sign-in calls `ask()`. That puts a card in front of the user (hub and
floating orb) and waits for their answer. No answer means no: a request that
times out, or that arrives when nobody is connected to answer it, is denied.

Pages can contain instructions aimed at the model. This is the backstop: what
a page talks the model into, the user still has to approve.
"""
from __future__ import annotations
import asyncio, itertools, time
from typing import Literal

from . import events

Kind = Literal["confirm", "handoff"]


class Approvals:
    def __init__(self) -> None:
        self.bus = None
        self.pending: dict[str, asyncio.Future] = {}
        self._ids = itertools.count(1)
        # Tests set this to answer without a UI. None = ask a real person.
        self.auto: bool | None = None

    def attach(self, bus) -> None:
        self.bus = bus

    async def ask(self, kind: Kind, title: str, detail: str = "", url: str = "",
                  timeout: float = 300.0) -> bool:
        """Show a card and wait. True only if the user explicitly said yes."""
        if self.auto is not None:
            return self.auto
        if self.bus is None or self.bus.subscriber_count == 0:
            return False                      # nobody there to say yes
        aid = "ap_%d_%d" % (int(time.time()), next(self._ids))
        fut = asyncio.get_running_loop().create_future()
        self.pending[aid] = fut
        await self.bus.emit(events.approval(aid, kind, title[:200], detail[:600], url[:300],
                                            int(timeout)))
        outcome = "expired"
        try:
            ok = await asyncio.wait_for(fut, timeout)
            outcome = "approved" if ok else "denied"
            return bool(ok)
        except asyncio.TimeoutError:
            return False
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            self.pending.pop(aid, None)
            await self.bus.emit(events.approval_resolved(aid, outcome))

    def resolve(self, aid: str, approved: bool) -> bool:
        fut = self.pending.get(aid)
        if fut is None or fut.done():
            return False
        fut.set_result(bool(approved))
        return True


APPROVALS = Approvals()
