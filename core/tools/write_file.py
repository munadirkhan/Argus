"""Write a file into the workspace. The artifact ARGUS hands back to the user."""
from __future__ import annotations
import os

from .base import Tool, ToolResult
from ._workspace import OutsideWorkspace, display, human_size, resolve

MAX_BYTES = 2_000_000


class WriteFile(Tool):
    name = "write_file"
    description = ("Write a file to the user's workspace, creating folders as "
                   "needed. Overwrites by default. Write complete, finished content "
                   "-- this is what the user will read. Use markdown for documents.")
    dangerous = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace."},
            "content": {"type": "string", "description": "The full file contents."},
            "append": {"type": "boolean", "description": "Append instead of overwrite."},
        },
        "required": ["path", "content"],
    }

    async def run(self, path: str, content: str, append: bool = False) -> ToolResult:
        try:
            full = resolve(path)
        except OutsideWorkspace as e:
            return ToolResult(ok=False, summary=str(e))
        if os.path.isdir(full):
            return ToolResult(ok=False, summary="%s is a directory" % display(full))
        data = (content or "").encode("utf-8")
        if len(data) > MAX_BYTES:
            return ToolResult(ok=False, summary="refusing to write %s" % human_size(len(data)))
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "ab" if append else "wb") as f:
                f.write(data)
        except OSError as e:
            return ToolResult(ok=False, summary="write failed: %s" % e)
        verb = "appended to" if append else "written to"
        return ToolResult(ok=True,
                          summary="%s %s %s" % (human_size(len(data)), verb, display(full)),
                          meta={"path": full, "bytes": len(data)})


TOOL = WriteFile()
