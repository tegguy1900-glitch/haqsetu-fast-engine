"""Dual-mode proof of the SLA clock.
  python -m core.run_clock_demo                 -> orchestrates TWO isolated subprocesses
                                                   (one per mode, fresh chain each) and
                                                   prints the policy-gate diff.  exit 0/1.
  python -m core.run_clock_demo --mode escalate -> runs ONE mode (used by the orchestrator).
Original bug: main() ran escalate then soft in ONE process on ONE shared chain, so soft
inherited escalate's breaches, emitted 0, and the diff crashed on StopIteration."""
import os, sys, json, time
from core import event_bus, sla_clock as clock

GP, DATE = "GP-CLOCK", "2026-10-21"   # 2026-10-21 is a Wednesday

def _seed():
    event_bus.init()
    t1 = event_bus.emit("mitra", "HS-CLOCK-1", "civic_intake",
                        {"category": "handpump", "ward": 4})["timestamp"]
    t2 = event_bus.emit("mitra", "HS-CLOCK-2", "civic_intake",
                        {"category": "drain", "ward": 3})["timestamp"]
    event_bus.emit("mitra", "HS-CLOCK-3", "civic_intake", {"category": "road", "ward": 1})
    event_bus.emit("engineer", "HS-CLOCK-3", "civic_closure_verified", {"photo_hash": "ok"})
    minutes = {"gp": GP, "meeting_date": DATE, "minutes_hash": "deadbeefcafe1234",
               "decisions": [], "funds_mentioned": [], "grievances": [],
               "action_items": [
                   {"owner": "secretary", "task": "I will fix the streetlights in Ward 2 by Friday.",
                    "deadline_raw": "by Friday"},                 # -> 2026-10-23
                   {"owner": "sarpanch",  "task": "Arrange water tanker soon.", "deadline_raw": "soon"},                      # -> UNRESOLVABLE
               ]}
    event_bus.emit("sarpanch", f"SABHA-{GP}-{DATE}", "sabha_signed", minutes)
    return max(t1, t2)

def _show(tag, st):
    print(f"  {tag}: open_civic={st['open_civic']} closed={st['closed_civic']} "
          f"breached_civic={st['breached_civic']}")
    print(f"           commitments tracked={st['tracked_commitments']} "
          f"breached={st['breached_commitments']} fulfilled={st['fulfilled_commitments']} "
          f"skipped={[s['id'] for s in st['skipped_commitments']]}")

def run(mode):
    os.environ["HAQ_SLA_MODE"] = mode
    import importlib; importlib.reload(clock)
    print(f"\n===================== MODE = {mode.upper()} =====================")
    latest = _seed()
    print("[OK] seeded 3 civic (1 closed) + 1 sabha (2 commitments, 1 unresolvable)")
    _show("before tick", clock.status())
    future = latest + 100 * 3600          # injectable clock; no signature tampering
    res = clock.tick(now=future)
    for w in res["warnings"]:
        print(w)
    print(f"[OK] tick(now=+100h) emitted {len(res['emitted'])} sla_breach:")
    for e in res["emitted"]:
        p = e["payload"]
        print(f"     - kind={p['kind']:11s} id={e['case_id']:18s} "
              f"mode={p['mode']:8s} escalated_to={p['escalated_to']} "
              f"overdue={p['hours_overdue']}h")
    _show("after tick ", res["status"])
    ck = [c for c in res["status"]["tracked_commitments"] if c.endswith("-0")]
    if ck:
        clock.fulfill(ck[0], owner="secretary")
        res2 = clock.tick(now=future)
        print(f"[OK] after fulfill({ck[0]}): re-tick emitted {len(res2['emitted'])} (idempotent=0 expected)")
        _show("final      ", res2["status"])
    else:
        res2 = res
    ok, bad, why = event_bus.verify()
    print(f"[OK] chain verify ok={ok} ({why})  chain_len={len(event_bus.tail(999))}")
    return res["emitted"]

def _orchestrate():
    import subprocess, tempfile, shutil
    print("##### CLOCK (two modes isolated into separate processes) #####")
    procs, emits = [], {}
    for mode in ("escalate", "soft"):
        d = tempfile.mkdtemp(prefix=f"haqclk_{mode}_")
        emit = os.path.join(d, "emit.json")
        env = dict(os.environ)
        env.update({"HAQ_CHAIN": f"{d}/chain.jsonl", "HAQ_VAULT": f"{d}/vault.jsonl",
                    "HAQ_KEYS": f"{d}/keys", "HAQ_VAULT_KEY": f"{d}/pii.key",
                    "SDM_DB": f"{d}/sdm.db", "HAQ_OUTBOX": f"{d}/outbox.db",
                    "HAQ_SLA_MODE": mode})
        p = subprocess.Popen([sys.executable, "-m", "core.run_clock_demo",
                              "--mode", mode, "--emit", emit], env=env)
        procs.append((mode, p, d, emit))
    rc = 0
    for mode, p, d, emit in procs:
        p.wait(); rc |= p.returncode
    if rc != 0:
        print(f"[FAIL] a mode subprocess exited nonzero (rc={rc})")
        for _,_,d,_ in procs: shutil.rmtree(d, ignore_errors=True)
        sys.exit(1)
    for mode, _, _, emit in procs:
        with open(emit) as f: emits[mode] = json.load(f)
    for _,_,d,_ in procs: shutil.rmtree(d, ignore_errors=True)
    esc, sof = emits["escalate"], emits["soft"]
    pe = next((x for x in esc if x["payload"]["kind"] == "civic"), None)
    ps = next((x for x in sof if x["payload"]["kind"] == "civic"), None)
    print("\n---------------- POLICY-GATE DIFF (the knob, not a silent choice) ----------------")
    if pe is None or ps is None:
        print(f"[FAIL] missing civic breach: escalate={pe is not None} soft={ps is not None}")
        sys.exit(1)
    print(f"  escalate -> escalated_to={pe['payload']['escalated_to']!r}  (dashboard RED + upward push)")
    print(f"  soft     -> escalated_to={ps['payload']['escalated_to']!r}  (dashboard AMBER, no push)")
    print("  [OK] same event type, same contract; policy carried in payload, flipped by env var")
    ok = (pe["payload"]["escalated_to"] == "block") and (ps["payload"]["escalated_to"] is None)
    print("[RESULT]", "CLOCK GREEN" if ok else "CLOCK FAILED")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
        emit = sys.argv[sys.argv.index("--emit") + 1] if "--emit" in sys.argv else None
        em = run(mode)
        if emit:
            with open(emit, "w") as f: json.dump(em, f)
        sys.exit(0)
    else:
        _orchestrate()
