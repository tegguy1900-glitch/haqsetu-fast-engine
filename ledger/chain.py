"""
Haq Setu - Unified Append-Only Ledger.  STORAGE: SQLite (WAL).  API IDENTICAL to
the prior JSONL module, so core.event_bus and every proven demo keep working.
SQLite serializes writers (BEGIN IMMEDIATE kills the read-head-then-insert FORK
race); WAL lets readers run concurrent with the single writer; append-only
TRIGGERS make UPDATE/DELETE physically impossible (Never-Forget @ storage layer).
"""
import os, json, time, hashlib, re, sqlite3, threading
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization

CHAIN_FILE = os.environ.get("HAQ_CHAIN", "ledger/chain.jsonl")          # kept for parity
def _db_path():
    p = CHAIN_FILE
    if p.endswith(".jsonl"): return p[:-6] + ".db"
    if p.endswith(".db"):    return p
    return p + ".db"
DB_PATH = _db_path()                       # frozen at IMPORT time from the shell env prefix
KEY_DIR = os.environ.get("HAQ_KEYS", "keys")

_FORBIDDEN_KEYS = {
    "name","full_name","citizen_name","phone","mobile","cell","aadhaar",
    "aadhar","aadhaar_last4","email","address","house_no","gp_address",
    "ration_card_no","job_card_no","bank_account","ifsc","pan",
}
_AADHAAR_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
_PHONE_RE   = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")

class PiiLeakError(Exception):
    """Raised when a payload tries to smuggle PII into the public ledger."""

_OPAQUE_VALUE_KEYS = {
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
        if _PHONE_RE.search(obj):   raise PiiLeakError(f"Phone-like 10-digit number at {path}")

def _pem(priv):
    return priv.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
def _pub_pem(pub):
    return pub.public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)

def load_or_create_keys():
    os.makedirs(KEY_DIR, exist_ok=True)
    ppath, kpath = f"{KEY_DIR}/node.pem", f"{KEY_DIR}/node_pub.pem"
    if os.path.exists(ppath) and os.path.exists(kpath):
        priv = serialization.load_pem_private_key(open(ppath,'rb').read(), None)
        pub  = serialization.load_pem_public_key(open(kpath,'rb').read())
        return priv, pub
    priv = Ed25519PrivateKey.generate()
    open(ppath,'wb').write(_pem(priv))
    open(kpath,'wb').write(_pub_pem(priv.public_key()))
    os.chmod(ppath, 0o600)
    return priv, priv.public_key()

def _canonical(event):
    e = {k: v for k, v in event.items() if k != "signature"}
    return json.dumps(e, sort_keys=True, separators=(",", ":")).encode()
def _sha256(b):
    return hashlib.sha256(b).hexdigest()

_COLS = ("seq","prev_hash","timestamp","actor_role","case_id","event_type",
         "payload","payload_hash","signature")
_init_lock = threading.Lock()
_initialized = set()

def _connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)  # manual txns
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=10000")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")     # crash-safe appends (Never-Forget)
    return c

def _ensure_schema(c):
    if DB_PATH in _initialized: return
    with _init_lock:
        if DB_PATH in _initialized: return
        c.execute("""CREATE TABLE IF NOT EXISTS events(
            seq INTEGER PRIMARY KEY, prev_hash TEXT NOT NULL, timestamp REAL NOT NULL,
            actor_role TEXT NOT NULL, case_id TEXT NOT NULL, event_type TEXT NOT NULL,
            payload TEXT NOT NULL, payload_hash TEXT NOT NULL, signature TEXT NOT NULL)""")
        c.execute("""CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON events
                     BEGIN SELECT RAISE(ABORT,'append-only: UPDATE forbidden'); END""")
        c.execute("""CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON events
                     BEGIN SELECT RAISE(ABORT,'append-only: DELETE forbidden'); END""")
        _initialized.add(DB_PATH)

def _row_to_event(row):
    return {"seq": row["seq"], "prev_hash": row["prev_hash"], "timestamp": row["timestamp"],
            "actor_role": row["actor_role"], "case_id": row["case_id"],
            "event_type": row["event_type"], "payload": json.loads(row["payload"]),
            "payload_hash": row["payload_hash"], "signature": row["signature"]}

def append_event(actor_role, case_id, event_type, payload, priv):
    _scan_pii(payload)                                  # Never Leak gate (unchanged)
    c = _connect(); _ensure_schema(c)
    try:
        c.execute("BEGIN IMMEDIATE")                    # write lock BEFORE reading head
        last = c.execute("SELECT * FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        if last is None:
            prev, seq = "GENESIS", 0
        else:
            prev, seq = _sha256(_canonical(_row_to_event(last))), last["seq"] + 1
        event = {"seq": seq, "prev_hash": prev, "timestamp": time.time(),
                 "actor_role": actor_role, "case_id": case_id, "event_type": event_type,
                 "payload": payload,
                 "payload_hash": _sha256(json.dumps(payload, sort_keys=True).encode())}
        event["signature"] = priv.sign(_canonical(event)).hex()
        c.execute(f"INSERT INTO events({','.join(_COLS)}) VALUES({','.join(':'+k for k in _COLS)})",
                  {k: (json.dumps(event[k], sort_keys=True) if k == "payload" else event[k])
                   for k in _COLS})
        c.execute("COMMIT")
        return event
    except Exception:
        try: c.execute("ROLLBACK")
        except Exception: pass
        raise
    finally:
        c.close()

def verify_chain(pub):
    c = _connect(); _ensure_schema(c)
    rows = c.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()
    c.close()
    expected_prev = "GENESIS"
    for row in rows:
        ev = _row_to_event(row)
        if ev["prev_hash"] != expected_prev:
            return False, ev["seq"], "broken prev_hash link"
        try:
            pub.verify(bytes.fromhex(ev["signature"]), _canonical(ev))
        except Exception:
            return False, ev["seq"], "bad signature"
        if _sha256(json.dumps(ev["payload"], sort_keys=True).encode()) != ev["payload_hash"]:
            return False, ev["seq"], "payload hash mismatch"
        expected_prev = _sha256(_canonical(ev))
    return True, None, "ok"

def get_chain():
    c = _connect(); _ensure_schema(c)
    rows = c.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()
    c.close()
    return [_row_to_event(r) for r in rows]
