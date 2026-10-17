/* Dictation for the composer, on the browser's own Web Speech API.
 *
 * No dependency, no key, no token cost. Push-to-talk: it only listens between
 * an explicit start and stop, never in the background -- an always-on agent
 * should not also be an always-on microphone.
 *
 * Note for the README: in Chrome this API streams audio to Google's speech
 * service. It is the browser's behaviour, not ours, but it is worth saying
 * out loud for a tool that otherwise keeps everything local.
 */

type Listener = (state: SpeechState) => void;

export interface SpeechState {
  listening: boolean;
  /** Text confirmed so far this session. */
  final: string;
  /** Words still being revised by the recogniser. */
  interim: string;
  error: string | null;
}

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
}

function ctor(): (new () => RecognitionLike) | null {
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const speechSupported = () => ctor() !== null;

const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone blocked — allow it in the address bar",
  "service-not-allowed": "Microphone blocked — allow it in the address bar",
  "audio-capture": "No microphone found",
  network: "Speech service unreachable",
  aborted: "",
  "no-speech": "",
};

class Dictation {
  private rec: RecognitionLike | null = null;
  private listeners = new Set<Listener>();
  private state: SpeechState = { listening: false, final: "", interim: "", error: null };
  /** Text already in the box when dictation started, so we never clobber it. */
  private base = "";

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    fn(this.state);
    return () => this.listeners.delete(fn);
  }

  private set(patch: Partial<SpeechState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn(this.state));
  }

  /** Full text to show in the box right now. */
  text() {
    const spoken = (this.state.final + this.state.interim).trim();
    if (!spoken) return this.base;
    return this.base ? `${this.base.replace(/\s+$/, "")} ${spoken}` : spoken;
  }

  start(existing = "") {
    const Ctor = ctor();
    if (!Ctor) {
      this.set({ error: "This browser has no speech recognition" });
      return;
    }
    if (this.state.listening) return;
    this.base = existing;

    const rec = new Ctor();
    rec.lang = navigator.language || "en-US";
    rec.continuous = true;       // keep going through natural pauses
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (e: any) => {
      let final = this.state.final;
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const chunk = e.results[i][0]?.transcript ?? "";
        if (e.results[i].isFinal) final += (final && !final.endsWith(" ") ? " " : "") + chunk.trim();
        else interim += chunk;
      }
      this.set({ final, interim });
    };
    rec.onerror = (e: any) => {
      const msg = ERRORS[e?.error] ?? `Microphone error: ${e?.error ?? "unknown"}`;
      this.set({ error: msg || null, listening: msg ? false : this.state.listening });
    };
    rec.onend = () => this.set({ listening: false, interim: "" });

    this.rec = rec;
    this.set({ listening: true, final: "", interim: "", error: null });
    try {
      rec.start();
    } catch {
      this.set({ listening: false, error: "Could not start the microphone" });
    }
  }

  stop() {
    this.set({ listening: false });
    try {
      this.rec?.stop();
    } catch {
      /* already stopped */
    }
  }

  /** Stop and discard whatever was being dictated. */
  cancel() {
    this.base = "";
    this.set({ listening: false, final: "", interim: "", error: null });
    try {
      this.rec?.abort();
    } catch {
      /* already stopped */
    }
  }

  clearError() {
    this.set({ error: null });
  }
}

export const dictation = new Dictation();
