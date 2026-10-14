"""The ARGUS agent loop: plan with Ultra, execute with Nano, synthesise with Ultra.

Flow for one user request:

    planner  (Ultra)  -> decompose into 2-5 concrete steps
    executor (Nano)   -> work each step with native tool calling
    planner  (Ultra)  -> synthesise the result into a final answer

Every stage emits contract events so the UI can show the routing live.
"""
from __future__ import annotations
import datetime, json, itertools, os, re

from . import events
from .bus import EventBus
from .models import BudgetExceeded, ModelRouter
from .prompts import PLANNER_SYSTEM, EXECUTOR_SYSTEM, WRITER_SYSTEM, SYNTH_SYSTEM
from .tools.registry import Registry
from .tools._workspace import SKIP_DIRS, human_size

WRITER_TOOLS = {"write_file", "read_file"}    # the writer writes; it does not research

MAX_TOOL_ITERS = 6
MAX_STEPS = 5
MATERIAL_PER_TOOL = 5000      # chars of each tool output carried forward
MATERIAL_PER_STEP = 18000
MATERIAL_FOR_SYNTH = 24000

_FENCE = chr(96) * 3
_FENCE_RE = re.compile(_FENCE + r"(?:json)?\s*(.+?)" + _FENCE, re.S)


def list_files(root, limit=80):
    """Workspace file list for prompts, so no stage ever guesses a path."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            out.append("- %s (%s)" % (rel, "empty" if size == 0 else human_size(size)))
            if len(out) >= limit:
                return "\n".join(out + ["- ... (more files not shown)"])
    return "\n".join(out) or "- (empty)"


def _today():
    return datetime.date.today().isoformat()


def extract_json(text):
    """Models wrap JSON in prose or code fences more often than they should."""
    if not text:
        return None
    candidates = [text] + _FENCE_RE.findall(text)
    for candidate in candidates:
        candidate = candidate.strip()
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            continue
    return None


def msg_to_dict(msg):
    """Normalise an SDK message object into an OpenAI-shaped dict."""
    out = {"role": "assistant", "content": getattr(msg, "content", None) or ""}
    tcs = getattr(msg, "tool_calls", None)
    if tcs:
        out["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tcs
        ]
    return out


class Agent:
    def __init__(self, router: ModelRouter, registry: Registry, bus: EventBus,
                 workspace: str | None = None) -> None:
        self.router = router
        self.registry = registry
        self.bus = bus
        self.workspace = os.path.abspath(
            workspace or os.environ.get("ARGUS_WATCH_ROOT") or os.getcwd())
        self._ids = itertools.count(1)
        self.transcript = []

    def _nid(self, prefix):
        return "%s_%d" % (prefix, next(self._ids))

    async def _emit_usage(self, u):
        await self.bus.emit(events.usage(
            u["tier"], u["model"], u["prompt_tokens"], u["completion_tokens"],
            u["cost_usd"], u["cumulative_cost_usd"]))

    # --- stage 1: plan (Ultra) ------------------------------------------
    async def plan(self, goal):
        r = self.router.for_tier("planner")
        await self.bus.emit(events.agent_thinking("planner", r.model_id, "Decomposing request"))

        tool_list = "\n".join("- %s: %s" % (t.name, t.description)
                              for t in self.registry.tools.values()) or "- (none)"
        msg, u = await self.router.complete(
            "planner",
            [{"role": "system", "content": PLANNER_SYSTEM.format(
                tool_list=tool_list, workspace=self.workspace, today=_today(),
                files=list_files(self.workspace))},
             {"role": "user", "content": goal}],
            response_format={"type": "json_object"},
            max_tokens=2000, temperature=0.3,
        )
        await self._emit_usage(u)

        parsed = extract_json(getattr(msg, "content", "") or "")
        raw_steps = (parsed or {}).get("steps") or []
        steps = []
        for s in raw_steps:
            if isinstance(s, dict):
                t = str(s.get("title", "")).strip()
                if t:
                    kind = "write" if str(s.get("kind", "")).lower() == "write" else "act"
                    steps.append({"title": t, "kind": kind})
        if not steps:
            steps = [{"title": goal, "kind": "act"}]
        steps = steps[:MAX_STEPS]
        for i, st in enumerate(steps):
            st["id"] = "s%d" % (i + 1)

        plan_id = self._nid("plan")
        # The contract's step shape is {id, title, status}; `kind` stays internal.
        await self.bus.emit(events.agent_plan(plan_id, [
            {"id": st["id"], "title": st["title"], "status": "pending"} for st in steps]))
        return plan_id, steps

    # --- stage 2: execute one step ----------------------------------------
    async def execute_step(self, goal, step, prior):
        """Run one step with tools. Returns (summary, material).

        `material` is the substance the tools returned -- search results, PDF
        text -- so later steps (and the writer) work from real content rather
        than from a one-line summary of it.
        """
        writing = step.get("kind") == "write"
        tier = "planner" if writing else "executor"      # Ultra writes the artifact
        r = self.router.for_tier(tier)
        context = ""
        if prior:
            context = "\n\nMaterial gathered by earlier steps:\n\n" + "\n\n".join(prior)
        system = (WRITER_SYSTEM if writing else EXECUTOR_SYSTEM).format(
            step=step["title"], goal=goal, workspace=self.workspace, context=context,
            today=_today(), files=list_files(self.workspace))
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Do this step now: " + step["title"]},
        ]
        schemas = [s for s in self.registry.schemas()
                   if not writing or s["function"]["name"] in WRITER_TOOLS]
        summary, material = "", []
        note = "Writing the document" if writing else "Calling tools"
        wrote = None

        for _ in range(MAX_TOOL_ITERS):
            await self.bus.emit(events.agent_thinking(tier, r.model_id, note))
            msg, u = await self.router.complete(
                tier, messages, tools=schemas or None,
                max_tokens=8000 if writing else 1500)
            await self._emit_usage(u)
            messages.append(msg_to_dict(msg))

            tcs = getattr(msg, "tool_calls", None)
            if not tcs:
                summary = (getattr(msg, "content", "") or "").strip()
                break

            for tc in tcs:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                await self.bus.emit(events.tool_call(tc.id, name, args))
                result = await self.registry.call(name, args)
                await self.bus.emit(events.tool_result(
                    tc.id, result.ok, result.summary, result.detail[:2000]))

                if name == "write_file" and result.ok:
                    await self._emit_artifact(args, result)
                    wrote = result.summary
                if result.ok and result.detail and name != "write_file":
                    material.append("[%s %s]\n%s" % (
                        name, json.dumps(args)[:160], result.detail[:MATERIAL_PER_TOOL]))

                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": result.for_model()})

            # A writing step is finished the moment the document lands. Left
            # to itself the writer keeps "improving" it into extra files.
            if writing and wrote:
                summary = wrote
                break

        summary = summary or ("(no summary returned for: %s)" % step["title"])
        mat = "\n\n".join(material)[:MATERIAL_PER_STEP]
        return summary, mat

    async def _emit_artifact(self, args, result):
        path = str(result.meta.get("path") or args.get("path", ""))
        content = str(args.get("content", ""))
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "txt"
        kind = {"md": "md", "json": "json", "py": "code", "ts": "code",
                "js": "code", "tsx": "code"}.get(ext, "txt")
        nbytes = result.meta.get("bytes", len(content.encode("utf-8")))
        await self.bus.emit(events.artifact_write(
            path.replace("\\", "/"), kind, nbytes, content[:4000]))

    # --- stage 3: synthesise (Ultra) -------------------------------------
    async def synthesise(self, goal, notes):
        r = self.router.for_tier("planner")
        await self.bus.emit(events.agent_thinking("planner", r.model_id, "Synthesising result"))
        joined = "\n\n".join("[%d] %s" % (i + 1, f) for i, f in enumerate(notes))
        msg, u = await self.router.complete(
            "planner",
            [{"role": "system", "content": SYNTH_SYSTEM + "\n\nToday's date: " + _today()},
             {"role": "user", "content":
              "The user asked: %s\n\nYour working notes from each step:\n%s\n\n"
              "Now write your reply to the user." % (goal, joined[:MATERIAL_FOR_SYNTH])}],
            max_tokens=500, temperature=0.6, thinking=False,
        )
        await self._emit_usage(u)
        return (getattr(msg, "content", "") or "").strip() or "Done."

    # --- the whole thing --------------------------------------------------
    async def run(self, goal, display=None):
        """Handle one user request end to end. `display` is what the chat shows
        as the user's message when it differs from the goal the model gets."""
        await self.bus.emit(events.agent_message(self._nid("m"), "user", display or goal))
        self.transcript.append({"role": "user", "content": goal})

        try:
            plan_id, steps = await self.plan(goal)
            material, notes = [], []

            for step in steps:
                await self.bus.emit(events.agent_step(plan_id, step["id"], "running"))
                try:
                    summary, mat = await self.execute_step(goal, step, material)
                    notes.append("%s: %s" % (step["title"], summary))
                    if mat:
                        material.append("## From step: %s\n%s" % (step["title"], mat))
                    await self.bus.emit(events.agent_step(plan_id, step["id"], "done"))
                except BudgetExceeded:
                    await self.bus.emit(events.agent_step(plan_id, step["id"], "failed"))
                    raise                       # stop the whole run, not just this step
                except Exception as e:
                    await self.bus.emit(events.agent_step(plan_id, step["id"], "failed"))
                    await self.bus.emit(events.error(
                        "step failed: %s: %s" % (type(e).__name__, e)))
                    notes.append("%s: FAILED (%s)" % (step["title"], e))

            answer = await self.synthesise(goal, notes + material)
        except Exception as e:
            await self.bus.emit(events.error("%s: %s" % (type(e).__name__, e), fatal=False))
            answer = "I hit a problem and stopped: %s" % e

        await self.bus.emit(events.agent_message(self._nid("m"), "assistant", answer))
        self.transcript.append({"role": "assistant", "content": answer})
        return answer
