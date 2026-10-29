"""Village node proof w/ REAL brain. Run: python -m core.run_village_demo (sandboxed).
Tolerant: every HTTP call is wrapped so a 500 (handler guard) or a disconnect becomes a
printed FAIL line carrying the server traceback, NOT an abort -> we see ALL results and
the exact server error. HAQ_DEBUG=1 so the 500 body includes the full traceback."""
import os, sys, json, time, base64, socket, threading, sqlite3, tempfile, subprocess, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
class _Mock(BaseHTTPRequestHandler):
    down = True; lock = threading.Lock()
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        with _Mock.lock: d = _Mock.down
        code = 503 if d else 200
        self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()
def _fp():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
def _wait(port, path="/health", to=10.0):
    t0 = time.time()
    while time.time() - t0 < to:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if path != "/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")
def _p(port, path, obj):
    """Tolerant POST: returns dict always; on HTTPError returns the parsed body+_status;
    on connect/drop returns {_status:0,error:repr}. Never raises -> demo continues."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: b = json.loads(e.read())
        except Exception: b = {"error": str(e)}
        b["_status"] = e.code; return b
    except Exception as e:
        return {"_status": 0, "error": repr(e)}
def _tb(v):
    """Render a server 500's traceback (or a drop) compactly for a FAIL line."""
    if v.get("_status") == 500:
        return f"SERVER-ERR {v.get('error')}: {(v.get('tb') or '').strip().splitlines()[-1] if v.get('tb') else ''}"
    if v.get("_status") == 0:
        return f"CONN-DROP {v.get('error')}"
    return ""
def _spawn(d, block=None, brain="real"):
    env = dict(os.environ)
    env.update({"HAQ_CHAIN": f"{d}/chain.jsonl", "HAQ_VAULT": f"{d}/vault.jsonl", "HAQ_KEYS": f"{d}/keys",
                "HAQ_VAULT_KEY": f"{d}/pii.key", "SDM_DB": f"{d}/sdm.db", "HAQ_OUTBOX": f"{d}/outbox.db",
                "HAQ_VILLAGE_PORT": str(_fp()), "HAQ_BRAIN": brain, "HAQ_DEBUG": "1"})
    if block: env["HAQ_BLOCK_URL"] = block
    else: env.pop("HAQ_BLOCK_URL", None)
    p = subprocess.Popen([sys.executable, "-m", "village.server"], env=env)
    return p, int(env["HAQ_VILLAGE_PORT"])
def phase_a():
    print("\n##### PHASE A : REAL brain over HTTP (uplink toggle) #####")
    d = tempfile.mkdtemp(prefix="haqvil_a_"); _Mock.down = True
    fp = _fp(); srv = HTTPServer(("127.0.0.1", fp), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p, port = _spawn(d, block=f"http://127.0.0.1:{fp}/sync", brain="real")
    try:
        h = _wait(port)
        chk("A village up, brain=real, uplink set", h.get("ok") is True and h.get("brain") == "real" and h.get("uplink_configured") is True, str(h))
        chk("A seams named (match_fn/extract)", h.get("match_seam") == "match_fn" and h.get("fact_seam") == "extract", str({k: h.get(k) for k in ('match_seam','fact_seam')}))
        v = _p(port, "/voice", {"raw_text": "Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai",
                                "pii_fields": {"name": "Lakshmi Bai", "phone": "9900112233"}})
        chk("A real /voice matched (conf>0.6)", v.get("decision") == "matched" and (v.get("confidence") or 0) > 0.6, _tb(v) or str(v.get("confidence")))
        chk("A matched a widow + old-age scheme (real catalog ids)", any("widow" in s for s in v.get("schemes", [])) and any("age" in s for s in v.get("schemes", [])), _tb(v) or str(v.get("schemes")))
        chk("A receipt issued", str(v.get("receipt_id", "")).startswith("HR-"), v.get("receipt_id"))
        chk("A proof_trace present", bool(v.get("proof_trace")), _tb(v))
        v3 = _p(port, "/voice", {"raw_text": "hello there nothing relevant at all"})
        chk("A garbage /voice ABSTAINED (not denied)", v3.get("decision") == "abstained", _tb(v3) or str(v3.get("reason")))
        c = _p(port, "/civic", {"category": "handpump", "ward": 4,
            "photo_b64": base64.b64encode(b"BROKEN-PUMP-PHOTO-BYTES").decode(),
            "pii_fields": {"name": "Sita", "phone": "9999888877"}})
        chk("A civic photo hashed (64 hex)", c.get("photo_hash") and len(c["photo_hash"]) == 64, _tb(c) or str(c.get("photo_hash"))[:12])
        s1 = _p(port, "/sync", {})
        chk("A sync#1 (down) queued, acked none", bool(s1.get("still_pending")) and not s1.get("acked"), _tb(s1) or str({k: s1.get(k) for k in ('acked','still_pending','dead')}))
        with _Mock.lock: _Mock.down = False
        s2 = _p(port, "/sync", {})
        chk("A sync#2 (up) acked queued", bool(s2.get("acked")) and not s2.get("still_pending"), _tb(s2) or str({k: s2.get(k) for k in ('acked','still_pending','dead')}))
        cc = sqlite3.connect(f"{d}/chain.db")
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events"))
        cids = [r[0] for r in cc.execute("SELECT case_id FROM events")]; cc.close()
        chk("A chain NO raw PII names", all(x not in blob for x in ("Lakshmi","Sita")))
        chk("A chain NO raw phone digits", all(x not in blob for x in ("9900112233","9999888877")))
        chk("A chain NO photo bytes", "BROKEN-PUMP-PHOTO-BYTES" not in blob)
        chk("A chain DOES carry photo HASH", bool(c.get("photo_hash")) and c["photo_hash"] in blob)
        chk("A civic case_id on chain (COLUMN)", c.get("case_id") in cids, str(cids))
    finally:
        p.terminate(); p.wait(timeout=5); srv.shutdown()
def phase_b():
    print("\n##### PHASE B : NO uplink (offline booth local-durable) #####")
    d = tempfile.mkdtemp(prefix="haqvil_b_"); p, port = _spawn(d, block=None, brain="real")
    try:
        h = _wait(port)
        chk("B village up + uplink NONE", h.get("ok") is True and h.get("uplink_configured") is False, str(h))
        c = _p(port, "/civic", {"category": "drain", "ward": 3, "pii_fields": {"name": "Ravi", "phone": "9700001111"}})
        chk("B civic accepted + local seq", c.get("seq") is not None and c.get("case_id"), _tb(c) or str(c))
        st = _wait(port, "/status")
        chk("B civic OPEN in /status (SLA tracked offline)", c.get("case_id") in st.get("open_civic", []), str(st.get("open_civic")))
        ob = _wait(port, "/health").get("outbox", {})
        chk("B outbox total==0 (not dead-lettered w/o uplink)", ob.get("total", -1) == 0, str(ob))
        cc = sqlite3.connect(f"{d}/chain.db")
        cids = [r[0] for r in cc.execute("SELECT case_id FROM events")]
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events")); cc.close()
        chk("B local chain durable (case_id COLUMN)", c.get("case_id") in cids, str(cids))
        chk("B local chain NO raw PII", "Ravi" not in blob and "9700001111" not in blob)
    finally:
        p.terminate(); p.wait(timeout=5)
def main():
    print("##### VILLAGE NODE - REAL PILLAR-1 BRAIN (tolerant) #####")
    phase_a(); phase_b()
    print("\n[RESULT]", "VILLAGE REAL-BRAIN GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
