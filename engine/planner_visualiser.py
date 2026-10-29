"""
HaqSetu PLANNER VISUALISER (Core #4, Proposal Sec 3.5 & 7)
Toggle schemes -> compute minimum visits (grouped by desk) -> show critical
path lower bound -> separate long-pole external waits. Pure Python constraint
logic (no heavy C-extensions needed). Port 8007.
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from typing import List

# The Dependency Graph (What does each scheme need?)
SCHEMES = {
    "pm_kisan": {
        "name": "PM-KISAN (Farmer)",
        "steps": [
            {"desk": "csc", "action": "e-KYC & Form", "days": 1},
            {"desk": "patwari", "action": "Land Record Verify", "days": 3},
            {"desk": "bank", "action": "Aadhaar Seeding", "days": 15, "long_pole": True}
        ]
    },
    "pension": {
        "name": "Old Age Pension",
        "steps": [
            {"desk": "panchayat", "action": "Age & Residence Cert", "days": 2},
            {"desk": "bank", "action": "Account Opening/Verify", "days": 5}
        ]
    },
    "ayushman": {
        "name": "Ayushman Bharat (Health)",
        "steps": [
            {"desk": "csc", "action": "SECC Verification & Card Print", "days": 1}
        ]
    },
    "awas": {
        "name": "PM Awas Yojana (Housing)",
        "steps": [
            {"desk": "panchayat", "action": "BPL & Land Check", "days": 3},
            {"desk": "bdo", "action": "Block Approval", "days": 10, "long_pole": True}
        ]
    }
}

def compute_plan(selected_schemes: List[str]):
    if not selected_schemes:
        return {"naive_visits": 0, "planned_visits": 0, "desks": [], "long_poles": [], "critical_path_days": 0}

    # 1. Naive approach (1 visit per scheme requirement)
    naive_visits = sum(len(SCHEMES[s]["steps"]) for s in selected_schemes if s in SCHEMES)

    # 2. HaqSetu Planner: Group by Desk to minimize physical visits
    desk_map = {}
    long_poles = []
    all_paths = []

    for s in selected_schemes:
        if s not in SCHEMES: continue
        for step in SCHEMES[s]["steps"]:
            desk = step["desk"]
            if desk not in desk_map:
                desk_map[desk] = {"desk": desk, "actions": [], "total_days": 0}
            
            if step["action"] not in desk_map[desk]["actions"]:
                desk_map[desk]["actions"].append(step["action"])
                desk_map[desk]["total_days"] += step["days"]
            
            if step.get("long_pole"):
                long_poles.append({"scheme": SCHEMES[s]["name"], "action": step["action"], "days": step["days"]})
            
            all_paths.append(step["days"])

    # The planned visits is simply the number of unique desks we must visit
    planned_visits = len(desk_map)
    
    # Critical Path (The longest sequential dependency)
    # In reality, some things happen in parallel, but the longest chain is the lower bound
    critical_path_days = max(all_paths) if all_paths else 0

    return {
        "naive_visits": naive_visits,
        "planned_visits": planned_visits,
        "visits_saved": naive_visits - planned_visits,
        "desks": list(desk_map.values()),
        "long_poles": long_poles,
        "critical_path_days": critical_path_days
    }

class PlanReq(BaseModel):
    schemes: List[str]

app = FastAPI(title="HaqSetu Planner Visualiser")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/plan")
def plan(req: PlanReq):
    return compute_plan(req.schemes)

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>One-Visit Planner</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:24px;}
h1{color:#38bdf8;} .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0;}
.scheme{background:#1e293b;border:2px solid #334155;border-radius:10px;padding:16px;cursor:pointer;text-align:center;transition:all 0.2s;}
.scheme.active{border-color:#10b981;background:#064e3b;}
.scheme h3{margin:0 0 8px;color:#f8fafc;} .scheme p{margin:0;font-size:12px;color:#94a3b8;}
.kpis{display:flex;gap:20px;margin:20px 0;} .kpi{background:#1e293b;padding:20px;border-radius:10px;text-align:center;flex:1;}
.kpi b{font-size:36px;display:block;} .kpi span{font-size:12px;color:#94a3b8;text-transform:uppercase;}
.naive{color:#ef4444;} .planned{color:#10b981;} .saved{color:#f59e0b;}
.desks{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0;}
.desk{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:14px;flex:1;min-width:200px;}
.desk h4{margin:0 0 10px;color:#38bdf8;} .desk ul{margin:0;padding-left:20px;font-size:13px;color:#cbd5e1;}
.long-pole{background:#451a03;border:1px solid #b45309;border-radius:8px;padding:14px;margin-top:20px;}
.long-pole h4{margin:0 0 10px;color:#f59e0b;} .long-pole p{margin:4px 0;font-size:13px;}
</style></head><body>
<h1>🗺️ HaqSetu ONE-VISIT PLANNER</h1>
<p>Select the schemes a household needs. Watch the planner collapse multiple trips into a single optimized route.</p>

<div class="grid" id="schemes"></div>

<div class="kpis">
    <div class="kpi"><b class="naive" id="naive">0</b><span>Naive Visits (Govt Way)</span></div>
    <div class="kpi"><b class="planned" id="planned">0</b><span>HaqSetu Planned Visits</span></div>
    <div class="kpi"><b class="saved" id="saved">0</b><span>Trips Saved</span></div>
    <div class="kpi"><b style="color:#38bdf8" id="cp">0d</b><span>Critical Path (Lower Bound)</span></div>
</div>

<h3>🏢 The Optimized Route (Grouped by Desk)</h3>
<div class="desks" id="desks"></div>

<div class="long-pole" id="longpole" style="display:none;">
    <h4>⏳ LONG-POLE ITEMS (External Waits)</h4>
    <p style="font-size:12px;color:#fbbf24;margin-bottom:10px;">These steps are tracked, not promised. The Panchayat cannot speed them up, but the clock is public.</p>
    <div id="lp-list"></div>
</div>

<script>
const SCHEMES = {
    "pm_kisan": {name: "PM-KISAN", desc: "Farmer Income Support"},
    "pension": {name: "Old Age Pension", desc: "Social Security"},
    "ayushman": {name: "Ayushman Bharat", desc: "Health Insurance"},
    "awas": {name: "PM Awas Yojana", desc: "Housing Assistance"}
};
let selected = new Set();

function renderSchemes() {
    const grid = document.getElementById('schemes');
    grid.innerHTML = '';
    for (const [id, s] of Object.entries(SCHEMES)) {
        const active = selected.has(id) ? 'active' : '';
        grid.innerHTML += `<div class="scheme ${active}" onclick="toggle('${id}')"><h3>${s.name}</h3><p>${s.desc}</p></div>`;
    }
}

async function toggle(id) {
    if (selected.has(id)) selected.delete(id); else selected.add(id);
    renderSchemes();
    await compute();
}

async function compute() {
    const r = await fetch('/plan', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({schemes: Array.from(selected)})});
    const d = await r.json();
    
    document.getElementById('naive').textContent = d.naive_visits;
    document.getElementById('planned').textContent = d.planned_visits;
    document.getElementById('saved').textContent = d.visits_saved;
    document.getElementById('cp').textContent = d.critical_path_days + 'd';
    
    const desks = document.getElementById('desks');
    desks.innerHTML = d.desks.map(d => `
        <div class="desk">
            <h4>🏢 ${d.desk.toUpperCase().replace('_', ' ')}</h4>
            <ul>${d.actions.map(a => `<li>${a}</li>`).join('')}</ul>
            <div style="margin-top:10px;font-size:11px;color:#94a3b8;">Est: ${d.total_days} days at desk</div>
        </div>
    `).join('') || '<i style="color:#94a3b8">Select schemes to see the route.</i>';
    
    const lp = document.getElementById('longpole');
    if (d.long_poles.length > 0) {
        lp.style.display = 'block';
        document.getElementById('lp-list').innerHTML = d.long_poles.map(p => 
            `<p>⚠️ <b>${p.scheme}</b>: ${p.action} takes <b>${p.days} days</b> (Bank/Block processing time).</p>`
        ).join('');
    } else {
        lp.style.display = 'none';
    }
}

renderSchemes();
compute();
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("🗺️ Planner Visualiser on http://127.0.0.1:8007")
    uvicorn.run(app, host="127.0.0.1", port=8007)