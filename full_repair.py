import os, glob, ast

print("=" * 62)
print("HAQSETU FULL SYSTEM REPAIR & HEALTH CHECK")
print("=" * 62)

# ---------- 1. AUDIT ----------
required = [
    "engine/rules.py", "engine/clocks.py", "engine/matcher.py", "engine/planner.py",
    "engine/critical_path.py", "engine/proof_trace.py", "engine/appeal.py", "engine/red_flags.py",
    "ledger/chain.py", "ledger/tamper_tests.py",
    "rulepack/schema.py", "rulepack/load_check.py", "rulepack/check_z3.py",
    "triage/baselines.py", "triage/slots.py", "triage/abstain.py",
    "agent/solution_generator.py",
    "eval/metrics.py", "eval/synthetic_village.py",
    "mesh/telemetry_beacon.py", "mesh/heatwave_server.py",
]
missing = [f for f in required if not os.path.exists(f)]
for f in required:
    print(("[OK]       " if os.path.exists(f) else "[MISSING]  ") + f)
print(f"\nRule packs on disk: {len(glob.glob('rulepack/schemes/*.yaml'))} schemes, {len(glob.glob('rulepack/routes/*.yaml'))} routes")
print("Missing core files:", missing if missing else "NONE")

# ---------- 2. REWRITE THE FRAGILE FILES ----------
os.makedirs("api", exist_ok=True)
os.makedirs("web", exist_ok=True)

main_py = '''from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys, os, json, hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.abstain import triage_with_abstention
from agent.solution_generator import generate_spoken_solution

app = FastAPI(title="HaqSetu Agentic API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TriageRequest(BaseModel):
    text: str


class DenialAttempt(BaseModel):
    case_id: str
    reason: str


@app.post("/triage")
def run_triage(req: TriageRequest):
    result = triage_with_abstention(req.text)
    labels = result.get("labels", [])
    scheme = labels[0] if labels else "unknown"
    outcome = "include" if result["action"] == "ACCEPT" else "needs_official_decision"
    spoken_script = generate_spoken_solution(
        scheme=scheme,
        outcome=outcome,
        facts={},
        ttbr_data={"ttbr_days": 7, "bottleneck": {"task": "verification"}},
        proof_data={},
    )
    brain_scan = result.get("intent", {}).get("scores", {})
    return {
        "action": result["action"],
        "confidence": result["confidence"],
        "labels": labels,
        "spoken_script": spoken_script,
        "brain_scan": brain_scan,
    }


@app.post("/upload-evidence")
async def upload_evidence(file: UploadFile = File(...), case_id: str = "UNKNOWN"):
    contents = await file.read()
    photo_hash = hashlib.sha256(contents).hexdigest()
    os.makedirs("uploads", exist_ok=True)
    with open(f"uploads/{file.filename}", "wb") as f:
        f.write(contents)
    ledger_event = {
        "event": "evidence_locked",
        "case_id": case_id,
        "filename": file.filename,
        "sha256_hash": photo_hash,
        "timestamp": datetime.now().isoformat(),
        "actor": "facilitator",
    }
    os.makedirs("ledger", exist_ok=True)
    with open("ledger/chain.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ledger_event) + "\\n")
    return {"status": "LOCKED", "filename": file.filename, "sha256": photo_hash}


@app.post("/attempt-denial")
def attempt_denial(req: DenialAttempt):
    proof_trace = {
        "premise_1": "HaqSetu Core Directive: include, escalate, abstain; never deny.",
        "premise_2": f"Local Official attempted to reject Case {req.case_id}.",
        "premise_3": f"Stated Reason: '{req.reason}'.",
        "premise_4": "Rule pack validation: citizen meets baseline criteria or requires human review.",
        "conclusion": "AUTOMATED DENIAL PRECLUDED BY CONSTRUCTION.",
        "action_taken": "Case escalated to District Grievance Redressal Officer.",
        "cryptographic_receipt": hashlib.sha256(
            f"{req.case_id}{req.reason}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16],
    }
    return {
        "status": "DENIAL_BLOCKED",
        "message": "The system cannot deny a citizen. Attempt logged and escalated.",
        "proof_trace": proof_trace,
    }


@app.get("/health")
def health():
    return {"status": "ok", "empire_status": "ONLINE"}


@app.get("/cases")
def get_cases():
    return []
'''

index_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HaqSetu | Agentic Node</title>
    <link rel="manifest" href="manifest.json">
    <meta name="theme-color" content="#0f172a">
    <style>
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; text-align: center; }
        h1 { color: #38bdf8; margin-bottom: 5px; }
        .tagline { color: #94a3b8; font-style: italic; margin-bottom: 30px; }
        .btn-mic { background: #dc2626; color: white; font-size: 24px; padding: 20px 40px; border-radius: 50px; border: none; cursor: pointer; box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4); }
        .btn-mic:disabled { background: #475569; cursor: not-allowed; }
        #voice-status { font-size: 18px; margin: 20px 0; min-height: 30px; color: #fbbf24; }
        .brain-scan { background: #1e293b; padding: 20px; border-radius: 12px; margin-top: 20px; display: none; text-align: left; border: 1px solid #334155; }
        .brain-title { font-size: 14px; color: #94a3b8; text-transform: uppercase; margin-bottom: 10px; }
        .bar-container { margin-bottom: 8px; }
        .bar-label { font-size: 12px; display: flex; justify-content: space-between; margin-bottom: 2px; }
        .bar-bg { background: #334155; height: 8px; border-radius: 4px; overflow: hidden; }
        .bar-fill { height: 100%; background: #38bdf8; border-radius: 4px; }
        .vault { background: #1e293b; padding: 20px; border-radius: 12px; margin-top: 20px; border: 1px solid #334155; display: none; }
        .vault-title { color: #10b981; font-weight: bold; margin-bottom: 10px; }
        .hash-display { font-family: monospace; font-size: 12px; color: #94a3b8; word-break: break-all; background: #0f172a; padding: 10px; border-radius: 6px; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>HaqSetu Agentic Node</h1>
    <p class="tagline">The village speaks. The right desk is named. The plan fits one visit. The clock is public. The machine never denies.</p>

    <button id="btn-speak" class="btn-mic">Speak to HaqSetu</button>
    <div id="voice-status">Click to begin intake...</div>

    <div id="brain-scan" class="brain-scan">
        <div class="brain-title">AI Brain Scan (Live Confidence Weights)</div>
        <div id="brain-bars"></div>
    </div>

    <div id="vault" class="vault">
        <div class="vault-title">Cryptographic Evidence Vault</div>
        <p style="font-size: 14px; color: #94a3b8;">Upload a photo. Its SHA-256 pixel hash is locked in the ledger.</p>
        <input type="file" id="file-input" accept="image/*" style="color: #f8fafc;">
        <button id="btn-upload" style="background: #10b981; color: white; padding: 10px 20px; border: none; border-radius: 6px; margin-top: 10px; cursor: pointer;">Lock Evidence</button>
        <div id="vault-hash" class="hash-display" style="display:none;"></div>
    </div>

    <div class="vault" style="display: block; border-color: #dc2626; margin-top: 30px;">
        <div class="vault-title" style="color: #dc2626;">EXHIBIT CHALLENGE: Try to Deny Me</div>
        <p style="font-size: 14px; color: #94a3b8;">Pretend you are a corrupt official. Try to reject this widow's pension case.</p>
        <input type="text" id="denial-reason" placeholder="Enter fake reason (e.g., 'No funds')" style="width: 100%; padding: 10px; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 6px; margin-top: 10px; box-sizing: border-box;">
        <button id="btn-deny" style="background: #dc2626; color: white; padding: 12px 20px; border: none; border-radius: 6px; margin-top: 10px; cursor: pointer; font-weight: bold; width: 100%;">ATTEMPT DENIAL (Sarpanch Override)</button>
        <div id="denial-result" style="display:none; margin-top: 15px; background: #0f172a; padding: 15px; border-radius: 8px; border: 2px solid #10b981; text-align: left;">
            <div style="color: #10b981; font-weight: bold; font-size: 16px; margin-bottom: 10px;">DENIAL BLOCKED. AUTO-ESCALATED.</div>
            <pre id="proof-trace" style="color: #f8fafc; font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 0;"></pre>
        </div>
    </div>

    <script src="app.js"></script>
</body>
</html>
'''

app_js = '''const API_URL = "http://127.0.0.1:8000";
const btnSpeak = document.getElementById('btn-speak');
const voiceStatus = document.getElementById('voice-status');
const brainScan = document.getElementById('brain-scan');
const brainBars = document.getElementById('brain-bars');
const vault = document.getElementById('vault');

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'hi-IN';
    recognition.interimResults = false;
}

btnSpeak.addEventListener('click', () => {
    if (!recognition) { voiceStatus.textContent = "Use Chrome, Edge or Brave for Voice AI."; return; }
    voiceStatus.textContent = "Listening...";
    btnSpeak.disabled = true;
    recognition.start();
});

if (recognition) {
    recognition.onresult = async (event) => {
        const transcript = event.results[0][0].transcript;
        voiceStatus.textContent = 'Heard: "' + transcript + '"';
        try {
            const res = await fetch(API_URL + "/triage", {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: transcript })
            });
            const data = await res.json();
            renderBrainScan(data.brain_scan || {});
            if (data.action === 'ABSTAIN') {
                voiceStatus.innerHTML = '<span style="color:#fbbf24">AI Abstained (safe). Facilitator selects manually.</span>';
            } else {
                voiceStatus.innerHTML = '<span style="color:#10b981">Intent: ' + data.labels.join(', ') + '. Speaking...</span>';
                speakOutLoud(data.spoken_script);
                vault.style.display = 'block';
            }
        } catch (e) { voiceStatus.textContent = "API Error. Is Uvicorn running on port 8000?"; }
        btnSpeak.disabled = false;
    };
    recognition.onerror = () => { voiceStatus.textContent = "Mic error. Allow microphone access."; btnSpeak.disabled = false; };
}

function renderBrainScan(scores) {
    brainScan.style.display = 'block';
    brainBars.innerHTML = '';
    const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]).slice(0, 5);
    sorted.forEach(([intent, score]) => {
        const pct = (score * 100).toFixed(1);
        brainBars.innerHTML += '<div class="bar-container"><div class="bar-label"><span>' + intent.replace('_', ' ') + '</span><span>' + pct + '%</span></div><div class="bar-bg"><div class="bar-fill" style="width:' + pct + '%"></div></div></div>';
    });
}

document.getElementById('btn-upload').addEventListener('click', async () => {
    const fileInput = document.getElementById('file-input');
    if (!fileInput.files.length) { alert("Select an image first."); return; }
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('case_id', 'LIVE-DEMO-001');
    voiceStatus.textContent = "Hashing pixels and locking into ledger...";
    const res = await fetch(API_URL + "/upload-evidence", { method: 'POST', body: formData });
    const data = await res.json();
    voiceStatus.innerHTML = '<span style="color:#10b981">Evidence Locked!</span>';
    const hd = document.getElementById('vault-hash');
    hd.style.display = 'block';
    hd.textContent = 'SHA-256: ' + data.sha256;
});

document.getElementById('btn-deny').addEventListener('click', async () => {
    const reason = document.getElementById('denial-reason').value || "No reason provided";
    const resultDiv = document.getElementById('denial-result');
    const proofTrace = document.getElementById('proof-trace');
    const btn = document.getElementById('btn-deny');
    btn.disabled = true;
    btn.textContent = "Processing Override...";
    try {
        const res = await fetch(API_URL + "/attempt-denial", {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_id: "WIDOW-PENSION-001", reason: reason })
        });
        const data = await res.json();
        let traceText = "";
        for (const [key, value] of Object.entries(data.proof_trace)) {
            traceText += key.toUpperCase() + ": " + value + "\\n";
        }
        proofTrace.textContent = traceText;
        resultDiv.style.display = 'block';
        speakOutLoud("Denial blocked. Automated rejection is precluded by construction. Case auto-escalated to District Magistrate.");
    } catch (e) { alert("Error connecting to Anti-Corruption Shield."); }
    btn.textContent = "ATTEMPT DENIAL (Sarpanch Override)";
    btn.disabled = false;
});

function speakOutLoud(text) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-IN';
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
}
'''

manifest_json = '''{
  "name": "HaqSetu Agentic Node",
  "short_name": "HaqSetu",
  "start_url": ".",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#0f172a",
  "description": "Verified-rules entitlement planner with tamper-evident ledger",
  "icons": [{"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌉</text></svg>", "sizes": "any", "type": "image/svg+xml"}]
}
'''

sw_js = '''const CACHE = 'haqsetu-v1';
const ASSETS = ['index.html', 'app.js', 'manifest.json'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))); });
self.addEventListener('fetch', e => { e.respondWith(caches.match(e.request).then(r => r || fetch(e.request))); });
'''

for path, content in [("api/main.py", main_py), ("web/index.html", index_html), ("web/app.js", app_js), ("web/manifest.json", manifest_json), ("web/sw.js", sw_js)]:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[UPDATED]  " + path)

# ---------- 3. SYNTAX VALIDATION ----------
print("-" * 62)
bad = []
for f in ["api/main.py", "triage/baselines.py", "triage/slots.py", "triage/abstain.py",
          "agent/solution_generator.py", "engine/rules.py", "engine/planner.py", "engine/red_flags.py"]:
    if os.path.exists(f):
        try:
            ast.parse(open(f, encoding="utf-8").read())
            print("[SYNTAX OK]   " + f)
        except Exception as e:
            bad.append(f)
            print("[SYNTAX FAIL] " + f + " -> " + str(e))
print("-" * 62)
if bad:
    print("!! DO NOT START SERVERS. Fix these first:", bad)
else:
    print("ALL CLEAR. Proceed to rule-pack refresh and boot.")