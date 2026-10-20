"""Run a shell command in the workspace. OFF unless ARGUS_ALLOW_SHELL=1.

A model that reads the web can be talked into things. File tools are confined
to the workspace; a shell cannot be confined the same way, so it is opt-in.
"""
from __future__ import annotations
import asyncio, os

from .base import Tool, ToolResult
from ._workspace import root

TIMEOUT_S = 20
MAX_OUTPUT = 8000


def enabled() -> bool:
    return os.environ.get("ARGUS_ALLOW_SHELL", "").lower() in ("1", "true", "yes")


class Shell(Tool):
    name = "shell"
    description = ("Run a shell command with the workspace as the working directory. "
                   "20 second limit. Prefer the file tools for reading and writing.")
    dangerous = True
    parameters = {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The command to run."}},
        "required": ["command"],
    }

    async def run(self, command: str) -> ToolResult:
        if not enabled():
            return ToolResult(ok=False, summary="shell is disabled (set ARGUS_ALLOW_SHELL=1)")
        command = (command or "").strip()
        if not command:
            return ToolResult(ok=False, summary="empty command")
        try:
            proc = await asyncio.create_subprocess_shell(
                command, cwd=root(), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
        except Exception as e:
            return ToolResult(ok=False, summary="could not start: %s" % e)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(ok=False, summary="timed out after %ds" % TIMEOUT_S)
        except asyncio.CancelledError:
            proc.kill()                     # the user pressed stop
            raise
        text = (out or b"").decode("utf-8", errors="replace")
        if len(text) > MAX_OUTPUT:
            text = text[:MAX_OUTPUT] + "\n...[truncated]"
        return ToolResult(ok=proc.returncode == 0,
                          summary="exit %d · %d lines" % (proc.returncode, text.count("\n")),
                          detail=text or "(no output)",
                          meta={"exit_code": proc.returncode})


TOOL = Shell()
