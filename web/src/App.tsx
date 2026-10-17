import { useEffect, useRef } from "react";
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
import { accept, dismiss, switchSource, toggleRecording } from "./lib/connection";
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
  useEffect(() => {
    switchSource("live");
  }, []);
  useEffect(() => (zone.current ? watchOrbZone(zone.current) : undefined), []);
  useEffect(() => {
    document.documentElement.classList.toggle('video-mode', VIDEO_MODE);
    const onKey = (event: KeyboardEvent) => {
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
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      <Panoptes />
      <div className="shell">
        <Header />
        <Tape />
        <aside className="col">
          <Oracles />
          <Senses />
          <Tribute />
        </aside>
        <main className="center">
          <div className="orb-zone" ref={zone}>
            <SightWindows />
            <OfflineNotice />
            <Prophecy />
          </div>
          <Chronicle />
        </main>
        <aside className="col">
          <Archive />
        </aside>
      </div>
    </>
  );
}
