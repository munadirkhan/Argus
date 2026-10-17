/* Voice input: record in the window, transcribe on this machine.
 *
 * Replaces the browser's Web Speech API, which streams audio to Google and
 * doesn't work inside Electron at all. Here the audio goes to the ARGUS core
 * on localhost, where faster-whisper turns it into text; nothing leaves the
 * machine. Push-to-talk only -- the mic is never open in the background.
 */
import { API } from "./connection";

export type VoicePhase = "idle" | "recording" | "transcribing";

export interface VoiceState {
  phase: VoicePhase;
  /** 0..1 loudness, for the meter. */
  level: number;
  /** Seconds recorded so far. */
  seconds: number;
  error: string | null;
}

type Listener = (s: VoiceState) => void;

const MAX_SECONDS = 90;

function pickMime(): string {
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return options.find((m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)) ?? "";
}

function explain(err: unknown): string {
  const name = (err as { name?: string })?.name ?? "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Microphone blocked — allow it for Argus";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No microphone found";
  if (name === "NotReadableError") return "The microphone is in use by another app";
  return "Couldn't start the microphone";
}

class Voice {
  private state: VoiceState = { phase: "idle", level: 0, seconds: 0, error: null };
  private listeners = new Set<Listener>();
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private audio: AudioContext | null = null;
  private raf = 0;
  private started = 0;
  private stopTimer = 0;
  private finished: ((text: string) => void) | null = null;

  supported() {
    return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    fn(this.state);
    return () => {
      this.listeners.delete(fn);
    };
  }

  get phase() {
    return this.state.phase;
  }

  private set(patch: Partial<VoiceState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn(this.state));
  }

  clearError() {
    this.set({ error: null });
  }

  /** Start recording. Resolves once the mic is live (or failed). */
  async start(): Promise<boolean> {
    if (this.state.phase !== "idle") return false;
    if (!this.supported()) {
      this.set({ error: "This window can't record audio" });
      return false;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      this.set({ error: explain(e) });
      return false;
    }
    const mime = pickMime();
    this.recorder = new MediaRecorder(this.stream, mime ? { mimeType: mime } : undefined);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.recorder.onstop = () => void this.transcribe();
    this.recorder.start(250);
    this.started = performance.now();
    this.set({ phase: "recording", level: 0, seconds: 0, error: null });
    this.meter();
    this.stopTimer = window.setTimeout(() => this.stop(), MAX_SECONDS * 1000);
    return true;
  }

  /** Stop recording; resolves with the transcribed text ("" if nothing usable). */
  stop(): Promise<string> {
    return new Promise((resolve) => {
      if (this.state.phase !== "recording" || !this.recorder) {
        resolve("");
        return;
      }
      this.finished = resolve;
      window.clearTimeout(this.stopTimer);
      this.recorder.stop();
    });
  }

  /** Throw the recording away. */
  cancel() {
    window.clearTimeout(this.stopTimer);
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.onstop = null;
      this.recorder.stop();
    }
    this.teardown();
    this.set({ phase: "idle", level: 0, seconds: 0 });
    this.finished?.("");
    this.finished = null;
  }

  private meter() {
    if (!this.stream) return;
    try {
      this.audio = new AudioContext();
      const src = this.audio.createMediaStreamSource(this.stream);
      const an = this.audio.createAnalyser();
      an.fftSize = 512;
      src.connect(an);
      const buf = new Uint8Array(an.fftSize);
      let last = 0;
      const tick = (now: number) => {
        if (this.state.phase !== "recording") return;
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.min(1, Math.sqrt(sum / buf.length) * 3.2);
        if (now - last > 50) {
          last = now;
          this.set({ level: this.state.level * 0.5 + rms * 0.5, seconds: (now - this.started) / 1000 });
        }
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    } catch {
      /* the meter is decoration; recording still works without it */
    }
  }

  private teardown() {
    cancelAnimationFrame(this.raf);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.recorder = null;
    void this.audio?.close().catch(() => undefined);
    this.audio = null;
  }

  private async transcribe() {
    const type = this.recorder?.mimeType || "audio/webm";
    const blob = new Blob(this.chunks, { type });
    this.teardown();
    const done = this.finished;
    this.finished = null;
    if (blob.size < 1200) {
      this.set({ phase: "idle", level: 0, seconds: 0 });
      done?.("");
      return;
    }
    this.set({ phase: "transcribing", level: 0 });
    try {
      const r = await fetch(API + "/transcribe", { method: "POST", body: blob, headers: { "content-type": type } });
      const j = await r.json();
      this.set({ phase: "idle", seconds: 0, error: j.ok ? null : j.error || "Transcription failed" });
      done?.(j.ok ? String(j.text || "").trim() : "");
    } catch {
      this.set({ phase: "idle", seconds: 0, error: "Can't reach the Argus core to transcribe" });
      done?.("");
    }
  }
}

export const voice = new Voice();
