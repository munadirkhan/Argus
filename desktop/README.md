# Argus on the desktop

The web hub, wrapped as a desktop app so Argus is *there* while you work —
not just while its tab is open.

| Piece | What it does |
|---|---|
| **Hub** | The full interface, in its own window. Closing it doesn't quit Argus. |
| **Floating orb** | Whenever the hub isn't in front, the hundred-eyed orb floats on top of everything — browser, file explorer, video, borderless games. Click it to open the hub. Drag it anywhere; it remembers where. |
| **The orb speaks** | When Argus notices something while you're elsewhere, a card slides out beside the orb with the offer — **Proceed** runs it without leaving what you're doing. Replies and progress show there too. |
| **Voice** | Push-to-talk, transcribed **on this machine** (faster-whisper). Your voice never leaves the computer. |
| **Tray** | Open, talk, change the watched folder, toggle the orb, start with Windows, quit. |
| **Core** | Starts the Python core if one isn't already running, and stops it on quit. |

## Hotkeys (work from any app)

| Keys | Action |
|---|---|
| `Ctrl+Alt+A` | Show / hide the hub |
| `Ctrl+Alt+Space` | Talk to Argus — press, speak, press again to send |

## Run it

Windows: double-click **`Argus.cmd`** in the repo root. It installs and builds on
first run, then launches.

Or by hand:

```bash
cd desktop
npm install
npm run build:web      # builds ../web/dist, which the app loads
npm start
```

Developing the UI? Run the Vite dev server (`cd web && npm run dev`) and start
the desktop with `npm run dev` — it loads http://localhost:5173 with hot reload.

The watched folder defaults to `~/Argus`. Change it from the tray, or set
`ARGUS_WATCH_ROOT` before launching.

## Notes

- **Exclusive-fullscreen games**: nothing can draw over a game running in
  exclusive fullscreen (that's how Windows works — overlays like Discord's hook
  the game itself). Borderless / windowed-fullscreen games, which most modern
  games default to, show the orb fine.
- **Voice model**: the first use downloads Whisper `base.en` (~145 MB) once.
  Set `ARGUS_STT_MODEL=small.en` for more accuracy, `tiny.en` for speed.
- **Permissions**: the app grants the microphone (audio only) and nothing else.
  The pages are sandboxed and context-isolated; the only bridge is
  `preload.js`.

## Test

```bash
npm test            # drives the real app: orb, card, hub, tray lifecycle,
                    # a spoken WAV fed in as the microphone, a real attachment
```

The test needs port 7600 free (it starts its own core in fake-model mode).
