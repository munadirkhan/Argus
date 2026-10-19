"""Hand Argus's browser to the user so they can sign in themselves.

Argus never sees or types a password. It opens the sign-in page in its own
browser, brings the window to the front, and waits until the user presses
DONE. The profile keeps them signed in for next time.
"""
from __future__ import annotations
from .base import Tool, ToolResult
from . import _web
from ..approvals import APPROVALS


class WebSignin(Tool):
    name = "web_signin"
    description = ("When a site needs the user signed in (a login page, 'sign in to apply'), open its "
                   "sign-in page in Argus's browser and let the USER sign in -- Argus never types "
                   "passwords. Waits until they press DONE (up to 15 minutes). Sign-ins persist, so "
                   "check with web_open first whether they already are.")
    parameters = {"type": "object", "properties": {
        "url": {"type": "string", "description": "The sign-in page URL (or the page that needs it)."},
        "site": {"type": "string", "description": "Short site name for the user, e.g. LinkedIn."}},
        "required": ["url"]}
    timeout = 930

    async def run(self, url: str, site: str = ""):
        s = _web.session()

        async def signin():
            await s.check_url(url)
            page = await s.page()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.bring_to_front()
            name = (site or _web.host_of(page.url))[:40]
            done = await APPROVALS.ask(
                "handoff", "Sign in to %s in Argus's browser" % name,
                detail=("Argus's browser window is open at the sign-in page. Sign in there yourself -- "
                        "Argus never sees or types your password. Press DONE when you're in."),
                url=page.url, timeout=900)
            if not done:
                return ToolResult(ok=False, summary=(
                    "The user did not sign in to %s. Stop and tell them the task needs it." % name))
            page = await s.page()
            return await _web.page_result(s, page, "Signed in to %s" % name)
        return await _web.guarded("web_signin", signin)


TOOL = WebSignin()
