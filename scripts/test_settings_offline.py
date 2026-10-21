"""The Sanctum's backend: settings are validated, saved, and applied live --
models, spending limit, voice, watcher, persona. Fake mode, no network.

Run:  python scripts/test_settings_offline.py
"""
import json, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
T = Path(tempfile.mkdtemp(prefix="argus_settings_"))
(T / "ws").mkdir()
os.environ.update(ARGUS_FAKE="1", TAVILY_API_KEY="", ARGUS_WATCH_ROOT=str(T / "ws"),
                  ARGUS_SETTINGS_FILE=str(T / "settings.json"), ARGUS_MEMORY_FILE=str(T / "memory.md"),
                  ARGUS_SKILLS_DIR=str(T / "skills"), ARGUS_ROUTINES_FILE=str(T / "routines.json"))

from fastapi.testclient import TestClient            # noqa: E402
from core import server, settings, speaker           # noqa: E402
from core.tools._workspace import is_protected       # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + str(detail)[:200]) if detail and not cond else ""))
    ok &= bool(cond)


with TestClient(server.app, base_url="http://127.0.0.1") as c:
    s = server.session
    print("=== reading ===")
    v = c.get("/settings").json()
    check("defaults", v["settings"]["theme"] == "panoptes" and v["settings"]["models"]["planner"] is None)
    check("shows what each role runs on", set(v["bound"]) == {"watcher", "planner", "executor"})
    check("starter skills and the briefing are listed", len(v["skills"]) == 2 and v["routines"][0]["name"] == "Morning briefing")

    print("=== changing ===")
    v = c.put("/settings", json={"theme": "arc-reactor", "budget_usd": 25,
                                 "persona": {"address": "sir", "tone": "butler"},
                                 "voice": {"name": "bm_daniel", "speed": 1.2},
                                 "watcher": {"enabled": False, "interval": 30, "cooldown": 600}}).json()
    check("saved to disk", json.loads((T / "settings.json").read_text())["theme"] == "arc-reactor")
    check("spending limit applies now", s.router.budget_usd == 25 and v["budget_usd"] == 25)
    check("voice applies now", speaker.DEFAULT_VOICE == "bm_daniel" and speaker.SPEED == 1.2)
    check("watcher muted and re-timed", s.watcher.muted and s.watcher.interval == 30 and s.watcher.cooldown == 600)
    p = settings.persona_prompt()
    check("persona reaches the prompts", '"sir"' in p and "butler" in p)
    check("partial updates keep the rest", c.put("/settings", json={"theme": "nyx"}).json()["settings"]["persona"]["address"] == "sir")

    print("=== refusing nonsense ===")
    for bad in [{"budget_usd": -1}, {"budget_usd": 5000}, {"voice": {"name": "../../etc"}},
                {"models": {"planner": "not/a-model"}}]:
        check("rejects %s" % json.dumps(bad), c.put("/settings", json=bad).status_code == 400)
    v = c.put("/settings", json={"watcher": {"interval": 1, "cooldown": 99999}, "voice": {"speed": 9}}).json()
    check("clamps out-of-range numbers", v["settings"]["watcher"]["interval"] == 5
          and v["settings"]["watcher"]["cooldown"] == 3600 and v["settings"]["voice"]["speed"] == 2.0)
    check("a web page can't change them", c.put("/settings", json={"budget_usd": 999},
          headers={"origin": "https://evil.example"}).status_code == 403)

    print("=== models ===")
    s.router.models["acme/Priced-Model"] = {"id": "acme/Priced-Model", "region": "us", "price_in": 0.5,
                                            "price_out": 1.5, "description": "", "context": 1000, "modality": "text->text"}
    s.router.models["acme/Unpriced"] = {"id": "acme/Unpriced", "region": "us", "price_in": None,
                                        "price_out": None, "description": "", "context": 1000, "modality": "text->text"}
    v = c.put("/settings", json={"models": {"executor": "acme/Priced-Model"}, "thinking": {"executor": False}}).json()
    check("any priced model can take a role", s.router.for_tier("executor").model_id == "acme/Priced-Model"
          and s.router.for_tier("executor").spec.price_in == 0.5)
    check("thinking override stored", s.router.thinking["executor"] is False)
    c.put("/settings", json={"models": {"planner": "acme/Unpriced"}})
    check("an unpriced model can't (the limit couldn't count it)", s.router.for_tier("planner").model_id != "acme/Unpriced")
    c.put("/settings", json={"models": {"executor": None, "planner": None}})
    check("back to automatic", s.router.for_tier("executor").model_id == s.router.automatic["executor"].model_id)

    print("=== memory, skills, routines from the Sanctum ===")
    r = c.put("/memory", json={"facts": ["I live in Toronto", "my password is hunter22", "I live in Toronto"]}).json()
    check("memory replaced, secrets and duplicates dropped", r["memory"] == ["I live in Toronto"], r)
    r = c.put("/skill", json={"name": "Cover letters", "when": "a job asks", "steps": "Three short paragraphs."}).json()
    check("skill saved", any(x["name"] == "Cover letters" for x in r["skills"]))
    r = c.put("/skill", json={"name": "Cover letter", "old_name": "Cover letters", "when": "a job asks", "steps": "Two paragraphs."}).json()
    check("skill renamed (no duplicate)", [x["name"] for x in r["skills"]].count("Cover letters") == 0)
    r = c.put("/routine", json={"name": "Weekly review", "time": "17:00", "days": ["fri"], "prompt": "Sum up my week.", "enabled": True}).json()
    check("routine added", any(x["name"] == "Weekly review" and x["days"] == ["fri"] for x in r["routines"]))
    check("routine deleted", c.delete("/routine", params={"name": "Weekly review"}).json()["ok"])

print("=== on disk ===")
home = Path(os.path.expanduser("~"))
check("~/.argus/settings.json is off-limits to agent tools", is_protected(str(home / ".argus" / "settings.json")))

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
