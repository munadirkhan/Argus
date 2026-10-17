"""Files the user hands to ARGUS on purpose.

ARGUS's file tools are confined to the workspace, and that is the guarantee
that stops a web page talking it into reading something private. Attaching a
file must not punch a hole in that. So an attachment is *copied into* the
workspace, under .argus/attachments/, and the agent reads the copy with its
normal confined tools. The user's explicit act of attaching is the grant;
nothing outside the workspace becomes reachable.

.argus/ starts with a dot, so the watcher's scan ignores it: attaching a file
never makes ARGUS comment on the file you just gave it.
"""
from __future__ import annotations
import os, re, unicodedata

MAX_BYTES = 25 * 1024 * 1024
SUBDIR = os.path.join(".argus", "attachments")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *("com%d" % i for i in range(1, 10)),
             *("lpt%d" % i for i in range(1, 10))}


def safe_name(name: str) -> str:
    """A filename that cannot escape the folder or upset Windows."""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("\\", "/").split("/")[-1]          # basename only
    name = _BAD.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    stem, ext = os.path.splitext(name)
    if not stem or stem.lower() in _RESERVED:
        stem = "attachment" if not stem else stem + "_"
    stem = stem[:100]
    ext = ext[:12]
    return stem + ext


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".pdf":
        return "pdf"
    return "file"


def save(root: str, name: str, data: bytes) -> dict:
    """Write `data` under <root>/.argus/attachments/, never overwriting.
    Returns the record the client and the agent both use."""
    if not data:
        raise ValueError("That file is empty")
    if len(data) > MAX_BYTES:
        raise ValueError("Files over %d MB can't be attached" % (MAX_BYTES // (1024 * 1024)))
    folder = os.path.join(os.path.realpath(root), SUBDIR)
    os.makedirs(folder, exist_ok=True)
    clean = safe_name(name)
    stem, ext = os.path.splitext(clean)
    candidate, n = clean, 2
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = "%s (%d)%s" % (stem, n, ext)
        n += 1
    full = os.path.join(folder, candidate)
    # Final guard: whatever happened above, the result must sit in the folder.
    if os.path.dirname(os.path.realpath(full)) != os.path.realpath(folder):
        raise ValueError("Invalid file name")
    tmp = full + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, full)
    rel = os.path.relpath(full, os.path.realpath(root)).replace("\\", "/")
    return {"path": rel, "name": candidate, "bytes": len(data), "kind": kind_of(candidate)}


def describe_for_agent(items: list[dict]) -> str:
    """The lines appended to the user's request so the planner knows what it has."""
    if not items:
        return ""
    lines = []
    for a in items:
        how = {"image": "image -- use view_image",
               "pdf": "PDF -- use read_file"}.get(a.get("kind"), "use read_file")
        lines.append("- %s (%s; %s bytes)" % (a.get("path"), how, a.get("bytes", "?")))
    return ("\n\nThe user attached these files for this request (paths are relative to "
            "the workspace; read them first):\n" + "\n".join(lines))
