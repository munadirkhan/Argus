"""The spend cap is the only thing standing between a runaway loop and the
user's bank card (Nebius bills the card once the balance is used up, and has no
server-side cap). These tests prove it holds. No API key, no network.

Run:  python scripts/test_budget_offline.py
"""
import asyncio, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent
from core.bus import EventBus
from core.fake import FakeClient, Turn
from core.models import BudgetExceeded, ModelRouter, Spend
from core.tools.registry import Registry
from core.watcher import Watcher, scan


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -- " + detail) if detail and not cond else ""))
    return bool(cond)


# One Ultra call at these token counts costs ~$0.0414
BIG = Turn(text="ok", prompt_tokens=38400, completion_tokens=1000)


async def main():
    ok = True
    tmp = tempfile.mkdtemp(prefix="argus_budget_")
    ledger = os.path.join(tmp, "spend.json")

    print("=== refuses before spending ===")
    sink = []
    r = ModelRouter(api_key="fake", budget_usd=0.10, ledger_path=ledger,
                    client_factory=FakeClient.factory({"ultra": [BIG] * 10}, sink=sink))
    made = 0
    try:
        for _ in range(10):
            await r.complete("planner", [{"role": "user", "content": "x"}])
            made += 1
    except BudgetExceeded as e:
        print("  stopped after %d calls: %s" % (made, e))
    ok &= check("stops at the cap", made == 3, "made %d calls" % made)
    calls_sent = sum(len(c.calls) for c in sink)
    ok &= check("the refused call never reached the API", calls_sent == made,
                "%d sent vs %d counted" % (calls_sent, made))
    ok &= check("overshoot bounded to one call", r.spend.total_usd < 0.10 + 0.05,
                "$%.4f" % r.spend.total_usd)

    print("\n=== survives a restart ===")
    r2 = ModelRouter(api_key="fake", budget_usd=0.10, ledger_path=ledger,
                     client_factory=FakeClient.factory({"ultra": [BIG]}))
    ok &= check("ledger reloaded", abs(r2.spend.total_usd - r.spend.total_usd) < 1e-9,
                "$%.4f vs $%.4f" % (r2.spend.total_usd, r.spend.total_usd))
    try:
        await r2.complete("planner", [{"role": "user", "content": "x"}])
        refused = False
    except BudgetExceeded:
        refused = True
    ok &= check("restart does NOT reset the cap", refused)

    print("\n=== raising the budget lets it continue ===")
    r3 = ModelRouter(api_key="fake", budget_usd=1.00, ledger_path=ledger,
                     client_factory=FakeClient.factory({"ultra": [BIG]}))
    try:
        await r3.complete("planner", [{"role": "user", "content": "x"}])
        cont = True
    except BudgetExceeded:
        cont = False
    ok &= check("higher budget resumes", cont)

    print("\n=== corrupt ledger fails closed ===")
    bad = os.path.join(tmp, "bad.json")
    open(bad, "w").write("{this is not json")
    s = Spend.load(bad)
    ok &= check("treated as fully spent", s.total_usd == float("inf"))
    r4 = ModelRouter(api_key="fake", budget_usd=100.0, ledger_path=bad,
                     client_factory=FakeClient.factory({"ultra": [BIG]}))
    try:
        await r4.complete("planner", [{"role": "user", "content": "x"}])
        blocked = False
    except BudgetExceeded:
        blocked = True
    ok &= check("refuses to spend on a corrupt ledger", blocked)

    print("\n=== ledger file is valid json ===")
    d = json.load(open(ledger))
    ok &= check("has total, by_tier, calls",
                {"total_usd", "by_tier", "calls"} <= set(d))
    ok &= check("no leftover temp file", not os.path.exists(ledger + ".tmp"))

    print("\n=== no ledger path = in-memory only (tests, fake mode) ===")
    r5 = ModelRouter(api_key="fake", client_factory=FakeClient.factory())
    ok &= check("nothing persisted", r5.spend.path is None)

    print("\n=== agent stops the whole run at the cap ===")
    bus = EventBus()
    script = {"ultra": [Turn(text=json.dumps({"steps": [
        {"title": "a"}, {"title": "b"}, {"title": "c"}]}),
        prompt_tokens=100, completion_tokens=50)],
        "nano": [BIG] * 20}
    r6 = ModelRouter(api_key="fake", budget_usd=0.0005,
                     client_factory=FakeClient.factory(script))
    agent = Agent(r6, Registry(), bus)
    answer = await agent.run("do three things")
    errs = [e for e in bus.history() if e["type"] == "error"]
    steps = [e for e in bus.history() if e["type"] == "agent.step"]
    ran = [e for e in steps if e["status"] == "running"]
    ok &= check("run ends with a message, not a crash", bool(answer))
    ok &= check("tells the user why", "cap" in answer.lower(), answer[:80])
    started = [e["id"] for e in ran]
    ok &= check("does not grind through remaining steps", "s3" not in started,
                "started: %s" % started)
    ok &= check("exactly one error event", len(errs) == 1, str(len(errs)))

    print("\n=== watcher pauses itself at the cap ===")
    bus = EventBus()
    r7 = ModelRouter(api_key="fake", budget_usd=0.0,
                     client_factory=FakeClient.factory())
    w = Watcher(r7, bus, tmp, cooldown=0)
    w.previous = scan(tmp)
    await w.consider(["x"], [], [])
    ok &= check("watcher disabled", w.enabled is False)
    ok &= check("reports why", any("paused" in e.get("message", "")
                                   for e in bus.history() if e["type"] == "error"))

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
