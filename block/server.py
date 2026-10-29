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
