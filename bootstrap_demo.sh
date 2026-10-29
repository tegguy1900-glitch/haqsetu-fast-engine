#!/usr/bin/env bash
# Haq Setu 30-min demo: a video-style voice page served BY the audited village node.
# Writes web_demo/index.html, adds a static "/" route to village/server.py (NOT protected),
# then LIVE-smokes the whole flow against the real rulepack + append-only ledger in a sandbox.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true
mkdir -p web_demo

cat > web_demo/index.html <<'HTMLEOF'
<!-- HAQSETU_DEMO_PAGE -->
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HaqSetu | हकसेतु — demo</title><style>
:root{--saf:#FF9933;--grn:#138808;--nav:#000080;--bg:#f4f6f9}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:#0f172a}
.ribbon{background:#dc2626;color:#fff;font-size:12px;font-weight:700;text-align:center;padding:6px 10px;line-height:1.3}
.tricolor{display:flex;height:5px}.tricolor div{flex:1}.tricolor div:nth-child(1){background:var(--saf)}.tricolor div:nth-child(2){background:#fff}.tricolor div:nth-child(3){background:var(--grn)}
header{background:var(--nav);color:#fff;padding:14px 18px}header h1{margin:0;font-size:20px}header p{margin:4px 0 0;font-size:12px;opacity:.85}
.wrap{max-width:880px;margin:18px auto;padding:0 14px}
.card{background:#fff;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,.06);padding:18px;margin-bottom:16px}
.mic{background:#dc2626;color:#fff;border:none;border-radius:50%;width:84px;height:84px;font-size:30px;cursor:pointer;display:block;margin:6px auto;box-shadow:0 4px 14px rgba(220,38,38,.4)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}
input[type=text]{flex:1;min-width:200px;padding:10px;border:1px solid #cbd5e1;border-radius:8px}
button.b{padding:10px 14px;border:none;border-radius:8px;background:var(--nav);color:#fff;cursor:pointer;font-weight:600}
button.g{background:var(--grn)}button.o{background:#f59e0b;color:#111}
#status{font-weight:700;color:#b45309;min-height:20px;margin:8px 0}
.sch{border-left:5px solid var(--grn);background:#f0fdf4;border-radius:8px;padding:10px 12px;margin:8px 0}
.sch h3{margin:0 0 4px;font-size:15px}.sch p{margin:2px 0;font-size:13px}
.likely{border-left-color:#f59e0b;background:#fffbeb}.civic{border-left-color:#2563eb;background:#eff6ff}
.warn{background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:10px 12px;margin:8px 0;font-weight:600}
.meta{font-size:11px;color:#64748b}.cd{font-size:18px;font-weight:800;color:#b91c1c}
pre.pet{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:8px;font-size:12px;white-space:pre-wrap;margin-top:8px}
#ledger{font-size:13px;color:#334155}
footer{font-size:11px;color:#64748b;text-align:center;padding:14px}
</style></head><body id="HAQSETU_DEMO_PAGE">
<div class="ribbon">DEMO BUILD — eligibility thresholds are NOT human‑verified · speech is your browser's, not the booth's model · do NOT use for real citizens</div>
<div class="tricolor"><div></div><div></div><div></div></div>
<header><h1>HaqSetu | हकसेतु</h1><p>The village speaks · the right desk is named · the clock is public · the machine never denies.</p></header>
<div class="wrap">
 <div class="card" style="text-align:center">
  <h2 style="margin:0 0 6px">Voice‑First Intake (abstains when unsure)</h2>
  <button class="mic" onclick="mic()">🎙️</button>
  <div id="status">Tap the mic, or type below.</div>
  <div class="row"><input id="t" type="text" placeholder="e.g. main 68 saal ki vidhwa hoon, kacha ghar hai  /  gaon ka handpump kharab ho gaya">
   <input id="ward" type="text" value="W-1" style="flex:0 0 90px;min-width:90px" title="ward">
   <button class="b" onclick="runAll()">Match Me</button>
   <button class="b o" onclick="speakResult()">🔊 Read</button></div>
  <div class="row" style="justify-content:center;font-size:12px;color:#64748b">quick:
   <button class="b" style="background:#e2e8f0;color:#0f172a" onclick="pick('main 68 saal ki vidhwa hoon, mera kacha ghar hai, aamdani 80 hazaar')">👵 Widow</button>
   <button class="b" style="background:#e2e8f0;color:#0f172a" onclick="pick('gaon ka handpump kharab ho gaya hai')">💧 Handpump</button>
   <button class="b" style="background:#e2e8f0;color:#0f172a" onclick="pick('naali ka paani bhar gaya, drain overflow')">🚰 Drain</button>
   <button class="b" style="background:#e2e8f0;color:#0f172a" onclick="pick('aaj mausam kaisa hai')">❓ Off‑topic</button></div>
 </div>
 <div class="card"><h3 style="margin:0 0 6px">Entitlements (real 77‑rule pack)</h3><div id="schemes"></div></div>
 <div class="card"><h3 style="margin:0 0 6px">Civic case + public clock</h3><div id="civic"></div></div>
 <div class="card"><div id="ledger">ledger not checked yet</div></div>
</div>
<footer>Powered by the audited village node · append‑only SQLite‑WAL ledger · PII stays vault‑side · this page is a demo, not a certified booth.</footer>
<script>
const $=id=>document.getElementById(id);
async function post(p,o){const r=await fetch(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(o)});if(!r.ok)throw new Error(p+" "+r.status);return r.json();}
async function getj(p){const r=await fetch(p);return r.json();}
function status(t){$("status").textContent=t;}
function pick(t){$("t").value=t;runAll();}
const CIVIC=[[/handpump|borewell|\bpump\b/i,"handpump"],[/\bpaani\b|\bpipe\b|water/i,"water"],[/drain|nala|sewage|ganda\s*paani/i,"drain"],[/road|sadak|rasta/i,"road"],[/garbage|kachra|kuda|waste/i,"garbage"],[/streetlight|batti|light\s*(not|nahi)/i,"streetlight"],[/toilet|shauchalaya|washroom/i,"public_toilet"],[/stray|kutte|janwar/i,"stray"],[/pollution|pradushan/i,"pollution"],[/encroach|kabza/i,"encroach"],[/community|bhawan|mandal/i,"community"]];
function detectCivic(t){for(const[re,c]of CIVIC)if(re.test(t))return c;return null;}
let cdTimer=null,lastSummary="";
async function runAll(){
 const t=$("t").value.trim();if(!t){status("Type or speak first.");return;}
 status('Heard: "'+t+'"');$("schemes").innerHTML="";$("civic").innerHTML="";lastSummary="";
 let v={};try{v=await post("/voice",{raw_text:t,actor_role:"mitra"});}catch(e){status("Server error: "+e);return;}
 renderVoice(v);
 const cat=detectCivic(t);
 if(cat){try{const c=await post("/civic",{category:cat,ward:$("ward").value||"W-1",actor_role:"mitra"});renderCivic(c,cat,t);}catch(e){$("civic").innerHTML='<div class="warn">civic error: '+e+'</div>';}}
 verifyLedger();
}
function renderVoice(v){
 const box=$("schemes");let h="";
 if(v.decision==="matched"){
  const tr=v.proof_trace||[];
  const inc=tr.filter(x=>x.outcome==="include");
  const lik=tr.filter(x=>x.outcome==="needs_official_decision"&&(x.uncertain_facts||[]).length);
  inc.forEach(x=>{h+='<div class="sch"><h3>✅ Enrol: '+(x.scheme_name||x.scheme)+'</h3>'+(x.benefit?'<p>Desk: '+x.benefit+'</p>':'')+'<p><b>Bring:</b> '+((x.docs||[]).join(", ")||"—")+'</p><p class="meta">verified by '+((x.verified_by||[]).join(", ")||"?")+(x.source&&x.source.url?' · '+x.source.url:'')+'</p></div>';});
  lik.forEach(x=>{h+='<div class="sch likely"><h3>📄 Likely: '+(x.scheme_name||x.scheme)+'</h3><p><b>Verify:</b> '+(x.uncertain_facts||[]).join(", ")+'</p></div>';});
  if(!inc.length&&!lik.length)(v.schemes||[]).forEach(s=>{h+='<div class="sch"><h3>✅ Enrol: '+s+'</h3></div>';});
  h+='<p class="meta">confidence '+v.confidence+' · case '+(v.case_id||"—")+' · receipt '+(v.receipt_id||"—")+'</p>';
  lastSummary="Based on what you told me, you can enrol in "+((v.schemes||[]).join(", ")||"the listed schemes")+".";
 }else{
  h+='<div class="warn">⚠️ AI abstained — nothing was denied. A facilitator will ask one question. ('+(v.reason||"unsure")+')</div>';
  lastSummary="I did not catch clear conditions. The facilitator will ask one question.";
 }
 box.innerHTML=h||'<div class="warn">No match; facilitator verifies.</div>';
}
function renderCivic(c,cat,t){
 const dl=Date.now()+(c.sla_hours||24)*3600*1000;
 $("civic").innerHTML='<div class="sch civic"><h3>🏛️ Civic case opened: '+cat+'</h3><p>case <b>'+(c.case_id||"")+'</b> · SLA <b>'+(c.sla_hours||"?")+'h</b> · clock running, on the next Panchayat agenda</p><p class="cd" id="cd">⏳ SLA remaining: —</p><pre class="pet">BEFORE THE GRAM PANCHAYAT SECRETARY\nUnder the Haryana Right to Service Act, 2014 (RTPS)\nCase ID: '+(c.case_id||"")+'\nSubject: '+cat+'\nFacts as declared and read back: '+t+'\nMandated period: '+(c.sla_hours||"?")+' hours from receipt. Countdown starts now.\n(Facilitator guidance. Portal submission SIMULATED in this demo.)</pre></div>';
 if(cdTimer)clearInterval(cdTimer);
 cdTimer=setInterval(()=>{const e=$("cd");if(!e){clearInterval(cdTimer);return;}const ms=dl-Date.now();if(ms<=0){e.textContent="⏰ SLA BREACHED — auto‑escalated above the Panchayat";clearInterval(cdTimer);return;}const d=Math.floor(ms/864e5),hh=Math.floor(ms%864e5/36e5),mm=Math.floor(ms%36e5/6e4),ss=Math.floor(ms%6e4/1e3);e.textContent="⏳ SLA remaining: "+d+"d "+hh+"h "+mm+"m "+ss+"s";},1000);
 lastSummary+=(lastSummary?" ":"")+"Your "+cat+" issue gets an SLA clock and the Panchayat‑meeting agenda.";
}
async function verifyLedger(){try{const rows=await getj("/chain");$("ledger").innerHTML='🔒 Append‑only ledger: <b>'+rows.length+'</b> signed rows. UPDATE/DELETE are blocked by DB triggers — a tampered row cannot be written back.';}catch(e){$("ledger").innerHTML="ledger check failed: "+e;}}
function speakResult(){if(!("speechSynthesis"in window))return alert("No TTS in this browser.");const u=new SpeechSynthesisUtterance(lastSummary||"Ready.");u.lang="en-IN";u.rate=.95;speechSynthesis.speak(u);}
function mic(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return alert("Use Chrome/Edge for the mic, or just type.");const r=new SR();r.lang="hi-IN";r.interimResults=false;r.onresult=e=>{$("t").value=e.results[0][0].transcript;runAll();};r.onerror=e=>status("Mic error: "+e.error);status("🔴 Listening…");r.start();}
</script></body></html>
HTMLEOF

python - <<'PATCHPY'
import pathlib,sys
p=pathlib.Path("village/server.py"); s=p.read_text()
if "_demo_html" in s:
    print("[skip] village already serves the demo page at /")
    sys.exit(0)
a1="class Handler(BaseHTTPRequestHandler):"
if s.count(a1)!=1: sys.exit(f"[ABORT] class anchor matched {s.count(a1)}x")
mods=('_DEMO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_demo", "index.html")\n'
      'def _demo_html():\n'
      '    try:\n'
      '        with open(_DEMO_PATH, encoding="utf-8") as f: return f.read()\n'
      '    except Exception:\n'
      '        return "<h1>demo page missing</h1><p>run bootstrap_demo.sh</p>"\n'
      'def _send_html(h, code, text):\n'
      '    b = text.encode("utf-8")\n'
      '    h.send_response(code); h.send_header("Content-Type","text/html; charset=utf-8")\n'
      '    h.send_header("Content-Length",str(len(b))); h.send_header("Access-Control-Allow-Origin","*")\n'
      '    h.send_header("Access-Control-Allow-Headers","Content-Type"); h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")\n'
      '    h.end_headers(); h.wfile.write(b)\n\n')
s=s.replace(a1, mods+a1, 1)
lines=s.splitlines(keepends=True)
idx=[i for i,l in enumerate(lines) if l.strip()=="u = urlparse(self.path)"]
if len(idx)!=1: sys.exit(f"[ABORT] urlparse anchor matched {len(idx)}x")
i=idx[0]; indent=lines[i][:len(lines[i])-len(lines[i].lstrip())]
lines[i+1:i+1]=[f'{indent}if u.path in ("/", "/demo", "/index.html"):\n',
                f'{indent}    _send_html(self, 200, _demo_html())\n',
                f'{indent}    return\n']
p.write_text("".join(lines)); print("[patch] village now serves /demo page")
PATCHPY
[ $? -ne 0 ] && { echo "[stop] patch failed"; exit 1; }
python -m py_compile village/server.py || { echo "[FAIL] village compile after patch"; exit 1; }

python - <<'SMOKEPY'
import os,sys,json,time,socket,subprocess,tempfile,urllib.request
root=os.getcwd(); d=tempfile.mkdtemp(prefix="haqdemo_")
s=socket.socket(); s.bind(("127.0.0.1",0)); port=s.getsockname()[1]; s.close()
env=dict(os.environ); env.update({"HAQ_CHAIN":f"{d}/chain.jsonl","HAQ_VAULT":f"{d}/vault.jsonl","HAQ_KEYS":f"{d}/keys","HAQ_VAULT_KEY":f"{d}/pii.key","SDM_DB":f"{d}/sdm.db","HAQ_OUTBOX":f"{d}/outbox.db","HAQ_BLOCK_DB":f"{d}/block.db","HAQ_VILLAGE_PORT":str(port),"HAQ_BLOCK_URL":"","HAQ_DEBUG":"1"}); env.pop("HAQ_RULEPACK",None)
p=subprocess.Popen([sys.executable,"-m","village.server"],cwd=root,env=env)
def get(pth):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{pth}",timeout=5) as r: return r.read()
def post(pth,o):
    rq=urllib.request.Request(f"http://127.0.0.1:{port}{pth}",data=json.dumps(o).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(rq,timeout=8) as r: return json.loads(r.read())
ok=True; m=[]
try:
    t0=time.time()
    while time.time()-t0<15:
        try:
            if json.loads(get("/health")).get("ok"): break
        except Exception: pass
        time.sleep(0.3)
    else: ok=False; m.append("village never became healthy")
    if ok:
        html=get("/").decode("utf-8","replace")
        if "HAQSETU_DEMO_PAGE" in html: m.append("GET / serves the demo page")
        else: ok=False; m.append("GET / missing sentinel (route not patched or page mangled by paste)")
    if ok:
        v=post("/voice",{"raw_text":"main 68 saal ki vidhwa hoon, mera kacha ghar hai, aamdani 80 hazaar","actor_role":"mitra"})
        if v.get("decision")=="matched" and (v.get("schemes") or v.get("proof_trace")): m.append("/voice matched via REAL rulepack: "+str(v.get("schemes")))
        else: ok=False; m.append("/voice not matched on real pack: "+json.dumps(v)[:200])
    if ok:
        c=post("/civic",{"category":"handpump","ward":"W-1","actor_role":"mitra"})
        c2=post("/civic",{"category":"drain","ward":"W-1","actor_role":"mitra"})
        if c.get("case_id") and c.get("sla_hours",0)>0 and c2.get("case_id"): m.append(f"/civic opened handpump {c['case_id']} ({c['sla_hours']}h) + drain {c2['case_id']}")
        else: ok=False; m.append("/civic bad: "+json.dumps(c)[:120]+" / "+json.dumps(c2)[:120])
    if ok:
        rows=json.loads(get("/chain"))
        if isinstance(rows,list) and len(rows)>=3: m.append(f"/chain has {len(rows)} signed rows (append-only)")
        else: ok=False; m.append("/chain rows<3")
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except Exception: p.kill()
for x in m: print("  "+x)
print("DEMO_READY" if ok else "DEMO_FAIL"); sys.exit(0 if ok else 1)
SMOKEPY
RC=$?
echo "----------------------------------------"
[ "$RC" -eq 0 ] && echo "DEMO_READY :: now start village (step 2) and open http://127.0.0.1:8000" || echo "DEMO_FAIL :: see the line above; re-copy ONLY this block and re-run (a paste likely dropped a newline)"
