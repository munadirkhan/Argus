"""End-to-end agent test with no API key and no network.

Proves the full plan -> execute -> synthesise loop, tool dispatch, event
ordering, and cost accounting, using a scripted fake model and stub tools.

Run:  python scripts/test_agent_offline.py
"""
import asyncio, json, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent, extract_json
from core.bus import EventBus
from core.fake import FakeClient, Turn
from core.models import ModelRouter
from core.tools.base import Tool, ToolResult
from core.tools.registry import Registry


# --- stub tools (the real ones are the web lane's job) ------------------
class StubSearch(Tool):
    name = "tavily_search"
    description = "Search the live web."
    parameters = {"type": "object",
                  "properties": {"query": {"type": "string"}},
                  "required": ["query"]}

    async def run(self, query, max_results=5):
        return ToolResult(ok=True, summary="3 results",
                          detail="arxiv 2608.11234 - consistency-matched samplers",
                          meta={"urls": ["https://arxiv.org/abs/2608.11234"]})


class StubWrite(Tool):
    name = "write_file"
    description = "Write a file to disk."
    dangerous = True
    parameters = {"type": "object",
                  "properties": {"path": {"type": "string"},
                                 "content": {"type": "string"}},
                  "required": ["path", "content"]}

    async def run(self, path, content):
        return ToolResult(ok=True, summary="%d bytes written" % len(content),
                          meta={"bytes": len(content)})


class StubBoom(Tool):
    name = "boom"
    description = "Always fails, to prove errors are contained."
    parameters = {"type": "object", "properties": {}}

    async def run(self):
        raise RuntimeError("intentional")


SCRIPT = {
    "ultra": [
        Turn(text=json.dumps({"steps": [
            {"title": "Search recent literature"},
            {"title": "Write summary to notes.md", "tools": ["write_file"]}]}),
            prompt_tokens=3200, completion_tokens=640),
        Turn(text="Written to notes.md. The June result your local paper builds on "
                  "was superseded in August - worth checking before you go further.",
             prompt_tokens=4100, completion_tokens=180),
    ],
    "nano": [
        Turn(tool_calls=[("tavily_search", {"query": "diffusion sampling 2026"})],
             prompt_tokens=1900, completion_tokens=180),
        Turn(text="Found 3 relevant papers, newest from August.",
             prompt_tokens=2400, completion_tokens=90),
        Turn(tool_calls=[("write_file", {"path": "C:/notes/notes.md",
                                         "content": "# Diffusion sampling\n\nthree things moved."})],
             prompt_tokens=2600, completion_tokens=210),
        Turn(text="Wrote the summary to notes.md.",
             prompt_tokens=2800, completion_tokens=70),
    ],
}


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -- " + detail) if detail and not cond else ""))
    return cond


async def main():
    print("=== extract_json robustness ===")
    fence = chr(96) * 3
    ok = True
    ok &= check("bare json", extract_json('{"steps":[]}') == {"steps": []})
    ok &= check("fenced json",
                extract_json(fence + 'json\n{"a":1}\n' + fence) == {"a": 1})
    ok &= check("json with prose",
                extract_json('Sure! {"a":2} hope that helps') == {"a": 2})
    ok &= check("garbage returns None", extract_json("no json here") is None)
    ok &= check("empty returns None", extract_json("") is None)

    print("\n=== full agent run ===")
    bus = EventBus()
    seen = []

    async def collect():
        async for e in bus.subscribe(replay=False):
            seen.append(e)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    router = ModelRouter(api_key="fake", client_factory=FakeClient.factory(SCRIPT))
    await router.resolve()

    registry = Registry()
    registry.tools = {t.name: t for t in (StubSearch(), StubWrite(), StubBoom())}

    agent = Agent(router, registry, bus)
    answer = await agent.run("summarise what changed in diffusion sampling")
    await asyncio.sleep(0.05)
    task.cancel()

    types = [e["type"] for e in seen]
    print("\n  %d events emitted" % len(seen))
    print("  sequence: " + " -> ".join(types[:8]) + " ...")

    ok &= check("seq is strictly increasing",
                [e["seq"] for e in seen] == list(range(1, len(seen) + 1)))
    ok &= check("every event has envelope",
                all(e.get("v") == 1 and "ts" in e for e in seen))
    ok &= check("plan emitted", "agent.plan" in types)
    ok &= check("two steps planned",
                len(next(e for e in seen if e["type"] == "agent.plan")["steps"]) == 2)
    ok &= check("both tools called",
                {e["name"] for e in seen if e["type"] == "tool.call"}
                == {"tavily_search", "write_file"})
    ok &= check("artifact emitted", "artifact.write" in types)
    ok &= check("all steps done",
                all(e["status"] == "done"
                    for e in seen if e["type"] == "agent.step" and e["status"] != "running"))
    ok &= check("final assistant message",
                any(e["type"] == "agent.message" and e["role"] == "assistant" for e in seen))
    ok &= check("no fatal errors",
                not any(e["type"] == "error" and e.get("fatal") for e in seen))

    tiers_used = {e["tier"] for e in seen if e["type"] == "agent.thinking"}
    ok &= check("both tiers visible in HUD", tiers_used == {"planner", "executor"},
                str(tiers_used))

    usages = [e for e in seen if e["type"] == "usage"]
    ok &= check("usage emitted per model call", len(usages) == 6, str(len(usages)))
    ok &= check("cumulative cost increases",
                all(usages[i]["cumulative_cost_usd"] <= usages[i + 1]["cumulative_cost_usd"]
                    for i in range(len(usages) - 1)))

    print("\n=== tool failure containment ===")
    r = await registry.call("boom", {})
    ok &= check("raising tool returns ok=False", r.ok is False, r.summary)
    r = await registry.call("nope", {})
    ok &= check("unknown tool handled", r.ok is False and "unknown" in r.summary)
    r = await registry.call("tavily_search", {"wrong_arg": 1})
    ok &= check("bad args handled", r.ok is False, r.summary)

    print("\n=== cost ===")
    print("  total $%.6f across %d calls" % (router.spend.total_usd, router.spend.calls))
    for tier, usd in sorted(router.spend.by_tier.items()):
        print("    %-9s $%.6f" % (tier, usd))

    print("\n=== answer ===")
    print("  " + answer[:120])

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
