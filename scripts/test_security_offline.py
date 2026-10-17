"""Who can talk to the core. The core runs shell commands and reads the
workspace, so a web page you happen to visit, or a machine on the same Wi-Fi,
must not be able to drive it. Fake mode: no API key, no network.

Run:  python scripts/test_security_offline.py
"""
import os, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="argus_sec_")
open(os.path.join(TMP, "secret.md"), "w").write("private notes")
os.environ["ARGUS_FAKE"] = "1"
os.environ["TAVILY_API_KEY"] = ""
os.environ["ARGUS_WATCH_ROOT"] = TMP
os.environ.pop("ARGUS_HOST", None)
os.environ.pop("ARGUS_ALLOWED_ORIGINS", None)

from fastapi.testclient import TestClient            # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402
from core import server                               # noqa: E402
from core.server import app, refusal                  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + detail) if detail and not cond else ""))
    ok &= bool(cond)


EXT = "chrome-extension://" + "a" * 32

print("=== the rule itself ===")
H = {"host": "127.0.0.1:7600"}
for origin, want in [
    (None, None),                                     # curl / desktop shell / terminal sensor
    ("http://localhost:5173", None),                  # Vite dev hub
    ("http://127.0.0.1:4173", None),                  # vite preview
    ("argus://app", None),                            # the desktop app
    (EXT, None),                                      # the browser-tab sensor
    ("https://evil.example", "origin"),
    ("http://localhost.evil.example", "origin"),
    ("http://127.0.0.1.evil.example:7600", "origin"),
    ("null", "origin"),                               # sandboxed iframe / file://
    ("https://argus-demo.vercel.app", "origin"),      # even our own public page
    ("chrome-extension://short", "origin"),
]:
    got = refusal({**H, **({"origin": origin} if origin else {})})
    check(f"origin {origin!r} -> {'allowed' if want is None else 'refused'}", got == want, f"got {got}")
for host, want in [("localhost:7600", None), ("[::1]:7600", None), ("127.0.0.1", None),
                   ("evil.example:7600", "host"), ("192.168.1.20:7600", "host")]:
    check(f"host {host!r} -> {'allowed' if want is None else 'refused'}", refusal({"host": host}) == want)
check("no Origin but cross-site fetch -> refused",
      refusal({**H, "sec-fetch-site": "cross-site"}) == "cross-site")
check("no Origin, same-site -> allowed", refusal({**H, "sec-fetch-site": "same-site"}) is None)

print("=== through the real app ===")
with TestClient(app, base_url="http://127.0.0.1") as c:
    check("hub origin: /health 200", c.get("/health", headers={"origin": "http://localhost:5173"}).status_code == 200)
    r = c.get("/health", headers={"origin": "argus://app"})
    check("desktop origin gets its CORS header", r.headers.get("access-control-allow-origin") == "argus://app")
    check("evil origin: /health 403", c.get("/health", headers={"origin": "https://evil.example"}).status_code == 403)
    check("evil origin: /artifact 403 (can't read your files)",
          c.get("/artifact", params={"path": "secret.md"}, headers={"origin": "https://evil.example"}).status_code == 403)
    check("evil origin: /attach 403 (can't plant files)",
          c.post("/attach", params={"name": "x.txt"}, content=b"x", headers={"origin": "https://evil.example"}).status_code == 403)
    check("evil origin: CORS preflight 403",
          c.options("/attach", headers={"origin": "https://evil.example", "access-control-request-method": "POST"}).status_code == 403)
    check("DNS rebinding (Host: evil.example) 403", c.get("/health", headers={"host": "evil.example:7600"}).status_code == 403)

    refused = False
    try:
        with c.websocket_connect("ws://127.0.0.1/ws", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_text()
    except WebSocketDisconnect:
        refused = True
    check("evil origin: websocket refused (can't run commands)", refused)

    accepted = False
    with c.websocket_connect("ws://127.0.0.1/ws", headers={"origin": "argus://app"}) as ws:
        accepted = bool(ws.receive_text())
    check("desktop origin: websocket accepted", accepted)

print("=== on the network ===")
check("binds loopback by default", server.HOST == "127.0.0.1", server.HOST)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))     # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


port = 7611
env = {**os.environ, "PORT": str(port), "PYTHONIOENCODING": "utf-8"}
proc = subprocess.Popen([sys.executable, "-m", "core.server"], cwd=ROOT, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    up = False
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            up = True
            break
        except Exception:
            time.sleep(0.5)
    check("real server answers on 127.0.0.1", up)
    ip = lan_ip()
    if ip and not ip.startswith("127."):
        reachable = True
        try:
            socket.create_connection((ip, port), timeout=1.5).close()
        except OSError:
            reachable = False
        check(f"real server NOT reachable from the network ({ip})", not reachable)
    else:
        print("  [SKIP] no LAN address to test from")
finally:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
