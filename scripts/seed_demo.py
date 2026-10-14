"""Build the demo workspace: a project folder where the user has just dropped
in their (slightly stale) research notes and opened an empty notes.md.

    python scripts/seed_demo.py --reset     # empty workspace (start the server now)
    python scripts/seed_demo.py --drop      # drop the files in (the watcher notices)

Default location: ../mark-ii next to the repo, so the agent never writes into
the codebase. Override with ARGUS_DEMO_DIR.

The notes are deliberately out of date: written in December 2025, they say
Nemotron 3 Ultra "is not available yet". It has since shipped and is on Token
Factory -- which is exactly the kind of thing ARGUS should catch.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_pdf import make_pdf

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "mark-ii")
DEMO_DIR = os.path.abspath(os.environ.get("ARGUS_DEMO_DIR", DEFAULT_DIR))

NEMOTRON_NOTES = [
    "Personal notes, written after the launch announcement. Not an official document.",
    "Nemotron 3 is NVIDIA's open model family: hybrid Mamba-Transformer mixture-of-experts, "
    "long context, open weights and open training data.",
    "Nano (30B total, about 3B active) is available now. Fast and cheap -- good for agent "
    "tool calls.",
    "Super (about 100B) and Ultra (about 500B) were announced but are NOT available yet. "
    "Expected sometime in the first half of 2026.",
    "Plan for Mark II: run everything on Nano for now, including planning. Switch planning "
    "to Super when it ships. Ultra is probably out of reach for this project.",
    "Open questions: Will Ultra be served on any hosted API, or self-host only? "
    "How much will the bigger models cost per million tokens?",
]

TOKEN_FACTORY_NOTES = [
    "Personal notes on setting up Nebius Token Factory. Not an official document.",
    "OpenAI-compatible API. Use the openai Python SDK with base URL "
    "https://api.tokenfactory.nebius.com/v1/ and an API key in NEBIUS_API_KEY.",
    "Nano pricing when I checked: roughly $0.06 per million input tokens.",
    "To check: which Nemotron 3 models are on Token Factory today, and what Super and Ultra "
    "cost. Also whether there is a spending limit -- I do not want surprise charges.",
]


def reset() -> None:
    if os.path.isdir(DEMO_DIR):
        shutil.rmtree(DEMO_DIR)
    os.makedirs(DEMO_DIR)
    print("reset: %s (empty)" % DEMO_DIR)


def drop() -> None:
    os.makedirs(os.path.join(DEMO_DIR, "refs"), exist_ok=True)
    make_pdf(os.path.join(DEMO_DIR, "refs", "nemotron-3-launch-notes.pdf"),
             "Nemotron 3 launch notes (December 2025)", NEMOTRON_NOTES)
    make_pdf(os.path.join(DEMO_DIR, "refs", "token-factory-setup-notes.pdf"),
             "Token Factory setup notes", TOKEN_FACTORY_NOTES)
    open(os.path.join(DEMO_DIR, "notes.md"), "w").close()
    print("dropped: refs/nemotron-3-launch-notes.pdf, refs/token-factory-setup-notes.pdf, notes.md (empty)")


if __name__ == "__main__":
    args = set(sys.argv[1:]) or {"--reset", "--drop"}
    if "--reset" in args:
        reset()
    if "--drop" in args:
        drop()
