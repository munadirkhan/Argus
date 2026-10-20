/* Argus's voice in the UI: fetches speech from the core (/speak, synthesized
 * on this machine) and plays it in order. A reply is split into sentences and
 * every sentence is requested at once, so the first one plays while the rest
 * are still being made. Anything new -- you pressing stop, sending a message,
 * or starting to talk -- hushes it. */
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
let queue: Promise<Blob | null>[] = [];
let playing = false;
let generation = 0; // bumps on hush: anything still in flight is dropped

/** Sentences, merged up to a sensible length so short ones don't stutter. */
export function chunks(text: string, max = 220): string[] {
  const parts = text.replace(/\s+/g, " ").trim().match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) ?? [];
  const out: string[] = [];
  for (const p of parts.map((s) => s.trim()).filter(Boolean)) {
    const last = out[out.length - 1];
    if (last && (last.length < 40 || last.length + p.length < 90) && last.length + p.length <= max) {
      out[out.length - 1] = `${last} ${p}`;
    } else out.push(p);
  }
  return out;
}

function synth(text: string, gen: number): Promise<Blob | null> {
  return fetch(API + "/speak", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  })
    .then((r) => (r.ok && gen === generation ? r.blob() : null))
    .catch(() => null);
}

function release() {
  if (audio) {
    audio.onended = audio.onerror = null;
    audio.pause();
    audio.src = "";
    audio = null;
  }
  if (url) {
    URL.revokeObjectURL(url);
    url = null;
  }
}

async function pump() {
  if (playing) return;
  playing = true;
  const gen = generation;
  while (queue.length && gen === generation) {
    const blob = await queue.shift()!;
    if (!blob || gen !== generation) continue;
    url = URL.createObjectURL(blob);
    audio = new Audio(url);
    const a = audio;
    await new Promise<void>((done) => {
      a.onended = a.onerror = () => done();
      a.play().catch(() => done());
    });
    release();
  }
  playing = false;
  if (queue.length) void pump(); // a hush mid-play left newer lines waiting
}

export const speaker = {
  get enabled() {
    return enabled;
  },
  /** Speak a line after whatever is already being said. */
  say(text: string) {
    if (!enabled || !text.trim()) return;
    const gen = generation;
    for (const c of chunks(text)) queue.push(synth(c, gen));
    void pump();
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
    playing = false;
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
