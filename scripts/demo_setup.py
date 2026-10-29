"""Set up (or reset) the demo workspace for recording the video.

    python scripts/demo_setup.py --reset

Creates demo/workspace with a small Node dashboard that really crashes
(`node dashboard/dev.js` -> TypeError), an empty earnings-watch.md, an
about-me.md and a placeholder resume. --reset puts the bug back and clears
what the last take wrote, so every take starts the same.
"""
import os, shutil, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.demo import BROKEN_JS  # noqa: E402

WS = os.path.join(ROOT, "demo", "workspace")

FILES = {
    "dashboard/package.json": '{\n  "name": "desk-dashboard",\n  "type": "module",\n  "private": true\n}\n',
    "dashboard/quotes.js": """// Quotes API client. v2 of the API returns { results: [...] }.
const SAMPLE = [
  { symbol: "NVDA", price: 187.42 },
  { symbol: "AMD", price: 162.25 },
  { symbol: "TSM", price: 204.73 },
];

export async function getQuotes(symbols) {
  const results = SAMPLE.filter((q) => symbols.includes(q.symbol));
  return { results, fetchedAt: Date.now() };
}
""",
    "dashboard/watchlist.js": BROKEN_JS,
    "dashboard/dev.js": """import { renderWatchlist } from "./watchlist.js";

console.log("  dashboard ready on :5173");
console.log(await renderWatchlist(["NVDA", "AMD", "TSM"]));
""",
    "earnings-watch.md": "",
    "notes/journal.md": "# October\n\n- Holding NVDA into earnings. Last time it beat on EPS and still fell.\n"
                        "- Need to know what actually moves it this time.\n",
    "about-me.md": "# About me\n\n- Name: Munadir Khan\n- Studying Computer Science\n"
                   "- Looking for junior software roles\n- Work authorization: Yes\n- Earliest start: May 2027\n",
}


def main() -> None:
    try:
        urllib.request.urlopen("http://127.0.0.1:7600/health", timeout=1)
        sys.exit("Argus is already running. Quit it from the tray first, then start the demo.")
    except OSError:
        pass
    if "--reset" in sys.argv and os.path.isdir(WS):
        shutil.rmtree(WS, ignore_errors=True)
    for rel, content in FILES.items():
        full = os.path.join(WS, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if "--reset" in sys.argv or not os.path.exists(full):
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
    pdf = os.path.join(WS, "resume.pdf")
    if not os.path.exists(pdf):
        with open(pdf, "wb") as f:
            f.write(b"%PDF-1.4\n% placeholder resume for the demo\n")
    print("Demo workspace ready:", WS)


if __name__ == "__main__":
    main()
