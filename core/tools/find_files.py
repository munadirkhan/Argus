"""Find files by name across the PC (or the workspace)."""
from __future__ import annotations
import asyncio, fnmatch, os, time

from .base import Tool, ToolResult
from ._workspace import (SKIP_DIRS, OutsideWorkspace, display, full_access, human_size,
                         is_protected, resolve)

MAX_RESULTS = 40
TIME_LIMIT_S = 12
# Folders full of app internals that are never what the user means.
NOISE = {"appdata", "$recycle.bin", "system volume information", "windows", "program files",
         "program files (x86)", "programdata", "site-packages", ".cache", ".npm", ".cargo", ".rustup"}


def _search(top: str, words: list[str], exts: set[str]) -> tuple[list[tuple[float, str, int]], bool]:
    hits, done, deadline = [], True, time.monotonic() + TIME_LIMIT_S
    for dirpath, dirnames, filenames in os.walk(top):
        if time.monotonic() > deadline:
            done = False
            break
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and d.lower() not in NOISE and not d.startswith(".")
                       and not is_protected(os.path.join(dirpath, d))]
        for fn in filenames:
            low = fn.lower()
            if exts and os.path.splitext(low)[1] not in exts:
                continue
            if all(fnmatch.fnmatch(low, w) if any(c in w for c in "*?[") else w in low for w in words):
                full = os.path.join(dirpath, fn)
                if is_protected(full):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                hits.append((st.st_mtime, full, st.st_size))
    hits.sort(reverse=True)
    return hits[:MAX_RESULTS], done


class FindFiles(Tool):
    name = "find_files"
    description = ("Find files by name, newest first -- e.g. the user's resume, a photo, a project. "
                   "Searches their home folder by default when full access is on (or the workspace). "
                   "Words must all appear in the file name; * and ? work as wildcards.")
    parameters = {"type": "object", "properties": {
        "name": {"type": "string", "description": "Words or a pattern from the file name, e.g. \"resume\" or \"*.pdf\"."},
        "folder": {"type": "string", "description": "Where to look. Default: home folder (full access) or workspace."},
        "types": {"type": "string", "description": "Optional extensions, e.g. \"pdf,docx\"."}},
        "required": ["name"]}
    timeout = 20

    async def run(self, name: str, folder: str = "", types: str = "") -> ToolResult:
        words = [w for w in str(name).lower().split() if w]
        if not words:
            return ToolResult(ok=False, summary="give part of the file name")
        default = os.path.expanduser("~") if full_access() else "."
        try:
            top = resolve(folder or default)
        except OutsideWorkspace as e:
            return ToolResult(ok=False, summary=str(e))
        if not os.path.isdir(top):
            return ToolResult(ok=False, summary="not a folder: %s" % display(top))
        exts = {"." + e.strip().lstrip(".").lower() for e in str(types).split(",") if e.strip()}
        hits, done = await asyncio.to_thread(_search, top, words, exts)
        if not hits:
            return ToolResult(ok=True, summary="nothing named like %r in %s" % (name, display(top)),
                              detail="No matches." + ("" if done else " (search stopped at the time limit)"))
        lines = ["%s  (%s, modified %s)" % (display(p), human_size(sz), time.strftime("%Y-%m-%d", time.localtime(m)))
                 for m, p, sz in hits]
        note = "" if done else "\n(search stopped at the %ds limit; narrow the folder for more)" % TIME_LIMIT_S
        return ToolResult(ok=True, summary="%d match%s for %r" % (len(hits), "" if len(hits) == 1 else "es", name),
                          detail="\n".join(lines) + note)


TOOL = FindFiles()
