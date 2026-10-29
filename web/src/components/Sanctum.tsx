import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API } from "../lib/connection";
import { desktop, hotkeys, keyLabel, type ShellSettings } from "../lib/desktop";
import { settingsApi, type ModelInfo, type Routine, type Settings, type SettingsView, type Skill, type Tier } from "../lib/settings";
import { speaker } from "../lib/speaker";
import { useArgus } from "../lib/store";
import { THEMES, useTheme } from "../lib/themes";
import { EyeGlyph } from "./Ornament";

/* The Sanctum: every setting Argus has, in one place, applied as you change it. */

const SECTIONS = [
  ["appearance", "Appearance"], ["voice", "Voice"], ["persona", "Persona"], ["minds", "Minds"],
  ["tribute", "Tribute"], ["watcher", "Watcher"], ["reach", "Reach"], ["memory", "Memory"],
  ["skills", "Skills"], ["routines", "Routines"], ["keys", "Keys"],
] as const;
type Section = (typeof SECTIONS)[number][0];
const NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"];

const TIER_INFO: Record<Tier, { title: string; what: string }> = {
  watcher: { title: "The Watcher", what: "Looks at your workspace all day and decides when to speak. Runs constantly, so cheap and fast wins." },
  planner: { title: "The Oracle", what: "Plans every request, writes documents and answers you. The smart one: worth paying for." },
  executor: { title: "The Hands", what: "Carries out each step with tools: searching, reading, clicking. Fast and reliable beats clever." },
};

const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const VOICE_GROUPS: [string, string][] = [
  ["bm_", "British · male"], ["bf_", "British · female"], ["am_", "American · male"], ["af_", "American · female"],
];

const money = (n: number | null | undefined) => (n == null ? "?" : n < 0.1 ? `$${n.toFixed(3)}` : `$${n.toFixed(2)}`);

function Toggle({ on, onChange, label, hint, disabled }: { on: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <label className={`sx-toggle ${disabled ? "disabled" : ""}`}>
      <button type="button" role="switch" aria-checked={on} disabled={disabled} onClick={() => onChange(!on)}
        className={`sx-switch ${on ? "on" : ""}`}><span /></button>
      <span className="sx-toggle-text">
        <span className="sx-toggle-label">{label}</span>
        {hint && <span className="sx-hint">{hint}</span>}
      </span>
    </label>
  );
}

function Seg<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="sx-seg" role="radiogroup">
      {options.map(([v, label]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="sx-field">
      <div className="sx-field-label">{label}</div>
      {children}
      {hint && <div className="sx-hint">{hint}</div>}
    </div>
  );
}

export default function Sanctum({ open, onClose }: { open: boolean; onClose: () => void }) {
  const live = useArgus((s) => s.source === "live" && s.conn === "live");
  const [section, setSection] = useState<Section>("appearance");
  const [view, setView] = useState<SettingsView | null>(null);
  const [shell, setShell] = useState<ShellSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(0);
  const theme = useTheme();

  const load = useCallback(async () => {
    setError(null);
    try {
      setView(await settingsApi.get());
    } catch (e) {
      setError(live ? `Couldn't load settings: ${(e as Error).message}` : null);
    }
    if (desktop?.getShell) setShell(await desktop.getShell());
  }, [live]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  const put = useCallback(async (patch: Partial<Record<keyof Settings, unknown>>) => {
    setError(null);
    try {
      setView(await settingsApi.put(patch));
      setSaved(Date.now());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const shellSet = useCallback(async (key: keyof ShellSettings, value: unknown) => {
    if (!desktop?.setShell) return;
    setShell(await desktop.setShell(key, value));
    setSaved(Date.now());
  }, []);

  const s = view?.settings;
  const coreless = !view;
  const visible = coreless ? SECTIONS.filter(([k]) => k === "appearance") : SECTIONS;

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="sanctum-veil" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
          <motion.div className="sanctum panel" role="dialog" aria-label="Settings" initial={{ y: 18, opacity: 0, scale: 0.985 }}
            animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 10, opacity: 0 }} transition={{ duration: 0.28, ease: [0.2, 0.7, 0.2, 1] }}>
            <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
            <header className="sx-head">
              <EyeGlyph size={26} lit />
              <div>
                <div className="sx-title">THE SANCTUM</div>
                <div className="sx-sub">EVERY SETTING ARGUS HAS · APPLIED AS YOU CHANGE IT</div>
              </div>
              <span className={`sx-saved ${Date.now() - saved < 1800 ? "show" : ""}`}>SAVED</span>
              <button className="sx-close" onClick={onClose} aria-label="Close settings">×</button>
            </header>
            <div className="sx-body">
              <nav className="sx-nav">
                {visible.map(([key, label], i) => (
                  <button key={key} className={section === key ? "on" : ""} onClick={() => setSection(key)}>
                    <span className="sx-num">{NUMERALS[i]}</span>{label.toUpperCase()}
                  </button>
                ))}
              </nav>
              <div className="sx-content">
                {error && <div className="sx-error">{error}</div>}
                {coreless && section !== "appearance" && <div className="sx-hint">Connect to a live core to change the rest.</div>}

                {section === "appearance" && (
                  <section>
                    <h3>Colour theme</h3>
                    <p className="sx-lead">Repaints everything at once: the panels, the hundred eyes, and the orb that floats over your other apps.</p>
                    <div className="sx-themes">
                      {Object.entries(THEMES).map(([key, p]) => (
                        <button key={key} className={`sx-theme ${theme.name === key ? "on" : ""}`}
                          onClick={() => { theme.set(key); if (view) void put({ theme: key }); }}
                          style={{ ["--t-void" as string]: p.void, ["--t-gold" as string]: p.gold, ["--t-amber" as string]: p.amber, ["--t-bone" as string]: p.bone }}>
                          <span className="sx-theme-eye"><span /></span>
                          <span className="sx-theme-swatches">
                            {[p.gold, p.amber, p.ember, p.bone].map((c) => <i key={c} style={{ background: c }} />)}
                          </span>
                          <span className="sx-theme-name">{p.label}</span>
                          <span className="sx-theme-blurb">{p.blurb}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {s && view && section === "voice" && <VoiceSection view={view} put={put} shell={shell} shellSet={shellSet} />}

                {s && section === "persona" && (
                  <section>
                    <h3>Persona</h3>
                    <p className="sx-lead">How Argus carries itself when it talks to you.</p>
                    <Field label="Call me" hint='e.g. "sir", "boss", your name. Leave empty and it won’t use one.'>
                      <input className="sx-input" defaultValue={s.persona.address} placeholder="(nothing)" maxLength={40}
                        onBlur={(e) => e.target.value !== s.persona.address && void put({ persona: { address: e.target.value } })} />
                    </Field>
                    <Field label="Manner">
                      <Seg value={s.persona.tone} onChange={(tone) => void put({ persona: { tone } })}
                        options={[["casual", "Casual"], ["butler", "Butler"], ["formal", "Formal"]]} />
                    </Field>
                    <Field label="Replies">
                      <Seg value={s.persona.length} onChange={(length) => void put({ persona: { length } })}
                        options={[["short", "Short"], ["normal", "Normal"], ["detailed", "Detailed"]]} />
                    </Field>
                  </section>
                )}

                {s && view && section === "minds" && <MindsSection view={view} put={put} />}

                {s && view && section === "tribute" && <TributeSection view={view} put={put} />}

                {s && view && section === "watcher" && (
                  <section>
                    <h3>The Watcher</h3>
                    <p className="sx-lead">Argus looking over your shoulder and offering help before you ask.</p>
                    <Toggle on={s.watcher.enabled} onChange={(enabled) => void put({ watcher: { enabled } })}
                      label="Watch and offer help" hint="Off: Argus only acts when you ask it something." />
                    <Field label={`Looks every ${s.watcher.interval} seconds`} hint="More often notices sooner, and costs a little more.">
                      <Slider value={s.watcher.interval} min={5} max={120} step={5} onCommit={(interval) => void put({ watcher: { interval } })} />
                    </Field>
                    <Field label={`Stays quiet ${Math.round(s.watcher.cooldown / 60)} min after speaking`} hint="How long before it may interrupt you again.">
                      <Slider value={s.watcher.cooldown} min={0} max={1800} step={60} onCommit={(cooldown) => void put({ watcher: { cooldown } })} />
                    </Field>
                    <Field label="Watched folder" hint={desktop ? "Changing it restarts Argus’s core (a few seconds)." : "Set ARGUS_WATCH_ROOT before starting the core."}>
                      <div className="sx-row">
                        <code className="sx-path">{shell?.workspace || view.workspace}</code>
                        {desktop?.chooseFolder && <button className="sx-btn" onClick={async () => setShell(await desktop!.chooseFolder!())}>CHANGE…</button>}
                      </div>
                    </Field>
                  </section>
                )}

                {s && view && section === "reach" && (
                  <section>
                    <h3>Reach</h3>
                    <p className="sx-lead">What Argus may touch on this PC, and how it stays with you.</p>
                    {shell ? (
                      <>
                        <Toggle on={shell.fullAccess} onChange={(v) => void shellSet("fullAccess", v)} label="Full PC access"
                          hint="Read anything on any drive, find and open files. Writing outside the watched folder and running programs still ask you. Restarts the core." />
                        <Toggle on={shell.orbEnabled} onChange={(v) => void shellSet("orbEnabled", v)} label="Floating orb"
                          hint="The hundred-eyed orb on top of your other apps whenever the hub isn’t in front." />
                        <Toggle on={shell.openAtLogin} onChange={(v) => void shellSet("openAtLogin", v)} label="Start with Windows"
                          hint="Argus starts quietly in the tray when you log in." />
                      </>
                    ) : <div className="sx-hint">These live in the desktop app. Right now the file tools reach: <b>{view.fs_scope === "full" ? "the whole PC" : "the watched folder"}</b>.</div>}
                    <div className="sx-note">
                      <b>Always off-limits</b>, whatever you allow: SSH and cloud keys, browser cookies and saved passwords,
                      Windows credential stores, <code>.env</code> files, password vaults, and Argus’s own memory, skills and settings.
                      Argus never types passwords, card or ID numbers, and every submit, payment, post, upload or download waits for your ALLOW.
                    </div>
                  </section>
                )}

                {view && section === "memory" && <MemorySection view={view} onSaved={(memory) => { setView({ ...view, memory }); setSaved(Date.now()); }} />}
                {view && section === "skills" && <SkillsSection view={view} onChange={(skills) => { setView({ ...view, skills }); setSaved(Date.now()); }} />}
                {view && section === "routines" && <RoutinesSection view={view} onChange={(routines) => { setView({ ...view, routines }); setSaved(Date.now()); }} />}
                {section === "keys" && <KeysSection view={view} />}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** A slider that shows its value while dragging and saves once you let go. */
function Slider({ value, min, max, step, onCommit, format }: { value: number; min: number; max: number; step: number; onCommit: (v: number) => void; format?: (v: number) => string }) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  return (
    <div className="sx-slider">
      <input type="range" min={min} max={max} step={step} value={v} onChange={(e) => setV(Number(e.target.value))}
        onPointerUp={() => v !== value && onCommit(v)} onKeyUp={() => v !== value && onCommit(v)} />
      {format && <span className="sx-slider-val">{format(v)}</span>}
    </div>
  );
}

function VoiceSection({ view, put, shell, shellSet }: { view: SettingsView; put: (p: Partial<Record<keyof Settings, unknown>>) => Promise<void>; shell: ShellSettings | null; shellSet: (k: keyof ShellSettings, v: unknown) => Promise<void> }) {
  const sp = view.speaker;
  const [voiceOn, setVoiceOn] = useState(speaker.enabled);
  useEffect(() => speaker.subscribe(setVoiceOn), []);
  const [previewing, setPreviewing] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const groups = useMemo(() => {
    const out: [string, string[]][] = VOICE_GROUPS.map(([p, label]) => [label, sp.voices.filter((v) => v.startsWith(p))]);
    const rest = sp.voices.filter((v) => !VOICE_GROUPS.some(([p]) => v.startsWith(p)));
    if (rest.length) out.push(["Other languages", rest]);
    return out.filter(([, list]) => list.length);
  }, [sp.voices]);
  const preview = async () => {
    setPreviewing(true);
    try {
      const r = await fetch(API + "/speak", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: "Good evening. Everything is in order, and I've taken the liberty of checking the news.", voice: sp.voice, speed: sp.speed }),
      });
      if (!r.ok) throw new Error(await r.text());
      audio.current?.pause();
      audio.current = new Audio(URL.createObjectURL(await r.blob()));
      audio.current.onended = () => setPreviewing(false);
      await audio.current.play();
    } catch {
      setPreviewing(false);
    }
  };
  return (
    <section>
      <h3>Voice</h3>
      <p className="sx-lead">Argus’s voice is made on this PC: free, private, and it never touches your credits.</p>
      <Toggle on={voiceOn} label="Speak replies" hint="Replies, what it notices, and its questions for you."
        onChange={(v) => { speaker.setEnabled(v); if (shell) void shellSet("voiceOut", v); }} />
      {sp.engine === "kokoro" ? (
        <Field label="Voice">
          <select className="sx-input" value={sp.voice} onChange={(e) => void put({ voice: { name: e.target.value } })}>
            {groups.map(([label, list]) => (
              <optgroup key={label} label={label}>
                {list.map((v) => <option key={v} value={v}>{v.slice(3).replace(/^\w/, (c) => c.toUpperCase())}{v === "bm_george" ? " (default)" : ""}</option>)}
              </optgroup>
            ))}
          </select>
        </Field>
      ) : (
        <div className="sx-note">Using the Windows voice. Run <code>python scripts/setup_voice.py</code> for the British voices.</div>
      )}
      <Field label={`Speed ${sp.speed.toFixed(2)}×`}>
        <Slider value={sp.speed} min={0.7} max={1.8} step={0.05} onCommit={(speed) => void put({ voice: { speed } })} />
      </Field>
      <div className="sx-row">
        <button className="sx-btn primary" onClick={() => void preview()} disabled={previewing}>{previewing ? "SPEAKING…" : "▶ PREVIEW"}</button>
        <button className="sx-btn" onClick={() => void put({ voice: { name: null, speed: null } })}>RESET TO .ENV</button>
      </div>
    </section>
  );
}

function MindsSection({ view, put }: { view: SettingsView; put: (p: Partial<Record<keyof Settings, unknown>>) => Promise<void> }) {
  const s = view.settings;
  const textModels = useMemo(
    () => view.catalogue.filter((m) => m.modality.endsWith("->text") && !/embed/i.test(m.id) && m.price_in != null),
    [view.catalogue]
  );
  const label = (m: ModelInfo) => `${m.id}  ·  ${money(m.price_in)} in / ${money(m.price_out)} out per 1M${m.context ? `  ·  ${Math.round(m.context / 1024)}K ctx` : ""}`;
  return (
    <section>
      <h3>Minds</h3>
      <p className="sx-lead">Which model does which job. Any model on your Nebius account works, priced live so the spending limit stays exact. Nemotron is the default (and the hackathon build).</p>
      {(["watcher", "planner", "executor"] as Tier[]).map((t) => {
        const chosen = s.models[t];
        const info = view.catalogue.find((m) => m.id === (chosen || view.bound[t]));
        return (
          <div className="sx-mind" key={t}>
            <div className="sx-mind-head">
              <span className="sx-mind-title">{TIER_INFO[t].title}</span>
              <span className="sx-hint">{TIER_INFO[t].what}</span>
            </div>
            <div className="sx-row">
              <select className="sx-input grow" value={chosen ?? ""} onChange={(e) => void put({ models: { [t]: e.target.value || null } })}>
                <option value="">Automatic · {view.automatic[t] ?? "Nemotron"}</option>
                {textModels.map((m) => <option key={m.id} value={m.id}>{label(m)}</option>)}
              </select>
              <select className="sx-input" value={s.thinking[t] === null ? "" : s.thinking[t] ? "on" : "off"} title="Reasoning before answering"
                onChange={(e) => void put({ thinking: { [t]: e.target.value === "" ? null : e.target.value === "on" } })}>
                <option value="">Thinking: default</option>
                <option value="on">Thinking: on</option>
                <option value="off">Thinking: off</option>
              </select>
            </div>
            {info && <div className="sx-hint">{info.description || info.id} {info.price_in != null && <>· <b>{money(info.price_in)}</b> in / <b>{money(info.price_out)}</b> out per million tokens</>}</div>}
          </div>
        );
      })}
    </section>
  );
}

function TributeSection({ view, put }: { view: SettingsView; put: (p: Partial<Record<keyof Settings, unknown>>) => Promise<void> }) {
  const [v, setV] = useState(view.budget_usd);
  useEffect(() => setV(view.budget_usd), [view.budget_usd]);
  const pct = Math.min(100, (view.spend_usd / Math.max(0.01, view.budget_usd)) * 100);
  return (
    <section>
      <h3>Tribute</h3>
      <p className="sx-lead">The hard spending limit. Every model call is refused <i>before</i> it’s sent once Argus has spent this much, so it can never run up your card.</p>
      <div className="sx-spend">
        <div className="sx-spend-num">{money(view.spend_usd)} <span>spent of {money(view.budget_usd)}</span></div>
        <div className="sx-bar"><i style={{ width: `${pct}%` }} /></div>
      </div>
      <Field label={`Limit: $${v.toFixed(0)}`}>
        <Slider value={v} min={1} max={60} step={1} onCommit={(b) => { setV(b); void put({ budget_usd: b }); }} />
      </Field>
      {v > 45 && <div className="sx-warn">Above $45: your Nebius credit is $50, and after that Nebius bills your card.</div>}
      <button className="sx-btn" onClick={() => void put({ budget_usd: null })}>RESET TO .ENV ({money(view.budget_default)})</button>
    </section>
  );
}

function MemorySection({ view, onSaved }: { view: SettingsView; onSaved: (m: string[]) => void }) {
  const [facts, setFacts] = useState<string[]>(view.memory);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setFacts(view.memory), [view.memory]);
  const dirty = JSON.stringify(facts) !== JSON.stringify(view.memory);
  const save = async (list: string[]) => {
    setErr(null);
    try {
      const r = await settingsApi.memory(list.map((f) => f.trim()).filter(Boolean));
      if (r.memory.length < list.filter((f) => f.trim()).length) setErr("Some lines weren’t kept: Argus never remembers passwords, codes, card or ID numbers.");
      onSaved(r.memory);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <section>
      <h3>Memory</h3>
      <p className="sx-lead">What Argus knows about you. It reads this before every request. Edit, delete, or add.</p>
      <div className="sx-list">
        {facts.length === 0 && <div className="sx-hint">Nothing yet. Tell Argus about yourself, or add a line below.</div>}
        {facts.map((f, i) => (
          <div className="sx-fact" key={i}>
            <input className="sx-input grow" value={f} onChange={(e) => setFacts(facts.map((x, j) => (j === i ? e.target.value : x)))} />
            <button className="sx-x" aria-label="Forget" onClick={() => setFacts(facts.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
      </div>
      <div className="sx-row">
        <input className="sx-input grow" value={draft} placeholder="e.g. I live in Toronto · I’m after junior SWE roles" onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && draft.trim()) { setFacts([...facts, draft.trim()]); setDraft(""); } }} />
        <button className="sx-btn" disabled={!draft.trim()} onClick={() => { setFacts([...facts, draft.trim()]); setDraft(""); }}>ADD</button>
      </div>
      {err && <div className="sx-warn">{err}</div>}
      <div className="sx-row">
        <button className="sx-btn primary" disabled={!dirty} onClick={() => void save(facts)}>SAVE MEMORY</button>
        <span className="sx-hint">Stored in <code>{view.memory_file}</code></span>
      </div>
    </section>
  );
}

function SkillsSection({ view, onChange }: { view: SettingsView; onChange: (s: Skill[]) => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", when: "", steps: "" });
  const [err, setErr] = useState<string | null>(null);
  const body = (s: Skill) => s.text.split("\n").slice(2).join("\n").trim();
  const open = (s: Skill | null) => {
    setErr(null);
    setEditing(s ? s.name : "__new__");
    setDraft(s ? { name: s.name, when: s.when, steps: body(s) } : { name: "", when: "", steps: "" });
  };
  const save = async () => {
    setErr(null);
    const r = await settingsApi.skill({ ...draft, old_name: editing && editing !== "__new__" ? editing : undefined });
    if (!r.ok) return setErr("Couldn’t save: give it a name and some steps (and no passwords or codes).");
    onChange(r.skills);
    setEditing(null);
  };
  return (
    <section>
      <h3>Skills</h3>
      <p className="sx-lead">Saved how-tos for jobs you hand Argus again and again. When a request fits one, Argus follows it. You can also teach them in chat.</p>
      {view.skills.map((s) => (
        <div className={`sx-card ${editing === s.name ? "open" : ""}`} key={s.name}>
          <button className="sx-card-head" onClick={() => (editing === s.name ? setEditing(null) : open(s))}>
            <span className="sx-card-title">{s.name}</span><span className="sx-hint">when {s.when || "—"}</span>
          </button>
          {editing === s.name && <SkillEditor draft={draft} setDraft={setDraft} onSave={save} err={err}
            onDelete={async () => { await settingsApi.deleteSkill(s.name); onChange(view.skills.filter((x) => x.name !== s.name)); setEditing(null); }} />}
        </div>
      ))}
      {editing === "__new__" ? (
        <div className="sx-card open"><SkillEditor draft={draft} setDraft={setDraft} onSave={save} err={err} onDelete={() => setEditing(null)} deleteLabel="CANCEL" /></div>
      ) : (
        <button className="sx-btn" onClick={() => open(null)}>+ NEW SKILL</button>
      )}
    </section>
  );
}

function SkillEditor({ draft, setDraft, onSave, onDelete, err, deleteLabel = "DELETE" }: { draft: { name: string; when: string; steps: string }; setDraft: (d: { name: string; when: string; steps: string }) => void; onSave: () => void; onDelete: () => void; err: string | null; deleteLabel?: string }) {
  return (
    <div className="sx-card-body">
      <input className="sx-input" placeholder="Name, e.g. Cover letters" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      <input className="sx-input" placeholder="When to use it, e.g. a job asks for a cover letter" value={draft.when} onChange={(e) => setDraft({ ...draft, when: e.target.value })} />
      <textarea className="sx-input" rows={7} placeholder="The steps, in plain words" value={draft.steps} onChange={(e) => setDraft({ ...draft, steps: e.target.value })} />
      {err && <div className="sx-warn">{err}</div>}
      <div className="sx-row">
        <button className="sx-btn primary" onClick={onSave}>SAVE</button>
        <button className="sx-btn danger" onClick={onDelete}>{deleteLabel}</button>
      </div>
    </div>
  );
}

function RoutinesSection({ view, onChange }: { view: SettingsView; onChange: (r: Routine[]) => void }) {
  const [adding, setAdding] = useState(false);
  const [ran, setRan] = useState<string | null>(null);
  return (
    <section>
      <h3>Routines</h3>
      <p className="sx-lead">Things Argus does on its own, on schedule. If the PC was asleep at the time, it catches up within three hours.</p>
      {view.routines.map((r) => (
        <RoutineRow key={r.id} r={r} onChange={onChange} ran={ran === r.name}
          onRun={async () => { const x = await settingsApi.runRoutine(r.name); setRan(x.ok ? r.name : null); }} />
      ))}
      {adding ? (
        <RoutineRow r={{ id: "new", name: "", time: "09:00", days: DAY_KEYS.slice(0, 5), prompt: "", enabled: true, last_run: "" }}
          isNew onChange={(list) => { onChange(list); setAdding(false); }} onCancel={() => setAdding(false)} />
      ) : (
        <button className="sx-btn" onClick={() => setAdding(true)}>+ NEW ROUTINE</button>
      )}
    </section>
  );
}

function RoutineRow({ r, onChange, onRun, onCancel, isNew, ran }: { r: Routine; onChange: (list: Routine[]) => void; onRun?: () => void; onCancel?: () => void; isNew?: boolean; ran?: boolean }) {
  const [d, setD] = useState(r);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setD(r), [r]);
  const dirty = isNew || JSON.stringify(d) !== JSON.stringify(r);
  const save = async (next = d) => {
    setErr(null);
    const res = await settingsApi.routine({ name: next.name, time: next.time, days: next.days, prompt: next.prompt, enabled: next.enabled, old_name: isNew ? undefined : r.name });
    if (!res.ok) return setErr("Needs a name, a time, at least one day, and what to do.");
    onChange(res.routines);
  };
  return (
    <div className={`sx-card open ${d.enabled ? "" : "off"}`}>
      <div className="sx-card-body">
        <div className="sx-row">
          <input className="sx-input grow" placeholder="Name, e.g. Weekly review" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />
          <input className="sx-input" type="time" value={d.time} onChange={(e) => setD({ ...d, time: e.target.value })} />
          {!isNew && <Toggle on={d.enabled} label="" onChange={(enabled) => { const n = { ...d, enabled }; setD(n); void save(n); }} />}
        </div>
        <div className="sx-days">
          {DAY_KEYS.map((k) => (
            <button key={k} className={d.days.includes(k) ? "on" : ""}
              onClick={() => setD({ ...d, days: d.days.includes(k) ? d.days.filter((x) => x !== k) : DAY_KEYS.filter((x) => x === k || d.days.includes(x)) })}>
              {k.slice(0, 2).toUpperCase()}
            </button>
          ))}
        </div>
        <textarea className="sx-input" rows={2} placeholder="What to do, as you’d ask Argus. e.g. Sum up my week: applications, what I worked on, what’s next." value={d.prompt} onChange={(e) => setD({ ...d, prompt: e.target.value })} />
        {err && <div className="sx-warn">{err}</div>}
        <div className="sx-row">
          <button className="sx-btn primary" disabled={!dirty} onClick={() => void save()}>{isNew ? "ADD ROUTINE" : "SAVE"}</button>
          {onRun && <button className="sx-btn" onClick={onRun}>{ran ? "STARTED ✓" : "RUN NOW"}</button>}
          {isNew ? <button className="sx-btn danger" onClick={onCancel}>CANCEL</button>
            : <button className="sx-btn danger" onClick={async () => { await settingsApi.deleteRoutine(r.name); onChange((await settingsApi.get()).routines); }}>DELETE</button>}
          {r.last_run && <span className="sx-hint">last ran {r.last_run}</span>}
        </div>
      </div>
    </div>
  );
}

function KeysSection({ view }: { view: SettingsView | null }) {
  const [keys, setKeys] = useState<{ hub: string | null; talk: string | null; snap?: string | null }>({ hub: null, talk: null });
  useEffect(() => void hotkeys().then(setKeys), []);
  const rows: [string, string][] = [
    ...(keys.hub ? [[keyLabel(keys.hub)!, "Show / hide the hub, from any app"] as [string, string]] : []),
    ...(keys.talk ? [[keyLabel(keys.talk)!, "Talk to Argus, from any app (press, speak, press again)"] as [string, string]] : []),
    ...(keys.snap ? [[keyLabel(keys.snap)!, "Look at my screen: snapshot, and Argus answers what's on it"] as [string, string]] : []),
    ["Esc", "Stop Argus mid-task · dismiss what it noticed · close this"],
    ["Enter", "Accept what Argus noticed"],
    ["/", "Jump to the message box"],
    ["Shift+R", "Record the session’s raw events"],
    ["Ctrl+,", "Open the Sanctum"],
  ];
  return (
    <section>
      <h3>Keys</h3>
      <div className="sx-keys">
        {rows.map(([k, what]) => <div key={k} className="sx-key"><kbd>{k}</kbd><span>{what}</span></div>)}
      </div>
      {view && (
        <div className="sx-note">
          Right now: watcher <b>{view.bound.watcher}</b> · oracle <b>{view.bound.planner}</b> · hands <b>{view.bound.executor}</b>.
          Voice <b>{view.speaker.engine === "kokoro" ? view.speaker.voice : "Windows"}</b>. Spent <b>{money(view.spend_usd)}</b> of {money(view.budget_usd)}.
        </div>
      )}
    </section>
  );
}
