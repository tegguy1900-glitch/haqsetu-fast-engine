"""Haq Setu - Backfill sweep. Propagates local-only history once an uplink is set.
Idempotent WITHOUT outbox.has_key: relies on outbox.enqueue's INSERT-OR-IGNORE dedup
(returns 1 inserted / 0 dup). Builds envelopes from the CHAIN payload (PII-clean by the
ledger guard); never reads the vault. Excludes local-only evidence (sabha_chunk_hashed)."""
import os,sys,threading
from core import event_bus,outbox
from ledger import chain as _chain
PROPAGATABLE={"civic_intake","entitlement_petition_issued","sabha_signed","sla_breach","official_rejection"}
_COPY=("category","ward","schemes","confidence","receipt_id","minutes_hash","reason_code","escalated_to","mode")
def sweep(block_url,event_types=None):
    if not event_bus.is_ready(): event_bus.init()
    types=set(event_types) if event_types else PROPAGATABLE
    seen=set(); enq=[]
    for ev in _chain.get_chain():
        if ev["event_type"] not in types: continue
        cid=ev["case_id"]
        if cid in seen: continue
        seen.add(cid)
        env={"kind":ev["event_type"],"case_id":cid,"seq":ev["seq"]}
        pl=ev.get("payload",{})
        for f in _COPY:
            if f in pl: env[f]=pl[f]
        if outbox.enqueue(f"DEL-{cid}",block_url,env)==1: enq.append(cid)
    return {"enqueued":enq,"scanned":len(seen)}
def loop(block_url,interval=300,stop=None,log=print,event_types=None):
    stop=stop or threading.Event()
    while not stop.is_set():
        try:
            r=sweep(block_url,event_types=event_types)
            if r["enqueued"]: log(f"[backfill] enqueued {len(r['enqueued'])}")
        except Exception as e: log(f"[backfill] error (looping): {e}")
        stop.wait(interval)
if __name__=="__main__":
    event_bus.init(); url=(os.environ.get("HAQ_BLOCK_URL","") or "").strip()
    if not url: print("[backfill] no uplink; offline booth"); sys.exit(0)
    loop(url,interval=int(os.environ.get("HAQ_BACKFILL_INTERVAL","300")))
