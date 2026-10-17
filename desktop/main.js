/* Argus on the desktop.
 *
 *  hub   the full interface, in a window with native controls over our header
 *  orb   a tiny, transparent, always-on-top window with the hundred-eyed orb.
 *        It appears whenever the hub isn't in front -- over the browser, the
 *        file explorer, a video, a borderless game -- and clicking it brings
 *        the hub back. When Argus has something to say, a card slides out
 *        beside it.
 *  tray  Argus keeps watching after you close the hub; quit from the tray.
 *  keys  Ctrl+Alt+A  show / hide the hub      (from any app)
 *        Ctrl+Alt+Space  talk to Argus         (press, speak, press again)
 *  core  starts the Python core if it isn't already running, stops it on quit.
 */
const {
  app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, screen,
  nativeImage, dialog, session, shell,
} = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const ASSETS = path.join(__dirname, "assets");
const DIST = path.join(REPO, "web", "dist", "index.html");
const CORE = (process.env.ARGUS_CORE_URL || "http://127.0.0.1:7600").replace(/\/$/, "");
const DEV = process.argv.includes("--dev");
const TEST = process.argv.includes("--test");
const START_HIDDEN = process.argv.includes("--hidden");
const UI_URL = process.env.ARGUS_UI_URL || (DEV ? "http://localhost:5173" : null);

const ORB = 168;          // the orb's square
const CARD = 340;         // the card that slides out beside it
const MARGIN = 24;

if (TEST) {
  app.setPath("userData", fs.mkdtempSync(path.join(os.tmpdir(), "argus-desktop-test-")));
  // Tests speak to Argus through a WAV file standing in for the microphone.
  if (process.env.ARGUS_FAKE_MIC) {
    app.commandLine.appendSwitch("use-fake-device-for-media-stream");
    app.commandLine.appendSwitch("use-file-for-fake-audio-capture", process.env.ARGUS_FAKE_MIC);
  }
}
if (!TEST && !app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

let hub = null;
let orb = null;
let tray = null;
let core = null;          // child process, only if we started it
let coreRoot = "";
let quitting = false;
let orbExpanded = false;
let orbSide = "left";
let orbAnchor = null;     // top-left of the orb's square, in screen DIPs
let drag = null;
let orbTimer = null;

/* ------------------------------------------------------------------ config */
const CONFIG_PATH = () => path.join(app.getPath("userData"), "argus.json");
let config = { workspace: "", orb: null, orbEnabled: true };

function loadConfig() {
  try {
    config = { ...config, ...JSON.parse(fs.readFileSync(CONFIG_PATH(), "utf8")) };
  } catch { /* first run */ }
}

function saveConfig() {
  try {
    fs.writeFileSync(CONFIG_PATH(), JSON.stringify(config, null, 2));
  } catch (e) {
    console.error("[argus] could not save config:", e.message);
  }
}

function workspace() {
  const ws = process.env.ARGUS_WATCH_ROOT || config.workspace || path.join(app.getPath("home"), "Argus");
  fs.mkdirSync(ws, { recursive: true });
  return ws;
}

/* -------------------------------------------------------------------- core */
function health() {
  return new Promise((resolve) => {
    const req = http.get(CORE + "/health", { timeout: 1500 }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try { resolve(JSON.parse(body)); } catch { resolve(null); }
      });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => { req.destroy(); resolve(null); });
  });
}

function python() {
  const venv = process.platform === "win32"
    ? path.join(REPO, ".venv", "Scripts", "python.exe")
    : path.join(REPO, ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : process.platform === "win32" ? "python" : "python3";
}

async function ensureCore() {
  const running = await health();
  if (running && running.ready) {
    coreRoot = running.root || "";
    return true;                 // someone already runs a core; use it, don't own it
  }
  const root = workspace();
  const log = fs.openSync(path.join(app.getPath("userData"), "core.log"), "a");
  core = spawn(python(), ["-m", "core.server"], {
    cwd: REPO,
    env: { ...process.env, ARGUS_WATCH_ROOT: root, PYTHONIOENCODING: "utf-8" },
    stdio: ["ignore", log, log],
    windowsHide: true,
  });
  core.on("exit", (code) => {
    core = null;
    if (!quitting) {
      console.error("[argus] core exited with", code);
      refreshTray();
    }
  });
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const h = await health();
    if (h && h.ready) {
      coreRoot = h.root || root;
      return true;
    }
    if (!core) break;
  }
  return false;
}

function stopCore() {
  if (core) {
    try { core.kill(); } catch { /* already gone */ }
    core = null;
  }
}

/* --------------------------------------------------------------- windows */
const prefs = (extra = {}) => ({
  preload: path.join(__dirname, "preload.js"),
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  ...extra,
});

function load(win, hash) {
  if (UI_URL) return win.loadURL(UI_URL + (hash ? "#" + hash : ""));
  if (!fs.existsSync(DIST)) {
    return win.loadURL("data:text/html," + encodeURIComponent(
      "<body style='background:#050407;color:#efe4cc;font:15px monospace;padding:40px'>" +
      "The interface isn't built yet. Run <b>npm run build:web</b> in argus/desktop, then start again.</body>"));
  }
  return win.loadFile(DIST, hash ? { hash } : undefined);
}

function guard(win) {
  // Links open in the real browser; the window itself never navigates away.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    const ours = url.startsWith("file:") || (UI_URL && url.startsWith(UI_URL));
    if (!ours) {
      e.preventDefault();
      if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    }
  });
}

function createHub() {
  const overlay = process.platform === "darwin"
    ? { titleBarStyle: "hiddenInset" }
    : { titleBarStyle: "hidden", titleBarOverlay: { color: "#050407", symbolColor: "#d6a04c", height: 34 } };
  hub = new BrowserWindow({
    width: 1600, height: 940, minWidth: 1200, minHeight: 700,
    show: false, backgroundColor: "#050407", title: "Argus",
    icon: path.join(ASSETS, process.platform === "win32" ? "icon.ico" : "icon.png"),
    ...overlay,
    webPreferences: prefs(),
  });
  guard(hub);
  load(hub);
  hub.once("ready-to-show", () => {
    if (!START_HIDDEN) hub.show();
    else scheduleOrb();
  });
  hub.on("focus", hideOrb);
  hub.on("blur", scheduleOrb);
  hub.on("minimize", scheduleOrb);
  hub.on("hide", scheduleOrb);
  hub.on("close", (e) => {
    if (!quitting) {
      e.preventDefault();      // Argus keeps watching from the tray and the orb
      hub.hide();
    }
  });
}

function defaultAnchor() {
  const wa = screen.getPrimaryDisplay().workArea;
  return { x: wa.x + wa.width - ORB - MARGIN, y: wa.y + wa.height - ORB - MARGIN };
}

function clampAnchor(a) {
  const wa = screen.getDisplayNearestPoint({ x: a.x + ORB / 2, y: a.y + ORB / 2 }).workArea;
  return {
    x: Math.round(Math.min(Math.max(a.x, wa.x), wa.x + wa.width - ORB)),
    y: Math.round(Math.min(Math.max(a.y, wa.y), wa.y + wa.height - ORB)),
  };
}

function applyOrbBounds() {
  if (!orb || orb.isDestroyed()) return;
  const wa = screen.getDisplayNearestPoint({ x: orbAnchor.x + ORB / 2, y: orbAnchor.y + ORB / 2 }).workArea;
  // The card opens toward the middle of the screen, so it never runs off the edge.
  const side = orbAnchor.x + ORB / 2 > wa.x + wa.width / 2 ? "left" : "right";
  const bounds = orbExpanded
    ? { x: side === "left" ? orbAnchor.x - CARD : orbAnchor.x, y: orbAnchor.y, width: ORB + CARD, height: ORB }
    : { x: orbAnchor.x, y: orbAnchor.y, width: ORB, height: ORB };
  orb.setBounds(bounds);
  if (side !== orbSide) {
    orbSide = side;
    orb.webContents.send("orb:side", side);
  }
}

function createOrb() {
  orbAnchor = clampAnchor(config.orb || defaultAnchor());
  orb = new BrowserWindow({
    x: orbAnchor.x, y: orbAnchor.y, width: ORB, height: ORB,
    frame: false, transparent: true, backgroundColor: "#00000000", hasShadow: false, thickFrame: false,
    resizable: false, minimizable: false, maximizable: false, fullscreenable: false,
    skipTaskbar: true, alwaysOnTop: true, show: false, title: "Argus — orb",
    webPreferences: prefs({ backgroundThrottling: false }),
  });
  orb.setAlwaysOnTop(true, "screen-saver");
  orb.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  guard(orb);
  load(orb, "orb");
  orb.webContents.on("did-finish-load", () => orb.webContents.send("orb:side", orbSide));
  applyOrbBounds();
}

function scheduleOrb() {
  clearTimeout(orbTimer);
  // A beat of delay: focus moving from the hub to the orb itself shouldn't flicker.
  orbTimer = setTimeout(() => {
    if (quitting || !config.orbEnabled || !orb || orb.isDestroyed()) return;
    // "In front" means visible, not minimized and focused. Windows can report a
    // just-minimized window as still focused, so check all three.
    if (hub && !hub.isDestroyed() && hub.isVisible() && !hub.isMinimized() && hub.isFocused()) return;
    if (!orb.isVisible()) {
      applyOrbBounds();
      orb.showInactive();     // never steal focus from the game or video you're in
      orb.webContents.send("orb:visible", true);
    }
  }, 150);
}

function hideOrb() {
  clearTimeout(orbTimer);
  if (orb && !orb.isDestroyed() && orb.isVisible()) {
    orb.hide();
    orb.webContents.send("orb:visible", false);
  }
}

function openHub() {
  if (!hub || hub.isDestroyed()) createHub();
  if (hub.isMinimized()) hub.restore();
  // Windows refuses to hand focus to a background app; briefly topmost gets around it.
  hub.setAlwaysOnTop(true);
  hub.show();
  hub.focus();
  hub.setAlwaysOnTop(false);
  hideOrb();
}

function toggleHub() {
  if (hub && !hub.isDestroyed() && hub.isVisible() && hub.isFocused()) hub.hide();
  else openHub();
}

function talk() {
  // The hub takes the voice when it's in front; otherwise the orb does.
  let target = hub && !hub.isDestroyed() && hub.isFocused() ? hub : null;
  if (!target && orb && !orb.isDestroyed() && orb.isVisible()) target = orb;
  if (!target) {
    openHub();
    target = hub;
  }
  target.webContents.send("voice:toggle");
}

/* ----------------------------------------------------------------- tray */
function refreshTray() {
  if (!tray) return;
  const root = coreRoot || workspace();
  tray.setToolTip(core || coreRoot ? `Argus — watching ${path.basename(root)}` : "Argus — core offline");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Argus", accelerator: "CommandOrControl+Alt+A", click: openHub },
    { label: "Talk to Argus", accelerator: "CommandOrControl+Alt+Space", click: talk },
    { type: "separator" },
    { label: `Watching: ${root}`, enabled: false },
    { label: "Choose watched folder…", click: chooseFolder },
    {
      label: "Floating orb", type: "checkbox", checked: config.orbEnabled,
      click: (item) => {
        config.orbEnabled = item.checked;
        saveConfig();
        if (item.checked) scheduleOrb(); else hideOrb();
      },
    },
    {
      label: process.platform === "darwin" ? "Open at login" : "Start with Windows",
      type: "checkbox", checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => {
        app.setLoginItemSettings({
          openAtLogin: item.checked,
          // In development, Electron needs the app folder; --hidden starts in the tray.
          args: app.isPackaged ? ["--hidden"] : [path.resolve(__dirname), "--hidden"],
        });
      },
    },
    { type: "separator" },
    { label: "Quit Argus", click: () => { quitting = true; app.quit(); } },
  ]));
}

async function chooseFolder() {
  const res = await dialog.showOpenDialog({
    title: "Which folder should Argus watch?",
    properties: ["openDirectory", "createDirectory"],
    defaultPath: coreRoot || workspace(),
  });
  if (res.canceled || !res.filePaths[0]) return;
  config.workspace = res.filePaths[0];
  saveConfig();
  if (core) {
    stopCore();
    await new Promise((r) => setTimeout(r, 800));
    await ensureCore();
    for (const w of [hub, orb]) if (w && !w.isDestroyed()) w.webContents.reload();
  } else {
    await dialog.showMessageBox({
      type: "info",
      message: "Saved. Argus is connected to a core you started yourself, so it will watch the new folder the next time the core starts from here.",
    });
  }
  refreshTray();
}

function createTray() {
  const img = nativeImage.createFromPath(path.join(ASSETS, "tray.png"));
  tray = new Tray(img);
  tray.on("click", openHub);
  refreshTray();
}

/* ------------------------------------------------------------------- ipc */
ipcMain.on("hub:open", openHub);

ipcMain.handle("orb:expand", (_e, expanded) => {
  orbExpanded = Boolean(expanded);
  applyOrbBounds();
  return orbSide;
});

ipcMain.on("orb:drag", (_e, phase) => {
  if (phase === "start") {
    // Follow the real cursor from here, so the drag keeps up even when the
    // pointer outruns this tiny window.
    clearInterval(drag?.timer);
    const start = screen.getCursorScreenPoint();
    drag = { start, anchor: { ...orbAnchor }, moved: false };
    drag.timer = setInterval(() => {
      const c = screen.getCursorScreenPoint();
      const dx = c.x - drag.start.x;
      const dy = c.y - drag.start.y;
      if (!drag.moved && Math.hypot(dx, dy) < 4) return;
      drag.moved = true;
      orbAnchor = { x: drag.anchor.x + dx, y: drag.anchor.y + dy };
      applyOrbBounds();
    }, 16);
  } else if (drag) {
    clearInterval(drag.timer);
    if (drag.moved) {
      orbAnchor = clampAnchor(orbAnchor);
      applyOrbBounds();
      config.orb = orbAnchor;
      saveConfig();
    }
    drag = null;
  }
});

/* -------------------------------------------------------------- lifecycle */
app.on("second-instance", openHub);

app.whenReady().then(async () => {
  if (process.platform === "win32") app.setAppUserModelId("dev.argus.desktop");
  loadConfig();

  // The microphone, for push-to-talk -- and nothing else.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb, details) => {
    if (permission === "media") return cb((details.mediaTypes || ["audio"]).every((t) => t === "audio"));
    cb(permission === "clipboard-sanitized-write");
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) =>
    permission === "media" || permission === "clipboard-sanitized-write");

  const coreOk = await ensureCore();
  createHub();
  createOrb();
  createTray();

  const keys = { "CommandOrControl+Alt+A": toggleHub, "CommandOrControl+Alt+Space": talk };
  for (const [accel, fn] of Object.entries(keys)) {
    if (!globalShortcut.register(accel, fn)) console.warn("[argus] shortcut taken by another app:", accel);
  }

  if (!coreOk && !TEST) {
    dialog.showMessageBox({
      type: "warning",
      message: "Argus couldn't start its core.",
      detail: `Check ${path.join(app.getPath("userData"), "core.log")}. The interface will connect as soon as the core is running (python -m core.server).`,
    });
  }

  screen.on("display-metrics-changed", () => {
    orbAnchor = clampAnchor(orbAnchor);
    applyOrbBounds();
  });

  if (TEST) {
    global.__argus = {
      hub: () => hub, orb: () => orb,
      state: () => ({ orbAnchor, orbExpanded, orbSide, coreRoot, ownsCore: Boolean(core) }),
      openHub, toggleHub,
    };
  }
});

app.on("before-quit", () => {
  quitting = true;
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  stopCore();
});

// Closing every window doesn't quit: Argus lives in the tray until you say so.
app.on("window-all-closed", () => {});
