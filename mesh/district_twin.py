"""
HaqSetu DISTRICT DIGITAL TWIN (Stretch #2, Proposal Sec 3.9 & 7)
Simulates a district of Gram Panchayats; computes per-institution bottleneck
medians from case timestamps using Kaplan-Meier (censoring-aware), applies
small-cell suppression, and renders an institution heat map + survival curves.
Self-contained, offline. Server on port 8003.
"""
import random
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Mean stage duration (days) per institution - the "true" bottleneck profile
INSTITUTIONS = {
    "csc": 2.0,
    "panchayat_secretary": 3.0,
    "bdo": 6.0,
    "revenue_patwari": 9.0,
    "bank_branch": 12.0,
}
COLORS = {"csc": "#10b981", "panchayat_secretary": "#38bdf8", "bdo": "#f59e0b",
          "revenue_patwari": "#f97316", "bank_branch": "#ef4444"}
HORIZON = 60      # simulated days of district history
CENSOR_P = 0.25   # share of cases still open at "today" (censored observations)
MIN_CELL = 5      # small-cell suppression threshold (Sec 3.9)

def simulate_district(seed=7, n_panchayats=12, n_cases=480):
    rng = random.Random(seed)
    cases = []
    for i in range(n_cases):
        gp = f"GP-{rng.randint(1, n_panchayats):02d}"
        path = rng.sample(list(INSTITUTIONS), rng.choice([1, 2, 2, 3]))
        censored = rng.random() < CENSOR_P
        cens_at = rng.randint(1, len(path)) if censored else None
        day, stages = 0.0, []
        for k, inst in enumerate(path, start=1):
            dur = max(0.5, rng.expovariate(1 / INSTITUTIONS[inst]))
            if censored and k == cens_at:
                partial = min(dur, max(0.5, HORIZON - day))
                stages.append({"inst": inst, "dur": round(partial, 1), "done": False})
                day += partial
                break
            stages.append({"inst": inst, "dur": round(dur, 1), "done": True})
            day += dur
        cases.append({"case_id": f"C-{seed}-{i:04d}", "gp": gp,
                      "closed": not censored, "total_days": round(day, 1), "stages": stages})
    return cases

def kaplan_meier(obs):
    """obs = list of (time, event_bool). Returns step curve + median."""
    obs = sorted(obs, key=lambda x: x[0])
    at_risk, S, curve, median, i = len(obs), 1.0, [[0.0, 1.0]], None, 0
    while i < len(obs):
        t, d, c, j = obs[i][0], 0, 0, i
        while j < len(obs) and obs[j][0] == t:
            if obs[j][1]: d += 1
            else: c += 1
            j += 1
        if d and at_risk > 0:
            S *= (1 - d / at_risk)
            curve.append([t, round(S, 4)])
            if median is None and S <= 0.5: median = t
        at_risk -= (d + c)
        i = j
    return curve, median

def institution_stats(cases):
    out = []
    for inst in INSTITUTIONS:
        obs = [(s["dur"], s["done"]) for c in cases for s in c["stages"] if s["inst"] == inst]
        if not obs: continue
        curve, med = kaplan_meier(obs)
        out.append({"inst": inst, "n": len(obs),
                    "censored": sum(1 for _, e in obs if not e),
                    "median_days": med, "km": curve})
    return out

def _row(name, sub, merged):
    closed = sorted(c["total_days"] for c in sub if c["closed"])
    return {"gp": name, "n": len(sub), "merged": merged,
            "median_ttbr": round(closed[len(closed) // 2], 1) if closed else None}

def panchayat_grid(cases):
    gps = sorted({c["gp"] for c in cases})
    rows, small = [], []
    for gp in gps:
        sub = [c for c in cases if c["gp"] == gp]
        if len(sub) < MIN_CELL: small.append(gp); continue
        rows.append(_row(gp, sub, False))
    if small:  # merge upward so tiny groups can never be identified
        rows.append(_row(f"MERGED small cells ({len(small)} GPs)",
                         [c for c in cases if c["gp"] in small], True))
    return rows

app = FastAPI(title="HaqSetu District Digital Twin")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/twin")
def twin(seed: int = 7):
    cases = simulate_district(seed=seed)
    obs_all = ([(c["total_days"], True) for c in cases if c["closed"]] +
               [(sum(s["dur"] for s in c["stages"]), False) for c in cases if not c["closed"]])
    km_all, med_all = kaplan_meier(obs_all)
    return {"seed": seed, "horizon_days": HORIZON, "n_cases": len(cases),
            "n_closed": sum(1 for c in cases if c["closed"]),
            "n_censored": sum(1 for c in cases if not c["closed"]),
            "median_ttbr_km": med_all, "km_overall": km_all,
            "institutions": institution_stats(cases), "panchayats": panchayat_grid(cases)}

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>District Digital Twin</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:24px;}
h1{color:#38bdf8;} h3{color:#94a3b8;margin-top:26px;}
.kpis{display:flex;gap:14px;flex-wrap:wrap;} .kpi{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 18px;}
.kpi b{font-size:26px;display:block;} .kpi span{font-size:11px;color:#94a3b8;text-transform:uppercase;}
table{border-collapse:collapse;margin-top:8px;} td,th{border:1px solid #334155;padding:7px 12px;font-size:13px;text-align:left;}
.merged{background:#3b2f14;color:#fbbf24;font-weight:bold;}
button{padding:10px 16px;border:none;border-radius:8px;background:#38bdf8;color:#0f172a;font-weight:bold;cursor:pointer;margin:8px 8px 0 0;}
canvas{background:#1e293b;border:1px solid #334155;border-radius:10px;margin-top:10px;}
.note{font-size:12px;color:#94a3b8;max-width:900px;line-height:1.5;}</style></head>
<body><h1>📈 HaqSetu DISTRICT DIGITAL TWIN</h1>
<p class='note'>Institution heat map + Kaplan-Meier time-to-closure, computed from ledger timestamps.
Open cases are <b>censored</b>, not ignored. Public cells with &lt;5 cases are merged upward (Sec 3.9).</p>
<button onclick='load(seed+1)'>🎲 Re-simulate district (new seed)</button>
<button onclick='load(7)'>Reset</button>
<div class='kpis' id='kpis'></div>
<h3>🔥 INSTITUTION BOTTLENECK HEAT MAP (median days per stage, KM)</h3>
<table id='heat'></table>
<h3>📉 KAPLAN-MEIER SURVIVAL: P(stage still pending after t days)</h3>
<canvas id='km' width='860' height='360'></canvas>
<h3>🏘️ PANCHAYAT GRID (median days to benefit-ready)</h3>
<table id='grid'></table>
<script>
let seed=7; const COLS={"csc":"#10b981","panchayat_secretary":"#38bdf8","bdo":"#f59e0b","revenue_patwari":"#f97316","bank_branch":"#ef4444"};
async function load(s){seed=s;const r=await fetch('/twin?seed='+s);const d=await r.json();
 document.getElementById('kpis').innerHTML=
  `<div class='kpi'><b>${d.n_cases}</b><span>cases / ${d.horizon_days}d</span></div>`+
  `<div class='kpi'><b>${d.n_closed}</b><span>closed</span></div>`+
  `<div class='kpi'><b>${d.n_censored}</b><span>censored (still open)</span></div>`+
  `<div class='kpi'><b>${d.median_ttbr_km}d</b><span>median TTBR (KM)</span></div>`;
 let h='<tr><th>Institution</th><th>stages n</th><th>censored</th><th>median days</th><th>heat</th></tr>';
 d.institutions.forEach(i=>{const m=i.median_days||0;const col=m>7?'#ef4444':m>3?'#f59e0b':'#10b981';
  h+=`<tr><td>${i.inst}</td><td>${i.n}</td><td>${i.censored}</td><td><b style='color:${col}'>${m}d</b></td><td style='background:${col};width:120px'></td></tr>`;});
 document.getElementById('heat').innerHTML=h;
 let g='<tr><th>Panchayat</th><th>n</th><th>median TTBR</th></tr>';
 d.panchayats.forEach(p=>{g+=`<tr class='${p.merged?'merged':''}'><td>${p.gp}</td><td>${p.n}</td><td>${p.median_ttbr?p.median_ttbr+'d':'-'}</td></tr>`;});
 document.getElementById('grid').innerHTML=g;
 drawKM(d);}
function drawKM(d){const cv=document.getElementById('km'),x=cv.getContext('2d');
 x.clearRect(0,0,cv.width,cv.height);x.strokeStyle='#334155';x.lineWidth=1;
 const maxT=d.horizon;const X=t=>40+t/maxT*(cv.width-60),Y=s=>20+(1-s)*(cv.height-50);
 x.beginPath();x.moveTo(40,20);x.lineTo(40,cv.height-30);x.lineTo(cv.width-20,cv.height-30);x.stroke();
 x.fillStyle='#94a3b8';x.font='11px monospace';x.fillText('S(t)=1',8,26);x.fillText('0',20,cv.height-30);x.fillText('days →',cv.width-70,cv.height-12);
 d.institutions.forEach(i=>{x.strokeStyle=COLS[i.inst];x.lineWidth=2;x.beginPath();
  i.km.forEach((p,k)=>{const px=X(p[0]),py=Y(p[1]);k?x.lineTo(px,py):x.moveTo(px,py);
   if(k>0){x.lineTo(px,Y(i.km[k-1][1]));x.lineTo(px,py);}});
  x.stroke();x.fillStyle=COLS[i.inst];x.fillText(i.inst,X(maxT*0.62),Y(0.95)+d.institutions.indexOf(i)*14);});}
load(7);
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("📈 District Digital Twin on http://127.0.0.1:8003")
    uvicorn.run(app, host="127.0.0.1", port=8003)