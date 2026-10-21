"""Argus's settings: what the Sanctum (the settings tab) edits.

Stored in ~/.argus/settings.json, applied live -- no restart. Anything not set
falls back to the environment (.env) and then to the defaults. Like the rest
of ~/.argus, no agent tool can write it; only the hub (and you) can.
"""
from __future__ import annotations
import copy, json, os, re

THEMES = ("panoptes", "arc-reactor", "hades", "olympus", "nyx", "gorgon")
TIERS = ("watcher", "planner", "executor")

DEFAULTS: dict = {
    "theme": "panoptes",
    "models": {"watcher": None, "planner": None, "executor": None},   # None = automatic
    "thinking": {"watcher": None, "planner": None, "executor": None},  # None = model default
    "budget_usd": None,                                                # None = .env / 10
    "voice": {"name": None, "speed": None},                            # None = .env / default
    "watcher": {"enabled": True, "interval": 20, "cooldown": 120},
    "persona": {"address": "", "tone": "casual", "length": "short"},
}

TONES = {
    "casual": "Talk like a sharp friend: casual, direct, relaxed.",
    "butler": "Talk like an impeccable English butler -- calm, precise, dry wit, unfailingly polite. "
              "Think a certain AI from a certain billionaire's workshop.",
    "formal": "Talk professionally: clear, courteous, no slang.",
}
LENGTHS = {
    "short": "Keep replies short.",
    "normal": "Replies can run a little longer when it helps.",
    "detailed": "Give fuller replies with the useful detail.",
}


def path() -> str:
    return os.environ.get("ARGUS_SETTINGS_FILE") or os.path.join(
        os.path.expanduser("~"), ".argus", "settings.json")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


def load() -> dict:
    try:
        with open(path(), encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def validate(s: dict, models: dict | None = None) -> dict:
    """Clamp everything to sane values; raise ValueError on what can't be fixed."""
    s = _merge(DEFAULTS, s)
    if s["theme"] not in THEMES:
        s["theme"] = "panoptes"
    for t in TIERS:
        mid = s["models"].get(t)
        if mid is not None and (not isinstance(mid, str) or (models is not None and mid not in models)):
            raise ValueError("unknown model for %s: %r" % (t, mid))
        if mid is not None and models is not None and models[mid].get("price_in") is None:
            raise ValueError("%s has no published price, so the spending limit couldn't count it" % mid)
        th = s["thinking"].get(t)
        s["thinking"][t] = th if th in (True, False) else None
    b = s["budget_usd"]
    if b is not None:
        b = float(b)
        if not 0 < b <= 1000:
            raise ValueError("the spending limit must be between $0 and $1000")
        s["budget_usd"] = round(b, 2)
    v = s["voice"]
    if v["name"] is not None and not (isinstance(v["name"], str) and re.fullmatch(r"[a-z]{2}_[a-z]{2,20}", v["name"])):
        raise ValueError("bad voice name")
    if v["speed"] is not None:
        v["speed"] = round(min(2.0, max(0.6, float(v["speed"]))), 2)
    w = s["watcher"]
    w["enabled"] = bool(w["enabled"])
    w["interval"] = int(min(600, max(5, float(w["interval"]))))
    w["cooldown"] = int(min(3600, max(0, float(w["cooldown"]))))
    p = s["persona"]
    p["address"] = re.sub(r"\s+", " ", str(p.get("address") or "")).strip()[:40]
    p["tone"] = p["tone"] if p.get("tone") in TONES else "casual"
    p["length"] = p["length"] if p.get("length") in LENGTHS else "short"
    return s


def save(s: dict) -> None:
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, path())


def persona_prompt() -> str:
    p = load()["persona"]
    lines = [TONES[p["tone"]], LENGTHS[p["length"]]]
    if p["address"]:
        lines.append('Address the user as "%s" now and then -- naturally, not every sentence.' % p["address"])
    return "Your manner (the user chose this in settings): " + " ".join(lines)
