"""Speech-to-text, entirely on this machine.

Token Factory serves no speech model, and a personal assistant that streams
your voice to a third party is the wrong default anyway. So ARGUS transcribes
locally with faster-whisper: the model is downloaded once (~145 MB for
base.en), then every utterance stays on the machine. A short command
transcribes in under a second on CPU.

Model choice: ARGUS_STT_MODEL (default "base.en"). "small.en" is more
accurate and ~3x slower; "tiny.en" is faster and rougher.
"""
from __future__ import annotations
import asyncio, os, tempfile, threading, time

MODEL_NAME = os.environ.get("ARGUS_STT_MODEL", "base.en")
MAX_AUDIO_BYTES = 20 * 1024 * 1024     # ~10+ minutes of opus; commands are seconds

_model = None
_lock = threading.Lock()

# Container suffix from the browser's MIME type. PyAV sniffs the content, but
# a correct suffix avoids a misdetection on very short clips.
_SUFFIX = {
    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "audio/wave": ".wav", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/flac": ".flac",
}


class VoiceUnavailable(RuntimeError):
    pass


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    global _model
    with _lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise VoiceUnavailable(
                    "Voice needs faster-whisper: pip install faster-whisper") from e
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        return _model


def _transcribe_file(path: str) -> str:
    model = _load()
    segments, _info = model.transcribe(
        path, beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()


async def transcribe(audio: bytes, mime: str = "audio/webm") -> dict:
    """Transcribe one utterance. Returns {"text", "ms"}; raises VoiceUnavailable
    or ValueError with a message fit to show the user."""
    if not audio:
        raise ValueError("No audio received")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Recording is too long")
    suffix = _SUFFIX.get((mime or "").split(";")[0].strip().lower(), ".webm")
    fd, path = tempfile.mkstemp(prefix="argus_voice_", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        t0 = time.perf_counter()
        try:
            text = await asyncio.to_thread(_transcribe_file, path)
        except VoiceUnavailable:
            raise
        except Exception as e:
            raise ValueError("Could not decode that recording (%s)" % type(e).__name__) from e
        return {"text": text, "ms": int((time.perf_counter() - t0) * 1000)}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def warm() -> None:
    """Load the model ahead of the first command, so that one isn't slow."""
    try:
        _load()
    except Exception as e:
        print("[voice] not available: %s" % e, flush=True)
