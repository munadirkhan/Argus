"""Live smoke test: real router, real watcher, real agent loop, real Nemotron.

Spends real credits (about a cent), tracked against the persistent cap in
.argus_spend.json. Tools are not built yet, so the agent runs with none --
this proves the model path, not the tool path.

Run:  python scripts/live_smoke.py
"""
import asyncio, os, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from core.agent import Agent
from core.bus import EventBus
from core.models import ModelRouter
from core.tools.registry import Registry
from core.watcher import Watcher, scan

LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      ".argus_spend.json")
DEMO_RUNS = 3


def write(root, rel, size=0, text=None):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        if text is not None:
            f.write(text.encode())
        elif size:
            f.write(b"%PDF-1.7\n" + b"0" * size)


async def watch_once(router, before, after):
    """Build a workspace with `before`, snapshot, apply `after`, ask the watcher."""
    ws = tempfile.mkdtemp(prefix="mark-ii_")
    for args in before:
        write(ws, *args)
    bus = EventBus()
    w = Watcher(router, bus, ws, cooldown=0)
    w.previous = scan(ws)
    time.sleep(1.1)
    for args in after:
        write(ws, *args)
    snap = scan(ws)
    added, modified, removed = snap.diff(w.previous)
    w.previous = snap
    obs = await w.consider(added, modified, removed)
    errs = [e["message"] for e in bus.history() if e["type"] == "error"]
    return obs, errs


async def main():
    router = ModelRouter(ledger_path=LEDGER)
    start_spend = router.spend.total_usd
    print("ledger before: $%.6f of $%.2f cap\n" % (start_spend, router.budget_usd))

    t0 = time.time()
    await router.resolve()
    print("=== live routing (%.1fs) ===" % (time.time() - t0))
    print(router.describe())

    # --- watcher: must speak on the demo scenario, reliably ------------
    print("\n=== watcher: demo scenario (should SPEAK) x%d ===" % DEMO_RUNS)
    demo_after = [("refs/consistency-samplers-2026.pdf", 880000),
                  ("refs/flow-matching-few-step.pdf", 610000),
                  ("notes.md", 0)]
    spoke = 0
    for i in range(DEMO_RUNS):
        t0 = time.time()
        obs, errs = await watch_once(router, [], demo_after)
        dt = time.time() - t0 - 1.1
        if obs:
            spoke += 1
            print("  run %d SPOKE (%.2f, %.2fs)" % (i + 1, obs["confidence"], dt))
            print("     obs: " + obs["observation"])
            print("     sug: " + obs["suggestion"])
        else:
            print("  run %d quiet %s" % (i + 1, errs or ""))
    print("  -> spoke %d/%d" % (spoke, DEMO_RUNS))

    # --- watcher: must stay quiet on routine activity ------------------
    print("\n=== watcher: routine edits (should stay QUIET) ===")
    before = [("src/main.py", 0, "print('hi')\n"), ("README.md", 0, "# app\n")]
    after = [("src/main.py", 0, "print('hi there')\n"),
             ("build/output.log", 0, "compiled ok\n" * 40)]
    obs, errs = await watch_once(router, before, after)
    print("  " + ("QUIET (correct)" if not obs else "SPOKE (too chatty): " + obs["observation"]))

    # --- full agent loop, no tools -------------------------------------
    print("\n=== agent (Ultra plans, Nano executes, Ultra synthesises) ===")
    bus = EventBus()
    agent = Agent(router, Registry(), bus)
    t0 = time.time()
    answer = await agent.run(
        "In two sentences: what is the practical difference between consistency "
        "models and flow matching for few-step image generation?")
    dt = time.time() - t0

    plan = next((e for e in bus.history() if e["type"] == "agent.plan"), None)
    if plan:
        print("plan:")
        for s in plan["steps"]:
            print("  -", s["title"])
    for e in bus.history():
        if e["type"] == "usage":
            print("  %-9s %5d in %5d out  $%.6f" % (
                e["tier"], e["prompt_tokens"], e["completion_tokens"], e["cost_usd"]))
    errs = [e["message"] for e in bus.history() if e["type"] == "error"]
    if errs:
        print("errors:", errs)
    print("\nanswer (%.1fs):\n  %s" % (dt, answer))

    spent = router.spend.total_usd - start_spend
    print("\n=== this run cost $%.6f | ledger now $%.6f of $%.2f ===" % (
        spent, router.spend.total_usd, router.budget_usd))


if __name__ == "__main__":
    asyncio.run(main())
