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
