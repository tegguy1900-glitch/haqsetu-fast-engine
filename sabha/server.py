"""
Haq Setu - Sabha HTTP service (Pillar 2 capture+decision seam), port 8020.
Stdlib only. Launch:  python -m sabha.server   (from project root)
Privacy model: raw audio lives ONLY in this process's RAM (_STAGE), is hashed
onto the chain (digest only), and is WIPED on successful transcription. A TTL
sweeper guarantees eventual deletion if a meeting is recorded but never
transcribed. Nothing audio-related ever hits disk or the ledger payload.
Routes:
  GET  /health     -> {ok, chain_len, pending_acks, staged, stt_backend}
  POST /record     -> {gp,date,chunk_index,audio_b64_chunk}
                      stages bytes in RAM, emits sabha_chunk_hashed (digest only),
                      returns {seq,chunk_hash,bytes,stage_token}
  POST /transcribe -> Path1 {gp,date,segments:[...]}  -> {minutes}      (no STT)
                      Path2 {gp,date,lang?}           -> {minutes,segments_used}
                      uses staged audio + HAQ_STT_BACKEND; abstains (503) if
                      unconfigured; 400 if no staged audio. Wipes stage on success.
  POST /sign       -> {minutes,signed,signer_role,refuse_reason,open_civic}
All writes go through core.event_bus (ONE ledger); PII guard active everywhere.
"""
import os, json, base64, hashlib, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import event_bus
from ledger import chain as _chain
from sabha import compressor, push_sdm, transcribe

PORT = int(os.environ.get("HAQ_SABHA_PORT", "8020"))
HOST = os.environ.get("HAQ_SABHA_HOST", "127.0.0.1")   # 0.0.0.0 only behind booth LAN
SWEEP_SECONDS = int(os.environ.get("HAQ_STAGE_TTL", "900"))

# ---- transient in-memory audio stage (never disk, never chain) ----
_STAGE = {}      # (gp,date,idx) -> bytes
_TS = {}         # (gp,date,idx) -> last-touch epoch
_LOCK = threading.Lock()

def _stage_put(gp, date, idx, raw):
    with _LOCK:
        _STAGE[(gp, date, idx)] = raw
        _TS[(gp, date, idx)] = time.time()

def _stage_gather(gp, date):
    with _LOCK:
        idxs = sorted(k[2] for k in _STAGE if k[0] == gp and k[1] == date)
        if not idxs:
            return None, []
        buf = b"".join(_STAGE[(gp, date, i)] for i in idxs)
        return buf, idxs

def _stage_wipe(gp, date):
    with _LOCK:
        for k in [k for k in _STAGE if k[0] == gp and k[1] == date]:
            _STAGE.pop(k, None); _TS.pop(k, None)

def _stage_count():
    with _LOCK:
        return len(_STAGE)

def _sweep_loop():
    while True:
        time.sleep(30)
        cut = time.time() - SWEEP_SECONDS
        with _LOCK:
            for k in [k for k, t in _TS.items() if t < cut]:
                _STAGE.pop(k, None); _TS.pop(k, None)

# ---- http plumbing (+CORS so recorder.html on a static port can call us) ----
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
        if self.path == "/health":
            try:
                event_bus.init()
                ok, _, _ = event_bus.verify()
                _send(self, 200, {"ok": ok, "chain_len": len(_chain.get_chain()),
                                  "pending_acks": len(push_sdm.pending_acks()),
                                  "staged": _stage_count(),
                                  "stt_backend": transcribe.backend()})
            except Exception as e:
                _send(self, 500, {"error": f"ledger init failed: {e}"})
        else:
            _send(self, 404, {"error": "not found"})

    def do_POST(self):
        try:
            event_bus.init()
        except Exception as e:
            _send(self, 500, {"error": f"ledger init failed: {e}"}); return
        try:
            data = _read_json(self)
        except Exception as e:
            _send(self, 400, {"error": f"bad json: {e}"}); return

        if self.path == "/record":
            gp = data.get("gp", "GP-UNKNOWN")
            date = data.get("date") or time.strftime("%Y-%m-%d")
            try:
                idx = int(data.get("chunk_index", 0))
            except Exception:
                _send(self, 400, {"error": "chunk_index must be int"}); return
            try:
                raw = base64.b64decode(data.get("audio_b64_chunk", ""))
            except Exception:
                _send(self, 400, {"error": "audio_b64_chunk not valid base64"}); return
            chash = hashlib.sha256(raw).hexdigest()
            case_id = f"SABHA-{gp}-{date}"
            ev = event_bus.emit("mitra", case_id, "sabha_chunk_hashed",
                                {"chunk_index": idx, "chunk_hash": chash,
                                 "byte_length": len(raw)})
            _stage_put(gp, date, idx, raw)   # RAM only
            _send(self, 200, {"seq": ev["seq"], "chunk_hash": chash,
                              "bytes": len(raw), "stage_token": f"{gp}|{date}|{idx}"})

        elif self.path == "/transcribe":
            gp = data.get("gp", "GP-UNKNOWN")
            date = data.get("date") or time.strftime("%Y-%m-%d")
            # Path 1: caller already has segments (test / pre-transcribed) -> no STT, no stage touch
            if isinstance(data.get("segments"), list):
                minutes = compressor.compress(data["segments"], gp=gp, date=date)
                _send(self, 200, {"minutes": minutes, "via": "segments"}); return
            # Path 2: real audio seam -> staged bytes -> external decoder -> compress -> wipe
            buf, idxs = _stage_gather(gp, date)
            if buf is None:
                _send(self, 400, {"error": "no staged audio for gp/date; call /record first"}); return
            lang = data.get("lang") or os.environ.get("HAQ_LANG", "hi")
            try:
                engine = (os.environ.get("HAQ_STT_ENGINE", "transcribe") or "transcribe").strip().lower()
                if engine == "decoder":
                    from sabha import decoder as _dec
                    segs = _dec.audio_to_segments(buf, lang)
                else:
                    segs = transcribe.audio_to_segments(buf, lang)
            except transcribe.SabhaSttUnavailable as e:
                # abstain: retain stage for retry within TTL (operator may fix config);
                # the sweeper is the hard backstop. We never fabricate.
                _send(self, 503, {"abstain": True, "reason": str(e)}); return
            except Exception as e:
                _send(self, 500, {"error": f"stt crashed: {e}"}); return
            _stage_wipe(gp, date)            # success -> bytes gone from RAM
            minutes = compressor.compress(segs, gp=gp, date=date)
            _send(self, 200, {"minutes": minutes, "via": "staged_audio",
                              "segments_used": len(segs)})

        elif self.path == "/sign":
            minutes = data.get("minutes")
            if not isinstance(minutes, dict) or "gp" not in minutes:
                _send(self, 400, {"error": "minutes object required (call /transcribe first)"}); return
            res = push_sdm.push(minutes,
                                signed=bool(data.get("signed", True)),
                                signer_role=data.get("signer_role", "sarpanch"),
                                refuse_reason=data.get("refuse_reason"),
                                open_civic_from_grievances=bool(data.get("open_civic", False)))
            _send(self, 200, {"seq": res["event"]["seq"], "minutes_hash": res["minutes_hash"],
                              "civic_cases_opened": res["civic_cases_opened"]})
        else:
            _send(self, 404, {"error": "not found"})

def main():
    event_bus.init()
    threading.Thread(target=_sweep_loop, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[sabha] http://{HOST}:{PORT}  chain={os.environ.get('HAQ_CHAIN','ledger/chain.jsonl')}  "
          f"sdm={os.environ.get('SDM_DB','sdm/sdm.db')}  stt={transcribe.backend()}  ttl={SWEEP_SECONDS}s")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
