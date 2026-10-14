"""The ARGUS agent loop: plan with Ultra, execute with Nano, synthesise with Ultra.

Flow for one user request:

    planner  (Ultra)  -> decompose into 2-5 concrete steps
    executor (Nano)   -> work each step with native tool calling
    planner  (Ultra)  -> synthesise the result into a final answer

Every stage emits contract events so the UI can show the routing live.
"""
from __future__ import annotations
import json, itertools, re

from . import events
from .bus import EventBus
from .models import BudgetExceeded, ModelRouter
from .prompts import PLANNER_SYSTEM, EXECUTOR_SYSTEM, SYNTH_SYSTEM
from .tools.registry import Registry

MAX_TOOL_ITERS = 6
MAX_STEPS = 5

_FENCE = chr(96) * 3
_FENCE_RE = re.compile(_FENCE + r"(?:json)?\s*(.+?)" + _FENCE, re.S)


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
    def __init__(self, router: ModelRouter, registry: Registry, bus: EventBus) -> None:
        self.router = router
        self.registry = registry
        self.bus = bus
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
            [{"role": "system", "content": PLANNER_SYSTEM.format(tool_list=tool_list)},
             {"role": "user", "content": goal}],
            response_format={"type": "json_object"},
            max_tokens=2000, temperature=0.3,
        )
        await self._emit_usage(u)

        parsed = extract_json(getattr(msg, "content", "") or "")
        raw_steps = (parsed or {}).get("steps") or []
        titles = []
        for s in raw_steps:
            if isinstance(s, dict):
                t = str(s.get("title", "")).strip()
                if t:
                    titles.append(t)
        if not titles:
            titles = [goal]
        titles = titles[:MAX_STEPS]

        plan_id = self._nid("plan")
        steps = [{"id": "s%d" % (i + 1), "title": t, "status": "pending"}
                 for i, t in enumerate(titles)]
        await self.bus.emit(events.agent_plan(plan_id, steps))
        return plan_id, steps

    # --- stage 2: execute one step (Nano + tools) ------------------------
    async def execute_step(self, goal, step, prior):
        r = self.router.for_tier("executor")
        context = ""
        if prior:
            context = "\nWhat earlier steps found:\n" + "\n".join("- " + p for p in prior)
        messages = [
            {"role": "system", "content": EXECUTOR_SYSTEM.format(
                step=step["title"], goal=goal, context=context)},
            {"role": "user", "content": "Do this step now: " + step["title"]},
        ]
        schemas = self.registry.schemas()
        findings = ""

        for _ in range(MAX_TOOL_ITERS):
            await self.bus.emit(events.agent_thinking("executor", r.model_id, "Calling tools"))
            msg, u = await self.router.complete(
                "executor", messages, tools=schemas or None, max_tokens=1200)
            await self._emit_usage(u)
            messages.append(msg_to_dict(msg))

            tcs = getattr(msg, "tool_calls", None)
            if not tcs:
                findings = (getattr(msg, "content", "") or "").strip()
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

                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": result.for_model()})
        return findings or ("(no summary returned for: %s)" % step["title"])

    async def _emit_artifact(self, args, result):
        path = str(args.get("path", ""))
        content = str(args.get("content", ""))
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "txt"
        kind = {"md": "md", "json": "json", "py": "code", "ts": "code",
                "js": "code", "tsx": "code"}.get(ext, "txt")
        nbytes = result.meta.get("bytes", len(content.encode("utf-8")))
        await self.bus.emit(events.artifact_write(path, kind, nbytes, content[:1200]))

    # --- stage 3: synthesise (Ultra) -------------------------------------
    async def synthesise(self, goal, findings):
        r = self.router.for_tier("planner")
        await self.bus.emit(events.agent_thinking("planner", r.model_id, "Synthesising result"))
        joined = "\n\n".join("[%d] %s" % (i + 1, f) for i, f in enumerate(findings))
        msg, u = await self.router.complete(
            "planner",
            [{"role": "system", "content": SYNTH_SYSTEM},
             {"role": "user", "content":
              "The user asked: %s\n\nYour working notes from each step:\n%s\n\n"
              "Now write your reply to the user." % (goal, joined)}],
            max_tokens=1500, temperature=0.7,
        )
        await self._emit_usage(u)
        return (getattr(msg, "content", "") or "").strip() or "Done."

    # --- the whole thing --------------------------------------------------
    async def run(self, goal):
        """Handle one user request end to end."""
        await self.bus.emit(events.agent_message(self._nid("m"), "user", goal))
        self.transcript.append({"role": "user", "content": goal})

        try:
            plan_id, steps = await self.plan(goal)
            findings = []

            for step in steps:
                await self.bus.emit(events.agent_step(plan_id, step["id"], "running"))
                try:
                    found = await self.execute_step(goal, step, findings)
                    findings.append("%s: %s" % (step["title"], found))
                    await self.bus.emit(events.agent_step(plan_id, step["id"], "done"))
                except BudgetExceeded:
                    await self.bus.emit(events.agent_step(plan_id, step["id"], "failed"))
                    raise                       # stop the whole run, not just this step
                except Exception as e:
                    await self.bus.emit(events.agent_step(plan_id, step["id"], "failed"))
                    await self.bus.emit(events.error(
                        "step failed: %s: %s" % (type(e).__name__, e)))
                    findings.append("%s: FAILED (%s)" % (step["title"], e))

            answer = await self.synthesise(goal, findings)
        except Exception as e:
            await self.bus.emit(events.error("%s: %s" % (type(e).__name__, e), fatal=False))
            answer = "I hit a problem and stopped: %s" % e

        await self.bus.emit(events.agent_message(self._nid("m"), "assistant", answer))
        self.transcript.append({"role": "assistant", "content": answer})
        return answer
