import { useEffect, useRef, useState } from "react";
import Panoptes from "./scene/Panoptes";
import Header from "./components/Header";
import Oracles from "./components/Oracles";
import Senses from './components/Senses';
import Tribute from "./components/Tribute";
import Chronicle from "./components/Chronicle";
import Prophecy from "./components/Prophecy";
import Archive from "./components/Archive";
import SightWindows from "./components/Sight";
import Tape from "./components/Tape";
import ModeNote from "./components/ModeNote";
import ApprovalCard from "./components/ApprovalCard";
import Sanctum from "./components/Sanctum";
import { syncSettings } from "./lib/settings";
import { detectMode } from "./lib/mode";
import { desktop } from "./lib/desktop";
import { useVoiceOut } from "./lib/useVoiceOut";
import { accept, dismiss, stop, switchSource, toggleRecording } from "./lib/connection";
import { isTyping, VIDEO_MODE } from './lib/keyboard';
import { useArgus } from "./lib/store";
import { watchOrbZone } from "./lib/layout";

function OfflineNotice() {
  const conn = useArgus((s) => s.conn);
  const source = useArgus((s) => s.source);
  if (source !== "live" || conn !== "offline") return null;
  return (
    <div className="panel offline">
      <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
      <div className="voice">Argus sleeps. Wake the core to watch live.</div>
      <code>python -m core.server</code>
      <button className="invoke" onClick={() => switchSource("replay")}>WATCH A SIMULATED SESSION</button>
    </div>
  );
}

export default function App() {
  const zone = useRef<HTMLDivElement>(null);
  // In a plain browser the hub talks; on the desktop the orb does.
  useVoiceOut(!desktop);
  const [sanctum, setSanctum] = useState(false);
  // The theme lives in the core's settings: pick it up whenever we (re)connect.
  useEffect(() => useArgus.subscribe((s, prev) => {
    if (s.conn === "live" && prev.conn !== "live") void syncSettings();
  }), []);
  useEffect(() => {
    // No core to reach (public page, or no key yet): play a session instead.
    void detectMode().then((mode) => switchSource(mode === "live" ? "live" : "replay"));
  }, []);
  useEffect(() => (zone.current ? watchOrbZone(zone.current) : undefined), []);
  useEffect(() => {
    document.documentElement.classList.toggle('video-mode', VIDEO_MODE);
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === ",") {
        event.preventDefault(); setSanctum((o) => !o); return;
      }
      if (event.repeat || event.isComposing || event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) return;
      if (event.shiftKey && event.key.toLowerCase() === 'r') {
        event.preventDefault(); toggleRecording(); return;
      }
      const state = useArgus.getState();
      if (event.key === '/' && !event.shiftKey) {
        event.preventDefault(); document.getElementById('argus-composer')?.focus();
      } else if (state.prophecy && !state.busy && (event.key === 'Escape' || (event.key === 'Enter' && !(event.target instanceof HTMLButtonElement)))) {
        event.preventDefault();
        if (event.key === 'Enter') accept(state.prophecy); else dismiss(state.prophecy);
      } else if (state.busy && event.key === 'Escape') {
        event.preventDefault();
        stop();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      <Panoptes />
      <div className="shell">
        <Header onSettings={() => setSanctum(true)} />
        <Tape />
        <aside className="col">
          <Oracles />
          <Senses />
          <Tribute />
        </aside>
        <main className="center">
          <div className="orb-zone" ref={zone}>
            <SightWindows />
            <ModeNote />
            <OfflineNotice />
            <Prophecy />
            <ApprovalCard />
          </div>
          <Chronicle />
        </main>
        <aside className="col">
          <Archive />
        </aside>
      </div>
      <Sanctum open={sanctum} onClose={() => setSanctum(false)} />
    </>
  );
}
