import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { speak } from "../lib/connection";
import { bytes, relative } from "../lib/format";
import { VIDEO_MODE } from "../lib/keyboard";
import { dictation, speechSupported, type SpeechState } from "../lib/speech";
import { useArgus } from "../lib/store";
import { EyeGlyph } from "./Ornament";

/* The composer: type, dictate, or reference a workspace file with @.
 *
 * Attaching means referencing, not uploading. ARGUS already reads files
 * itself, and its file tools are confined to the workspace -- so "@notes.md"
 * hands it a path it can open, instead of a copy it cannot verify. That keeps
 * the confinement guarantee intact and works for a 200MB PDF.
 */

const MAX_SUGGESTIONS = 8;

interface Entry {
  path: string;
  rel: string;
  bytes: number;
}

/** Subsequence match, so "wljs" finds "watchlist.js". Returns null if no match. */
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

export default function Composer() {
  const [text, setText] = useState("");
  const [picker, setPicker] = useState<{ query: string; from: number } | null>(null);
  const [active, setActive] = useState(0);
  const [speech, setSpeech] = useState<SpeechState>({
    listening: false, final: "", interim: "", error: null,
  });

  const busy = useArgus((s) => s.busy);
  const conn = useArgus((s) => s.conn);
  const tree = useArgus((s) => s.tree);
  const note = useArgus((s) => (s.activeTier ? s.tiers[s.activeTier].note : ""));

  const input = useRef<HTMLInputElement>(null);
  const live = conn === "live";
  const canSend = live && !busy && text.trim().length > 0;
  const mic = useMemo(speechSupported, []);

  useEffect(() => {
    const off = dictation.subscribe(setSpeech);
    return () => { off(); };
  }, []);

  // While dictating, the box mirrors what has been heard so far.
  useEffect(() => {
    if (speech.listening) setText(dictation.text());
  }, [speech.listening, speech.final, speech.interim]);

  const files: Entry[] = useMemo(
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
      .filter((m): m is { f: Entry; s: number } => m.s !== null)
      .sort((a, b) => a.s - b.s || a.f.rel.length - b.f.rel.length)
      .slice(0, MAX_SUGGESTIONS)
      .map((m) => m.f);
  }, [picker, files]);

  useEffect(() => setActive(0), [picker?.query]);

  const closePicker = () => setPicker(null);

  /** Rewrite the @token under the cursor into a real path. */
  const choose = (f: Entry) => {
    if (!picker) return;
    const after = text.slice(picker.from + 1 + picker.query.length);
    const next = `${text.slice(0, picker.from)}@${f.rel} ${after.replace(/^\s+/, "")}`;
    setText(next);
    closePicker();
    requestAnimationFrame(() => {
      const caret = picker.from + f.rel.length + 2;
      input.current?.focus();
      input.current?.setSelectionRange(caret, caret);
    });
  };

  const onChange = (value: string, caret: number) => {
    setText(value);
    // An @ that starts a word, with no space since, opens the picker.
    const upto = value.slice(0, caret);
    const at = upto.lastIndexOf("@");
    const token = at >= 0 ? upto.slice(at + 1) : "";
    const startsWord = at === 0 || /\s/.test(upto[at - 1] ?? "");
    setPicker(at >= 0 && startsWord && !/\s/.test(token) ? { query: token, from: at } : null);
  };

  const openPicker = () => {
    if (!live || busy) return;
    const el = input.current;
    const caret = el?.selectionStart ?? text.length;
    const needsSpace = caret > 0 && !/\s$/.test(text.slice(0, caret));
    const insert = (needsSpace ? " " : "") + "@";
    const next = text.slice(0, caret) + insert + text.slice(caret);
    setText(next);
    setPicker({ query: "", from: caret + insert.length - 1 });
    requestAnimationFrame(() => {
      el?.focus();
      const pos = caret + insert.length;
      el?.setSelectionRange(pos, pos);
    });
  };

  const toggleMic = () => {
    if (!live || busy) return;
    if (speech.listening) dictation.stop();
    else {
      dictation.clearError();
      dictation.start(text);
      input.current?.focus();
    }
  };

  const submit = () => {
    if (!canSend) return;
    if (speech.listening) dictation.stop();
    if (speak(text.trim())) {
      dictation.cancel();
      setText("");
      closePicker();
    }
  };

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
      if (picker) { e.preventDefault(); closePicker(); return; }
      if (speech.listening) { e.preventDefault(); dictation.stop(); return; }
    }
    if (e.key === "Enter") submit();
  };

  const placeholder = VIDEO_MODE
    ? ""
    : !live
      ? "Argus is not connected — simulated sessions are read-only"
      : busy
        ? `Argus is at work${note ? ` — ${note.toLowerCase()}` : ""}…`
        : speech.listening
          ? "Listening…"
          : "Speak, and Argus will act…   @ for a file";

  return (
    <div className={`composer ${speech.listening ? "listening" : ""}`}>
      <AnimatePresence>
        {picker && (
          <motion.div
            className="picker"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.14 }}
          >
            <div className="picker-head">
              <span className="label">WORKSPACE</span>
              <span className="mono-dim">
                {matches.length ? "↑↓ choose · ⏎ insert · esc close" : "no file matches"}
              </span>
            </div>
            {matches.map((f, i) => (
              <button
                key={f.path}
                className={`picker-row ${i === active ? "on" : ""}`}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => { e.preventDefault(); choose(f); }}
              >
                <span className="pf">{f.rel}</span>
                <span className="pb">{bytes(f.bytes)}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {speech.error && (
        <div className="mic-error" role="status">
          {speech.error}
          <button onClick={() => dictation.clearError()} aria-label="Dismiss">×</button>
        </div>
      )}

      <EyeGlyph size={20} lit={busy || speech.listening} />

      <button
        className="composer-btn"
        onClick={openPicker}
        disabled={!live || busy}
        title="Reference a file from the workspace (@)"
        aria-label="Reference a workspace file"
      >
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden>
          <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>

      <input
        id="argus-composer"
        ref={input}
        aria-label="Speak to Argus"
        autoComplete="off"
        value={text}
        onChange={(e) => onChange(e.target.value, e.target.selectionStart ?? e.target.value.length)}
        onKeyDown={onKeyDown}
        onBlur={() => window.setTimeout(closePicker, 120)}
        placeholder={placeholder}
        disabled={!live || busy}
      />

      {!picker && <kbd className="composer-key" title="Focus composer">/</kbd>}

      {mic && (
        <button
          className={`composer-btn mic ${speech.listening ? "on" : ""}`}
          onClick={toggleMic}
          disabled={!live || busy}
          title={speech.listening ? "Stop dictation (esc)" : "Dictate"}
          aria-label={speech.listening ? "Stop dictation" : "Start dictation"}
          aria-pressed={speech.listening}
        >
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden>
            <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
            <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" fill="none" stroke="currentColor"
                  strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          {speech.listening && <span className="pulse" aria-hidden />}
        </button>
      )}

      <button className="invoke" disabled={!canSend} onClick={submit}>INVOKE</button>
    </div>
  );
}
