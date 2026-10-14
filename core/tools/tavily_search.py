"""Live web search via Tavily.

Uses advanced search depth with Tavily's synthesized answer, deduplicates by
URL, and returns numbered citations so the planner can cite sources by number
and the UI can render them as links.
"""
from __future__ import annotations
import os
from urllib.parse import urlsplit

from .base import Tool, ToolResult

SNIPPET_CHARS = 700
TIME_RANGES = ("day", "week", "month", "year")


def _norm(url: str) -> str:
    p = urlsplit(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


class TavilySearch(Tool):
    name = "tavily_search"
    description = ("Search the live web for current information. Use for anything "
                   "recent, factual, or that you are not certain of. Returns a short "
                   "synthesized answer plus numbered sources with snippets; cite "
                   "sources by their [number].")
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "A specific search query, as a person would type it."},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10,
                            "description": "How many sources to return. Default 6."},
            "time_range": {"type": "string", "enum": list(TIME_RANGES),
                           "description": "Only return results from this recent window."},
            "topic": {"type": "string", "enum": ["general", "news"],
                      "description": "Use 'news' for current events."},
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 6, time_range: str | None = None,
                  topic: str | None = None) -> ToolResult:
        key = os.environ.get("TAVILY_API_KEY")
        if not key:
            return ToolResult(ok=False, summary="TAVILY_API_KEY is not set")
        query = (query or "").strip()
        if not query:
            return ToolResult(ok=False, summary="empty query")
        try:
            max_results = max(1, min(10, int(max_results)))
        except (TypeError, ValueError):
            max_results = 6

        kwargs = {"search_depth": "advanced", "max_results": max_results,
                  "include_answer": "basic"}
        if time_range in TIME_RANGES:
            kwargs["time_range"] = time_range
        if topic in ("general", "news"):
            kwargs["topic"] = topic

        try:
            from tavily import AsyncTavilyClient
            data = await AsyncTavilyClient(api_key=key).search(query, **kwargs)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate" in msg.lower():
                return ToolResult(ok=False, summary="Tavily rate limit hit; try again shortly")
            return ToolResult(ok=False, summary="search failed: %s" % msg[:160])

        seen, results = set(), []
        for r in data.get("results") or []:
            url = r.get("url") or ""
            k = _norm(url)
            if not url or k in seen:
                continue
            seen.add(k)
            results.append(r)

        if not results:
            return ToolResult(ok=True, summary="no results",
                              detail="No web results for: %s" % query)

        citations, blocks = [], []
        answer = (data.get("answer") or "").strip()
        if answer:
            blocks.append("Summary: %s\n" % answer)
        for i, r in enumerate(results, 1):
            title = (r.get("title") or "").strip() or r["url"]
            snippet = " ".join((r.get("content") or "").split())[:SNIPPET_CHARS]
            blocks.append("[%d] %s\n%s\n%s" % (i, title, r["url"], snippet))
            citations.append({"n": i, "title": title, "url": r["url"],
                              "domain": urlsplit(r["url"]).netloc.removeprefix("www."),
                              "score": round(float(r.get("score") or 0), 3)})

        domains = []
        for c in citations:
            if c["domain"] not in domains:
                domains.append(c["domain"])
        summary = "%d sources · %s" % (len(citations), ", ".join(domains[:3]))
        return ToolResult(ok=True, summary=summary, detail="\n\n".join(blocks),
                          meta={"query": query, "answer": answer, "citations": citations})


TOOL = TavilySearch()
