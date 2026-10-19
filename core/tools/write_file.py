"""Write a file into the workspace. The artifact ARGUS hands back to the user."""
from __future__ import annotations
import os

from .base import Tool, ToolResult
from ._workspace import OutsideWorkspace, display, human_size, inside_workspace, resolve
from ..approvals import APPROVALS

MAX_BYTES = 2_000_000


class WriteFile(Tool):
    timeout = 330          # may wait for the user
    name = "write_file"
    description = ("Write a file to the user's workspace, creating folders as "
                   "needed. Overwrites by default. Write complete, finished content "
                   "-- this is what the user will read. Use markdown for documents.")
    dangerous = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace, or an absolute path (anywhere on the PC when full access is on)."},
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
        if not inside_workspace(full):
            # Anywhere else on the PC: the user says yes to this exact write.
            exists = os.path.isfile(full)
            what = ("appends %s to it" % human_size(len(data)) if append and exists else
                    "replaces it (%s now, %s after)" % (human_size(os.path.getsize(full)),
                                                          human_size(len(data))) if exists else
                    "creates it (%s)" % human_size(len(data)))
            preview = (content or "")[:300]
            if not await APPROVALS.ask("confirm", "Write %s" % display(full),
                                       detail="This %s.\n\n%s" % (what, preview)):
                return ToolResult(ok=False, summary=(
                    "The user did not approve writing %s. Write inside the workspace instead, or "
                    "stop and tell them." % display(full)))
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
