import re, json, hashlib, yaml, io, secrets, sys
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from core.production import (router as prod_router, record as prod_record,
                             geo_ok, otp_used, otp_verify_code)

BASE = Path(__file__).resolve().parent
for sub in ("mesh",):
    p = BASE / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
CHAIN = BASE / "ledger" / "match_chain.jsonl"
app = FastAPI(title="HaqSetu Commercial Core")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(prod_router)

RULES = []
for folder in ("schemes", "routes"):
    d = BASE / "rulepack" / folder
    if d.exists():
        for f in sorted(d.glob("*.yaml")):
            try: data = yaml.safe_load(f.read_text(encoding="utf-8"))
            except Exception: continue
            for r in (data.get("rules") or []):
                RULES.append({"scheme": f.stem, "desc": r.get("description", ""), "when": r.get("when") or [],
                              "docs": r.get("documents") or [], "desk": r.get("desk", ""), "clock": r.get("clock_hours")})

COND = [
    (r"\b(\d{1,2})\s*(?:saal|sal|years|year)\b", "age", "int"), (r"\bwidow|vidhwa\b", "is_widow", True),
    (r"\bdisab\w*\s*(\d{2,3})\s*%?", "disability_pct", "int"), (r"\bpregnant|garbhavati\b", "is_pregnant", True),
    (r"\bgirl|beti|ladki\b", "is_girl", True), (r"\bstudent|school|college|padhai\b", "is_student", True),
    (r"\bfarmer|kisan|kheti|fasal|crop\b", "is_farmer", True),
    (r"\bincome\s*(?:below|under|at most|up to)?\s*(?:rs?\.?|inr)?\s*([\d,]+)", "annual_income_inr", "int"),
    (r"\bbpl\b", "is_bpl", True), (r"\bno\s+(?:pucca\s+)?house|kacha\s+ghar\b", "has_pucca_house", False),
    (r"\bno\s+toilet|shouchalay\s+nahi\b", "has_toilet", False), (r"\bno\s+(?:gas|lpg|cylinder)|chulha\b", "has_lpg", False),
    (r"\bcrop\s+loss\s*(\d{1,3})\s*%|fasal\s+(?:kharab|barbad)\b", "crop_loss", 40), (r"\binsured|bima\b", "has_crop_insurance", True),
    (r"\bworker|majdoor|labour|labor\b", "is_unorganized", True), (r"\bartisan|karigar|weaver|potter\b", "is_artisan", True),
    (r"\bfish\w*|machhua\b", "is_fisher", True), (r"\bcow|cattle|buffalo|pashu|livestock\b", "has_livestock", True),
    (r"\bwoman|mahila|female\b", "is_female", True),
    (r"\bjob\s*card|nrega|vb-?g\s*ram\s*g|majdoori|kaam\s+chahiye\b", "willing_work", True), (r"\badult\b|18\s*\+", "is_adult", True)]
CIVIC = [(r"handpump|borewell|paani|pipe|water", "water_supply"), (r"street\s*light|bulb|lamp", "streetlight"),
         (r"road|sadak|kichad", "road_repair"), (r"drain|naali|sewage", "drainage"), (r"garbage|kachra|trash", "garbage")]

def extract(text):
    t = text.lower(); facts = {}
    for pat, field, kind in COND:
        m = re.search(pat, t)
        if not m: continue
        if kind == "int":
            val = m.group(1).replace(",", "") if m.groups() else None
            if val: facts[field] = int(val)
        else: facts[field] = kind
    if "age" in facts: facts["is_adult"] = facts["age"] >= 18
    return facts, [n for pat, n in CIVIC if re.search(pat, t)]

def ev(c, f):
    if c.get("field") not in f: return None
    a = f[c["field"]]
    return {"eq": a == c["value"], "gte": a >= c["value"], "lte": a <= c["value"], "gt": a > c["value"], "lt": a < c["value"]}.get(c["op"])

def match(f):
    can, likely = [], []
    for r in RULES:
        if not r["when"]: continue
        res = [ev(c, f) for c in r["when"]]
        if any(x is False for x in res): continue
        miss = [c["field"] for c, x in zip(r["when"], res) if x is None]
        if not miss: can.append(r)
        elif any(x is True for x in res): likely.append({**r, "missing": miss})
    return can, likely

def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def log(event):
    CHAIN.parent.mkdir(parents=True, exist_ok=True)
    lines = CHAIN.read_text(encoding="utf-8").splitlines() if CHAIN.exists() else []
    prev = sha(lines[-1])[:16] if lines else sha("genesis")[:16]
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "prev": prev, **event}
    rec["hash"] = sha(json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True))[:16]
    with CHAIN.open("a", encoding="utf-8") as fh: fh.write(json.dumps(rec) + "\n")
    try: prod_record(event.get("case",""), "system", event.get("event",""), event)
    except Exception: pass
    return rec

SLA_DAYS = {"water_supply": 7, "streetlight": 7, "drainage": 7, "garbage": 3, "road_repair": 15}
DBT = {"pm_kisan": ["Aadhaar e-KYC", "NPCI mapper (Aadhaar-bank)", "Bank account seeded", "State treasury release", "DBT credit"],
       "pension": ["Life certificate", "Bank account seeded", "State treasury release", "DBT credit"],
       "default": ["Document verification", "Bank account seeded", "State treasury release", "DBT credit"]}
SCHEMES_PLAN = {"pm_kisan": [{"desk": "CSC", "days": 1}, {"desk": "Patwari", "days": 3}, {"desk": "Bank", "days": 15}],
                "pension": [{"desk": "Panchayat", "days": 2}, {"desk": "Bank", "days": 5}],
                "awas": [{"desk": "Panchayat", "days": 3}, {"desk": "BDO", "days": 10}],
                "ayushman": [{"desk": "CSC", "days": 1}]}

@app.post("/api/match")
def api_match(body: dict):
    text = body.get("text", ""); gp = body.get("gp", "GP-01")
    facts, civic = extract(text)
    if not facts and not civic:
        log({"event": "intake_abstain", "gp": gp})
        return {"action": "ABSTAIN", "facts": {}, "civic": [], "can": [], "likely": [], "case": "",
                "speak": "I did not catch clear conditions. The facilitator will ask one question."}
    can, likely = match(facts)
    rec = log({"event": "intake", "gp": gp, "facts": facts, "civic": civic, "can": [r["scheme"] for r in can]})
    names = ", ".join(r["scheme"].replace("_", " ") for r in can) or "no scheme yet"
    speak = "Based on what you told me, you can enrol in: " + names + "."
    if civic: speak += " Your civic issue gets an SLA clock and the Panchayat-meeting agenda."
    return {"action": "MATCH", "case": rec["hash"][:8], "facts": facts, "civic": civic, "can": can, "likely": likely, "speak": speak}

@app.post("/api/petition")
def petition(body: dict):
    text = body.get("text", ""); case = (body.get("case") or "")[:8]
    facts, civic = extract(text)
    can, _ = (match(facts) if facts else ([], []))
    subj = can[0]["scheme"] if can else (civic[0] if civic else "grievance")
    days = SLA_DAYS.get(subj, 30)
    rec = log({"event": "petition_filed", "case": case, "subject": subj, "sla_days": days})
    pet = ("BEFORE THE GRAM PANCHAYAT SECRETARY\nUnder the Haryana Right to Service Act, 2014 (RTPS)\n"
           f"Case ID: {case or rec['hash'][:8].upper()}   Applicant: ward-only label (DPDP-minimal)\n"
           f"Subject: {subj.replace('_',' ')}\nFacts as declared and read back: {text}\n"
           f"Mandated period: {days} days from receipt. Countdown starts now.\nLedger chain code: {rec['hash']}\n"
           "(Facilitator guidance. Portal submission SIMULATED in this exhibit.)")
    return {"petition": pet, "days": days, "deadline": (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")}

@app.post("/api/evidence")
def evidence(body: dict):
    rec = log({"event": "evidence_locked", "case": body.get("case", "DEMO"),
               "photo_hash": body.get("photo_hash", "")[:16], "geo": body.get("geo"), "taken_at": body.get("taken_at")})
    return {"receipt": rec["hash"]}

@app.post("/api/close")
def close(body: dict):
    c = body.get("case", "DEMO")
    ok = otp_verify_code(c, body.get("otp","")) if body.get("otp") else otp_used(c)
    if not ok: return {"error": "Citizen confirmation missing: OTP unused or wrong."}
    if not body.get("fix_photo_hash") or body.get("fix_photo_hash") == body.get("orig_photo_hash"):
        return {"error": "Closure needs a NEW geo-tagged photo of the fixed site."}
    g1, g2 = body.get("orig_geo",""), body.get("geo","")
    if g1 and g2 and g1 not in ("denied","unavailable") and g2 not in ("denied","unavailable") and not geo_ok(g1, g2):
        return {"error": "Fix-photo GPS is more than 200 m from the break-photo GPS. Closure rejected."}
    log({"event": "ticket_closed", "case": c, "fix_photo_hash": body.get("fix_photo_hash","")[:16], "geo": g2})
    return {"status": "CLOSED_WITH_PROOF"}

@app.post("/api/appeal")
def appeal(body: dict):
    return {"receipt": log({"event": "appeal", "case": body.get("case", "")})["hash"]}

@app.post("/api/plan")
def plan(body: dict):
    sel = body.get("schemes", [])
    naive = sum(len(SCHEMES_PLAN[s]) for s in sel if s in SCHEMES_PLAN)
    desks = {st["desk"] for s in sel for st in SCHEMES_PLAN.get(s, [])}
    return {"naive": naive, "planned": len(desks), "saved": naive - len(desks), "dbt": DBT.get(sel[0], DBT["default"]) if sel else []}

@app.get("/api/digest")
def digest():
    rows = [json.loads(l) for l in CHAIN.read_text(encoding="utf-8").splitlines()] if CHAIN.exists() else []
    counts = {}
    for r in rows:
        for s in r.get("can", []): counts[s] = counts.get(s, 0) + 1
        for c in r.get("civic", []): counts[c] = counts.get(c, 0) + 1
    return {"counts": {k: v for k, v in counts.items() if v >= 5}, "merged_small_cells": sum(v for v in counts.values() if v < 5),
            "chain_anchor": rows[-1]["hash"] if rows else sha("genesis")[:16], "privacy": "counts only; cells under 5 merged (Sec 3.9)"}

@app.post("/api/digest_send")
def digest_send(): return {"ack": log({"event": "block_digest_sent"})["hash"]}

@app.get("/api/ledger")
def ledger():
    rows = [json.loads(l) for l in CHAIN.read_text(encoding="utf-8").splitlines()] if CHAIN.exists() else []
    ok = all(r["prev"] == (sha("genesis")[:16] if i == 0 else rows[i-1]["hash"]) for i, r in enumerate(rows))
    return {"rows": rows, "ok": ok}

@app.post("/api/tamper")
def tamper():
    rows = [json.loads(l) for l in CHAIN.read_text(encoding="utf-8").splitlines()] if CHAIN.exists() else []
    if len(rows) > 1:
        rows[1]["event"] = rows[1].get("event", "") + "_TAMPERED"
        CHAIN.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return {"status": "tampered"}

@app.post("/api/deny")
def deny(body: dict):
    return {"status": "DENIAL_BLOCKED", "proof_trace": {
        "premise_1": "Include, escalate, abstain - never deny.",
        "premise_2": "Official attempted rejection: " + body.get("reason", ""),
        "conclusion": "AUTOMATED DENIAL PRECLUDED. Escalated with proof trace.",
        "receipt": sha(body.get("reason", "") + datetime.now().isoformat())[:16]}}

@app.get("/api/qr")
def qr(request: Request, case: str = ""):
    tok = secrets.token_hex(8)
    url = str(request.base_url).rstrip("/") + "/roles?role=villager&case=" + case + "&t=" + tok
    try:
        import qrcode, qrcode.image.svg
        q = qrcode.QRCode(border=1); q.add_data(url); q.make(fit=True)
        buf = io.BytesIO(); q.make_image(image_factory=qrcode.image.svg.SvgImage).save(buf)
        return HTMLResponse(buf.getvalue().decode())
    except Exception:
        return HTMLResponse(f"<div style='font-family:monospace;font-size:11px'>QR lib missing.<br>{url}</div>")

@app.get("/api/role")
def role(role: str = "panchayat", case: str = ""):
    rows = [json.loads(l) for l in CHAIN.read_text(encoding="utf-8").splitlines()] if CHAIN.exists() else []
    cases = {}; n_in = 0; n_ab = 0
    for r in rows:
        e = r.get("event")
        if e == "intake":
            n_in += 1; cid = r["hash"][:8]
            cases[cid] = {"case": cid, "gp": r.get("gp", "GP-01"), "ts": r["ts"], "civic": r.get("civic", []),
                          "can": r.get("can", []), "state": "open", "sla": None, "deadline": None,
                          "evidence": False, "closed": False, "appeals": 0, "subject": ""}
        elif e == "intake_abstain": n_ab += 1
        else:
            c = cases.get((r.get("case") or "")[:8])
            if not c: continue
            if e == "petition_filed":
                c["state"] = "progress"; c["sla"] = r.get("sla_days"); c["subject"] = r.get("subject", "")
                c["deadline"] = (datetime.fromisoformat(r["ts"]) + timedelta(days=r.get("sla_days", 30))).isoformat()
            if e == "evidence_locked": c["evidence"] = True
            if e == "ticket_closed": c["closed"] = True; c["state"] = "closed"
            if e == "appeal": c["appeals"] += 1
    now = datetime.now()
    for c in cases.values():
        if c["deadline"] and not c["closed"] and now > datetime.fromisoformat(c["deadline"]): c["state"] = "breached"
        c["pending"] = "other-office" if any(s in ("pm_kisan", "pension", "awas") for s in c["can"]) else "panchayat"
        if c["civic"]: c["pending"] = "panchayat"
    if role == "villager":
        return {"case": cases.get(case[:8], {}), "privacy": "ward-only label; no names, no Aadhaar (Sec 3.1, 3.6)"}
    if role == "panchayat":
        return {"cases": list(cases.values())}
    if role == "sdm":
        gps = {}
        for c in cases.values():
            g = gps.setdefault(c["gp"], {"gp": c["gp"], "open": 0, "progress": 0, "closed": 0, "breached": 0, "p": 0, "o": 0})
            g[c["state"]] += 1; g["p" if c["pending"] == "panchayat" else "o"] += 1
        return {"gps": list(gps.values()), "escalations": [c for c in cases.values() if c["state"] == "breached"]}
    counts = {}
    for c in cases.values():
        for s in c["can"]: counts[s] = counts.get(s, 0) + 1
        for v in c["civic"]: counts[v] = counts.get(v, 0) + 1
    kept = {k: v for k, v in counts.items() if v >= 5}
    staged = []
    try:
        import district_twin
        staged = district_twin.institution_stats(district_twin.simulate_district(seed=7))
    except Exception:
        pass
    return {"counts": kept, "merged": sum(v for v in counts.values() if v < 5), "n_intake": n_in, "n_abstain": n_ab,
            "abstain_rate": round(n_ab / (n_ab + n_in), 3) if (n_ab + n_in) else 0, "staged": staged}

@app.get("/roles")
def roles_page(): return HTMLResponse((BASE / "roles.html").read_text(encoding="utf-8"))

@app.get("/")
def home(): return HTMLResponse((BASE / "index.html").read_text(encoding="utf-8"))

if __name__ == "__main__":
    print("🇮 HaqSetu Commercial Core: http://127.0.0.1:8000  (HAQ_AUTH=1 for pilot login mode)")
    uvicorn.run(app, host="127.0.0.1", port=8000)
