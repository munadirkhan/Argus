"""Watcher tests with no API key and no network.

The watcher's whole job is restraint, so most of these assert that it stays
quiet. Run:  python scripts/test_watcher_offline.py
"""
import asyncio, json, os, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.bus import EventBus
from core.fake import FakeClient, Turn
from core.models import ModelRouter
from core.watcher import Watcher, scan, describe_changes


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -- " + detail) if detail and not cond else ""))
    return bool(cond)


def router_saying(*turns):
    return ModelRouter(api_key="fake",
                       client_factory=FakeClient.factory({"lightning": list(turns)}))


SPEAK = Turn(text=json.dumps({
    "speak": True, "confidence": 0.86,
    "observation": "You pulled two papers into refs/ and opened an empty notes.md.",
    "suggestion": "Want me to pull the current literature and draft that summary?"}),
    prompt_tokens=18400, completion_tokens=95)

QUIET = Turn(text=json.dumps({"speak": False}),
             prompt_tokens=18400, completion_tokens=12)


async def main():
    ok = True
    tmp = tempfile.mkdtemp(prefix="argus_watch_")

    print("=== snapshot and diff ===")
    open(os.path.join(tmp, "a.txt"), "w").write("one")
    s1 = scan(tmp)
    ok &= check("scan finds file", len(s1.files) == 1, str(s1.files))

    time.sleep(1.1)
    open(os.path.join(tmp, "b.txt"), "w").write("two")
    s2 = scan(tmp)
    added, modified, removed = s2.diff(s1)
    ok &= check("detects added", [os.path.basename(p) for p in added] == ["b.txt"])
    ok &= check("no false modifications", modified == [], str(modified))

    time.sleep(1.1)
    open(os.path.join(tmp, "a.txt"), "w").write("one changed")
    s3 = scan(tmp)
    added, modified, removed = s3.diff(s2)
    ok &= check("detects modification",
                [os.path.basename(p) for p in modified] == ["a.txt"], str(modified))

    os.remove(os.path.join(tmp, "b.txt"))
    s4 = scan(tmp)
    _, _, removed = s4.diff(s3)
    ok &= check("detects removal", [os.path.basename(p) for p in removed] == ["b.txt"])

    ok &= check("ignores skip dirs",
                not any("node_modules" in p for p in s4.files))
    ok &= check("change description readable",
                "added" in describe_changes(["x/new.md"], [], []))

    print("\n=== first scan stays silent ===")
    bus = EventBus()
    w = Watcher(router_saying(SPEAK), bus, tmp, cooldown=0)
    out = await w.tick()
    ok &= check("no observation on first scan", out is None)
    ok &= check("but emits fs.tree",
                any(e["type"] == "fs.tree" for e in bus.history()))

    print("\n=== no changes, no noise ===")
    bus = EventBus()
    w = Watcher(router_saying(SPEAK), bus, tmp, cooldown=0)
    await w.tick()
    before = len(bus.history())
    out = await w.tick()
    ok &= check("silent when nothing changed", out is None)
    ok &= check("emits nothing at all", len(bus.history()) == before,
                "%d new events" % (len(bus.history()) - before))

    print("\n=== model declines to speak ===")
    bus = EventBus()
    w = Watcher(router_saying(QUIET), bus, tmp, cooldown=0)
    await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "c.txt"), "w").write("three")
    out = await w.tick()
    ok &= check("respects speak:false", out is None)
    ok &= check("no observation event",
                not any(e["type"] == "watcher.observation" for e in bus.history()))
    ok &= check("but still billed for looking",
                any(e["type"] == "usage" for e in bus.history()))

    print("\n=== model speaks up ===")
    bus = EventBus()
    w = Watcher(router_saying(SPEAK), bus, tmp, cooldown=0)
    await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "d.txt"), "w").write("four")
    out = await w.tick()
    ok &= check("observation returned", out is not None)
    obs = [e for e in bus.history() if e["type"] == "watcher.observation"]
    ok &= check("exactly one observation event", len(obs) == 1)
    if obs:
        e = obs[0]
        ok &= check("has observation text", bool(e["observation"]))
        ok &= check("has suggestion text", bool(e["suggestion"]))
        ok &= check("confidence in range", 0.0 <= e["confidence"] <= 1.0)
        ok &= check("dismissible", e["dismissible"] is True)
        ok &= check("watcher tier on HUD",
                    any(x["type"] == "agent.thinking" and x["tier"] == "watcher"
                        for x in bus.history()))

    print("\n=== cooldown suppresses chatter ===")
    bus = EventBus()
    w = Watcher(router_saying(SPEAK, SPEAK), bus, tmp, cooldown=999)
    await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "e.txt"), "w").write("five")
    first = await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "f.txt"), "w").write("six")
    second = await w.tick()
    ok &= check("spoke once", first is not None)
    ok &= check("then held its tongue", second is None)

    print("\n=== dismissal ===")
    if first:
        w.dismiss(first["id"])
        ok &= check("dismissed recorded", first["id"] in w.dismissed)
        ok &= check("removed from pending", first["id"] not in w.pending)

    print("\n=== malformed model output ===")
    bus = EventBus()
    w = Watcher(router_saying(Turn(text="I think maybe you should...")), bus, tmp, cooldown=0)
    await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "g.txt"), "w").write("seven")
    out = await w.tick()
    ok &= check("non-JSON output does not crash or speak", out is None)

    bus = EventBus()
    w = Watcher(router_saying(Turn(text=json.dumps({"speak": True}))), bus, tmp, cooldown=0)
    await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "h.txt"), "w").write("eight")
    out = await w.tick()
    ok &= check("speak:true with no text is suppressed", out is None)

    print("\n=== watcher cost ===")
    r = router_saying(SPEAK)
    w = Watcher(r, EventBus(), tmp, cooldown=0)
    await w.tick()
    time.sleep(1.1)
    open(os.path.join(tmp, "i.txt"), "w").write("nine")
    await w.tick()
    per_cycle = r.spend.total_usd
    print("  one observe cycle: $%.6f" % per_cycle)
    print("  running every 20s for 8h: $%.4f" % (per_cycle * 3 * 60 * 8))
    ok &= check("a cycle costs under a cent", per_cycle < 0.01, "$%.6f" % per_cycle)

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
