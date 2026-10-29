"""
HaqSetu PHASE 2 — Crop Loss + Document Camera + KYC Router (port 8011)
Isolated from the orchestrator: own hash-chain writer, own chain file.
Implements Sec 3.4 Route A (72h from event, insured? slot, 14447, ticket hash),
Sec 3.5.4 document-in-hand (capture->hash->discard, manual fields, NO OCR,
Aadhaar auto-stripped), Sec 3.5.5 facilitator status check (no scraping),
mismatch = prompt not verdict, and the never-deny invariant.
Camera = browser getUserMedia (offline, zero deps); backend hashes bytes in
memory and NEVER writes the image to disk (Sec 3.1.3 / 3.6.1).
"""
import os, sys, json, hashlib, re, base64, difflib
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_CHAIN = os.path.join(ROOT, "ledger", "doc_chain.jsonl")

# ---------- isolated signed hash chain (Sec 3.6) ----------
KEYS = {"facilitator": "k-fac", "system": "k-sys", "citizen": "k-cit"}
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def body_of(r): return {k: v for k, v in r.items() if k not in ("hash", "sig")}
def sig_of(actor, body): return sha(KEYS.get(actor, "k-?") + json.dumps(body, sort_keys=True))[:16]
def hash_of(body, s): return sha(json.dumps(body, sort_keys=True) + s)[:16]

def append(chain_path, case_id, actor, action, detail=""):
    os.makedirs(os.path.dirname(chain_path), exist_ok=True)
    lines = open(chain_path, encoding="utf-8").read().splitlines() if os.path.exists(chain_path) else []
    prev = sha(lines[-1])[:16] if lines else sha("genesis")[:16]
    body = {"i": len(lines), "ts": datetime.now().isoformat(timespec="seconds"),
            "case_id": case_id, "actor": actor, "action": action, "detail": detail, "prev_hash": prev}
    s = sig_of(actor, body)
    rec = {**body, "sig": s, "hash": hash_of(body, s)}
    with open(chain_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec["hash"]

def verify(chain_path):
    if not os.path.exists(chain_path): return {"ok": True, "n": 0}
    lines = open(chain_path, encoding="utf-8").read().splitlines()
    for idx, line in enumerate(lines):
        r = json.loads(line); body = body_of(r)
        exp = sha("genesis")[:16] if idx == 0 else sha(lines[idx-1])[:16]
        if r.get("prev_hash") != exp or r.get("hash") != hash_of(body, r.get("sig","")) or r.get("sig") != sig_of(r.get("actor"), body):
            return {"ok": False, "broken": idx, "n": len(lines)}
    return {"ok": True, "n": len(lines)}

# ---------- Aadhaar safety net (Sec 3.1.3: never stored) ----------
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b|\b\d{12}\b")
def strip_aadhaar(text):
    t = text or ""
    found = bool(AADHAAR_RE.search(t))
    cleaned = AADHAAR_RE.sub("[REDACTED-AADHAAR]", t)
    return cleaned, found

# ---------- transliteration-aware fuzzy match (Sec 3.5.4) ----------
def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())
def fuzzy(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb: return 0.0, "missing-field"
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    tok = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    score = max(seq, 0.6*seq + 0.4*tok)
    flag = "MATCH" if score >= 0.82 else ("LIKELY-MISMATCH" if score >= 0.55 else "MISMATCH")
    return round(score, 3), flag

# ===================== ROUTE A: CROP LOSS (Sec 3.4) =====================
class CropReq(BaseModel):
    crop: str = ""
    cause: str = ""           # ola / baadh / aag / post-harvest
    event_when: str = "today" # today | yesterday | YYYY-MM-DD
    area_bigha: str = ""
    insured: str = ""         # yes | no | unknown
    ticket: str = ""          # 14447 ticket, logged by facilitator
    photo_hash: str = ""      # from /capture, optional evidence

def _event_date(when):
    now = datetime.now()
    if when == "yesterday": return now - timedelta(days=1)
    if when == "today": return now
    try: return datetime.fromisoformat(when)
    except Exception: return now

def crop_loss(req: CropReq):
    ev = _event_date(req.event_when)
    deadline = ev + timedelta(hours=72)            # 72h FROM THE EVENT, not from contact
    hrs_left = max(0, int((deadline - datetime.now()).total_seconds() // 3600))
    insured = (req.insured or "").lower()
    if insured == "yes":
        route = ("PMFBY insured: call 14447 from the booth now. Facilitator logs the "
                 "ticket number; it is hashed into the ledger. Crop Insurance app / bank / "
                 "agriculture office are the parallel channels.")
        close_rule = "Closes only when the insurer/helpline ticket is logged (Sec 3.8 Route A)."
    elif insured == "no":
        route = ("Uninsured: NOT a denial. Route to the state compensation channel "
                 "(Haryana: register prior loss on Meri Fasal Mera Byora, then the "
                 "Haryana Compensation Portal). A guided case is opened with the same clock.")
        close_rule = "Tracked as a guided case; never auto-denied (Sec 3)."
    else:
        route = ("Insured status unknown -> ask the ONE rule-changing question: "
                 "'Kya aap PMFBY ke tahat beema karwaya tha?' (Sec 3.2.4 next-question-by-rule-coverage).")
        close_rule = "Hold at facilitator until the insured? slot is filled."
    cid = "CX-" + datetime.now().strftime("%y%m%d-") + f"{abs(hash(req.crop+req.cause))%999:03d}"
    detail = f"crop={strip_aadhaar(req.crop)[0]};cause={strip_aadhaar(req.cause)[0]};insured={insured or 'unknown'};ev={ev.date()};ticket={strip_aadhaar(req.ticket)[0]}"
    h = append(DOC_CHAIN, cid, "system", "crop_case_opened", detail)
    if req.photo_hash:
        append(DOC_CHAIN, cid, "facilitator", "crop_evidence_hashed", req.photo_hash[:16])
    return {"case_id": cid, "route": "A", "clock_hours": 72, "event_date": ev.date().isoformat(),
            "deadline": deadline.isoformat(timespec="minutes"), "hours_left": hrs_left,
            "breaching": hrs_left < 12, "insured_slot": insured or "unknown",
            "route_text": route, "close_rule": close_rule, "ledger_hash": h,
            "label": "Facilitator guidance. Final decision by competent authority. The machine never denies (Sec 3)."}

# ===================== DOCUMENT CAPTURE (Sec 3.5.4 / 3.6.1) =====================
class CaptureReq(BaseModel):
    doc_type: str
    case_id: str = ""
    b64: str = ""             # jpeg data-url body from the browser canvas

def capture(req: CaptureReq):
    if not req.b64:
        return {"error": "no image frame received"}
    raw = base64.b64decode(req.b64)                # bytes live only in memory
    img_hash = hashlib.sha256(raw).hexdigest()     # hash the actual pixels
    # NOTE: we deliberately DO NOT write `raw` anywhere. Image discarded after extraction.
    h = append(DOC_CHAIN, req.case_id or "DOC", "facilitator", "doc_image_hashed",
               f"type={req.doc_type};img={img_hash[:16]}")
    return {"doc_type": req.doc_type, "image_sha256": img_hash, "ledger_hash": h,
            "bytes_in_memory": len(raw),
            "discarded": "Image hashed in RAM and discarded. Never written to disk (Sec 3.1.3, 3.6.1).",
            "fields_note": "Now enter ONLY names/dates as printed by hand. Aadhaar number is never a field (Sec 3.5.4)."}

# ===================== MISMATCH CHECK (Sec 3.5.4) =====================
class MatchReq(BaseModel):
    name_a: str; name_b: str; dob_a: str = ""; dob_b: str = ""
def mismatch(req: MatchReq):
    na, fa = strip_aadhaar(req.name_a); nb, fb = strip_aadhaar(req.name_b)
    score, flag = fuzzy(na, nb)
    dob_flag = "n/a"
    if req.dob_a and req.dob_b:
        dob_flag = "MATCH" if norm(req.dob_a) == norm(req.dob_b) else "CHECK-DOB"
    aadhaar_warn = fa or fb
    return {"name_score": score, "name_flag": flag, "dob_flag": dob_flag,
            "aadhaar_stripped": aadhaar_warn,
            "verdict": "PROMPT FOR HUMAN — not a verdict (Sec 3.5.4).",
            "next": ("Go to CSC for name/DOB correction support BEFORE bank seeding."
                     if flag != "MATCH" else "Names align; proceed to seeding route.")}

# ===================== KYC / BANK ROUTER (Sec 3.5 / 3.5.5) =====================
class KycReq(BaseModel):
    mismatch: bool = False
    ekyc_done: str = "unknown"     # yes|no|unknown  (facilitator-checked, Sec 3.5.5)
    seeded: str = "unknown"        # yes|no|unknown  (facilitator-checked on official portal)
    has_passbook: bool = True
    has_aadhaar: bool = True
def kyc_route(req: KycReq):
    steps, long_pole = [], []
    if not req.has_aadhaar or not req.has_passbook:
        steps.append({"desk": "panchayat", "action": "Obtain/attest the missing document (a planned step, not a denial)", "days": 2})
    if req.mismatch:
        steps.append({"desk": "csc", "action": "Name/DOB correction support (bring both originals)", "days": 1})
    if req.ekyc_done != "yes":
        steps.append({"desk": "csc", "action": "e-KYC (offline biometric/OTP at Aadhaar Seva Kendra — box cannot do this)", "days": 1})
    if req.seeded != "yes":
        steps.append({"desk": "bank", "action": "Aadhaar seeding into account (bank-side wait)", "days": 15, "lp": True})
    steps.append({"desk": "patwari", "action": "Land record (khasra/khuni) verify if scheme needs it", "days": 3, "lp": True})
    for s in steps:
        if s.get("lp"): long_pole.append(s)
    desks = []
    for s in steps:
        if s["desk"] not in desks: desks.append(s["desk"])
    naive = len(steps)
    return {"naive_visits": naive, "planned_visits": len(desks), "visits_saved": naive - len(desks),
            "route_order": desks, "steps": steps, "long_poles": long_pole,
            "critical_path_days": max([s["days"] for s in steps], default=0),
            "status_source": "ekyc/seeded values are FACILITATOR-CHECKED on the official portal with the citizen present (Sec 3.5.5). No scraping, no live bank API.",
            "label": "One visit = every step doable in person. Waiting steps are tracked, not promised (Sec 3.5.2)."}

# ===================== API =====================
app = FastAPI(title="HaqSetu Phase 2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
@app.post("/crop")
def api_crop(req: CropReq): return crop_loss(req)
@app.post("/capture")
def api_capture(req: CaptureReq): return capture(req)
@app.post("/mismatch")
def api_mismatch(req: MatchReq): return mismatch(req)
@app.post("/kyc")
def api_kyc(req: KycReq): return kyc_route(req)
@app.get("/chain")
def api_chain(): return verify(DOC_CHAIN)

# ===================== UI =====================
PAGE = r"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>HaqSetu Phase 2</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:18px;max-width:1080px;margin:auto;}
h1{color:#38bdf8;} h2{color:#94a3b8;margin-top:24px;border-bottom:1px solid #334155;padding-bottom:4px;}
.panel{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;margin:10px 0;}
button{padding:9px 13px;margin:3px;border:none;border-radius:7px;cursor:pointer;font-weight:bold;background:#38bdf8;color:#0f172a;}
button.red{background:#dc2626;color:#fff;} button.green{background:#10b981;color:#04211a;} button.amber{background:#f59e0b;color:#0f172a;}
input,select{background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:6px;padding:7px;margin:3px;}
video{width:320px;height:240px;background:#000;border-radius:8px;border:1px solid #334155;}
.out{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px;margin-top:8px;font-size:13px;white-space:pre-wrap;min-height:20px;}
.bad{color:#f87171;font-weight:bold;} .ok{color:#10b981;font-weight:bold;} .warn{color:#fbbf24;font-weight:bold;}
.tag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:bold;margin:2px;}
.tA{background:#7f1d1d;color:#fecaca;} .tCSC{background:#0c4a6e;color:#bae6fd;} .tBANK{background:#78350f;color:#fde68a;} .tPAT{background:#581c87;color:#e9d5ff;}
.note{font-size:12px;color:#94a3b8;line-height:1.5;}</style></head><body>
<h1>📷 HaqSetu Phase 2 — Crop Loss · Document Camera · KYC Router</h1>
<p class='note'>Camera = your laptop webcam (offline, zero install). It captures a frame, the backend hashes the pixels in RAM and <b>discards the image</b>. Fields are entered by hand — names/dates as printed, <b>never</b> an Aadhaar number (Sec 3.5.4). No live bank/e-KYC API is claimed (Sec 3.5.5).</p>

<h2>🌾 Route A — Crop Loss (72h from the EVENT)</h2>
<div class='panel'>
Crop <input id='c_crop' placeholder='gehu / wheat'> Cause <input id='c_cause' placeholder='ola / baadh / aag'>
When <select id='c_when'><option value='today'>aaj (today)</option><option value='yesterday'>kal (yesterday)</option><option value='2026-10-09'>date…</option></select>
Area <input id='c_area' placeholder='bigha' size='6'>
Insured? <select id='c_ins'><option value=''>— unknown —</option><option value='yes'>haan (yes)</option><option value='no'>nahi (no)</option></select>
Ticket <input id='c_tick' placeholder='14447 ticket' size='12'>
<button class='red' onclick='crop()'>▶ Open crop case</button>
<button class='amber' onclick='grabForCrop()'>📸 attach crop photo</button>
<div class='out' id='o_crop'></div></div>

<h2>🪪 Document Camera — capture · hash · discard</h2>
<div class='panel'>
Doc type <select id='d_type'><option>aadhaar</option><option>passbook</option><option>ration_card</option><option>land_record</option><option>income_cert</option><option>pension_cert</option><option>job_card</option></select>
Case id <input id='d_case' placeholder='optional CX-...' size='14'>
<button class='green' onclick='startCam()'>🎥 Start camera</button>
<button onclick='snap()'>📸 Capture & hash</button>
<button onclick='stopCam()'>⏹ Stop</button>
<br><video id='vid' autoplay playsinline muted></video>
<div class='out' id='o_cam'></div></div>

<h2>🔤 Name / DOB mismatch (prompt, not verdict)</h2>
<div class='panel'>
Name on Aadhaar <input id='m_a' placeholder='e.g. Kamla Devi'> Name on passbook <input id='m_b' placeholder='e.g. Kamla Devii'>
DOB A <input id='m_da' placeholder='01-01-1965' size='11'> DOB B <input id='m_db' placeholder='01-01-1965' size='11'>
<button onclick='match()'>▶ Check mismatch</button>
<div class='out' id='o_match'></div></div>

<h2>🗺️ KYC / Bank one-visit router (facilitator-checked status)</h2>
<div class='panel'>
Mismatch? <input type='checkbox' id='k_mm'> e-KYC done? <select id='k_ek'><option value='unknown'>unknown</option><option value='yes'>yes</option><option value='no'>no</option></select>
Seeded? <select id='k_sd'><option value='unknown'>unknown</option><option value='yes'>yes</option><option value='no'>no</option></select>
Has passbook <input type='checkbox' id='k_pb' checked> Has Aadhaar <input type='checkbox' id='k_ad' checked>
<button onclick='kyc()'>▶ Build route</button>
<div class='out' id='o_kyc'></div></div>

<h2>⛓️ Doc / Crop chain</h2><button class='green' onclick='chk()'>Verify chain</button> <span id='chain'></span>
<canvas id='cv' style='display:none'></canvas>
<script>
let stream=null;
const $=id=>document.getElementById(id);
function q(txt){const c=$('cv'),x=c.getContext('2d');c.width=160;c.height=120;x.drawImage($('vid'),0,0,160,120);
 const d=x.getImageData(0,0,160,120).data;let s=0,s2=0,n=0;for(let i=0;i<d.length;i+=4){const v=(d[i]+d[i+1]+d[i+2])/3;s+=v;s2+=v*v;n++;}
 const mean=s/n,variance=s2/n-mean*mean;return {mean:Math.round(mean),variance:Math.round(variance)};}
async function startCam(){try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment',width:640,height:480}});$('vid').srcObject=stream;$('o_cam').textContent='Camera live. Place the document flat under the lens.';}catch(e){$('o_cam').innerHTML='<span class=bad>Camera blocked: '+e.message+' — allow permission, or use a USB webcam.</span>';}}
function stopCam(){if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;$('vid').srcObject=null;}}
async function snap(){if(!stream)return $('o_cam').textContent='Start the camera first.';
 const qv=q();let warn='';if(qv.mean<45||qv.mean>225||qv.variance<250)warn='\n⚠ LOW QUALITY (mean '+qv.mean+', var '+qv.variance+') — retake in better light / flatter.';
 const c=$('cv'),x=c.getContext('2d');c.width=$('vid').videoWidth||640;c.height=$('vid').videoHeight||480;x.drawImage($('vid'),0,0,c.width,c.height);
 const url=c.toDataURL('image/jpeg',0.85);const b64=url.split(',')[1];
 const r=await fetch('/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({doc_type:$('d_type').value,case_id:$('d_case').value,b64})});
 const d=await r.json();
 $('o_cam').innerHTML='<span class=ok>✅ HASHED & DISCARDED</span>'+warn+'\ndoc='+d.doc_type+'\nimage sha256='+d.image_sha256+'\nbytes hashed in RAM = '+d.bytes_in_memory+'\nledger '+d.ledger_hash+'\n'+d.discarded+'\n'+d.fields_note;
 $('d_case').value=$('d_case').value||('DOC-'+Date.now()%100000);}
async function grabForCrop(){if(!stream){await startCam();}setTimeout(async()=>{const c=$('cv'),x=c.getContext('2d');c.width=$('vid').videoWidth||640;c.height=$('vid').videoHeight||480;x.drawImage($('vid'),0,0,c.width,c.height);const b64=c.toDataURL('image/jpeg',0.85).split(',')[1];
 const r=await fetch('/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({doc_type:'crop_evidence',case_id:$('d_case').value||'CROP',b64})});const d=await r.json();$('c_tick').dataset.ph=d.image_sha256;$('o_crop').innerHTML='<span class=ok>📸 crop photo hashed '+d.image_sha256.slice(0,16)+'… (image discarded)</span>';},400);}
async function crop(){const r=await fetch('/crop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({crop:$('c_crop').value,cause:$('c_cause').value,event_when:$('c_when').value,area_bigha:$('c_area').value,insured:$('c_ins').value,ticket:$('c_tick').value,photo_hash:$('c_tick').dataset.ph||''})});
 const d=await r.json();const br=d.breaching?'<span class=bad>⏳ BREACHING (&lt;12h left)</span>':'<span class=ok>within 72h window</span>';
 $('o_crop').innerHTML='<span class="tag tA">Route '+d.route+'</span> <b>'+d.case_id+'</b> · event '+d.event_date+' · deadline '+d.deadline+' · '+br+' ('+d.hours_left+'h left)\ninsured slot: '+d.insured_slot+'\n'+d.route_text+'\nClose rule: '+d.close_rule+'\nledger '+d.ledger_hash+'\n<span class=note>'+d.label+'</span>';}
async function match(){const r=await fetch('/mismatch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name_a:$('m_a').value,name_b:$('m_b').value,dob_a:$('m_da').value,dob_b:$('m_db').value})});
 const d=await r.json();const cls=d.name_flag==='MATCH'?'ok':(d.name_flag==='LIKELY-MISMATCH'?'warn':'bad');
 $('o_match').innerHTML='name score '+d.name_score+' → <span class='+cls+'>'+d.name_flag+'</span> · DOB '+d.dob_flag+(d.aadhaar_stripped?' · <span class=bad>Aadhaar-like digits auto-stripped</span>':'')+'\n'+d.verdict+'\nNext: '+d.next;}
async function kyc(){const r=await fetch('/kyc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mismatch:$('k_mm').checked,ekyc_done:$('k_ek').value,seeded:$('k_sd').value,has_passbook:$('k_pb').checked,has_aadhaar:$('k_ad').checked})});
 const d=await r.json();let h='naive '+d.naive_visits+' → planned '+d.planned_visits+' visits (saved '+d.visits_saved+') · critical path '+d.critical_path_days+'d\nOrder: '+d.route_order.join(' → ')+'\n';
 d.steps.forEach(s=>{const t=s.desk==='csc'?'tCSC':s.desk==='bank'?'tBANK':s.desk==='patwari'?'tPAT':'tA';h+='<span class="tag '+t+'">'+s.desk+'</span> '+s.action+' ('+s.days+'d)'+(s.lp?' <span class=warn>LONG-POLE</span>':'')+'\n';});
 h+='\n'+d.status_source+'\n<span class=note>'+d.label+'</span>';$('o_kyc').innerHTML=h;}
async function chk(){const v=await (await fetch('/chain')).json();$('chain').innerHTML=v.ok?'<span class=ok>✅ CHAIN OK ('+v.n+')</span>':'<span class=bad>❌ TAMPER at #'+v.broken+'</span>';}
chk();
</script></body></html>"""
@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("📷 Phase 2 on http://127.0.0.1:8011")
    uvicorn.run(app, host="127.0.0.1", port=8011)