"""Look at an image in the workspace with Nemotron 3.5 Super VL.

The text models can't see, so screenshots and photos the user attaches go to
NVIDIA's vision-language model on Token Factory. The call is routed through
the server's ModelRouter, so it is refused by the spend cap like any other.
"""
from __future__ import annotations
import base64, os

from .base import Tool, ToolResult
from ._workspace import OutsideWorkspace, display, resolve

MAX_BYTES = 10 * 1024 * 1024
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
DEFAULT_Q = ("Describe this image precisely and completely. Transcribe any text, code, error "
             "messages, numbers or UI labels exactly as written.")


class ViewImage(Tool):
    name = "view_image"
    description = ("Look at an image file in the workspace (screenshot, photo, diagram, "
                   "chart) and get a precise description, including any text in it. "
                   "Pass a question to focus on something specific.")
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Image path, relative to the workspace or absolute."},
            "question": {"type": "string", "description": "Optional: what to look for."},
        },
        "required": ["path"],
    }

    async def run(self, path: str, question: str = "") -> ToolResult:
        from ..models import BudgetExceeded, active_router
        try:
            full = resolve(path)
        except OutsideWorkspace as e:
            return ToolResult(ok=False, summary=str(e))
        name = display(full)
        ext = os.path.splitext(full)[1].lower()
        if ext not in MIME:
            return ToolResult(ok=False, summary="%s is not an image I can view" % name)
        if not os.path.isfile(full):
            return ToolResult(ok=False, summary="no such file: %s" % name)
        if os.path.getsize(full) > MAX_BYTES:
            return ToolResult(ok=False, summary="%s is over 10 MB" % name)
        router = active_router()
        if router is None:
            return ToolResult(ok=False, summary="vision is not available in this session")
        with open(full, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        q = (question or "").strip() or DEFAULT_Q
        try:
            text, u = await router.see(b64, MIME[ext], q)
        except BudgetExceeded as e:
            return ToolResult(ok=False, summary=str(e))
        except Exception as e:
            return ToolResult(ok=False, summary="vision failed: %s" % str(e)[:160])
        if not text:
            return ToolResult(ok=False, summary="the vision model returned nothing for %s" % name)
        return ToolResult(ok=True, summary="%s · seen by Nemotron VL" % name, detail=text,
                          meta={"path": full, "model": u["model"], "cost_usd": u["cost_usd"]})


TOOL = ViewImage()
