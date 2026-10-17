/* Attaching files: each one is copied into the workspace by the core
 * (POST /attach), and the message carries the resulting paths. The agent then
 * reads them with its own workspace-confined tools. */
import { API } from "./connection";

export interface Attachment {
  id: string;
  name: string;
  bytes: number;
  kind: "image" | "pdf" | "file";
  status: "uploading" | "ready" | "error";
  /** Workspace-relative path, once the core has stored it. */
  path?: string;
  error?: string;
  /** Object URL for an image thumbnail. */
  preview?: string;
}

export const MAX_BYTES = 25 * 1024 * 1024;
const IMAGE = /\.(png|jpe?g|webp|gif|bmp)$/i;

let n = 0;

export function kindOf(name: string): Attachment["kind"] {
  if (IMAGE.test(name)) return "image";
  if (/\.pdf$/i.test(name)) return "pdf";
  return "file";
}

/** A pasted screenshot arrives as "image.png" with no useful name. */
function nameFor(file: File): string {
  if (file.name && file.name !== "image.png") return file.name;
  const ext = (file.type.split("/")[1] || "png").replace("jpeg", "jpg");
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  return `screenshot-${stamp}.${ext}`;
}

export function draft(file: File): Attachment {
  const name = nameFor(file);
  const kind = kindOf(name);
  return {
    id: `att${++n}`,
    name,
    bytes: file.size,
    kind,
    status: file.size > MAX_BYTES ? "error" : "uploading",
    error: file.size > MAX_BYTES ? "Over 25 MB" : undefined,
    preview: kind === "image" ? URL.createObjectURL(file) : undefined,
  };
}

export async function upload(file: File, a: Attachment): Promise<Partial<Attachment>> {
  if (a.status === "error") return {};
  try {
    const r = await fetch(`${API}/attach?name=${encodeURIComponent(a.name)}`, {
      method: "POST",
      body: file,
      headers: { "content-type": "application/octet-stream" },
    });
    const j = await r.json();
    if (!j.ok) return { status: "error", error: j.error || "Upload failed" };
    return { status: "ready", path: j.path, name: j.name, kind: j.kind };
  } catch {
    return { status: "error", error: "Can't reach the Argus core" };
  }
}

export function release(a: Attachment) {
  if (a.preview) URL.revokeObjectURL(a.preview);
}
