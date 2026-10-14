"""List the workspace as an indented tree with sizes."""
from __future__ import annotations
import os

from .base import Tool, ToolResult
from ._workspace import SKIP_DIRS, OutsideWorkspace, display, human_size, resolve

MAX_ENTRIES = 300


class ListDir(Tool):
    name = "list_dir"
    description = ("List files and folders in the user's workspace, with sizes. "
                   "Start here to see what you have to work with.")
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Folder, relative to the workspace. Default '.'."},
            "depth": {"type": "integer", "minimum": 1, "maximum": 4,
                      "description": "How many levels deep. Default 2."},
        },
    }

    async def run(self, path: str = ".", depth: int = 2) -> ToolResult:
        try:
            top = resolve(path)
        except OutsideWorkspace as e:
            return ToolResult(ok=False, summary=str(e))
        if not os.path.isdir(top):
            return ToolResult(ok=False, summary="not a folder: %s" % display(top))
        try:
            depth = max(1, min(4, int(depth)))
        except (TypeError, ValueError):
            depth = 2

        lines, files, dirs, truncated = [], 0, 0, False

        def walk(d: str, level: int) -> None:
            nonlocal files, dirs, truncated
            try:
                entries = sorted(os.scandir(d), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                return
            for e in entries:
                if len(lines) >= MAX_ENTRIES:
                    truncated = True
                    return
                if e.name.startswith(".") or e.name in SKIP_DIRS:
                    continue
                pad = "  " * level
                if e.is_dir(follow_symlinks=False):
                    dirs += 1
                    lines.append("%s%s/" % (pad, e.name))
                    if level + 1 < depth:
                        walk(e.path, level + 1)
                else:
                    files += 1
                    try:
                        size = e.stat().st_size
                    except OSError:
                        size = 0
                    lines.append("%s%s  (%s)" % (pad, e.name, human_size(size)))

        walk(top, 0)
        header = "%s/" % (display(top) if display(top) != "." else "workspace")
        body = "\n".join(lines) if lines else "(empty)"
        if truncated:
            body += "\n... (truncated at %d entries)" % MAX_ENTRIES
        return ToolResult(ok=True, summary="%d files, %d folders" % (files, dirs),
                          detail=header + "\n" + body,
                          meta={"path": top, "files": files, "dirs": dirs})


TOOL = ListDir()
