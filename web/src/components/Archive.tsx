import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useArgus } from "../lib/store";
import { fetchArtifact } from "../lib/connection";
import { basename, bytes, relative } from "../lib/format";
import { EyeGlyph, Panel } from "./Ornament";

const TEXT_EXT = /\.(md|txt|json|py|ts|tsx|js|csv|yaml|yml|toml|html)$/i;

function tagOf(path: string) {
  const ext = (path.split(".").pop() ?? "").toLowerCase();
  if (ext === "pdf") return { t: "PDF", c: "pdf" };
  if (ext === "md") return { t: "MD", c: "md" };
  return { t: ext.slice(0, 4).toUpperCase() || "FILE", c: "" };
}

function Tree() {
  const tree = useArgus((s) => s.tree);
  const touched = useArgus((s) => s.touched);
  const selected = useArgus((s) => s.selectedArtifact);
  const select = useArgus((s) => s.selectArtifact);
  const [, tick] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 1500);
    return () => window.clearInterval(t);
  }, []);

  const groups = useMemo(() => {
    const g = new Map<string, { path: string; rel: string; bytes: number }[]>();
    tree.nodes
      .filter((n) => !n.dir)
      .forEach((n) => {
        const rel = relative(n.path, tree.root);
        const parts = rel.split("/");
        const folder = parts.length > 1 ? parts.slice(0, -1).join("/") + "/" : "";
        if (!g.has(folder)) g.set(folder, []);
        g.get(folder)!.push({ path: n.path, rel, bytes: n.bytes });
      });
    return [...g.entries()].sort(([a], [b]) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
  }, [tree]);

  if (!tree.nodes.length) {
    return <div className="tree"><div className="folder">— the workspace is empty —</div></div>;
  }
  const now = Date.now();
  return (
    <div className="tree">
      {groups.map(([folder, files]) => (
        <div key={folder || "."}>
          {folder && <div className="folder">▸ {folder}</div>}
          {files.map((f) => {
            const tag = tagOf(f.path);
            const fresh = now - (touched[f.path] ?? 0) < 6000;
            const norm = f.path.replace(/\\/g, "/");
            return (
              <div
                key={f.path}
                className={`file ${fresh ? "fresh" : ""} ${selected === norm ? "sel" : ""}`}
                style={{ paddingLeft: folder ? 20 : 8 }}
                onClick={() => TEXT_EXT.test(f.path) && select(norm)}
                title={f.rel}
              >
                <span className={`ftag ${tag.c}`}>{tag.t}</span>
                <span>{basename(f.path)}</span>
                <span className="size">{bytes(f.bytes)}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function Document() {
  const artifacts = useArgus((s) => s.artifacts);
  const selected = useArgus((s) => s.selectedArtifact);
  const select = useArgus((s) => s.selectArtifact);
  const [full, setFull] = useState<Record<string, string>>({});

  const current = artifacts.find((a) => a.path === selected) ?? null;
  const path = selected;
  const at = current?.at ?? 0;

  useEffect(() => {
    if (!path) return;
    let alive = true;
    fetchArtifact(path).then((text) => {
      if (alive && text !== null) setFull((f) => ({ ...f, [path]: text }));
    });
    return () => {
      alive = false;
    };
  }, [path, at]);

  if (!path) {
    return (
      <div className="doc-empty">
        <EyeGlyph size={64} />
        <div className="voice">Nothing has been inscribed yet.</div>
        <div style={{ fontSize: 11 }}>When Argus finishes a task, the document it writes appears here.</div>
      </div>
    );
  }

  const raw = full[path] ?? current?.preview ?? "";
  const isCode = current?.kind === "code" || /\.(tsx?|jsx?|py|json)$/i.test(path);
  const fence = "```";
  const body = isCode ? `${fence}${path.split(".").pop() ?? ""}\n${raw}\n${fence}` : raw;
  return (
    <>
      {artifacts.length > 0 && (
        <div className="doc-tabs" role="tablist">
          {artifacts.map((a) => (
            <button key={a.path} role="tab" aria-selected={a.path === path} onClick={() => select(a.path)}>
              {basename(a.path)}
            </button>
          ))}
        </div>
      )}
      <div className="doc">
        <div className="stamp">
          <span>{basename(path).toUpperCase()}</span>
          <span>{current ? `${bytes(current.bytes)} · INSCRIBED BY THE ORACLE` : "FROM THE WORKSPACE"}</span>
        </div>
        <div className="scroll-doc">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer" /> }}
          >
            {body || "_(empty)_"}
          </ReactMarkdown>
        </div>
      </div>
    </>
  );
}

export default function Archive() {
  const session = useArgus((s) => s.session);
  const count = useArgus((s) => s.tree.nodes.filter((n) => !n.dir).length);
  return (
    <Panel num="IV" title="THE ARCHIVE" meta={session ? `~/${basename(session.cwd)} · ${count} files` : ""} className="archive">
      <Tree />
      <div style={{ borderTop: "1px solid var(--line)", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <Document />
      </div>
    </Panel>
  );
}
