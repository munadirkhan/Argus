"""Scripted model responses for ARGUS_FAKE=1.

Lets the real server, real tools, real websocket and real UI run end to end
with no API key and no network. Used for frontend development and as a safety
net if the demo machine loses connectivity.
"""
import json

from .fake import Turn

_PLAN = json.dumps({"steps": [
    {"title": "Search the web for what changed recently"},
    {"title": "Read the local reference files"},
    {"title": "Write the summary to disk"},
]})

_OBSERVE = json.dumps({
    "speak": True,
    "confidence": 0.86,
    "observation": "You pulled two papers into refs/ and opened an empty notes.md.",
    "suggestion": "Want me to pull the current literature and draft that summary?",
})

_ANSWER = ("Written to notes.md. One thing worth flagging: the June result your "
           "local paper builds on was superseded in August, so I'd check that "
           "before you go further.")

DEMO_SCRIPT = {
    # watcher tier
    "lightning": [
        Turn(text=json.dumps({"speak": False}), prompt_tokens=14200, completion_tokens=11),
        Turn(text=_OBSERVE, prompt_tokens=18400, completion_tokens=95),
        Turn(text=json.dumps({"speak": False}), prompt_tokens=18900, completion_tokens=11),
    ],
    # planner tier
    "ultra": [
        Turn(text=_PLAN, prompt_tokens=3200, completion_tokens=640),
        Turn(text=_ANSWER, prompt_tokens=4100, completion_tokens=180),
    ],
    # executor tier
    "nano": [
        Turn(tool_calls=[("tavily_search",
                          {"query": "diffusion sampling advances 2026", "max_results": 6})],
             prompt_tokens=1900, completion_tokens=180),
        Turn(text="Found six results; the newest is from August.",
             prompt_tokens=2400, completion_tokens=90),
        Turn(tool_calls=[("list_dir", {"path": "."})],
             prompt_tokens=2200, completion_tokens=110),
        Turn(text="Two PDFs in refs/, both predating August.",
             prompt_tokens=2500, completion_tokens=80),
        Turn(tool_calls=[("write_file", {
            "path": "notes.md",
            "content": ("# Diffusion sampling - what changed since June 2026\n\n"
                        "Three things actually moved. Everything else is noise.\n\n"
                        "## 1. Consistency-matched samplers\n\n"
                        "The June result your local paper builds on was superseded "
                        "in August.\n")})],
             prompt_tokens=2600, completion_tokens=210),
        Turn(text="Wrote the summary to notes.md.",
             prompt_tokens=2800, completion_tokens=70),
    ],
}
