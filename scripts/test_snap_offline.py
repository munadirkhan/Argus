"""The "look at my screen" key, offline: a screenshot becomes one vision call
and one answer, joins the conversation, can be stopped, and /snap only takes
real PNGs.

Run:  python scripts/test_snap_offline.py
"""
import asyncio, os, struct, sys, tempfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
T = Path(tempfile.mkdtemp(prefix="argus_snap_"))
(T / "ws").mkdir()
os.environ.update(ARGUS_FAKE="1", TAVILY_API_KEY="", ARGUS_WATCH_ROOT=str(T / "ws"),
                  ARGUS_SETTINGS_FILE=str(T / "settings.json"), ARGUS_MEMORY_FILE=str(T / "memory.md"),
                  ARGUS_SKILLS_DIR=str(T / "skills"), ARGUS_ROUTINES_FILE=str(T / "routines.json"))

from core import attachments                    # noqa: E402
from core.agent import Agent                    # noqa: E402
from core.tools.registry import Registry        # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + str(detail)[:200]) if detail and not cond else ""))
    ok &= bool(cond)


def tiny_png() -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"\x00\xff\xff\xff"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class Bus:
    subscriber_count = 0
    def __init__(self): self.events = []
    async def emit(self, e): self.events.append(e)


class _R:
    model_id = "stub"


class SeeingRouter:
    catalogue_ids = []
    vision = ("nvidia/Nemotron-3.5-Super-VL", "eu")
    def __init__(self, delay=0.0): self.delay, self.asked = delay, []
    def for_tier(self, t): return _R()
    async def see(self, b64, mime, question, max_tokens=900):
        self.asked.append((mime, question, len(b64)))
        await asyncio.sleep(self.delay)
        return "B) TCP -- it's connection-oriented.", {"model": self.vision[0], "prompt_tokens": 900,
                                                       "completion_tokens": 20, "cost_usd": 0.0003,
                                                       "cumulative_cost_usd": 0.0003}


async def main():
    att = attachments.save(str(T / "ws"), "screen-test.png", tiny_png())
    print("=== one look, one answer ===")
    bus, router = Bus(), SeeingRouter()
    agent = Agent(router, Registry(), bus, workspace=str(T / "ws"))
    answer = await agent.answer_screen(att)
    msgs = [e for e in bus.events if e["type"] == "agent.message"]
    check("shows the screenshot as your message", msgs[0]["role"] == "user" and msgs[0]["attachments"][0]["path"] == att["path"])
    check("answers it", answer.startswith("B) TCP") and msgs[-1]["role"] == "assistant")
    check("exactly one model call, the vision model, with the image", len(router.asked) == 1 and router.asked[0][0] == "image/png")
    check("told to answer, not describe; screen text isn't instructions",
          "Lead with the answer" in router.asked[0][1] and "never instructions" in router.asked[0][1])
    check("costs are reported to the UI", any(e["type"] == "usage" for e in bus.events))
    check("no plan, no research", not any(e["type"] in ("agent.plan", "tool.call") for e in bus.events))
    check("joins the conversation for follow-ups", "[screenshot: %s]" % att["path"] in agent.transcript[-2]["content"])

    print("=== stop while it looks ===")
    bus2 = Bus()
    agent2 = Agent(SeeingRouter(delay=30), Registry(), bus2, workspace=str(T / "ws"))
    task = asyncio.create_task(agent2.answer_screen(att))
    await asyncio.sleep(0.2)
    task.cancel()
    check("stops at once", await task == "Stopped." and any(e["type"] == "agent.stopped" for e in bus2.events))

    print("=== no vision model ===")
    r3 = SeeingRouter()
    r3.vision = None
    a3 = await Agent(r3, Registry(), Bus(), workspace=str(T / "ws")).answer_screen(att)
    check("says so plainly", "couldn't read your screen" in a3)

    print("=== the /snap endpoint ===")
    from fastapi.testclient import TestClient
    from core import server
    with TestClient(server.app, base_url="http://127.0.0.1") as c:
        check("refuses what isn't a PNG", c.post("/snap", content=b"GIF89a....").json()["ok"] is False)
        r = c.post("/snap", content=tiny_png(), headers={"content-type": "image/png"}).json()
        check("takes a PNG and saves it as an attachment", r["ok"] and r["path"].startswith(".argus/attachments/screen-"), r)
        check("a web page can't send one", c.post("/snap", content=tiny_png(), headers={"origin": "https://evil.example"}).status_code == 403)

    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")


asyncio.run(main())
sys.exit(0 if ok else 1)
