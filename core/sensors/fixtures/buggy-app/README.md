# Real terminal crash fixture

No dependencies: Node alone runs this app. It prints startup lines, then throws
a real TypeError at `watchlist.js:24` when the first quote response is missing.
The printed URL is illustrative; this fixture does not serve HTTP.

From the Argus repository (PowerShell):

```powershell
python core/sensors/fixtures/seed_buggy_app.py ../desk-dashboard
$env:ARGUS_WATCH_ROOT = (Resolve-Path ../desk-dashboard).Path
python -m core.server
```

Start the UI with `cd web` then `npm run dev`. In another terminal, from the
Argus repository, use the same `ARGUS_WATCH_ROOT` and run:

```powershell
python -m core.sensors.terminal_log run -- node ../desk-dashboard/dev.js
```

The terminal window should show the crash. Accept the watcher's offer and run
the same command again after the fix. A successful fix prints a green check
and exits 0. Rerun the seed script to reset the fixture (overwrites these four
fixture files only). Live model acceptance requires your local Nebius key.
`ARGUS_FAKE=1` uses the existing research script, so it cannot prove this fix.

For macOS/Linux set `export ARGUS_WATCH_ROOT=...`. The wrapper tees stdout and
stderr unchanged to the console, removes ANSI in `.argus/terminal.log`, writes
command/exit markers, and propagates the child's exit code. Start the core
before the command: pre-existing log history is context, never replayed alerts.
Additional opted-in logs go in `ARGUS_LOGS`, separated by `;` on Windows or `:`
on macOS/Linux. They may be outside the workspace; don't opt in sensitive logs.
