"""Storage-layer proof. Run: python -m core.run_wal_migration   (forge via HAQ_WAL_FORGE=1)"""
import os, sys, json, time, sqlite3, threading
from core import event_bus
from ledger import chain as _chain, pii_store as _pii

FAIL = []
def chk(name, cond, extra=""):
    print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' :: '+extra) if extra else ''}")
    if not cond: FAIL.append(name)

def _journal_mode():
    c = sqlite3.connect(_chain.DB_PATH)
    try: return c.execute("PRAGMA journal_mode").fetchone()[0]
    finally: c.close()

def part1():
    print("\n##### PART 1 : public-API parity #####")
    for fn in ("load_or_create_keys","verify_chain","append_event","get_chain"):
        chk(f"chain.{fn} present", callable(getattr(_chain, fn, None)))
    chk("chain.PiiLeakError present", hasattr(_chain, "PiiLeakError"))
    for fn in ("put_pii","get_pii","erase_pii"):
        chk(f"pii.{fn} present", callable(getattr(_pii, fn, None)))
    event_bus.init()
    e1 = event_bus.emit("mitra","HS-WAL-1","entitlement_matched",{"schemes":["nsap"],"confidence":0.9})
    e2 = event_bus.emit("sarpanch","SABHA-WAL","sabha_signed",{"gp":"GP-WAL","meeting_date":"2026-10-21",
              "minutes_hash":"a"*64,"action_items":[{"owner":"secretary","task":"fix by Friday","deadline_raw":"by Friday"}],
              "grievances":[],"decisions":[],"funds_mentioned":[]})
    e3 = event_bus.emit("mitra","HS-WAL-2","civic_intake",{"category":"handpump","ward":4},
                        pii_fields={"name":"Geeta Devi","phone":"9812345678"})
    chk("3 cross-pillar events appended", [e1["seq"],e2["seq"],e3["seq"]] == [0,1,2])
    blob = e3["payload"]["pii_ref"]
    chk("vault round-trip", _pii.get_pii(blob)["name"] == "Geeta Devi")
    chk("ledger payload has NO raw PII", "name" not in json.dumps(e3["payload"]) and "9812345678" not in json.dumps(e3["payload"]))
    ok,_,why = event_bus.verify(); chk("chain verifies after parity writes", ok, why)
    chk("WAL journal_mode active", _journal_mode() == "wal", _journal_mode())

def part2():
    print("\n##### PART 2 : append-only triggers (Never-Forget @ storage) #####")
    c = _chain._connect()
    try:
        try:
            c.execute("UPDATE events SET payload='{}' WHERE seq=0"); upd=False
        except sqlite3.IntegrityError as ex: upd = "UPDATE forbidden" in str(ex)
        try:
            c.execute("DELETE FROM events WHERE seq=0"); dele=False
        except sqlite3.IntegrityError as ex: dele = "DELETE forbidden" in str(ex)
        chk("UPDATE on committed row ABORTed", upd)
        chk("DELETE on committed row ABORTed", dele)
        chk("row count unchanged after aborted mutations", len(_chain.get_chain()) == 3)
    finally:
        c.close()

def part4(T=24):
    print(f"\n##### PART 4 : {T} contending appends (fork-race kill) #####")
    base = len(_chain.get_chain())
    bar = threading.Barrier(T)
    errs = []
    def worker(i):
        try:
            bar.wait()
            if i % 2 == 0:
                event_bus.emit("mitra", f"HS-CONC-{i}", "civic_intake",
                               {"category":"drain","ward":i}, pii_fields={"name":f"C{i}","phone":f"980000000{i%10}"})
            else:
                event_bus.emit("mitra", f"HS-CONC-{i}", "civic_intake", {"category":"road","ward":i})
        except Exception as ex:
            errs.append(repr(ex))
    ths = [threading.Thread(target=worker, args=(i,)) for i in range(T)]
    [t.start() for t in ths]; [t.join() for t in ths]
    chk("no thread errored under contention", not errs, str(errs[:2]))
    ch = _chain.get_chain()
    seqs = sorted(e["seq"] for e in ch)
    chk(f"chain grew by exactly {T}", len(ch) == base + T, f"base={base} now={len(ch)}")
    chk("seqs contiguous 0..N-1 (NO fork / NO dup)", seqs == list(range(len(ch))))
    linked = all(ch[i]["prev_hash"] == ("GENESIS" if i==0 else _chain._sha256(_chain._canonical(ch[i-1])))
                 for i in range(len(ch)))
    chk("hash-chain singly linked end-to-end", linked)
    ok,_,why = event_bus.verify(); chk("chain verifies after concurrent writes", ok, why)
    pii_n = sum(1 for i in range(T) if i % 2 == 0)
    vb = _pii._connect()
    try: total = vb.execute("SELECT COUNT(*) c FROM blobs").fetchone()["c"]
    finally: vb.close()
    chk(f"vault holds all {pii_n} concurrent PII blobs intact", total >= pii_n, f"vault_rows={total}")

def part5():
    print("\n##### PART 5 : erase-on-closure + final integrity #####")
    n = _pii.erase_pii("HS-WAL-2")
    chk("erase_pii removed the closed case's blob", n == 1, f"erased={n}")
    chk("chain events survive the PII erase (Never-Forget vs right-to-be-forgotten)",
        any(e["case_id"]=="HS-WAL-2" for e in _chain.get_chain()))
    ok,_,why = event_bus.verify(); chk("FINAL chain verify ok", ok, why)
    print(f"  chain_len={len(_chain.get_chain())}  db={_chain.DB_PATH}")

def part3_forge():
    print("\n##### PART 3 : forged append (bad signature) caught on read #####")
    event_bus.init()
    payload = {"category":"handpump","ward":99}
    ph = _chain._sha256(json.dumps(payload, sort_keys=True).encode())
    c = _chain._connect(); _chain._ensure_schema(c)
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute(f"INSERT INTO events({','.join(_chain._COLS)}) VALUES(?,?,?,?,?,?,?,?,?)",
                  (0,"GENESIS",time.time(),"attacker","HS-FORGE","civic_intake",
                   json.dumps(payload,sort_keys=True), ph, "deadbeef"*16))
        c.execute("COMMIT")
    finally:
        c.close()
    pub = _chain.load_or_create_keys()[1]
    ok, bad, why = _chain.verify_chain(pub)
    chk("verify_chain REJECTS the forged row", (not ok) and why == "bad signature", f"ok={ok} seq={bad} why={why}")
    chk("forgery localized to the appended seq", bad == 0)

def main():
    if os.environ.get("HAQ_WAL_FORGE") == "1":
        part3_forge()
    else:
        part1(); part2(); part4(); part5()
    print("\n[RESULT]", "WAL MIGRATION GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)

if __name__ == "__main__":
    main()
