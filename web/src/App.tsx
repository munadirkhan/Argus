import { useEffect, useRef } from "react";
import Panoptes from "./scene/Panoptes";
import Header from "./components/Header";
import Oracles from "./components/Oracles";
import Tribute from "./components/Tribute";
import Chronicle from "./components/Chronicle";
import Prophecy from "./components/Prophecy";
import Archive from "./components/Archive";
import SightWindows from "./components/Sight";
import Tape from "./components/Tape";
import { switchSource } from "./lib/connection";
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

  return (
    <>
      <Panoptes />
      <div className="shell">
        <Header />
        <Tape />
        <aside className="col">
          <Oracles />
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
