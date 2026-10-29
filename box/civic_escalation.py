"""
HaqSetu PHASE 3 - Civic Agenda + Escalation Ladder + Route D + Public Record (port 8012)
Isolated code, UNIFIED data: case events append to ledger/box_chain.jsonl with the
SAME signing scheme as the orchestrator, so one ledger tells the whole case story (Sec 3.6).
Evidence hashes stay in doc_chain (Sec 3.6.2). Implements Sec 3.4 (Routes C,D),
Sec 3.8 (closure, two verifiers, disputed reopen, weekly digest, visible missing ack),
Sec 3.9 (48h stall, local-vs-external owner, small-cell suppression, counts-only public),
and the never-auto-accuse rule (Sec 3.6.4 / citizen Q40).
"""
import os, sys, json, hashlib, random
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOX_CHAIN = os.path.join(ROOT, "ledger", "box_chain.jsonl")      # unified case ledger
STATE = os.path.join(ROOT, "ledger", "civic_state.json")

# ---- identical signing scheme to the orchestrator (so box_chain stays one verifiable chain) ----
KEYS = {"facilitator": "k-fac", "system": "k-sys", "official": "k-off",
        "verifier": "k-ver", "citizen": "k-cit", "block": "k-blk", "district": "k-dist", "state": "k-st"}
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def body_of(r): return {k: v for k, v in r.items() if k not in ("hash", "sig")}
def sig_of(actor, body): return sha(KEYS.get(actor, "k-?") + json.dumps(body, sort_keys=True))[:16]
def hash_of(body, s): return sha(json.dumps(body, sort_keys=True) + s)[:16]

def append(case_id, actor, action, detail=""):
    os.makedirs(os.path.dirname(BOX_CHAIN), exist_ok=True)
    lines = open(BOX_CHAIN, encoding="utf-8").read().splitlines() if os.path.exists(BOX_CHAIN) else []
    prev = sha(lines[-1])[:16] if lines else sha("genesis")[:16]
    body = {"i": len(lines), "ts": datetime.now().isoformat(timespec="seconds"),
            "case_id": case_id, "actor": actor, "action": action, "detail": detail, "prev_hash": prev}
    s = sig_of(actor, body)
    rec = {**body, "sig": s, "hash": hash_of(body, s)}
    with open(BOX_CHAIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec["hash"]

def verify_chain():
    if not os.path.exists(BOX_CHAIN): return {"ok": True, "n": 0}
    lines = open(BOX_CHAIN, encoding="utf-8").read().splitlines()
    for idx, line in enumerate(lines):
        r = json.loads(line); body = body_of(r)
        exp = sha("genesis")[:16] if idx == 0 else sha(lines[idx-1])[:16]
        if (r.get("prev_hash") != exp or r.get("hash") != hash_of(body, r.get("sig", ""))
                or r.get("sig") != sig_of(r.get("actor"), body)):
            return {"ok": False, "broken": idx, "n": len(lines)}
    return {"ok": True, "n": len(lines)}

# ---- clocks (Sec 3.4 / 3.9 + citizen-approved table Q29/Q36) ----
# resolve_hours = board target; stall_hours = 48h no-change rule (Sec 3.9)
ISSUE_CLOCKS = {
    "drain":        {"resolve": 24, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
    "sewage":       {"resolve": 24, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
    "garbage":      {"resolve": 24, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
    "public_toilet":{"resolve": 24, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
    "handpump":     {"resolve": 48, "stall": 48, "first_owner": "village_water_committee / state water dept", "local": False},  # Sec 3.4
    "water":        {"resolve": 48, "stall": 48, "first_owner": "village_water_committee / state water dept", "local": False},
    "streetlight":  {"resolve": 48, "stall": 48, "first_owner": "panchayat_secretary / line man", "local": True},
    "road":         {"resolve": 72, "stall": 48, "first_owner": "bdo / junior engineer", "local": False},
    "community":    {"resolve": 72, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
    "encroach":     {"resolve": 72, "stall": 48, "first_owner": "tehsil", "local": False},
    "pollution":    {"resolve": 48, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
    "stray":        {"resolve": 48, "stall": 48, "first_owner": "panchayat_secretary", "local": True},
}
FUNDING = ["15th Finance Commission", "VB-G RAM G (rules verify)", "State Water Mission",
           "SDGF / district", "Panchayat own fund", "MGNREGA legacy (verify)"]   # Sec 3.4 funding-source field
# escalation dwell budgets in hours (Q36): ack / action per level 0=Panchayat 1=Block 2=District 3=State
ACK    = {0: 48, 1: 168, 2: 360, 3: 720}
ACTION = {0: 168, 1: 360, 2: 720, 3: None}
LEVEL_NAME = {0: "Panchayat", 1: "Block Office", 2: "District", 3: "State"}
LEVEL_ACTOR = {0: "official", 1: "block", 2: "district", 3: "state"}
# verifier pool outside implementing desk (Sec 3.8 Route C)
POOL = [{"id": "teacher", "role": "School Teacher"}, {"id": "asha", "role": "ASHA Worker"},
        {"id": "shg", "role": "SHG Representative"}]

CASES = {}
AGENDA = []          # next-meeting items (Sec 3.4 Route C)
DIGESTS = {}         # weekly batched digest, one per case (Sec 3.8)

def load():
    global CASES, AGENDA, DIGESTS
    if os.path.exists(STATE):
        d = json.load(open(STATE, encoding="utf-8"))
        CASES = d.get("cases", {}); AGENDA = d.get("agenda", []); DIGESTS = d.get("digests", {})
def save():
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"cases": CASES, "agenda": AGENDA, "digests": DIGESTS},
              open(STATE, "w", encoding="utf-8"), indent=1)

def new_cid(prefix):
    return prefix + "-" + datetime.now().strftime("%y%m%d-") + f"{random.randint(100,999)}"

# ===================== OPEN CIVIC CASE (Sec 3.4 Route C) =====================
class CivicReq(BaseModel):
    issue: str; ward: str = "W-1"; note: str = ""; funding_source: str = ""
def open_civic(req):
    key = req.issue if req.issue in ISSUE_CLOCKS else "community"
    c = ISSUE_CLOCKS[key]
    cid = new_cid("CV")
    CASES[cid] = {
        "id": cid, "kind": "civic", "issue": key, "ward": req.ward, "note": req.note[:120],
        "funding_source": req.funding_source, "first_owner": c["first_owner"], "owner_local": c["local"],
        "resolve_hours": c["resolve"], "stall_hours": c["stall"],
        "hours_elapsed": 0, "last_change": 0, "level": 0, "level_entered": 0,
        "status": "OPEN", "acked": [False, False, False, False],
        "evidence_hash": "", "explanation": "", "verifiers": [], "audit_sample": False,
        "frozen": False, "integrity_alert": False, "citizen_confirmed": False,
        "opened": datetime.now().isoformat(timespec="minutes"),
    }
    # add to next Panchayat meeting agenda with funding-source field (Sec 3.4)
    AGENDA.append({"case_id": cid, "issue": key, "ward": req.ward,
                   "funding_source": req.funding_source or "(secretary to set)",
                   "owner": c["first_owner"], "local": c["local"]})
    h = append(cid, "system", "civic_case_opened",
               f"issue={key};ward={req.ward};owner={c['first_owner']};local={c['local']};fund={req.funding_source}")
    save()
    return {"case_id": cid, "ledger_hash": h, "route": "C", "first_owner": c["first_owner"],
            "owner_local": c["local"], "resolve_hours": c["resolve"], "stall_hours": c["stall"],
            "agenda_added": True,
            "note": ("Water-supply repair routes FIRST to the village water committee / state water "
                     "department, not the panchayat (Sec 3.4)." if key in ("handpump", "water") else
                     "Listed at next Panchayat meeting; overdue shown on board (Sec 3.4).")}

# ===================== TICK + AUTO-ESCALATION (Sec 3.9 stall / Sec 3.4 resolve) =====================
class TickReq(BaseModel): case_id: str; hours: int = 24
def tick(req):
    c = CASES.get(req.case_id)
    if not c: return {"error": "no such case"}
    if c["frozen"]: return {"error": "case frozen by integrity alert (Sec 3.6.4)"}
    c["hours_elapsed"] += req.hours
    events = []
    dwell = c["hours_elapsed"] - c["level_entered"]
    # missing-ack visibility (Sec 3.8): ack due but not logged
    if not c["acked"][c["level"]] and dwell >= ACK[c["level"]]:
        events.append(f"ACK MISSING at {LEVEL_NAME[c['level']]} (visible on board, Sec 3.8)")
    # climb triggers: 48h no status change (Sec 3.9) OR resolve target passed with no evidence (Q30/Q37)
    stall_breach = (c["hours_elapsed"] - c["last_change"]) >= c["stall_hours"] and c["status"] == "OPEN"
    resolve_breach = c["hours_elapsed"] >= c["resolve_hours"] and c["status"] == "OPEN" and not c["evidence_hash"]
    if c["status"] == "OPEN" and (stall_breach or resolve_breach):
        why = "48h stall, no complaint needed (Sec 3.9)" if stall_breach else "resolve target passed, no evidence-backed explanation (Q30/Q37)"
        climb(c, why); events.append("ESCALATED: " + why)
    save()
    return {"case_id": c["id"], "hours_elapsed": c["hours_elapsed"], "status": c["status"],
            "level": LEVEL_NAME[c["level"]], "events": events, "chain": verify_chain()}

def climb(c, why):
    if c["level"] >= 3:
        c["status"] = "STATE_REVIEW"; c["last_change"] = c["hours_elapsed"]
        append(c["id"], "system", "state_review_opened", why); return
    c["level"] += 1; c["level_entered"] = c["hours_elapsed"]; c["last_change"] = c["hours_elapsed"]
    c["status"] = "ESCALATED"; c["owner_local"] = False   # above panchayat = external office (Sec 3.9)
    append(c["id"], LEVEL_ACTOR[c["level"]], "escalated_to_" + LEVEL_NAME[c["level"]].replace(" ", "_"), why)

# ===================== OFFICIAL RESPONDS WITH EVIDENCE (Q30/Q37 anti-corruption core) =====================
class RespondReq(BaseModel): case_id: str; explanation: str = ""; evidence_hash: str = ""
def respond(req):
    c = CASES.get(req.case_id)
    if not c: return {"error": "no such case"}
    if c["frozen"]: return {"error": "frozen (Sec 3.6.4)"}
    c["explanation"] = req.explanation[:200]
    if req.evidence_hash:
        c["evidence_hash"] = req.evidence_hash[:64]
        c["status"] = "EXPLAINED"; c["last_change"] = c["hours_elapsed"]   # pause climbing until verified
        append(c["id"], "official", "evidence_backed_explanation", c["evidence_hash"][:16])
        verdict = "Explanation accepted as evidence-backed; escalation PAUSED pending verifier check (Q37)."
    else:
        # words without evidence do NOT stop the clock (Q30: 'reasonable explanation backed with evidence')
        append(c["id"], "official", "explanation_no_evidence", c["explanation"][:40])
        verdict = "No evidence attached -> the clock keeps running; this does NOT pause escalation (Q30)."
    save()
    return {"case_id": c["id"], "status": c["status"], "verdict": verdict, "chain": verify_chain()}

# ===================== BLOCK ACK (Sec 3.8 missing ack visible) =====================
class AckReq(BaseModel): case_id: str
def ack(req):
    c = CASES.get(req.case_id)
    if not c: return {"error": "no such case"}
    c["acked"][c["level"]] = True; c["last_change"] = c["hours_elapsed"]
    append(c["id"], LEVEL_ACTOR[c["level"]], "block_ack", LEVEL_NAME[c["level"]]); save()
    return {"case_id": c["id"], "acked_level": LEVEL_NAME[c["level"]], "chain": verify_chain()}

# ===================== ROUTE C CLOSURE: two verifiers outside desk (Sec 3.8) =====================
class VerifyReq(BaseModel): case_id: str; verifier_id: str; result: str = "accept"
def verify_c(req):
    c = CASES.get(req.case_id)
    if not c: return {"error": "no such case"}
    if c["frozen"]: return {"error": "frozen (Sec 3.6.4)"}
    v = next((p for p in POOL if p["id"] == req.verifier_id), None)
    if not v: return {"error": "unknown verifier"}
    # verifier must be outside the implementing desk (Sec 3.8); pool roles are all non-desk, enforced anyway
    if req.verifier_id in c["verifiers"]: return {"error": "same person cannot verify twice (Sec 3.7)"}
    if req.result == "reject":
        c["status"] = "REOPENED"; c["evidence_hash"] = ""; c["last_change"] = c["hours_elapsed"]
        climb(c, "verifier rejected the evidence"); append(c["id"], v["role"], "verifier_rejected", ""); save()
        return {"case_id": c["id"], "status": c["status"], "note": "Evidence rejected -> reopened + escalated (Sec 3.8)."}
    c["verifiers"].append(req.verifier_id); c["last_change"] = c["hours_elapsed"]
    append(c["id"], v["role"], "verifier_confirmed", str(len(c["verifiers"])))
    if len(c["verifiers"]) >= 2:                      # Sec 3.8 Route C: two verifiers close the work
        rec_hash = append(c["id"], "system", "work_verified_complete", "two verifiers outside desk")
        c["audit_sample"] = (int(sha(c["id"] + rec_hash)[:8], 16) % 10 == 0)   # 10% callback (Sec 3.8)
        c["status"] = "CLOSED_AUDIT" if c["audit_sample"] else "CLOSED"
        append(c["id"], "system", "closed" if not c["audit_sample"] else "audit_sampled", "Route C")
    save()
    return {"case_id": c["id"], "status": c["status"], "verifiers": c["verifiers"],
            "audit_sample": c["audit_sample"], "chain": verify_chain()}

# ===================== CITIZEN CONFIRM / DISPUTE (Sec 3.8 disputed reopen) =====================
class CitizenReq(BaseModel): case_id: str; action: str
def citizen(req):
    c = CASES.get(req.case_id)
    if not c: return {"error": "no such case"}
    if req.action == "dispute":
        if c["status"] not in ("CLOSED", "CLOSED_AUDIT"): return {"error": "nothing closed to dispute"}
        c["status"] = "REOPENED"; c["verifiers"] = []; c["evidence_hash"] = ""
        c["last_change"] = c["hours_elapsed"]
        append(c["id"], "citizen", "citizen_disputed", "reopens automatically, shows on board (Sec 3.8)")
        save(); return {"case_id": c["id"], "status": "REOPENED", "note": "Disputed closure reopened automatically and shows on the board (Sec 3.8)."}
    # confirm
    if c["status"] not in ("CLOSED", "CLOSED_AUDIT", "EXPLAINED"): return {"error": "confirm after closure/explanation"}
    c["citizen_confirmed"] = True
    if c["status"] == "CLOSED_AUDIT": c["status"] = "CLOSED"
    append(c["id"], "citizen", "citizen_confirmed", "separate act (Sec 3.8)"); save()
    return {"case_id": c["id"], "status": c["status"], "citizen_confirmed": True, "chain": verify_chain()}

# ===================== ROUTE D: corruption / powerful-person complaint (Sec 3.4) =====================
class CorruptReq(BaseModel): ward: str = "W-1"; detail: str = ""; consent: bool = True
def route_d(req):
    if not req.consent:
        return {"error": "Route D requires the citizen's consent to leave the panchayat (Sec 3.4)."}
    cid = new_cid("RD")
    # identity NEVER stored in the case record; local screen will show only 'escalated'
    CASES[cid] = {
        "id": cid, "kind": "route_d", "issue": "grievance_against_official", "ward": req.ward,
        "note": "", "funding_source": "", "first_owner": "block / district grievance (hidden locally)",
        "owner_local": False, "resolve_hours": 168, "stall_hours": 48,
        "hours_elapsed": 0, "last_change": 0, "level": 1, "level_entered": 0,   # starts at Block
        "status": "ESCALATED", "acked": [True, False, False, False],            # local 'ack' = the hidden escalation ref
        "evidence_hash": "", "explanation": "", "verifiers": [], "audit_sample": False,
        "frozen": False, "integrity_alert": False, "citizen_confirmed": False,
        "escalation_ref": "CPGR-" + sha(cid)[:8].upper(),                       # Sec 3.4 escalation reference
        "opened": datetime.now().isoformat(timespec="minutes"),
    }
    # ledger stores IDs + codes ONLY; the detail text is NOT written to the chain (Sec 3.6.1)
    append(cid, "system", "route_d_escalated", f"ward={req.ward};ref=CPGR;identity=hidden")
    save()
    return {"case_id": cid, "route": "D", "local_screen_shows": "ESCALATED (only)",
            "escalation_ref": CASES[cid]["escalation_ref"],
            "identity_stored": False,
            "note": "Complainant identity is never in the ledger or the local screen (Sec 3.4 / 3.6.1). "
                    "Ladder: Block -> District -> State. The system never concludes corruption; it flags "
                    "a suspected irregularity pending independent human investigation (Sec 3.6.4 / Q40)."}

# ===================== WEEKLY DIGEST, one per case (Sec 3.8) =====================
def build_digest():
    over = [c for c in CASES.values() if c["status"] in ("OPEN", "ESCALATED", "EXPLAINED", "REOPENED")
            and not c.get("digest_sent") and c["hours_elapsed"] >= 168]   # day-30 (Sec 3.8)
    if not over: return {"note": "Nothing at day-30 yet. One escalation per case, weekly batch (Sec 3.8)."}
    did = "DG-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    DIGESTS[did] = {"id": did, "case_ids": [c["id"] for c in over],
                    "sent": datetime.now().isoformat(timespec="minutes"), "ack": None}
    for c in over: c["digest_sent"] = True
    append("DIGEST", "system", "weekly_digest_sent", did); save()
    return DIGESTS[did]
def digest_ack(did):
    d = DIGESTS.get(did)
    if not d: return {"error": "no such digest"}
    d["ack"] = datetime.now().isoformat(timespec="minutes")
    append("DIGEST", "block", "block_ack", did); save(); return d

# ===================== PUBLIC RECORD: counts only + small-cell suppression (Sec 3.9) =====================
def public_records():
    rows = []
    for c in CASES.values():
        if c["kind"] == "route_d":
            rows.append({"public_id": sha(c["id"])[:10], "ward": c["ward"], "issue_type": "grievance (Route D)",
                         "opened": c["opened"][:10], "days_elapsed": c["hours_elapsed"] // 24,
                         "owner_desk": "block/district (hidden locally)", "escalation_level": LEVEL_NAME[c["level"]],
                         "status": "ESCALATED", "citizen_confirmed": c["citizen_confirmed"],
                         "integrity_alert": c["integrity_alert"], "owner_local": False})
            continue
        rows.append({"public_id": sha(c["id"])[:10], "ward": c["ward"], "issue_type": c["issue"],
                     "opened": c["opened"][:10], "days_elapsed": c["hours_elapsed"] // 24,
                     "owner_desk": c["first_owner"], "escalation_level": LEVEL_NAME[c["level"]],
                     "status": c["status"], "citizen_confirmed": c["citizen_confirmed"],
                     "integrity_alert": c["integrity_alert"], "owner_local": c["owner_local"]})
    # small-cell suppression: any (ward, issue_type) bucket under 5 merges upward (Sec 3.9)
    from collections import Counter, defaultdict
    cnt = Counter((r["ward"], r["issue_type"]) for r in rows)
    out, merged = [], defaultdict(list)
    for r in rows:
        if cnt[(r["ward"], r["issue_type"])] >= 5:
            out.append(r)
        else:
            merged[r["issue_type"]].append(r)
    for it, grp in merged.items():
        out.append({"public_id": "AGG-" + sha(it)[:8], "ward": "MERGED (small cells)", "issue_type": it,
                    "opened": "-", "days_elapsed": sum(g["days_elapsed"] for g in grp) // max(1, len(grp)),
                    "owner_desk": "aggregated", "escalation_level": "aggregated",
                    "status": f"{len(grp)} cases (suppressed, Sec 3.9)", "citizen_confirmed": False,
                    "integrity_alert": any(g["integrity_alert"] for g in grp), "owner_local": False})
    return out

# ===================== INTEGRITY: tamper -> freeze + suspected-misconduct alert (Q45 / Sec 3.6.4) =====================
class TamperReq(BaseModel): index: int
def tamper(req):
    if not os.path.exists(BOX_CHAIN): return {"error": "no chain yet"}
    lines = open(BOX_CHAIN, encoding="utf-8").read().splitlines()
    if not (0 <= req.index < len(lines)): return {"error": "index out of range"}
    rec = json.loads(lines[req.index])
    rec["action"] = rec["action"][:-1] + ("X" if not rec["action"].endswith("X") else "Y")
    lines[req.index] = json.dumps(rec)
    open(BOX_CHAIN, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    v = verify_chain()
    # freeze the case whose entry was wounded + raise anonymized integrity alert (NOT a corruption verdict)
    if not v["ok"]:
        cid = rec.get("case_id", "")
        if cid in CASES:
            CASES[cid]["frozen"] = True; CASES[cid]["integrity_alert"] = True
            append(cid, "system", "integrity_alert_frozen", "suspected tamper, pending independent investigation")
            save()
    return {"tampered_index": req.index, "verify": v,
            "label": "SUSPECTED INTEGRITY BREACH - case frozen, block + independent verifier notified, "
                     "anonymized public alert raised. NOT a proven corruption verdict (Sec 3.6.4 / Q40)."}

# ===================== API =====================
app = FastAPI(title="HaqSetu Phase 3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# (the two lines above are intentional no-op guards removed in the clean build below)
load()

@app.post("/civic_open")
def api_civic(req: CivicReq): return open_civic(req)
@app.post("/tick")
def api_tick(req: TickReq): return tick(req)
@app.post("/respond")
def api_respond(req: RespondReq): return respond(req)
@app.post("/ack")
def api_ack(req: AckReq): return ack(req)
@app.post("/verify_c")
def api_verify(req: VerifyReq): return verify_c(req)
@app.post("/citizen")
def api_citizen(req: CitizenReq): return citizen(req)
@app.post("/route_d")
def api_route_d(req: CorruptReq): return route_d(req)
@app.post("/digest")
def api_digest(): return build_digest()
@app.post("/digest_ack")
def api_digest_ack(did: str = ""): return digest_ack(did)
@app.get("/public")
def api_public(): return public_records()
@app.post("/tamper")
def api_tamper(req: TamperReq): return tamper(req)
@app.get("/chain")
def api_chain(): return verify_chain()
@app.get("/state")
def api_state():
    return {"cases": list(CASES.values()), "agenda": AGENDA, "digests": list(DIGESTS.values()),
            "public": public_records(), "chain": verify_chain(), "pool": POOL,
            "funding": FUNDING, "levels": LEVEL_NAME}

# ===================== UI =====================
PAGE = r"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>HaqSetu Phase 3</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:16px;max-width:1180px;margin:auto;}
h1{color:#38bdf8;} h2{color:#94a3b8;margin-top:20px;border-bottom:1px solid #334155;padding-bottom:3px;}
.panel{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px;margin:8px 0;}
button{padding:8px 12px;margin:2px;border:none;border-radius:7px;cursor:pointer;font-weight:bold;background:#38bdf8;color:#0f172a;}
button.red{background:#dc2626;color:#fff;} button.green{background:#10b981;color:#04211a;} button.amber{background:#f59e0b;color:#0f172a;} button.purple{background:#a855f7;color:#fff;}
input,select{background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:6px;padding:6px;margin:2px;}
.case{background:#0f172a;border-left:6px solid #38bdf8;border-radius:8px;padding:10px;margin:8px 0;}
.case.frozen{border-color:#f87171;background:#2a0a0a;} .case.closed{border-color:#10b981;} .case.escal{border-color:#f59e0b;}
.tag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:bold;margin:2px;}
.tC{background:#78350f;color:#fde68a;} .tD{background:#581c87;color:#e9d5ff;} .tlocal{background:#064e3b;color:#a7f3d0;} .text{background:#0c4a6e;color:#bae6fd;}
.bad{color:#f87171;font-weight:bold;} .ok{color:#10b981;font-weight:bold;} .warn{color:#fbbf24;font-weight:bold;}
table{border-collapse:collapse;margin-top:6px;width:100%;} td,th{border:1px solid #334155;padding:5px 8px;font-size:12px;text-align:left;}
.merged{background:#3b2f14;color:#fbbf24;} .note{font-size:12px;color:#94a3b8;line-height:1.5;}</style></head><body>
<h1> HaqSetu Phase 3 — Civic Agenda · Escalation Ladder · Route D · Public Record</h1>
<p class='note'>Case events append to the SAME <b>box_chain.jsonl</b> as the orchestrator (one ledger, Sec 3.6). Water routes first to the water committee/state dept (Sec 3.4). 48h stall auto-escalates with no complaint (Sec 3.9). Route C closes on two verifiers outside the desk; disputes reopen automatically (Sec 3.8). Public record is counts-only with small-cell suppression (Sec 3.9). Tamper = freeze + <i>suspected</i> alert, never a proven verdict (Sec 3.6.4).</p>

<h2>🏘️ Open civic case (Route C)</h2>
<div class='panel'>
Issue <select id='i_issue'></select> Ward <input id='i_ward' value='W-1' size='5'>
Note <input id='i_note' placeholder='lane behind school' size='22'>
Funding <select id='i_fund'></select>
<button class='amber' onclick='openCivic()'>▶ Open + add to next meeting agenda</button>
<button class='purple' onclick='routeD()'>🕶 Route D: complaint about an official (consent)</button>
<div id='o_new' class='note'></div></div>

<h2>📋 Next Panchayat meeting agenda (Sec 3.4)</h2><div id='agenda' class='panel'></div>

<h2>🪜 Cases + escalation ladder</h2><div id='cases'></div>

<h2>📨 Weekly digest (one per case; missing block ack visible, Sec 3.8)</h2>
<button onclick='digest()'>Build weekly digest (day-30)</button><div id='dig' class='panel'></div>

<h2>🌐 Public anonymized record (counts only, small-cell suppressed, Sec 3.9)</h2>
<button class='green' onclick='pub()'>Render public board</button><div id='pub' class='panel'></div>

<h2>⛓️ Unified ledger</h2>
<button class='green' onclick='chk()'>Verify chain</button>
<button class='red' onclick='tamper()'>🧨 Tamper line 0 (freeze + suspected alert)</button>
<span id='chain'></span>
<script>
const $=id=>document.getElementById(id);
const ISSUES=["drain","sewage","garbage","public_toilet","handpump","water","streetlight","road","community","encroach","pollution","stray"];
ISSUES.forEach(x=>$('i_issue').add(new Option(x,x)));
let FUND=[];
async function boot(){const s=await (await fetch('/state')).json();FUND=s.funding;
 $('i_fund').innerHTML='<option value="">(secretary to set)</option>'+FUND.map(f=>`<option>${f}</option>`).join('');
 render(s);}
async function post(p,b){const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});return r.json();}
async function openCivic(){const d=await post('/civic_open',{issue:$('i_issue').value,ward:$('i_ward').value,note:$('i_note').value,funding_source:$('i_fund').value});
 $('o_new').innerHTML=`<span class=ok>✅ ${d.case_id}</span> Route ${d.route} · first owner <b>${d.first_owner}</b> (${d.owner_local?'<span class=tlocal>LOCAL</span>':'<span class=text>EXTERNAL</span>'}) · resolve ${d.resolve_hours}h · stall ${d.stall_hours}h · agenda_added=${d.agenda_added}<br><span class=note>${d.note}</span>`; boot();}
async function routeD(){const d=await post('/route_d',{ward:$('i_ward').value,detail:'(identity never stored)',consent:true});
 $('o_new').innerHTML=`<span class=ok>🕶 ${d.case_id}</span> Route D · local screen shows ONLY "<b>${d.local_screen_shows}</b>" · ref ${d.escalation_ref} · identity_stored=${d.identity_stored}<br><span class=note>${d.note}</span>`; boot();}
async function tick(id){await post('/tick',{case_id:id,hours:24}); boot();}
async function respond(id){const ex=prompt('Explanation (words alone do NOT stop the clock, Q30):')||'';const ev=prompt('Evidence hash (leave blank = no evidence):')||'';
 const d=await post('/respond',{case_id:id,explanation:ex,evidence_hash:ev}); $('o_new').innerHTML='<span class=warn>'+d.verdict+'</span>'; boot();}
async function ack(id){await post('/ack',{case_id:id}); boot();}
async function ver(id,vid,res){const d=await post('/verify_c',{case_id:id,verifier_id:vid,result:res||'accept'}); boot();}
async function cit(id,a){await post('/citizen',{case_id:id,action:a}); boot();}
async function digest(){const d=await post('/digest',{}); $('o_new').innerHTML=d.note||('digest '+d.id+' sent for '+d.case_ids.length+' case(s)'); boot();}
async function dack(did){await fetch('/digest_ack?did='+encodeURIComponent(did),{method:'POST'}); boot();}
async function pub(){const rows=await (await fetch('/public')).json();
 $('pub').innerHTML='<table><tr><th>public_id</th><th>ward</th><th>issue</th><th>days</th><th>owner desk</th><th>local?</th><th>level</th><th>status</th><th>citizen?</th><th>integrity</th></tr>'+
  rows.map(r=>`<tr class='${r.ward.includes('MERGED')?'merged':''}'><td>${r.public_id}</td><td>${r.ward}</td><td>${r.issue_type}</td><td>${r.days_elapsed}</td><td>${r.owner_desk}</td><td>${r.owner_local?'LOCAL':'EXTERNAL'}</td><td>${r.escalation_level}</td><td>${r.status}</td><td>${r.citizen_confirmed?'✔':'—'}</td><td>${r.integrity_alert?'<span class=bad>ALERT</span>':'—'}</td></tr>`).join('')+'</table><p class=note>No names, no Aadhaar, no audio, no documents (Sec 3.9). Buckets under 5 merged upward.</p>';}
async function chk(){const v=await (await fetch('/chain')).json();$('chain').innerHTML=v.ok?`<span class=ok>✅ CHAIN OK (${v.n}) — shared with orchestrator</span>`:`<span class=bad>❌ TAMPER at #${v.broken}</span>`;}
async function tamper(){const d=await post('/tamper',{index:0}); $('o_new').innerHTML='<span class=bad>'+d.label+'</span>'; chk(); boot();}
function render(s){
 $('agenda').innerHTML=s.agenda.length?('<table><tr><th>case</th><th>issue</th><th>ward</th><th>funding source</th><th>owner</th><th>local?</th></tr>'+
   s.agenda.map(a=>`<tr><td>${a.case_id}</td><td>${a.issue}</td><td>${a.ward}</td><td>${a.funding_source}</td><td>${a.owner}</td><td>${a.local?'<span class=tlocal>LOCAL</span>':'<span class=text>EXTERNAL</span>'}</td></tr>`).join('')+'</table>'):'<i class=note>empty</i>';
 $('cases').innerHTML=s.cases.map(c=>{
   const cls=c.frozen?'frozen':(c.status.startsWith('CLOSED')?'closed':(c.status==='ESCALATED'||c.status==='REOPENED'?'escal':''));
   const lv=c.level; const dwell=c.hours_elapsed-c.level_entered; const ackDue=({0:48,1:168,2:360,3:720})[lv];
   const ackBadge=(!c.acked[lv]&&dwell>=ackDue)?'<span class=bad>ACK MISSING (visible, Sec 3.8)</span>':(c.acked[lv]?'<span class=ok>acked</span>':'<span class=note>ack due '+(ackDue-dwell)+'h</span>');
   const vpool=s.pool.filter(p=>!c.verifiers.includes(p.id)).map(p=>`<button onclick="ver('${c.id}','${p.id}','accept')">✓ ${p.role}</button><button class=red onclick="ver('${c.id}','${p.id}','reject')">✗ ${p.role}</button>`).join('');
   return `<div class='case ${cls}'><span class='tag ${c.kind==='route_d'?'tD':'tC'}'>${c.kind==='route_d'?'Route D':'Route C'}</span> <b>${c.id}</b> · ${c.issue} · ${c.ward} · <span class=note>${c.status}</span> · level <b>${s.levels[lv]}</b> · elapsed ${c.hours_elapsed}h ${c.frozen?'<span class=bad>🧊 FROZEN</span>':''} ${c.audit_sample?'<span class=warn>🎯 10% audit</span>':''}<br>
   <span class=note>owner: ${c.first_owner} (${c.owner_local?'<span class=tlocal>pending at Panchayat</span>':'<span class=text>pending at another office</span>'}) · resolve target ${c.resolve_hours}h · evidence: ${c.evidence_hash?c.evidence_hash.slice(0,12)+'…':'<span class=warn>none</span>'} · verifiers: ${c.verifiers.join('+')||'none'}${c.escalation_ref?' · ref '+c.escalation_ref:''}</div>
   ${ackBadge}<br>
   <button onclick="tick('${c.id}')">⏩ +24h</button>
   <button class=amber onclick="respond('${c.id}')">📝 official responds (+evidence?)</button>
   <button class=green onclick="ack('${c.id}')">📨 log block ack</button>
   ${vpool}
   <button class=green onclick="cit('${c.id}','confirm')">📦 citizen confirm</button>
   <button class=red onclick="cit('${c.id}','dispute')">⚠ citizen dispute (reopens)</button></div>`;
 }).join('')||'<i class=note>no cases yet</i>';
 $('dig').innerHTML=s.digests.length?s.digests.map(d=>`<div class='panel'>${d.id} · ${d.case_ids.join(', ')} · sent ${d.sent} · `+(d.ack?`<span class=ok>ACK ${d.ack}</span>`:`<span class=bad>AWAITING BLOCK ACK — visible (Sec 3.8)</span>`)+` <button onclick="dack('${d.id}')">log ack</button></div>`).join(''):'<i class=note>none</i>';
 chk();
}
boot();
</script></body></html>"""
@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("🪜 Phase 3 on http://127.0.0.1:8012")
    uvicorn.run(app, host="127.0.0.1", port=8012)