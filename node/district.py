"""DISTRICT / DM SERVICE - a separate place. Receives COUNTS ONLY from block
services (Sec 3.9). It has no case rows, no names, no audio - by construction,
not by policy. Applies small-cell suppression before anything is displayed."""
import json, os, sqlite3, urllib.request
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "ledger", "district.db")
BLOCKS = [{"id": "B1", "url": "http://127.0.0.1:8100"}]
app = FastAPI(title="District / DM Service")

def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, block TEXT, payload TEXT)")
    con.commit(); return con
_db().close()

def fetch(url):
    with urllib.request.urlopen(url, timeout=6) as r: return json.loads(r.read().decode())

@app.post("/sync/pull")
@app.get("/sync/pull")
def pull():
    out = []
    for b in BLOCKS:
        try:
            d = fetch(b["url"] + "/api/block_digest")
            con = _db(); con.execute("INSERT INTO history(ts,block,payload) VALUES(?,?,?)",
                                     (datetime.now().isoformat(timespec="seconds"), b["id"], json.dumps(d)))
            con.commit(); con.close(); out.append({"block": b["id"], "ok": True})
        except Exception as e:
            out.append({"block": b["id"], "ok": False, "error": str(e)})
    return out

@app.get("/api/dm")
def dm():
    con = _db(); rows = con.execute("SELECT * FROM history ORDER BY id DESC").fetchall(); con.close()
    if not rows: return {"counts": {}, "merged": 0, "abstain": {"intakes": 0, "abstains": 0}, "escalations_count": 0, "history": []}
    latest = json.loads(rows[0]["payload"])
    counts = latest.get("counts", {})
    kept = {k: v for k, v in counts.items() if v >= 5}
    merged = sum(v for v in counts.values() if v < 5)
    return {"counts": kept, "merged": merged, "abstain": latest.get("abstain", {}),
            "escalations_count": latest.get("escalations_count", 0),
            "history": [{"ts": r["ts"], "intakes": json.loads(r["payload"]).get("abstain", {}).get("intakes", 0)} for r in rows[:12]]}

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>District / DM Control Room</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#0b1020;color:#e2e8f0;margin:0;padding:24px}
h1{color:#f59e0b} .card{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:16px;margin:10px 0}
.big{font-size:30px;font-weight:bold} table{border-collapse:collapse;width:100%}
td,th{border:1px solid #1f2937;padding:8px;font-size:13px;text-align:left}
button{background:#f59e0b;color:#0b1020;border:none;padding:10px 16px;border-radius:6px;font-weight:bold;cursor:pointer}
.small{font-size:12px;color:#94a3b8} .priv{background:#064e3b;border:1px solid #10b981;padding:10px;border-radius:8px;font-size:13px}</style></head><body>
<h1>🗺️ DISTRICT / DM CONTROL ROOM — separate service, separate store (port 8101)</h1>
<p class='priv'>🔒 This service receives COUNTS ONLY from block offices. Case rows, names and audio never reach the district - by construction, not by policy (Sec 3.9). Cells under 5 are merged before display.</p>
<button onclick="sync()">🔄 Pull block digests now</button><span id='r' class='small'></span>
<div class='card'>Intakes <span class='big' id='ni'>0</span> · Abstains <span class='big' id='na'>0</span> ·
 Abstention rate <span class='big' id='ar'>0%</span> · Escalations received <span class='big' id='es'>0</span></div>
<div class='card'><h3>Category counts (suppressed)</h3><table id='ct'></table></div>
<div class='card'><h3>Intake trend across syncs</h3><table id='hs'></table></div>
<script>
async function sync(){const d=await(await fetch('/sync/pull',{method:'POST'})).json();document.getElementById('r').textContent=JSON.stringify(d);load();}
async function load(){const d=await(await fetch('/api/dm')).json();
 document.getElementById('ni').textContent=d.abstain.intakes||0;
 document.getElementById('na').textContent=d.abstain.abstains||0;
 const t=(d.abstain.intakes||0); document.getElementById('ar').textContent=(t?((d.abstain.abstains||0)/t*100).toFixed(1):'0')+'%';
 document.getElementById('es').textContent=d.escalations_count||0;
 document.getElementById('ct').innerHTML='<tr><th>category</th><th>count</th></tr>'+Object.entries(d.counts).map(([k,v])=>`<tr><td>${k.replace(/_/g,' ')}</td><td>${v}</td></tr>`).join('')+
  (d.merged?`<tr><td><i>merged small cells (&lt;5)</i></td><td>${d.merged}</td></tr>`:'')||'<tr><td colspan=2>No digests yet.</td></tr>';
 document.getElementById('hs').innerHTML='<tr><th>sync time</th><th>intakes</th></tr>'+d.history.map(h=>`<tr><td>${h.ts}</td><td>${h.intakes}</td></tr>`).join('');}
load(); setInterval(load,30000);
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("🗺️ District/DM service: http://127.0.0.1:8101")
    uvicorn.run(app, host="127.0.0.1", port=8101)
