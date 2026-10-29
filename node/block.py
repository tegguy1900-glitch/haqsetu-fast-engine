"""BLOCK / SDM SERVICE - a separate place. Pulls signed ledger rows from village
nodes, verifies the hash chain itself, stores its OWN copy, escalates breaches.
Case-level data stops here: upward we send counts only (Sec 3.9)."""
import hashlib, json, os, sqlite3, urllib.request
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "ledger", "block.db")
VILLAGES = [{"id": "V1", "url": "http://127.0.0.1:8000"}]
app = FastAPI(title="Block / SDM Service")

def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    con.executescript("""CREATE TABLE IF NOT EXISTS rows(hash TEXT PRIMARY KEY, village TEXT, gp TEXT, event TEXT, ts TEXT, payload TEXT);
                         CREATE TABLE IF NOT EXISTS syncs(village TEXT, ts TEXT, ok INTEGER, n INTEGER);""")
    con.commit(); return con
_db().close()

def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def fetch(url):
    with urllib.request.urlopen(url, timeout=6) as r: return json.loads(r.read().decode())

def verify_rows(rows):
    prev = sha("genesis")[:16]
    for r in rows:
        if r.get("prev") != prev: return False
        if r.get("hash") != sha(json.dumps({k: v for k, v in r.items() if k != "hash"}, sort_keys=True))[:16]: return False
        prev = r["hash"]
    return True

@app.post("/sync/pull")
@app.get("/sync/pull")
def pull():
    out = []
    for v in VILLAGES:
        ok, n = False, 0
        try:
            rows = fetch(v["url"] + "/api/ledger")["rows"]
            ok = verify_rows(rows); con = _db()
            if ok:
                for r in rows:
                    con.execute("INSERT OR IGNORE INTO rows VALUES(?,?,?,?,?,?)",
                                (r["hash"], v["id"], r.get("gp","GP-01"), r.get("event",""), r.get("ts",""), json.dumps(r)))
                n = len(rows)
            con.execute("INSERT INTO syncs VALUES(?,?,?,?)", (v["id"], datetime.now().isoformat(timespec="seconds"), 1 if ok else 0, n))
            con.commit(); con.close()
        except Exception as e:
            con = _db(); con.execute("INSERT INTO syncs VALUES(?,?,?,?)", (v["id"], datetime.now().isoformat(timespec="seconds"), 0, 0)); con.commit(); con.close()
            out.append({"village": v["id"], "ok": False, "error": str(e)}); continue
        out.append({"village": v["id"], "ok": ok, "rows": n})
    return out

def aggregates():
    con = _db(); rows = con.execute("SELECT * FROM rows").fetchall()
    syncs = con.execute("SELECT * FROM syncs ORDER BY ts DESC LIMIT 8").fetchall(); con.close()
    cases, gps, esc, counts = {}, {}, [], {}
    n_in = n_ab = 0; now = datetime.now()
    for r in rows:
        p = json.loads(r["payload"]); ev = p.get("event"); gp = p.get("gp", r["gp"])
        g = gps.setdefault(gp, {"gp": gp, "open": 0, "progress": 0, "closed": 0, "breached": 0})
        cid = r["hash"][:8] if ev == "intake" else (p.get("case") or "")[:8]
        if ev == "intake":
            n_in += 1; cases[cid] = {"gp": gp, "state": "open"}
            for s in p.get("can", []): counts[s] = counts.get(s, 0) + 1
            for c in p.get("civic", []): counts[c] = counts.get(c, 0) + 1
        elif ev == "intake_abstain": n_ab += 1
        elif cid in cases:
            if ev == "petition_filed":
                cases[cid]["state"] = "progress"
                dl = datetime.fromisoformat(p["ts"]) + timedelta(days=p.get("sla_days", 30))
                if now > dl:
                    cases[cid]["state"] = "breached"; g["breached"] += 1
                    esc.append({"case": cid, "gp": gp, "subject": p.get("subject",""), "breached": dl.date().isoformat()})
            if ev == "ticket_closed": cases[cid]["state"] = "closed"
    for c in cases.values(): gps[c["gp"]][c["state"] if c["state"] in ("open","progress","closed") else "breached"] += 1
    return {"gps": list(gps.values()), "escalations": esc, "counts": counts,
            "abstain": {"intakes": n_in, "abstains": n_ab},
            "syncs": [dict(s) for s in syncs]}

@app.get("/api/sdm")
def sdm(): return aggregates()

@app.get("/api/block_digest")
def block_digest():
    a = aggregates()
    return {"week": datetime.now().isocalendar()[1], "counts": a["counts"], "abstain": a["abstain"],
            "escalations_count": len(a["escalations"]), "gps_count": len(a["gps"])}

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>Block / SDM Office</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}
h1{color:#38bdf8} .card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;margin:10px 0}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #334155;padding:8px;font-size:13px;text-align:left}
button{background:#38bdf8;color:#0f172a;border:none;padding:10px 16px;border-radius:6px;font-weight:bold;cursor:pointer}
.esc{border-left:6px solid #dc2626;background:#450a0a;padding:10px;border-radius:8px;margin:6px 0}
.small{font-size:12px;color:#94a3b8}</style></head><body>
<h1>🧑 BLOCK / SDM OFFICE — separate service, separate store (port 8100)</h1>
<p class='small'>Data arrives only as signed ledger rows from village nodes; the chain is re-verified here. Case-level data stops at this office: upward we send counts only.</p>
<button onclick="sync()">🔄 Pull from village nodes now</button><span id='syncres' class='small'></span>
<div class='card'><h3>Per-Gram-Panchayat position</h3><table id='gps'></table></div>
<div class='card'><h3>Auto-escalations (SLA breached, evidence attached)</h3><div id='esc'></div></div>
<div class='card'><h3>Sync log</h3><table id='syncs'></table></div>
<script>
async function sync(){const d=await(await fetch('/sync/pull',{method:'POST'})).json();
 document.getElementById('syncres').textContent=JSON.stringify(d);}
async function load(){const d=await(await fetch('/api/sdm')).json();
 document.getElementById('gps').innerHTML='<tr><th>GP</th><th>open</th><th>progress</th><th>closed</th><th>breached</th></tr>'+
  d.gps.map(g=>`<tr><td>${g.gp}</td><td>${g.open}</td><td>${g.progress}</td><td>${g.closed}</td><td>${g.breached}</td></tr>`).join('')||'<tr><td colspan=5>No data pulled yet.</td></tr>';
 document.getElementById('esc').innerHTML=d.escalations.map(e=>`<div class='esc'>⬆️ ${e.case} (${e.gp}) — ${e.subject} — breached ${e.breached}</div>`).join('')||'<p>None. Zero silent drops by design.</p>';
 document.getElementById('syncs').innerHTML='<tr><th>village</th><th>time</th><th>chain OK</th><th>rows</th></tr>'+
  d.syncs.map(s=>`<tr><td>${s.village}</td><td>${s.ts}</td><td>${s.ok?'✅':'❌'}</td><td>${s.n}</td></tr>`).join('');}
load(); setInterval(load,30000);
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("🧑‍ Block/SDM service: http://127.0.0.1:8100")
    uvicorn.run(app, host="127.0.0.1", port=8100)
