# Round 2 UI acceptance

The LIVE UI consumes the core websocket and `/health` on port 7600. No model
calls happen in the browser. Start the core, then `npm ci` and `npm run dev`
in this folder. The design retains the v1 dark palette, fonts, borders and orb.

- Terminal windows show the last sensor window, wrap long lines, scroll to the
  newest line, and flash newly arrived error rows once. Overlapping old rows
  retain their DOM identity during bursts.
- SENSES reads the registered sensors from `/health`, plus the core filesystem
  watcher. Indicators pulse amber for 2 seconds on activity; idle is dim gold.
- With an offer open: **Enter** proceeds and **Esc** dismisses. **/** focuses the
  composer. Shortcuts leave input fields, editable content and native buttons
  alone. The same shortcuts work in SIMULATE without sending requests to core.
- **Shift+R**, or RECORD in the header, starts/stops a LIVE recording. Stopping
  downloads `argus-session.jsonl`. It preserves raw websocket JSON and timestamps,
  including unknown fields, and seeds the last session/tree events for path
  anonymization. Switching to SIMULATE stops and saves it. Recording automatically
  saves at 10 MB. Raw logs are local: do not commit them.
- **`?record=1`** hides the pointer, omits composer placeholder text and leaves
  the initial eyes idling, without pointer-follow motion. Real events still
  drive the gaze and moods.

Convert an actual recording with the existing core-owned converter:

```powershell
python scripts/record_replay.py web/.local/terminal-success/ui-recording.jsonl web/mock/recorded-code.json
```

The included **Code (recorded)** scene comes from the successful real-model run:
the watcher named `watchlist.js:24`, Proceed read and rewrote it, and the next
wrapped run exited 0. Detection was approximately 1.15 seconds. The converter
anonymized workspace paths; the original raw JSONL is ignored. Montage uses this
recording between illustrative Markets and recorded Research. Replay identifiers
are scoped by montage segment so separate live sessions cannot overwrite plans.

Verify using `npx tsc --noEmit -p .`, `npm run build`, and from the repository
`python web/tests/test_ui.py` with Vite running. Browser tests use an isolated
contract fixture, require Playwright/Chromium, and make no model calls. They
check 1920×1080 and 1280×720, shortcuts, recorder, terminal bursts, pulses and
video mode. Real acceptance screenshots live under `web/evidence/`.
Use `python web/tests/test_ui.py --evidence web/evidence/ui` to capture the recorded
Code scene at both required sizes. Real browser-agent acceptance is reproducible
with `python core/tools/tests/accept_browse.py` (uses the configured core budget).

Integration gate: the core-owned `scripts/test_tools.py` still expects exactly six
tools. Core must add `browse` before the browser PR can satisfy the brief's test
gate. All other core checks and the new sensor/tool suites pass. No frozen files
were edited to bypass this assertion.

Final verification: browser regression checks pass at both resolutions with no
console errors; TypeScript and production build pass. The existing large-bundle
build warning remains. An installed Chromium sample of 180 animation frames at
1920×1080 measured 60 fps; this is a short local sample, not a hardware-independent
performance guarantee. No new runtime web dependencies were added.
