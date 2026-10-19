import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import Panoptes from "../scene/Panoptes";
import { accept, approve, dismiss, speak, switchSource } from "../lib/connection";
import { desktop, hotkeys, keyLabel, type OrbSide } from "../lib/desktop";
import { detectMode, useMode } from "../lib/mode";
import { moodOf, useArgus } from "../lib/store";
import { voice, type VoiceState } from "../lib/voice";

/* The floating orb: Argus while you are anywhere else -- a browser, a game,
 * a video. Always on top, tiny, draggable; click it to open the hub. When it
 * has something to say, a card slides out beside it, so you can answer
 * without leaving what you're doing. */

const REPLY_SECONDS = 14;
const DRAG_THRESHOLD = 4;

type Card =
  | { kind: "approval"; id: string; handoff: boolean; title: string; detail: string }
  | { kind: "listening" }
  | { kind: "transcribing" }
  | { kind: "heard"; text: string }
  | { kind: "prophecy"; id: string; observation: string; suggestion: string }
  | { kind: "working"; note: string; step: string }
  | { kind: "reply"; text: string }
  | null;

function plain(md: string) {
  return md.replace(/[*_`#>]/g, "").replace(/\[(\d+)\]/g, "").replace(/\s+/g, " ").trim();
}

export default function OrbApp() {
  const [side, setSide] = useState<OrbSide>("left");
  const [mic, setMic] = useState<VoiceState>({ phase: "idle", level: 0, seconds: 0, error: null });
  const [reply, setReply] = useState<{ id: string; text: string; until: number } | null>(null);
  const [heard, setHeard] = useState<{ text: string; until: number } | null>(null);
  const [, tick] = useState(0);
  const [talkKey, setTalkKey] = useState<string | null>(null);
  useEffect(() => { void hotkeys().then((h) => setTalkKey(keyLabel(h.talk))); }, []);

  const mood = useArgus((s) => moodOf(s));
  const conn = useArgus((s) => s.conn);
  const busy = useArgus((s) => s.busy);
  const prophecyId = useArgus((s) => s.prophecy);
  const approval = useArgus((s) => s.approval);
  const obs = useArgus((s) => (s.prophecy ? s.observations[s.prophecy] : null));
  const note = useArgus((s) => (s.activeTier ? s.tiers[s.activeTier].note : ""));
  const step = useArgus((s) => {
    const plans = Object.values(s.plans);
    const run = plans.flatMap((p) => p.steps).filter((st) => st.status === "running").pop();
    return run?.title ?? "";
  });
  // Select a stable value (the entry object itself), never a fresh {..} --
  // a new object on every read makes React re-render forever and drop the tree.
  const lastReply = useArgus((s) => {
    for (let i = s.entries.length - 1; i >= 0; i--) {
      const e = s.entries[i];
      if (e.kind === "message" && e.role === "assistant") return e;
    }
    return null;
  });

  useEffect(() => {
    document.documentElement.classList.add("orb-mode");
    // Before a key is added there is no core to wait for; stay dim until GO LIVE reloads us.
    void detectMode().then((mode) => mode === "live" && switchSource("live"));
    const unsub = voice.subscribe(setMic);
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => {
      unsub();
      window.clearInterval(t);
    };
  }, []);

  // A fresh reply surfaces beside the orb for a few seconds. On connect the
  // core replays its whole history in a burst; anything in that burst is old
  // news, so replies only count once the connection has settled.
  const liveSince = useRef(0);
  useEffect(() => {
    liveSince.current = conn === "live" ? Date.now() : 0;
  }, [conn]);
  // Whether this window is actually on screen. The desktop shell says so
  // explicitly: Electron reports a hidden window's document as "visible".
  const shown = useRef(!desktop);
  useEffect(() => {
    if (!desktop) return;
    return desktop.onOrbVisible((v) => {
      shown.current = v;
      if (!v) setReply(null);
    });
  }, []);
  useEffect(() => {
    if (!lastReply || lastReply.kind !== "message") return;
    if (!liveSince.current || Date.now() - liveSince.current < 1500) return;
    // Only news if you were away: a reply that landed while the hub was in
    // front has already been read there.
    if (!shown.current) return;
    setReply({ id: lastReply.id, text: plain(lastReply.text), until: Date.now() + REPLY_SECONDS * 1000 });
  }, [lastReply?.id]);

  // Push-to-talk from anywhere: the talk hotkey starts, again sends.
  useEffect(() => {
    if (!desktop) return;
    return desktop.onVoiceToggle(async () => {
      const st = useArgus.getState();
      if (st.conn !== "live" || st.busy) return;
      if (voice.phase === "recording") {
        const text = await voice.stop();
        if (text) {
          setHeard({ text, until: Date.now() + 4000 });
          speak(text);
        }
      } else if (voice.phase === "idle") {
        voice.clearError();
        await voice.start();
      }
    });
  }, []);

  useEffect(() => (desktop ? desktop.onOrbSide(setSide) : undefined), []);

  const now = Date.now();
  const card: Card = useMemo(() => {
    // Argus waiting on you beats everything: nothing moves until you answer.
    if (approval)
      return { kind: "approval", id: approval.id, handoff: approval.kind === "handoff",
               title: approval.title, detail: approval.detail };
    if (mic.phase === "recording") return { kind: "listening" };
    if (mic.phase === "transcribing") return { kind: "transcribing" };
    if (heard && heard.until > now) return { kind: "heard", text: heard.text };
    if (prophecyId && obs && obs.state === "pending")
      return { kind: "prophecy", id: prophecyId, observation: obs.observation, suggestion: obs.suggestion };
    if (busy) return { kind: "working", note, step };
    if (reply && reply.until > now) return { kind: "reply", text: reply.text };
    return null;
  }, [approval, mic.phase, heard, prophecyId, obs, busy, note, step, reply, now]);

  const expanded = card !== null;
  useEffect(() => {
    void desktop?.orbExpand(expanded).then(setSide);
  }, [expanded]);

  // Click opens the hub; press-and-move drags the orb (the main process follows
  // the cursor, which keeps working when it leaves this tiny window).
  const down = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    down.current = { x: e.screenX, y: e.screenY, moved: false };
    desktop?.orbDrag("start");
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = down.current;
    if (d && !d.moved && Math.hypot(e.screenX - d.x, e.screenY - d.y) > DRAG_THRESHOLD) d.moved = true;
  };
  const onPointerUp = () => {
    const d = down.current;
    down.current = null;
    desktop?.orbDrag("end");
    if (d && !d.moved) desktop?.openHub();
  };

  const offline = conn !== "live";
  const needsKey = useMode((m) => m.mode) === "needs-key";
  const lit = mood !== "idle" || mic.phase === "recording" || card?.kind === "prophecy" || card?.kind === "approval";

  return (
    <div className={`orb-app side-${side} ${expanded ? "expanded" : ""}`}>
      <div
        className={`orb-box mood-${mood} ${lit ? "lit" : ""} ${offline ? "offline" : ""}`}
        style={{ "--level": mic.level } as React.CSSProperties}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        title={needsKey ? "Add your Nebius key to go live — click to open" : offline ? "Argus core is offline — click to open" : "Open Argus · drag to move"}
      >
        <div className="orb-aura" />
        <Panoptes compact />
        {mic.phase === "recording" && <div className="orb-ring" />}
        {(card?.kind === "prophecy" || card?.kind === "approval") && <div className="orb-badge" />}
      </div>

      <AnimatePresence>
        {card && (
          <motion.div
            key={card.kind}
            className={`orb-card ${card.kind}`}
            initial={{ opacity: 0, x: side === "left" ? 16 : -16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.2, 0.7, 0.2, 1] }}
          >
            {card.kind === "listening" && (
              <>
                <div className="oc-label">LISTENING · {mic.seconds.toFixed(0)}s</div>
                <div className="oc-meter">
                  {Array.from({ length: 18 }, (_, i) => (
                    <span key={i} style={{ height: `${12 + Math.abs(Math.sin(i * 1.7 + mic.seconds * 6)) * mic.level * 88}%` }} />
                  ))}
                </div>
                <div className="oc-hint">{talkKey ? `${talkKey} to send` : "Click the orb to finish"} <button onClick={() => voice.cancel()}>cancel</button></div>
              </>
            )}
            {card.kind === "approval" && (
              <>
                <div className="oc-label">{card.handoff ? "YOUR TURN" : "ARGUS ASKS"}</div>
                <div className="oc-text">{card.title}</div>
                {card.detail && <div className="oc-detail">{card.detail}</div>}
                <div className="oc-actions">
                  <button className="oc-go" onClick={() => approve(card.id, true)}>{card.handoff ? "DONE" : "ALLOW"}</button>
                  <button onClick={() => approve(card.id, false)}>{card.handoff ? "CANCEL" : "DENY"}</button>
                  <button onClick={() => desktop?.openHub()}>OPEN</button>
                </div>
              </>
            )}
            {card.kind === "transcribing" && <div className="oc-label">TRANSCRIBING ON THIS MACHINE…</div>}
            {card.kind === "heard" && (
              <>
                <div className="oc-label">YOU SAID</div>
                <div className="oc-text">“{card.text}”</div>
              </>
            )}
            {card.kind === "prophecy" && (
              <>
                <div className="oc-label">ARGUS HAS NOTICED</div>
                <div className="oc-text">{card.suggestion}</div>
                <div className="oc-actions">
                  <button className="oc-go" onClick={() => accept(card.id)}>PROCEED</button>
                  <button onClick={() => desktop?.openHub()}>OPEN</button>
                  <button className="oc-x" onClick={() => dismiss(card.id)} aria-label="Not now">×</button>
                </div>
              </>
            )}
            {card.kind === "working" && (
              <>
                <div className="oc-label">AT WORK</div>
                <div className="oc-text dim">{card.step || card.note || "…"}</div>
              </>
            )}
            {card.kind === "reply" && (
              <>
                <div className="oc-label">ARGUS</div>
                <div className="oc-text">{card.text}</div>
                <div className="oc-actions">
                  <button onClick={() => desktop?.openHub()}>OPEN</button>
                  <button className="oc-x" onClick={() => setReply(null)} aria-label="Close">×</button>
                </div>
              </>
            )}
            {mic.error && <div className="oc-error">{mic.error}</div>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
