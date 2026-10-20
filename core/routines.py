"""Routines: things Argus does on its own at set times -- like a spoken
morning briefing.

Stored in ~/.argus/routines.json. A routine runs once on each of its days, at
or after its time; if the PC was off or asleep it catches up within three
hours, never later (an 8am briefing at 4pm is no use). Create, move or cancel
them in chat ("move my briefing to 7:30", "every Friday at 5 sum up my week").
"""
from __future__ import annotations
import datetime, json, os, re, uuid

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CATCH_UP = datetime.timedelta(hours=3)


def path() -> str:
    return os.environ.get("ARGUS_ROUTINES_FILE") or os.path.join(
        os.path.expanduser("~"), ".argus", "routines.json")


def load() -> list[dict]:
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
        return [r for r in data if isinstance(r, dict) and r.get("id")]
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, path())


def parse_days(days) -> list[str] | None:
    if isinstance(days, str):
        d = days.strip().lower()
        if d in ("daily", "every day", "everyday", "all"):
            return list(DAYS)
        if d in ("weekdays", "workdays"):
            return DAYS[:5]
        if d in ("weekends", "weekend"):
            return DAYS[5:]
        days = re.split(r"[,\s]+", d)
    if not isinstance(days, list):
        return None
    out = [str(x).strip().lower()[:3] for x in days]
    return out if out and all(x in DAYS for x in out) else None


def parse_time(t) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*", str(t or "").lower())
    if not m:
        return None
    h, mins, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return "%02d:%02d" % (h, mins) if h < 24 and mins < 60 else None


def upsert(name, time, days, prompt, enabled=True) -> dict | None:
    """Create a routine, or update the one with this name."""
    t, d = parse_time(time), parse_days(days)
    if not (isinstance(name, str) and name.strip() and t and d and isinstance(prompt, str) and prompt.strip()):
        return None
    items = load()
    for r in items:
        if r["name"].lower() == name.strip().lower():
            r.update(time=t, days=d, prompt=prompt.strip()[:1500], enabled=bool(enabled))
            _save(items)
            return r
    r = {"id": uuid.uuid4().hex[:8], "name": name.strip()[:60], "time": t, "days": d,
         "prompt": prompt.strip()[:1500], "enabled": bool(enabled), "last_run": ""}
    items.append(r)
    _save(items)
    return r


def remove(name) -> bool:
    items = load()
    keep = [r for r in items if r["name"].lower() != str(name).strip().lower()]
    if len(keep) != len(items):
        _save(keep)
        return True
    return False


def due(now: datetime.datetime | None = None) -> list[dict]:
    now = now or datetime.datetime.now()
    out = []
    for r in load():
        if not r.get("enabled") or DAYS[now.weekday()] not in r.get("days", []):
            continue
        if r.get("last_run") == now.date().isoformat():
            continue
        h, m = map(int, r["time"].split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if at <= now < at + CATCH_UP:
            out.append(r)
    return out


def mark_ran(rid: str, now: datetime.datetime | None = None) -> None:
    items = load()
    for r in items:
        if r["id"] == rid:
            r["last_run"] = (now or datetime.datetime.now()).date().isoformat()
    _save(items)


def for_planner() -> str:
    items = load()
    if not items:
        return "Routines: none."
    return "Routines (things you do on a schedule):\n" + "\n".join(
        "- %s: %s at %s%s" % (r["name"], ",".join(r["days"]) if len(r["days"]) < 7 else "daily",
                              r["time"], "" if r.get("enabled") else " (off)") for r in items)


def ensure_morning_briefing() -> None:
    """The one routine every Argus starts with: a spoken briefing on weekdays at 8."""
    if not os.path.exists(path()):
        upsert("Morning briefing", "08:00", "weekdays",
               "Give me my morning briefing. Follow the Morning briefing skill.")
