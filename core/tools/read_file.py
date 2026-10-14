"""Read a file from the workspace. PDFs are converted to text."""
from __future__ import annotations
import asyncio, os

from .base import Tool, ToolResult
from ._workspace import OutsideWorkspace, display, resolve

MAX_TEXT_BYTES = 400_000
MAX_PDF_PAGES = 40


def _read_pdf(path: str) -> tuple[str, int, int]:
    from pypdf import PdfReader
    reader = PdfReader(path)
    total = len(reader.pages)
    parts = []
    for i, page in enumerate(reader.pages[:MAX_PDF_PAGES]):
        try:
            t = (page.extract_text() or "").strip()
        except Exception:
            t = ""
        if t:
            parts.append("--- page %d ---\n%s" % (i + 1, t))
    return "\n\n".join(parts), min(total, MAX_PDF_PAGES), total


class ReadFile(Tool):
    name = "read_file"
    description = ("Read a file from the user's workspace. Handles PDFs (returns "
                   "their text) and any text file. Paths are relative to the workspace.")
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string",
                                "description": "File path, relative to the workspace."}},
        "required": ["path"],
    }

    async def run(self, path: str) -> ToolResult:
        try:
            full = resolve(path)
        except OutsideWorkspace as e:
            return ToolResult(ok=False, summary=str(e))
        if not os.path.isfile(full):
            return ToolResult(ok=False, summary="no such file: %s" % display(full))

        name = display(full)
        if full.lower().endswith(".pdf"):
            try:
                text, read, total = await asyncio.to_thread(_read_pdf, full)
            except Exception as e:
                return ToolResult(ok=False, summary="could not read PDF %s: %s" % (name, e))
            if not text:
                return ToolResult(ok=False,
                                  summary="%s has no extractable text (scanned?)" % name)
            more = "" if read == total else " (first %d of %d)" % (read, total)
            return ToolResult(ok=True, summary="%s · %d pages%s" % (name, read, more),
                              detail=text, meta={"path": full, "pages": read,
                                                 "total_pages": total})

        size = os.path.getsize(full)
        with open(full, "rb") as f:
            raw = f.read(MAX_TEXT_BYTES)
        if b"\x00" in raw[:4096]:
            return ToolResult(ok=False, summary="%s looks binary; not reading it" % name)
        text = raw.decode("utf-8", errors="replace")
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        note = "" if size <= MAX_TEXT_BYTES else " (truncated)"
        return ToolResult(ok=True, summary="%s · %d lines%s" % (name, lines, note),
                          detail=text or "(empty file)",
                          meta={"path": full, "bytes": size, "lines": lines})


TOOL = ReadFile()
