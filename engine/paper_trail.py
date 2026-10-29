"""
HaqSetu CRYPTOGRAPHIC PAPER TRAIL (Stretch #1, Proposal Sec 3.6 & 7)
Issues a printable "Haq Receipt" (citizen slip) carrying case ID, route,
next steps, clock, short chain code and a QR payload whose hash is appended
to the Sabha Ledger at issue time. Any slip can later be verified:
VALID (paper and chain agree) or INVALID/TAMPER. Fully offline. Port 8004.
"""
import hashlib, json, os, io, sys
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

try:
    import qrcode
    import qrcode.image.svg
    QR_OK = True
except Exception:
    QR_OK = False

LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ledger", "chain.jsonl")

PERSONAS = {
 "KAMLA": {"case_id": "HS-2026-0001", "citizen": "Kamla Devi (ward-only label)",
   "route": "B - Individual entitlement",
   "needs": ["Pension 3 months unpaid", "PM-KISAN instalment stuck"],
   "next_steps": ["Bring Aadhaar card + bank passbook (names as printed)",
                  "Panchayat attests residence where rules allow",
                  "Camp-day slot: CSC e-KYC, then bank seeding"],
   "long_pole": "Land-record correction (owner: Revenue Patwari; tracked, not promised)",
   "clock_hours": 48,
   "flags": ["Name mismatch flagged: Aadhaar vs passbook (human prompt, not verdict)"]},
 "KISHAN": {"case_id": "HS-2026-0002", "citizen": "Kishan (ward-only label)",
   "route": "A - Citizen-direct, immediate",
   "needs": ["Hail flattened wheat last night"],
   "next_steps": ["Insured under PMFBY: YES -> facilitator calls 14447 from booth",
                  "Helpline ticket number logged to ledger"],
   "long_pole": None, "clock_hours": 72,
   "flags": ["72-hour intimation clock started at event time"]},
}

def sha(t): return hashlib.sha256(t.encode()).hexdigest()

def last_chain_code():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        if lines:
            rec = json.loads(lines[-1])
            return (rec.get("hash") or rec.get("receipt_hash") or sha(lines[-1]))[:8]
    except Exception:
        pass
    return sha("genesis")[:8]

def make_qr_svg(payload):
    if not QR_OK: return ""
    qr = qrcode.QRCode(border=2)
    qr.add_data(payload); qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(image_factory=qrcode.image.svg.SvgImage).save(buf)
    return buf.getvalue().decode("utf-8")

def issue(persona_key):
    p = PERSONAS[persona_key]
    chain = last_chain_code()
    now = datetime.now()
    core = f"{p['case_id']}|{p['route']}|{p['clock_hours']}|{chain}|{now.isoformat(timespec='minutes')}"
    h = sha(core)
    payload = f"HAQSETU|{p['case_id']}|{chain}|{h[:16]}"
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "receipt_issued", "case_id": p["case_id"],
                            "chain_code": chain, "receipt_hash": h,
                            "timestamp": now.isoformat()}) + "\n")
    return {**p, "chain_code": chain, "issued": now.isoformat(timespec="minutes"),
            "deadline": (now + timedelta(hours=p["clock_hours"])).isoformat(timespec="minutes"),
            "receipt_hash": h, "qr_payload": payload, "qr_svg": make_qr_svg(payload), "qr_ok": QR_OK}

class IssueReq(BaseModel): persona: str
class VerifyReq(BaseModel): case_id: str; chain_code: str; receipt_hash: str

def verify(req: VerifyReq):
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                r = json.loads(line)
                if (r.get("event") == "receipt_issued" and r.get("case_id") == req.case_id
                        and r.get("receipt_hash") == req.receipt_hash
                        and r.get("chain_code") == req.chain_code):
                    return {"verdict": "VALID", "note": "Slip matches the Sabha Ledger. Paper and chain agree."}
    except Exception:
        pass
    return {"verdict": "INVALID / TAMPER", "note": "No ledger entry matches this slip. Re-issue at booth; flag to independent verifier."}

app = FastAPI(title="HaqSetu Paper Trail")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/issue")
def api_issue(req: IssueReq): return issue(req.persona)
@app.post("/verify")
def api_verify(req: VerifyReq): return verify(req)

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>Haq Receipt</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:24px;}
h1{color:#38bdf8;} button{padding:10px 16px;margin:4px;border:none;border-radius:8px;background:#38bdf8;color:#0f172a;font-weight:bold;cursor:pointer;}
.receipt{background:#fff;color:#111;max-width:420px;margin:18px auto;padding:18px;border-radius:4px;font-size:13px;line-height:1.45;
 background-image:linear-gradient(#fff 95%, transparent);box-shadow:0 6px 24px rgba(0,0,0,.5);}
.receipt h2{margin:0 0 4px;font-size:16px;} .receipt .code{font-size:22px;letter-spacing:3px;font-weight:bold;margin:6px 0;}
.receipt svg{width:130px;height:130px;display:block;margin:8px auto;} .receipt hr{border:none;border-top:1px dashed #999;margin:8px 0;}
.badge{display:inline-block;padding:8px 16px;border-radius:8px;font-weight:bold;margin-top:10px;}
.ok{background:#10b981;color:#04211a;} .bad{background:#dc2626;color:#fff;}
input{background:#1e293b;color:#f8fafc;border:1px solid #334155;border-radius:6px;padding:8px;width:340px;font-family:monospace;}
@media print{body *{visibility:hidden;} .receipt,.receipt *{visibility:visible;} .receipt{position:absolute;left:0;top:0;box-shadow:none;}}
</style></head><body>
<h1>🧾 HaqSetu CRYPTOGRAPHIC PAPER TRAIL</h1>
<p>Issue a citizen slip (persona card). Its hash is appended to the Sabha Ledger at issue time. Verify any slip later.</p>
<button onclick="issue('KAMLA')">👵 Issue slip: Kamla Devi (Route B)</button>
<button onclick="issue('KISHAN')">🌾 Issue slip: Kishan (Route A, 72h)</button>
<button onclick="window.print()">🖨️ Print slip (thermal/any printer)</button>
<div id='receipt'></div>
<h3>🔎 Slip Verification (block office / verifier)</h3>
Case ID <input id='v_case'><br><br>
Chain code <input id='v_chain' style='width:120px'> Receipt hash <input id='v_hash' style='width:260px'><br><br>
<button onclick="doVerify(false)">Verify slip</button>
<button style='background:#dc2626;color:#fff' onclick="doVerify(true)">🧪 Simulate ALTERED slip (tear test)</button>
<div id='verdict'></div>
<script>
let last=null;
async function issue(k){const r=await fetch('/issue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona:k})});
 last=await r.json();
 document.getElementById('receipt').innerHTML=
 `<div class='receipt'><h2>HAQSETU — HAQ RECEIPT (facilitator guidance)</h2>
 <div>${last.citizen}</div><div>Case: <b>${last.case_id}</b> · Route ${last.route}</div>
 <div class='code'>CHAIN ${last.chain_code}</div><hr>
 <b>Needs:</b><ul>${last.needs.map(n=>`<li>${n}</li>`).join('')}</ul>
 <b>Next steps:</b><ul>${last.next_steps.map(n=>`<li>${n}</li>`).join('')}</ul>
 ${last.long_pole?`<b>Long-pole (tracked):</b> ${last.long_pole}<br>`:''}
 ${last.flags.map(f=>`⚠ ${f}<br>`).join('')}<hr>
 <div>Issued ${last.issued} · <b>Clock deadline ${last.deadline}</b></div>
 <div>Hash ${last.receipt_hash.slice(0,16)}…</div>
 ${last.qr_svg||'<i>(QR unavailable: pip install qrcode)</i>'}
 <div style='font-size:11px'>Slip carries pictogram + number. Facilitator reads slip back. Escalate anytime with this code.</div></div>`;
 document.getElementById('v_case').value=last.case_id;
 document.getElementById('v_chain').value=last.chain_code;
 document.getElementById('v_hash').value=last.receipt_hash;
 document.getElementById('verdict').innerHTML='';}
async function doVerify(alter){let h=document.getElementById('v_hash').value;
 if(alter){h=h.slice(0,-1)+(h.slice(-1)==='0'?'1':'0');document.getElementById('v_hash').value=h;}
 const r=await fetch('/verify',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({case_id:document.getElementById('v_case').value,chain_code:document.getElementById('v_chain').value,receipt_hash:h})});
 const d=await r.json();
 document.getElementById('verdict').innerHTML=`<div class='badge ${d.verdict=='VALID'?'ok':'bad'}'>${d.verdict}</div><p>${d.note}</p>`;}
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "issue":
        r = issue(sys.argv[2])
        print(f"HAQ RECEIPT {r['case_id']} | chain {r['chain_code']} | deadline {r['deadline']}")
        print(f"hash {r['receipt_hash']}")
        if QR_OK:
            qr = qrcode.QRCode(border=2); qr.add_data(r["qr_payload"]); qr.make(fit=True)
            qr.print_ascii(invert=True)
    else:
        print("🧾 Paper Trail on http://127.0.0.1:8004")
        uvicorn.run(app, host="127.0.0.1", port=8004)