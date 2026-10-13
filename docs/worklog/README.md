# Worklog protocol

Two agents work this repo in parallel and cannot see each other's sessions.
These logs are how they stay in sync.

## Rules

1. **One writer per file.** `CORE.md` is written only by the core lane.
   `WEB.md` is written only by the web lane. Never edit the other's file —
   that is what keeps merges clean.
2. **Append only.** Newest entry at the top, under the header. Never rewrite
   or delete past entries.
3. **Read the other lane's log before you start work**, and again before you
   open a PR. If something there affects you, say so in your entry.
4. Log anything the other lane could trip over: new files, changed interfaces,
   installed deps, decisions, blockers, things you tried that failed.
   Do not log routine progress — this is a notice board, not a diary.

## Entry format

```
### 2026-10-13 14:20 — core
**Did:** Added three-tier router in `core/router.py`.
**Affects web:** `agent.thinking` now fires before every model call, not just
planning. Expect ~3x more of these events.
**Needs from web:** nothing.
**Watch out:** Ultra is served from us-central1, Nano from eu-north1 —
separate clients, don't reuse one base URL.
```

Keep it to four lines. If it needs more, it needs a conversation instead.
