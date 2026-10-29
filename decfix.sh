#!/usr/bin/env bash
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true
python - <<'PY'
import pathlib
p=pathlib.Path("sabha/run_decoder_demo.py"); s=p.read_text()
old="json.dumps(FAKE_SEGS)"; new="repr(FAKE_SEGS)"
if new in s and old not in s:
    print("[skip] fixture already fixed")
elif s.count(old)!=1:
    raise SystemExit(f"[ABORT] anchor matched {s.count(old)}x (need 1)")
else:
    p.write_text(s.replace(old,new,1)); print("[ok] fake-stt fixture: json.dumps -> repr (valid Python)")
PY
python -m py_compile sabha/run_decoder_demo.py && echo "[ok] compiles" || { echo "[FAIL]"; exit 1; }
./run_gates.sh
