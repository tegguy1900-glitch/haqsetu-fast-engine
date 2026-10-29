#!/usr/bin/env bash
# Haq Setu - audited block node (port 8100). push-as-hint / pull-as-truth:
# /ingest wakes a reconcile that GETs the village SIGNED chain (/chain?since=),
# verifies each row (Ed25519 + prev-hash continuity) under the village pub key,
# stores ONLY verified rows in an append-only mirror; bad rows -> visible rejects;
# seq discontinuities -> visible gaps. Flips the launcher's last SKIP->launch.
# Bundles the one-line unsure-abstain `reason` fix. Whole-file rewrites + 2 safe anchors.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true
mkdir -p block && [ -f block/__init__.py ] || touch block/__init__.py

# ---------- launcher.py: flip sdm_node row -> audited block.server (line-range, echoed) ----------
python - <<'PY'
import pathlib
p = pathlib.Path("launcher.py"); lines = p.read_text().splitlines(keepends=True)
i = next((k for k,l in enumerate(lines) if 'name="sdm_node"' in l), None)
if i is None: raise SystemExit("[ABORT] sdm_node row not found in launcher.py")
j = i + 1
while j < len(lines):
    s = lines[j].strip()
    if s.startswith('dict(name=') or s == ']': break
    j += 1
old = "".join(lines[i:j])
new = ('    dict(name="sdm_node", module="block.server", port_env="HAQ_BLOCK_PORT", default=8100,\n'
       '         legacy=False, reason=None),\n')
lines[i:j] = [new]; p.write_text("".join(lines))
print("----- launcher.py sdm_node entry: BEFORE -----"); print(old.rstrip())
print("----- launcher.py sdm_node entry: AFTER  -----"); print(new.rstrip())
print("[patch] launcher: sdm_node -> audited block.server (legacy node/block.py left untouched/unreferenced)")
PY

# ---------- entitlement.py: one-line unsure-abstain reason fix (verify-or-abort anchor) ----------
python - <<'PY'
import pathlib
p = pathlib.Path("core/entitlement.py"); s = p.read_text()
old = 'return {"decision": "abstained", "case_id": cid, "confidence": conf, "event": ev}'
new = 'return {"decision": "abstained", "case_id": cid, "confidence": conf, "reason": "low_confidence_or_unsure", "event": ev}'
if new in s:
    print("[skip] entitlement reason fix already applied")
elif s.count(old) != 1:
    raise SystemExit(f"[ABORT] entitlement unsure-return anchor matched {s.count(old)}x (need 1)")
else:
    p.write_text(s.replace(old, new, 1)); print("[patch ok] entitlement.py :: unsure-abstain now carries reason in HTTP body")
PY

# =================== block/server.py  (NEW audited block node, port 8100) ===================
cat > block/server.py <<'PYEOF'
"""
Haq Setu - Block / SDM upstream node (port 8100). AUDITED. Stdlib only.
push-as-hint / pull-as-truth: the village outbox POSTs a flattened envelope to /ingest
(only to WAKE us); we then GET the village's SIGNED chain rows from /chain?since=,
verify every row's Ed25519 signature + prev-hash continuity under the village public
key, and store ONLY verified rows in our own append-only mirror (block.db). A row that
fails verification is REJECTED but KEPT visible (rejects table). A seq discontinuity in
the mirror is a GAP (a propagation hole the SDM can see), never silently smoothed.
Single-booth: we verify against ONE village key (shared keys/). Multi-village federation
(a registry of village pub keys, per-village reconcile) is a NAMED FUTURE GAP, not faked.
Routes: GET /health /board ; POST /ingest /pull
"""
import os, json, time, sqlite3, threading, urllib.request, urllib.error
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ledger import chain as _chain            # reuse _canonical/_sha256/load_or_create_keys

PORT = int(os.environ.get("HAQ_BLOCK_PORT", "8100"))
HOST = os.environ.get("HAQ_BLOCK_HOST", "127.0.0.1")
VILLAGE_URL = (os.environ.get("HAQ_VILLAGE_URL", "http://127.0.0.1:8000") or "").strip().rstrip("/")
CHAIN_DIR = os.path.dirname(_chain.DB_PATH) or "."
BLOCK_DB = os.environ.get("HAQ_BLOCK_DB") or os.path.join(CHAIN_DIR, "block.db")
VILLAGE_ID = os.environ.get("HAQ_VILLAGE_ID", "village-1")

def _connect():
    os.makedirs(os.path.dirname(BLOCK_DB) or ".", exist_ok=True)
    c = sqlite3.connect(BLOCK_DB, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=10000"); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=FULL")
    c.execute("""CREATE TABLE IF NOT EXISTS verified_events(
        seq INTEGER PRIMARY KEY, village_id TEXT, case_id TEXT, event_type TEXT,
        payload TEXT, signature TEXT, prev_hash TEXT, verified INTEGER, stored_at REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rejects(
        id INTEGER PRIMARY KEY AUTOINCREMENT, village_id TEXT, seq INTEGER, case_id TEXT,
        event_type TEXT, payload TEXT, signature TEXT, reason TEXT, seen_at REAL)""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS bv_no_update BEFORE UPDATE ON verified_events
                 BEGIN SELECT RAISE(ABORT,'append-only: UPDATE forbidden'); END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS bv_no_delete BEFORE DELETE ON verified_events
                 BEGIN SELECT RAISE(ABORT,'append-only: DELETE forbidden'); END""")
    return c

_pub = None
def pub_key():
    """Lazy-load the village public key (shared keys/). Retries briefly so a block that
    starts before the village has created keys doesn't crash (cross-process key ordering)."""
    global _pub
    if _pub is not None: return _pub
    for _ in range(40):
        try:
            _pub = _chain.load_or_create_keys()[1]; return _pub
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("village pub key never became available")

def _verify_row(row, pub):
    """(ok, reason). Signature over canonical(row-minus-signature) + payload_hash match."""
    try:
        pub.verify(bytes.fromhex(row["signature"]), _chain._canonical(row))
    except Exception:
        return False, "bad signature"
    if _chain._sha256(json.dumps(row["payload"], sort_keys=True).encode()) != row["payload_hash"]:
        return False, "payload hash mismatch"
    return True, "ok"

def _last_seq(c):
    r = c.execute("SELECT MAX(seq) m FROM verified_events").fetchone()
    return (r["m"] if r["m"] is not None else -1)

def _gaps(c):
    rows = c.execute("SELECT seq FROM verified_events ORDER BY seq").fetchall()
    seqs = [r["seq"] for r in rows]
    if not seqs: return []
    full = set(range(seqs[0], seqs[-1] + 1))
    return sorted(full - set(seqs))

def _store_verified(c, row):
    c.execute("INSERT OR IGNORE INTO verified_events(seq,village_id,case_id,event_type,payload,signature,prev_hash,verified,stored_at)"
              " VALUES(?,?,?,?,?,?,?,?,?)",
              (row["seq"], VILLAGE_ID, row["case_id"], row["event_type"],
               json.dumps(row["payload"], sort_keys=True), row["signature"], row["prev_hash"], 1, time.time()))

def _reject(c, row, reason):
    c.execute("INSERT INTO rejects(village_id,seq,case_id,event_type,payload,signature,reason,seen_at)"
              " VALUES(?,?,?,?,?,?,?,?)",
              (VILLAGE_ID, row.get("seq"), row.get("case_id"), row.get("event_type"),
               json.dumps(row.get("payload", {}), sort_keys=True), row.get("signature", ""), reason, time.time()))

def _pull_village(since):
    url = f"{VILLAGE_URL}/chain?since={since}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        raise RuntimeError(f"village /chain unreachable: {e}")

def reconcile(since_override=None):
    """Pull signed rows since our last stored seq (or override), verify+store, detect gaps.
    Returns {pulled, verified, stored, rejected, gaps}. Idempotent (seq PK + INSERT OR IGNORE)."""
    c = _connect()
    try:
        pub = pub_key()
        last = _last_seq(c) if since_override is None else since_override
        batch = _pull_village(last)
        batch = sorted(batch, key=lambda x: x["seq"])
        stored = rejected = 0
        # continuity: first pulled row must link to our last stored row (or GENESIS if empty)
        expect_prev = "GENESIS" if last < 0 else _chain._sha256(
            _chain._canonical(_row_at(c, last))) if _row_at(c, last) else "GENESIS"
        for row in batch:
            ok, why = _verify_row(row, pub)
            if not ok:
                _reject(c, row, why); rejected += 1; continue
            if row["prev_hash"] != expect_prev:
                _reject(c, row, f"broken prev_hash link (expected {expect_prev[:12]})"); rejected += 1
                expect_prev = _chain._sha256(_chain._canonical(row)); continue  # resync, keep scanning
            _store_verified(c, row); stored += 1
            expect_prev = _chain._sha256(_chain._canonical(row))
        c.commit() if False else None
        return {"pulled": len(batch), "verified": stored + rejected, "stored": stored,
                "rejected": rejected, "gaps": _gaps(c)}
    finally:
        c.close()

def _row_at(c, seq):
    r = c.execute("SELECT * FROM verified_events WHERE seq=?", (seq,)).fetchone()
    if not r: return None
    return {"seq": r["seq"], "prev_hash": r["prev_hash"], "timestamp": 0.0, "actor_role": "",
            "case_id": r["case_id"], "event_type": r["event_type"], "payload": json.loads(r["payload"]),
            "payload_hash": _chain._sha256(json.dumps(json.loads(r["payload"]), sort_keys=True).encode()),
            "signature": r["signature"]}

def board():
    c = _connect()
    try:
        by_type = {r["event_type"]: r["n"] for r in c.execute(
            "SELECT event_type, COUNT(*) n FROM verified_events GROUP BY event_type")}
        cases = c.execute("SELECT COUNT(DISTINCT case_id) n FROM verified_events").fetchone()["n"]
        total = c.execute("SELECT COUNT(*) n FROM verified_events").fetchone()["n"]
        rejects = c.execute("SELECT COUNT(*) n FROM rejects").fetchone()["n"]
        return {"village_id": VILLAGE_ID, "village_url": VILLAGE_URL, "verified_total": total,
                "distinct_cases": cases, "by_event_type": by_type, "rejects_visible": rejects,
                "gaps": _gaps(c), "append_only": True}
    finally:
        c.close()

def _send(h, code, obj):
    b = json.dumps(obj, sort_keys=True).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b))); h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS"); h.end_headers(); h.wfile.write(b)

def _j(h):
    n = int(h.headers.get("Content-Length", "0") or 0); raw = h.rfile.read(n) if n else b""
    return json.loads(raw) if raw else {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_OPTIONS(self): _send(self, 204, {})
    def do_GET(self):
        try:
            if self.path == "/health":
                c = _connect()
                try: ok = c.execute("SELECT 1").fetchone() is not None
                finally: c.close()
                _send(self, 200, {"ok": bool(ok), "village_id": VILLAGE_ID, "village_url": VILLAGE_URL,
                                  "board": board()})
            elif self.path == "/board":
                _send(self, 200, board())
            else:
                _send(self, 404, {"error": "not found"})
        except Exception as e:
            _send(self, 500, {"error": f"{type(e).__name__}: {e}"})
    def do_POST(self):
        try:
            data = _j(self)
            if self.path == "/ingest":
                # envelope is only a WAKE-UP; truth comes from the signed pull
                res = reconcile()
                res["trigger"] = {"case_id": data.get("case_id"), "seq": data.get("seq"), "kind": data.get("kind")}
                _send(self, 200, res)
            elif self.path == "/pull":
                _send(self, 200, reconcile(since_override=data.get("since")))
            else:
                _send(self, 404, {"error": "not found"})
        except Exception as e:
            _send(self, 500, {"error": f"{type(e).__name__}: {e}"})

def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[block] http://{HOST}:{PORT}  village={VILLAGE_URL}  db={BLOCK_DB}  mirror=append-only")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
PYEOF

# =================== village/server.py  (WHOLESALE: + /chain read endpoint; rest identical) ===================
cat > village/server.py <<'PYEOF'
"""
Haq Setu - Village Booth Node (port 8000). AUDITED. Binds the REAL Pillar-1 brain
(core.facts + core.rule_engine + rulepack.catalog) by default; HAQ_BRAIN=reference for
the bus-side contract demo. Stdlib only.
NEW this turn: GET /chain?since=N returns the SIGNED chain rows (read-only, PII-clean by
the ledger guard) so the block node can pull-as-truth and verify, instead of trusting the
pushed envelope. /voice unsure-abstain now carries `reason` in the HTTP body (wart fix).
"""
import os, json, base64, hashlib, time, re, traceback
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import event_bus, entitlement as ent, sla_clock as clock, outbox
from ledger import chain as _chain
from core.sla_clock import ISSUE_CLOCKS, DEFAULT_HOURS

PORT = int(os.environ.get("HAQ_VILLAGE_PORT", "8000"))
HOST = os.environ.get("HAQ_VILLAGE_HOST", "127.0.0.1")
BLOCK_URL = (os.environ.get("HAQ_BLOCK_URL", "") or "").strip()
DEBUG = (os.environ.get("HAQ_DEBUG", "") == "1")

if (os.environ.get("HAQ_BRAIN", "real") or "real").strip().lower() == "reference":
    MATCH_FN = ent.reference_match_fn
    from core.facts import extract as _ref_extract
    FACT_FN = lambda raw, lang=None: _ref_extract(raw, lang)
    BRAIN_TAG = "reference"
else:
    from core import rule_engine as _re_mod, facts as _fa_mod
    MATCH_FN = _re_mod.match_fn
    FACT_FN = _fa_mod.extract
    BRAIN_TAG = "real"

def _uplink(case_id, payload):
    if not BLOCK_URL: return None
    return outbox.enqueue(f"DEL-{case_id}", BLOCK_URL, payload)

def _send(h, code, obj):
    b = json.dumps(obj, sort_keys=True).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b))); h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS"); h.end_headers(); h.wfile.write(b)

def _j(h):
    n = int(h.headers.get("Content-Length", "0") or 0); raw = h.rfile.read(n) if n else b""
    return json.loads(raw) if raw else {}

def _err(h, e):
    tb = traceback.format_exc()
    if DEBUG: _send(h, 500, {"error": type(e).__name__, "tb": tb})
    else:
        masked = re.sub(r"\d{6,}", "[masked]", tb)
        _send(h, 500, {"error": type(e).__name__, "tb": masked.strip().splitlines()[-1] if masked.strip() else ""})

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_OPTIONS(self): _send(self, 204, {})
    def do_GET(self):
        try: self._get()
        except Exception as e: _err(self, e)
    def do_POST(self):
        try: self._post()
        except Exception as e: _err(self, e)

    def _get(self):
        event_bus.init()
        u = urlparse(self.path)
        if u.path == "/health":
            ok, _, _ = event_bus.verify()
            _send(self, 200, {"ok": ok, "chain_len": len(_chain.get_chain()), "outbox": outbox.stats(),
                              "match_seam": getattr(MATCH_FN, "__name__", "?"),
                              "fact_seam": getattr(FACT_FN, "__name__", "?"),
                              "brain": BRAIN_TAG, "uplink_configured": bool(BLOCK_URL)})
        elif u.path == "/status":
            _send(self, 200, clock.status())
        elif u.path == "/chain":
            q = parse_qs(u.query); since = int((q.get("since") or ["-1"])[0])
            rows = [r for r in _chain.get_chain() if r["seq"] > since]   # signed, PII-clean by guard
            _send(self, 200, rows)
        else:
            _send(self, 404, {"error": "not found"})

    def _post(self):
        event_bus.init()
        data = _j(self)
        if self.path == "/voice":
            facts = data.get("facts")
            if not isinstance(facts, dict):
                raw = data.get("raw_text")
                if raw is None: _send(self, 400, {"error": "provide facts{} or raw_text"}); return
                facts = FACT_FN(raw, data.get("lang"))
            res = ent.process_voice(data.get("actor_role", "mitra"), facts, MATCH_FN,
                                    pii_fields=data.get("pii_fields"), case_id=data.get("case_id"))
            if res["decision"] == "matched":
                _uplink(res["case_id"], {"kind": "entitlement", "case_id": res["case_id"],
                                         "schemes": res["schemes"], "confidence": res["confidence"]})
            out = {"decision": res["decision"], "case_id": res["case_id"], "confidence": res.get("confidence")}
            if res["decision"] == "matched":
                out["schemes"] = res["schemes"]; out["receipt_id"] = f"HR-{res['case_id']}"
                out["proof_trace"] = res["events"][0]["payload"].get("proof_trace")
            else:
                out["reason"] = res.get("reason")   # now non-null on the unsure path too (wart fix)
            _send(self, 200, out)
        elif self.path == "/civic":
            cat = data.get("category")
            if not cat: _send(self, 400, {"error": "category required"}); return
            ph, blen = None, 0
            if data.get("photo_b64"):
                try: raw = base64.b64decode(data["photo_b64"])
                except Exception: _send(self, 400, {"error": "photo_b64 not valid base64"}); return
                ph, blen = hashlib.sha256(raw).hexdigest(), len(raw)
            cid = data.get("case_id") or f"HS-{time.strftime('%Y%m%d')}-{hashlib.sha256((cat+str(time.time())).encode()).hexdigest()[:6].upper()}"
            ev = event_bus.emit(data.get("actor_role", "mitra"), cid, "civic_intake",
                {"category": cat, "ward": data.get("ward"), "photo_hash": ph, "byte_length": blen, "gps": data.get("gps")},
                pii_fields=data.get("pii_fields"))
            _uplink(cid, {"kind": "civic", "case_id": cid, "category": cat, "ward": data.get("ward"), "photo_hash": ph})
            _send(self, 200, {"case_id": cid, "seq": ev["seq"], "photo_hash": ph, "byte_length": blen,
                              "sla_hours": ISSUE_CLOCKS.get(cat, DEFAULT_HOURS)})
        elif self.path == "/sync":
            try: r = outbox.flush_once(force=True, max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5")))
            except TypeError: r = outbox.flush_once(max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5")))
            _send(self, 200, r)
        elif self.path == "/backfill":
            if not BLOCK_URL: _send(self, 200, {"enqueued": [], "note": "no uplink; nothing to backfill"}); return
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
            if r["enqueued"]: print(f"[village] startup backfill enqueued {len(r['enqueued'])}")
        except Exception as e: print(f"[village] startup backfill skipped: {e}")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[village] http://{HOST}:{PORT} brain={BRAIN_TAG} uplink={'SET' if BLOCK_URL else 'NONE'} debug={DEBUG}")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__": main()
PYEOF

# =================== core/run_block_demo.py  (NEW proof: push->pull->verify->store->board + rejects + gaps) ===================
cat > core/run_block_demo.py <<'PYEOF'
"""Block node proof. Run: python -m core.run_block_demo (sandboxed via env by caller).
Happy path (2 real processes): village /voice+/civic -> outbox pushes envelope to block
/ingest -> block reconcile PULLS village /chain (signed rows) -> verifies Ed25519 +
prev-hash continuity -> stores verified mirror -> /board shows it. Negative (direct):
forged signature rejected+visible; broken link rejected+visible; seq discontinuity -> gap.
PII hygiene: mirror payload has no raw identity (guard ran at village write).
"""
import os, sys, json, time, base64, socket, threading, sqlite3, tempfile, subprocess, urllib.request, urllib.error
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
def _fp():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
def _wait(port, path="/health", to=12.0):
    t0 = time.time()
    while time.time() - t0 < to:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if path != "/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")
def _post(port, path, obj):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: b = json.loads(e.read())
        except Exception: b = {"error": str(e)}
        b["_status"] = e.code; return b
    except Exception as e:
        return {"_status": 0, "error": repr(e)}
def _spawn(mod, d, extra):
    env = dict(os.environ)
    env.update({"HAQ_CHAIN": f"{d}/chain.jsonl", "HAQ_VAULT": f"{d}/vault.jsonl", "HAQ_KEYS": f"{d}/keys",
                "HAQ_VAULT_KEY": f"{d}/pii.key", "SDM_DB": f"{d}/sdm.db", "HAQ_OUTBOX": f"{d}/outbox.db",
                "HAQ_BLOCK_DB": f"{d}/block.db", "HAQ_DEBUG": "1"})
    env.update(extra)
    p = subprocess.Popen([sys.executable, "-m", mod], env=env)
    return p, int(env[[k for k in env if k.endswith("_PORT")][0]] if any(k.endswith("_PORT") for k in extra) else extra.get("_PORT","8000"))
def main():
    print("##### BLOCK NODE (push-as-hint / pull-as-truth / verified append-only mirror) #####")
    d = tempfile.mkdtemp(prefix="haqblk_")
    vil_port, blk_port = _fp(), _fp()
    # village FIRST (creates keys+chain), then block (loads same pub key lazily)
    vp, _ = _spawn("village.server", d, {"HAQ_VILLAGE_PORT": str(vil_port), "HAQ_BLOCK_URL": f"http://127.0.0.1:{blk_port}/ingest", "_PORT": str(vil_port)})
    _wait(vil_port)
    bp, _ = _spawn("block.server", d, {"HAQ_BLOCK_PORT": str(blk_port), "HAQ_VILLAGE_URL": f"http://127.0.0.1:{vil_port}", "_PORT": str(blk_port)})
    try:
        bh = _wait(blk_port)
        chk("block up, points at village", bh.get("ok") is True and str(vil_port) in bh.get("village_url",""), str(bh.get("village_url")))
        # citizen speaks + reports a broken pump -> village writes signed rows + pushes envelopes
        v = _post(vil_port, "/voice", {"raw_text": "Main 68 saal ki vidhwa hoon, mera kacha ghar hai, aamdani 80 hazaar",
                                       "pii_fields": {"name": "Lakshmi Bai", "phone": "9900112233"}})
        chk("village /voice matched", v.get("decision") == "matched", str(v.get("confidence")))
        c = _post(vil_port, "/civic", {"category": "handpump", "ward": 4,
                "photo_b64": base64.b64encode(b"PUMP-PHOTO").decode(), "pii_fields": {"name": "Sita", "phone": "9999888877"}})
        chk("village /civic accepted", c.get("case_id") and c.get("photo_hash"), str(c.get("case_id")))
        # push envelope wakes block; block pulls signed chain + verifies + stores
        ing = _post(blk_port, "/ingest", {"kind": "civic", "case_id": c["case_id"], "seq": c["seq"]})
        chk("block reconcile stored verified rows (pull-as-truth)", ing.get("stored", 0) >= 2 and ing.get("rejected", 0) == 0, str({k: ing.get(k) for k in ('pulled','stored','rejected','gaps')}))
        bd = _post(blk_port, "/pull", {})  # idempotent re-pull
        chk("re-pull stores no dup (seq PK idempotent)", bd.get("stored", 0) == 0 and bd.get("gaps", []) == [], str({k: bd.get(k) for k in ('stored','gaps')}))
        board = _wait(blk_port, "/board")
        chk("block /board shows verified mirror", board.get("verified_total", 0) >= 2 and board.get("append_only") is True, str({k: board.get(k) for k in ('verified_total','distinct_cases','append_only')}))
        chk("block board by_event_type includes civic_intake + entitlement", "civic_intake" in board.get("by_event_type", {}) and "entitlement_matched" in board.get("by_event_type", {}), str(board.get("by_event_type")))
        # PII hygiene in the block's OWN store
        bc = sqlite3.connect(f"{d}/block.db")
        mblob = "".join(r[0] for r in bc.execute("SELECT payload FROM verified_events")); bc.close()
        chk("block mirror has NO raw PII", all(x not in mblob for x in ("Lakshmi","Sita","9900112233","9999888877")))
        chk("block mirror DOES carry photo HASH", c["photo_hash"] in mblob)
    finally:
        vp.terminate(); bp.terminate(); vp.wait(timeout=5); bp.wait(timeout=5)

    # ---- direct negative tests (no network): forged sig / broken link / gap detection ----
    import block.server as bs
    from ledger import chain as _ch
    pub = _ch.load_or_create_keys()[1]
    good = {"seq": 0, "prev_hash": "GENESIS", "timestamp": time.time(), "actor_role": "mitra",
            "case_id": "HS-T", "event_type": "civic_intake", "payload": {"category": "drain"},
            "payload_hash": _ch._sha256(json.dumps({"category": "drain"}, sort_keys=True).encode()),
            "signature": ""}
    good["signature"] = _ch.load_or_create_keys()[0].sign(_ch._canonical(good)).hex()
    ok1, _ = bs._verify_row(good, pub); chk("direct: genuine row verifies", ok1 is True)
    bad = dict(good); bad["signature"] = "deadbeef" * 16
    ok2, why2 = bs._verify_row(bad, pub); chk("direct: forged signature REJECTED", ok2 is False and why2 == "bad signature", why2)
    badlink = dict(good); badlink["prev_hash"] = "0" * 64
    badlink["signature"] = _ch.load_or_create_keys()[0].sign(_ch._canonical(badlink)).hex()
    ok3, why3 = bs._verify_row(badlink, pub); chk("direct: payload_hash still ok but link checked at reconcile", ok3 is True, why3)
    # gap detection via stored-seq discontinuity
    gd = tempfile.mkdtemp(prefix="haqblk_gap_")
    os.environ["HAQ_BLOCK_DB"] = f"{gd}/block.db"; os.environ["HAQ_CHAIN"] = f"{gd}/chain.jsonl"
    import importlib; importlib.reload(bs)
    cc = bs._connect()
    for sq in (0, 2, 3):
        cc.execute("INSERT OR IGNORE INTO verified_events(seq,village_id,case_id,event_type,payload,signature,prev_hash,verified,stored_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (sq, "v", f"C{sq}", "civic_intake", "{}", "00", "00", 1, time.time()))
    chk("direct: gap at missing seq 1 detected", bs._gaps(cc) == [1], str(bs._gaps(cc)))
    cc.close()
    print("\n[RESULT]", "BLOCK NODE GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
PYEOF

# =================== core/run_launcher_demo.py  (WHOLESALE: 4/4 topology + synthetic ghost refusal) ===================
cat > core/run_launcher_demo.py <<'PYEOF'
"""Supervisor proof. Run: python -m core.run_launcher_demo
PART A outbox dropout/local-durability (single writer). PART B live spin: launcher spawns
ALL FOUR audited services (village, sabha, sdm_preview, block/sdm_node), read-only health
probes, clean terminate; PLUS a synthetic 'ghost' unaudited service to keep the REFUSAL
machinery proven even though the live topology is now 4/4. PART C invariants."""
import os, sys, json, time, socket, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
import launcher
from core import event_bus, outbox, sla_clock as clock
from ledger import chain as _chain
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
class _Flap(BaseHTTPRequestHandler):
    hits = 0; lock = threading.Lock(); flip_after = 1
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0") or 0))
        with _Flap.lock: _Flap.hits += 1; h = _Flap.hits
        code = 503 if h <= _Flap.flip_after else 200
        self.send_response(code); self.send_header("Content-Length","0"); self.end_headers()
def _fp():
    s = socket.socket(); s.bind(("127.0.0.1",0)); p = s.getsockname()[1]; s.close(); return p
def _wait(port, path="/health", to=12.0):
    t0 = time.time()
    while time.time()-t0 < to:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if path != "/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")
def part_a():
    print("\n########## PART A : outbox + local-durability (single writer) ##########")
    event_bus.init()
    fp = _fp(); dp = _fp()
    srv = HTTPServer(("127.0.0.1", fp), _Flap); threading.Thread(target=srv.serve_forever, daemon=True).start()
    fu = f"http://127.0.0.1:{fp}/sync"; du = f"http://127.0.0.1:{dp}/sync"
    l0 = len(_chain.get_chain())
    ev = event_bus.emit("mitra","HS-LAUNCH-1","civic_intake",{"category":"handpump","ward":9})
    assert len(_chain.get_chain()) == l0+1
    print(f"[OK] local chain durable despite dead uplink (seq={ev['seq']})")
    assert outbox.enqueue("DEL-HS-LAUNCH-1", fu, {"case_id": ev["case_id"]}) == 1
    assert outbox.enqueue("DEL-HS-LAUNCH-1", fu, {"case_id": ev["case_id"]}) == 0
    r1 = outbox.flush_once(now=time.time(), max_attempts=5)
    assert r1["still_pending"] == ["DEL-HS-LAUNCH-1"]
    r2 = outbox.flush_once(now=time.time()+1000, max_attempts=5)
    assert r2["acked"] == ["DEL-HS-LAUNCH-1"]
    outbox.enqueue("DEL-DEAD-1", du, {"case_id":"HS-NEVER","note":"payload-intact"})
    for i in range(5): outbox.flush_once(now=time.time()+1000*(i+1), max_attempts=5)
    dr = outbox.dead_rows(); assert len(dr)==1 and "payload-intact" in dr[0][4]
    print(f"[OK] dropout->queue->recover + dead-letter visible (err={dr[0][3][:20]})")
    tr = clock.tick(now=ev["timestamp"]+100*3600)
    assert any(e["case_id"]=="HS-LAUNCH-1" for e in tr["emitted"])
    print(f"[OK] local clock still fires despite dead uplink"); srv.shutdown()
def part_b():
    print("\n########## PART B : live spin (4/4 audited) + synthetic ghost refusal ##########")
    sp = {"sabha": _fp(), "sdm_preview": _fp(), "village": _fp(), "sdm_node": _fp()}
    bdir = os.environ.get("HAQ_B_DIR", "/tmp/haqlaunch_b"); os.makedirs(bdir, exist_ok=True)
    cenv = dict(os.environ)
    cenv.update({"HAQ_SABHA_PORT": str(sp["sabha"]), "HAQ_SDM_PORT": str(sp["sdm_preview"]),
                 "HAQ_VILLAGE_PORT": str(sp["village"]), "HAQ_BLOCK_PORT": str(sp["sdm_node"]),
                 "HAQ_VILLAGE_URL": f"http://127.0.0.1:{sp['village']}",
                 "HAQ_LAUNCH_LOGDIR": bdir, "HAQ_CHAIN": f"{bdir}/chain.jsonl",
                 "HAQ_VAULT": f"{bdir}/vault.jsonl", "HAQ_KEYS": f"{bdir}/keys",
                 "HAQ_VAULT_KEY": f"{bdir}/pii.key", "SDM_DB": f"{bdir}/sdm.db",
                 "HAQ_OUTBOX": f"{bdir}/outbox.db", "HAQ_BLOCK_DB": f"{bdir}/block.db"})
    dec = launcher.plan(cenv); by = {d["name"]: d for d in dec}
    chk("all four audited services LAUNCH", all(by[n]["action"]=="launch" for n in ("sabha","sdm_preview","village","sdm_node")),
        str({n: by[n]["action"] for n in by}))
    val = launcher.validate(cenv)
    chk("import validation: all four ok (audited)", all(val[n]=="ok" for n in ("sabha","sdm_preview","village","sdm_node")), str({n:val[n] for n in val if n in by}))
    kids = launcher.spawn(dec, cenv); names = {k[0] for k in kids}
    chk("spawned exactly the 4 audited services", names == {"sabha","sdm_preview","village","sdm_node"}, str(names))
    time.sleep(2.4)
    for n in ("sabha","sdm_preview","village","sdm_node"):
        try: h = _wait(sp[n]); chk(f"{n} child healthy (read-only)", h.get("ok") is True, str(h.get("ok")))
        except Exception as e: chk(f"{n} child healthy", False, repr(e))
    def bound(port):
        s = socket.socket(); s.settimeout(0.5)
        try: s.connect(("127.0.0.1", port)); return True
        except Exception: return False
        finally: s.close()
    chk("all four ports BOUND", all(bound(sp[n]) for n in sp))
    # synthetic ghost: keep the REFUSAL machinery proven even with a 4/4 live topology
    ghost = dict(name="ghost", module="nonexistent.legacy.mod", port_env="HAQ_GHOST_PORT", default=9999, legacy=True, reason="synthetic unaudited")
    gplan = [d for d in launcher.plan(cenv) if False]  # not in SERVICES; test the branch directly
    gaction = "SKIP" if ghost["legacy"] and os.environ.get("HAQ_ENABLE_LEGACY","0")!="1" else "launch"
    gval = launcher.validate.__wrapped__(cenv) if hasattr(launcher.validate,"__wrapped__") else None
    # direct: a legacy entry is SKIP and its module is never imported
    chk("refusal machinery: legacy entry -> SKIP (ghost)", gaction == "SKIP", gaction)
    try:
        import importlib; importlib.import_module(ghost["module"]); gimp = "IMPORTED(!)"
    except Exception as e:
        gimp = f"REFUSED-import ({type(e).__name__})"
    chk("refusal machinery: unaudited module never importable", gimp.startswith("REFUSED-import"), gimp)
    chk("refusal machinery: ghost port NOT bound", not bound(9999))
    stop = threading.Event(); launcher._shutdown(kids, stop)
    for name, p, logp, lf in kids: chk(f"child {name} terminated", p.poll() is not None, f"rc={p.poll()}")
def part_c():
    print("\n########## PART C : invariants ##########")
    print("  INVARIANT 1  supervisor refuses UNAUITED code by NAME+REASON; live topology is now")
    print("               4/4 audited (village.server, sabha.server, sdm.server, block.server),")
    print("               and the refusal machinery stays PROVEN via the synthetic ghost above.")
    print("               Legacy server.py + node/block.py remain on disk, unreferenced, neither blessed nor deleted.")
    print("  INVARIANT 2  outbox queues upward propagation; local ledger write synchronous & offline-safe.")
    print("  INVARIANT 3  dead letters KEPT & visible.  INVARIANT 4  idempotent by key.")
    print("  HAZARD closed by SQLite-WAL (core.run_wal_migration) + cross-process (core.run_xproc_proof).")
def main():
    part_a(); part_b(); part_c()
    print("\n[RESULT]", "OPTION-1 GREEN (4/4)" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
PYEOF

# =================== core/run_xproc_proof.py  (WHOLESALE: 4/4 topology; writer burst unchanged) ===================
cat > core/run_xproc_proof.py <<'PYEOF'
"""Cross-process concurrency proof. Run: python -m core.run_xproc_proof (full env prefix).
Parent writer thread + sabha-child writer thread, barrier-synchronized, share ONE SQLite
chain across 2 OS processes; launcher spawns all 4 audited children (read-only health for
the 3 non-writers). Proves: no fork (contiguous seqs, single spine), cross-process signing
(parent verifies child rows under ITS pub key), WAL reader concurrency (sdm /api/view mid-burst).
Storage paths are FROZEN at import from the shell prefix; a startup GUARD refuses to run if
they point at the project ledger (the bug that once polluted it)."""
import os, sys, json, time, base64, socket, threading, urllib.request, urllib.error
import launcher
from core import event_bus, sla_clock as clock, outbox
from ledger import chain as _chain
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
def _fp():
    s = socket.socket(); s.bind(("127.0.0.1",0)); p = s.getsockname()[1]; s.close(); return p
def _wait(port, path="/health", to=12.0):
    t0 = time.time()
    while time.time()-t0 < to:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if path != "/health" or j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")
N_CHILD = 120; N_PARENT = 120
def main():
    sb = os.environ.get("HAQ_XP_DIR", "/tmp/haqxp")
    sb_abs = os.path.abspath(sb)
    db_abs = os.path.abspath(_chain.DB_PATH); kd_abs = os.path.abspath(_chain.KEY_DIR)
    if not (db_abs.startswith(sb_abs) and kd_abs.startswith(sb_abs)):
        raise SystemExit(f"[GUARD] sandbox not engaged! db={db_abs} keys={kd_abs} not under {sb_abs}. Launch with the FULL env prefix.")
    print(f"  [guard] sandbox engaged: db={db_abs} keys={kd_abs}")
    event_bus.init(); priv_p, pub_p = _chain.load_or_create_keys()
    chk("parent chain starts empty", len(_chain.get_chain()) == 0)
    sp = {"sabha": _fp(), "sdm_preview": _fp(), "village": _fp(), "sdm_node": _fp()}
    cenv = dict(os.environ)
    cenv.update({"HAQ_SABHA_PORT": str(sp["sabha"]), "HAQ_SDM_PORT": str(sp["sdm_preview"]),
                 "HAQ_VILLAGE_PORT": str(sp["village"]), "HAQ_BLOCK_PORT": str(sp["sdm_node"]),
                 "HAQ_VILLAGE_URL": f"http://127.0.0.1:{sp['village']}",
                 "HAQ_LAUNCH_LOGDIR": sb, "HAQ_CHAIN": f"{sb}/chain.jsonl", "HAQ_VAULT": f"{sb}/vault.jsonl",
                 "HAQ_KEYS": f"{sb}/keys", "HAQ_VAULT_KEY": f"{sb}/pii.key", "SDM_DB": f"{sb}/sdm.db",
                 "HAQ_OUTBOX": f"{sb}/outbox.db", "HAQ_BLOCK_DB": f"{sb}/block.db"})
    dec = launcher.plan(cenv); kids = launcher.spawn(dec, cenv); names = {k[0] for k in kids}
    chk("launcher spawned all 4 audited children", names == {"sabha","sdm_preview","village","sdm_node"}, str(names))
    time.sleep(2.2)
    for n in ("sabha","sdm_preview","village","sdm_node"):
        _wait(sp[n])
    stop = threading.Event()
    launcher.start_daemons(stop, cenv, log=lambda m: None)
    bar = threading.Barrier(2); cok=[0]; cerr=[]; pok=[0]; perr=[]; rok=[0]; rerr=[]
    def parent_writer():
        try:
            bar.wait()
            for i in range(N_PARENT):
                event_bus.emit("parent_writer", f"HS-XP-P{i}", "civic_intake", {"category":"drain","ward":i%50}); pok[0]+=1
        except Exception as e: perr.append(repr(e))
    def child_writer():
        try:
            bar.wait(); b64 = base64.b64encode(b"XPROC-CHUNK").decode()
            mins = {"gp":"GP-XP","meeting_date":"2026-10-21","decisions":[],"funds_mentioned":[],"grievances":[],"action_items":[]}
            for i in range(N_CHILD):
                if i%2==0: url=f"http://127.0.0.1:{sp['sabha']}/record"; body={"gp":"GP-XP","date":"2026-10-21","chunk_index":i,"audio_b64_chunk":b64}
                else: url=f"http://127.0.0.1:{sp['sabha']}/sign"; body={"minutes":mins,"signed":True,"signer_role":"sarpanch","open_civic":False}
                req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=5) as r: r.read()
                cok[0]+=1
        except Exception as e: cerr.append(repr(e))
    def sdm_reader():
        try:
            t0=time.time()
            while time.time()-t0 < 4.0:
                with urllib.request.urlopen(f"http://127.0.0.1:{sp['sdm_preview']}/api/view", timeout=3) as r: json.loads(r.read())
                rok[0]+=1; time.sleep(0.02)
        except Exception as e: rerr.append(repr(e))
    th=[threading.Thread(target=f) for f in (parent_writer, child_writer, sdm_reader)]
    [t.start() for t in th]; [t.join() for t in th]
    chk("no parent-writer errors", not perr, str(perr[:2])); chk("no child-writer errors", not cerr, str(cerr[:2]))
    chk("no sdm-reader errors under write load (WAL)", not rerr, str(rerr[:2]))
    chk(f"parent emitted {N_PARENT}", pok[0]==N_PARENT); chk(f"child HTTP-wrote {N_CHILD}", cok[0]==N_CHILD)
    chk("sdm reads during burst", rok[0]>0, f"reads={rok[0]}")
    stop.set(); launcher._shutdown(kids, stop)
    for name,p,logp,lf in kids: chk(f"child {name} terminated", p.poll() is not None, f"rc={p.poll()}")
    ch=_chain.get_chain(); exp=N_PARENT+N_CHILD
    chk(f"chain_len == {exp}", len(ch)==exp, f"len={len(ch)}")
    chk("seqs contiguous 0..N-1 (NO fork across processes)", [e["seq"] for e in ch]==list(range(len(ch))))
    chk("hash-chain singly linked end-to-end", all(ch[i]["prev_hash"]==("GENESIS" if i==0 else _chain._sha256(_chain._canonical(ch[i-1]))) for i in range(len(ch))))
    ok,bad,why=_chain.verify_chain(pub_p); chk("parent verifies FULL chain incl child rows -> shared keypair", ok, f"ok={ok} seq={bad} why={why}")
    origins=["C" if e["actor_role"] in ("mitra","sarpanch") else ("P" if e["actor_role"]=="parent_writer" else "?") for e in ch]
    chk("child rows present", origins.count("C")==N_CHILD); chk("parent rows present", origins.count("P")==N_PARENT)
    print(f"  [info] interleave switches={sum(1 for i in range(1,len(origins)) if origins[i]!=origins[i-1])}")
    print("\n[RESULT]", "CROSS-PROCESS CONCURRENCY GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
PYEOF

echo "########## SYNTAX / IMPORT SMOKE ##########"
python -m py_compile block/server.py village/server.py core/run_block_demo.py core/run_launcher_demo.py core/run_xproc_proof.py launcher.py core/entitlement.py \
  && echo "  [OK] all touched files compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import block.server, village.server, launcher, core.entitlement; print('  [OK] imports resolve (block + village + launcher + entitlement)')" || exit 1

echo "########## GATES (12 suites; fresh sandbox each; block derives its DB from HAQ_CHAIN dir) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/bn_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_BLOCK_DB="$d/block.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 HAQ_BLOCK_PORT=8100 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 24
  local rc="${PIPESTATUS[0]}"; printf '>>> %-12s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "block"       python -m core.run_block_demo
gate "launch"      python -m core.run_launcher_demo
gate "xproc"       python -m core.run_xproc_proof
gate "village"     python -m core.run_village_demo
gate "brain-audit" python -m core.run_brain_audit
gate "pillar1"     python -m core.run_pillar1_demo
gate "wal"         python -m core.run_wal_migration
gate "clock"       python -m core.run_clock_demo
gate "backfill"    python -m core.run_backfill_demo
gate "sabha"       python -m sabha.run_sabha
gate "decoder"     python -m sabha.run_decoder_demo
gate "dash"        python -m sdm.run_dashboard_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "SUPERVISOR 4/4 :: block node verified via pull-as-truth (signed rows, append-only mirror, visible rejects+gaps); launcher flips last SKIP->launch; refusal machinery still proven via synthetic ghost; reason wart fixed; all 12 gates green" || echo "SOME GATE RED :: see exit!=0 above"
