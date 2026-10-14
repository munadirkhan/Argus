"""The whole demo, live, headless: watcher notices -> user accepts -> agent
researches with real tools -> document lands on disk.

Spends real credits (a few cents), tracked against the spend cap.
Run:  python scripts/live_demo.py
"""
import asyncio, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))

import seed_demo
from core.agent import Agent
from core.bus import EventBus
from core.models import ModelRouter
from core.tools.registry import Registry
from core.watcher import Watcher, scan

LEDGER = os.path.join(os.path.dirname(HERE), ".argus_spend.json")


def fmt(e, t0):
    t = "%5.1fs" % (time.time() - t0)
    k = e["type"]
    if k == "agent.thinking":
        return "%s  %-9s %s" % (t, e["tier"].upper(), e["note"])
    if k == "agent.plan":
        return "%s  PLAN      " % t + " | ".join(s["title"] for s in e["steps"])
    if k == "tool.call":
        arg = next(iter(e["args"].values()), "") if e["args"] else ""
        return "%s    -> %s(%s)" % (t, e["name"], str(arg)[:70])
    if k == "tool.result":
        return "%s    <- %s %s" % (t, "ok " if e["ok"] else "ERR", e["summary"][:90])
    if k == "artifact.write":
        return "%s  ARTIFACT  %s (%d bytes)" % (t, e["path"], e["bytes"])
    if k == "error":
        return "%s  ERROR     %s" % (t, e["message"][:120])
    return None


async def main():
    seed_demo.reset()
    ws = seed_demo.DEMO_DIR
    os.environ["ARGUS_WATCH_ROOT"] = ws

    router = ModelRouter(ledger_path=LEDGER)
    spend0 = router.spend.total_usd
    await router.resolve()

    bus = EventBus()
    t0 = time.time()
    printer_done = asyncio.Event()

    async def printer():
        async for e in bus.subscribe(replay=False):
            line = fmt(e, t0)
            if line:
                print(line, flush=True)

    ptask = asyncio.create_task(printer())
    await asyncio.sleep(0)

    watcher = Watcher(router, bus, ws, cooldown=0)
    await watcher.tick()                      # baseline: empty folder
    print("\n[user drops research notes into the project]\n")
    time.sleep(1.1)
    seed_demo.drop()
    obs = await watcher.tick()
    if not obs:
        print("\nwatcher stayed quiet -- aborting")
        ptask.cancel()
        return
    print("\n  ARGUS: %s\n         %s\n" % (obs["observation"], obs["suggestion"]))
    print("[user clicks accept]\n")

    agent = Agent(router, Registry(), bus, workspace=ws)
    goal = ("You noticed: %s\nYou offered: %s\nThe user said yes -- do it."
            % (obs["observation"], obs["suggestion"]))
    answer = await agent.run(goal, display="Go ahead.")
    await asyncio.sleep(0.1)
    ptask.cancel()

    print("\n  ARGUS: %s\n" % answer)
    log = os.environ.get("ARGUS_RUN_LOG", os.path.join(HERE, "last_run.jsonl"))
    with open(log, "w", encoding="utf-8") as f:
        for e in bus.history():
            f.write(json.dumps(e) + "\n")
    print("full event log: %s" % log)
    notes = os.path.join(ws, "notes.md")
    body = open(notes, encoding="utf-8").read() if os.path.exists(notes) else ""
    print("=" * 78)
    print("notes.md (%d chars)" % len(body))
    print("=" * 78)
    print(body or "(empty -- the agent did not write it)")
    print("=" * 78)
    print("wall time %.1fs | cost $%.4f | ledger $%.4f of $%.2f" % (
        time.time() - t0, router.spend.total_usd - spend0,
        router.spend.total_usd, router.budget_usd))
    by = {}
    for e in bus.history():
        if e["type"] == "usage":
            by.setdefault(e["tier"], [0, 0, 0.0])
            by[e["tier"]][0] += 1
            by[e["tier"]][1] += e["prompt_tokens"] + e["completion_tokens"]
            by[e["tier"]][2] += e["cost_usd"]
    for tier, (n, tok, usd) in by.items():
        print("  %-9s %2d calls %7d tokens  $%.4f" % (tier, n, tok, usd))


if __name__ == "__main__":
    asyncio.run(main())
