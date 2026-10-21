"""Argus's voice: text to speech, on this machine.

Nebius Token Factory has no speech models, and a cloud voice (ElevenLabs and
the like) bills per character. So the voice is local, free and private:

  kokoro  Kokoro-82M (Apache-2.0) through onnxruntime on the CPU. Has British
          male voices -- bm_george (default), bm_lewis, bm_daniel, bm_fable --
          for the calm, dry butler Argus is going for. Needs `pip install
          kokoro-onnx` and two model files in ~/.argus/voice (see README).
  sapi    Windows' built-in voice, as a fallback so Argus can always talk.
          American unless an en-GB voice pack is installed.

It's "Jarvis-style", not a copy of any actor's voice.
"""
from __future__ import annotations
import asyncio, io, os, re, subprocess, sys, tempfile, threading, wave

VOICE_DIR = os.environ.get("ARGUS_VOICE_DIR") or os.path.join(os.path.expanduser("~"), ".argus", "voice")
MODEL_FILES = ("kokoro-v1.0.int8.onnx", "kokoro-v1.0.onnx")
VOICES_FILE = "voices-v1.0.bin"
DEFAULT_VOICE = os.environ.get("ARGUS_VOICE", "bm_george")
SPEED = float(os.environ.get("ARGUS_VOICE_SPEED", "1.0"))
MAX_CHARS = 900

_kokoro = None
_lock = threading.Lock()


def configure(name: str | None = None, speed: float | None = None) -> None:
    """Settings override .env: None means back to the .env / built-in value."""
    global DEFAULT_VOICE, SPEED
    DEFAULT_VOICE = name or os.environ.get("ARGUS_VOICE", "bm_george")
    SPEED = float(speed if speed is not None else os.environ.get("ARGUS_VOICE_SPEED", "1.0"))


class VoiceUnavailable(RuntimeError):
    pass


def _model_path() -> str | None:
    for name in MODEL_FILES:
        p = os.path.join(VOICE_DIR, name)
        if os.path.isfile(p) and os.path.isfile(os.path.join(VOICE_DIR, VOICES_FILE)):
            return p
    return None


def engine() -> str | None:
    """Which engine will speak: kokoro, sapi, or None."""
    if _model_path():
        try:
            import kokoro_onnx  # noqa: F401
            return "kokoro"
        except ImportError:
            pass
    if sys.platform == "win32":
        return "sapi"
    return None


def voices() -> list[str]:
    if engine() != "kokoro":
        return []
    k = _load()
    names = list(k.get_voices()) if hasattr(k, "get_voices") else []
    # English first, British first: the ones that fit Argus.
    return sorted(names, key=lambda v: (not v.startswith("b"), not v.startswith(("bm", "am")), v))


def clean(text: str) -> str:
    """What should be heard, not read: no markdown, citations, links or code."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[(\d+)\]", "", t)                       # [1] citations
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)         # [label](url)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_#>|~]", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > MAX_CHARS:                                  # say the start, whole sentences
        cut = t[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = cut[:end + 1] if end > 200 else cut
    return t


def _load():
    global _kokoro
    with _lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(_model_path(), os.path.join(VOICE_DIR, VOICES_FILE))
        return _kokoro


def _wav(samples, rate: int) -> bytes:
    import numpy as np
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _kokoro_say(text: str, voice: str, speed: float | None = None) -> bytes:
    k = _load()
    lang = "en-gb" if voice.startswith("b") else "en-us"
    samples, rate = k.create(text, voice=voice, speed=speed or SPEED, lang=lang)
    return _wav(samples, rate)


def _sapi_say(text: str) -> bytes:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        # Text goes in through stdin, never through the command line.
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$gb = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'en-GB' -and "
            "$_.VoiceInfo.Gender -eq 'Male' } | Select-Object -First 1;"
            "if ($gb) { $s.SelectVoice($gb.VoiceInfo.Name) };"
            "$s.Rate = 0;"
            "$s.SetOutputToWaveFile($env:ARGUS_TTS_OUT);"
            "$s.Speak([Console]::In.ReadToEnd());"
            "$s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       input=text.encode("utf-8"), env={**os.environ, "ARGUS_TTS_OUT": path},
                       capture_output=True, timeout=60, check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


async def say(text: str, voice: str | None = None, speed: float | None = None) -> tuple[bytes, str]:
    """Synthesize speech. Returns (wav bytes, engine used)."""
    text = clean(text)
    if not text:
        raise VoiceUnavailable("nothing to say")
    eng = engine()
    if eng == "kokoro":
        return await asyncio.to_thread(_kokoro_say, text, voice or DEFAULT_VOICE, speed), eng
    if eng == "sapi":
        return await asyncio.to_thread(_sapi_say, text), eng
    raise VoiceUnavailable("no text-to-speech engine on this machine")


def warm() -> None:
    """Load the voice model ahead of the first reply."""
    if engine() == "kokoro":
        try:
            _kokoro_say("Ready.", DEFAULT_VOICE)
        except Exception as e:
            print("[argus] voice warm-up failed:", e, flush=True)
