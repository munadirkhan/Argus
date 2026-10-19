"""Type into a field in Argus's browser. Never passwords, payment or ID numbers."""
from __future__ import annotations
import re
from .base import Tool, ToolResult
from . import _web
from ..approvals import APPROVALS

SEARCHY = re.compile(r"search|find|query|keyword|\bq\b|where|what", re.I)


class WebType(Tool):
    name = "web_type"
    description = ("Type text into a field in Argus's browser by its [ref], replacing what is there. "
                   "Refuses password, one-time-code, payment and government-ID fields: the user fills "
                   "those in themselves. submit=true presses Enter afterwards (a search box submits "
                   "freely; any other form asks the user first).")
    parameters = {"type": "object", "properties": {
        "ref": {"type": "string", "description": "The field's [ref]."},
        "text": {"type": "string", "description": "What to type."},
        "submit": {"type": "boolean", "description": "Press Enter afterwards."}},
        "required": ["ref", "text"]}
    timeout = 330

    async def run(self, ref: str, text: str, submit: bool = False):
        s = _web.session()

        async def type_():
            if not isinstance(text, str):
                return ToolResult(ok=False, summary="text must be a string")
            page, loc, info = await s.locate(ref)
            label = info["labelText"] or info["name"] or info["placeholder"] or info["nameAttr"] or "field"
            if _web.is_secret_field(info):
                return ToolResult(ok=False, summary=(
                    '"%s" is a password, code, payment or ID field. Argus never types those. '
                    "If a sign-in is needed, call web_signin so the user does it; otherwise tell "
                    "the user to fill it in Argus's browser themselves." % label[:60]))
            if info["editable"]:
                await loc.click(timeout=8000)
                await page.keyboard.press("Control+A")
                await page.keyboard.type(text, delay=8)
            else:
                await loc.fill(text, timeout=8000)
            if submit:
                harmless = SEARCHY.search(" ".join([label, info["type"], info["nameAttr"], info["id"]]))
                if not harmless:
                    ok = await APPROVALS.ask(
                        "confirm", 'Press Enter in "%s" on %s' % (label[:60], _web.host_of(page.url)),
                        detail="\n".join(info["fields"]), url=page.url)
                    if not ok:
                        return ToolResult(ok=False, summary=(
                            "Typed it, but the user did not approve submitting. Stop and tell them."))
                await loc.press("Enter")
                await page.wait_for_timeout(800)
                page = await s.page()
            return await _web.page_result(s, page, 'Typed into "%s"' % label[:60])
        return await _web.guarded("web_type", type_)


TOOL = WebType()
