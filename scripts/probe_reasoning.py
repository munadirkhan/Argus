"""Second probe: Nemotron 3 models are reasoning models. Find out where the
thinking goes, and which switch turns it off, so JSON-mode calls (the watcher,
the planner) get clean output.

Usage:  python scripts/probe_reasoning.py
"""
import json, os, sys, time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
KEY = os.environ.get("NEBIUS_API_KEY") or sys.exit("Set NEBIUS_API_KEY")
client = OpenAI(base_url="https://api.tokenfactory.us-central1.nebius.com/v1/",
                api_key=KEY, timeout=120)

MODELS = {
    "lightning": "nvidia/Nemotron-3_5-Lightning",
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
}

TASK = ('Decide whether to interrupt a user who just created notes.md next to two '
        'PDFs. Respond with JSON only: {"speak": true|false, "reason": "<short>"}')

VARIANTS = {
    "default": {},
    "kwargs_off": {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
    "no_think_sys": {"system": "/no_think"},
    "reasoning_effort_low": {"extra_body": {"reasoning_effort": "low"}},
}


def run(model, variant):
    msgs = []
    if "system" in variant:
        msgs.append({"role": "system", "content": variant["system"]})
    msgs.append({"role": "user", "content": TASK})
    kw = dict(model=model, messages=msgs, max_tokens=600, temperature=0.3,
              response_format={"type": "json_object"})
    if "extra_body" in variant:
        kw["extra_body"] = variant["extra_body"]
    t0 = time.time()
    try:
        r = client.chat.completions.create(**kw)
    except Exception as e:
        return {"error": str(e)[:100]}
    m = r.choices[0].message
    content = m.content or ""
    raw = m.model_dump() if hasattr(m, "model_dump") else {}
    reasoning = raw.get("reasoning_content") or raw.get("reasoning") or ""
    try:
        json.loads(content)
        valid = True
    except Exception:
        valid = False
    return {
        "lat": round(time.time() - t0, 2),
        "out_tok": r.usage.completion_tokens,
        "finish": r.choices[0].finish_reason,
        "json_ok": valid,
        "has_think_tag": "<think>" in content,
        "reasoning_field": len(reasoning),
        "content": content[:70].replace("\n", " "),
    }


results = {}
for fam, mid in MODELS.items():
    print("\n## %s  (%s)" % (fam, mid))
    for vname, v in VARIANTS.items():
        res = run(mid, v)
        results["%s/%s" % (fam, vname)] = res
        if "error" in res:
            print("  %-22s ERROR %s" % (vname, res["error"]))
        else:
            print("  %-22s json=%-5s out=%-4d think_field=%-5d tag=%-5s %5.2fs | %s"
                  % (vname, res["json_ok"], res["out_tok"], res["reasoning_field"],
                     res["has_think_tag"], res["lat"], res["content"]))

json.dump(results, open("scripts/probe_reasoning_results.json", "w"), indent=2)
print("\nwrote scripts/probe_reasoning_results.json")
