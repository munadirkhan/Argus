"""Skills: saved how-tos Argus follows for jobs it does again and again.

One markdown file per skill in ~/.argus/skills:

    # Apply to a job
    When: the user wants to apply to a job posting

    1. ...the steps, in plain words...

The planner sees every skill's name and "When"; for a request that matches,
it names the skill, and the full text goes to the steps doing the work. You
can teach one in chat ("save this as a skill: ..."), or edit the files.
"""
from __future__ import annotations
import os, re

from .memory import _SECRETISH

MAX_CHARS = 4000


def folder() -> str:
    return os.environ.get("ARGUS_SKILLS_DIR") or os.path.join(os.path.expanduser("~"), ".argus", "skills")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "skill"


def _parse(path: str) -> dict | None:
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    lines = text.splitlines()
    name = lines[0].lstrip("# ").strip() if lines else os.path.basename(path)[:-3]
    when = next((l.split(":", 1)[1].strip() for l in lines[1:4] if l.lower().startswith("when:")), "")
    return {"name": name, "when": when, "path": path, "text": text.strip()}


def all_skills() -> list[dict]:
    d = folder()
    if not os.path.isdir(d):
        return []
    out = [_parse(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".md")]
    return [s for s in out if s]


def find(names) -> list[dict]:
    if not isinstance(names, list):
        return []
    wanted = {str(n).strip().lower() for n in names[:4]}
    return [s for s in all_skills() if s["name"].lower() in wanted or _slug(s["name"]) in wanted]


def save(name, when, steps) -> dict | None:
    """Create or replace a skill. Refuses anything that looks like a secret."""
    if not all(isinstance(x, str) for x in (name, when, steps)):
        return None
    name, when, steps = name.strip()[:80], when.strip()[:200], steps.strip()[:MAX_CHARS]
    if len(name) < 3 or len(steps) < 10 or _SECRETISH.search(steps + " " + when):
        return None
    os.makedirs(folder(), exist_ok=True)
    path = os.path.join(folder(), _slug(name) + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# %s\nWhen: %s\n\n%s\n" % (name, when, steps))
    return _parse(path)


def delete(name) -> bool:
    gone = False
    for s in find([name]):
        try:
            os.remove(s["path"])
            gone = True
        except OSError:
            pass
    return gone


def for_planner() -> str:
    skills = all_skills()
    if not skills:
        return "Saved skills: none yet."
    return ("Saved skills (how-tos the user taught you; name the ones that fit in \"use_skills\"):\n"
            + "\n".join("- %s -- when: %s" % (s["name"], s["when"] or "(not said)") for s in skills))


def for_steps(chosen: list[dict]) -> str:
    if not chosen:
        return ""
    return ("Follow these saved skills (the user's own instructions for this kind of job):\n\n"
            + "\n\n".join(s["text"] for s in chosen))


STARTERS = {
    "Apply to a job": (
        "the user wants to apply to a job posting or role",
        """1. Find the user's resume (find_files "resume", newest PDF) and read about-me.md if there is one.
2. Open the posting in Argus's browser. If it needs an account, hand the user the sign-in (web_signin).
3. Fill every field from the resume and about-me.md only. Never invent experience, dates or answers
   to screening questions -- if one is required and unknown, stop and ask the user.
4. Upload the resume when the form asks (the user approves it).
5. Before the final submit, list what was filled in; the submit itself waits for the user's yes.
6. After submitting, add a line to job-applications.md in the workspace: date, company, role, link,
   status."""),
    "Morning briefing": (
        "a morning briefing, daily summary, or 'what's on today'",
        """1. Today's date, and the weather where the user lives (from memory; search if needed).
2. Three news items that matter to their interests and work (from memory), one line each.
3. If email or calendar are connected: today's events and anything urgent.
4. Job search: what job-applications.md says is pending or new.
5. Say it like a good butler: warm, brief, a little dry. Spoken, so no lists or links. Under 120
   words. No document.
Only look things up (search, read): a briefing never opens windows, drives the browser or writes
files."""),
}


def ensure_starters() -> None:
    """Put the starter skills in place once; the user's edits are never overwritten."""
    os.makedirs(folder(), exist_ok=True)
    for name, (when, steps) in STARTERS.items():
        if not os.path.exists(os.path.join(folder(), _slug(name) + ".md")):
            save(name, when, steps)
