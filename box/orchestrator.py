"""
HaqSetu BOX ORCHESTRATOR — Phase 1 (the master brain)
Pipeline: consent -> speak -> split -> route -> clock -> ledger -> speak back.
Reuses triage/, agent/, engine/ modules already built. Enforces Sec 3.1 privacy
(no audio stored, no Aadhaar field, ledger = IDs+codes only) and Sec 3 "never deny".
Obey Sec 3.2.1 two-issue split, Sec 3.2.4 next-question-by-rule-coverage,
Sec 3.4 route table + clocks, Sec 3.6 signed hash chain. Port 8010.
"""
import os, sys, json, hashlib, re
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BOX_CHAIN = os.path.join(ROOT, "ledger", "box_chain.jsonl")

# ---- reuse existing brains, with clear errors if a path moved ----
try:
    from triage.abstain import triage_with_abstention
except Exception as e:
    triage_with_abstention = None; print("WARN abstain import:", e)
try:
    from triage.baselines import predict as intent_predict
except Exception as e:
    intent_predict = None; print("WARN baselines import:", e)
try:
    from agent.solution_generator import generate_spoken_solution
except Exception as e:
    generate_spoken_solution = None; print("WARN solution import:", e)
try:
    from engine.planner_visualiser import compute_plan
except Exception as e:
    compute_plan = None; print("WARN planner import:", e)

# ===================== ROUTE TABLE (Sec 3.4) =====================
# intent substring -> (route, clock_hours, owner_desk)
ROUTE_RULES = [
    (("crop", "pmfby", "fasal", "kharab", "ola", "baadh"), ("A", 72, "patwari / insurer helpline")),
    (("water", "handpump", "paani", "pipe", "borewell", "jal"), ("C", 48, "panchayat_secretary / water committee")),
    (("street", "light", "bulb", "lamp", "bijli", "saubhagya"), ("C", 48, "panchayat_secretary / line man")),
    (("road", "sadak", "gali", "kichad", "repair"), ("C", 72, "bdo / junior engineer")),
    (("drain", "naali", "sewage", "ganda", "garbage", "kachra", "toilet", "shouchalay"), ("C", 24, "panchayat_secretary")),
    (("pond", "talab", "cremation", "smashan", "community", "panchayat_ghar", "encroach", "pollution", "stray", "awara", "tree", "building", "fund", "paras"), ("C", 72, "panchayat_secretary")),
    (("grievance", "corrupt", "bribe", "paisa", "patwari", "sarpanch", "shikayat", "harass"), ("D", 48, "block / district grievance (hidden locally)")),
    (("pension", "vidhwa", "viklang", "budhapa", "kisan", "pm_kisan", "kist", "samman", "ration", "nfasa", "aay", "ayushman", "health", "insurance", "awas", "makan", "housing", "ujjwala", "gas", "cylinder", "mgnrega", "nrega", "majdoori", "wage", "job", "rozgar", "sukanya", "beti", "ladli", "pmmvy", "maternity", "pregnant", "sbm", "eshram", "shram", "kcc", "mudra", "loan", "standup", "vishwakarma", "artisan", "skill", "kaushal", "pre_matric", "post_matric", "scholarship", "midday", "poshan", "anganwadi", "single_woman", "transgender", "freedom", "ex_servicemen", "dairy", "horticulture", "soil", "organic", "irrigation", "agri", "matsya", "fisher", "godown", "tractor", "kcc", "pashu", "livestock", "gkalyan", "har_ghar", "kusum", "solar"), ("B", 48, "csc / bank / panchayat / patwari")),
]
HUMAN_QUEUE = ("HUMAN", 48, "facilitator review")

def route_for(intent):
    s = (intent or "").lower()
    for keys, val in ROUTE_RULES:
        if any(k in s for k in keys):
            return val
    return HUMAN_QUEUE

# ===================== SLOT EXTRACTION (Sec 3.2.1) =====================
def extract_slots(text):
    t = text.lower(); slots = {}
    m = re.search(r"(\d+)\s*(mahine|month|mahina)", t)
    if m: slots["months_unpaid"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(din|day)", t)
    if m: slots["days_pending"] = int(m.group(1))
    if re.search(r"(gehu|wheat|rice|dhan|bajra|kharif|rabi|fasal|crop)", t): slots["crop"] = True
    if re.search(r"(insured|pmfby|bima|haan|i am|yes)", t) and not re.search(r"(nahi|no|not|uninsured)", t):
        slots["insured"] = True
    if re.search(r"(nahi|no|not|uninsured|bima nahi)", t) and re.search(r"(insured|pmfby|bima)", t):
        slots["insured"] = False
    if re.search(r"(aaj|today)", t): slots["event_when"] = "today"
    if re.search(r"(kal|yesterday|last night|raat)", t): slots["event_when"] = "yesterday"
    return slots

# required slots that CHANGE outcome, per route (Sec 3.2.4 next-question-by-rule-coverage)
REQUIRED = {"A": ["insured", "crop", "event_when"], "B": [], "C": [], "D": [], "HUMAN": []}
def next_question(route, slots):
    need = REQUIRED.get(route, [])
    for f in need:
        if f not in slots:
            return {"field": f,
                    "ask": {"insured": "Kya aap PMFBY ke tahat beema karwaya tha? (Insured under PMFBY?)",
                            "crop": "Kaunsi fasal thi? (Which crop?)",
                            "event_when": "Nuksaan kab hua — aaj ya kal? (When did the loss happen?)"}.get(f, f"Please confirm: {f}")}
    return None

# ===================== TWO-ISSUE SPLIT (Sec 3.2.1) =====================
def split_intents(text):
    """Return list of (intent, confidence). Splits a 2-issue sentence into 2 cases."""
    if triage_with_abstention:
        r = triage_with_abstention(text)
        labels = r.get("labels") or []
        conf = float(r.get("confidence") or 0.0)
        action = r.get("action", "ABSTAIN")
        if action == "ABSTAIN" or not labels:
            return [{"intent": "other", "confidence": conf, "abstain": True}]
        # multi-label: keep each label that the classifier actually returned
        out = []
        for i, lab in enumerate(labels):
            out.append({"intent": lab, "confidence": conf if i == 0 else max(0.0, conf - 0.05*i), "abstain": False})
        return out or [{"intent": "other", "confidence": conf, "abstain": True}]
    if intent_predict:
        p = intent_predict(text); labs = p.get("labels") or ["other"]
        return [{"intent": l, "confidence": 0.5, "abstain": False} for l in labs]
    return [{"intent": "other", "confidence": 0.0, "abstain": True}]

# ===================== SIGNED HASH CHAIN (Sec 3.6) =====================
KEYS = {"facilitator": "k-fac", "system": "k-sys", "official": "k-off", "verifier": "k-ver", "citizen": "k-cit", "block": "k-blk", "district": "k-dist", "state": "k-st"}
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def body_of(r): return {k: v for k, v in r.items() if k not in ("hash", "sig")}
def sig_of(actor, body): return sha(KEYS.get(actor, "k-?") + json.dumps(body, sort_keys=True))[:16]
def hash_of(body, s): return sha(json.dumps(body, sort_keys=True) + s)[:16]

def append_ledger(case_id, actor, action, detail=""):
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

def verify_box_chain():
    if not os.path.exists(BOX_CHAIN): return {"ok": True, "n": 0}
    lines = open(BOX_CHAIN, encoding="utf-8").read().splitlines()
    for idx, line in enumerate(lines):
        r = json.loads(line); body = body_of(r)
        exp_prev = sha("genesis")[:16] if idx == 0 else sha(lines[idx-1])[:16]
        if r.get("prev_hash") != exp_prev or r.get("hash") != hash_of(body, r.get("sig","")) or r.get("sig") != sig_of(r.get("actor"), body):
            return {"ok": False, "broken": idx, "n": len(lines)}
    return {"ok": True, "n": len(lines)}

# ===================== DOCUMENTS TO BRING (Sec 3.5.4 / Haq Pack) =====================
DOCS = {"A": ["Aadhaar", "bank passbook", "land record (khasra/khuni)"],
        "B": ["Aadhaar", "bank passbook", "ration card / income certificate as applicable"],
        "C": ["none — facilitator logs location + photo evidence"],
        "D": ["none — identity protected; escalation reference only"],
        "HUMAN": ["facilitator will ask one clarifying question"]}

# ===================== API =====================
app = FastAPI(title="HaqSetu Box Orchestrator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Intake(BaseModel):
    text: str
    consent: str = "named"   # named | ward_only | anonymous  (Sec 3.1.2)

@app.post("/intake")
def intake(req: Intake):
    text = (req.text or "").strip()
    if not text:
        return {"error": "no speech"}
    parts = split_intents(text)
    slots = extract_slots(text)
    cases = []
    for p in parts:
        route, clock, desk = route_for(p["intent"])
        nq = next_question(route, slots)
        deadline = (datetime.now() + timedelta(hours=clock)).isoformat(timespec="minutes")
        # ledger: IDs + codes ONLY (Sec 3.6.1) — never the transcript text, never Aadhaar
        cid = "BX-" + datetime.now().strftime("%y%m%d-") + f"{len(cases)+1:03d}-{abs(hash(p['intent']))%999:03d}"
        h = append_ledger(cid, "system", "case_opened", f"route={route};intent={p['intent']};consent={req.consent}")
        cases.append({
            "case_id": cid, "intent": p["intent"], "route": route, "clock_hours": clock,
            "deadline": deadline, "owner_desk": desk, "confidence": round(p["confidence"], 3),
            "abstain": p.get("abstain", False), "documents": DOCS.get(route, []),
            "next_question": nq, "ledger_hash": h,
            "consent": req.consent,
            "label": "Facilitator guidance. Final decision by competent authority.",  # Sec 3.3.5
            "never_deny": "Automated denial precluded by construction (Sec 3).",
        })
    # planner hand-off (Sec 3.5) for route-B welfare bundles
    plan = None
    if compute_plan:
        scheme_keys = [c["intent"] for c in cases if c["route"] == "B"]
        if scheme_keys:
            try: plan = compute_plan(scheme_keys)
            except Exception: plan = None
    # spoken response (Sec 3.2.5: AI never writes free text to citizen beyond guidance)
    spoken = None
    if generate_spoken_solution and cases:
        c0 = cases[0]
        spoken = generate_spoken_solution(scheme=c0["intent"], outcome=("needs_official_decision" if c0["abstain"] else "include"),
                                          facts=slots, ttbr_data=(plan or {}), proof_data={})
    return {"n_issues": len(cases), "cases": cases, "plan": plan, "spoken": spoken,
            "slots": slots, "chain": verify_box_chain(),
            "privacy": "Audio not stored (transient ASR only). Aadhaar never a field. Ledger holds IDs+codes only (Sec 3.1, 3.6)."}

@app.get("/chain")
def chain(): return verify_box_chain()

# ===================== BOX CONSOLE UI =====================
PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>HaqSetu Box</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:18px;max-width:1000px;margin:auto;}
h1{color:#38bdf8;} .consent{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;margin:10px 0;}
.consent b{color:#fbbf24;} button{padding:10px 14px;margin:4px;border:none;border-radius:8px;cursor:pointer;font-weight:bold;background:#38bdf8;color:#0f172a;}
button.red{background:#dc2626;color:#fff;} button.green{background:#10b981;color:#04211a;} button.amber{background:#f59e0b;color:#0f172a;}
button.sel{outline:3px solid #38bdf8;} textarea{width:100%;height:60px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:8px;padding:8px;box-sizing:border-box;}
.case{background:#1e293b;border-left:6px solid #38bdf8;border-radius:8px;padding:12px;margin:10px 0;}
.case.A{border-color:#ef4444;} .case.B{border-color:#38bdf8;} .case.C{border-color:#f59e0b;} .case.D{border-color:#a855f7;} .case.HUMAN{border-color:#94a3b8;}
.badge{display:inline-block;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:bold;margin:2px;}
.rA{background:#7f1d1d;color:#fecaca;} .rB{background:#0c4a6e;color:#bae6fd;} .rC{background:#78350f;color:#fde68a;} .rD{background:#581c87;color:#e9d5ff;} .rHUMAN{background:#334155;color:#cbd5e1;}
.split{color:#10b981;font-weight:bold;} .warn{color:#fbbf24;} .hash{font-size:11px;color:#94a3b8;word-break:break-all;}
.bar{height:8px;background:#334155;border-radius:4px;overflow:hidden;margin:3px 0;} .fill{height:100%;background:#38bdf8;}
.note{font-size:12px;color:#94a3b8;line-height:1.5;} .ok{color:#10b981;} .bad{color:#f87171;}</style></head><body>
<h1>📦 HaqSetu Panchayat Intelligence Box</h1>
<div class='consent'><b>Consent notice (Sec 3.1.2):</b> Aapka data sirf aapke haq ke liye use hoga. Aadhaar number kabhi store nahi hoga. Awaaz transcription ke baad delete ho jaati hai. Aap chuniye:
 <button id='c-named' class='sel' onclick='setConsent("named",this)'>Named</button>
 <button id='c-ward' onclick='setConsent("ward_only",this)'>Ward-only</button>
 <button id='c-anon' onclick='setConsent("anonymous",this)'>Anonymous</button>
 <button class='amber' onclick='readConsent()'>🔊 Read consent aloud</button></div>
<textarea id='t' placeholder='Citizen speaks here (or use mic in Phase 1.5)... e.g. "meri pension 3 mahine se nahi aayi aur pm kisan bhi ruk gaya"'></textarea>
<button class='red' onclick='mic()'>🎙️ Speak to Box</button>
<button onclick='run()'>▶ Process Intake</button>
<div id='out'></div>
<h3>⛓️ Box Ledger</h3><button class='green' onclick='chk()'>Verify chain</button> <span id='chain'></span>
<script>
let consent="named";
function setConsent(v,b){consent=v;["c-named","c-ward","c-anon"].forEach(i=>document.getElementById(i).classList.remove("sel"));b.classList.add("sel");}
function readConsent(){const u=new SpeechSynthesisUtterance("Consent notice: your data is used only for your rightful entitlement. Aadhaar number is never stored. Audio is deleted right after transcription. You may choose named, ward-only, or anonymous.");u.lang="en-IN";speechSynthesis.speak(u);}
function mic(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return alert("Use Chrome/Edge for mic.");const r=new SR();r.lang="hi-IN";r.onresult=e=>{document.getElementById('t').value=e.results[0][0].transcript;run();};r.start();}
async function run(){const text=document.getElementById('t').value;const r=await fetch('/intake',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,consent})});const d=await r.json();
 if(d.error){document.getElementById('out').innerHTML='<p class=bad>'+d.error+'</p>';return;}
 let h=`<p class='split'>🔀 Detected ${d.n_issues} issue(s) → ${d.n_issues} case(s). Slots: ${JSON.stringify(d.slots)}</p>`;
 h+=`<p class='note'>🔒 ${d.privacy}</p>`;
 d.cases.forEach(c=>{h+=`<div class='case ${c.route}'><span class='badge r${c.route}'>Route ${c.route}</span> <b>${c.intent}</b> · conf ${c.confidence} ${c.abstain?'<span class=warn>⚠ ABSTAIN → human</span>':''}<br>
 <span class='note'>Owner: ${c.owner_desk} · Clock: ${c.clock_hours}h · Deadline: ${c.deadline} · Consent: ${c.consent}</span><br>
 <b>Bring:</b> ${c.documents.join(', ')}<br>
 ${c.next_question?`<span class='warn'>❓ Next question (rule coverage): ${c.next_question.ask}</span><br>`:''}
 <span class='note'>${c.label} ${c.never_deny}</span>
 <div class='bar'><div class='fill' style='width:${(c.confidence*100).toFixed(0)}%'></div></div>
 <div class='hash'>ledger ${c.ledger_hash}</div></div>`;});
 if(d.plan){h+=`<div class='case B'><b>🗺️ One-Visit Planner</b><br><span class='note'>Naive ${d.plan.naive_visits} → Planned ${d.plan.planned_visits} visits (saved ${d.plan.visits_saved}). Critical path ${d.plan.critical_path_days}d. Long-pole: ${(d.plan.long_poles||[]).map(p=>p.action+' '+p.days+'d').join(', ')||'none'}.</span></div>`;}
 if(d.spoken){h+=`<div class='case'><b>🔊 Box speaks</b><br><span class='note'>${d.spoken}</span> <button class='green' onclick='spk(this)' data-x='${d.spoken.replace(/'/g,"&#39;")}'>Speak</button></div>`;}
 document.getElementById('out').innerHTML=h; chk();}
function spk(b){const u=new SpeechSynthesisUtterance(b.dataset.x);u.lang="en-IN";u.rate=.95;speechSynthesis.speak(u);}
async function chk(){const v=await (await fetch('/chain')).json();document.getElementById('chain').innerHTML=v.ok?`<span class='ok'>✅ CHAIN OK (${v.n})</span>`:`<span class='bad'>❌ TAMPER at #${v.broken}</span>`;}
chk();
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("📦 Box Orchestrator on http://127.0.0.1:8010")
    uvicorn.run(app, host="127.0.0.1", port=8010)