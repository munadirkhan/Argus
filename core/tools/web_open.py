"""Open a page in Argus's own (visible, signed-in) browser."""
from __future__ import annotations
from .base import Tool
from . import _web


class WebOpen(Tool):
    name = "web_open"
    description = ("Open a URL in Argus's own browser -- a real, visible browser where the user may "
                   "already be signed in. Use it to DO things on websites (fill forms, apply, navigate "
                   "an account). Returns the page's clickable/typeable elements as [ref]s. For just "
                   "reading a page, fetch_url is cheaper.")
    parameters = {"type": "object", "properties": {
        "url": {"type": "string", "description": "Public http(s) URL."},
        "find": {"type": "string", "description": "Optional text to focus the page text on."}},
        "required": ["url"]}
    timeout = 60

    async def run(self, url: str, find: str = ""):
        s = _web.session()

        async def go():
            await s.check_url(url)
            page = await s.page()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await s.check_url(page.url)
            await page.bring_to_front()
            return await _web.page_result(s, page, "Opened", find)
        return await _web.guarded("web_open", go)


TOOL = WebOpen()
