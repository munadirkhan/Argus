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
  orbExpand: (expanded) => ipcRenderer.invoke("orb:expand", Boolean(expanded)),
  onVoiceToggle: (cb) => listen("voice:toggle", () => cb()),
  onOrbSide: (cb) => listen("orb:side", (side) => cb(side === "right" ? "right" : "left")),
  onOrbVisible: (cb) => listen("orb:visible", (v) => cb(Boolean(v))),
  getHotkeys: () => ipcRenderer.invoke("app:hotkeys"),
});
