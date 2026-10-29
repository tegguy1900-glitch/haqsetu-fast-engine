"""
HaqSetu CLOSURE LOOP (Core #5; rules from Sec 3.6, 3.7, 3.8)
Pass / Reject with closed-list reason codes; rotating verifier pool with
desk exclusion; separate Citizen Confirm act; disputed closure auto-reopens;
10% hash-selected callback audit; weekly batched digest with visible block
acknowledgement; chained closure ledger with verify + tamper challenge.
Port 8006.
"""
import hashlib, json, os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAIN = os.path.join(ROOT, "ledger", "closure_chain.jsonl")
SNAP = os.path.join(ROOT, "ledger", "closure_cases.json")

REASON_CODES = ["no_funds", "outside_panchayat_power", "duplicate", "ineligible_per_rule", "deferred_to_date"]
VERIFIER_POOL = [{"id": "teacher", "role": "School Teacher"},
                 {"id": "asha", "role": "ASHA Worker"},
                 {"id": "shg", "role": "SHG Representative"}]
DESKS = ["panchayat_secretary", "csc", "bank_branch", "revenue_patwari", "bdo"]
COLOR = {"OPEN": "red", "REOPENED": "red", "APPROVED": "amber",
         "CLOSED_AUDIT": "amber", "REJECTED": "amber", "CLOSED": "green"}

CASES, DIGESTS = {}, {}
FORCE_AUDIT = {"on": False}

def sha(t): return hashlib.sha256(t.encode()).hexdigest()

def load():
    if os.path.exists(SNAP):
        d = json.load(open(SNAP, encoding="utf-8"))
        CASES.update(d.get("cases", {})); DIGESTS.update(d.get("digests", {}))

def save():
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    json.dump({"cases": CASES, "digests": DIGESTS}, open(SNAP, "w", encoding="utf-8"), indent=1)

def append(case_id, actor, action, detail=""):
    os.makedirs(os.path.dirname(CHAIN), exist_ok=True)
    lines = open(CHAIN, encoding="utf-8").read().splitlines() if os.path.exists(CHAIN) else []
    prev = sha(lines[-1])[:16] if lines else sha("genesis")[:16]
    rec = {"i": len(lines), "ts": datetime.now().isoformat(timespec="seconds"),
           "case_id": case_id, "actor": actor, "action": action,
           "detail": detail, "prev_hash": prev}
    rec["hash"] = sha(json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True))[:16]
    with open(CHAIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec

def verify_chain():
    if not os.path.exists(CHAIN): return {"ok": True, "n": 0}
    lines = open(CHAIN, encoding="utf-8").read().splitlines()
    for idx, line in enumerate(lines):
        rec = json.loads(line)
        exp_prev = sha("genesis")[:16] if idx == 0 else sha(lines[idx - 1])[:16]
        body = {k: v for k, v in rec.items() if k != "hash"}
        if rec.get("prev_hash") != exp_prev or rec.get("hash") != sha(json.dumps(body, sort_keys=True))[:16]:
            return {"ok": False, "broken_index": idx, "record": rec, "n": len(lines)}
    return {"ok": True, "n": len(lines)}

def audit_sample(case_id, closure_hash):
    if FORCE_AUDIT["on"]: return True
    return int(sha(case_id + "|" + closure_hash)[:8], 16) % 10 == 0

class CaseReq(BaseModel): route: str; desk: str; summary: str
class IdReq(BaseModel): case_id: str
class TicketReq(BaseModel): case_id: str; ticket: str
class DecisionReq(BaseModel): case_id: str; action: str; reason_code: str = ""; official: str = "named_official"
class VerifyReq(BaseModel): case_id: str; verifier_id: str
class CitizenReq(BaseModel): case_id: str; action: str
class AuditReq(BaseModel): case_id: str; result: str
class AgeReq(BaseModel): case_id: str; hours: int
class TamperReq(BaseModel): index: int
class AckReq(BaseModel): digest_id: str

app = FastAPI(title="HaqSetu Closure Loop")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/cases")
def cases():
    out = []
    for c in CASES.values():
        d = dict(c); d["color"] = COLOR[c["state"]]
        d["verifier_pool"] = [v for v in VERIFIER_POOL if v["role"].lower().replace(" ", "_") != c["desk"]]
        out.append(d)
    return {"cases": out, "digests": list(DIGESTS.values()), "force_audit": FORCE_AUDIT["on"]}

@app.post("/case")
def new_case(r: CaseReq):
    if r.route not in "ABCD" or r.desk not in DESKS:
        return {"error": "route must be A-D and desk from the list"}
    cid = "HS-" + datetime.now().strftime("%y%m%d-") + f"{len(CASES)+1:03d}"
    CASES[cid] = {"id": cid, "route": r.route, "desk": r.desk, "summary": r.summary,
                  "state": "OPEN", "verifiers": [], "ticket": "", "esc": "",
                  "reason_code": "", "audit_sample": False, "digest_sent": False,
                  "age_hours": 0, "opened": datetime.now().isoformat(timespec="minutes")}
    append(cid, "facilitator", "case_opened", r.summary[:60]); save()
    return CASES[cid]

@app.post("/ticket")
def ticket(r: TicketReq):
    c = CASES.get(r.case_id)
    if not c: return {"error": "no such case"}
    c["ticket"] = r.ticket
    append(c["id"], "facilitator", "ticket_logged", r.ticket); save()
    return c

@app.post("/decision")
def decision(r: DecisionReq):
    c = CASES.get(r.case_id)
    if not c: return {"error": "no such case"}
    if r.action == "reject":
        if r.reason_code not in REASON_CODES:
            return {"error": "Reject needs a reason code from the closed list (Sec 3.6). The machine never denies; a named official may, only with a written reason."}
        c["state"], c["reason_code"], c["official"] = "REJECTED", r.reason_code, r.official
        append(c["id"], r.official, "rejected_with_reason", r.reason_code); save()
        return c
    if c["state"] not in ("OPEN", "REOPENED"):
        return {"error": "decision only on open/reopened cases"}
    c["state"] = "APPROVED"
    append(c["id"], r.official, "decision_pass", ""); save()
    return c

@app.post("/verify")
def verify(r: VerifyReq):
    c = CASES.get(r.case_id)
    if not c: return {"error": "no such case"}
    if c["state"] != "APPROVED": return {"error": "verifier acts after the official decision"}
    v = next((p for p in VERIFIER_POOL if p["id"] == r.verifier_id), None)
    if not v: return {"error": "unknown verifier"}
    if v["role"].lower().replace(" ", "_") == c["desk"]:
        return {"error": "Verifier must be outside the implementing desk (Sec 3.7)."}
    if r.verifier_id in c["verifiers"]: return {"error": "the same person cannot verify twice"}
    c["verifiers"].append(r.verifier_id)
    append(c["id"], v["role"], "verifier_confirmed", str(len(c["verifiers"])))
    if c["route"] == "C" and len(c["verifiers"]) >= 2:
        rec = append(c["id"], "system", "closure_check", "two verifiers")
        c["audit_sample"] = audit_sample(c["id"], rec["hash"])
        c["state"] = "CLOSED_AUDIT" if c["audit_sample"] else "CLOSED"
        append(c["id"], "system", "audit_sampled" if c["audit_sample"] else "closed", "route C")
    save()
    return c

@app.post("/citizen")
def citizen(r: CitizenReq):
    c = CASES.get(r.case_id)
    if not c: return {"error": "no such case"}
    if r.action == "dispute":
        if c["state"] not in ("CLOSED", "CLOSED_AUDIT"): return {"error": "nothing closed to dispute"}
        c["state"] = "REOPENED"
        append(c["id"], "citizen", "citizen_disputed", "reopens automatically, shows on board"); save()
        return c
    if c["state"] != "APPROVED": return {"error": "citizen confirms after the official decision"}
    if c["route"] == "C": return {"error": "Route C closes on two verifiers, not citizen confirm (Sec 3.8)."}
    if c["route"] == "A" and not c["ticket"]:
        return {"error": "Route A closes only when the insurer/helpline ticket is logged (Sec 3.8)."}
    if c["route"] == "D" and not c["esc"]:
        return {"error": "Route D closes only when the escalation reference is logged (Sec 3.8). Log it with /ticket."}
    rec = append(c["id"], "citizen", "citizen_confirmed", "separate physical act")
    c["audit_sample"] = audit_sample(c["id"], rec["hash"])
    c["state"] = "CLOSED_AUDIT" if c["audit_sample"] else "CLOSED"
    append(c["id"], "system", "audit_sampled" if c["audit_sample"] else "closed", "10% callback sample")
    save()
    return c

@app.post("/audit")
def audit(r: AuditReq):
    c = CASES.get(r.case_id)
    if not c or c["state"] != "CLOSED_AUDIT": return {"error": "only audit-pending closures can be audited"}
    if r.result == "confirmed":
        c["state"] = "CLOSED"; append(c["id"], "independent_callback", "audit_confirmed", "")
    else:
        c["state"] = "REOPENED"; append(c["id"], "independent_callback", "audit_reopened", "closure was false")
    save()
    return c

@app.post("/age")
def age(r: AgeReq):
    c = CASES.get(r.case_id)
    if not c: return {"error": "no such case"}
    c["age_hours"] += r.hours
    append(c["id"], "system", "clock_advanced", "+" + str(r.hours) + "h"); save()
    return c

@app.post("/digest")
def digest():
    over = [c for c in CASES.values() if c["age_hours"] >= 48
            and c["state"] in ("OPEN", "APPROVED", "REOPENED") and not c["digest_sent"]]
    if not over:
        return {"note": "Nothing overdue. One escalation per case, weekly batch (Sec 3.8)."}
    did = "DIG-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    DIGESTS[did] = {"id": did, "case_ids": [c["id"] for c in over],
                    "sent": datetime.now().isoformat(timespec="minutes"), "ack": None}
    for c in over: c["digest_sent"] = True
    append("DIGEST", "system", "weekly_digest_sent", did); save()
    return DIGESTS[did]

@app.post("/ack")
def ack(r: AckReq):
    d = DIGESTS.get(r.digest_id)
    if not d: return {"error": "no such digest"}
    d["ack"] = datetime.now().isoformat(timespec="minutes")
    append("DIGEST", "block_office", "block_ack", d["id"]); save()
    return d

@app.get("/chain")
def chain():
    lines = open(CHAIN, encoding="utf-8").read().splitlines() if os.path.exists(CHAIN) else []
    return {"records": [json.loads(l) for l in lines], "verify": verify_chain()}

@app.post("/tamper")
def tamper(r: TamperReq):
    lines = open(CHAIN, encoding="utf-8").read().splitlines()
    if not (0 <= r.index < len(lines)): return {"error": "index out of range"}
    rec = json.loads(lines[r.index])
    rec["action"] = rec["action"][:-1] + ("X" if not rec["action"].endswith("X") else "Y")
    lines[r.index] = json.dumps(rec)
    open(CHAIN, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return {"tampered_index": r.index}

@app.post("/force_audit")
def force_audit():
    FORCE_AUDIT["on"] = not FORCE_AUDIT["on"]
    return {"on": FORCE_AUDIT["on"]}

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>Closure Loop</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:20px;}
h1{color:#38bdf8;} h3{color:#94a3b8;margin-top:22px;}
.card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;margin:10px 0;max-width:900px;}
button{padding:8px 12px;margin:3px;border:none;border-radius:6px;cursor:pointer;font-weight:bold;background:#38bdf8;color:#0f172a;}
button.red{background:#dc2626;color:#fff;} button.green{background:#10b981;color:#04211a;} button.amber{background:#f59e0b;color:#0f172a;}
select,input{background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:6px;padding:6px;margin:3px;}
.led{display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:6px;vertical-align:middle;}
.red{box-shadow:0 0 8px #dc2626;background:#dc2626;} .amber{box-shadow:0 0 8px #f59e0b;background:#f59e0b;} .green{box-shadow:0 0 8px #10b981;background:#10b981;}
.badge{padding:3px 8px;border-radius:5px;font-size:12px;font-weight:bold;}
pre{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px;font-size:12px;overflow:auto;max-height:260px;}
.err{color:#f87171;font-weight:bold;margin:6px 0;}</style></head><body>
<h1>🔐 HaqSetu CLOSURE LOOP</h1>
<p>Pass / Reject (closed-list reasons) · rotating verifiers · separate Citizen Confirm · 10% callback audit · weekly digest · chained ledger.</p>
<div class='card'><b>New case</b>
 Route <select id='r'><option>A</option><option>B</option><option>C</option><option>D</option></select>
 Desk <select id='d'></select>
 <input id='s' placeholder='summary e.g. lane drain overflow' size='34'>
 <button onclick='post("/case",{route:el("r").value,desk:el("d").value,summary:el("s").value})'>Open case</button>
 <button class='amber' onclick='post("/force_audit",{})'>🎲 Toggle force-audit-sample</button>
 <div id='err' class='err'></div></div>
<h3>🏘️ BOARD (ESP32 preview)</h3><div id='board'></div>
<h3>📁 CASES</h3><div id='cases'></div>
<h3>📨 WEEKLY DIGEST (block acknowledgement is visible)</h3>
<button onclick='post("/digest",{})'>Build weekly digest</button><div id='dig'></div>
<h3>⛓️ CLOSURE LEDGER</h3>
<button class='green' onclick='chain()'>Verify chain</button>
<button class='red' onclick='tamper()'>🧨 Tamper line 2</button>
<pre id='chain'></pre>
<script>
const DESKS=["panchayat_secretary","csc","bank_branch","revenue_patwari","bdo"];
el=id=>document.getElementById(id);
DESKS.forEach(d=>el('d').add(new Option(d,d)));
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const d=await r.json(); el('err').textContent=d.error||''; refresh(); return d;}
async function refresh(){const d=await (await fetch('/cases')).json();
 el('board').innerHTML=d.cases.map(c=>`<span class='led ${c.color}' title='${c.id}'></span>`).join('')||'<i>empty</i>';
 el('cases').innerHTML=d.cases.map(c=>card(c)).join('')||'<i>no cases yet</i>';
 el('dig').innerHTML=d.digests.map(g=>`<div class='card'>${g.id} · ${g.case_ids.join(', ')} · sent ${g.sent} · `+
   (g.ack?`<span class='badge' style='background:#10b981'>ACK ${g.ack}</span>`:`<span class='badge' style='background:#dc2626'>AWAITING BLOCK ACK — visible</span>`)+
   ` <button onclick="post('/ack',{digest_id:'${g.id}'})">Log block ack</button></div>`).join('');}
function card(c){const vp=c.verifier_pool.map(v=>`<option value='${v.id}'>${v.role}</option>`).join('');
 return `<div class='card'><span class='led ${c.color}'></span><b>${c.id}</b> Route ${c.route} · desk ${c.desk} · <span class='badge' style='background:#334155'>${c.state}</span> · age ${c.age_hours}h<br>
 ${c.summary}<br>verifiers: ${c.verifiers.join('+')||'none'} ${c.ticket?'· ticket '+c.ticket:''} ${c.reason_code?'· reason '+c.reason_code:''} ${c.audit_sample?'· 🎯 10% audit sample':''}<br>
 <button onclick="post('/ticket',{case_id:'${c.id}',ticket:'14447-'+Math.floor(Math.random()*9000+1000)})}>Log ticket/esc-ref</button>
 <button class='green' onclick="post('/decision',{case_id:'${c.id}',action:'pass',official:'sarpanch'})}>PASS</button>
 <select id='rc-${c.id}'>${["no_funds","outside_panchayat_power","duplicate","ineligible_per_rule","deferred_to_date"].map(r=>`<option>${r}</option>`).join('')}</select>
 <button class='red' onclick="post('/decision',{case_id:'${c.id}',action:'reject',reason_code:el('rc-${c.id}').value,official:'sarpanch'})}>REJECT</button>
 <select id='vf-${c.id}'>${vp}</select>
 <button class='amber' onclick="post('/verify',{case_id:'${c.id}',verifier_id:el('vf-${c.id}').value})}>VERIFY</button>
 <button class='green' onclick="post('/citizen',{case_id:'${c.id}',action:'confirm'})}>📦 CITIZEN CONFIRM (separate box)</button>
 <button class='red' onclick="post('/citizen',{case_id:'${c.id}',action:'dispute'})">DISPUTE</button>
 <button onclick="post('/audit',{case_id:'${c.id}',result:'confirmed'})}>Audit: confirm</button>
 <button class='red' onclick="post('/audit',{case_id:'${c.id}',result:'reopened'})}>Audit: reopen</button>
 <button onclick="post('/age',{case_id:'${c.id}',hours:48})}>⏩ +48h</button></div>`;}
async function chain(){const d=await (await fetch('/chain')).json();
 el('chain').textContent=JSON.stringify(d.verify,null,1)+'\\n'+d.records.map(r=>`${r.i} ${r.case_id} ${r.actor} ${r.action} ${r.hash}`).join('\\n');}
async function tamper(){await post('/tamper',{index:2}); await chain();}
refresh();
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

load()
if __name__ == "__main__":
    print("🔐 Closure Loop on http://127.0.0.1:8006")
    uvicorn.run(app, host="127.0.0.1", port=8006)