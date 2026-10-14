"""Read a web page as clean text.

Tavily Extract first (clean markdown, handles JS-heavy pages), plain HTTP with
a crude HTML strip as the fallback so a Tavily outage doesn't blind the agent.
"""
from __future__ import annotations
import html, os, re
from urllib.parse import urlsplit

from .base import Tool, ToolResult

MAX_CHARS = 12000


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


class FetchUrl(Tool):
    name = "fetch_url"
    description = ("Read the full text of a web page, e.g. a source found by "
                   "tavily_search. Use when a snippet isn't enough.")
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Full http(s) URL."}},
        "required": ["url"],
    }

    async def run(self, url: str) -> ToolResult:
        url = (url or "").strip()
        if urlsplit(url).scheme not in ("http", "https"):
            return ToolResult(ok=False, summary="only http(s) URLs can be fetched")
        domain = urlsplit(url).netloc.removeprefix("www.")

        key = os.environ.get("TAVILY_API_KEY")
        if key:
            try:
                from tavily import AsyncTavilyClient
                data = await AsyncTavilyClient(api_key=key).extract(
                    url, format="markdown", timeout=20)
                hits = data.get("results") or []
                text = (hits[0].get("raw_content") or "").strip() if hits else ""
                if text:
                    return ToolResult(ok=True, summary="%s · %d chars" % (domain, len(text)),
                                      detail=text[:MAX_CHARS],
                                      meta={"url": url, "via": "tavily_extract",
                                            "chars": len(text)})
            except Exception:
                pass                        # fall through to plain HTTP

        try:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=15,
                                         headers={"User-Agent": "ARGUS/1.0"}) as c:
                r = await c.get(url)
            if r.status_code >= 400:
                return ToolResult(ok=False, summary="HTTP %d from %s" % (r.status_code, domain))
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return ToolResult(ok=False, summary="not a text page (%s)" % ctype[:40])
            text = _strip_html(r.text)
            return ToolResult(ok=True, summary="%s · %d chars" % (domain, len(text)),
                              detail=text[:MAX_CHARS],
                              meta={"url": url, "via": "http", "chars": len(text)})
        except Exception as e:
            return ToolResult(ok=False, summary="fetch failed: %s" % str(e)[:140])


TOOL = FetchUrl()
