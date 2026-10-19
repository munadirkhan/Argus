"""Pick an option, or tick / untick a box, in Argus's browser."""
from __future__ import annotations
from .base import Tool, ToolResult
from . import _web
from ..approvals import APPROVALS

YES = {"yes", "true", "on", "check", "checked", "tick", "1"}
NO = {"no", "false", "off", "uncheck", "unchecked", "untick", "0"}


class WebChoose(Tool):
    name = "web_choose"
    description = ("Choose in a dropdown, or tick/untick a checkbox, radio button or switch, by [ref]. "
                   "For a dropdown pass the option's visible text; for a box pass \"yes\" or \"no\". "
                   "Ticking a box that agrees to terms asks the user first.")
    parameters = {"type": "object", "properties": {
        "ref": {"type": "string", "description": "The element's [ref]."},
        "option": {"type": "string", "description": "Option text, or yes/no for a box."}},
        "required": ["ref", "option"]}
    timeout = 330

    async def run(self, ref: str, option: str):
        s = _web.session()

        async def choose():
            page, loc, info = await s.locate(ref)
            label = (info["labelText"] or info["name"] or "field")[:80]
            want = str(option).strip()
            if info["tag"] == "select":
                try:
                    await loc.select_option(label=want, timeout=5000)
                except Exception:
                    await loc.select_option(value=want, timeout=5000)
                return await _web.page_result(s, page, 'Chose "%s" in "%s"' % (want[:40], label))
            if info["type"] in ("checkbox", "radio") or want.lower() in YES | NO:
                on = want.lower() not in NO
                if on and _web.is_consequential(info):
                    ok = await APPROVALS.ask("confirm", 'Tick "%s" on %s' % (label, _web.host_of(page.url)),
                                             url=page.url)
                    if not ok:
                        return ToolResult(ok=False, summary='The user did not approve ticking "%s".' % label)
                if info["type"] in ("checkbox", "radio"):
                    await (loc.check if on else loc.uncheck)(timeout=5000)
                else:
                    await loc.click(timeout=5000)      # a custom switch or ARIA checkbox
                return await _web.page_result(s, page, '%s "%s"' % ("Ticked" if on else "Unticked", label))
            # A custom dropdown: open it, then click the option by its text.
            await loc.click(timeout=5000)
            await page.wait_for_timeout(400)
            target = page.get_by_role("option", name=want, exact=False)
            if await target.count() == 0:
                target = page.get_by_text(want, exact=True)
            await target.first.click(timeout=5000)
            return await _web.page_result(s, page, 'Chose "%s" in "%s"' % (want[:40], label))
        return await _web.guarded("web_choose", choose)


TOOL = WebChoose()
