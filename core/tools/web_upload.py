"""Attach a workspace file (a resume, say) to a page in Argus's browser."""
from __future__ import annotations
import os
from .base import Tool, ToolResult
from . import _web
from ._workspace import OutsideWorkspace, display, resolve
from ..approvals import APPROVALS


class WebUpload(Tool):
    name = "web_upload"
    description = ("Upload a file from the user's workspace (e.g. their resume) through a file field or "
                   "upload button, by [ref]. Always asks the user first. Only workspace files.")
    parameters = {"type": "object", "properties": {
        "ref": {"type": "string", "description": "The file field's or upload button's [ref]."},
        "path": {"type": "string", "description": "File path relative to the workspace."}},
        "required": ["ref", "path"]}
    timeout = 330

    async def run(self, ref: str, path: str):
        s = _web.session()

        async def upload():
            try:
                full = resolve(path)
            except OutsideWorkspace as e:
                return ToolResult(ok=False, summary=str(e))
            if not os.path.isfile(full):
                return ToolResult(ok=False, summary="No file %s in the workspace." % display(full))
            page, loc, info = await s.locate(ref)
            name = os.path.basename(full)
            ok = await APPROVALS.ask("confirm", "Upload %s to %s" % (name, _web.host_of(page.url)),
                                     detail="From your workspace: %s" % display(full), url=page.url)
            if not ok:
                return ToolResult(ok=False, summary="The user did not approve uploading %s." % name)
            if info["tag"] == "input" and info["type"] == "file":
                await loc.set_input_files(full, timeout=8000)
            else:
                async with page.expect_file_chooser(timeout=8000) as chooser:
                    await loc.click(timeout=5000)
                await (await chooser.value).set_files(full)
            await page.wait_for_timeout(800)
            return await _web.page_result(s, page, "Uploaded %s" % name)
        return await _web.guarded("web_upload", upload)


TOOL = WebUpload()
