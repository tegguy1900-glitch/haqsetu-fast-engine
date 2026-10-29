#!/usr/bin/env bash
# Haq Setu village node. Run:  cd ~/Downloads/project1 && bash village.sh
# Parsed from DISK by bash, so the heredocs below cannot be shredded by tty paste.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true
[ -f village/__init__.py ] || { mkdir -p village && touch village/__init__.py; }

# =================== village/server.py  (audited booth node, port 8000) ===================
cat > village/server.py <<'PYEOF'
"""
Haq Setu - Village Booth Node (port 8000). AUDITED replacement for the legacy
server.py on this port. Stdlib only. Launch: python -m village.server
It is the real PRODUCER for the offline outbox: every citizen action writes the
local signed ledger SYNCHRONOUSLY (durable now, uplink irrelevant), then — only
if an uplink is configured (HAQ_BLOCK_URL) — enqueues upward propagation. With no
uplink the event is still local-durable and still tracked by the SLA clock; the
"configure-the-uplink-later backfill sweep" is a named FUTURE brick, not silently
half-built here. PII (name/phone) goes to the vault via emit(pii_fields=...); the
chain never sees raw identity. Photo bytes are hashed (SHA-256) and only the digest
lands on-chain (Never-Leak at the capture layer), mirroring sabha /record.

The two Pillar-1 brains are SEAMS with labeled stand-ins:
  match_fn        -> bind engine/rules.py match()  (reference_match_fn is a stand-in)
  fact_extract_fn -> bind your regex voice->facts (reference_fact_extract is a stand-in)
Neither is guessed at your logic; both abstain honestly when uncertain.

Routes:
  GET  /health -> {ok, chain_len, outbox, stt_backend, match_seam, fact_seam, uplink_configured}
  GET  /status -> clock.status() (civic/commitment/petition buckets) for the booth screen
  POST /voice  -> {facts? , raw_text?, lang?, pii_fields?} -> {decision, case_id, schemes,
                  receipt_id?, proof_trace?, confidence}   (never denies; abstains on unsure)
  POST /civic  -> {category, ward?, photo_b64?, gps?, pii_fields?} -> {case_id, photo_hash,
                  byte_length, sla_hours}                  (starts the SLA clock)
  POST /sync   -> manual outbox flush (Mitra taps 'sync' on signal) -> flush_once result
All writes go through core.event_bus (ONE ledger); PII guard active everywhere.
"""
import os, json, base64, hashlib, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import event_bus, entitlement as ent, sla_clock as clock, outbox
from ledger import chain as _chain

PORT = int(os.environ.get("HAQ_VILLAGE_PORT", "8000"))
HOST = os.environ.get("HAQ_VILLAGE_HOST", "127.0.0.1")   # 0.0.0.0 only behind booth LAN
BLOCK_URL = (os.environ.get("HAQ_BLOCK_URL", "") or "").strip()

# ---- SEAM 1: fact extractor (stand-in for your regex voice->facts) ----
import re as _re
_AGE = _re.compile(r"\b(\d{2})\b")
def reference_fact_extract(raw_text, lang=None):
    """STAND-IN. Replace by binding fact_extract_fn to engine's voice->facts regex.
    Pulls a few signals from free text; returns {} if nothing confident (=> downstream
    abstains, never guesses)."""
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
MATCH_FN = ent.reference_match_fn            # bind to your match() here in production
FACT_FN  = reference_fact_extract            # bind to your extractor here in production

def _uplink_enqueue(case_id, payload):
    """Enqueue upward propagation ONLY if an uplink is configured. No uplink => the
    event is already local-durable; we do NOT dead-letter a merely-unconfigured booth."""
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
    h.end_headers(); h.wfile.write(body)

def _read_json(h):
    n = int(h.headers.get("Content-Length", "0") or 0)
    raw = h.rfile.read(n) if n else b""
    return json.loads(raw) if raw else {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_OPTIONS(self): _send(self, 204, {})

    def do_GET(self):
        try: event_bus.init()
        except Exception as e: _send(self, 500, {"error": f"ledger init failed: {e}"}); return
        if self.path == "/health":
            ok, _, _ = event_bus.verify()
            _send(self, 200, {"ok": ok, "chain_len": len(_chain.get_chain()),
                              "outbox": outbox.stats(),
                              "match_seam": getattr(MATCH_FN, "__name__", "?"),
                              "fact_seam": getattr(FACT_FN, "__name__", "?"),
                              "uplink_configured": bool(BLOCK_URL)})
        elif self.path == "/status":
            _send(self, 200, clock.status())
        else:
            _send(self, 404, {"error": "not found"})

    def do_POST(self):
        try: event_bus.init()
        except Exception as e: _send(self, 500, {"error": f"ledger init failed: {e}"}); return
        try: data = _read_json(self)
        except Exception as e: _send(self, 400, {"error": f"bad json: {e}"}); return

        if self.path == "/voice":
            facts = data.get("facts")
            if not isinstance(facts, dict):
                raw = data.get("raw_text")
                if raw is None:
                    _send(self, 400, {"error": "provide facts{} or raw_text"}); return
                facts = FACT_FN(raw, data.get("lang"))
            res = ent.process_voice(data.get("actor_role", "mitra"), facts, MATCH_FN,
                                    pii_fields=data.get("pii_fields"),
                                    case_id=data.get("case_id"))
            if res["decision"] == "matched":
                _uplink_enqueue(res["case_id"], {"kind": "entitlement", "case_id": res["case_id"],
                                                 "schemes": res["schemes"], "confidence": res["confidence"]})
            out = {"decision": res["decision"], "case_id": res["case_id"],
                   "confidence": res.get("confidence")}
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
                _send(self, 400, {"error": "category required"}); return
            ph, blen = None, 0
            if data.get("photo_b64"):
                try: raw = base64.b64decode(data["photo_b64"])
                except Exception: _send(self, 400, {"error": "photo_b64 not valid base64"}); return
                ph, blen = hashlib.sha256(raw).hexdigest(), len(raw)   # bytes NEVER stored
            case_id = data.get("case_id") or f"HS-{time.strftime('%Y%m%d')}-{hashlib.sha256((cat+str(time.time())).encode()).hexdigest()[:6].upper()}"
            ev = event_bus.emit(data.get("actor_role", "mitra"), case_id, "civic_intake",
                                {"category": cat, "ward": data.get("ward"),
                                 "photo_hash": ph, "byte_length": blen, "gps": data.get("gps")},
                                pii_fields=data.get("pii_fields"))
            _uplink_enqueue(case_id, {"kind": "civic", "case_id": case_id, "category": cat,
                                      "ward": data.get("ward"), "photo_hash": ph})
            from core.sla_clock import ISSUE_CLOCKS, DEFAULT_HOURS
            _send(self, 200, {"case_id": case_id, "seq": ev["seq"], "photo_hash": ph,
                              "byte_length": blen, "sla_hours": ISSUE_CLOCKS.get(cat, DEFAULT_HOURS)})

        elif self.path == "/sync":
            _send(self, 200, outbox.flush_once(max_attempts=int(os.environ.get("HAQ_SYNC_MAXATT", "5"))))
        else:
            _send(self, 404, {"error": "not found"})

def main():
    event_bus.init()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[village] http://{HOST}:{PORT}  chain={os.environ.get('HAQ_CHAIN','ledger/chain.jsonl')}  "
          f"uplink={'SET' if BLOCK_URL else 'NONE(local-only)'}  match={getattr(MATCH_FN,'__name__','?')}")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
PYEOF

# ============ surgical launcher flip: village -> audited village.server (line-slice, echoed) ============
python - <<'PY'
import pathlib, re
p = pathlib.Path("launcher.py"); lines = p.read_text().splitlines(keepends=True)
# locate the village SERVICES entry by its unique name marker, then the NEXT structural boundary
i = next(k for k,l in enumerate(lines) if 'name="village"' in l)
j = i + 1
while j < len(lines):
    s = lines[j].strip()
    if s.startswith('dict(name=') or s == ']':
        break
    j += 1
old = "".join(lines[i:j])
new = ('    dict(name="village", module="village.server", port_env="HAQ_VILLAGE_PORT", default=8000,\n'
       '         legacy=False, reason=None),\n')
# NOTE: this points the launcher at the AUDITED village.server, NOT the unaudited legacy server.py.
# The legacy server.py file remains on disk, unreferenced by the launcher; it is neither blessed nor
# deleted. sdm_node (node/block.py) stays legacy=True/SKIP until ITS source is audited.
lines[i:j] = [new]
p.write_text("".join(lines))
print("----- launcher.py village entry: BEFORE -----"); print(old.rstrip())
print("----- launcher.py village entry: AFTER  -----"); print(new.rstrip())
print("[patch] launcher: village now -> audited village.server (legacy server.py left untouched/unreferenced)")
PY

# ===== run_launcher_demo.py REWRITE: Part B now EXPECTS village live, sdm_node still refused =====
cat > core/run_launcher_demo.py <<'PYEOF'
"""Three-part proof of the supervisor. Run: python -m core.run_launcher_demo
  PART A  outbox dropout/flap/dead-letter + local-durability-before-uplink (single writer)
  PART B  supervisor live spin: spawn proven nodes (sabha, sdm_preview, AND audited village),
          read-only health probes, kill (race-free); assert village bound+healthy and
          sdm_node (still unaudited) NOT bound.
  PART C  legacy-refusal invariant (sdm_node) + the multi-writer hazard + next brick
"""
import os, sys, json, time, socket, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import launcher
from core import event_bus, outbox, sla_clock as clock
from ledger import chain as _chain

FAIL = []
def chk(name, cond, extra=""):
    print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' :: '+extra) if extra else ''}")
    if not cond: FAIL.append(name)

class _Flap(BaseHTTPRequestHandler):
    hits = 0; lock = threading.Lock(); flip_after = 1
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        with _Flap.lock: _Flap.hits += 1; h = _Flap.hits
        code = 503 if h <= _Flap.flip_after else 200
        self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self): self.do_POST()

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def _wait_health(port, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                j = json.loads(r.read())
                if j.get("ok") is True: return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f"child :{port} never became healthy")

def part_a():
    print("\n########## PART A : outbox + local-durability (single writer) ##########")
    event_bus.init()
    flap_port = _free_port(); dead_port = _free_port()
    srv = HTTPServer(("127.0.0.1", flap_port), _Flap)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    flap_url = f"http://127.0.0.1:{flap_port}/sync"; dead_url = f"http://127.0.0.1:{dead_port}/sync"
    len0 = len(_chain.get_chain())
    ev = event_bus.emit("mitra", "HS-LAUNCH-1", "civic_intake", {"category": "handpump", "ward": 9})
    assert len(_chain.get_chain()) == len0 + 1, "local write must not depend on uplink"
    print(f"[OK] local chain durable despite dead uplink (seq={ev['seq']}, len={len(_chain.get_chain())})")
    assert outbox.enqueue("DEL-HS-LAUNCH-1", flap_url, {"case_id": ev["case_id"], "seq": ev["seq"]}) == 1
    assert outbox.enqueue("DEL-HS-LAUNCH-1", flap_url, {"case_id": ev["case_id"]}) == 0
    print("[OK] propagation intent enqueued; duplicate key ignored (idempotent)")
    r1 = outbox.flush_once(now=time.time(), max_attempts=5)
    assert r1["still_pending"] == ["DEL-HS-LAUNCH-1"] and outbox.stats()["pending"] == 1
    print(f"[OK] dropout queued (not lost): flush#1 -> {r1['failed']} still_pending={r1['still_pending']}")
    r2 = outbox.flush_once(now=time.time() + 1000, max_attempts=5)
    assert r2["acked"] == ["DEL-HS-LAUNCH-1"] and outbox.stats()["acked"] == 1
    print(f"[OK] uplink recovered -> flush#2 acked={r2['acked']}")
    outbox.enqueue("DEL-DEAD-1", dead_url, {"case_id": "HS-NEVER-SYNCED", "note": "payload-intact"})
    for i in range(5): outbox.flush_once(now=time.time() + 1000 * (i + 1), max_attempts=5)
    dr = outbox.dead_rows()
    assert len(dr) == 1 and dr[0][0] == "DEL-DEAD-1" and "payload-intact" in dr[0][4]
    print(f"[OK] dead-letter VISIBLE not deleted: key={dr[0][0]} attempts={dr[0][2]} err={dr[0][3][:24]}")
    fut = ev["timestamp"] + 100 * 3600
    tr = clock.tick(now=fut)
    kinds = [e["payload"]["kind"] for e in tr["emitted"]]
    assert "civic" in kinds and any(e["case_id"] == "HS-LAUNCH-1" for e in tr["emitted"])
    print(f"[OK] local clock still fires despite dead uplink: tick(+100h) emitted {kinds}")
    print(f"     outbox stats={outbox.stats()}  chain_len={len(_chain.get_chain())}")
    srv.shutdown()

def part_b():
    print("\n########## PART B : supervisor live spin (village now AUDITED+live; sdm_node still refused) ##########")
    sabha_port, sdm_port, vil_port = _free_port(), _free_port(), _free_port()
    bdir = os.environ.get("HAQ_B_DIR", "/tmp/haqlaunch_b"); os.makedirs(bdir, exist_ok=True)
    child_env = dict(os.environ)
    child_env.update({"HAQ_SABHA_PORT": str(sabha_port), "HAQ_SDM_PORT": str(sdm_port),
                      "HAQ_VILLAGE_PORT": str(vil_port), "HAQ_LAUNCH_LOGDIR": bdir,
                      "HAQ_CHAIN": f"{bdir}/chain.jsonl", "HAQ_VAULT": f"{bdir}/vault.jsonl",
                      "HAQ_KEYS": f"{bdir}/keys", "HAQ_VAULT_KEY": f"{bdir}/pii.key",
                      "SDM_DB": f"{bdir}/sdm.db", "HAQ_OUTBOX": f"{bdir}/outbox.db"})
    # NOTE: no HAQ_BLOCK_URL -> village runs local-only on /health probe (no propagation attempted)
    dec = launcher.plan(child_env); by = {d["name"]: d for d in dec}
    chk("village now LAUNCH (audited village.server)", by["village"]["action"] == "launch", by["village"]["module"])
    chk("sdm_node STILL SKIP (node/block.py unaudited)", by["sdm_node"]["action"] == "SKIP")
    chk("sabha + sdm_preview launch", by["sabha"]["action"] == "launch" and by["sdm_preview"]["action"] == "launch")
    val = launcher.validate(child_env)
    chk("import validation: village ok (audited)", val["village"] == "ok", val["village"])
    chk("import validation: sdm_node REFUSED (unaudited)", val["sdm_node"].startswith("REFUSED-import"), val["sdm_node"])
    chk("import validation: sabha + sdm_preview ok", val["sabha"] == "ok" and val["sdm_preview"] == "ok")
    kids = launcher.spawn(dec, child_env)
    names = {k[0] for k in kids}
    chk("spawned exactly sabha+sdm_preview+village", names == {"sabha","sdm_preview","village"}, str(names))
    time.sleep(2.2)
    hs, hd, hv = _wait_health(sabha_port), _wait_health(sdm_port), _wait_health(vil_port)
    chk("village child healthy + reports uplink NONE (local-only probe)", hv.get("ok") is True and hv.get("uplink_configured") is False, str(hv))
    chk("village child names its seams (match/fact stand-ins)", "match_seam" in hv and "fact_seam" in hv, str({k:hv.get(k) for k in ('match_seam','fact_seam')}))
    chk("sabha + sdm children healthy", hs.get("ok") is True and hd.get("ok") is True)
    # runtime proof: village port IS bound (we spawned it); sdm_node port is NOT (refused)
    def bound(port):
        s = socket.socket(); s.settimeout(0.5)
        try: s.connect(("127.0.0.1", port)); return True
        except Exception: return False
        finally: s.close()
    chk("village port BOUND (audited node live)", bound(vil_port))
    chk("sdm_node port NOT bound (still refused at runtime)", not bound(by["sdm_node"]["port"]))
    stop = threading.Event(); launcher._shutdown(kids, stop)
    for name, p, logp, lf in kids: chk(f"child {name} terminated", p.poll() is not None, f"rc={p.poll()}")

def part_c():
    print("\n########## PART C : invariants + the hazard we will NOT ship silently ##########")
    print("  INVARIANT 1  supervisor refuses UNAUITED legacy code by NAME+REASON (sdm_node/node/block.py),")
    print("               even with the file present on disk (never-guess @ process layer). The village row")
    print("               is now LAUNCH because it points at the AUDITED village.server, not legacy server.py.")
    print("  INVARIANT 2  outbox queues upward propagation; local ledger write is synchronous & offline-safe.")
    print("  INVARIANT 3  dead letters are KEPT & visible (Never-Forget @ propagation layer).")
    print("  INVARIANT 4  idempotent by key -> a retried emit cannot double-apply upstream.")
    print("  HAZARD (closed by the SQLite-WAL migration, proven in core.run_wal_migration): two local")
    print("  processes once shared one chain.jsonl via O_APPEND -- not a production guarantee. SQLite")
    print("  BEGIN IMMEDIATE serializes writers; WAL lets readers run concurrent. The live spin above is")
    print("  read-only (health probes, zero writes) so it is race-free BY CONSTRUCTION; the cross-process")
    print("  WRITE proof is core.run_xproc_proof (240 rows, two OS processes, contiguous + parent-verifies).")

def main():
    part_a(); part_b(); part_c()
    print("\n[RESULT]", "OPTION-1 GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)

if __name__ == "__main__":
    main()
PYEOF

# ============ run_village_demo.py: producer-layer dropout + offline-local-durable + seams ============
cat > core/run_village_demo.py <<'PYEOF'
"""Village node proof (spawns the real server as a subprocess; demo only speaks HTTP).
Run: python -m core.run_village_demo   (sandboxed via env by the caller)
Phase A (uplink = flappy mock): voice->receipt+PII-vault, civic->photo-hash-not-bytes,
        sync#1->503 pending, sync#2->ack, garbage-voice->abstain (no enqueue).
Phase B (NO uplink): civic emit -> local-durable + open in /status + outbox total==0
        (a merely-unconfigured booth is never wrongly dead-lettered).
"""
import os, sys, json, time, base64, socket, threading, urllib.request, urllib.error, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

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

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1",0)); p = s.getsockname()[1]; s.close(); return p

def _wait(port, path="/health", timeout=10.0):
    t0 = time.time()
    while time.time()-t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                j = json.loads(r.read())
                if j.get("ok") is True or path != "/health": return j
        except Exception: pass
        time.sleep(0.15)
    raise RuntimeError(f":{port}{path} never healthy")

def _post(port, path, obj):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
                                 headers={"Content-Type":"application/json"}, method="POST")
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
    print("\n##### PHASE A : uplink flappy (producer-layer dropout -> queue -> recover) #####")
    import tempfile; d = tempfile.mkdtemp(prefix="haqvil_a_")
    flap_port = _free_port(); srv = HTTPServer(("127.0.0.1", flap_port), _Flap)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p, port = _spawn_village(d, block_url=f"http://127.0.0.1:{flap_port}/sync")
    try:
        h = _wait(port)
        chk("A village up + uplink configured", h.get("ok") is True and h.get("uplink_configured") is True, str(h))
        chk("A seams are labeled stand-ins", "reference" in str(h.get("match_seam","")) and "reference" in str(h.get("fact_seam","")), str({k:h.get(k) for k in ('match_seam','fact_seam')}))
        # voice (structured facts) -> matched + receipt; PII to vault only
        v = _post(port, "/voice", {"facts": {"age": 65, "is_widow": True, "has_pucca_house": False},
                                   "pii_fields": {"name": "Lakshmi Bai", "phone": "9900112233"}})
        chk("A voice matched 3 schemes", v.get("decision") == "matched" and len(v.get("schemes",[])) == 3, str(v.get("schemes")))
        chk("A voice issued receipt", str(v.get("receipt_id","")).startswith("HR-"), v.get("receipt_id"))
        chk("A voice has proof_trace", bool(v.get("proof_trace")))
        # raw_text path through the fact-extract seam
        v2 = _post(port, "/voice", {"raw_text": "Main 70 saal ki vidhwa hoon, mera kacha ghar hai",
                                    "pii_fields": {"name": "Durga", "phone": "9811122233"}})
        chk("A raw_text -> facts -> matched", v2.get("decision") == "matched" and len(v2.get("schemes",[])) >= 1, str(v2.get("schemes")))
        # garbage voice -> abstain (never deny), and NO enqueue
        v3 = _post(port, "/voice", {"raw_text": "hello there nothing relevant"})
        chk("A garbage voice ABSTAINED (not denied)", v3.get("decision") == "abstained", str(v3.get("reason")))
        # civic with photo -> hash on chain, bytes NOT stored
        c = _post(port, "/civic", {"category": "handpump", "ward": 4,
                                   "photo_b64": base64.b64encode(b"BROKEN-PUMP-PHOTO-BYTES").decode(),
                                   "pii_fields": {"name": "Sita", "phone": "9999888877"}})
        chk("A civic photo hashed (64 hex)", c.get("photo_hash") and len(c["photo_hash"]) == 64, str(c.get("photo_hash"))[:12])
        chk("A civic byte_length recorded, bytes not on chain", c.get("byte_length") == len(b"BROKEN-PUMP-PHOTO-BYTES"))
        # dropout: sync#1 -> 503 -> pending ; sync#2 -> 200 -> ack
        s1 = _post(port, "/sync", {})
        chk("A sync#1 queued on 503 (not lost)", s1.get("still_pending") and not s1.get("acked"), str({k:s1.get(k) for k in ('acked','still_pending','dead')}))
        s2 = _post(port, "/sync", {})
        chk("A sync#2 acked after uplink recovered", s2.get("acked"), str({k:s2.get(k) for k in ('acked','still_pending','dead')}))
        # chain hygiene: no raw PII, no photo bytes anywhere on the local chain
        import sqlite3
        cc = sqlite3.connect(f"{d}/chain.db")
        blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events"))
        cc.close()
        chk("A chain has NO raw PII names", "Lakshmi" not in blob and "Durga" not in blob and "Sita" not in blob)
        chk("A chain has NO raw phone digits", "9900112233" not in blob and "9811122233" not in blob and "9999888877" not in blob)
        chk("A chain has NO photo bytes", "BROKEN-PUMP-PHOTO-BYTES" not in blob)
        chk("A chain DOES carry photo HASH", c["photo_hash"] in blob)
        # abstain produced no propagation row (only matched+civic enqueued)
        ob = _wait(port, "/health").get("outbox", {})
        chk("A outbox acked>=2 (voice+voice2+civic minus abstain; >=2 propagated)", ob.get("acked",0) >= 2, str(ob))
    finally:
        p.terminate(); p.wait(timeout=5); srv.shutdown()

def phase_b():
    print("\n##### PHASE B : NO uplink (offline booth = local-durable, never wrongly dead-lettered) #####")
    import tempfile; d = tempfile.mkdtemp(prefix="haqvil_b_")
    p, port = _spawn_village(d, block_url=None)   # HAQ_BLOCK_URL unset
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
        # local chain still holds the event (durable) with no raw PII
        import sqlite3
        cc = sqlite3.connect(f"{d}/chain.db"); blob = "".join(r[0] for r in cc.execute("SELECT payload FROM events")); cc.close()
        chk("B local chain durable (civic event present)", c["case_id"] in blob)
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

echo "########## GATES (each in its own fresh sandbox) ##########"
GATES=""
gate () {
  local label="$1"; shift
  local d; d="$(mktemp -d /tmp/vgate_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" \
      HAQ_VAULT_KEY="$d/pii.key" SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" \
      HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 7
  local rc="${PIPESTATUS[0]}"
  printf '>>> %-12s exit=%s\n' "$label" "$rc"
  rm -rf "$d"; GATES="$GATES $label=$rc"
}
gate "village"     python -m core.run_village_demo
gate "launch"      python -m core.run_launcher_demo
gate "wal"         python -m core.run_wal_migration
gate "clock"       python -m core.run_clock_demo
gate "xproc"       python -m core.run_xproc_proof
gate "pillar1"     python -m core.run_pillar1_demo
gate "sabha"       python -m sabha.run_sabha
gate "dash"        python -m sdm.run_dashboard_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "ALL GATES GREEN :: village node live+audited on 8000, sdm_node still refused, dropout proven at producer layer, offline local-durable, nothing regressed" || echo "SOME GATE RED :: see exit!=0 above"
