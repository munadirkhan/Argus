"""The scripted demo mode (ARGUS_DEMO=1): every beat plays through the real
server and websocket, the hidden cues work, PROCEED / ALLOW / DENY / STOP
really steer it, and files land in the workspace. Fast-forwarded.

Run:  python scripts/test_demo_offline.py
"""
import json, os, struct, sys, tempfile, threading, queue, time, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
T = Path(tempfile.mkdtemp(prefix="argus_demo_"))
(T / "ws").mkdir()
os.environ.update(ARGUS_DEMO="1", ARGUS_FAKE="1", ARGUS_DEMO_SPEED="0.02", TAVILY_API_KEY="",
                  ARGUS_WATCH_ROOT=str(T / "ws"), ARGUS_SETTINGS_FILE=str(T / "settings.json"),
                  ARGUS_MEMORY_FILE=str(T / "memory.md"), ARGUS_SKILLS_DIR=str(T / "skills"),
                  ARGUS_ROUTINES_FILE=str(T / "routines.json"))

from fastapi.testclient import TestClient     # noqa: E402
from core import server                       # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + str(detail)[:220]) if detail and not cond else ""))
    ok &= bool(cond)


def png() -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


class Reader:
    def __init__(self, ws):
        self.ws, self.q = ws, queue.Queue()
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                self.q.put(json.loads(self.ws.receive_text()))
            except Exception:
                return

    def until(self, pred, secs=20):
        got, end = [], time.time() + secs
        while time.time() < end:
            try:
                e = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            got.append(e)
            if pred(e):
                return e, got
        return None, got

    def drain(self):
        while not self.q.empty():
            self.q.get()


def reply(e):
    return e["type"] == "agent.message" and e["role"] == "assistant"


with TestClient(server.app, base_url="http://127.0.0.1") as c:
    s = server.session
    print("=== demo mode is on, and honest about it ===")
    check("the session is labelled 'scripted demo'", s.label == "scripted demo")
    check("the real watcher stays quiet (the director does the noticing)", s.watcher.muted)
    with c.websocket_connect("ws://127.0.0.1/ws") as ws:
        r = Reader(ws)
        time.sleep(0.5)
        r.drain()

        print("=== cue 1: markets, then PROCEED ===")
        check("the cue is accepted", c.post("/demo/cue", json={"beat": "markets"}).json()["ok"])
        obs, got = r.until(lambda e: e["type"] == "watcher.observation")
        check("Argus notices, with the chart and the browser on screen",
              obs and any(e.get("source") == "market" for e in got) and "brief" in obs["suggestion"], obs)
        ws.send_text(json.dumps({"type": "user.accept", "id": obs["id"]}))
        done, got = r.until(reply)
        check("PROCEED runs the brief: plan, search, file", any(e["type"] == "agent.plan" for e in got)
              and any(e.get("name") == "tavily_search" for e in got if e["type"] == "tool.call"))
        check("earnings-watch.md written for real", "data-center" in (T / "ws" / "earnings-watch.md").read_text(encoding="utf-8"))
        check("the reply names the file", done and "earnings-watch.md" in done["text"])
        check("costs move the spend meter", any(e["type"] == "usage" for e in got))

        print("=== cue 2: the dashboard crash, then PROCEED ===")
        (T / "ws" / "dashboard").mkdir(exist_ok=True)
        c.post("/demo/cue", json={"beat": "code"})
        obs, got = r.until(lambda e: e["type"] == "watcher.observation")
        check("Argus notices the crash in the terminal", obs and any(
            l.get("tone") == "err" for e in got if e.get("source") == "terminal" for l in e.get("lines", [])))
        ws.send_text(json.dumps({"type": "user.accept", "id": obs["id"]}))
        done, _ = r.until(reply)
        check("the fix lands in watchlist.js", "results ?? []" in (T / "ws" / "dashboard" / "watchlist.js").read_text(encoding="utf-8"))

        print("=== talking: what does ARGUS stand for ===")
        ws.send_text(json.dumps({"type": "user.message", "text": "Argus, what does your name stand for?"}))
        done, _ = r.until(reply)
        check("the acronym", done and "A Really Good User System" in done["text"], done)

        print("=== apply to a job: the approval card ===")
        ws.send_text(json.dumps({"type": "user.message", "text": "apply to the junior engineer job for me"}))
        card, got = r.until(lambda e: e["type"] == "agent.approval")
        check("browser work shows, then it asks before submitting", card and "Submit application" in card["title"]
              and any(e.get("app") == "Argus · hands" for e in got), card)
        ws.send_text(json.dumps({"type": "user.approve", "id": card["id"], "approved": True}))
        done, _ = r.until(reply)
        check("ALLOW submits and logs it", done and done["text"].startswith("Submitted")
              and (T / "ws" / "job-applications.md").exists())
        ws.send_text(json.dumps({"type": "user.message", "text": "apply to another job"}))
        card, _ = r.until(lambda e: e["type"] == "agent.approval")
        ws.send_text(json.dumps({"type": "user.approve", "id": card["id"], "approved": False}))
        done, _ = r.until(reply)
        check("DENY holds off", done and done["text"].startswith("Held off"), done)

        print("=== STOP on a long research run ===")
        ws.send_text(json.dumps({"type": "user.message", "text": "do a deep dive report on the AI PC market"}))
        r.until(lambda e: e["type"] == "tool.call")
        ws.send_text(json.dumps({"type": "user.stop"}))
        done, got = r.until(reply)
        check("STOP cuts it off", done and done["text"] == "Stopped." and any(e["type"] == "agent.stopped" for e in got))

        print("=== look at my screen ===")
        res = c.post("/snap", content=png(), headers={"content-type": "image/png"}).json()
        done, _ = r.until(reply)
        check("the screenshot answer", res["ok"] and done and "react-markdown" in done["text"], done)

        print("=== morning briefing (tray) ===")
        c.post("/routine/run", json={"name": "Morning briefing"})
        done, _ = r.until(reply)
        check("spoken briefing", done and done["text"].startswith("Morning."), done)

    server.session.director, saved = None, server.session.director
    check("a non-demo core refuses cues", c.post("/demo/cue", json={"beat": "markets"}).json()["ok"] is False)
    server.session.director = saved

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
