/* Argus's voice in the UI: fetches speech from the core (/speak, synthesized
 * on this machine) and plays it, one line at a time. Anything new -- you
 * pressing stop, sending a message, or starting to talk -- hushes it. */
import { API } from "./connection";
import { desktop } from "./desktop";

type Listener = (on: boolean) => void;

const KEY = "argus.voiceOut";
let enabled = true;
try {
  enabled = localStorage.getItem(KEY) !== "0";
} catch {
  /* no storage: default on */
}
const listeners = new Set<Listener>();

let audio: HTMLAudioElement | null = null;
let url: string | null = null;
let queue: string[] = [];
let generation = 0; // bumps on hush, so a line still being synthesized is dropped

function release() {
  if (audio) {
    audio.pause();
    audio.src = "";
    audio = null;
  }
  if (url) {
    URL.revokeObjectURL(url);
    url = null;
  }
}

async function next() {
  if (audio || !queue.length) return;
  const text = queue.shift()!;
  const gen = generation;
  try {
    const r = await fetch(API + "/speak", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok || gen !== generation) return void next();
    url = URL.createObjectURL(await r.blob());
    audio = new Audio(url);
    audio.onended = audio.onerror = () => {
      release();
      void next();
    };
    await audio.play();
  } catch {
    release();
    void next();
  }
}

export const speaker = {
  get enabled() {
    return enabled;
  },
  /** Speak a line after whatever is already being said. */
  say(text: string) {
    if (!enabled || !text.trim()) return;
    queue.push(text);
    void next();
  },
  /** Say this now, cutting off anything else. */
  sayNow(text: string) {
    this.hush(false);
    this.say(text);
  },
  /** Silence, right now. `everywhere` also hushes the other Argus window. */
  hush(everywhere = true) {
    generation++;
    queue = [];
    release();
    if (everywhere) desktop?.hush?.();
  },
  setEnabled(on: boolean, fromShell = false) {
    enabled = on;
    try {
      localStorage.setItem(KEY, on ? "1" : "0");
    } catch {
      /* fine */
    }
    if (!on) this.hush(false);
    if (!fromShell) desktop?.setVoiceOut?.(on);
    listeners.forEach((l) => l(on));
  },
  subscribe(l: Listener) {
    listeners.add(l);
    return () => void listeners.delete(l);
  },
};

// The desktop shell keeps one voice setting for both windows, and can hush us.
if (desktop?.onVoiceOut) {
  void desktop.getVoiceOut?.().then((on) => speaker.setEnabled(on, true));
  desktop.onVoiceOut((on) => speaker.setEnabled(on, true));
}
desktop?.onHush?.(() => speaker.hush(false));
