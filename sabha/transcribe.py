"""
Haq Setu - Sabha audio -> segments seam (Pillar 2 capture, v1).
NEVER fabricates a transcript. Backends:
  none (default) -> abstain (SabhaSttUnavailable). No guessing from silence.
  cmd            -> run HAQ_STT_CMD, feed staged bytes on STDIN, expect a JSON
                    list of {speaker?,text} on STDOUT. This is the honest seam:
                    the booth operator installs whatever STT they trust
                    (whisper.cpp, a `python -m whisper` wrapper, a Bhashini CLI,
                    a Vosk runner) and points HAQ_STT_CMD at it. We orchestrate
                    bytes->cmd->segments->compress->wipe; we do not pretend to
                    know your decoder's internals.
Diarization note: a single mic in a noisy Sabha can't reliably separate voices.
That's OK - compressor v2 recovers the owner ROLE from text cues, so commitments
survive even with speaker=None. Speaker labels here are ROLES only, never names.
"""
import os, json, shlex, subprocess

class SabhaSttUnavailable(Exception):
    """Raised instead of inventing text. Caller must surface, never swallow."""

def backend():
    return (os.environ.get("HAQ_STT_BACKEND", "none") or "none").strip().lower()

def audio_to_segments(audio: bytes, lang: str = "hi"):
    b = backend()
    if b == "none":
        raise SabhaSttUnavailable(
            "no STT backend configured (HAQ_STT_BACKEND=none); refusing to fabricate "
            "a transcript. Set HAQ_STT_BACKEND=cmd + HAQ_STT_CMD, or POST /transcribe "
            "with 'segments' directly.")
    if b == "cmd":
        cmd = os.environ.get("HAQ_STT_CMD", "").strip()
        if not cmd:
            raise SabhaSttUnavailable("HAQ_STT_BACKEND=cmd but HAQ_STT_CMD is empty")
        try:
            p = subprocess.run(
                shlex.split(cmd), input=audio,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=int(os.environ.get("HAQ_STT_TIMEOUT", "120")))
        except FileNotFoundError as e:
            raise SabhaSttUnavailable(f"stt cmd not found: {e}")
        except subprocess.TimeoutExpired:
            raise SabhaSttUnavailable("stt cmd timed out")
        if p.returncode != 0:
            raise SabhaSttUnavailable(
                f"stt cmd exit {p.returncode}: "
                f"{p.stderr.decode('utf-8','replace')[:300]}")
        try:
            segs = json.loads(p.stdout.decode("utf-8", "replace"))
        except Exception as e:
            raise SabhaSttUnavailable(f"stt cmd stdout is not JSON: {e}")
        if not isinstance(segs, list):
            raise SabhaSttUnavailable("stt cmd must return a JSON list of segments")
        out = []
        for s in segs:
            if isinstance(s, dict) and "text" in s:
                out.append({"speaker": s.get("speaker"), "text": str(s["text"])})
            elif isinstance(s, str):
                out.append({"speaker": None, "text": s})
        return out
    raise SabhaSttUnavailable(f"unknown HAQ_STT_BACKEND='{b}' (use none|cmd)")
