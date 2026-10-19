"""Look at the page Argus's browser is on right now."""
from __future__ import annotations
from .base import Tool
from . import _web


class WebLook(Tool):
    name = "web_look"
    description = ("Look at the current page in Argus's browser again: its elements as [ref]s and its "
                   "text. Use after the page changed on its own, or with scroll=true to load more of a "
                   "long page.")
    parameters = {"type": "object", "properties": {
        "find": {"type": "string", "description": "Optional text to focus the page text on."},
        "scroll": {"type": "boolean", "description": "Scroll down one screen first."}}}
    timeout = 45

    async def run(self, find: str = "", scroll: bool = False):
        s = _web.session()

        async def look():
            page = await s.page()
            if scroll:
                await page.mouse.wheel(0, 900)
                await page.wait_for_timeout(600)
            return await _web.page_result(s, page, "Looked", find)
        return await _web.guarded("web_look", look)


TOOL = WebLook()
