#!/usr/bin/env bash
# Haq Setu continue/repair: fixes double-patched village/server.py and lands bricks 2-4 safely.
# Run: cd ~/Downloads/project1 && bash continue.sh
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

echo "########## PRE-REPAIR: D1/D2a/D2b/D4 idempotent self-heal ##########"
python - <<'PYEOF'
import pathlib, re, sys

def replace_func(source, func_name, new_code):
    lines = source.split("\n")
    start = None
    pat = re.compile(rf"^def {re.escape(func_name)}\(")
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i
            break
    if start is None:
        raise SystemExit(f"[ABORT] def {func_name}( not found")
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line and not line[0].isspace() and not line.startswith("#") and not line.startswith("@"):
            break
        end += 1
    return "\n".join(lines[:start]) + "\n" + new_code + "\n" + "\n".join(lines[end:])

def patch_line(fname, anchor, repl, tag):
    p = pathlib.Path(fname)
    if not p.exists():
        raise SystemExit(f"[ABORT] {fname} missing [{tag}]")
    lines = p.read_text().splitlines(keepends=True)
    hits = [i for i, l in enumerate(lines) if anchor in l]
    if len(hits) != 1:
        raise SystemExit(f"[ABORT] {fname}: {anchor!r} matched {len(hits)}x (need 1) [{tag}]")
    i = hits[0]
    if isinstance(repl, list):
        lines[i:i+1] = [r if r.endswith("\n") else r + "\n" for r in repl]
    else:
        lines[i] = repl if repl.endswith("\n") else repl + "\n"
    p.write_text("".join(lines))
    print(f"  [ok] {fname} :: {tag}")

# D1: chain.py opaque-token exemption
cp = pathlib.Path("ledger/chain.py")
src = cp.read_text()
if "_OPAQUE_VALUE_KEYS" in src:
    print("  [skip] D1 already applied")
else:
    new = '''_OPAQUE_VALUE_KEYS = {
    "pii_ref","photo_hash","minutes_hash","chunk_hash","evidence_hash",
    "commitment_id","opened_by_minutes",
}
def _scan_pii(obj, path="payload"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).strip().lower()
            if kl in _FORBIDDEN_KEYS:
                raise PiiLeakError(f"Forbidden PII key '{k}' at {path}")
            if kl in _OPAQUE_VALUE_KEYS:
                continue
            _scan_pii(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_pii(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if _AADHAAR_RE.search(obj): raise PiiLeakError(f"Aadhaar-like 12-digit number at {path}")
        if _PHONE_RE.search(obj):   raise PiiLeakError(f"Phone-like 10-digit number at {path}")'''
    cp.write_text(replace_func(src, "_scan_pii", new))
    print("  [ok] ledger/chain.py :: D1 _scan_pii opaque exemption")

# D2a: outbox.pending(force)
op = pathlib.Path("core/outbox.py")
src = op.read_text()
if "def pending(now=None, force=False):" in src:
    print("  [skip] D2a already applied")
else:
    new = '''def pending(now=None, force=False):
    now = now if now is not None else time.time()
    with _conn() as c:
        if force:
            return c.execute(
                "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
                " WHERE status='pending' ORDER BY id").fetchall()
        return c.execute(
            "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
            " WHERE status='pending' AND next_try<=? ORDER BY id", (now,)).fetchall()'''
    op.write_text(replace_func(src, "pending", new))
    print("  [ok] core/outbox.py :: D2a pending(force)")

# D2b: outbox.flush_once(force)
src = op.read_text()
if "def flush_once(now=None, timeout=3, max_attempts=5, force=False):" in src and "pending(now, force=force)" in src:
    print("  [skip] D2b already applied")
else:
    if "def flush_once(now=None, timeout=3, max_attempts=5, force=False):" not in src:
        patch_line("core/outbox.py",
            "def flush_once(now=None, timeout=3, max_attempts=5):",
            "def flush_once(now=None, timeout=3, max_attempts=5, force=False):",
            "D2b flush_once sig")
    src = op.read_text()
    if "pending(now, force=force)" not in src:
        patch_line("core/outbox.py",
            "in pending(now):",
            "in pending(now, force=force):",
            "D2b flush_once call")

# D4: xproc stale assert
xp = pathlib.Path("core/run_xproc_proof.py")
src = xp.read_text()
if "STILL-unaudited sdm_node" in src:
    print("  [skip] D4 already applied")
elif "did NOT spawn legacy village/sdm_node" in src:
    patch_line("core/run_xproc_proof.py",
        "did NOT spawn legacy village/sdm_node",
        [
            '    chk("supervisor did NOT spawn the STILL-unaudited sdm_node", "sdm_node" not in spawned, str(spawned))',
            '    chk("supervisor DID spawn the now-audited village", "village" in spawned, str(spawned))',
        ],
        "D4 xproc assert refresh")
else:
    print("  [warn] D4 anchor not found; assuming already refreshed or file drifted")

print("[pre-repair] done")
PYEOF

RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[stop] pre-repair rc=$RC"
  exit "$RC"
fi

echo
echo "########## BRICK 2: core/backfill.py ##########"
cat > core/backfill.py <<'PYEOF'
"""
Haq Setu - Backfill Sweep.
Propagates local-only history once an uplink is configured.
Events created while HAQ_BLOCK_URL was unset live only on the local chain.
sweep() scans the chain for distinct case_ids carrying a PROPAGATABLE event that
has no outbox row yet, and enqueues a minimal envelope built from the CHAIN
payload. The chain payload is PII-clean by construction (ledger guard), so
forwarding it cannot re-introduce identity. The vault is never read here.
Idempotent by key (outbox.enqueue dedups), so re-running is free.
"""
import os, sys, threading
from core import event_bus, outbox
from ledger import chain as _chain

PROPAGATABLE = {
    "civic_intake",
    "entitlement_petition_issued",
    "sabha_signed",
    "sla_breach",
    "official_rejection",
}
_COPY_FIELDS = (
    "category", "ward", "schemes", "confidence", "receipt_id",
    "minutes_hash", "reason_code", "escalated_to", "mode",
)

def sweep(block_url, event_types=None):
    if not event_bus.is_ready():
        event_bus.init()
    types = set(event_types) if event_types else PROPAGATABLE
    seen, enqueued = set(), []
    for ev in _chain.get_chain():
        if ev["event_type"] not in types:
            continue
        cid = ev["case_id"]
        if cid in seen:
            continue
        seen.add(cid)
        key = f"DEL-{cid}"
        if outbox.has_key(key):
            continue
        env = {"kind": ev["event_type"], "case_id": cid, "seq": ev["seq"]}
        pl = ev.get("payload", {})
        for f in _COPY_FIELDS:
            if f in pl:
                env[f] = pl[f]
        outbox.enqueue(key, block_url, env)
        enqueued.append(cid)
    return {"enqueued": enqueued, "scanned": len(seen)}

def loop(block_url, interval=300, stop=None, log=print, event_types=None):
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            r = sweep(block_url, event_types=event_types)
            if r["enqueued"]:
                log(f"[backfill] enqueued {len(r['enqueued'])} local-only case(s)")
        except Exception as e:
            log(f"[backfill] sweep error (kept looping): {e}")
        stop.wait(interval)

if __name__ == "__main__":
    event_bus.init()
    url = (os.environ.get("HAQ_BLOCK_URL", "") or "").strip()
    if not url:
        print("[backfill] no HAQ_BLOCK_URL set; nothing to propagate (offline booth)")
        sys.exit(0)
    iv = int(os.environ.get("HAQ_BACKFILL_INTERVAL", "300"))
    print(f"[backfill] looping every {iv}s -> {url}")
    loop(url, interval=iv)
PYEOF

echo
echo "########## BRICK 3: sabha/decoder.py ##########"
cat > sabha/decoder.py <<'PYEOF'
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
PYEOF

echo
echo "########## ADDITIVE PRODUCT PATCHES ##########"
python - <<'PYEOF'
import pathlib

def patch_line(fname, anchor, repl, tag):
    p = pathlib.Path(fname)
    if not p.exists():
        raise SystemExit(f"[ABORT] {fname} missing [{tag}]")
    lines = p.read_text().splitlines(keepends=True)
    hits = [i for i, l in enumerate(lines) if anchor in l]
    if len(hits) != 1:
        raise SystemExit(f"[ABORT] {fname}: {anchor!r} matched {len(hits)}x (need 1) [{tag}]")
    i = hits[0]
    if isinstance(repl, list):
        lines[i:i+1] = [r if r.endswith("\n") else r + "\n" for r in repl]
    else:
        lines[i] = repl if repl.endswith("\n") else repl + "\n"
    p.write_text("".join(lines))
    print(f"  [ok] {fname} :: {tag}")

# outbox.has_key for backfill idempotency
op = pathlib.Path("core/outbox.py")
src = op.read_text()
if "def has_key" in src:
    print("  [skip] outbox.has_key already present")
else:
    patch_line("core/outbox.py",
        "def stats():",
        [
            "def has_key(key):",
            "    with _conn() as c:",
            '        return c.execute("SELECT 1 FROM deliveries WHERE key=? LIMIT 1", (key,)).fetchone() is not None',
            "",
            "def stats():",
        ],
        "outbox.has_key")

# sabha decoder engine switch
sp = pathlib.Path("sabha/server.py")
src = sp.read_text()
if "HAQ_STT_ENGINE" in src:
    print("  [skip] sabha decoder engine switch already present")
else:
    patch_line("sabha/server.py",
        "segs = transcribe.audio_to_segments(buf, lang)",
        [
            '                engine = (os.environ.get("HAQ_STT_ENGINE", "transcribe") or "transcribe").strip().lower()',
            '                if engine == "decoder":',
            '                    from sabha import decoder as _dec',
            '                    segs = _dec.audio_to_segments(buf, lang)',
            '                else:',
            '                    segs = transcribe.audio_to_segments(buf, lang)',
        ],
        "sabha decoder engine switch")

print("[additive-patch] done")
PYEOF

RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[stop] additive patch rc=$RC"
  exit "$RC"
fi

echo
echo "########## REWRITE village/server.py (canonical, clean, with backfill) ##########"
cat > village/server.py <<'PYEOF'
"""
Haq Setu - Village Booth Node (port 8000). AUDITED replacement for legacy server.py.
Stdlib only. Launch: python -m village.server

This is the real producer for the offline outbox:
  - every citizen action writes the local signed ledger SYNCHRONOUSLY
  - if HAQ_BLOCK_URL is configured, it also enqueues upward propagation
  - if no uplink is configured, the event is still local-durable and SLA-tracked
  - PII goes to the vault; the chain never sees raw identity
  - photo bytes are hashed; only the digest lands on-chain

Pillar-1 brains are SEAMS with labeled stand-ins:
  MATCH_FN -> bind engine/rules.py match()
  FACT_FN  -> bind your regex voice->facts extractor

Routes:
  GET  /health
  GET  /status
  POST /voice
  POST /civic
  POST /sync
  POST /backfill
"""
import os, json, base64, hashlib, time, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import event_bus, entitlement as ent, sla_clock as clock, outbox
from ledger import chain as _chain
from core.sla_clock import ISSUE_CLOCKS, DEFAULT_HOURS

PORT = int(os.environ.get("HAQ_VILLAGE_PORT", "8000"))
HOST = os.environ.get("HAQ_VILLAGE_HOST", "127.0.0.1")
BLOCK_URL = (os.environ.get("HAQ_BLOCK_URL", "") or "").strip()

# ---- SEAM 1: fact extractor (stand-in for your regex voice->facts) ----
_AGE = re.compile(r"\b(\d{2})\b")

def reference_fact_extract(raw_text, lang=None):
    """STAND-IN. Replace by binding FACT_FN to your real voice->facts extractor."""
    f = {}
    t = (raw_text or "").lower()
    m = _AGE.search(t)
    if m and 18 <= int(m.group(1)) <= 120:
        f["age"] = int(m.group(1))
    if any(k in t for k in ("widow", "vidhwa", "parinemta", "parinamita")):
        f["is_widow"] = True
    if any(k in t for k in ("pucca", "pakka", "pakke", "concrete")):
        f["has_pucca_house"] = True
    elif any(k in t for k in ("kacha", "kachcha", "kutcha", "mud", "kutchi", "jhoppi")):
        f["has_pucca_house"] = False
    return f

# ---- SEAM 2: rule brain (stand-in for engine/rules.py match) ----
MATCH_FN = ent.reference_match_fn
FACT_FN = reference_fact_extract

def _uplink_enqueue(case_id, payload):
    if not BLOCK_URL:
        return None
    return outbox.enqueue(f"DEL-{case_id}", BLOCK_URL, payload)

def _send(h, code, obj):
    body = json.dumps(obj, sort_keys=True).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    h.end_headers()
    h.wfile.write(body)

def _read_json(h):
    n = int(h.headers.get("Content-Length", "0") or 0)
    raw = h.rfile.read(n) if n else b""
    return json.loads(raw) if raw else {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_OPTIONS(self):
        _send(self, 204, {})

    def do_GET(self):
        try:
            event_bus.init()
        except Exception as e:
            _send(self, 500, {"error": f"ledger init failed: {e}"})
            return

        if self.path == "/health":
            ok, _, _ = event_bus.verify()
            _send(self, 200, {
                "ok": ok,
                "chain_len": len(_chain.get_chain()),
                "outbox": outbox.stats(),
                "match_seam": getattr(MATCH_FN, "__name__", "?"),
                "fact_seam": getattr(FACT_FN, "__name__", "?"),
                "uplink_configured": bool(BLOCK_URL),
            })
        elif self.path == "/status":
            _send(self, 200, clock.status())
        else:
            _send(self, 404, {"error": "not found"})

    def do_POST(self):
        try:
            event_bus.init()
        except Exception as e:
            _send(self, 500, {"error": f"ledger init failed: {e}"})
            return

        try:
            data = _read_json(self)
        except Exception as e:
            _send(self, 400, {"error": f"bad json: {e}"})
            return

        if self.path == "/voice":
            facts = data.get("facts")
            if not isinstance(facts, dict):
                raw = data.get("raw_text")
                if raw is None:
                    _send(self, 400, {"error": "provide facts{} or raw_text"})
                    return
                facts = FACT_FN(raw, data.get("lang"))

            res = ent.process_voice(
                data.get("actor_role", "mitra"),
                facts,
                MATCH_FN,
                pii_fields=data.get("pii_fields"),
                case_id=data.get("case_id"),
            )

            if res["decision"] == "matched":
                _uplink_enqueue(res["case_id"], {
                    "kind": "entitlement",
                    "case_id": res["case_id"],
                    "schemes": res["schemes"],
                    "confidence": res["confidence"],
                })

            out = {
                "decision": res["decision"],
                "case_id": res["case_id"],
                "confidence": res.get("confidence"),
            }
            if res["decision"] == "matched":
                out["schemes"] = res["schemes"]
                out["receipt_id"] = f"HR-{res['case_id']}"
                out["proof_trace"] = res["events"][0]["payload"].get("proof_trace")
            else:
                out["reason"] = res.get("reason")

            _send(self, 200, out)

        elif self.path == "/civic":
            cat = data.get("category")
            if not cat:
                _send(self, 400, {"error": "category required"})
                return

            ph, blen = None, 0
            if data.get("photo_b64"):
                try:
                    raw = base64.b64decode(data["photo_b64"])
                except Exception:
                    _send(self, 400, {"error": "photo_b64 not valid base64"})
                    return
                ph, blen = hashlib.sha256(raw).hexdigest(), len(raw)

            case_id = data.get("case_id") or (
                f"HS-{time.strftime('%Y%m%d')}-"
                f"{hashlib.sha256((cat + str(time.time())).encode()).hexdigest()[:6].upper()}"
            )

            ev = event_bus.emit(
                data.get("actor_role", "mitra"),
                case_id,
                "civic_intake",
                {
                    "category": cat,
                    "ward": data.get("ward"),
                    "photo_hash": ph,
                    "byte_length": blen,
                    "gps": data.get("gps"),
                },
                pii_fields=data.get("pii_fields"),
            )

            _uplink_enqueue(case_id, {
                "kind": "civic",
                "case_id": case_id,
                "category": cat,
                "ward": data.get("ward"),
                "photo_hash": ph,
            })

            _send(self, 200, {
                "case_id": case_id,
                "seq": ev["seq"],
                "photo_hash": ph,
                "byte_length": blen,
                "sla_hours": ISSUE_CLOCKS.get(cat, DEFAULT_HOURS),
            })

        elif self.path == "/sync":
            try:
                res = outbox.flush_once(
                    force=True,
                    max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5")),
                )
            except TypeError:
                res = outbox.flush_once(
                    max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5")),
                )
            _send(self, 200, res)

        elif self.path == "/backfill":
            if not BLOCK_URL:
                _send(self, 200, {"enqueued": [], "note": "no uplink configured; nothing to backfill"})
                return
            from core import backfill as _bf
            _send(self, 200, _bf.sweep(BLOCK_URL))

        else:
            _send(self, 404, {"error": "not found"})

def main():
    event_bus.init()

    if BLOCK_URL:
        try:
            from core import backfill as _bf
            r = _bf.sweep(BLOCK_URL)
            if r["enqueued"]:
                print(f"[village] startup backfill enqueued {len(r['enqueued'])} local-only case(s)")
        except Exception as e:
            print(f"[village] startup backfill skipped: {e}")

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(
        f"[village] http://{HOST}:{PORT} "
        f"chain={os.environ.get('HAQ_CHAIN', 'ledger/chain.jsonl')} "
        f"uplink={'SET' if BLOCK_URL else 'NONE(local-only)'} "
        f"match={getattr(MATCH_FN, '__name__', '?')}"
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
PYEOF

python -m py_compile village/server.py && echo "  [ok] village/server.py compiles"

echo
echo "########## BRICK 2 PROOF: core/run_backfill_demo.py ##########"
cat > core/run_backfill_demo.py <<'PYEOF'
"""Backfill sweep proof. Run: python -m core.run_backfill_demo"""
import os, sys, json, threading, sqlite3, socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from core import event_bus, outbox, backfill
from ledger import chain as _chain

FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c:
        FAIL.append(n)

class _Up(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

def _free():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

def main():
    event_bus.init()
    print("##### BACKFILL SWEEP (propagate local-only history once uplink configured) #####")

    event_bus.emit("mitra", "HS-BF-1", "civic_intake", {"category": "handpump", "ward": 4},
                   pii_fields={"name": "Meera", "phone": "9800011122"})
    event_bus.emit("mitra", "HS-BF-2", "entitlement_petition_issued",
                   {"schemes": ["nsap"], "confidence": 0.95, "receipt_id": "HR-HS-BF-2"})
    event_bus.emit("sarpanch", "SABHA-BF", "sabha_signed",
                   {"gp": "GP-BF", "meeting_date": "2026-10-21", "minutes_hash": "b" * 64,
                    "action_items": [], "grievances": []})
    event_bus.emit("mitra", "HS-BF-3", "civic_intake", {"category": "drain", "ward": 3})
    event_bus.emit("mitra", "HS-BF-CHK", "sabha_chunk_hashed",
                   {"chunk_index": 0, "chunk_hash": "c" * 64, "byte_length": 10})

    chk("P1 local-only events written, outbox empty (no uplink)", outbox.stats()["total"] == 0, str(outbox.stats()))

    port = _free()
    srv = HTTPServer(("127.0.0.1", port), _Up)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/sync"

    r = backfill.sweep(url)
    fwd = set(r["enqueued"])
    chk("P2 swept exactly the 4 propagatable cases",
        fwd == {"HS-BF-1", "HS-BF-2", "SABHA-BF", "HS-BF-3"}, str(sorted(fwd)))
    chk("P2 chunk-hash NOT forwarded (local-only evidence)", "HS-BF-CHK" not in fwd)
    chk("P2 outbox now 4 pending", outbox.stats()["pending"] == 4, str(outbox.stats()))

    r2 = backfill.sweep(url)
    chk("P3 re-sweep enqueues 0 (idempotent by key)", r2["enqueued"] == [], str(r2))

    fr = outbox.flush_once(force=True)
    chk("P4 flush acked all 4", len(fr["acked"]) == 4 and outbox.stats()["pending"] == 0, str(outbox.stats()))

    cc = sqlite3.connect(outbox.DB_PATH)
    blobs = "".join(x[0] for x in cc.execute("SELECT payload FROM deliveries"))
    cc.close()
    chk("P5 forwarded envelopes have NO raw PII", "Meera" not in blobs and "9800011122" not in blobs)
    chk("P5 forwarded envelope DOES carry case_id", "HS-BF-1" in blobs)

    srv.shutdown()
    print("\n[RESULT]", "BACKFILL SWEEP GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)

if __name__ == "__main__":
    main()
PYEOF

echo
echo "########## BRICK 3 PROOF: sabha/run_decoder_demo.py ##########"
cat > sabha/run_decoder_demo.py <<'PYEOF'
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
        "#!/usr/bin/env python3\nimport sys,json\nsys.stdin.buffer.read()\nprint(json.dumps(%s))\n" % json.dumps(FAKE_SEGS))
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
PYEOF

echo
echo "########## BRICK 4: booth packaging ##########"
cat > env.example <<'ENVEOF'
# Haq Setu booth environment. Copy to /etc/haqsetu/haqsetu.env and edit, then:
#   systemctl daemon-reload && systemctl enable --now haqsetu haqsetu-backfill
# All persistent state is the SQLite files below -- back THOSE .db files up; the
# ledger is append-only (UPDATE/DELETE physically blocked by triggers), so a backup
# is a true point-in-time copy and a restore is putting the .db files back.

# --- storage (paths frozen at process import; .jsonl suffix -> .db WAL alongside) ---
HAQ_CHAIN=/var/lib/haqsetu/chain.jsonl
HAQ_VAULT=/var/lib/haqsetu/vault.jsonl
HAQ_KEYS=/var/lib/haqsetu/keys
HAQ_VAULT_KEY=/var/lib/haqsetu/keys/pii.key
SDM_DB=/var/lib/haqsetu/sdm.db
HAQ_OUTBOX=/var/lib/haqsetu/outbox.db

# --- service ports (booth LAN) ---
HAQ_VILLAGE_PORT=8000
HAQ_SABHA_PORT=8020
HAQ_SDM_PORT=8110
HAQ_BLOCK_PORT=8100

# --- uplink to the block/SDM node. LEAVE EMPTY for an offline-only booth; the
#     backfill sweep propagates local-only history the moment you set it. ---
HAQ_BLOCK_URL=

# --- STT (Sabha audio -> segments). none=abstain; cmd=HAQ_STT_CMD; auto=probe PATH.
#     HAQ_STT_ENGINE: transcribe (proven default) | decoder (multi-backend adapter).
#     Format note: MediaRecorder yields webm/opus; whisper.cpp wants wav -- transcode
#     or capture PCM at the booth. The adapter passes bytes through untouched. ---
HAQ_STT_BACKEND=none
HAQ_STT_CMD=
HAQ_STT_ENGINE=transcribe
HAQ_AUTO_PROBE=whisper-cli,main,vosk-run,bhashini-stt
HAQ_WHISPER_BIN=
HAQ_WHISPER_MODEL=
HAQ_VOSK_BIN=
HAQ_BHASHINI_BIN=
HAQ_STT_TIMEOUT=120
HAQ_LANG=hi

# --- policy knobs ---
HAQ_SLA_MODE=escalate
HAQ_CONF_THRESHOLD=0.6
HAQ_PETITION_SLA_H=72
HAQ_TICK_INTERVAL=60
HAQ_BACKFILL_INTERVAL=300
HAQ_STAGE_TTL=900
HAQ_SYNC_MAXATT=5
ENVEOF

cat > boot.sh <<'BOOTEOF'
#!/usr/bin/env bash
# Haq Setu booth boot. Usage:
#   bash boot.sh --check   run the full proof gate suite (self-test; no services)
#   bash boot.sh --init    create dirs + initialize the ledger (genesis)
#   bash boot.sh --live    start the 3 audited services + clock/outbox daemons + backfill loop
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
[ -d venv ] && source venv/bin/activate 2>/dev/null || true
ENV_FILE="${HAQSETU_ENV:-$HERE/haqsetu.env}"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }
CMD="${1:---help}"

gate () {
  local label="$1"; shift
  local d
  d="$(mktemp -d /tmp/bootchk_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" \
      python -m "$@" >/dev/null 2>&1
  local rc=$?
  rm -rf "$d"
  printf '  %-22s exit=%s\n' "$label" "$rc"
  echo "$rc"
}

case "$CMD" in
  --check)
    echo "== Haq Setu self-test =="
    bad=0
    for m in core.run_wal_migration core.run_clock_demo core.run_xproc_proof \
             core.run_pillar1_demo core.run_village_demo core.run_backfill_demo \
             sabha.run_sabha sabha.run_decoder_demo sdm.run_dashboard_demo \
             core.run_launcher_demo; do
      r=$(gate "$m" "$m")
      [ "$r" = 0 ] || bad=1
    done
    [ "$bad" = 0 ] && echo "SELF-TEST GREEN" || echo "SELF-TEST RED"
    exit "$bad"
    ;;
  --init)
    mkdir -p ledger keys sdm core
    python -c "from core import event_bus; event_bus.init(); print('[boot] ledger genesis ready')"
    ;;
  --live)
    mkdir -p ledger keys sdm core
    python -c "from core import event_bus; event_bus.init()"
    python -m core.backfill & BF=$!
    python -m launcher --live
    kill "$BF" 2>/dev/null
    ;;
  *)
    echo "usage: bash boot.sh [--check|--init|--live]"
    exit 1
    ;;
esac
BOOTEOF

cat > haqsetu.service <<'UNITEOF'
[Unit]
Description=Haq Setu Gram Sabha governance node (booth: village+sabha+sdm-preview + daemons)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=haqsetu
Group=haqsetu
WorkingDirectory=/opt/haqsetu
EnvironmentFile=/etc/haqsetu/haqsetu.env
ExecStart=/opt/haqsetu/venv/bin/python -m launcher --live
Restart=on-failure
RestartSec=3
StateDirectory=haqsetu
StateDirectoryMode=0750
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNITEOF

cat > haqsetu-backfill.service <<'UNITEOF'
[Unit]
Description=Haq Setu backfill sweep (propagate local-only events once uplink configured)
After=haqsetu.service

[Service]
Type=simple
User=haqsetu
WorkingDirectory=/opt/haqsetu
EnvironmentFile=/etc/haqsetu/haqsetu.env
ExecStart=/opt/haqsetu/venv/bin/python -m core.backfill
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNITEOF

echo "########## PACKAGING LINT ##########"
PKG_OK=1
bash -n boot.sh && echo "  [OK] boot.sh syntax" || { echo "  [FAIL] boot.sh syntax"; PKG_OK=0; }

python - <<'PY' || PKG_OK=0
import re, sys
bad = []
for ln in open("env.example"):
    s = ln.rstrip("\n")
    if not s.strip() or s.lstrip().startswith("#"):
        continue
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", s):
        bad.append(s)
if bad:
    print("  [FAIL] env.example malformed lines:")
    for b in bad:
        print("     ", b)
    sys.exit(1)
print("  [OK] env.example: every assignment line is KEY=VALUE")
PY

python -c "import launcher, village.server, sabha.server, sdm.server, core.backfill, sabha.decoder, core.run_backfill_demo, sabha.run_decoder_demo; print('  [OK] all modules import (incl new backfill + decoder)')" || PKG_OK=0

grep -q 'ExecStart=.*launcher --live' haqsetu.service && \
grep -q 'EnvironmentFile=' haqsetu.service && \
grep -q 'WantedBy=multi-user.target' haqsetu.service && \
echo "  [OK] haqsetu.service: ExecStart->launcher --live, EnvironmentFile, WantedBy present" || \
{ echo "  [FAIL] haqsetu.service lint"; PKG_OK=0; }

grep -q 'ExecStart=.*core.backfill' haqsetu-backfill.service && \
grep -q 'WantedBy=multi-user.target' haqsetu-backfill.service && \
echo "  [OK] haqsetu-backfill.service: ExecStart->core.backfill, WantedBy present" || \
{ echo "  [FAIL] haqsetu-backfill.service lint"; PKG_OK=0; }

echo "  [note] actual 'systemctl daemon-reload && systemctl start' is an operator step on the"
echo "         booth (needs root + the /opt/haqsetu install path); we lint the units, not install."
[ "$PKG_OK" = 1 ] && echo "PACKAGING LINT GREEN" || echo "PACKAGING LINT RED"

echo
echo "########## GATES (10 suites; each in its own fresh sandbox) ##########"
GATES=""
gate2 () {
  local label="$1"; shift
  local d
  d="$(mktemp -d /tmp/b3gate_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 6
  local rc="${PIPESTATUS[0]}"
  printf '>>> %-14s exit=%s\n' "$label" "$rc"
  rm -rf "$d"
  GATES="$GATES $label=$rc"
}

gate2 "wal"        python -m core.run_wal_migration
gate2 "clock"      python -m core.run_clock_demo
gate2 "xproc"      python -m core.run_xproc_proof
gate2 "pillar1"    python -m core.run_pillar1_demo
gate2 "village"    python -m core.run_village_demo
gate2 "backfill"   python -m core.run_backfill_demo
gate2 "sabha"      python -m sabha.run_sabha
gate2 "decoder"    python -m sabha.run_decoder_demo
gate2 "dash"       python -m sdm.run_dashboard_demo
gate2 "launch"     python -m core.run_launcher_demo

echo
echo "########## SUMMARY ##########"
echo "PKG_OK=$PKG_OK"
echo "GATES:$GATES"
allok=$PKG_OK
for kv in $GATES; do
  [ "${kv#*=}" = "0" ] || allok=0
done

if [ "$allok" = 1 ]; then
  echo "ALL GATES GREEN :: village syntax repaired, backfill landed, decoder adapter landed, booth packaging linted, all prior proofs unregressed"
else
  echo "SOME GATE RED :: see exit!=0 / PKG_OK above"
fi
