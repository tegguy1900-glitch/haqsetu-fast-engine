"""
Haq Setu - Propagation Outbox (the "dropout queues, never 500s, never loses" layer).
SCOPE: this queues UPWARD DELIVERIES (village -> block/SDM over HTTP). It does NOT
queue the local ledger write -- that is synchronous and offline-safe by design
(Never-Forget must not wait for a tower). Ordering guarantee, enforced by callers:
    1) event_bus.emit(...)  -> local chain append  (durable NOW, uplink irrelevant)
    2) outbox.enqueue(...)  -> propagation intent  (best-effort, retried, queued)
If the uplink is dead at step 2, the event is ALREADY safe locally; only the upward
copy waits. Dead letters are NEVER deleted -- a failed delivery stays visible as a
red flag (Never-Forget at the propagation layer), not silent loss.
Stdlib only. Idempotent by key (a retried emit cannot double-apply upstream).
"""
import os, json, time, sqlite3, threading, urllib.request, urllib.error, socket

DB_PATH = os.environ.get("HAQ_OUTBOX", "core/outbox.db")
_LOCK = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.execute("""CREATE TABLE IF NOT EXISTS deliveries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, url TEXT, method TEXT, payload TEXT,
        created REAL, attempts INTEGER DEFAULT 0, last_error TEXT,
        status TEXT DEFAULT 'pending', next_try REAL DEFAULT 0)""")
    c.commit(); return c

def enqueue(key, url, payload, method="POST"):
    """Insert a propagation intent. Idempotent: existing key -> no dup, returns 0."""
    body = json.dumps(payload, sort_keys=True)
    with _LOCK, _conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO deliveries(key,url,method,payload,created,next_try)"
            " VALUES(?,?,?,?,?,?)", (key, url, method, body, time.time(), 0))
        return cur.rowcount          # 1 inserted, 0 already-present

def pending(now=None, force=False):
    now = now if now is not None else time.time()
    with _conn() as c:
        if force:
            return c.execute(
                "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
                " WHERE status='pending' ORDER BY id").fetchall()
        return c.execute(
            "SELECT id,key,url,method,payload,attempts,status FROM deliveries"
            " WHERE status='pending' AND next_try<=? ORDER BY id", (now,)).fetchall()

def _backoff(n):
    return min(60.0, float(2 ** n))

def flush_once(now=None, timeout=3, max_attempts=5, force=False):
    """Attempt every due pending delivery. Returns {acked,failed,dead,still_pending}
    as lists of keys. Non-2xx / refused / timeout => failed attempt; after
    max_attempts => status 'dead' (row KEPT, payload intact).
    force=True => ignore next_try backoff and attempt ALL pending now (a manual 'sync'
    tap by the Mitra must retry immediately, not wait out exponential backoff; the
    background flush_loop keeps force=False so it respects backoff)."""
    now = now if now is not None else time.time()
    acked, failed, dead, still = [], [], [], []
    for rid, key, url, method, payload, attempts, _st in pending(now, force=force):
        data = payload.encode() if method.upper() != "GET" else None
        req = urllib.request.Request(url, data=data, method=method.upper(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ok = 200 <= getattr(r, "status", 200) < 300
            err = None if ok else f"non-2xx {getattr(r,'status','?')}"
        except urllib.error.HTTPError as e:
            ok, err = False, f"HTTP {e.code}"
        except (urllib.error.URLError, socket.timeout, OSError, ValueError) as e:
            ok, err = False, f"{type(e).__name__}: {str(e)[:120]}"
        with _LOCK, _conn() as c:
            if ok:
                c.execute("UPDATE deliveries SET status='acked', last_error=NULL WHERE id=?", (rid,))
                acked.append(key)
            else:
                na = attempts + 1
                if na >= max_attempts:
                    c.execute("UPDATE deliveries SET attempts=?, last_error=?, status='dead' WHERE id=?",
                              (na, err, rid))
                    dead.append(key)
                else:
                    c.execute("UPDATE deliveries SET attempts=?, last_error=?, next_try=? WHERE id=?",
                              (na, err, now + _backoff(na), rid))
                    failed.append(key); still.append(key)
            c.commit()
    return {"acked": acked, "failed": failed, "dead": dead, "still_pending": still}

def has_key(key):
    with _conn() as c:
        return c.execute("SELECT 1 FROM deliveries WHERE key=? LIMIT 1", (key,)).fetchone() is not None

def stats():
    with _conn() as c:
        rows = c.execute("SELECT status, COUNT(*) FROM deliveries GROUP BY status").fetchall()
    d = {s: n for s, n in rows}
    return {"pending": d.get("pending", 0), "acked": d.get("acked", 0),
            "dead": d.get("dead", 0), "total": sum(d.values())}

def dead_rows():
    """Dead letters, payload intact -- the visible red-flag list."""
    with _conn() as c:
        return c.execute("SELECT key,url,attempts,last_error,payload FROM deliveries"
                         " WHERE status='dead' ORDER BY id").fetchall()

def flush_loop(interval=30, max_attempts=5, stop=None, log=None):
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            r = flush_once(max_attempts=max_attempts)
            if log and (r["acked"] or r["dead"]):
                log(f"[outbox] acked={len(r['acked'])} dead={len(r['dead'])} "
                    f"pending={stats()['pending']}")
        except Exception as e:                       # a flush crash must not kill the loop
            if log: log(f"[outbox] flush error (kept looping): {e}")
        stop.wait(interval)
