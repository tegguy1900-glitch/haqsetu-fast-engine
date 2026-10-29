"""STT decoder adapter proof (dispatch + abstention; no real model faked)."""
import os, sys, json, stat, tempfile, pathlib
from sabha import decoder
from sabha.transcribe import SabhaSttUnavailable

FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c:
        FAIL.append(n)

FAKE_SEGS = [
    {"speaker": None, "text": "The handpump in Ward 9 is broken, no water."},
    {"speaker": "Secretary", "text": "I will repair the road by Monday."},
]

def _mkbin(d, name, body):
    p = pathlib.Path(d) / name
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)

def main():
    print("##### STT DECODER ADAPTER (multi-backend behind identical contract) #####")
    d = tempfile.mkdtemp(prefix="haqdec_")

    fake = _mkbin(d, "fake_stt",
        "#!/usr/bin/env python3\nimport sys,json\nsys.stdin.buffer.read()\nprint(json.dumps(%s))\n" % repr(FAKE_SEGS))
    bad = _mkbin(d, "fake_bad",
        "#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read()\nprint('not json at all')\n")

    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

    os.environ["HAQ_STT_BACKEND"] = "cmd"
    os.environ["HAQ_STT_CMD"] = fake
    segs = decoder.audio_to_segments(b"AUDIO", "hi")
    chk("cmd->fake returns 2 segments", len(segs) == 2 and all("text" in s for s in segs), str(segs))
    chk("cmd->fake preserves speaker ROLE", segs[1]["speaker"] == "Secretary", str(segs[1]))

    os.environ["HAQ_STT_BACKEND"] = "auto"
    os.environ["HAQ_AUTO_PROBE"] = "fake_stt"
    segs2 = decoder.audio_to_segments(b"AUDIO", "hi")
    chk("auto->probe picks the available fake", len(segs2) == 2, str(segs2))

    os.environ["HAQ_STT_BACKEND"] = "none"
    try:
        decoder.audio_to_segments(b"AUDIO", "hi")
        chk("none abstains", False, "FABRICATED a transcript!")
    except SabhaSttUnavailable as e:
        chk("none abstains (no fabrication)", True, str(e)[:55])

    os.environ["HAQ_STT_BACKEND"] = "auto"
    os.environ["HAQ_AUTO_PROBE"] = "definitely_missing_xyz"
    try:
        decoder.audio_to_segments(b"AUDIO", "hi")
        chk("auto-missing abstains", False, "FABRICATED!")
    except SabhaSttUnavailable as e:
        chk("auto-missing abstains", True, str(e)[:60])

    os.environ["HAQ_STT_BACKEND"] = "cmd"
    os.environ["HAQ_STT_CMD"] = bad
    try:
        decoder.audio_to_segments(b"AUDIO", "hi")
        chk("garbage-bin abstains", False, "ACCEPTED junk as segments!")
    except SabhaSttUnavailable as e:
        chk("garbage-bin abstains", True, str(e)[:60])

    print("\n[RESULT]", "DECODER ADAPTER GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)

if __name__ == "__main__":
    main()
