import { moodOf, useArgus } from "../lib/store";
import { startReplay, switchSource, toggleRecording } from "../lib/connection";
import { basename } from "../lib/format";
import { SCENARIOS } from "../sim/scenarios";
import { EyeGlyph } from "./Ornament";
import { useMode } from "../lib/mode";
import { useEffect, useState } from "react";
import { speaker } from "../lib/speaker";
import type { Mood } from "../lib/types";

const WORD: Record<Mood, string> = {
  idle: "WATCHING",
  observe: "OBSERVING",
  deliberate: "DELIBERATING",
  act: "ACTING",
  gaze: "SPEAKING",
};

export default function Header({ onSettings }: { onSettings?: () => void }) {
  const mood = useArgus((s) => moodOf(s));
  const conn = useArgus((s) => s.conn);
  const source = useArgus((s) => s.source);
  const session = useArgus((s) => s.session);
  const scenario = useArgus((s) => s.scenario);
  const sc = scenario ? SCENARIOS[scenario] : null;
  const sim = source === "replay";
  const recording = useArgus(s => s.recording);
  const mode = useMode((m) => m.mode);
  const [voiceOn, setVoiceOn] = useState(speaker.enabled);
  useEffect(() => speaker.subscribe(setVoiceOn), []);

  const connLabel =
    conn === "live" ? "Live" : conn === "connecting" ? "Connecting" : conn === "offline" ? "Offline" : "";

  return (
    <header className="header">
      <div className="brand">
        <EyeGlyph size={34} lit={mood !== "idle"} />
        <div>
          <div className="name">ARGUS</div>
          <div className="sub">PANOPTES · THE HUNDRED-EYED</div>
        </div>
      </div>

      <div className="state">
        <div className="word">{WORD[mood]}</div>
        <div className="where">
          {session ? `${session.runtime === "local" ? "local" : "sandbox"} · ~/${basename(session.cwd)}` : "—"}
        </div>
      </div>

      <div className="controls">
        <div className="seg" role="group" aria-label="Event source">
          <button aria-pressed={!sim} onClick={() => switchSource("live")} disabled={mode !== "live"}
            title={mode === "hosted" ? "Live runs on your desktop — see GitHub" : mode === "needs-key" ? "Add your Nebius key to go live" : undefined}>LIVE</button>
          <button aria-pressed={sim} onClick={() => switchSource("replay")}>SIMULATE</button>
        </div>
        {onSettings && (
          <button className="sanctum-btn" onClick={onSettings} title="Settings: theme, voice, models, memory... (Ctrl+,)">
            <span className="glyph">☼</span>SANCTUM
          </button>
        )}
        {!sim && (
          <button className={`voice-toggle ${voiceOn ? "on" : ""}`} aria-pressed={voiceOn}
            onClick={() => speaker.setEnabled(!voiceOn)}
            title={voiceOn ? "Argus speaks its replies -- click to mute" : "Argus is muted -- click to let it speak"}>
            <span className="dot" />{voiceOn ? "VOICE" : "MUTED"}
          </button>
        )}
        {!sim && <button className={`record-toggle ${recording ? 'recording' : ''}`}
          onClick={toggleRecording} disabled={!recording && conn !== 'live'} aria-pressed={recording}
          title="Shift+R · download raw session events on stop">
          <span className="dot" />{recording ? 'STOP REC' : 'RECORD'} <kbd>⇧R</kbd>
        </button>}
        {sim ? (
          <span className={`pill ${sc?.kind === "recorded" ? "rec" : "simpill"}`} title={sc?.blurb}>
            <span className="dot live" />
            {sc?.kind === "recorded" ? "RECORDED LIVE RUN" : "SIMULATED SESSION"}
          </span>
        ) : (
          <span className="pill">
            <span className={`dot ${conn === "live" ? "live" : conn === "offline" ? "warn" : ""}`} />
            {connLabel}
            {session?.label ? ` · ${session.label}` : ""}
          </span>
        )}
      </div>
      {sim && (
        <div className="scenario-bar">
          <span className="scenario-label">SESSIONS</span>
          <div className="seg scen" role="group" aria-label="Scenario">
            {Object.values(SCENARIOS).map((s) => (
              <button key={s.id} aria-pressed={scenario === s.id} title={s.blurb} onClick={() => startReplay(s.id)}>
                {s.name.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      )}
    </header>
  );
}
