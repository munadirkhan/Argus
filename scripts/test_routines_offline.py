"""Skills and routines, offline: scheduling rules, the morning briefing,
teaching Argus a skill in chat, and that no tool can rewrite them.

Run:  python scripts/test_routines_offline.py
"""
import asyncio, datetime, json, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TMP = Path(tempfile.mkdtemp(prefix="argus_routines_"))
os.environ["ARGUS_ROUTINES_FILE"] = str(TMP / "routines.json")
os.environ["ARGUS_SKILLS_DIR"] = str(TMP / "skills")
os.environ["ARGUS_MEMORY_FILE"] = str(TMP / "memory.md")
os.environ["ARGUS_WATCH_ROOT"] = str(TMP / "ws")
(TMP / "ws").mkdir()

from core import routines, skills                     # noqa: E402
from core.tools._workspace import is_protected        # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- " + str(detail)[:200]) if detail and not cond else ""))
    ok &= bool(cond)


def scheduling():
    print("=== times and days ===")
    for raw, want in [("8", "08:00"), ("7:30", "07:30"), ("7:30pm", "19:30"), ("12am", "00:00"),
                      ("12 pm", "12:00"), ("25:00", None), ("soon", None)]:
        check("time %r -> %r" % (raw, want), routines.parse_time(raw) == want, routines.parse_time(raw))
    check("weekdays", routines.parse_days("weekdays") == ["mon", "tue", "wed", "thu", "fri"])
    check("a list", routines.parse_days(["Monday", "fri"]) == ["mon", "fri"])
    check("nonsense days refused", routines.parse_days(["someday"]) is None)

    print("=== the morning briefing ===")
    routines.ensure_morning_briefing()
    r = routines.load()[0]
    check("every Argus starts with one", r["name"] == "Morning briefing" and r["time"] == "08:00"
          and r["days"] == routines.DAYS[:5])
    mon = datetime.datetime(2026, 10, 19)                 # a Monday
    at = lambda h, m=0: mon.replace(hour=h, minute=m)
    check("not before 8", not routines.due(at(7, 59)))
    check("due at 8", [x["name"] for x in routines.due(at(8))] == ["Morning briefing"])
    check("catches up if the PC was asleep (10:30)", routines.due(at(10, 30)))
    check("but not hours later (11:30)", not routines.due(at(11, 30)))
    check("not on Saturday", not routines.due(mon.replace(day=24, hour=8, minute=5)))
    routines.mark_ran(r["id"], at(8))
    check("once a day", not routines.due(at(8, 1)))
    check("tomorrow again", routines.due(mon.replace(day=20, hour=8, minute=1)))

    print("=== changing them ===")
    routines.upsert("morning briefing", "7:30", "daily", "Give me my morning briefing.")
    check("same name moves it, no duplicate", len(routines.load()) == 1 and routines.load()[0]["time"] == "07:30")
    check("bad time refused", routines.upsert("x", "whenever", "daily", "do it") is None)
    check("removed", routines.remove("Morning Briefing") and routines.load() == [])


def skill_files():
    print("=== skills ===")
    skills.ensure_starters()
    names = [s["name"] for s in skills.all_skills()]
    check("starter skills", "Apply to a job" in names and "Morning briefing" in names, names)
    check("the planner sees names and when", "Apply to a job -- when:" in skills.for_planner())
    s = skills.save("Weekly review", "the user asks for a weekly review", "1. Read job-applications.md\n2. Sum it up")
    check("save one", s and s["when"] == "the user asks for a weekly review")
    check("find by name", skills.find(["weekly review"])[0]["name"] == "Weekly review")
    check("never a secret", skills.save("Bank", "paying", "use password hunter22 to log in") is None)
    p = Path(skills.folder(), "apply-to-a-job.md")
    p.write_text(p.read_text(encoding="utf-8") + "\nMy own note.\n", encoding="utf-8")
    skills.ensure_starters()
    check("the user's edits survive a restart", "My own note." in p.read_text(encoding="utf-8"))
    check("delete", skills.delete("Weekly review") and not skills.find(["Weekly review"]))


def protected():
    print("=== tools can't rewrite them ===")
    home = Path(os.path.expanduser("~"))
    for rel in [".argus/skills/apply-to-a-job.md", ".argus/routines.json", ".argus/memory.md",
                ".argus/browser/Default/Cookies"]:
        check("~/%s is off-limits to tools" % rel, is_protected(str(home / rel)))
    check("a workspace's own .argus/attachments is fine", not is_protected(str(TMP / "ws" / ".argus" / "attachments" / "a.png")))


class _Msg:
    def __init__(self, content): self.content, self.tool_calls = content, None


class _R:
    model_id = "stub"


class Router:
    catalogue_ids = []
    def __init__(self, replies): self.replies, self.sent = list(replies), []
    def for_tier(self, t): return _R()
    async def complete(self, tier, messages, **kw):
        self.sent.append((tier, messages))
        return _Msg(self.replies.pop(0)), {"tier": tier, "model": "stub", "prompt_tokens": 1,
                                            "completion_tokens": 1, "cost_usd": 0.0, "cumulative_cost_usd": 0.0}


class Bus:
    subscriber_count = 0
    def __init__(self): self.events = []
    async def emit(self, e): self.events.append(e)


async def chat():
    from core.agent import Agent
    from core.tools.registry import Registry
    print("=== in conversation ===")
    router = Router([
        json.dumps({"reply": "Done -- 7:30 on weekdays from now on.",
                    "routine": {"name": "Morning briefing", "time": "7:30", "days": "weekdays",
                                "prompt": "Give me my morning briefing. Follow the Morning briefing skill."}}),
        json.dumps({"reply": "Got it, saved.",
                    "save_skill": {"name": "Cover letters", "when": "a job wants a cover letter",
                                   "steps": "Three short paragraphs, no fluff, mention one real project."}}),
        json.dumps({"use_skills": ["Apply to a job"], "steps": [{"title": "Open the posting", "kind": "act"}]}),
        "Opened it.",                                          # the executor
        "The posting is open and ready.",                      # synthesis
    ])
    bus = Bus()
    agent = Agent(router, Registry(), bus, workspace=str(TMP / "ws"))
    await agent.run("yo move my briefing to 7 30")
    check("moving the briefing in chat", routines.load()[0]["time"] == "07:30", routines.load())
    check("planner sees the routines", "Routines" in router.sent[0][1][0]["content"])
    await agent.run("when i need a cover letter keep it short, 3 paragraphs, one real project")
    check("teaching a skill in chat", skills.find(["Cover letters"]))
    await agent.run("apply to this https://jobs.example.com/123")
    executor_prompt = next(m for t, m in router.sent[3:] if t == "executor")[0]["content"]
    check("the chosen skill reaches the step doing the work", "Follow these saved skills" in executor_prompt
          and "never invent" in executor_prompt.lower())


async def loop():
    print("=== the scheduler ===")
    os.environ["ARGUS_FAKE"] = "1"
    os.environ["TAVILY_API_KEY"] = ""
    from core import server
    ran = []

    async def fake_run(text, display=None, attachments=None):
        ran.append(display)
    server.session._run_agent = fake_run
    routines.upsert("Now thing", datetime.datetime.now().strftime("%H:%M"),
                    "daily", "Say hello.")
    task = asyncio.create_task(server.session.routine_loop(every=0.05))
    await asyncio.sleep(0.4)
    task.cancel()
    check("a due routine runs, once", ran == ["⏰ Now thing"], ran)


async def main():
    scheduling()
    skill_files()
    protected()
    await chat()
    await loop()
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")


asyncio.run(main())
sys.exit(0 if ok else 1)
