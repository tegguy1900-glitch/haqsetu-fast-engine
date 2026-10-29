
#!/usr/bin/env bash
# Haq Setu defect fixes (D1-D4). Run:  cd ~/Downloads/project1 && bash fixes.sh
# Parsed from DISK; inline replaces verify-or-abort so a drifted anchor fails LOUD, never no-ops.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

# ===== targeted product+demo patches (each anchor must match exactly once or we abort) =====
python - <<'PY'
import pathlib
def rep(fname, old, new, tag):
    p = pathlib.Path(fname); s = p.read_text()
    if old not in s:
        raise SystemExit(f"[ABORT] anchor NOT found in {fname} ({tag}); on-disk text drifted, not patching blindly.")
    if s.count(old) != 1:
        raise SystemExit(f"[ABORT] anchor appears {s.count(old)}x in {fname} ({tag}); ambiguous, not patching.")
    p.write_text(s.replace(old, new, 1)); print(f"[patch ok] {fname} :: {tag}")

# ---- D1 (product): exempt system opaque tokens from the PII VALUE regexes ----
rep("ledger/chain.py",
'''def _scan_pii(obj, path="payload"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).strip().lower() in _FORBIDDEN_KEYS:
                raise PiiLeakError(f"Forbidden PII key '{k}' at {path}")
            _scan_pii(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_pii(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if _AADHAAR_RE.search(obj): raise PiiLeakError(f"Aadhaar-like 12-digit number at {path}")
        if _PHONE_RE.search(obj):   raise PiiLeakError(f"Phone-like 10-digit number at {path}")''',
'''_OPAQUE_VALUE_KEYS = {
    "pii_ref","photo_hash","minutes_hash","chunk_hash","evidence_hash",
    "commitment_id","opened_by_minutes",
}
def _scan_pii(obj, path="payload"):
    # The value-regexes (aadhaar 12-digit / phone 10-digit) target HUMAN-TYPED free text.
    # System-written opaque tokens (uuid blob_ids, hex digests, hex-derived ids) legitimately
    # contain long decimal runs and would false-positive (~2.8% of uuids, ~19% of 64-hex
    # digests). Every key below is written ONLY by the system, never by user input, so
    # skipping its VALUE leaks nothing; the key-name check above still runs on every key.
    # Fail-closed-safe: a future unlisted token would loudly crash here and get added.
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
        if _PHONE_RE.search(obj):   raise PiiLeakError(f"Phone-like 10-digit number at {path}")''',
"D1 chain._scan_pii opaque-token exemption")

# ---- D2 (product): outbox.pending gains force (ignore next_try) ----
rep("core/outbox.py",
'''def pending(now=None):
    now = now if now is not None else time.time()
    with _conn() as c:
        return c.execute(
            "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
            " WHERE status='pending' AND next_try<=? ORDER BY id", (now,)).fetchall()''',
'''def pending(now=None, force=False):
    now = now if now is not None else time.time()
    with _conn() as c:
        if force:
            return c.execute(
                "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
                " WHERE status='pending' ORDER BY id").fetchall()
        return c.execute(
            "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
            " WHERE status='pending' AND next_try<=? ORDER BY id", (now,)).fetchall()''',
"D2a outbox.pending force")

# ---- D2 (product): outbox.flush_once threads force to pending ----
rep("core/outbox.py",
'''def flush_once(now=None, timeout=3, max_attempts=5):
    """Attempt every due pending delivery. Returns {acked,failed,dead,still_pending}
    as lists of keys. Non-2xx / refused / timeout => failed attempt; after
    max_attempts => status 'dead' (row KEPT, payload intact)."""
    now = now if now is not None else time.time()
    acked, failed, dead, still = [], [], [], []
    for rid, key, url, method, payload, attempts, _st in pending(now):''',
'''def flush_once(now=None, timeout=3, max_attempts=5, force=False):
    """Attempt every due pending delivery. Returns {acked,failed,dead,still_pending}
    as lists of keys. Non-2xx / refused / timeout => failed attempt; after
    max_attempts => status 'dead' (row KEPT, payload intact).
    force=True => ignore next_try backoff and attempt ALL pending now (a manual 'sync'
    tap by the Mitra must retry immediately, not wait out exponential backoff; the
    background flush_loop keeps force=False so it respects backoff)."""
    now = now if now is not None else time.time()
    acked, failed, dead, still = [], [], [], []
    for rid, key, url, method, payload, attempts, _st in pending(now, force=force):''',
"D2b outbox.flush_once force")

# ---- D2 (product): village /sync = manual tap bypasses backoff ----
rep("village/server.py",
'''        elif self.path == "/sync":
            _send(self, 200, outbox.flush_once(max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5"))))''',
'''        elif self.path == "/sync":
            # Manual Mitra tap = retry everything NOW, bypassing the daemon's backoff.
            _send(self, 200, outbox.flush_once(force=True,
                      max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5"))))''',
"D2c village./sync force")

# ---- D4 (demo): xproc stale assert (village is now audited & spawns) ----
rep("core/run_xproc_proof.py",
'''    chk("supervisor did NOT spawn legacy village/sdm_node", not ({"village","sdm_node"} & spawned), str(spawned))''',
'''    chk("supervisor did NOT spawn the STILL-unaudited sdm_node", "sdm_node" not in spawned, str(spawned))
    chk("supervisor DID spawn the now-audited village", "village" in spawned, str(spawned))''',
"D4 xproc village-assert refresh")
print("[inline-patch] all 5 anchors matched exactly once; product+demo patched")
PY

# ===== D2a/D3 (demo): full re-emit of the coupled village demo (toggle mock + column durability) =====
cat > core/run_village_demo.py <<'PYEOF'
"""Village node proof. Run: python -m core.run_village_demo (sandboxed via env by caller)
Phase A (uplink = TOGGLE mock, starts DOWN): voice->receipt+PII-vault, civic->photo-hash,
        sync#1 while DOWN -> every pending attempts once, all 503 -> still_pending, acked NONE;
        flip UP; sync#2 (force) -> acked, none still-pending. garbage-voice -> abstain (no enqueue).
        Chain hygiene: no raw PII/bytes on chain, photo HASH present, civic case_id in COLUMN.
Phase B (NO uplink): civic -> local-durable (case_id COLUMN) + open in /status + outbox total==0.
"""
import os, sys, json, time, base64, socket, threading, urllib.request, urllib.error, subprocess, sqlite3, tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)

class _Mock(BaseHTTPRequestHandler):
    down = True
    lock = threading.Lock()
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        with _Mock.lock: d = _Mock.down
        code = 503 if d else 200
        self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def _wait(port, path="/health", timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if path != "/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")

def _post(port, path, obj):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: b = json.loads(e.read())
        except Exception: b = {"error": str(e)}
        b["_status"] = e.code; return b

def _spawn_village(d, block_url=None):
    env = dict(os.environ)
    env.update({"HAQ_CHAIN": f"{d}/chain.jsonl", "HAQ_VAULT": f"{d}/vault.jsonl",
                "HAQ_KEYS": f"{d}/keys", "HAQ_VAULT_KEY": f"{d}/pii.key",
                "SDM_DB": f"{d}/sdm.db", "HAQ_OUTBOX": f"{d}/outbox.db",
                "HAQ_VILLAGE_PORT": str(_free_port())})
    if block_url: env["HAQ_BLOCK_URL"] = block_url
    else: env.pop("HAQ_BLOCK_URL", None)
    p = subprocess.Popen([sys.executable, "-m", "village.server"], env=env)
    return p, int(env["HAQ_VILLAGE_PORT"])

def phase_a():
    print("\n##### PHASE A : uplink toggle (producer-layer dropout -> queue -> recover) #####")
    d = tempfile.mkdtemp(prefix="haqvil_a_")
    _Mock.down = True
    flap_port = _free_port(); srv = HTTPServer(("127.0.0.1", flap_port), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p, port = _spawn_village(d, block_url=f"http://127.0.0.1:{flap_port}/sync")
    try:
        h = _wait(port)
        chk("A village up + uplink configured", h.get("ok") is True and h.get("uplink_configured") is True, str(h))
        chk("A seams are labeled stand-ins", "reference" in str(h.get("match_seam","")) and "reference" in str(h.get("fact_seam","")), str({k:h.get(k) for k in ('match_seam','fact_seam')}))
        v = _post(port, "/voice", {"facts": {"age": 65, "is_widow": True, "has_pucca_house": False},
                                   "pii_fields": {"name": "Lakshmi Bai", "phone": "9900112233"}})
        chk("A voice matched 3 schemes", v.get("decision") == "matched" and len(v.get("schemes",[])) == 3, str(v.get("schemes")))
        chk("A voice issued receipt", str(v.get("receipt_id","")).startswith("HR-"), v.get("receipt_id"))
        chk("A voice has proof_trace", bool(v.get("proof_trace")))
        v2 = _post(port, "/voice", {"raw_text": "Main 70 saal ki vidhwa hoon, mera kacha ghar hai",
                                    "pii_fields": {"name": "Durga", "phone": "9811122233"}})
        chk("A raw_text -> facts -> matched", v2.get("decision") == "matched" and len(v2.get("schemes",[])) >= 1, str(v2.get("schemes")))
        v3 = _post(port, "/voice", {"raw_text": "hello there nothing relevant"})
        chk("A garbage voice ABSTAINED (not denied)", v3.get("decision") == "abstained", str(v3.get("reason")))
        c = _post(port, "/civic", {"category": "handpump", "ward": 4,
                                   "photo_b64": base64.b64encode(b"BROKEN-PUMP-PHOTO-BYTES").decode(),
                                   "pii_fields": {"name": "Sita", "phone": "9999888877"}})
        chk("A civic photo hashed (64 hex)", c.get("photo_hash") and len(c["photo_hash"]) == 64, str(c.get("photo_hash"))[:12])
        chk("A civic byte_length recorded, bytes not on chain", c.get("byte_length") == len(b"BROKEN-PUMP-PHOTO-BYTES"))
        s1 = _post(port, "/sync", {})
        chk("A sync#1 (down) queued all, acked none", bool(s1.get("still_pending")) and not s1.get("acked"),
            str({k: s1.get(k) for k in ('acked','still_pending','dead','failed')}))
        with _Mock.lock: _Mock.down = False
        s2 = _post(port, "/sync", {})
        chk("A sync#2 (up, force) acked the queued deliveries", bool(s2.get("acked")) and not s2.get("still_pending"),
            str({k: s2.get(k) for k in ('acked','still_pending','dead','failed')}))
        cc = sqlite3.connect(f"{d}/chain.db")
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events"))
        cids = [r[0] for r in cc.execute("SELECT case_id FROM events")]
        cc.close()
        chk("A chain has NO raw PII names", "Lakshmi" not in blob and "Durga" not in blob and "Sita" not in blob)
        chk("A chain has NO raw phone digits", "9900112233" not in blob and "9811122233" not in blob and "9999888877" not in blob)
        chk("A chain has NO photo bytes", "BROKEN-PUMP-PHOTO-BYTES" not in blob)
        chk("A chain DOES carry photo HASH", c["photo_hash"] in blob)
        chk("A civic case_id is on the chain (COLUMN)", c["case_id"] in cids, str(cids))
        ob = _wait(port, "/health").get("outbox", {})
        chk("A outbox acked>=3 (voice+voice2+civic propagated; abstain not enqueued)", ob.get("acked",0) >= 3, str(ob))
    finally:
        p.terminate(); p.wait(timeout=5); srv.shutdown()

def phase_b():
    print("\n##### PHASE B : NO uplink (offline booth = local-durable, never wrongly dead-lettered) #####")
    d = tempfile.mkdtemp(prefix="haqvil_b_")
    p, port = _spawn_village(d, block_url=None)
    try:
        h = _wait(port)
        chk("B village up + uplink NONE", h.get("ok") is True and h.get("uplink_configured") is False, str(h))
        c = _post(port, "/civic", {"category": "drain", "ward": 3,
                                   "pii_fields": {"name": "Ravi", "phone": "9700001111"}})
        chk("B civic accepted + local seq", c.get("seq") is not None and c.get("case_id"), str(c))
        st = _wait(port, "/status")
        chk("B civic OPEN in local /status (SLA tracked offline)", c["case_id"] in st.get("open_civic", []), str(st.get("open_civic")))
        ob = _wait(port, "/health").get("outbox", {})
        chk("B outbox total==0 (nothing enqueued w/o uplink; not dead-lettered)", ob.get("total", -1) == 0, str(ob))
        cc = sqlite3.connect(f"{d}/chain.db")
        cids = [r[0] for r in cc.execute("SELECT case_id FROM events")]
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events"))
        cc.close()
        chk("B local chain durable (civic event present, case_id COLUMN)", c["case_id"] in cids, str(cids))
        chk("B local chain has NO raw PII", "Ravi" not in blob and "9700001111" not in blob)
    finally:
        p.terminate(); p.wait(timeout=5)

def main():
    print("##### VILLAGE NODE (audited booth producer; seams = labeled stand-ins) #####")
    phase_a(); phase_b()
    print("\n[RESULT]", "VILLAGE NODE GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)

if __name__ == "__main__":
    main()
PYEOF

echo "########## GATES (each in its own fresh sandbox; xproc gets a village port) ##########"
GATES=""
gate () {
  local label="$1"; shift
  local d; d="$(mktemp -d /tmp/fgate_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 7
  local rc="${PIPESTATUS[0]}"
  printf '>>> %-12s exit=%s\n' "$label" "$rc"
  rm -rf "$d"; GATES="$GATES $label=$rc"
}
gate "village"     python -m core.run_village_demo
gate "xproc"       python -m core.run_xproc_proof
gate "pillar1"     python -m core.run_pillar1_demo
gate "wal"         python -m core.run_wal_migration
gate "clock"       python -m core.run_clock_demo
gate "launch"      python -m core.run_launcher_demo
gate "sabha"       python -m sabha.run_sabha
gate "dash"        python -m sdm.run_dashboard_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "ALL GATES GREEN :: D1 opaque-token false-positive killed, D2 manual-sync bypasses backoff, D3 durability reads the column, D4 xproc expects audited village" || echo "SOME GATE RED :: see exit!=0 above"
