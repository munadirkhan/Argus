"""Write a small, valid, text-extractable PDF with no dependencies.

Used to build test fixtures and the demo workspace without downloading files.
"""
from __future__ import annotations
import textwrap


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: str, title: str, paragraphs: list[str], width: int = 88) -> None:
    lines = [title, ""]
    for p in paragraphs:
        lines += textwrap.wrap(p, width) or [""]
        lines.append("")

    per_page = 48
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    objs: list[bytes] = []
    n_pages = len(pages)
    font_id = 3 + 2 * n_pages
    kids = " ".join("%d 0 R" % (3 + 2 * i) for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n_pages)).encode())
    for i, page in enumerate(pages):
        content_id = 4 + 2 * i
        objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                     "/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>"
                     % (content_id, font_id)).encode())
        ops = ["BT", "/F1 10 Tf", "13 TL", "60 740 Td"]
        for j, ln in enumerate(page):
            if i == 0 and j == 0:
                ops += ["/F1 14 Tf", "(%s) Tj" % _esc(ln), "/F1 10 Tf", "T*"]
            else:
                ops += ["(%s) Tj" % _esc(ln), "T*"]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1", errors="replace")
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % k + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as f:
        f.write(out)
