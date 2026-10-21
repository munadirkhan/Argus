"""What Argus remembers about the user, across restarts.

A plain markdown file (default ~/.argus/memory.md) of short facts, one per
line: who they are, what they're working toward, how they like things done.
The planner adds to it when the user says something worth keeping and removes
lines when asked to forget. The user can open and edit it any time.

Never stored: anything that looks like a password, code, card, account or ID
number. Memory goes into prompts, and prompts go to the model provider.
"""
from __future__ import annotations
import datetime, os, re

PATH = os.environ.get("ARGUS_MEMORY_FILE") or os.path.join(
    os.path.expanduser("~"), ".argus", "memory.md")
MAX_FACTS = 200
IN_PROMPT = 60
HEADER = ("# What Argus remembers about you\n\n"
          "One fact per line. Edit or delete anything; Argus reads this before every request.\n\n")

_SECRETISH = re.compile(
    r"pass(word|code|phrase)|\bpin\b|\botp\b|cvv|cvc|card number|credit card|\bssn\b|"
    r"social (security|insurance)|\bsin\b|passport (no|number)|api[_ ]?key|secret|token|"
    r"\d[\d \-]{8,}\d", re.I)


def _path() -> str:
    return os.environ.get("ARGUS_MEMORY_FILE") or PATH


def load() -> list[str]:
    try:
        with open(_path(), encoding="utf-8") as f:
            return [ln[2:].strip() for ln in f if ln.startswith("- ") and ln[2:].strip()]
    except OSError:
        return []


def _save(facts: list[str]) -> None:
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(HEADER + "".join("- %s\n" % x for x in facts[-MAX_FACTS:]))
    os.replace(tmp, _path())


def clean(fact) -> str | None:
    if not isinstance(fact, str):
        return None
    fact = re.sub(r"\s+", " ", fact).strip().lstrip("-• ").strip()
    if not (3 <= len(fact) <= 240) or _SECRETISH.search(fact):
        return None
    return fact


def apply(remember=None, forget=None) -> tuple[list[str], list[str]]:
    """Add and remove facts. Returns (added, removed)."""
    facts = load()
    removed = []
    for phrase in (forget or [])[:10]:
        if isinstance(phrase, str) and len(phrase.strip()) >= 3:
            p = phrase.strip().lower()
            removed += [f for f in facts if p in f.lower()]
            facts = [f for f in facts if p not in f.lower()]
    added = []
    have = {f.lower().rstrip(".") for f in facts}
    for raw in (remember or [])[:10]:
        fact = clean(raw)
        if fact and fact.lower().rstrip(".") not in have:
            facts.append(fact)
            have.add(fact.lower().rstrip("."))
            added.append(fact)
    if added or removed:
        _save(facts)
    return added, removed


def replace(facts) -> list[str]:
    """The user edited the list in settings: keep exactly theirs (secrets still refused)."""
    out, seen = [], set()
    for raw in (facts or [])[:MAX_FACTS]:
        f = clean(raw)
        if f and f.lower() not in seen:
            out.append(f)
            seen.add(f.lower())
    _save(out)
    return out


def for_prompt() -> str:
    facts = load()[-IN_PROMPT:]
    if not facts:
        return ("What you remember about the user: nothing yet. (It builds up as they tell you "
                "things; it lives in %s.)" % _path())
    return ("What you remember about the user (from earlier conversations; they can edit %s):\n%s"
            % (_path(), "\n".join("- " + f for f in facts)))


def today() -> str:
    return datetime.date.today().isoformat()
