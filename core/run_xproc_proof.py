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
