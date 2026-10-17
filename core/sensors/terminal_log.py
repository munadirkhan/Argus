"""Tail opted-in terminal logs, or tee a command: python -m ... run -- node dev.js."""
from __future__ import annotations

import asyncio
import codecs
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field

from .base import Sensor

ANSI = re.compile(r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-_])")
ERROR = re.compile(r"Error|Exception|Traceback|FATAL|panic:|npm ERR!|Uncaught|[✗×✘]|FAILED|\bERR_\w+", re.I)
FRAME = re.compile(r'^\s+(?:at\s|File "[^\"]+", line \d+)')
EXIT = re.compile(r"\[exit (-?\d+)\]")


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def classify(text: str, in_error: bool = False) -> str | None:
    text = strip_ansi(text)
    if text.startswith("$ ") or not text.strip():
        return "dim"
    exited = EXIT.search(text)
    if exited:
        return "ok" if int(exited[1]) == 0 else "err"
    if ERROR.search(text) or (in_error and FRAME.match(text)):
        return "err"
    if re.search(r"\bwarn(?:ing)?\b|deprecated", text, re.I):
        return "warn"
    if re.search(r"ready in|compiled|[✓✔]|listening on|Local:", text, re.I):
        return "ok"
    return None


def signature(text: str) -> str:
    text = re.sub(r"\b\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:\d\d)?", "", text)
    text = re.sub(r"(?<![\w.:])\d\d:\d\d:\d\d(?:[.,]\d+)?", "", text)
    text = re.sub(r"\b0x[0-9a-f]+\b", "", text, flags=re.I)
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:ms|s|seconds?|milliseconds?)\b", "", text, flags=re.I)
    return " ".join(text.split())


@dataclass
class Tail:
    offset: int = 0
    identity: tuple | None = None
    anchor: bytes = b""
    pending: bytes = b""
    lines: deque = field(default_factory=lambda: deque(maxlen=25))
    title: str = ""
    in_error: bool = False
    seen: deque = field(default_factory=lambda: deque(maxlen=20))

    def add(self, raw: bytes) -> dict:
        text = strip_ansi(raw.decode("utf-8", errors="replace").rstrip("\r"))[:4000]
        tone = classify(text, self.in_error)
        if text.startswith("$ "):
            self.title = text[2:]
            self.in_error = False
        elif tone == "ok":
            self.in_error = False
        elif tone == "err":
            self.in_error = True
        line = {"text": text}
        if tone:
            line["tone"] = tone
        self.lines.append(line)
        return line


class TerminalLog(Sensor):
    name = "terminal"
    interval = 0.5

    def __init__(self, paths: list[Path] | None = None):
        self.paths = paths
        self.tails: dict[Path, Tail] = {}
        self.recent: deque = deque(maxlen=25)
        self._alert_event = None

    def _sources(self):
        if self.paths is not None:
            return self.paths
        root = Path(os.environ.get("ARGUS_WATCH_ROOT") or os.getcwd())
        return list(dict.fromkeys([root / ".argus" / "terminal.log", *(
            Path(p).expanduser() for p in os.environ.get("ARGUS_LOGS", "").split(os.pathsep) if p)]))

    def _read(self, path: Path, tail: Tail) -> list[bytes]:
        # Bounded reads and retained partial lines keep bursty logs inexpensive.
        with path.open("rb") as f:
            stat = os.fstat(f.fileno())
            identity = (stat.st_dev, stat.st_ino)
            if tail.identity is None:
                f.seek(max(0, stat.st_size - 128_000))
                data = f.read(128_000)
                parts = data.split(b"\n")
                tail.pending = parts.pop()[-128_000:]
                for raw in parts[-25:]:
                    tail.add(raw)
                tail.offset = f.tell()
                tail.identity = identity
                tail.anchor = data[-64:]
                return []
            f.seek(max(0, tail.offset - len(tail.anchor)))
            rotated = (identity != tail.identity or stat.st_size < tail.offset or
                       f.read(len(tail.anchor)) != tail.anchor)
            if rotated:
                tail.offset = 0
                tail.pending = b""
                tail.lines.clear()
                tail.title = ""
                tail.in_error = False
            tail.identity = identity
            f.seek(tail.offset)
            data = f.read(256_000)
            tail.offset = f.tell()
            f.seek(max(0, tail.offset - 64))
            tail.anchor = f.read(min(64, tail.offset))
        parts = (tail.pending + data).split(b"\n")
        tail.pending = parts.pop()[-128_000:]
        return parts

    def _poll(self):
        new = []
        title = ""
        wake = False
        for path in self._sources():
            tail = self.tails.setdefault(path, Tail())
            try:
                raw_lines = self._read(path, tail)
            except (OSError, ValueError):
                continue
            # Only the first error of a burst is its signature; continuation
            # frames arriving in later polls must not create a second alert.
            first_error = None
            for raw in raw_lines:
                was_error = tail.in_error
                line = tail.add(raw)
                new.append(line)
                self.recent.append(line)
                title = tail.title or path.name
                tone = line.get("tone")
                if tone == "ok":
                    tail.seen.clear()
                    first_error = None
                elif tone == "err" and not (was_error and (FRAME.match(line["text"]) or EXIT.search(line["text"]))) and first_error is None:
                    first_error = signature(line["text"])
                    if first_error not in tail.seen:
                        tail.seen.append(first_error)
                        wake = True
        if not new:
            return []
        event = {"type": "activity", "source": "terminal", "app": "Terminal",
                 "title": title, "lines": list(self.recent)[-12:],
                 "focus": any(l.get("tone") == "err" for l in new)}
        self._alert_event = event if wake else None
        return [event]

    async def poll(self):
        try:
            return await asyncio.to_thread(self._poll)
        except (OSError, ValueError):
            return []

    def context(self):
        parts = []
        for path, tail in self.tails.items():
            if tail.lines:
                lines = "\n".join(("!! " if l.get("tone") == "err" else "") + l["text"] for l in tail.lines)
                parts.append(f"Log: {path}\n" + lines)
        if not parts:
            return ""
        # Keep file identity and the error/stack when a verbose burst exceeds cap.
        budget = max(0, 1500 // len(parts) - 1)
        clipped = []
        for part in parts:
            header, _, body = part.partition("\n")
            header = header[:min(300, budget)]
            room = max(0, budget - len(header) - 1)
            clipped.append(header + "\n" + (body if len(body) <= room else body[-room:] if room else ""))
        return "\n".join(clipped)[:1500]

    def alert(self, event):
        if event is self._alert_event:
            self._alert_event = None
            return True
        return False


class AnsiStream:
    """Strip even ANSI sequences split between pipe reads (including OSC)."""
    def __init__(self):
        self.state = "text"

    def feed(self, text):
        out = []
        for c in text:
            if self.state == "text":
                if c == "\x1b":
                    self.state = "esc"
                else:
                    out.append(c)
            elif self.state == "esc":
                self.state = "csi" if c == "[" else "osc" if c == "]" else "text"
            elif self.state == "csi" and "@" <= c <= "~":
                self.state = "text"
            elif self.state == "osc":
                if c == "\x07":
                    self.state = "text"
                elif c == "\x1b":
                    self.state = "osc_end"
            elif self.state == "osc_end":
                self.state = "text" if c == "\\" else "osc"
        return "".join(out)


def run_command(command: list[str]) -> int:
    root = Path(os.environ.get("ARGUS_WATCH_ROOT") or os.getcwd())
    log_path = root / ".argus" / "terminal.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = shutil.which(command[0])
    args = [resolved or command[0], *command[1:]]
    display = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    cleaner = AnsiStream()
    child = None
    code = 127
    with log_path.open("a", encoding="utf-8", newline="\n") as log:
        log.write(f"$ {display}\n")
        log.flush()
        last = "\n"
        try:
            child = subprocess.Popen(args if resolved or os.name != "nt" else subprocess.list2cmdline(args),
                shell=not resolved and os.name == "nt", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
            while chunk := child.stdout.read1(8192):
                if hasattr(sys.stdout, "buffer"):
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                else:
                    sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
                clean = cleaner.feed(decoder.decode(chunk))
                log.write(clean)
                log.flush()
                last = clean[-1:] or last
            log.write(cleaner.feed(decoder.decode(b"", final=True)))
            code = child.wait()
        except KeyboardInterrupt:
            if child and child.poll() is None:
                if os.name == "nt":
                    child.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            code = 130
        except OSError as exc:
            log.write(f"\nError: {exc}\n")
            print(str(exc), file=sys.stderr)
        finally:
            if child and child.stdout:
                child.stdout.close()
            log.write(("\n" if last != "\n" else "") + f"[exit {code}]\n")
    return code


SENSOR = TerminalLog()

if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] != ["run"] or len(args) < 2:
        sys.exit("Usage: python -m core.sensors.terminal_log run -- COMMAND [ARGS...]")
    command = args[2:] if args[1] == "--" else args[1:]
    if not command:
        sys.exit("A command is required after --")
    sys.exit(run_command(command))
