# UI redesign brief (for Darsh's Astra)

**Goal:** make Argus look like a funded startup, not a hackathon project:
cooler, more aura, nonchalant, mature, professional. **Visuals only.** All
features already exist and work; don't build or change features.

## 1. Branch

```bash
git fetch origin
git checkout -b feat/ui-v2 origin/submission
```

- Work on **`feat/ui-v2`** (branched from `submission`) and push it there.
- **Do not push to `main` or `submission`.** Munadir merges.
- `submission` is the full current app. Old `main` / `feat/web` are 10 commits
  behind and are missing most of the screens below; don't restyle those.

## 2. Every screen there is to restyle

| Screen | File(s) |
|---|---|
| Hub layout, header (LIVE/SIMULATE, SANCTUM, VOICE, RECORD buttons) | `web/src/App.tsx`, `components/Header.tsx` |
| Left column: model tiers, senses, spend | `components/Oracles.tsx`, `Senses.tsx`, `Tribute.tsx` |
| Ticker tape | `components/Tape.tsx` |
| Chat + message box (attach, mic, INVOKE / red STOP while working) | `components/Chronicle.tsx`, `Composer.tsx` |
| Right column: files Argus wrote | `components/Archive.tsx` |
| Floating windows over the orb (chart, browser, terminal, editor) | `components/Sight.tsx` |
| "Argus has noticed" card | `components/Prophecy.tsx` |
| **ALLOW / DENY and DONE / CANCEL approval card** | `components/ApprovalCard.tsx` |
| Replay / "add your key" banner | `components/ModeNote.tsx` |
| **The Sanctum** (settings overlay, 11 sections) | `components/Sanctum.tsx` |
| **The floating orb** (desktop): orb + cards beside it | `components/OrbApp.tsx` |
| The 3D hundred-eyed sphere | `scene/Panoptes.tsx` (visual tweaks fine) |
| Eye glyphs, ornaments | `components/Ornament.tsx` |
| All styles | `web/src/styles.css` |

The orb card states are: listening, transcribing, heard, prophecy, working
(with STOP), reply, approval, looking-at-screen, and the big answer panel.
To see them without the desktop app, run the hub (`cd web && npm run dev`)
and use SIMULATE, or open the Sanctum with **Ctrl+,**.

## 3. Hard rules: things that break the app or the tests

**Don't edit** (logic, not looks):
- `web/src/lib/**` (connection, store, settings, speaker, voice, themes data, desktop bridge)
- `core/**`, `desktop/main.js`, `desktop/preload.js`, `extension/**`, `scripts/**`
- any `tests/` folder

**Colours: use the CSS variables, never hard-coded colours.** There are six
switchable colour themes (Sanctum -> Appearance). They work by swapping these
values at runtime. A hard-coded colour won't follow the theme.
- `--void` (background), `--bone` (text), `--ash` (quiet text), `--gold`, `--gold-dim`,
  `--amber` (glow), `--ember` (alarms), `--line`, `--line-strong`, `--amber-soft`, `--gold-faint`
- for transparency: `rgba(var(--gold-rgb), .3)`, likewise `--amber-rgb`, `--ember-rgb`,
  `--bone-rgb`, `--void-rgb`, `--panel-rgb`
- You may add new variables, but add them to all six palettes in
  `web/src/lib/themes.ts` (that one data edit is fine).

**Don't rename or remove these class names / IDs** (restyle them freely):
`#argus-composer` `.composer` `.composer-btn` `.mic` `.listening` `.invoke` `.att-chip`
`.sent-att` `.msg-user` `.header` `.state` `.word` `.seg` `.pill` `.simpill` `.rec`
`.record-toggle` `.oracles` `.senses` `.sense` `.tape` `.sight` `.browser` `.btitle`
`.terminal-output` `.mode-note` `.mn-btn` (incl. `.mn-btn.go`) `.prophecy` `.btn-accept`
`.btn-dismiss` `.orb-box` `.orb-card` (and its kind classes: `.reply` `.answer`
`.approval` `.prophecy`) `.oc-actions` `.oc-x` `.oc-stop` `.oc-go` `.oc-answer`
`.sanctum` `.sanctum-btn` `.sx-*` `.voice-toggle` `.video-mode` `.lit` `.ok` `.err`

**Don't change these visible strings** (tests read them): `WATCHING` (header state word),
`TERMINAL`, `LIVE`, `OPEN` (orb card button), `Add your Nebius key`, `No key found yet`,
`STOP`.

**Desktop constraints:**
- The hub header must keep `padding-right: 146px` in desktop mode (`html.desktop .header`):
  that's where the Windows minimize/close buttons sit. Keep `-webkit-app-region: drag`
  on the header and `no-drag` on its buttons.
- The orb window is **168×168**, transparent. With a card it becomes 168 + **340×146**;
  the screen-answer panel is 168 + **480×440**. Designs must fit those exact sizes.
- Nothing in the orb may block clicks on the orb itself (click = open hub, drag = move).

## 4. Check before you push

```bash
cd web && npx tsc -b && npm run build        # must pass
```

Then Munadir runs the full suite (`desktop/ npm test`, `python web/tests/test_ui.py`).
Screenshots of each screen in the PR description help him review fast.
