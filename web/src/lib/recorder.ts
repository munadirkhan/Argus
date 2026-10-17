import type { ArgusEvent } from './types';

const MAX_BYTES = 10_000_000;
let recording: string[] | null = null;
let bytes = 0;
let baseline = new Map<string, string>();
let identities = new Set<string>();
let report: (active: boolean) => void = () => {};

export function recorderStatus(callback: typeof report) { report = callback; }
export function recordingActive() { return recording !== null; }
export function clearRecordingBaseline() { baseline = new Map(); }

/** Keep the original wire JSON and timestamps, including unfamiliar event fields. */
export function recordFrame(raw: string, event: ArgusEvent) {
  if (event.type === 'session.state' || event.type === 'fs.tree') baseline.set(event.type, raw);
  if (!recording || typeof event.ts !== 'number') return;
  const identity = `${event.seq}:${event.ts}`;
  if (event.seq !== undefined && identities.has(identity)) return;
  if (event.seq !== undefined) identities.add(identity);
  recording.push(raw);
  bytes += new TextEncoder().encode(raw).length;
  if (bytes >= MAX_BYTES) stopRecording();
}

export function startRecording() {
  if (recording) return;
  recording = [...baseline.values()].sort((a, b) => JSON.parse(a).ts - JSON.parse(b).ts);
  identities = new Set(recording.map(raw => { const e = JSON.parse(raw); return `${e.seq}:${e.ts}`; }));
  bytes = recording.reduce((total, raw) => total + new TextEncoder().encode(raw).length, 0);
  report(true);
}

export function stopRecording(): string | null {
  if (!recording) return null;
  const text = recording.join('\n') + (recording.length ? '\n' : '');
  recording = null;
  identities.clear();
  report(false);
  const url = URL.createObjectURL(new Blob([text], {type: 'application/x-ndjson'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'argus-session.jsonl';
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  return text;
}
