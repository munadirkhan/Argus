"""Where the file tools may reach.

Two scopes, set by ARGUS_FS_SCOPE:

  workspace  (default) only the watched folder. Anything that resolves
             outside it -- `..`, an absolute path, another drive, a symlink
             pointing out -- is refused.
  full       the whole PC. Relative paths still mean the workspace; absolute
             paths and ~ reach anywhere. Writing outside the workspace asks
             the user first (write_file does that).

In both, some places are never opened: SSH and cloud keys, browser profiles
(cookies, saved passwords), Windows credential stores, .env files, key and
password-vault files, and Argus's own browser profile. Argus reads web pages,
and pages can contain instructions; these are what a hijacked model would go
after first.

Leading underscore: the registry skips this module (it is not a tool).
"""
from __future__ import annotations
import os
import re


class OutsideWorkspace(ValueError):
    pass


class Protected(OutsideWorkspace):
    pass


def root() -> str:
    return os.path.realpath(os.environ.get("ARGUS_WATCH_ROOT") or os.getcwd())


def full_access() -> bool:
    return os.environ.get("ARGUS_FS_SCOPE", "workspace").strip().lower() == "full"


# Folders (anywhere in the path) and file names that hold secrets.
_PROTECTED_DIRS = re.compile(
    r"(^|/)(\.ssh|\.gnupg|\.aws|\.azure|\.kube|\.docker|\.argus/browser|"
    r"appdata/(local|roaming)/(google/chrome|microsoft/edge|bravesoftware|vivaldi|opera software|"
    r"mozilla/firefox|microsoft/credentials|microsoft/protect|microsoft/vault|"
    r"1password|bitwarden|keepassxc)|"
    r"windows/system32/config)(/|$)", re.I)
_PROTECTED_FILES = re.compile(
    r"(^|/)(\.env(\..+)?|\.git-credentials|\.netrc|_netrc|\.npmrc|\.pypirc|\.pgpass|"
    r"id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|known_hosts|authorized_keys|"
    r"[^/]*\.(pem|key|p12|pfx|kdbx|kdb|keychain|ovpn|ppk)|wallet\.dat|"
    r"login data|cookies|web data|\.argus_spend\.json)$", re.I)


def is_protected(real: str) -> bool:
    # Argus's own home (~/.argus): memory, skills, routines, browser profile,
    # voice. They steer what Argus does next, so no tool may rewrite them --
    # only the user, in chat or by editing the files.
    own = os.path.realpath(os.path.join(os.path.expanduser("~"), ".argus"))
    try:
        if os.path.commonpath([os.path.realpath(real), own]) == own:
            return True
    except ValueError:
        pass
    p = real.replace("\\", "/")
    if p.endswith("/.env.example") or p.lower().endswith(".env.example"):
        return False
    return bool(_PROTECTED_DIRS.search(p) or _PROTECTED_FILES.search(p))


def inside_workspace(real: str) -> bool:
    base = root()
    try:
        return os.path.commonpath([real, base]) == base
    except ValueError:                      # different drives on Windows
        return False


def resolve(path: str | None) -> str:
    """Resolve a model-supplied path to an absolute path the tools may use."""
    base = root()
    raw = (path or ".").strip().strip('"').strip("'") or "."
    if full_access():
        raw = os.path.expandvars(os.path.expanduser(raw))
    candidate = raw if os.path.isabs(raw) else os.path.join(base, raw)
    real = os.path.realpath(candidate)
    if not full_access() and not inside_workspace(real):
        raise OutsideWorkspace(
            "'%s' is outside the workspace (%s). Use a path relative to it." % (raw, base))
    if is_protected(real):
        raise Protected(
            "'%s' holds keys, passwords or browser data. Argus never opens those." % raw)
    return real


def display(path: str) -> str:
    """Workspace-relative inside the workspace, the full path anywhere else."""
    if inside_workspace(path):
        return os.path.relpath(path, root()).replace("\\", "/")
    return path.replace("\\", "/")


def places() -> str:
    """Where things live on this PC, for the prompts (full access only)."""
    if not full_access():
        return ""
    home = os.path.expanduser("~")
    named = []
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"):
        for base in (os.path.join(home, "OneDrive", name), os.path.join(home, name)):
            if os.path.isdir(base):
                named.append("%s: %s" % (name, base))
                break
    drives = []
    if os.name == "nt":
        drives = ["%s:\\" % d for d in "CDEFGHIJ" if os.path.exists("%s:\\" % d)]
    return ("You can read files anywhere on this PC, not just the workspace. Use absolute paths "
            "outside it. Home: %s. %s. Drives: %s. Writing outside the workspace asks the user. "
            "Keys, passwords, browser data and .env files are off-limits."
            % (home, "; ".join(named), ", ".join(drives) or "/"))


def human_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024)
    return "%.1f MB" % (n / (1024 * 1024))


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
             "dist", "build", ".idea", ".vscode", ".pytest_cache"}
