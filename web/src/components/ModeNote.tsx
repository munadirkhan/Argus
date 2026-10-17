import { useState } from "react";
import { desktop } from "../lib/desktop";
import { goLive, REPO_URL, useMode } from "../lib/mode";
import { VIDEO_MODE } from "../lib/keyboard";

/* A quiet line over the orb when this hub can't go live: on the public page
 * (a replay of real runs) or in the desktop app before a key is added. */
export default function ModeNote() {
  const mode = useMode((m) => m.mode);
  const [status, setStatus] = useState<"" | "waking" | "no-key" | "failed">("");
  if (mode === "live" || VIDEO_MODE) return null;

  if (mode === "hosted") {
    return (
      <div className="mode-note" role="note">
        <span className="mn-tag">REPLAY</span>
        <span className="mn-text">Real Argus sessions, replayed. Argus itself runs on your desktop — watching your files, terminal and browser.</span>
        <a className="mn-btn" href={REPO_URL} target="_blank" rel="noreferrer">GET IT ↗</a>
      </div>
    );
  }

  const wake = async () => {
    setStatus("waking");
    const r = await goLive();
    // On success the desktop reloads this window, live.
    if (!r.ok) setStatus(r.needsKey ? "no-key" : "failed");
  };

  return (
    <div className="mode-note" role="note">
      <span className="mn-tag">SIMULATED</span>
      <span className="mn-text">
        {status === "waking" ? "Waking the core…"
          : status === "no-key" ? "No key found yet — paste it after NEBIUS_API_KEY= and save."
          : status === "failed" ? "The core didn't start. See core.log in the app's data folder."
          : "Add your Nebius key to go live."}
      </span>
      <button className="mn-btn" onClick={() => void desktop?.openKeyFile()}>ADD KEY</button>
      <button className="mn-btn go" onClick={() => void wake()} disabled={status === "waking"}>GO LIVE</button>
    </div>
  );
}
