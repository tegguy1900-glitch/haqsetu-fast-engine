"""Deterministic full-spectrum seed + render + assertions. Run: python -m sdm.run_dashboard_demo"""
import os, json, time
from core import event_bus, sla_clock as clock
from sabha import push_sdm
from sdm import view_model

GP1, GP2, GP3, DATE = "GP-BOARD", "GP-BOARD2", "GP-BOARD3", "2026-10-21"

def seed():
    event_bus.init()
    # Sabha1: signed, 1 grievance (-> Glue handpump case), 3 commitments (1 unresolvable)
    m1 = {"gp": GP1, "meeting_date": DATE, "decisions": ["approved Rs 50,000 for Ward 3 drain"],
          "funds_mentioned": [{"amount": 50000, "purpose": "drain"}], "grievances": [],
          "action_items": [
              {"owner": "secretary", "task": "I will fix the streetlights in Ward 2 by Friday.", "deadline_raw": "by Friday"},
              {"owner": "sarpanch",  "task": "Arrange water tanker soon.", "deadline_raw": "soon"},
              {"owner": "mitra",     "task": "Deliver school books by 2026-10-22.", "deadline_raw": "by 2026-10-22"},
          ]}
    # give Sabha1 a grievance so the Glue opens a handpump civic case linked to it
    m1["grievances"] = [{"category": "handpump", "ward": 4, "summary": "The handpump in Ward 4 is broken, no water."}]
    r1 = push_sdm.push(m1, signed=True, open_civic_from_grievances=True)
    mh1 = r1["minutes_hash"][:12]
    glue_handpump = r1["civic_cases_opened"][0]   # HS-GP-BOARD-2026-10-21-0

    # plain civic seeds (no glue)
    event_bus.emit("mitra", "HS-BOARD-DRAIN", "civic_intake", {"category": "drain", "ward": 3})
    event_bus.emit("mitra", "HS-BOARD-LIGHT", "civic_intake", {"category": "streetlight", "ward": 2})
    event_bus.emit("mitra", "HS-BOARD-ROAD", "civic_intake", {"category": "road", "ward": 1})
    event_bus.emit("engineer", "HS-BOARD-ROAD", "civic_closure_verified", {"photo_hash": "FIX-EVID-9999"})
    event_bus.emit("mitra", "HS-BOARD-WELL", "civic_intake", {"category": "well", "ward": 5})      # default 168h -> slate
    event_bus.emit("mitra", "HS-BOARD-BRIDGE", "civic_intake", {"category": "bridge", "ward": 6})  # default 168h -> will get soft breach

    # Sabha2: signed + a far-future commitment (slate) ; will be acked -> green sabha
    m2 = {"gp": GP2, "meeting_date": DATE, "decisions": [], "funds_mentioned": [], "grievances": [],
          "action_items": [{"owner": "secretary", "task": "Submit annual report by 2030-01-01.", "deadline_raw": "by 2030-01-01"}]}
    r2 = push_sdm.push(m2, signed=True)
    # Sabha3: unsigned/contested -> red sabha
    m3 = {"gp": GP3, "meeting_date": DATE, "decisions": [], "funds_mentioned": [], "grievances": [], "action_items": []}
    push_sdm.push(m3, signed=False, refuse_reason="quorum_not_met")
    return mh1, r2, glue_handpump

def main():
    mh1, r2, glue_hp = seed()
    print("[OK] seeded 3 sabhas + 6 civic (1 closed, 1 glue-linked) ; Sabha2 row id =", r2["event"]["seq"])
    # find Sabha2's sqlite row id to ack it (green)
    sabha2_row = next(x[0] for x in push_sdm.all_rows() if x[1] == GP2)
    now = time.time() + 100 * 3600          # injectable clock; no signature tampering

    res = clock.tick(now=now)               # escalate (default) -> red breaches on short clocks
    print(f"[OK] tick(+100h) emitted {len(res['emitted'])} escalate sla_breach")

    # manual SOFT-mode breach on the bridge (168h, not yet daemon-breached at +100h)
    # -> proves the board colors per payload.mode, independent of daemon MODE
    event_bus.emit("sdm", "HS-BOARD-BRIDGE", "sla_breach",
                   {"kind": "civic", "case_id": "HS-BOARD-BRIDGE", "category": "bridge",
                    "sla_hours": 168, "hours_overdue": round((now - (time.time()))/3600,1),
                    "mode": "soft", "escalated_to": None})
    print("[OK] manual soft-mode breach emitted for bridge (per-payload policy)")

    # fulfill the deliver-books commitment -> green (overrides its red breach)
    clock.fulfill(f"COMMIT-{mh1}-2", owner="mitra")
    push_sdm.ack(sabha2_row)                # Sabha2 -> green acked
    print(f"[OK] fulfilled COMMIT-{mh1}-2 ; acked Sabha2 row {sabha2_row}")

    v = view_model.build(now=now)
    print("\n---------------- VIEW-MODEL (compact) ----------------")
    print("integrity:", v["integrity"])
    print("counts   :", v["counts"])
    for grp in ("civic", "commitments", "sabhas"):
        print(f"\n[{grp.upper()}]")
        for it in v[grp]:
            extra = ""
            if grp == "civic" and it.get("from_sabha"): extra = f"  <- {it['from_sabha']}"
            if grp == "commitments" and it.get("raw_deadline"): extra = f"  phrase='{it['raw_deadline']}'"
            print(f"  {it['color']:5s} {it['state']:18s} {it.get('case_id') or it.get('id') or (str(it['gp'])+' '+str(it['date']))}{extra}")

    # ---- assertions: every color present in every section where expected ----
    def colors(sec): return {it["color"] for it in v[sec]}
    A = []
    A.append(("civic has red",    "red" in colors("civic")))
    A.append(("civic has amber",  "amber" in colors("civic")))     # bridge soft-breach
    A.append(("civic has slate",  "slate" in colors("civic")))     # well in-SLA
    A.append(("civic has green",  "green" in colors("civic")))     # road closed
    A.append(("glue linkage",     any(c.get("from_sabha") and c["case_id"]==glue_hp for c in v["civic"])))
    A.append(("comm red",         "red" in colors("commitments")))      # by-Friday
    A.append(("comm amber(skip)", "amber" in colors("commitments")))    # soon -> needs_date
    A.append(("comm green(ful)",  "green" in colors("commitments")))    # deliver-books
    A.append(("comm slate",       "slate" in colors("commitments")))    # 2030 report
    A.append(("skip surfaces reason", any(c["state"]=="needs_date" and c.get("reason") for c in v["commitments"])))
    A.append(("sabha red(contest)","red" in colors("sabhas")))
    A.append(("sabha amber(ack)", "amber" in colors("sabhas")))
    A.append(("sabha green(acked)","green" in colors("sabhas")))
    A.append(("chain ok header",  v["integrity"]["chain_ok"] is True))
    # renderer color fn, both branches (proves soft-breach mapping w/o double-breach data)
    A.append(("_color escalate", view_model._color_for_breach({"mode":"escalate"})=="red"))
    A.append(("_color soft",     view_model._color_for_breach({"mode":"soft"})=="amber"))
    print("\n---------------- ASSERTIONS ----------------")
    allok = True
    for name, ok in A:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}"); allok = allok and ok
    # dump full json for the live server to serve identically
    with open(os.path.join(os.environ.get("HAQ_DASH_DIR","/tmp/haqdash"), "view_seed.json"), "w") as f:
        json.dump(v, f, sort_keys=True)
    print("\n[RESULT]", "ALL GREEN" if allok else "SOME FAILED")
    if not allok: raise SystemExit(1)

if __name__ == "__main__":
    main()
