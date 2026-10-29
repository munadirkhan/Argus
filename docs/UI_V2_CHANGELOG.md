# Argus UI v2 — change record and personal test checklist

Date: October 29, 2026

Working branch: `feat/ui-v2`

Starting point: `origin/submission` at `b74d46d`

## What changed

This update gives the existing app a quieter visual hierarchy while retaining
the hundred-eyed sphere, Greek branding, and all six colour themes.

| Area | Changes |
| --- | --- |
| Shared design | Consistent rounded panels and controls, lighter borders and shadows, less ornament, clearer keyboard focus. Windows uses Segoe UI for controls and body copy; branding retains Cinzel and code retains JetBrains Mono. No new font downloads or dependencies. |
| Hub | Narrower side columns, more room for conversation, less height reserved for the scene, independently scrollable telemetry on short windows. Tablet layouts put the archive below; phone layouts stack the sections. |
| Header | More compact controls, readable status, and a separate labelled row for replay scenarios. The desktop header still reserves exactly 146px for native controls and retains drag/no-drag regions. |
| Models, senses, spending | Quieter nested cards, aligned statistics, a subtle active-model marker, compact sensor indicators, and simpler spending bars. |
| Ticker | Smaller type, reduced contrast, and less visual weight. Live/replay labels and motion still work. |
| Conversation | User message surfaces, readable sans-serif answers, more spacing, clearer plans, quieter tool rows, and consistent artifact links and errors. |
| Composer | Unified input surface, larger attachment/microphone targets, rounded menus and chips, readable placeholders, and theme-aware STOP styling. Attachment, file-reference, dictation, and sending behaviour is unchanged. |
| Archive | Clear selected rows, ellipsis for long filenames, cleaner document tabs and empty states, readable documents and code, scrollable wide tables. |
| Activity windows | Consistent title bars and surfaces for charts, browsers, terminals, and editors; theme-aware syntax/success/error accents; preserved terminal wrapping and scrolling. |
| Observation and approval cards | Opaque surfaces, clearer text and action hierarchy, less glow, readable detail blocks and countdowns. ALLOW/DENY and DONE/CANCEL remain distinct. |
| Mode notices | Compact, wrapping replay/offline/key notices and consistent action buttons. |
| Sanctum | Restyled navigation, fields, toggles, sliders, buttons, feedback, theme tiles, memory rows, skill editors, routine forms, and hotkey rows across all 11 sections. |
| Floating orb cards | Matching typography and controls, less glow, room reserved for actions, constrained approval detail, and a readable scrolling answer panel. Orb dimensions remain 168×168; cards remain 340×146; answers remain 480×440. |
| 3D scene | Lower bloom and halo intensity, quieter particles, subtler rings and highlights. The original prominent floor grid is retained behind the orb and panels. Eye count, gaze, animation timing, mood transitions, and drag/click behaviour are unchanged. Orb body and pupils now follow the active palette too. |
| Themes | Removed fixed presentation colours from UI surfaces, shadows, code accents, STOP controls, and eye glyphs. Existing palette variables drive all six themes; palette definitions are unchanged. |
| Motion | CSS decoration and transitions respect the system reduced-motion preference. The existing 3D animation remains active. |

## Files changed

### Follow-up: restore the floor grid

Restored the original grid line thickness, brighter theme-accent major lines,
24-unit fade distance, and original fade strength after Darsh requested the
previous grid appearance. The rest of the UI v2 styling stays in place. Earlier
screenshots below show the initial, quieter grid; the grid-restored screenshots
show this follow-up.

Verified with TypeScript checking, a production build, and isolated browser
screenshots at 1920×1080 and 1280×720, with no page errors or horizontal overflow.

### Implementation files

- `web/src/styles.css` — shared presentation and responsive layouts.
- `web/src/components/Header.tsx` — replay scenarios moved to their own row; existing handlers retained.
- `web/src/components/Ornament.tsx` — eye glyph colours use palette variables.
- `web/src/scene/Panoptes.tsx` — visual intensity and palette-derived materials.
- `docs/UI_V2_CHANGELOG.md` — this record and checklist.
- `web/evidence/ui-v2/` — screenshots from isolated review fixtures and browser regression checks.

Backend code, event contracts, `web/src/lib/`, settings persistence, native window
management, extension code, scripts, dependencies, and test sources are unchanged.
The private screen-sharing feature, new demo scenes, and deployment are outside
this update.

## How to open it locally

From PowerShell in the repository:

```powershell
git branch --show-current
cd web
npm run dev
```

Open the localhost URL Vite prints. Use **SIMULATE** for a model-free preview.
Open **SANCTUM** or press **Ctrl+,** to preview themes. Settings beyond Appearance
require a running core. For the full desktop experience, build the web app and
launch the desktop app using the repository's normal setup:

```powershell
cd C:\Users\Darsh\Argus\web
npm run build
cd ..\desktop
npm start
```

## Personal test checklist

Check boxes below are intentionally empty so you can record your own testing.
Live requests use your configured core and budget; SIMULATE does not run models.

### Hub, layout, and themes

- [ ] Confirm the branch is `feat/ui-v2`.
- [ ] View the hub at 1920×1080 and 1280×720; all controls fit and the composer stays reachable.
- [ ] Resize the window to a tablet/phone width; sections stack and the page scrolls without horizontal overflow.
- [ ] Switch through Panoptes, Arc Reactor, Hades, Olympus, Nyx, and Gorgon.
- [ ] In each theme, check panel backgrounds, text, active buttons, the orb, terminals, errors, and STOP.
- [ ] In SIMULATE, select each existing scene; the selected scene and recorded/simulated labels remain clear.
- [ ] Select Code (recorded), watch its observation, task progression, written artifact, and successful terminal exit.
- [ ] Open a document in the archive; check tabs, long names, links, code blocks, tables, and scrolling.

### Conversation and controls

- [ ] In LIVE, send a message; check user and Argus text, plan steps, and expandable tool output.
- [ ] Press `/` to focus the composer. Typing in it must not activate global shortcuts.
- [ ] Attach a file, reference one with `@`, and remove an attachment chip.
- [ ] Try drag-and-drop and pasting a screenshot; verify chips and any error messages remain readable.
- [ ] Start and finish dictation; check the recording indicator, microphone feedback, transcription, and cancel.
- [ ] While a task runs, verify STOP is visible and clicking it or pressing Esc stops the task.
- [ ] Accept a watcher offer with Enter and dismiss a different one with Esc.
- [ ] Trigger an approval; read details and countdown, then check ALLOW/DENY or DONE/CANCEL as applicable.
- [ ] Toggle VOICE and RECORD; Shift+R should save a session recording when stopped.

### All Sanctum sections

- [ ] **Appearance:** six previews, selection, and immediate theme repaint.
- [ ] **Voice:** voice selection, speed, preview, mute, and reset controls.
- [ ] **Persona:** address, manner, and reply length.
- [ ] **Minds:** model selectors, reasoning selectors, and model details.
- [ ] **Tribute:** spending display, budget slider, and warning state.
- [ ] **Watcher:** enabled state, intervals, cooldown, and watched folder display.
- [ ] **Reach:** access/orb/startup toggles and explanatory notes in the desktop app.
- [ ] **Memory:** add/edit/remove rows, save state, long text, and feedback.
- [ ] **Skills:** open an existing skill, edit it, and inspect the new-skill form.
- [ ] **Routines:** time, day buttons, prompt, enabled state, and action buttons.
- [ ] **Keys:** hotkey labels, descriptions, and current setup summary.
- [ ] Close with Esc and the close button; reopen at a smaller window size and check scrolling.

### Desktop and floating orb

- [ ] Drag the hub by its header; minimize/close controls and header buttons remain clickable.
- [ ] Hide the hub, then click the orb to reopen it; drag the orb to reposition it.
- [ ] Check the orb alone has a transparent background with no rectangular page backdrop.
- [ ] Check listening, transcribing, heard, working, reply, and prophecy cards.
- [ ] Check approval and handoff cards; long details must leave actions visible.
- [ ] Trigger screen inspection; check the looking state, STOP, and failure feedback if applicable.
- [ ] Read a long screen answer, scroll it, copy it, open the hub, and close the answer.
- [ ] Move the orb near different screen edges; standard and large cards must stay usable on either side and when growing upward.
- [ ] With no key configured in a separate test setup, verify ADD KEY / GO LIVE and the no-key feedback fit.

## Verification performed by Codex

- **Passed:** `cd web; npx tsc -b`.
- **Passed:** `cd web; npm run build`. Vite still reports its existing bundle-size warning (the main JavaScript chunk exceeds 500 kB).
- **Passed:** the existing browser regression checks at 1920×1080 and 1280×720, with a supplementary mock for `/settings` and speech muted in the isolated browser. This covers terminal node stability, burst scrolling, sensor pulses, shortcuts that protect typing, raw recording/download, recorded Code replay through a successful exit, montage identities, and video mode. Test source is unchanged.
- **Browser fixture limitation:** invoking `python web/tests/test_ui.py` directly reports connection errors for newer settings/speech calls that its older fixture does not mock. The supplementary local fixture supplies settings and disables speech; it changes no application code or test source. This is not a claim that the direct command passes as-is.
- **Passed:** isolated visual review of all six themes and all 11 settings sections, confirm/handoff approval cards, STOP, replay, and widths 1920, 1280, 1000, 760, and 390 pixels. No page errors or horizontal overflow in those checks.
- **Passed:** isolated orb review of working, approval, prophecy, reply, listening, transcribing, heard, screen inspection, failure, and long-answer states. Verified 340×146 and 480×440 geometry, visible actions, OPEN, direct orb click, transparent background, and answer scrolling.
- **Fixed during review:** shared observation-card styling initially overrode the native orb card width; desktop cards now explicitly retain their fixed dimensions. Approval titles retain two complete lines while detail text yields space to the action row.
- **Passed:** `git diff --check`; protected application-logic and test-source paths have no changes.
- **Native desktop:** every assertion passed except local microphone transcription, which returned an empty string. Passing checks include startup/core ownership, attachment upload and sending, microphone recording state, native header clearance, hiding/restoring the hub, orb transparency/size/side, OPEN, screen capture, the 480×440 answer panel, closing it, and core shutdown.
- **Confirmed pre-existing failure:** the same unchanged desktop suite against the original `b74d46d` submission UI also returned an empty microphone transcript and passed its other assertions. Therefore `npm test` remains nonzero on this machine; this visual update does not fix the transcription issue.
- **Passed:** standalone `cd desktop; node tests/test_nokey.mjs`, including ADD KEY / GO LIVE, disabled LIVE, simulated mode, missing-key feedback, and the inactive orb.
- **Passed after final header polish:** live and replay controls at desktop widths 1920 and 1280 stay within the header's 146px native-control clearance. The final no-key Electron check also passed again.

Fixtures use generic workspace content and inert desktop callbacks. They test
rendering and controls without model calls, and do not change your personal settings.
Actual microphone transcription, real model responses, multi-monitor placement,
and personal workflow checks should also be tested on your normal setup.

### Screenshots

- [Restored grid, 1920×1080](../web/evidence/ui-v2/grid-restored-1920.png)
- [Restored grid, 1280×720](../web/evidence/ui-v2/grid-restored-1280.png)
- [Hub, 1920×1080](../web/evidence/ui-v2/hub-1920.png)
- [Laptop replay, 1280×720](../web/evidence/ui-v2/hub-1280.png)
- [All six themes](../web/evidence/ui-v2/themes.png)
- [Appearance settings](../web/evidence/ui-v2/settings-appearance.png)
- [All 11 settings sections](../web/evidence/ui-v2/settings-sections.png)
- [Settings at phone width](../web/evidence/ui-v2/settings-mobile.png)
- [Native desktop with no key](../web/evidence/ui-v2/hub-no-key.png)
- [Desktop header at laptop width](../web/evidence/ui-v2/desktop-header-1280.png)
- [Approval card](../web/evidence/ui-v2/approval-confirm.png)
- [Nine standard orb states](../web/evidence/ui-v2/orb-states.png)
- [Large scrolling answer](../web/evidence/ui-v2/orb-answer.png)
- [Recorded Code regression, 1920×1080](../web/evidence/ui-v2/code-recorded-1920.png)
- [Recorded Code regression, 1280×720](../web/evidence/ui-v2/code-recorded-1280.png)

## Git handoff

The delivery branch is `feat/ui-v2`. Munadir handles integration into
`submission`. This update includes no merge into `main` or `submission` and no
deployment.
