# Recording the demo video (3:00 max)

The app runs in **scripted demo mode**: the real hub, floating orb, voice,
approval cards and settings, with Argus's answers scripted so every take is
reliable and costs nothing. The header shows **LIVE · SCRIPTED DEMO**, so the
video is honest about it. Say so once in the narration too (beat 1).

## Before you record

1. **Quit your normal Argus** (tray icon -> Quit Argus).
2. **Double-click `Run-Demo.cmd`** in the repo. It resets the demo workspace
   (puts the bug back, clears last take's files) and starts Argus.
   Re-run it before every take.
3. **Recorder:** record the **whole display**, not a window, or the orb won't be
   in it: OBS "Display Capture" at 1080p 30fps, or Snipping Tool -> Record ->
   full screen. Mic on for narration (or narrate afterwards).
4. **Set up the windows** (all on the display you record):
   - Chrome with two tabs: **finance.yahoo.com/quote/NVDA** and
     **`demo/props/ci-failure.html`** (drag the file into Chrome).
   - **VS Code** opened on `demo/workspace`, with `dashboard/watchlist.js` open
     and a terminal ready in `demo/workspace`.
   - The Argus hub in front. Theme: **Panoptes** (gold) to start; you switch to
     Arc Reactor at the end. VOICE on (header).
5. Do one practice run. The voice and speech model take ~5 s to load the
   first time after launch.

## Hidden keys (only in demo mode)

| Keys | What happens |
|---|---|
| **Ctrl+Alt+1** | Argus notices you looking at NVDA and offers an earnings brief |
| **Ctrl+Alt+2** | Argus notices the dashboard crash and offers to fix it |
| Ctrl+Alt+J | Talk (press, speak, press again). What you say is really transcribed. |
| Ctrl+Alt+S | Look at my screen (have the CI page in front) |
| Ctrl+Alt+A | Show / hide the hub |
| Esc / STOP | Stop Argus mid-task |

What you **say or type** picks the scripted answer, so use these phrases:
- "...what does your name **stand for**?" -> the acronym
- "...**apply** to the junior engineer **job** at Example Co" -> fills it, asks ALLOW / DENY
- "...do a **deep dive** report on the AI PC market" -> a long run, to STOP

## The shot list (~2:55)

| Time | On screen | Do | Say (suggested; M = Munadir, D = Darsh) | Argus |
|---|---|---|---|---|
| **0:00–0:15** | Hub, the hundred-eyed sphere | Nothing; let the eyes move | M: "This is Argus: A Really Good User System. Named for Argus Panoptes, the giant with a hundred eyes who never slept. It lives on your PC, watches what you're working on, and helps before you ask. What you're seeing is our scripted demo mode, so every take is the same." | — |
| **0:15–0:45** | Chrome on NVDA; **the orb** floats bottom-right | Click into Chrome (orb appears). After a beat press **Ctrl+Alt+1**. When the card slides out, click **PROCEED**. | D: "I tab out to my browser. Argus stays with me as this orb... and it's noticed I've been on NVDA before earnings." (after PROCEED) "It plans, searches with Tavily, reads the release, and writes the brief. Without opening anything." | Speaks the offer; card shows **AT WORK**; then speaks: "The brief is in earnings-watch.md..." |
| **0:45–1:05** | Still in Chrome | **Ctrl+Alt+J**, say *"Argus, what does your name stand for?"*, **Ctrl+Alt+J** | M: "I can just talk to it. No hub, no typing." | Orb shows what you said, then speaks the acronym |
| **1:05–1:35** | VS Code + terminal | In the terminal: `node dashboard/dev.js`: it really crashes. Press **Ctrl+Alt+2**, click **PROCEED**. When it's done, run `node dashboard/dev.js` again. | D: "My dashboard crashes. Argus sees the stack trace in my terminal and offers to fix it... and the fix is written straight into the file. Run it again: works." | Notices the TypeError; writes the fix to `watchlist.js` (VS Code updates); speaks the cause |
| **1:35–1:55** | Chrome on the CI page | **Ctrl+Alt+S** | M: "Stuck on something on screen? One key. Argus takes a snapshot and reads it with Nemotron's vision model." | Answer panel slides out beside the orb, spoken; hit **COPY** |
| **1:55–2:25** | Hub (Ctrl+Alt+A) | Type or say *"Apply to the junior engineer job at Example Co for me"*. When the **ARGUS ASKS** card appears, pause on it, then **ALLOW**. | D: "Argus has its own browser. It fills the application from my resume... but anything final, like submit, pay, post, waits for my yes." | Browser window in the hub fills the form; card shows exactly what was filled; "Submitted. I logged it..." |
| **2:25–2:35** | Hub | Say or type *"Do a deep dive report on the AI PC market"*; after ~3 s press **Esc** | M: "And if it's going somewhere I don't want, one key stops it dead." | Starts searching... **Stopped.** |
| **2:35–2:52** | The Sanctum (**Ctrl+,**) | Appearance -> click **Arc Reactor** (everything recolours). Then **Minds**, then **Tribute**. | D: "Everything's in the Sanctum: themes, the voice, which Nemotron model does which job, priced live from Nebius, and a hard spending limit it can never go over." | — |
| **2:52–3:00** | Hub, Arc Reactor theme | Nothing | M: "Four Nemotron models on Nebius Token Factory, Tavily for the web, and voice that never leaves your machine. Argus. It's on GitHub." | — |

**If you're over time**, cut in this order: the STOP beat, the Tribute page,
the second `node dashboard/dev.js` run.

**Retake a beat?** Quit Argus (tray), re-run `Run-Demo.cmd`, start that beat
again. Cut the takes together afterwards.

## After recording

Upload to YouTube as **Public** (not unlisted), max 3:00, and put the link in
Devpost.
