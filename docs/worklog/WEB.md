# Web lane worklog
<!-- Written ONLY by the web lane (frontend, tools layer, sandbox runtime). -->
<!-- Newest entry at top. Append only. -->

### 2026-10-16 18:30 — web · browser
**Did:** Added opt-in MV3 browser sense, push sensor, lazy Playwright browse tool, pinned public-IP egress proxy, documentation and tests; extension-to-core latency 3.17s, real JS page and example.com reads pass.
**Affects core:** Registry adds `browser_tab` and `browse`; append-only dependency `playwright>=1.48` requires `python -m playwright install chromium`; existing meta.activity forwards browser results.
**Needs from core:** `scripts/test_tools.py` hardcodes six tools and must include `browse` (all its other checks, including live Tavily, pass); live agent tool choice awaits working Nebius credentials (HTTP 401).
**Watch out:** Browser profile/text never reused or persisted by the extension; sensitive defaults are editable. Extension acceptance used installed Edge Chromium because downloaded Chrome for Testing fails Windows side-by-side startup (14001).

### 2026-10-16 18:00 — web · terminal
**Did:** Added terminal wrapper/sensor, real Node crash fixture, seeder, offline tests and live acceptance harness; all seven core suites and TypeScript pass.
**Affects core:** Auto-discovered `terminal` polls at 0.5s; real crash reached LIVE UI in ~0.67s, `/health` lists terminal; screenshot in `web/evidence/terminal/`.
**Needs from core:** None yet; live prophecy/Proceed verification awaits a populated local Nebius key. Uncommitted raw evidence: `web/.local/terminal/argus-session.jsonl` (current failure is missing credentials).
**Watch out:** PR branch `codex/terminal-sensor` starts at `feat/web`; raw recordings and scratch workspace are ignored under `web/.local/`; first log discovery loads context without replaying history.

### (no entries yet)
