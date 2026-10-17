import { useArgus } from "./store";
import type { ArgusEvent, SentAttachment } from "./types";
import { SCENARIOS } from "../sim/scenarios";
import { clearRecordingBaseline, recordFrame, recorderStatus, recordingActive, startRecording, stopRecording } from './recorder';

recorderStatus(active => useArgus.getState().setRecording(active));

export function toggleRecording() {
  const state = useArgus.getState();
  if (recordingActive()) stopRecording();
  else if (state.source === 'live' && state.conn === 'live') startRecording();
}

export const API = (import.meta.env.VITE_ARGUS_API as string | undefined) ?? "http://localhost:7600";
const WS_URL = API.replace(/^http/, "ws") + "/ws";

let ws: WebSocket | null = null;
let retry: number | null = null;
let timers: number[] = [];
let wanted: "live" | "replay" = "live";

function clearReplay() {
  timers.forEach((t) => window.clearTimeout(t));
  timers = [];
}

async function fetchHealth(socket: WebSocket) {
  try {
    const r = await fetch(API + "/health");
    const h = await r.json();
    if (ws !== socket || wanted !== 'live') return;
    const st = useArgus.getState();
    if (typeof h.budget_usd === "number") st.setBudget(h.budget_usd);
    if (h.models) st.setModels(h.models);
    if (Array.isArray(h.sensors)) st.setSensors(h.sensors.filter((s: unknown) => typeof s === 'string'));
  } catch {
    /* health is a nicety */
  }
}

function connectLive() {
  const st = useArgus.getState();
  st.reset(); // Reconnect replays the core's history; rebuild without duplicate rows.
  st.setConn("connecting");
  try {
    ws = new WebSocket(WS_URL);
  } catch {
    st.setConn("offline");
    scheduleRetry();
    return;
  }
  const socket = ws;
  ws.onopen = () => {
    if (ws !== socket || wanted !== 'live') return;
    useArgus.getState().setConn("live");
    fetchHealth(socket);
  };
  ws.onmessage = (m) => {
    if (ws !== socket || wanted !== 'live') return;
    try {
      const event = JSON.parse(m.data) as ArgusEvent;
      recordFrame(m.data, event);
      useArgus.getState().ingest(event);
    } catch {
      /* ignore malformed frames */
    }
  };
  ws.onclose = () => {
    if (ws !== socket) return;
    ws = null;
    if (wanted === "live") {
      useArgus.getState().setConn("offline");
      scheduleRetry();
    }
  };
}

function scheduleRetry() {
  if (retry || wanted !== "live") return;
  retry = window.setTimeout(() => {
    retry = null;
    if (wanted === "live") connectLive();
  }, 2000);
}

export function startReplay(id?: string) {
  clearReplay();
  const st = useArgus.getState();
  const sc = SCENARIOS[id ?? st.scenario ?? "montage"] ?? SCENARIOS.montage;
  st.reset();
  st.setConn("replay");
  st.setScenario(sc.id);
  // Spend accumulates across the whole replay, like the live cap does.
  let cumulative = 0;
  sc.events.forEach((e) => {
    timers.push(
      window.setTimeout(() => {
        let ev: ArgusEvent = e;
        if (e.type === "usage") {
          cumulative += e.cost_usd;
          ev = { ...e, cumulative_cost_usd: cumulative };
        }
        useArgus.getState().ingest(ev);
      }, e.t_offset_ms)
    );
  });
}

export function switchSource(source: "live" | "replay") {
  if (source === 'live' && wanted === 'live' && ws) return;
  if (source === 'replay') stopRecording();
  wanted = source;
  useArgus.getState().setSource(source);
  clearReplay();
  if (retry) {
    window.clearTimeout(retry);
    retry = null;
  }
  if (source === "replay") {
    if (ws) {
      ws.onclose = null;
      ws.close();
      ws = null;
    }
    startReplay();
  } else {
    clearRecordingBaseline();
    useArgus.getState().reset();
    if (!ws) connectLive();
  }
}

export function send(msg: Record<string, unknown>) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
    return true;
  }
  return false;
}

function unreachable(what: string) {
  useArgus.getState().ingest({
    type: "error",
    message: `Couldn't reach Argus to ${what}: the core isn't connected. Start it with python -m core.server`,
    fatal: false,
  });
}

export function accept(id: string) {
  if (useArgus.getState().source === "replay") {
    useArgus.getState().resolveObservation(id, "accepted");
    return;
  }
  if (send({ type: "user.accept", id })) useArgus.getState().resolveObservation(id, "accepted");
  else unreachable("accept");
}

export function dismiss(id: string) {
  useArgus.getState().resolveObservation(id, "dismissed");
  // Replay ids (obs_1...) collide with live ones; never let replay touch the server.
  if (useArgus.getState().source === "live") send({ type: "user.dismiss", id });
}

export function speak(text: string, attachments: SentAttachment[] = []) {
  const ok = send({ type: "user.message", text, attachments });
  if (!ok) unreachable("send that");
  return ok;
}

export async function fetchArtifact(path: string): Promise<string | null> {
  if (useArgus.getState().source !== "live") return null;
  try {
    const r = await fetch(API + "/artifact?path=" + encodeURIComponent(path));
    const j = await r.json();
    return j.ok ? (j.text as string) : null;
  } catch {
    return null;
  }
}

// Editing this module (or the store) in dev would leave a second socket alive
// in the old module instance. Reload instead of hot-swapping.
if (import.meta.hot) import.meta.hot.accept(() => window.location.reload());
