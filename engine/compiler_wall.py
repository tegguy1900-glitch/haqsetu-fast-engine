"""
HaqSetu RULE COMPILER WALL (Exhibit Core #3, Proposal Sec 7)
Guideline text -> drafted typed rule -> Z3 internal-consistency verdict -> test-vector check.
Proves: (a) a planted contradiction is caught live by Z3;
        (b) a planted CONSISTENT-but-WRONG rule is caught ONLY by test vectors.
Self-contained server on port 8002.
"""
import re, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

try:
    from z3 import Int, Bool, Solver, sat, And, Not
    Z3_OK = True
except Exception:
    Z3_OK = False

# ---------- 1. THE DRAFTER (LLM-assisted drafting, simulated offline) ----------
def draft_rule(text, scheme="draft_scheme"):
    conds, notes = [], []
    t = text.lower()
    m = re.search(r"age[d]?\s+(?:of\s+)?(\d+)\s*(?:years)?\s*(?:or\s+above|and\s+above|or\s+older)", t)
    if m: conds.append({"field": "age", "op": "gte", "value": int(m.group(1))})
    m = re.search(r"below\s+(?:age\s+)?(\d+)", t)
    if m: conds.append({"field": "age", "op": "lt", "value": int(m.group(1))})
    m = re.search(r"(?:annual\s+)?income\s+(?:below|under|at\s+most|not\s+exceeding|up\s+to)\s*(?:rs\.?|inr|₹)?\s*([\d,]+)", t)
    if m: conds.append({"field": "annual_income_inr", "op": "lte", "value": int(m.group(1).replace(",", ""))})
    if re.search(r"\b(widow|widowed)\b", t): conds.append({"field": "is_widow", "op": "eq", "value": True})
    if re.search(r"\b(woman|women|female)\b", t): conds.append({"field": "applicant_gender", "op": "eq", "value": "female"})
    m = re.search(r"disab\w+\s*(?:of\s+)?(\d+)\s*(?:%|percent)", t)
    if m: conds.append({"field": "disability_percentage", "op": "gte", "value": int(m.group(1))})
    if re.search(r"\b(bpl|below\s+poverty\s+line)\b", t): conds.append({"field": "is_bpl", "op": "eq", "value": True})
    if not conds: notes.append("No typed condition extracted. Human drafting required.")
    notes.append("DRAFT ONLY: two human reviewers must check every row against its source (Sec 3.3).")
    y = [f"scheme: {scheme}", "state: haryana", "rules:", f"  - id: {scheme}_draft",
         f'    description: "{text.strip()[:80]}"', "    when:"]
    for c in conds:
        v = "true" if c["value"] is True else c["value"]
        y += [f"      - field: {c['field']}", f"        op: {c['op']}", f"        value: {v}"]
    y += ["    outcome: include", "    documents: [aadhaar]", "    desk: csc",
          "    source: {doc: PASTED_GUIDELINE, clause: unverified, url: none}",
          "    verified_by: [DRAFT, NEEDS_TWO_HUMAN_REVIEWERS]",
          "    test_vectors: []   # MUST be filled from guideline worked examples"]
    return {"conditions": conds, "yaml": "\n".join(y), "notes": notes}

# ---------- 2. THE Z3 VERDICT (internal consistency ONLY) ----------
def z3_verdict(conds):
    if not Z3_OK: return {"verdict": "Z3 UNAVAILABLE", "explanation": "pip install z3-solver"}
    if not conds: return {"verdict": "NO CONDITIONS", "explanation": "Nothing to check."}
    s, vars = Solver(), {}
    def gv(f, kind):
        if (f, kind) not in vars: vars[(f, kind)] = Int(f) if kind == "int" else Bool(f)
        return vars[(f, kind)]
    cs = []
    for c in conds:
        f, op, v = c["field"], c["op"], c["value"]
        if isinstance(v, bool):
            cs.append(gv(f, "bool") if v else Not(gv(f, "bool")))
        elif isinstance(v, (int, float)):
            x = gv(f, "int")
            cs.append({"gte": x >= v, "lte": x <= v, "gt": x > v, "lt": x < v, "eq": x == v}[op])
        else:
            cs.append(gv(f + "_s", "int") == (sum(ord(ch) for ch in str(v)) % 997))
    s.add(And(*cs))
    if s.check() == sat:
        return {"verdict": "CONSISTENT", "explanation": "Z3 found a satisfying assignment. Internal consistency holds. Correctness still needs source review + test vectors."}
    return {"verdict": "CONTRADICTION", "explanation": "Z3 proved the conditions UNSATISFIABLE: no citizen can EVER satisfy this rule. Draft rejected."}

# ---------- 3. THE TEST-VECTOR CATCHER (correctness, not consistency) ----------
def eval_rule(conds, facts):
    for c in conds:
        a = facts.get(c["field"])
        if a is None: return False
        v, op = c["value"], c["op"]
        if op == "eq" and not a == v: return False
        if op == "gte" and not a >= v: return False
        if op == "lte" and not a <= v: return False
        if op == "lt" and not a < v: return False
        if op == "gt" and not a > v: return False
    return True

def run_vectors(conds, vectors):
    out = []
    for vec in vectors:
        got = "include" if eval_rule(conds, vec["input"]) else "needs_official_decision"
        out.append({"input": vec["input"], "expect": vec["expect"], "got": got, "pass": got == vec["expect"]})
    return out

# ---------- 4. THE PLANTED DEMOS (Proposal Sec 7, Core #3) ----------
PLANTS = {
    "contradiction": {"text": "Applicant must be aged 60 or above and below age 18 to qualify.", "vectors": []},
    "wrong": {"text": "Widow applicant with annual income at most 10000 is included.",
              "vectors": [{"input": {"is_widow": True, "annual_income_inr": 15000}, "expect": "include"},
                          {"input": {"is_widow": True, "annual_income_inr": 8000}, "expect": "include"}]}
}

# ---------- 5. THE SERVER + EXHIBIT UI ----------
app = FastAPI(title="HaqSetu Rule Compiler Wall")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class CompileReq(BaseModel):
    text: str = ""
    plant: str = "none"

@app.post("/compile")
def compile_wall(req: CompileReq):
    text, vectors = req.text, []
    if req.plant in PLANTS:
        text, vectors = PLANTS[req.plant]["text"], PLANTS[req.plant]["vectors"]
    draft = draft_rule(text)
    verdict = z3_verdict(draft["conditions"])
    vres = run_vectors(draft["conditions"], vectors) if vectors else []
    vver = None if not vres else ("PASS" if all(r["pass"] for r in vres) else "FAIL: caught by TEST VECTORS, not by Z3")
    return {"text": text, "draft": draft, "z3": verdict, "vectors": vres, "vectors_verdict": vver}

PAGE = """<!DOCTYPE html><html><head><meta charset='utf-8'><title>Rule Compiler Wall</title>
<style>body{font-family:monospace;background:#0f172a;color:#f8fafc;padding:24px;}
h1{color:#38bdf8;} textarea{width:100%;height:90px;background:#1e293b;color:#f8fafc;border:1px solid #334155;border-radius:8px;padding:10px;font-size:14px;}
button{padding:12px 18px;margin:6px 6px 6px 0;border:none;border-radius:8px;cursor:pointer;font-weight:bold;}
.b1{background:#38bdf8;color:#0f172a;} .b2{background:#dc2626;color:#fff;} .b3{background:#f59e0b;color:#0f172a;}
pre{background:#1e293b;padding:14px;border-radius:8px;border:1px solid #334155;white-space:pre-wrap;}
.badge{display:inline-block;padding:6px 14px;border-radius:6px;font-weight:bold;margin:6px 0;}
.ok{background:#10b981;color:#04211a;} .bad{background:#dc2626;color:#fff;} .warn{background:#f59e0b;color:#0f172a;}
table{border-collapse:collapse;margin-top:8px;} td,th{border:1px solid #334155;padding:6px 10px;font-size:13px;}</style></head>
<body><h1>🧱 HaqSetu RULE COMPILER WALL</h1>
<p>Guideline text → drafted rule → Z3 verdict → test-vector check. (Proposal Sec 3.3 & 7)</p>
<textarea id='g'>Applicant must be aged 60 or above with annual income below 30000.</textarea><br>
<button class='b1' onclick='go("none")'>1️⃣ Draft & Compile</button>
<button class='b2' onclick='go("contradiction")'>🧨 Plant CONTRADICTION (Z3 must catch)</button>
<button class='b3' onclick='go("wrong")'>🐛 Plant CONSISTENT-BUT-WRONG (only vectors catch)</button>
<div id='out'></div>
<script>
async function go(plant){
  const text=document.getElementById('g').value;
  const r=await fetch('/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,plant})});
  const d=await r.json(); const o=document.getElementById('out');
  let h='<h3>📄 Drafted Rule (YAML)</h3><pre>'+d.draft.yaml+'</pre>';
  h+='<h3>🔎 Z3 Internal-Consistency Verdict</h3><div class="badge '+(d.z3.verdict=='CONSISTENT'?'ok':'bad')+'">'+d.z3.verdict+'</div><p>'+d.z3.explanation+'</p>';
  if(d.vectors.length){ h+='<h3>🧪 Test-Vector Check (correctness)</h3><table><tr><th>Input</th><th>Expect</th><th>Got</th><th>Result</th></tr>';
    d.vectors.forEach(v=>{h+='<tr><td>'+JSON.stringify(v.input)+'</td><td>'+v.expect+'</td><td>'+v.got+'</td><td class="'+(v.pass?'ok':'bad')+'">'+(v.pass?'PASS':'FAIL')+'</td></tr>';});
    h+='</table><div class="badge '+(d.vectors_verdict=='PASS'?'ok':'warn')+'">'+d.vectors_verdict+'</div>'; }
  h+='<h3>⚠️ Reviewer Notes</h3><ul>'+d.draft.notes.map(n=>'<li>'+n+'</li>').join('')+'</ul>';
  o.innerHTML=h;
}
</script></body></html>"""

@app.get("/")
def home(): return HTMLResponse(PAGE)

if __name__ == "__main__":
    print("🧱 Rule Compiler Wall on http://127.0.0.1:8002")
    uvicorn.run(app, host="127.0.0.1", port=8002)