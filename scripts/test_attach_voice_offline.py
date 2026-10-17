"""Attachments + local voice, offline (no API key, no network).

The voice section synthesizes a real spoken sentence with Windows' built-in
speech engine and transcribes it with local Whisper, so it is skipped on other
platforms or when faster-whisper isn't installed.

Run:  python scripts/test_attach_voice_offline.py
"""
import asyncio, json, os, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WS = tempfile.mkdtemp(prefix="argus_attach_")
os.environ.update({"ARGUS_FAKE": "1", "ARGUS_WATCH_ROOT": WS, "TAVILY_API_KEY": "",
                   "ARGUS_WATCH_INTERVAL": "60"})

from core import attachments as A          # noqa: E402
from core import voice                     # noqa: E402


def check(label, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- %s" % detail) if detail and not cond else ""))
    return bool(cond)


def sapi_wav(text: str) -> str | None:
    if os.name != "nt":
        return None
    out = os.path.join(tempfile.mkdtemp(), "say.wav")
    ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.SetOutputToWaveFile('%s'); $s.Speak('%s'); $s.Dispose()" % (out, text.replace("'", "")))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
    return out if r.returncode == 0 and os.path.exists(out) else None


async def main():
    ok = True

    print("=== filenames can't escape or misbehave ===")
    cases = {
        "../../etc/passwd": "passwd",
        "C:\\Windows\\win.ini": "win.ini",
        "notes.md": "notes.md",
        "con.txt": "con_.txt",
        "": "attachment",
        "..": "attachment",
        "a<b>:c?.txt": "a_b__c_.txt",
        "  spaced   name .pdf ": "spaced name .pdf",
    }
    for raw, want in cases.items():
        got = A.safe_name(raw)
        ok &= check("%-24r -> %r" % (raw, want), got == want, got)
    ok &= check("long names are capped", len(A.safe_name("x" * 400 + ".txt")) <= 112)

    print("\n=== saving ===")
    r1 = A.save(WS, "report.pdf", b"%PDF-1.4 hello")
    r2 = A.save(WS, "report.pdf", b"%PDF-1.4 again")
    ok &= check("lands in .argus/attachments", r1["path"] == ".argus/attachments/report.pdf", r1)
    ok &= check("never overwrites", r2["name"] == "report (2).pdf", r2)
    ok &= check("kind detected", r1["kind"] == "pdf" and A.kind_of("shot.PNG") == "image")
    for bad, why in ((b"", "empty"), (b"x" * (A.MAX_BYTES + 1), "too big")):
        try:
            A.save(WS, "x.bin", bad)
            ok &= check("rejects %s" % why, False)
        except ValueError:
            ok &= check("rejects %s" % why, True)
    trav = A.save(WS, "../../../escape.txt", b"nope")
    ok &= check("traversal name stays inside", trav["path"] == ".argus/attachments/escape.txt", trav)
    ok &= check("nothing written above the workspace",
                not os.path.exists(os.path.join(os.path.dirname(WS), "escape.txt")))

    print("\n=== through the server ===")
    from fastapi.testclient import TestClient
    from core import server
    with TestClient(server.app) as c:
        r = c.post("/attach", params={"name": "../shot.png"}, content=b"\x89PNG fake").json()
        ok &= check("/attach saves and sanitises", r.get("ok") and r["path"] == ".argus/attachments/shot.png", r)
        bad = c.post("/attach", params={"name": "empty.txt"}, content=b"").json()
        ok &= check("/attach refuses empty", bad.get("ok") is False and "empty" in bad.get("error", ""))
        h = c.get("/health").json()
        ok &= check("/health reports voice + tools", "voice" in h and "view_image" in h["tools"])

        # Only real files from the attachment folder are accepted; anything a
        # client invents is dropped before the agent ever sees it.
        outside = os.path.join(tempfile.mkdtemp(), "secret.txt")
        open(outside, "w").write("secret")
        att = [{"path": r["path"]}, {"path": "../../secret.txt"}, {"path": outside},
               {"path": "notes.md"}, "junk"]
        known = server.session._known_attachments(att)
        ok &= check("only genuine attachments survive", [a["path"] for a in known] == [r["path"]], known)

        with c.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "user.message", "text": "", "attachments": [{"path": r["path"]}]}))
            got = None
            deadline = time.time() + 8
            while time.time() < deadline:
                e = json.loads(ws.receive_text())
                if e.get("type") == "agent.message" and e.get("role") == "user":
                    got = e
                    break
        ok &= check("attachment-only message is accepted", got is not None)
        if got:
            ok &= check("chat shows a sensible line", got["text"] == "Have a look at shot.png.", got["text"])
            ok &= check("event carries the attachment", got.get("attachments", [{}])[0].get("kind") == "image")
        goal = next((m["content"] for m in server.session.agent.transcript if m["role"] == "user"), "")
        ok &= check("agent goal names the path and tool", ".argus/attachments/shot.png" in goal and "view_image" in goal)

        print("\n=== voice ===")
        bad = c.post("/transcribe", content=b"", headers={"content-type": "audio/webm"}).json()
        ok &= check("empty audio refused politely", bad.get("ok") is False)
        junk = c.post("/transcribe", content=b"not audio at all", headers={"content-type": "audio/webm"}).json()
        ok &= check("undecodable audio refused politely", junk.get("ok") is False, junk)
        wav = sapi_wav("Argus, read my notes and check what changed since June.") if voice.available() else None
        if wav:
            data = open(wav, "rb").read()
            t0 = time.time()
            res = c.post("/transcribe", content=data, headers={"content-type": "audio/wav"}).json()
            heard = (res.get("text") or "").lower()
            ok &= check("real speech transcribed locally", res.get("ok") and "notes" in heard and "june" in heard, res)
            print("    heard %r in %.1fs" % (res.get("text"), time.time() - t0))
        else:
            print("  [SKIP] no Windows speech engine or faster-whisper here")

    print("\n=== vision tool without a vision model ===")
    from core.tools.view_image import TOOL as VIEW
    open(os.path.join(WS, "pic.png"), "wb").write(b"\x89PNG not really")
    r = await VIEW.run(path="pic.png")
    ok &= check("fails cleanly, never raises", r.ok is False, r.summary)
    r = await VIEW.run(path="../outside.png")
    ok &= check("confined to the workspace", r.ok is False and "outside" in r.summary, r.summary)

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
