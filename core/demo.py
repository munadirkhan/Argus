"""Scripted demo mode (ARGUS_DEMO=1): a director that plays believable Argus
behaviour through the REAL app -- hub, floating orb, voice, approval cards --
without calling a model. For recording the demo video reliably.

The presenter drives it:
  - Ctrl+Alt+1 / Ctrl+Alt+2 (desktop, demo mode only): Argus "notices"
    something -- the markets beat, or the dev-server crash. PROCEED runs it.
  - Typing or talking (Ctrl+Alt+J): the message is matched to a beat by its
    words (see BEATS). What you say is shown and transcribed for real.
  - Ctrl+Alt+S: the real screenshot goes in; the answer is the scripted one
    for demo/props/ci-failure.html, so open that page first.
  - STOP / Esc really cancels; ALLOW / DENY really decide.

Everything else is real: files are written into the demo workspace, the
voice is synthesized, settings and themes work. The hub labels the session
"scripted demo" so the video is honest about it.
"""
from __future__ import annotations
import asyncio, itertools, os, re

from . import events
from .approvals import APPROVALS

MODELS = {"watcher": "nvidia/Nemotron-3_5-Lightning", "planner": "nvidia/Nemotron-3-Ultra-550b-a55b",
          "executor": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "vision": "nvidia/Nemotron-3.5-Super-VL"}
# Tests run the beats fast (ARGUS_DEMO_SPEED=0.02); 1 = real pacing for the video.
SPEED = float(os.environ.get("ARGUS_DEMO_SPEED", "1"))
PRICE = {"watcher": (0.06, 0.24), "planner": (1.0, 3.0), "executor": (0.06, 0.24), "vision": (0.30, 0.90)}

BROKEN_JS = """// Watchlist: renders the live quote for each symbol.
import { getQuotes } from "./quotes.js";

export async function renderWatchlist(symbols) {
  const quotes = await getQuotes(symbols);
  return quotes.data.map((q) => `${q.symbol.padEnd(5)} ${q.price.toFixed(2)}`).join("\\n");
}
"""

FIXED_JS = """// Watchlist: renders the live quote for each symbol.
import { getQuotes } from "./quotes.js";

export async function renderWatchlist(symbols) {
  const quotes = await getQuotes(symbols);
  // The quotes API returns { results: [...] } since v2 -- `data` no longer exists,
  // so the first render crashed. Read `results`, and tolerate an empty reply.
  const rows = quotes.results ?? [];
  return rows.map((q) => `${q.symbol.padEnd(5)} ${q.price.toFixed(2)}`).join("\\n");
}
"""

EARNINGS_DOC = """# NVDA into earnings: what to watch

**Bottom line:** the stock will trade on data-center revenue and next-quarter
guidance, not the headline EPS. Last quarter beat on EPS and still fell on a
soft data-center number.

## The three numbers that matter
1. **Data-center revenue**: the whole story. Consensus sits just above last
   quarter's record; a miss here outweighs any beat elsewhere [1][2].
2. **Next-quarter guidance**: the market is pricing in another step up. Flat
   guidance would read as a peak [1].
3. **Gross margin**: watch whether new rack-scale systems dilute it [3].

## What changed since your journal entry
- Supply commentary has turned more confident [2].
- Options imply a larger-than-usual move on the day [3].

## Sources
1. Reuters: earnings preview
2. CNBC: what analysts are watching
3. Nasdaq: options-implied move
"""

APPLY_FIELDS = ("Name: Munadir Khan\nEmail: (from about-me.md)\nResume: resume.pdf\n"
                "Work authorization: Yes\nStart date: May 2027\nCover note: 3 short paragraphs")


class Director:
    def __init__(self, session) -> None:
        self.s = session
        self.bus = session.bus
        self.root = session.root
        self.cum = 0.0
        self._ids = itertools.count(1)
        self.offers: dict[str, str] = {}          # observation id -> beat to run on PROCEED

    # --- little timeline helpers -------------------------------------------
    def nid(self, p: str) -> str:
        return "demo_%s_%d" % (p, next(self._ids))

    async def wait(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000 * SPEED)

    async def think(self, tier: str, note: str) -> None:
        await self.bus.emit(events.agent_thinking("planner" if tier == "vision" else tier, MODELS[tier], note))

    async def use(self, tier: str, pin: int, pout: int) -> None:
        cin, cout = PRICE[tier]
        cost = (pin * cin + pout * cout) / 1_000_000
        self.cum += cost
        await self.bus.emit(events.usage("planner" if tier == "vision" else tier, MODELS[tier],
                                         pin, pout, cost, self.cum))

    async def say(self, role: str, text: str, attachments=None) -> None:
        await self.bus.emit(events.agent_message(self.nid("m"), role, text, attachments=attachments))
        self.s.agent.transcript.append({"role": role, "content": text})

    async def plan(self, titles: list[str]) -> tuple[str, list[str]]:
        pid = self.nid("plan")
        ids = ["s%d" % (i + 1) for i in range(len(titles))]
        await self.bus.emit(events.agent_plan(pid, [{"id": i, "title": t, "status": "pending"}
                                                    for i, t in zip(ids, titles)]))
        return pid, ids

    async def step(self, pid: str, sid: str, status: str) -> None:
        await self.bus.emit(events.agent_step(pid, sid, status))

    async def tool(self, name: str, args: dict, ms: int, summary: str, detail: str = "") -> None:
        tid = self.nid("tc")
        await self.bus.emit(events.tool_call(tid, name, args))
        await self.wait(ms)
        await self.bus.emit(events.tool_result(tid, True, summary, detail))

    async def activity(self, **kw) -> None:
        await self.bus.emit({"type": "activity", **kw})

    async def write(self, rel: str, content: str, kind: str = "md") -> None:
        """A real file in the demo workspace, so the editor and Archive update for real."""
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        data = content.encode("utf-8")
        await self.tool("write_file", {"path": rel}, 180, "%.1f KB written to %s" % (len(data) / 1024, rel))
        await self.bus.emit(events.artifact_write(full.replace("\\", "/"), kind, len(data), content[:4000]))

    # --- entry points ------------------------------------------------------
    async def run(self, text: str, display=None, attachments=None, screen=None) -> None:
        """Called inside the server's agent lock, so STOP cancels it like a real run."""
        try:
            if screen:
                await self.say("user", text or "What's on my screen?", [screen])
                await self.snap()
            elif text.startswith("__accept__:"):
                await self.say("user", "Go ahead.")
                beat = self.offers.pop(text.split(":", 1)[1], "")
                await getattr(self, beat, self.chat)()
            else:
                await self.say("user", display or text, attachments)
                await self.route(text)()
        except asyncio.CancelledError:
            await self.bus.emit(events.agent_stopped())
            await self.say("assistant", "Stopped.")

    def route(self, text: str):
        t = text.lower()
        for pattern, beat in BEATS:
            if re.search(pattern, t):
                return getattr(self, beat)
        return self.chat

    async def cue(self, name: str) -> bool:
        """The presenter's hidden hotkeys: Argus notices something."""
        beat = {"markets": self.notice_markets, "code": self.notice_crash}.get(name)
        if not beat:
            return False
        await beat()
        return True

    # --- the beats ----------------------------------------------------------
    async def notice_markets(self) -> None:
        await self.activity(source="market", app="Chart", title="NVDA · 15m", focus=True,
                            market={"symbol": "NVDA", "price": 187.42, "change": 1.84, "interval": "15m"})
        await self.wait(1200)
        await self.activity(source="browser", app="Browser", title="NVIDIA Investor Relations: upcoming earnings call",
                            url="investor.nvidia.com/events", focus=True, lines=[
                                {"text": "Upcoming events", "tone": "hl"},
                                {"text": "Quarterly financial results conference call"},
                                {"text": "Webcast · Investor Relations"}])
        await self.wait(1500)
        await self.think("watcher", "Observing")
        await self.wait(900)
        await self.use("watcher", 1180, 41)
        oid = self.nid("obs")
        self.offers[oid] = "earnings_brief"
        await self.bus.emit(events.watcher_observation(
            oid, "You've had NVDA open for a while, with the earnings-call page up.",
            "Want me to pull what analysts are watching into the call and write you a one-page brief?", 0.88))

    async def earnings_brief(self) -> None:
        await self.think("planner", "Decomposing request")
        await self.wait(1100)
        await self.use("planner", 2240, 310)
        pid, s = await self.plan(["Search what analysts are watching into the call",
                                  "Read last quarter's earnings release",
                                  "Write the brief to earnings-watch.md"])
        await self.step(pid, s[0], "running")
        await self.think("executor", "Calling tools")
        await self.activity(source="browser", app="Argus · search", title="Searching: NVIDIA earnings preview",
                            url="tavily · reuters.com, cnbc.com, nasdaq.com", focus=True, lines=[
                                {"text": "[1] Reuters: NVIDIA earnings preview", "tone": "hl"},
                                {"text": "[2] CNBC: what analysts are watching"},
                                {"text": "[3] Nasdaq: options-implied move"}])
        await self.tool("tavily_search", {"query": "NVIDIA earnings preview what analysts are watching"}, 2200,
                        "6 sources · reuters.com, cnbc.com, nasdaq.com")
        await self.use("executor", 4300, 96)
        await self.step(pid, s[0], "done")
        await self.step(pid, s[1], "running")
        await self.tool("fetch_url", {"url": "https://investor.nvidia.com/news/prior-quarter-results"}, 1600,
                        "investor.nvidia.com · 18,204 chars")
        await self.use("executor", 9100, 140)
        await self.step(pid, s[1], "done")
        await self.step(pid, s[2], "running")
        await self.think("planner", "Writing earnings-watch.md")
        await self.wait(2400)
        await self.use("planner", 15800, 1260)
        await self.write("earnings-watch.md", EARNINGS_DOC)
        await self.step(pid, s[2], "done")
        await self.think("planner", "Synthesising result")
        await self.wait(800)
        await self.use("planner", 3100, 64)
        await self.say("assistant", "The brief is in earnings-watch.md. Watch data-center revenue and next "
                       "quarter's guidance. That's what moved the stock last time, not the headline EPS.")

    async def notice_crash(self) -> None:
        await self.activity(source="editor", app="Editor", title="dashboard/watchlist.js", startLine=1, focus=True,
                            lines=[{"text": l, "tone": "code"} for l in BROKEN_JS.splitlines()], errorLine=5)
        await self.wait(900)
        await self.activity(source="terminal", app="Terminal", title="node dev.js", focus=True, lines=[
            {"text": "$ node dev.js", "tone": "dim"},
            {"text": "  dashboard ready on :5173", "tone": "ok"},
            {"text": "✗ TypeError: Cannot read properties of undefined (reading 'map')", "tone": "err"},
            {"text": "    at renderWatchlist (dashboard/watchlist.js:6:22)", "tone": "err"}])
        await self.wait(1200)
        await self.think("watcher", "Observing")
        await self.wait(700)
        await self.use("watcher", 980, 38)
        oid = self.nid("obs")
        self.offers[oid] = "fix_crash"
        await self.bus.emit(events.watcher_observation(
            oid, "Your dashboard just crashed: TypeError at watchlist.js line 6.",
            "Want me to find the cause and patch watchlist.js?", 0.93))

    async def fix_crash(self) -> None:
        await self.think("planner", "Decomposing request")
        await self.wait(900)
        await self.use("planner", 1980, 220)
        pid, s = await self.plan(["Read dashboard/watchlist.js and dashboard/quotes.js",
                                  "Write the fix to dashboard/watchlist.js"])
        await self.step(pid, s[0], "running")
        await self.think("executor", "Calling tools")
        await self.tool("read_file", {"path": "dashboard/watchlist.js"}, 600, "watchlist.js · 8 lines")
        await self.tool("read_file", {"path": "dashboard/quotes.js"}, 500, "quotes.js · 14 lines")
        await self.use("executor", 3100, 80)
        await self.step(pid, s[0], "done")
        await self.step(pid, s[1], "running")
        await self.think("planner", "Writing dashboard/watchlist.js")
        await self.wait(2200)
        await self.use("planner", 6400, 420)
        await self.write("dashboard/watchlist.js", FIXED_JS, "code")
        await self.step(pid, s[1], "done")
        await self.activity(source="terminal", app="Terminal", title="node dev.js", focus=True, lines=[
            {"text": "$ node dev.js", "tone": "dim"},
            {"text": "  [reload] dashboard/watchlist.js", "tone": "dim"},
            {"text": "  dashboard ready on :5173 · 0 errors", "tone": "ok"}])
        await self.say("assistant", "Fixed. The quotes API renamed data to results in v2, so the first render "
                       "crashed. watchlist.js reads results now and copes with an empty reply.")

    async def snap(self) -> None:
        await self.think("vision", "Looking at your screen")
        await self.wait(2200)
        await self.use("vision", 1840, 210)
        await self.say("assistant",
            "Your CI is failing on a peer-dependency clash, not your code.\n\n"
            "react-markdown 8 wants React 18, and you upgraded to React 19. Two ways out:\n"
            "1. Upgrade it: npm i react-markdown@10 (supports React 19). Best fix.\n"
            "2. Or unblock CI now: add --legacy-peer-deps to the npm ci step.\n\n"
            "Go with 1; option 2 just hides the clash.")

    async def acronym(self) -> None:
        await self.think("planner", "Answering")
        await self.wait(900)
        await self.use("planner", 2100, 60)
        await self.say("assistant", "A Really Good User System. And the name's older than the acronym: "
                       "Argus Panoptes, the hundred-eyed giant of Greek myth who never slept. I just do it "
                       "with a spending limit.")

    async def apply_job(self) -> None:
        await self.think("planner", "Decomposing request")
        await self.wait(1000)
        await self.use("planner", 2600, 280)
        pid, s = await self.plan(["Find the resume and read about-me.md",
                                  "Open the posting and fill in the application",
                                  "Submit it, with your go-ahead"])
        await self.step(pid, s[0], "running")
        await self.think("executor", "Calling tools")
        await self.tool("find_files", {"name": "resume", "types": "pdf"}, 700, "1 match: resume.pdf")
        await self.tool("read_file", {"path": "about-me.md"}, 500, "about-me.md · 22 lines")
        await self.use("executor", 2900, 70)
        await self.step(pid, s[0], "done")
        await self.step(pid, s[1], "running")
        filled = []
        for line in ["Opened jobs.example.com/junior-engineer", "Typed Name", "Typed Email",
                     "Chose Work authorization: Yes", "Attached resume.pdf", "Typed Cover note"]:
            filled.append({"text": line, "tone": "hl" if not filled else None})
            await self.activity(source="browser", app="Argus · hands", title="Apply: Junior Engineer, Example Co",
                                url="jobs.example.com/junior-engineer", focus=True,
                                lines=[{k: v for k, v in l.items() if v} for l in filled[-6:]])
            await self.wait(900)
        await self.use("executor", 8800, 260)
        await self.step(pid, s[1], "done")
        await self.step(pid, s[2], "running")
        ok = await APPROVALS.ask("confirm", 'Click "Submit application" on jobs.example.com', detail=APPLY_FIELDS,
                                 url="https://jobs.example.com/junior-engineer", timeout=180)
        if not ok:
            await self.step(pid, s[2], "failed")
            await self.say("assistant", "Held off. The application is filled in and waiting in my browser, "
                           "so you can check it and submit when you're ready.")
            return
        await self.activity(source="browser", app="Argus · hands", title="Application received",
                            url="jobs.example.com/junior-engineer/thanks", focus=True,
                            lines=[{"text": "Thanks, your application was received.", "tone": "ok"}])
        await self.write("job-applications.md", "# Job applications\n\n"
                         "| Date | Company | Role | Status |\n|---|---|---|---|\n"
                         "| today | Example Co | Junior Engineer | Submitted |\n")
        await self.step(pid, s[2], "done")
        await self.say("assistant", "Submitted. I logged it in job-applications.md, and I'll flag it if they write back.")

    async def deep_research(self) -> None:
        """Long on purpose: the beat to show STOP on."""
        await self.think("planner", "Decomposing request")
        await self.wait(1100)
        await self.use("planner", 2400, 340)
        pid, s = await self.plan(["Survey the market and the main players", "Read the latest filings",
                                  "Compare pricing and growth", "Write the report"])
        await self.step(pid, s[0], "running")
        for q in ["AI PC market size 2026", "on-device assistant competitors", "agent pricing models",
                  "Nemotron enterprise adoption", "desktop agent privacy concerns"]:
            await self.think("executor", "Searching: " + q)
            await self.tool("tavily_search", {"query": q}, 3200, "5 sources")
            await self.use("executor", 3800, 90)
        await self.step(pid, s[0], "done")
        await self.step(pid, s[1], "running")
        await self.wait(30000)
        await self.say("assistant", "Report's in market-scan.md.")

    async def briefing(self) -> None:
        await self.think("planner", "Morning briefing")
        await self.wait(800)
        await self.tool("tavily_search", {"query": "top news today"}, 1600, "6 sources")
        await self.use("executor", 3600, 90)
        await self.think("planner", "Synthesising")
        await self.wait(1000)
        await self.use("planner", 4200, 160)
        await self.say("assistant", "Morning. Cloudy, nine degrees, clearing by noon. Two things matter today: "
                       "NVIDIA reports after the close, and your brief is ready in earnings-watch.md. Your "
                       "Example Co application went through yesterday; nothing back yet. Last night's "
                       "dashboard crash is patched. That's all. Go have a good one.")

    async def chat(self) -> None:
        await self.think("planner", "Answering")
        await self.wait(1000)
        await self.use("planner", 1900, 70)
        await self.say("assistant", "On it. In this recording I'm running a scripted demo: ask me what my "
                       "name stands for, have me apply to a job, or press the look-at-my-screen key.")


# First match wins. Phrases the presenter will say or type.
BEATS = [
    (r"stand for|your name|who are you|what are you", "acronym"),
    (r"\bapply\b|application|\bjob\b", "apply_job"),
    (r"research|deep dive|report on|market scan", "deep_research"),
    (r"briefing|morning|what's on today", "briefing"),
    (r"earnings|nvidia|nvda|brief", "earnings_brief"),
    (r"crash|error|fix|bug", "fix_crash"),
]
