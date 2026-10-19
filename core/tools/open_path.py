"""Open a file or folder on the user's screen, like double-clicking it."""
from __future__ import annotations
import os, subprocess, sys

from .base import Tool, ToolResult
from ._workspace import OutsideWorkspace, display, resolve
from ..approvals import APPROVALS

# Opening these runs code. They need the user's yes.
RUNS_CODE = {".exe", ".msi", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
             ".wsh", ".scr", ".lnk", ".jar", ".py", ".pyw", ".sh", ".reg", ".hta", ".cpl", ".msc",
             ".appref-ms", ".url"}


def _open(path: str, reveal: bool) -> None:
    if sys.platform == "win32":
        if reveal:
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)      # noqa: S606 -- the default app, exactly like a double-click
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path] if reveal else ["open", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if reveal else path])


class OpenPath(Tool):
    name = "open_path"
    description = ("Open a file in its default app, or a folder in the file explorer, on the user's "
                   "screen. reveal=true shows the file selected in its folder instead. Programs and "
                   "scripts ask the user first.")
    parameters = {"type": "object", "properties": {
        "path": {"type": "string", "description": "File or folder path."},
        "reveal": {"type": "boolean", "description": "Show it in its folder instead of opening it."}},
        "required": ["path"]}
    timeout = 330

    async def run(self, path: str, reveal: bool = False) -> ToolResult:
        try:
            full = resolve(path)
        except OutsideWorkspace as e:
            return ToolResult(ok=False, summary=str(e))
        if not os.path.exists(full):
            return ToolResult(ok=False, summary="nothing at %s" % display(full))
        if not reveal and os.path.splitext(full)[1].lower() in RUNS_CODE:
            if not await APPROVALS.ask("confirm", "Run %s" % os.path.basename(full),
                                       detail="Opening it runs it: %s" % display(full)):
                return ToolResult(ok=False, summary="The user did not approve running %s." % display(full))
        try:
            _open(full, bool(reveal))
        except OSError as e:
            return ToolResult(ok=False, summary="could not open: %s" % e)
        return ToolResult(ok=True, summary="%s %s" % ("Showed" if reveal else "Opened", display(full)))


TOOL = OpenPath()
