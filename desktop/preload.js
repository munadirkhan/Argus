// The only bridge between the web UI and the desktop shell. Context-isolated
// and sandboxed: the page gets these few functions and nothing else.
const { contextBridge, ipcRenderer } = require("electron");

function listen(channel, cb) {
  const handler = (_event, value) => cb(value);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

contextBridge.exposeInMainWorld("argusDesktop", {
  platform: process.platform,
  openHub: () => ipcRenderer.send("hub:open"),
  orbDrag: (phase) => ipcRenderer.send("orb:drag", phase === "end" ? "end" : "start"),
  orbExpand: (expanded, big) => ipcRenderer.invoke("orb:expand", Boolean(expanded), Boolean(big)),
  onOrbGrow: (cb) => listen("orb:grow", (d) => cb(d === "up" ? "up" : "down")),
  onVoiceToggle: (cb) => listen("voice:toggle", () => cb()),
  onOrbSide: (cb) => listen("orb:side", (side) => cb(side === "right" ? "right" : "left")),
  onOrbVisible: (cb) => listen("orb:visible", (v) => cb(Boolean(v))),
  getHotkeys: () => ipcRenderer.invoke("app:hotkeys"),
  getSetup: () => ipcRenderer.invoke("app:setup"),
  openKeyFile: () => ipcRenderer.invoke("app:open-key-file"),
  goLive: () => ipcRenderer.invoke("app:go-live"),
  getVoiceOut: () => ipcRenderer.invoke("voice:get-out"),
  setVoiceOut: (on) => ipcRenderer.send("voice:set-out", Boolean(on)),
  onVoiceOut: (cb) => listen("voice:out", (on) => cb(Boolean(on))),
  hush: () => ipcRenderer.send("voice:hush"),
  onHush: (cb) => listen("voice:hush", () => cb()),
  getShell: () => ipcRenderer.invoke("shell:get"),
  setShell: (key, value) => ipcRenderer.invoke("shell:set", String(key), value),
  chooseFolder: () => ipcRenderer.invoke("shell:choose-folder"),
  notifySettings: () => ipcRenderer.send("settings:changed"),
  onSettings: (cb) => listen("settings:changed", () => cb()),
  onSnap: (cb) => {
    const a = listen("snap:started", () => cb({ phase: "started" }));
    const b = listen("snap:failed", (why) => cb({ phase: "failed", error: String(why || "") }));
    return () => { a(); b(); };
  },
});
