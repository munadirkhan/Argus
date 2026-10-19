"""Event constructors for the ARGUS websocket contract (docs/EVENT_CONTRACT.md v1).

Every function here returns a plain dict ready to be JSON-serialised. The
envelope fields (`v`, `seq`, `ts`) are stamped by the EventBus, not here, so
these stay pure and trivially testable.
"""
from __future__ import annotations
from typing import Any, Literal

Tier = Literal["watcher", "planner", "executor"]
StepStatus = Literal["pending", "running", "done", "failed"]
RuntimeKind = Literal["local", "sandbox"]
RuntimeStatus = Literal["connected", "connecting", "degraded"]


def session_state(runtime: RuntimeKind, status: RuntimeStatus, cwd: str,
                  label: str) -> dict[str, Any]:
    return {"type": "session.state", "runtime": runtime, "status": status,
            "cwd": cwd, "label": label}


def watcher_observation(id: str, observation: str, suggestion: str,
                        confidence: float, dismissible: bool = True) -> dict[str, Any]:
    return {"type": "watcher.observation", "id": id, "confidence": round(confidence, 3),
            "observation": observation, "suggestion": suggestion,
            "dismissible": dismissible}


def agent_message(id: str, role: Literal["user", "assistant"], text: str,
                  streaming: bool = False, done: bool = True,
                  attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ev = {"type": "agent.message", "id": id, "role": role, "text": text,
          "streaming": streaming, "done": done}
    if attachments:                      # additive: files the user attached
        ev["attachments"] = [{k: a.get(k) for k in ("path", "name", "bytes", "kind")}
                             for a in attachments]
    return ev


def agent_plan(id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "agent.plan", "id": id, "steps": steps}


def agent_step(plan_id: str, id: str, status: StepStatus) -> dict[str, Any]:
    return {"type": "agent.step", "plan_id": plan_id, "id": id, "status": status}


def agent_thinking(tier: Tier, model: str, note: str) -> dict[str, Any]:
    return {"type": "agent.thinking", "tier": tier, "model": model, "note": note}


def tool_call(id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool.call", "id": id, "name": name, "args": args}


def tool_result(id: str, ok: bool, summary: str, detail: str = "") -> dict[str, Any]:
    return {"type": "tool.result", "id": id, "ok": ok, "summary": summary,
            "detail": detail}


def artifact_write(path: str, kind: str, bytes_: int, preview: str) -> dict[str, Any]:
    return {"type": "artifact.write", "path": path, "kind": kind,
            "bytes": bytes_, "preview": preview}


def fs_tree(root: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "fs.tree", "root": root, "nodes": nodes}


def usage(tier: Tier, model: str, prompt_tokens: int, completion_tokens: int,
          cost_usd: float, cumulative_cost_usd: float) -> dict[str, Any]:
    return {"type": "usage", "tier": tier, "model": model,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "cost_usd": round(cost_usd, 8),
            "cumulative_cost_usd": round(cumulative_cost_usd, 6)}


def error(message: str, fatal: bool = False) -> dict[str, Any]:
    return {"type": "error", "message": message, "fatal": fatal}


# --- every type the contract defines, for validation in tests ---
CONTRACT_TYPES = {
    "session.state", "watcher.observation", "agent.message", "agent.plan",
    "agent.step", "agent.thinking", "tool.call", "tool.result",
    "artifact.write", "fs.tree", "usage", "error",
}
CLIENT_TYPES = {"user.message", "user.dismiss"}


def approval(id: str, kind: str, title: str, detail: str, url: str,
             timeout_s: int) -> dict[str, Any]:
    """Argus wants the user's go-ahead (kind "confirm") or needs them to do
    something themselves, like signing in (kind "handoff")."""
    return {"type": "agent.approval", "id": id, "kind": kind, "title": title,
            "detail": detail, "url": url, "timeout_s": timeout_s}


def approval_resolved(id: str, outcome: str) -> dict[str, Any]:
    """outcome: approved | denied | expired | cancelled"""
    return {"type": "agent.approval.resolved", "id": id, "outcome": outcome}
