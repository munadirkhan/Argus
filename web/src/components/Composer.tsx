import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { draft, release, upload, type Attachment } from "../lib/attach";
import { speak, stop } from "../lib/connection";
import { speaker } from "../lib/speaker";
import { useMode } from "../lib/mode";
import { desktop, hotkeys, keyLabel } from "../lib/desktop";
import { bytes, relative } from "../lib/format";
import { VIDEO_MODE } from "../lib/keyboard";
import { useArgus } from "../lib/store";
import { voice, type VoiceState } from "../lib/voice";
import { EyeGlyph } from "./Ornament";

/* The composer: type, talk, attach.
 *
 *  + menu   attach files from anywhere (copied into the workspace), or
 *           reference a workspace file with @
 *  drop     drag files anywhere onto the hub
 *  paste    Ctrl+V a screenshot or files
 *  mic      push-to-talk, transcribed locally; the talk hotkey works from any app
 */

const MAX_SUGGESTIONS = 8;

interface WsFile {
  path: string;
  rel: string;
  bytes: number;
}

/** Subsequence match, so "wljs" finds "watchlist.js". Null when it can't match. */
function score(rel: string, query: string): number | null {
  if (!query) return 0;
  const hay = rel.toLowerCase();
  const needle = query.toLowerCase();
  const direct = hay.indexOf(needle);
  if (direct >= 0) return direct === 0 ? -200 : -100 + direct;
  let i = 0;
  let last = -1;
  let gaps = 0;
  for (const ch of needle) {
    const at = hay.indexOf(ch, i);
    if (at < 0) return null;
    if (last >= 0) gaps += at - last - 1;
    last = at;
    i = at + 1;
  }
  return gaps;
}

function hasFiles(e: DragEvent | React.DragEvent) {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

export default function Composer() {
  const [text, setText] = useState("");
  const [picker, setPicker] = useState<{ query: string; from: number } | null>(null);
  const [active, setActive] = useState(0);
  const [menu, setMenu] = useState(false);
  const [atts, setAtts] = useState<Attachment[]>([]);
  const [dropping, setDropping] = useState(false);
  const [mic, setMic] = useState<VoiceState>({ phase: "idle", level: 0, seconds: 0, error: null });

  const busy = useArgus((s) => s.busy);
  const conn = useArgus((s) => s.conn);
  const tree = useArgus((s) => s.tree);
  const note = useArgus((s) => (s.activeTier ? s.tiers[s.activeTier].note : ""));

  const input = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const textRef = useRef(text);
  textRef.current = text;
  const attsRef = useRef(atts);
  attsRef.current = atts;

  const live = conn === "live";
  const mode = useMode((m) => m.mode);
  const uploading = atts.some((a) => a.status === "uploading");
  const ready = atts.filter((a) => a.status === "ready");
  const canSend = live && !busy && !uploading && (text.trim().length > 0 || ready.length > 0);
  const micOk = useMemo(() => voice.supported(), []);
  const [talkKey, setTalkKey] = useState<string | null>(null);
  useEffect(() => { void hotkeys().then((h) => setTalkKey(keyLabel(h.talk))); }, []);

  useEffect(() => voice.subscribe(setMic), []);
  useEffect(() => () => attsRef.current.forEach(release), []);

  /* ---------------- attachments ---------------- */
  const addFiles = useCallback(
    (list: FileList | File[]) => {
      if (!live) return;
      const files = Array.from(list).slice(0, 10);
      if (!files.length) return;
      const drafts = files.map(draft);
      setAtts((cur) => [...cur, ...drafts]);
      files.forEach((file, i) => {
        void upload(file, drafts[i]).then((patch) =>
          setAtts((cur) => cur.map((a) => (a.id === drafts[i].id ? { ...a, ...patch } : a)))
        );
      });
      input.current?.focus();
    },
    [live]
  );

  const removeAtt = (id: string) =>
    setAtts((cur) => {
      const gone = cur.find((a) => a.id === id);
      if (gone) release(gone);
      return cur.filter((a) => a.id !== id);
    });

  // Drop files anywhere on the hub.
  useEffect(() => {
    let depth = 0;
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth++;
      setDropping(true);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (!depth) setDropping(false);
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDropping(false);
      if (e.dataTransfer?.files.length) addFiles(e.dataTransfer.files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [addFiles]);

  /* ---------------- sending ---------------- */
  const send = useCallback(
    (raw: string) => {
      const body = raw.trim();
      const sent = attsRef.current.filter((a) => a.status === "ready" && a.path);
      if (!live || busy || attsRef.current.some((a) => a.status === "uploading")) return false;
      if (!body && !sent.length) return false;
      const ok = speak(
        body,
        sent.map((a) => ({ path: a.path!, name: a.name, bytes: a.bytes, kind: a.kind }))
      );
      if (ok) {
        setText("");
        setPicker(null);
        attsRef.current.forEach(release);
        setAtts([]);
      }
      return ok;
    },
    [live, busy]
  );

  const submit = () => {
    if (canSend) send(text);
  };

  /* ---------------- voice ---------------- */
  const appendHeard = (heard: string) => {
    if (!heard) return;
    setText((cur) => (cur.trim() ? `${cur.replace(/\s+$/, "")} ${heard}` : heard));
    requestAnimationFrame(() => {
      const el = input.current;
      el?.focus();
      el?.setSelectionRange(el.value.length, el.value.length);
    });
  };

  const toggleMic = async () => {
    if (!live || busy) return;
    if (mic.phase === "recording") appendHeard(await voice.stop());
    else if (mic.phase === "idle") {
      voice.clearError();
      speaker.hush();
      await voice.start();
    }
  };

  // Global push-to-talk (the talk hotkey) while the hub is in front: speak, and
  // the request goes straight to Argus -- no reaching for the keyboard.
  useEffect(() => {
    if (!desktop) return;
    return desktop.onVoiceToggle(async () => {
      const st = useArgus.getState();
      if (st.conn !== "live" || st.busy) return;
      if (voice.phase === "recording") {
        const heard = await voice.stop();
        const full = [textRef.current.trim(), heard].filter(Boolean).join(" ");
        if (full) send(full);
      } else if (voice.phase === "idle") {
        voice.clearError();
        speaker.hush();
      await voice.start();
      }
    });
  }, [send]);

  /* ---------------- @ workspace references ---------------- */
  const files: WsFile[] = useMemo(
    () =>
      tree.nodes
        .filter((n) => !n.dir)
        .map((n) => ({ path: n.path, rel: relative(n.path, tree.root), bytes: n.bytes })),
    [tree]
  );

  const matches = useMemo(() => {
    if (!picker) return [];
    return files
      .map((f) => ({ f, s: score(f.rel, picker.query) }))
      .filter((m): m is { f: WsFile; s: number } => m.s !== null)
      .sort((a, b) => a.s - b.s || a.f.rel.length - b.f.rel.length)
      .slice(0, MAX_SUGGESTIONS)
      .map((m) => m.f);
  }, [picker, files]);

  useEffect(() => setActive(0), [picker?.query]);

  const choose = (f: WsFile) => {
    if (!picker) return;
    const after = text.slice(picker.from + 1 + picker.query.length);
    setText(`${text.slice(0, picker.from)}@${f.rel} ${after.replace(/^\s+/, "")}`);
    setPicker(null);
    requestAnimationFrame(() => {
      const caret = picker.from + f.rel.length + 2;
      input.current?.focus();
      input.current?.setSelectionRange(caret, caret);
    });
  };

  const onChange = (value: string, caret: number) => {
    setText(value);
    const upto = value.slice(0, caret);
    const at = upto.lastIndexOf("@");
    const token = at >= 0 ? upto.slice(at + 1) : "";
    const startsWord = at === 0 || /\s/.test(upto[at - 1] ?? "");
    setPicker(at >= 0 && startsWord && !/\s/.test(token) ? { query: token, from: at } : null);
  };

  const startReference = () => {
    setMenu(false);
    const el = input.current;
    const caret = el?.selectionStart ?? text.length;
    const pad = caret > 0 && !/\s$/.test(text.slice(0, caret)) ? " " : "";
    setText(text.slice(0, caret) + pad + "@" + text.slice(caret));
    setPicker({ query: "", from: caret + pad.length });
    requestAnimationFrame(() => {
      el?.focus();
      const pos = caret + pad.length + 1;
      el?.setSelectionRange(pos, pos);
    });
  };

  /* ---------------- keys ---------------- */
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (picker && matches.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => (i + (e.key === "ArrowDown" ? 1 : matches.length - 1)) % matches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        choose(matches[active]);
        return;
      }
    }
    if (e.key === "Escape") {
      if (picker) return e.preventDefault(), setPicker(null);
      if (menu) return e.preventDefault(), setMenu(false);
      if (mic.phase === "recording") return e.preventDefault(), voice.cancel();
    }
    if (e.key === "Backspace" && !text && atts.length) removeAtt(atts[atts.length - 1].id);
    if (e.key === "Enter") submit();
  };

  const onPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    if (e.clipboardData.files.length) {
      e.preventDefault();
      addFiles(e.clipboardData.files);
    }
  };

  const recording = mic.phase === "recording";
  const placeholder = VIDEO_MODE
    ? ""
    : !live
      ? mode === "hosted" ? "This is a replay — Argus runs on your desktop"
        : mode === "needs-key" ? "Add your Nebius key to talk to Argus"
        : "Argus is not connected — simulated sessions are read-only"
      : busy
        ? `Argus is at work${note ? ` — ${note.toLowerCase()}` : ""}…`
        : recording
          ? `Listening… ${mic.seconds.toFixed(0)}s — click the mic to finish`
          : mic.phase === "transcribing"
            ? "Transcribing…"
            : "Speak, and Argus will act…   @ for a file · drop or paste to attach";

  return (
    <div className={`composer ${recording ? "listening" : ""}`}>
      <AnimatePresence>
        {dropping && (
          <motion.div className="drop-veil" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="drop-card">
              <EyeGlyph size={48} lit />
              <div className="voice">Hand it to Argus.</div>
              <div className="mono-dim">Dropped files are copied into the workspace for Argus to read.</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {picker && (
          <motion.div className="picker" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }} transition={{ duration: 0.14 }}>
            <div className="picker-head">
              <span className="label">WORKSPACE</span>
              <span className="mono-dim">{matches.length ? "↑↓ choose · ⏎ insert · esc close" : "no file matches"}</span>
            </div>
            {matches.map((f, i) => (
              <button key={f.path} className={`picker-row ${i === active ? "on" : ""}`}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); choose(f); }}>
                <span className="pf">{f.rel}</span>
                <span className="pb">{bytes(f.bytes)}</span>
              </button>
            ))}
          </motion.div>
        )}
        {menu && !picker && (
          <motion.div className="attach-menu" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }} transition={{ duration: 0.14 }}>
            <button onMouseDown={(e) => { e.preventDefault(); setMenu(false); filesInput.current?.click(); }}>
              <span className="mi">⇪</span>
              <span><b>Attach files</b><i>from anywhere on this computer</i></span>
            </button>
            <button onMouseDown={(e) => { e.preventDefault(); startReference(); }}>
              <span className="mi">@</span>
              <span><b>Reference a workspace file</b><i>Argus opens it in place</i></span>
            </button>
            <div className="attach-hint">or drag files onto Argus · Ctrl+V pastes screenshots</div>
          </motion.div>
        )}
      </AnimatePresence>

      {mic.error && (
        <div className="mic-error" role="status">
          {mic.error}
          <button onClick={() => voice.clearError()} aria-label="Dismiss">×</button>
        </div>
      )}

      {atts.length > 0 && (
        <div className="att-row">
          {atts.map((a) => (
            <div key={a.id} className={`att-chip ${a.status} ${a.kind}`} title={a.error || a.path || a.name}>
              {a.preview ? <img src={a.preview} alt="" /> : <i>{a.kind === "pdf" ? "PDF" : "FILE"}</i>}
              <span className="an">{a.name}</span>
              <span className="ab">{a.status === "uploading" ? "…" : a.status === "error" ? a.error : bytes(a.bytes)}</span>
              <button onClick={() => removeAtt(a.id)} aria-label={`Remove ${a.name}`}>×</button>
            </div>
          ))}
        </div>
      )}

      <EyeGlyph size={20} lit={busy || recording} />

      <button className={`composer-btn ${menu ? "open" : ""}`} onClick={() => setMenu((m) => !m)}
        disabled={!live || busy} title="Attach or reference files" aria-label="Attach files" aria-expanded={menu}>
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden>
          <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      <input ref={filesInput} type="file" multiple hidden
        onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />

      <input
        id="argus-composer"
        ref={input}
        aria-label="Speak to Argus"
        autoComplete="off"
        value={text}
        onChange={(e) => onChange(e.target.value, e.target.selectionStart ?? e.target.value.length)}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        onBlur={() => window.setTimeout(() => { setPicker(null); setMenu(false); }, 120)}
        placeholder={placeholder}
        disabled={!live || busy}
      />

      {!picker && !recording && <kbd className="composer-key" title="Focus composer">/</kbd>}

      {micOk && (
        <button
          className={`composer-btn mic ${recording ? "on" : ""} ${mic.phase === "transcribing" ? "working" : ""}`}
          style={{ "--level": mic.level } as React.CSSProperties}
          onClick={toggleMic}
          disabled={!live || busy || mic.phase === "transcribing"}
          title={recording ? "Finish (esc cancels)" : talkKey ? `Talk — or ${talkKey} from any app` : "Talk"}
          aria-label={recording ? "Finish dictation" : "Start dictation"}
          aria-pressed={recording}
        >
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden>
            <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
            <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          {recording && <span className="pulse" aria-hidden />}
        </button>
      )}

      {live && busy ? (
        <button className="invoke stop" onClick={stop} title="Stop Argus right now (Esc)">STOP <kbd>Esc</kbd></button>
      ) : (
        <button className="invoke" disabled={!canSend} onClick={submit}>{uploading ? "UPLOADING" : "INVOKE"}</button>
      )}
    </div>
  );
}
