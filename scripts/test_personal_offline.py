"""Personal-Argus features, offline: full-PC file access and its limits, memory,
and answering directly (with the conversation so far) instead of researching.

Run:  python scripts/test_personal_offline.py
"""
import asyncio, json, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HOME = Path(tempfile.mkdtemp(prefix="argus_home_"))
WS = HOME / "Argus"
WS.mkdir()
os.environ["ARGUS_WATCH_ROOT"] = str(WS)
os.environ["ARGUS_MEMORY_FILE"] = str(HOME / ".argus" / "memory.md")
(HOME / "Documents" / "jobs").mkdir(parents=True)
(HOME / "Documents" / "jobs" / "Munadir_Resume_2026.pdf").write_bytes(b"%PDF fake")
(HOME / "Documents" / "notes.txt").write_text("groceries: eggs")
(HOME / ".ssh").mkdir()
(HOME / ".ssh" / "id_ed25519").write_text("PRIVATE KEY")
(HOME / "proj").mkdir()
(HOME / "proj" / ".env").write_text("NEBIUS_API_KEY=sk-live")
(HOME / "vault.kdbx").write_bytes(b"x")
chrome = HOME / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default"
chrome.mkdir(parents=True)
(chrome / "Login Data").write_bytes(b"x")

from core import memory                                         # noqa: E402
from core.approvals import APPROVALS                            # noqa: E402
from core.tools._workspace import is_protected                  # noqa: E402
from core.tools.read_file import TOOL as read_file              # noqa: E402
from core.tools.list_dir import TOOL as list_dir                # noqa: E402
from core.tools.write_file import TOOL as write_file            # noqa: E402
from core.tools.find_files import TOOL as find_files            # noqa: E402
from core.tools.open_path import TOOL as open_path              # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + str(detail)[:200]) if detail and not cond else ""))
    ok &= bool(cond)


async def files():
    notes = str(HOME / "Documents" / "notes.txt")
    print("=== workspace scope (the default) ===")
    os.environ["ARGUS_FS_SCOPE"] = "workspace"
    r = await read_file.run(notes)
    check("outside the workspace is refused", not r.ok and "outside the workspace" in r.summary, r.summary)

    print("=== full scope ===")
    os.environ["ARGUS_FS_SCOPE"] = "full"
    r = await read_file.run(notes)
    check("reads anywhere on the PC", r.ok and "eggs" in r.detail, r.summary)
    for p, what in [(HOME / ".ssh" / "id_ed25519", "SSH key"), (HOME / "proj" / ".env", ".env"),
                    (HOME / "vault.kdbx", "password vault"), (chrome / "Login Data", "Chrome passwords")]:
        r = await read_file.run(str(p))
        check("never opens a %s" % what, not r.ok and "never opens" in r.summary, r.summary)
    check(".env.example is fine", not is_protected(str(HOME / "proj" / ".env.example")))
    r = await list_dir.run(str(HOME), depth=1)
    check("listing hides secret folders", r.ok and "Documents/" in r.detail and ".ssh" not in r.detail
          and "vault.kdbx" not in r.detail, r.detail[:300])

    r = await find_files.run("resume", folder=str(HOME), types="pdf")
    check("finds the resume from the home folder", r.ok and "Munadir_Resume_2026.pdf" in r.detail, r.detail[:300])
    r = await find_files.run("id_ed25519", folder=str(HOME))
    check("search never surfaces secrets", "id_ed25519" not in (r.detail or ""), r.detail)

    print("=== writing ===")
    APPROVALS.auto = None                       # no UI connected: any question is a no
    r = await write_file.run("inside.md", "hello")
    check("inside the workspace: no question asked", r.ok and (WS / "inside.md").exists(), r.summary)
    out = HOME / "Documents" / "plan.md"
    APPROVALS.auto = False
    r = await write_file.run(str(out), "the plan")
    check("outside: declined -> nothing written", not r.ok and not out.exists(), r.summary)
    APPROVALS.auto = True
    r = await write_file.run(str(out), "the plan")
    check("outside: approved -> written", r.ok and out.read_text() == "the plan", r.summary)
    r = await write_file.run(str(HOME / ".ssh" / "authorized_keys"), "attacker key")
    check("even approved, never writes into .ssh", not r.ok and not (HOME / ".ssh" / "authorized_keys").exists(), r.summary)

    print("=== opening ===")
    exe = HOME / "Documents" / "setup.exe"
    exe.write_bytes(b"MZ")
    APPROVALS.auto = False
    r = await open_path.run(str(exe))
    check("running a program asks first (declined)", not r.ok and "did not approve" in r.summary, r.summary)
    APPROVALS.auto = None
    os.environ["ARGUS_FS_SCOPE"] = "workspace"


def memories():
    print("=== memory ===")
    added, _ = memory.apply(["Name is Munadir", "Looking for junior SWE roles in Toronto", "name is munadir."])
    check("remembers facts, once each", added == ["Name is Munadir", "Looking for junior SWE roles in Toronto"], added)
    added, _ = memory.apply(["My password is hunter22", "card 4111 1111 1111 1111", "SIN is 123 456 789",
                             "my api key is abc"])
    check("never remembers secrets", added == [], added)
    check("in the prompt", "junior SWE roles" in memory.for_prompt())
    _, removed = memory.apply(forget=["toronto"])
    check("forgets on request", removed and "Toronto" not in memory.for_prompt(), removed)
    text = Path(os.environ["ARGUS_MEMORY_FILE"]).read_text(encoding="utf-8")
    check("a readable markdown file", text.startswith("# What Argus remembers") and "- Name is Munadir" in text)


class _Msg:
    def __init__(self, content): self.content, self.tool_calls = content, None


class _Resolved:
    model_id = "stub-model"


class StubRouter:
    """Answers the planner with a fixed JSON reply; records what it was sent."""
    catalogue_ids = []
    def __init__(self, replies): self.replies, self.sent = list(replies), []
    def for_tier(self, tier): return _Resolved()
    async def complete(self, tier, messages, **kw):
        self.sent.append(messages)
        return _Msg(self.replies.pop(0)), {"tier": tier, "model": "stub", "prompt_tokens": 1,
                                            "completion_tokens": 1, "cost_usd": 0.0, "cumulative_cost_usd": 0.0}


class Bus:
    def __init__(self): self.events = []
    async def emit(self, e): self.events.append(e)
    subscriber_count = 0


async def replies():
    from core.agent import Agent
    from core.tools.registry import Registry
    print("=== answering directly ===")
    router = StubRouter([
        json.dumps({"reply": "Yeah -- I've got my own browser now. Say the word and I'll open it so you can sign in once.",
                    "remember": ["Wants Argus to apply to jobs for them"]}),
        json.dumps({"reply": "Opening it now."}),
    ])
    bus = Bus()
    agent = Agent(router, Registry(), bus, workspace=str(WS))
    a1 = await agent.run("yo how do i give u internet access like grok bot so u can apply to jobs for me")
    types = [e["type"] for e in bus.events]
    check("answers without planning or researching", "agent.plan" not in types and a1.startswith("Yeah"), types)
    check("no document written", "artifact.write" not in types)
    check("remembers what it learned", "apply to jobs" in memory.for_prompt())
    system = router.sent[0][0]["content"]
    check("planner knows about its own browser", "OWN BROWSER" in system and "web_signin" in system)
    check("planner is told how the user talks", "slang" in system and "typos" in system)
    await agent.run("ok do that")
    second = router.sent[1]
    roles = [m["role"] for m in second]
    check("the next turn sees the conversation so far", roles[-3:] == ["user", "assistant", "user"]
          and "grok bot" in second[-3]["content"], roles)


async def main():
    await files()
    memories()
    await replies()
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")


asyncio.run(main())
sys.exit(0 if ok else 1)
