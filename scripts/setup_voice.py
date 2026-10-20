"""Give Argus its British voice: Kokoro-82M, local and free.

Downloads two files (about 120 MB total) from the kokoro-onnx project's
official GitHub release into ~/.argus/voice, after installing the
`kokoro-onnx` package into this Python environment.

Run:  python scripts/setup_voice.py            (then restart Argus)
      python scripts/setup_voice.py --try bm_lewis "Good evening."
"""
import os, subprocess, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {"kokoro-v1.0.int8.onnx": 92_361_116, "voices-v1.0.bin": 28_214_398}


def install_package():
    try:
        import kokoro_onnx  # noqa: F401
        print("kokoro-onnx already installed")
    except ImportError:
        print("installing kokoro-onnx ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "kokoro-onnx>=0.6,<0.7"])


def download(voice_dir):
    os.makedirs(voice_dir, exist_ok=True)
    for name, size in FILES.items():
        dest = os.path.join(voice_dir, name)
        if os.path.isfile(dest) and abs(os.path.getsize(dest) - size) < 1_000_000:
            print("have", name)
            continue
        print("downloading %s (%.0f MB) ..." % (name, size / 1e6))
        tmp = dest + ".part"
        urllib.request.urlretrieve(RELEASE + name, tmp)
        got = os.path.getsize(tmp)
        if abs(got - size) > 1_000_000:
            os.remove(tmp)
            sys.exit("%s: expected ~%d bytes, got %d -- not using it" % (name, size, got))
        os.replace(tmp, dest)


def main():
    from core import speaker
    if "--try" not in sys.argv:
        install_package()
        download(speaker.VOICE_DIR)
    import importlib
    importlib.reload(speaker)
    voice = sys.argv[sys.argv.index("--try") + 1] if "--try" in sys.argv else speaker.DEFAULT_VOICE
    text = sys.argv[sys.argv.index("--try") + 2] if "--try" in sys.argv and len(sys.argv) > sys.argv.index("--try") + 2 \
        else "Good evening. All systems are online, and I've taken the liberty of checking your inbox."
    import asyncio
    audio, eng = asyncio.run(speaker.say(text, voice))
    out = os.path.join(speaker.VOICE_DIR, "sample-%s.wav" % voice)
    open(out, "wb").write(audio)
    print("engine: %s | voice: %s | sample: %s" % (eng, voice, out))
    print("British voices to try: bm_george (default), bm_lewis, bm_daniel, bm_fable "
          "-- set ARGUS_VOICE in .env to change.")


if __name__ == "__main__":
    main()
