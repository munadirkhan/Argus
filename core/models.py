"""Three-tier Nemotron routing over Nebius Token Factory.

ARGUS deliberately uses three different Nemotron models, because the product
forces it:

  watcher  -> Nemotron 3.5 Lightning  1M ctx @ $0.06/M -- runs constantly,
                                       must be cheap and hold huge context
  planner  -> Nemotron 3 Ultra 550B   the reasoning moment, used rarely
  executor -> Nemotron 3 Nano 30B     fast, high-volume tool calls

Model IDs are RESOLVED AT STARTUP against the live /v1/models rather than
hardcoded. Published IDs disagree with the live catalogue on casing -- Nebius's
own cookbook says `nvidia/nvidia-nemotron-3-nano-30b-a3b`, the API serves
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` -- so matching is case-insensitive.

Reasoning is switched PER TIER (probed live, see scripts/probe_reasoning.py).
All Nemotron 3 models think by default. That is what the planner is for, and
Ultra keeps its reasoning in a separate field so the answer stays clean. On the
hot path it is pure cost: Lightning with thinking on spills its reasoning into
the answer and breaks JSON (600 tokens, 2.8s); with it off it returns valid
JSON in 25 tokens and 0.8s.
"""
from __future__ import annotations
import os, asyncio, json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Tier = Literal["watcher", "planner", "executor"]

BASE_US = os.environ.get("NEBIUS_BASE_US", "https://api.tokenfactory.us-central1.nebius.com/v1/")
BASE_EU = os.environ.get("NEBIUS_BASE_EU", "https://api.tokenfactory.eu-north1.nebius.com/v1/")


@dataclass(frozen=True)
class ModelSpec:
    """A model family we know how to find and price."""
    key: str                      # substring to match in the live catalogue
    region: str                   # "us" | "eu"
    price_in: float               # USD per 1M prompt tokens
    price_out: float              # USD per 1M completion tokens
    fallback_id: str              # used if catalogue lookup fails

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.price_in + completion_tokens * self.price_out) / 1_000_000


CATALOGUE: dict[str, ModelSpec] = {
    # All four verified live in us-central1 (2026-10-14).
    "lightning": ModelSpec("lightning", "us", 0.06, 0.24, "nvidia/Nemotron-3_5-Lightning"),
    "nano":      ModelSpec("nano",      "us", 0.06, 0.24, "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    "super":     ModelSpec("super",     "us", 0.30, 0.90, "nvidia/nemotron-3-super-120b-a12b"),
    "ultra":     ModelSpec("ultra",     "us", 1.00, 3.00, "nvidia/Nemotron-3-Ultra-550b-a55b"),
}

TIER_PREFERENCE: dict[Tier, tuple[str, ...]] = {
    "watcher":  ("lightning", "nano", "super"),
    "planner":  ("ultra", "super", "nano"),
    "executor": ("nano", "lightning", "super"),
}

# Reasoning on only where it earns its tokens.
TIER_THINKING: dict[Tier, bool] = {
    "watcher":  False,      # Lightning breaks JSON with thinking on
    "planner":  True,       # the reasoning moment
    "executor": False,      # fast tool calls; the plan is already made
}

_NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


@dataclass
class Resolved:
    tier: Tier
    family: str
    model_id: str
    region: str
    spec: ModelSpec


class BudgetExceeded(RuntimeError):
    """Raised instead of making a model call once the spend cap is reached."""


@dataclass
class Spend:
    """Running cost, reported to the UI on every call.

    When `path` is set, the ledger is persisted to disk after every call and
    reloaded on startup, so the budget is a real cap across restarts rather
    than one that quietly resets every time the server comes back up.
    """
    total_usd: float = 0.0
    by_tier: dict[str, float] = field(default_factory=dict)
    calls: int = 0
    path: str | None = None

    def add(self, tier: str, usd: float) -> float:
        self.total_usd += usd
        self.by_tier[tier] = self.by_tier.get(tier, 0.0) + usd
        self.calls += 1
        self.save()
        return self.total_usd

    def save(self) -> None:
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"total_usd": self.total_usd, "by_tier": self.by_tier,
                       "calls": self.calls}, f)
        os.replace(tmp, self.path)          # atomic: never leaves a torn ledger

    @classmethod
    def load(cls, path: str | None) -> "Spend":
        if not path or not os.path.exists(path):
            return cls(path=path)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            return cls(total_usd=float(d.get("total_usd", 0.0)),
                       by_tier=dict(d.get("by_tier", {})),
                       calls=int(d.get("calls", 0)), path=path)
        except (OSError, ValueError, TypeError):
            # A corrupt ledger must fail CLOSED: assume the budget is spent
            # rather than silently restarting the count at zero.
            print("[router] spend ledger unreadable at %s; refusing to spend" % path)
            return cls(total_usd=float("inf"), path=path)


DEFAULT_BUDGET_USD = float(os.environ.get("ARGUS_BUDGET_USD", "10"))


class ModelRouter:
    """Owns per-region clients, tier resolution, cost accounting, and the cap."""

    def __init__(self, api_key: str | None = None,
                 client_factory: Callable[[str, str], Any] | None = None,
                 budget_usd: float | None = None,
                 ledger_path: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("NEBIUS_API_KEY", "")
        self._client_factory = client_factory or self._default_client_factory
        self._clients: dict[str, Any] = {}
        self.resolved: dict[Tier, Resolved] = {}
        self.budget_usd = DEFAULT_BUDGET_USD if budget_usd is None else budget_usd
        self.spend = Spend.load(ledger_path)
        self.catalogue_ids: list[str] = []
        self._warned = False

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.spend.total_usd)

    def check_budget(self) -> None:
        if self.spend.total_usd >= self.budget_usd:
            raise BudgetExceeded(
                "Spend cap reached: $%.4f of $%.2f. Raise ARGUS_BUDGET_USD to continue."
                % (self.spend.total_usd, self.budget_usd))

    def _default_client_factory(self, region: str, api_key: str) -> Any:
        from openai import AsyncOpenAI
        base = BASE_US if region == "us" else BASE_EU
        return AsyncOpenAI(base_url=base, api_key=api_key, timeout=180.0, max_retries=2)

    def client(self, region: str) -> Any:
        if region not in self._clients:
            self._clients[region] = self._client_factory(region, self.api_key)
        return self._clients[region]

    async def _list_models(self, region: str) -> list[str]:
        try:
            res = await self.client(region).models.list()
            return [m.id for m in res.data]
        except Exception as e:
            print(f"[router] catalogue lookup failed for {region}: {type(e).__name__}: {e}")
            return []

    async def resolve(self) -> dict[Tier, Resolved]:
        """Discover real model IDs, then bind each tier to the best available."""
        us, eu = await asyncio.gather(self._list_models("us"), self._list_models("eu"))
        live = {"us": us, "eu": eu}
        self.catalogue_ids = sorted(set(us) | set(eu))

        def find(spec: ModelSpec) -> str | None:
            for mid in live.get(spec.region, []):
                low = mid.lower()
                if "nemotron" in low and spec.key in low:
                    return mid
            return None

        for tier, prefs in TIER_PREFERENCE.items():
            bound: Resolved | None = None
            for family in prefs:
                spec = CATALOGUE[family]
                mid = find(spec)
                if mid:
                    bound = Resolved(tier, family, mid, spec.region, spec)
                    break
            if bound is None:
                family = prefs[0]
                spec = CATALOGUE[family]
                bound = Resolved(tier, family, spec.fallback_id, spec.region, spec)
                print(f"[router] {tier}: no live match, using fallback {spec.fallback_id}")
            self.resolved[tier] = bound
        return self.resolved

    def for_tier(self, tier: Tier) -> Resolved:
        if tier not in self.resolved:
            spec = CATALOGUE[TIER_PREFERENCE[tier][0]]
            self.resolved[tier] = Resolved(tier, spec.key, spec.fallback_id, spec.region, spec)
        return self.resolved[tier]

    async def complete(self, tier: Tier, messages: list[dict[str, Any]],
                       tools: list[dict] | None = None,
                       max_tokens: int = 2048,
                       temperature: float = 0.6,
                       response_format: dict | None = None,
                       thinking: bool | None = None) -> tuple[Any, dict[str, Any]]:
        """Call the model bound to `tier`.

        Returns (message, usage_info) where usage_info carries the numbers the
        UI needs for the routing HUD and the cost meter.
        """
        self.check_budget()                 # refuse BEFORE spending, never after
        r = self.for_tier(tier)
        kwargs: dict[str, Any] = {
            "model": r.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format
        think = TIER_THINKING[tier] if thinking is None else thinking
        if not think:
            kwargs["extra_body"] = _NO_THINK

        resp = await self.client(r.region).chat.completions.create(**kwargs)

        u = getattr(resp, "usage", None)
        pin = getattr(u, "prompt_tokens", 0) or 0
        pout = getattr(u, "completion_tokens", 0) or 0
        cost = r.spec.cost(pin, pout)
        cumulative = self.spend.add(tier, cost)
        if not self._warned and cumulative >= 0.8 * self.budget_usd:
            self._warned = True
            print("[router] WARNING: spent $%.4f of $%.2f budget"
                  % (cumulative, self.budget_usd), flush=True)

        msg = resp.choices[0].message
        reasoning = (getattr(msg, "reasoning_content", None)
                     or getattr(msg, "reasoning", None) or "")
        return msg, {
            "tier": tier, "model": r.model_id, "family": r.family,
            "prompt_tokens": pin, "completion_tokens": pout,
            "cost_usd": cost, "cumulative_cost_usd": cumulative,
            "thinking": think, "reasoning_chars": len(reasoning),
            "finish_reason": getattr(resp.choices[0], "finish_reason", None),
        }

    def describe(self) -> str:
        lines = ["tier       family      model id                                          region"]
        for tier in ("watcher", "planner", "executor"):
            r = self.for_tier(tier)
            lines.append(f"{tier:10} {r.family:11} {r.model_id:49} {r.region}")
        return "\n".join(lines)
