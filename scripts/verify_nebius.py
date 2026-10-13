"""
Probe Nebius Token Factory: which Nemotron models exist, in which region,
how fast they are, and -- critically -- whether they do tool calling.

Usage:  export NEBIUS_API_KEY=...   &&   python scripts/verify_nebius.py
"""
import os, sys, time, json

try:
    from openai import OpenAI
except ImportError:
    sys.exit("pip install openai")

try:  # load .env if present
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

KEY = os.environ.get("NEBIUS_API_KEY")
if not KEY:
    sys.exit("Set NEBIUS_API_KEY first.")

REGIONS = {
    "us-central1": "https://api.tokenfactory.us-central1.nebius.com/v1/",
    "eu-north1":   "https://api.tokenfactory.eu-north1.nebius.com/v1/",
    "default":     "https://api.tokenfactory.nebius.com/v1/",
}

# per 1M tokens (input, output), from the public catalog
PRICING = {
    "nano": (0.06, 0.24), "lightning": (0.06, 0.24),
    "super": (0.30, 0.90), "ultra": (1.00, 3.00),
}

def tier_of(mid):
    m = mid.lower()
    for t in ("lightning", "ultra", "super", "nano"):
        if t in m:
            return t
    return None

WEATHER_TOOL = [{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file from the user's local disk.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute file path"}},
            "required": ["path"],
        },
    },
}]


def discover():
    """Find every nemotron model and which region actually serves it."""
    found = {}  # model_id -> region
    for region, base in REGIONS.items():
        try:
            client = OpenAI(base_url=base, api_key=KEY, timeout=30)
            models = client.models.list()
        except Exception as e:
            print(f"  [{region:12}] unreachable: {str(e)[:80]}")
            continue
        ids = [m.id for m in models.data]
        nem = [i for i in ids if "nemotron" in i.lower()]
        print(f"  [{region:12}] {len(ids):3} models, {len(nem)} nemotron")
        for i in nem:
            found.setdefault(i, region)
    return found


def probe(model_id, region):
    base = REGIONS[region]
    client = OpenAI(base_url=base, api_key=KEY, timeout=120)
    out = {"model": model_id, "region": region}

    # 1. basic completion + latency
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=16,
        )
        out["latency_s"] = round(time.time() - t0, 2)
        out["reply"] = (r.choices[0].message.content or "").strip()[:40]
        u = r.usage
        out["tokens"] = f"{u.prompt_tokens}in/{u.completion_tokens}out"
        tier = tier_of(model_id)
        if tier and tier in PRICING:
            pin, pout = PRICING[tier]
            cost = (u.prompt_tokens * pin + u.completion_tokens * pout) / 1_000_000
            out["cost_usd"] = f"{cost:.8f}"
            out["tier"] = tier
    except Exception as e:
        out["error"] = str(e)[:140]
        return out

    # 2. THE important one: does it do tool calling?
    try:
        r = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Read the file at C:/notes/plan.txt for me."}],
            tools=WEATHER_TOOL,
            tool_choice="auto",
            max_tokens=256,
        )
        tc = r.choices[0].message.tool_calls
        if tc:
            call = tc[0]
            args = json.loads(call.function.arguments)
            ok = call.function.name == "read_file" and "plan.txt" in str(args.get("path", ""))
            out["tools"] = "YES (correct)" if ok else f"YES (odd args: {args})"
        else:
            out["tools"] = "NO tool_call returned"
    except Exception as e:
        out["tools"] = f"ERROR {str(e)[:90]}"

    # 3. structured output / JSON mode
    try:
        r = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": 'Return JSON: {"status":"ok"}'}],
            response_format={"type": "json_object"},
            max_tokens=64,
        )
        json.loads(r.choices[0].message.content)
        out["json_mode"] = "YES"
    except Exception as e:
        out["json_mode"] = f"NO ({str(e)[:50]})"

    return out


print("\n=== Discovering Nemotron models across regions ===")
found = discover()

if not found:
    sys.exit("\nNo nemotron models found. Check your API key / account access.")

print(f"\n=== Found {len(found)} nemotron model(s). Probing each ===\n")
results = []
for mid, region in sorted(found.items()):
    print(f"-> {mid}  ({region})")
    res = probe(mid, region)
    results.append(res)
    for k, v in res.items():
        if k not in ("model", "region"):
            print(f"     {k:10} {v}")
    print()

with open("scripts/nebius_probe_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("=== SUMMARY ===")
print(f"{'tier':10} {'model id':48} {'region':12} {'tools':16} {'lat':>6}")
for r in results:
    if "error" in r:
        print(f"{'?':10} {r['model'][:48]:48} {r['region']:12} ERROR")
    else:
        print(f"{r.get('tier','?'):10} {r['model'][:48]:48} {r['region']:12} "
              f"{str(r.get('tools'))[:16]:16} {r.get('latency_s','?'):>6}")
print("\nWrote scripts/nebius_probe_results.json")
