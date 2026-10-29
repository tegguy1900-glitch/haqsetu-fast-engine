"""
HaqSetu TAMPER CHALLENGE (Core #6; rules from Sec 3.6, Sec 2 metrics)
Judge edits past ledger lines in the browser; the check shows TAMPER and
names the entry. Attack ladder: modify -> delete -> insert -> swap ->
single-insider rebuild (caught by per-actor signatures) -> all-key-holder
rebuild (local chain OK, caught by weekly anchor) -> anchor replacement
(the honest escape, stated on the poster). Demo chain only. Port 8008.
"""
import hashlib, json, os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAIN = os.path.join(ROOT, "ledger", "demo_chain.jsonl")
ANCHOR = os.path.join(ROOT, "ledger", "demo_anchor.json")
KEYS = {"facilitator": "k-fac", "official": "k-off", "verifier": "k-ver",
        "citizen": "k-cit", "system": "k-sys"}

def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def body_of(r): return {k: v for k, v in r.items() if k not in ("hash", "sig")}
def sig_of(actor, body): return sha(KEYS.get(actor, "k-UNKNOWN") + json.dumps(body, sort_keys=True))[:16]
def hash_of(body, s): return sha(json.dumps(body, sort_keys=True) + s)[:16]

def make_rec(i, case, actor, action, detail, prev):
    body = {"i": i, "ts": datetime.now().isoformat(timespec="seconds"), "case_id": case,
            "actor": actor, "action": action, "detail": detail, "prev_hash": prev}
    s = sig_of(actor, body)
    return {**body, "sig": s, "hash": hash_of(body, s)}

def seed():
    rows, prev = [], sha("genesis")[:16]
    spec = [("HS-001", "facilitator", "case_opened", "pension 3 months unpaid"),
            ("HS-001", "official", "decision_pass", ""),
            ("HS-002", "facilitator", "case_opened", "lane drain overflow"),
            ("HS-001", "citizen", "citizen_confirmed", "slip code"),
            ("HS-003", "facilitator", "case_opened", "hail on wheat"),
            ("HS-003", "system", "clock_72h", "insured yes"),
            ("HS-003", "official", "ticket_logged", "14447-889"),
            ("HS-000", "verifier", "weekly_chain_check", "anchor published")]
    for i, (c, a, ac, d) in enumerate(spec):
        r = make_rec(i, c, a, ac, d, prev)
        rows.append(r); prev = r["hash"]
    os.makedirs(os.path.dirname(CHAIN), exist_ok=True)
    with open(CHAIN, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    json.dump({"index": 5, "hash": rows[5]["hash"],
               "note": "weekly anchor: notice board + block office + verifier"},
              open(ANCHOR, "w", encoding="utf-8"))

def load():
    if not os.path.exists(CHAIN): seed()
    return [json.loads(l) for l in open(CHAIN, encoding="utf-8").read().splitlines() if l.strip()]

def save_rows(rows):
    with open(CHAIN, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")

def verify():
    rows = load(); issues = []
    for idx, r in enumerate(rows):
        body = body_of(r)
        if r.get("sig") != sig_of(r.get("actor"), body): issues.append([idx, "signature"])
        if r.get("hash") != hash_of(body, r.get("sig", "")): issues.append([idx, "hash"])
        exp = sha("genesis")[:16] if idx == 0 else rows[idx - 1].get("hash")
        if r.get("prev_hash") != exp: issues.append([idx, "link"])
    a = json.load(open(ANCHOR, encoding="utf-8")) if os.path.exists(ANCHOR) else None
    anchor_ok = True
    if a and a["index"] < len(rows):
        anchor_ok = rows[a["index"]].get("hash") == a["hash"]
    return {"issues": issues, "anchor_ok": anchor_ok, "n": len(rows)}

def relink_rehash(rows, start, resign):
    prev = rows[start - 1]["hash"] if start > 0 else sha("genesis")[:16]
    for idx in range(start, len(rows)):
        r = rows[idx]; body = body_of(r); body["prev_hash"] = prev
        s = sig_of(r["actor"], body) if resign else r.get("sig", "")
        rows[idx] = {**body, "sig": s, "hash": hash_of(body, s)}
        prev = rows[idx]["hash"]

class SaveReq(BaseModel): index: int; record: dict
class AttackReq(BaseModel): kind: str

app = FastAPI(title="HaqSetu Tamper Challenge")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/chain")
def chain(): return {"rows": load(), "verify": verify()}

@app.post("/save")
def save(r: SaveReq):
    rows = load()
    if not (0 <= r.index < len(rows)): return {"error": "index out of range"}
    rows[r.index] = r.record
    save_rows(rows); return verify()

@app.post("/attack")
def attack(r: AttackReq):
    rows = load(); k = r.kind
    if k == "modify":
        rows[2]["action"] = "case_closed_cash"; rows[2]["detail"] = "settled offline"
    elif k == "delete":
        del rows[3]
    elif k == "insert":
        body = {"i": 99, "ts": datetime.now().isoformat(timespec="seconds"), "case_id": "HS-002",
                "actor": "official", "action": "decision_pass", "detail": "forged",
                "prev_hash": rows[2]["hash"]}
        s = sha("k-ATTACKER" + json.dumps(body, sort_keys=True))[:16]
        rows.insert(3, {**body, "sig": s, "hash": hash_of(body, s)})
    elif k == "swap":
        rows[2], rows[5] = rows[5], rows[2]
    elif k == "rebuild_insider":
        relink_rehash(rows, 2, resign=False)
    elif k == "rebuild_collusion":
        relink_rehash(rows, 2, resign=True)
    elif k == "replace_anchor":
        v = verify(); a = json.load(open(ANCHOR, encoding="utf-8"))
        a["hash"] = rows[a["index"]]["hash"]; a["note"] = "REPLACED BY ATTACKER (all three copies)"
        json.dump(a, open(ANCHOR, "w", encoding="utf-8"))
    elif k == "reset":
        seed(); return verify()
    else:
        return {"error": "unknown attack"}
    if k not in ("replace_anchor",): save_rows(rows)
    return verify()

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>Tamper Challenge</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:20px;}
h1{color:#38bdf8;} h3{color:#94a3b8;margin-top:20px;}
.row{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:8px;margin:6px 0;max-width:980px;}
.row textarea{width:100%;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:6px;font-family:monospace;font-size:11px;}
button{padding:8px 12px;margin:3px;border:none;border-radius:6px;cursor:pointer;font-weight:bold;background:#38bdf8;color:#0f172a;}
button.red{background:#dc2626;color:#fff;} button.green{background:#10b981;color:#04211a;} button.amber{background:#f59e0b;color:#0f172a;}
#verdict{padding:14px;border-radius:10px;margin:12px 0;max-width:980px;font-weight:bold;}
.ok{background:#064e3b;border:2px solid #10b981;color:#a7f3d0;}
.bad{background:#450a0a;border:2px solid #dc2626;color:#fecaca;}
.warn{background:#451a03;border:2px solid #f59e0b;color:#fde68a;}
.poster{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;max-width:980px;font-size:13px;line-height:1.7;}
.esc{color:#f87171;} .caught{color:#10b981;}</style></head><body>
<h1>🧨 HaqSetu TAMPER CHALLENGE</h1>
<p>Edit any past line below (or fire a preset attack), then press VERIFY. The check names the wounded entry. Per-actor keys: facilitator, official, verifier, citizen, system.</p>
<button class='red' onclick="atk('modify')">✏️ Modify entry #2</button>
<button class='red' onclick="atk('delete')">🗑 Delete entry #3</button>
<button class='red' onclick="atk('insert')">➕ Insert forged row</button>
<button class='red' onclick="atk('swap')">🔀 Swap #2 and #5</button>
<button class='amber' onclick="atk('rebuild_insider')">🕵️ Rebuild chain (single insider)</button>
<button class='amber' onclick="atk('rebuild_collusion')">🤝 Rebuild + re-sign (ALL key holders collude)</button>
<button class='amber' onclick="atk('replace_anchor')">📋 Replace all 3 anchor copies</button>
<button class='green' onclick="atk('reset')">♻️ Reset demo chain</button>
<button style='font-size:16px' onclick="check()">🔎 VERIFY CHAIN</button>
<div id='verdict' class='ok'>Chain not checked yet.</div>
<h3>📜 THE LEDGER (judge-editable)</h3><div id='rows'></div>
<h3>📌 POSTER PANEL — per-attack-class results (Sec 2, Sec 3.6)</h3>
<div class='poster'>
<span class='caught'>CAUGHT, entry named:</span> modify past entry (hash+link break) · delete a row (link break at the gap) · insert forged row (signature fails: forger lacks the actor's key) · reorder rows (link break) · rebuild by a single insider (per-actor signatures fail on relinked rows).<br>
<span class='caught'>CAUGHT BY THE WEEKLY ANCHOR:</span> rebuild + re-sign by all key holders — the local chain verifies, but the anchor on the notice board, at the block office and with the independent verifier does not match.<br>
<span class='esc'>ESCAPES (stated honestly):</span> an attacker holding the laptop AND all three anchor copies AND able to reprint every citizen slip; collusion of every key holder together with anchor control; and a complaint that was never logged — that gap is what doorstep outreach and the 10% callback sample exist for. The ledger is detective, not preventive.
</div>
<script>
async function refresh(){const d=await (await fetch('/chain')).json();
 document.getElementById('rows').innerHTML=d.rows.map((r,i)=>
  `<div class='row'>#${r.i} · ${r.actor} · ${r.action}<textarea id='t${i}' rows='2'>${JSON.stringify(r)}</textarea>
   <button onclick="saveRow(${i})">Save edit</button></div>`).join('');}
async function saveRow(i){const rec=JSON.parse(document.getElementById('t'+i).value);
 const v=await (await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:i,record:rec})})).json();
 show(v); refresh();}
async function atk(k){const v=await (await fetch('/attack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:k})})).json();
 show(v); refresh();}
async function check(){show(await (await fetch('/chain')).json().then(d=>d.verify));}
function show(v){const el=document.getElementById('verdict');
 if(v.issues && v.issues.length){el.className='bad';
  el.innerHTML='❌ TAMPER DETECTED at entry #'+v.issues[0][0]+' — class: '+v.issues[0][1]+
   ' (all wounds: '+v.issues.map(x=>'#'+x[0]+' '+x[1]).join(', ')+')';}
 else if(!v.anchor_ok){el.className='warn';
  el.innerHTML='⚠️ LOCAL CHAIN VERIFIES — BUT THE WEEKLY ANCHOR DOES NOT MATCH. Caught by the notice-board / block-office / verifier copies.';}
 else {el.className='ok'; el.innerHTML='✅ CHAIN OK — '+v.n+' entries, anchor matches.';}}
refresh();
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("🧨 Tamper Challenge on http://127.0.0.1:8008")
    uvicorn.run(app, host="127.0.0.1", port=8008)