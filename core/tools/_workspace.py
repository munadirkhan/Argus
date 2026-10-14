"""Workspace confinement shared by the file tools.

ARGUS reads web pages, and web pages can contain instructions. Whatever the
model is talked into, file tools can only touch paths inside the workspace
root (ARGUS_WATCH_ROOT). Anything that resolves outside it -- `..`, absolute
paths elsewhere, another drive, a symlink pointing out -- is refused.

Leading underscore: the registry skips this module (it is not a tool).
"""
from __future__ import annotations
import os


class OutsideWorkspace(ValueError):
    pass


def root() -> str:
    return os.path.realpath(os.environ.get("ARGUS_WATCH_ROOT") or os.getcwd())


def resolve(path: str | None) -> str:
    """Resolve a model-supplied path to an absolute path inside the workspace."""
    base = root()
    raw = (path or ".").strip().strip('"').strip("'") or "."
    candidate = raw if os.path.isabs(raw) else os.path.join(base, raw)
    real = os.path.realpath(candidate)
    try:
        inside = os.path.commonpath([real, base]) == base
    except ValueError:                      # different drives on Windows
        inside = False
    if not inside:
        raise OutsideWorkspace(
            "'%s' is outside the workspace (%s). Use a path relative to it." % (raw, base))
    return real


def display(path: str) -> str:
    """Workspace-relative, forward-slashed, for summaries the UI shows."""
    try:
        return os.path.relpath(path, root()).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def human_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024)
    return "%.1f MB" % (n / (1024 * 1024))


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
             "dist", "build", ".idea", ".vscode", ".pytest_cache"}
