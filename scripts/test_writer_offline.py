"""Writer stage + helpers, offline. Ultra (scripted) writes markdown; ARGUS
saves it with the real write_file tool into a temp workspace.

Run:  python scripts/test_writer_offline.py
"""
import asyncio, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent, brief, pick_target, strip_fences
from core.bus import EventBus
from core.fake import FakeClient, Turn
from core.models import ModelRouter
from core.tools.registry import Registry


def check(label, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- %s" % detail) if detail and not cond else ""))
    return bool(cond)


DOC = "# Nemotron 3 — current status\n\n> Your notes are outdated: Ultra is live.\n\n## Sources\n\n1. x"
FENCE = chr(96) * 3


async def main():
    ok = True
    ws = tempfile.mkdtemp(prefix="argus_writer_")
    os.environ["ARGUS_WATCH_ROOT"] = ws
    os.makedirs(os.path.join(ws, "refs"))
    open(os.path.join(ws, "notes.md"), "w").close()

    print("=== pick_target ===")
    ok &= check("named + existing wins", pick_target("Write findings to notes.md", "", ws) == "notes.md")
    ok &= check("named but new", pick_target("Write summary.md", "", ws) == "summary.md")
    ok &= check("falls back to empty doc", pick_target("Write it up", "do the thing", ws) == "notes.md")
    empty = tempfile.mkdtemp()
    ok &= check("last resort default", pick_target("Write it up", "", empty) == "argus-notes.md")

    print("\n=== strip_fences / brief ===")
    ok &= check("unwraps markdown fence", strip_fences(FENCE + "markdown\n# Hi\n" + FENCE) == "# Hi")
    ok &= check("leaves plain text", strip_fences("# Hi\n\ntext") == "# Hi\n\ntext")
    long = " ".join(["This sentence has exactly seven words here."] * 20)
    b = brief(long)
    ok &= check("brief trims to whole sentences", len(b.split()) <= 75 and b.endswith("."), len(b.split()))
    ok &= check("short text untouched", brief("Short reply.") == "Short reply.")

    print("\n=== full run with a write step ===")
    script = {
        "ultra": [
            Turn(text=json.dumps({"steps": [{"title": "Write findings to notes.md", "kind": "write"}]})),
            Turn(text=FENCE + "markdown\n" + DOC + "\n" + FENCE, prompt_tokens=9000, completion_tokens=900),
            Turn(text="Your notes were outdated; Ultra is live. Updated notes.md."),
        ],
    }
    bus = EventBus()
    router = ModelRouter(api_key="fake", client_factory=FakeClient.factory(script))
    await router.resolve()
    agent = Agent(router, Registry(), bus, workspace=ws)
    answer = await agent.run("check my notes")
    hist = bus.history()
    written = open(os.path.join(ws, "notes.md"), encoding="utf-8").read()
    ok &= check("document saved to the empty notes.md", written == DOC, written[:60])
    ok &= check("artifact event emitted", any(e["type"] == "artifact.write" for e in hist))
    calls = [e for e in hist if e["type"] == "tool.call"]
    ok &= check("UI sees exactly one write", len(calls) == 1 and calls[0]["name"] == "write_file")
    ok &= check("no extra files", sorted(os.listdir(ws)) == ["notes.md", "refs"], os.listdir(ws))
    ok &= check("writer ran on the planner tier",
                any(e["type"] == "agent.thinking" and e["tier"] == "planner" and "Writing" in e["note"] for e in hist))
    ok &= check("no errors", not any(e["type"] == "error" for e in hist),
                [e["message"] for e in hist if e["type"] == "error"])
    ok &= check("reply delivered", "outdated" in answer)

    print("\n=== code fix: writes the code file, verbatim ===")
    code_ws = tempfile.mkdtemp(prefix="argus_code_")
    os.environ["ARGUS_WATCH_ROOT"] = code_ws
    open(os.path.join(code_ws, "watchlist.js"), "w").write("export const rows = (q) => q.data.map(r => r);\n")
    open(os.path.join(code_ws, "notes.md"), "w").close()   # must NOT be chosen
    ok &= check("named code file wins over empty notes.md",
                pick_target("Write the fixed watchlist.js", "", code_ws) == "watchlist.js")
    FIXED = "// q.data is undefined until the first fetch resolves.\nexport const rows = (q) => (q.data ?? []).map(r => r);"
    script = {"ultra": [
        Turn(text=json.dumps({"steps": [{"title": "Write the fixed watchlist.js", "kind": "write"}]})),
        Turn(text=FENCE + "js\n" + FIXED + "\n" + FENCE),
        Turn(text="Patched watchlist.js."),
    ]}
    sink = []
    r3 = ModelRouter(api_key="fake", client_factory=FakeClient.factory(script, sink=sink))
    await r3.resolve()
    bus = EventBus()
    await Agent(r3, Registry(), bus, workspace=code_ws).run("fix the TypeError in watchlist.js")
    got = open(os.path.join(code_ws, "watchlist.js"), encoding="utf-8").read()
    ok &= check("code file rewritten, fences stripped", got == FIXED, got[:80])
    ok &= check("notes.md untouched", os.path.getsize(os.path.join(code_ws, "notes.md")) == 0)
    writer_prompt = next((c["messages"][0]["content"] for cl in sink for c in cl.calls
                          if "writing stage" in c["messages"][0]["content"]), "")
    ok &= check("writer told it's code, not markdown",
                "is a code file" in writer_prompt and "markdown headings" not in writer_prompt)
    arts = [e for e in bus.history() if e["type"] == "artifact.write"]
    ok &= check("artifact marked as code", arts and arts[0]["kind"] == "code", arts[:1])

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
