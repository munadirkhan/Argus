"""Click something in Argus's browser. Final buttons wait for the user's yes."""
from __future__ import annotations
from .base import Tool, ToolResult
from . import _web
from ..approvals import APPROVALS


class WebClick(Tool):
    name = "web_click"
    description = ("Click an element in Argus's browser by its [ref] from the latest page snapshot. "
                   "Clicks that submit, apply, pay, post, delete or agree first ask the user; if they "
                   "say no, stop and tell them.")
    parameters = {"type": "object", "properties": {
        "ref": {"type": "string", "description": "The element's [ref], e.g. \"12\" or \"f1:4\"."}},
        "required": ["ref"]}
    timeout = 330          # may wait for the user

    async def run(self, ref: str):
        s = _web.session()

        async def click():
            page, loc, info = await s.locate(ref)
            label = info["name"][:80] or info["tag"]
            if _web.is_consequential(info):
                detail = "\n".join(info["fields"]) if info["fields"] else ""
                ok = await APPROVALS.ask(
                    "confirm", 'Click "%s" on %s' % (label, _web.host_of(page.url)),
                    detail=detail, url=page.url)
                if not ok:
                    return ToolResult(ok=False, summary=(
                        'The user did not approve clicking "%s". Do not try another way -- '
                        "stop and tell them what is ready." % label))
            await loc.click(timeout=8000)
            await page.wait_for_timeout(700)
            # A click may have opened a new tab; follow it.
            page = await s.page()
            return await _web.page_result(s, page, 'Clicked "%s"' % label)
        return await _web.guarded("web_click", click)


TOOL = WebClick()
