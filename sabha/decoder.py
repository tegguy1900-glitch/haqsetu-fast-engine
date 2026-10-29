"""
Haq Setu - STT decoder adapter.
Multi-backend registry behind the identical audio_to_segments(audio, lang) contract.
Returns list[{speaker?, text}] or raises SabhaSttUnavailable. Never fabricates.

Backends (HAQ_STT_BACKEND):
  none        -> abstain
  cmd         -> run HAQ_STT_CMD, audio on stdin, JSON segments on stdout
  whisper_cpp -> run HAQ_WHISPER_BIN (probe whisper-cli/main/whisper)
  vosk        -> run HAQ_VOSK_BIN (probe vosk-run/vosk-transcriber)
  bhashini    -> run HAQ_BHASHINI_BIN (probe bhashini-stt/bhashini)
  auto        -> probe HAQ_AUTO_PROBE names on PATH, pick first present; none -> abstain

This proves dispatch + abstention. Real transcription remains an operator step.
"""
import os, json, shutil, subprocess, tempfile
from sabha.transcribe import SabhaSttUnavailable

_BIN = {
    "whisper_cpp": ("HAQ_WHISPER_BIN", ["whisper-cli", "main", "whisper"]),
    "vosk":        ("HAQ_VOSK_BIN",    ["vosk-run", "vosk-transcriber"]),
    "bhashini":    ("HAQ_BHASHINI_BIN",["bhashini-stt", "bhashini"]),
}

def _timeout():
    return int(os.environ.get("HAQ_STT_TIMEOUT", "120"))

def _which_first(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None

def _norm(segs):
    out = []
    for s in segs:
        if isinstance(s, dict) and "text" in s:
            out.append({"speaker": s.get("speaker"), "text": str(s["text"])})
        elif isinstance(s, str):
            out.append({"speaker": None, "text": s})
    return out

def _run_json(cmd, audio=None):
    try:
        p = subprocess.run(
            cmd,
            input=audio,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_timeout(),
        )
    except FileNotFoundError as e:
        raise SabhaSttUnavailable(f"bin not found: {e}")
    except subprocess.TimeoutExpired:
        raise SabhaSttUnavailable("stt timed out")

    if p.returncode != 0:
        raise SabhaSttUnavailable(
            f"stt exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[:200]}"
        )

    try:
        segs = json.loads(p.stdout.decode("utf-8", "replace"))
    except Exception as e:
        raise SabhaSttUnavailable(f"stt stdout not JSON: {e}")

    if not isinstance(segs, list):
        raise SabhaSttUnavailable("stt must return a JSON list of segments")
    return _norm(segs)

def _whisper(audio, lang):
    exe = os.environ.get("HAQ_WHISPER_BIN") or _which_first(_BIN["whisper_cpp"][1])
    if not exe:
        raise SabhaSttUnavailable("whisper_cpp backend but no binary on PATH")
    model = os.environ.get("HAQ_WHISPER_MODEL", "")
    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "in.bin")
        outp = os.path.join(td, "out")
        open(inp, "wb").write(audio)
        cmd = [exe, "-m", model, "-f", inp, "-oj", "-of", outp]
        if lang:
            cmd += ["-l", lang]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=_timeout())
        except Exception as e:
            raise SabhaSttUnavailable(f"whisper run failed: {e}")
        jp = outp + ".json"
        if not os.path.exists(jp):
            raise SabhaSttUnavailable("whisper produced no .json output")
        try:
            data = json.load(open(jp))
        except Exception as e:
            raise SabhaSttUnavailable(f"whisper .json unreadable: {e}")
        segs = [
            {"speaker": None, "text": s.get("text", "").strip()}
            for s in data.get("transcription", [])
            if s.get("text", "").strip()
        ]
        if not segs:
            raise SabhaSttUnavailable("whisper .json had no text segments")
        return segs

def _simple(env_key, names, audio, lang):
    exe = os.environ.get(env_key) or _which_first(names)
    if not exe:
        raise SabhaSttUnavailable(f"backend needs {env_key} or one of {names} on PATH")
    cmd = [exe] + ([lang] if lang else [])
    return _run_json(cmd, audio=audio)

def audio_to_segments(audio, lang="hi"):
    b = (os.environ.get("HAQ_STT_BACKEND", "none") or "none").strip().lower()

    if b == "none":
        raise SabhaSttUnavailable("HAQ_STT_BACKEND=none; refusing to fabricate a transcript")

    if b == "cmd":
        import shlex
        cmd = os.environ.get("HAQ_STT_CMD", "").strip()
        if not cmd:
            raise SabhaSttUnavailable("cmd backend but HAQ_STT_CMD empty")
        return _run_json(shlex.split(cmd), audio=audio)

    if b == "whisper_cpp":
        return _whisper(audio, lang)

    if b == "vosk":
        return _simple(*_BIN["vosk"], audio, lang)

    if b == "bhashini":
        return _simple(*_BIN["bhashini"], audio, lang)

    if b == "auto":
        probe = [
            p.strip()
            for p in os.environ.get(
                "HAQ_AUTO_PROBE",
                "whisper-cli,main,vosk-run,bhashini-stt",
            ).split(",")
            if p.strip()
        ]
        exe = _which_first(probe)
        if not exe:
            raise SabhaSttUnavailable("auto: no STT binary on PATH (probe=" + ",".join(probe) + ")")
        base = os.path.basename(exe)
        if base in _BIN["whisper_cpp"][1] or "whisper" in base or base == "main":
            return _whisper(audio, lang)
        if base in _BIN["vosk"][1] or "vosk" in base:
            return _simple(*_BIN["vosk"], audio, lang)
        if base in _BIN["bhashini"][1] or "bhashini" in base:
            return _simple(*_BIN["bhashini"], audio, lang)
        return _run_json([exe], audio=audio)

    raise SabhaSttUnavailable(f"unknown HAQ_STT_BACKEND='{b}' (none|cmd|whisper_cpp|vosk|bhashini|auto)")
