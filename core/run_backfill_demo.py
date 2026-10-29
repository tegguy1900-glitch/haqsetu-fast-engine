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
