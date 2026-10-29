"""
Haq Setu - Encrypted PII Vault.  STORAGE: SQLite (WAL).  API IDENTICAL.
Old put_pii did read-all -> append -> write-all on JSONL with NO lock; the
multi-threaded village node could corrupt the vault in-process. SQLite makes
put_pii one atomic INSERT, erasing that race. Names/phones never reach the chain;
the ledger stores only an opaque blob_id. Erase-on-closure preserved.
"""
import os, json, uuid, sqlite3
from cryptography.fernet import Fernet

VAULT_FILE = os.environ.get("HAQ_VAULT", "ledger/pii_vault.jsonl")   # kept for parity
def _db_path():
    p = VAULT_FILE
    if p.endswith(".jsonl"): return p[:-6] + ".db"
    if p.endswith(".db"):    return p
    return p + ".db"
DB_PATH = _db_path()
KEY_FILE = os.environ.get("HAQ_VAULT_KEY", "keys/pii.key")

def _key():
    os.makedirs(os.path.dirname(KEY_FILE) or ".", exist_ok=True)
    if not os.path.exists(KEY_FILE):
        k = Fernet.generate_key(); open(KEY_FILE, "wb").write(k); os.chmod(KEY_FILE, 0o600)
    return open(KEY_FILE, "rb").read()
def _fernet(): return Fernet(_key())

def _connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=10000")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    c.execute("""CREATE TABLE IF NOT EXISTS blobs(
        blob_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, token TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_case ON blobs(case_id)")
    return c

def put_pii(case_id, fields):
    blob_id = str(uuid.uuid4())
    token = _fernet().encrypt(json.dumps(fields, sort_keys=True).encode()).decode()
    c = _connect()
    try:
        c.execute("INSERT INTO blobs(blob_id,case_id,token) VALUES(?,?,?)", (blob_id, case_id, token))
        return blob_id
    finally:
        c.close()

def get_pii(blob_id):
    c = _connect()
    try:
        row = c.execute("SELECT token FROM blobs WHERE blob_id=?", (blob_id,)).fetchone()
    finally:
        c.close()
    if row is None: return None
    return json.loads(_fernet().decrypt(row["token"].encode()))

def erase_pii(case_id):
    c = _connect()
    try:
        cur = c.execute("DELETE FROM blobs WHERE case_id=?", (case_id,))
        return cur.rowcount
    finally:
        c.close()
