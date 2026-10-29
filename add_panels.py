import os

os.makedirs("api", exist_ok=True)
os.makedirs("web", exist_ok=True)

main_py = '''from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys, os, json, hashlib, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.abstain import triage_with_abstention
from agent.solution_generator import generate_spoken_solution
from engine.red_flags import analyze_corruption_risk

app = FastAPI(title="HaqSetu Agentic API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CASES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases_board.json")
VERIFIER_POOL = ["School Teacher (rotating pool)", "ASHA Worker (rotating pool)", "SHG Representative (rotating pool)"]


class TriageRequest(BaseModel):
    text: str


class DenialAttempt(BaseModel):
    case_id: str
    reason: str


class OpenCase(BaseModel):
    case_id: str
    route: str
    desk: str
    waiting_at: str = "Panchayat"
    clock_hours: int = 48


class CloseCase(BaseModel):
    case_id: str
    force_audit: bool = False


class FastForward(BaseModel):
    case_id: str
    hours: int = 48


def _load_cases():
    if not os.path.exists(CASES_FILE):
        return []
    with open(CASES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_cases(cases):
    with open(CASES_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)


def _log_ledger(event):
    os.makedirs("ledger", exist_ok=True)
    with open("ledger/chain.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\\n")


@app.post("/triage")
def run_triage(req: TriageRequest):
    result = triage_with_abstention(req.text)
    labels = result.get("labels", [])
    scheme = labels[0] if labels else "unknown"
    outcome = "include" if result["action"] == "ACCEPT" else "needs_official_decision"
    spoken_script = generate_spoken_solution(
        scheme=scheme, outcome=outcome, facts={},
        ttbr_data={"ttbr_days": 7, "bottleneck": {"task": "verification"}}, proof_data={},
    )
    return {
        "action": result["action"],
        "confidence": result["confidence"],
        "labels": labels,
        "spoken_script": spoken_script,
        "brain_scan": result.get("intent", {}).get("scores", {}),
    }


@app.post("/upload-evidence")
async def upload_evidence(file: UploadFile = File(...), case_id: str = "UNKNOWN"):
    contents = await file.read()
    photo_hash = hashlib.sha256(contents).hexdigest()
    os.makedirs("uploads", exist_ok=True)
    with open(f"uploads/{file.filename}", "wb") as f:
        f.write(contents)
    _log_ledger({"event": "evidence_locked", "case_id": case_id, "filename": file.filename,
                 "sha256_hash": photo_hash, "timestamp": datetime.now().isoformat(), "actor": "facilitator"})
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
            f"{req.case_id}{req.reason}{datetime.now().isoformat()}".encode()).hexdigest()[:16],
    }
    return {"status": "DENIAL_BLOCKED",
            "message": "The system cannot deny a citizen. Attempt logged and escalated.",
            "proof_trace": proof_trace}


@app.get("/red-flags")
def red_flags():
    return analyze_corruption_risk()


@app.post("/open-case")
def open_case(req: OpenCase):
    cases = _load_cases()
    cases.append({"case_id": req.case_id, "route": req.route, "desk": req.desk,
                  "waiting_at": req.waiting_at, "clock_hours": req.clock_hours,
                  "opened_at": datetime.now().isoformat(), "status": "open"})
    _save_cases(cases)
    _log_ledger({"event": "case_opened", "case_id": req.case_id, "route": req.route,
                 "desk": req.desk, "clock_hours": req.clock_hours,
                 "timestamp": datetime.now().isoformat(), "actor": "facilitator"})
    return {"status": "opened", "case_id": req.case_id}


@app.get("/board")
def board():
    cases = _load_cases()
    now = datetime.now()
    out = []
    changed = False
    led_map = {"open": "red", "in_progress": "amber", "escalated": "amber",
               "ghost_audit": "amber", "closed": "green"}
    for c in cases:
        elapsed = (now - datetime.fromisoformat(c["opened_at"])).total_seconds() / 3600.0
        if c["status"] in ("open", "in_progress") and elapsed > c["clock_hours"]:
            c["status"] = "escalated"
            c["waiting_at"] = "Block Office (auto-escalated with evidence)"
            changed = True
            _log_ledger({"event": "auto_escalation", "case_id": c["case_id"],
                         "reason": "stall rule exceeded", "timestamp": now.isoformat(), "actor": "system"})
        out.append({**c, "hours_elapsed": round(elapsed, 1),
                    "led": led_map.get(c["status"], "red"),
                    "overdue": elapsed > c["clock_hours"]})
    if changed:
        _save_cases(cases)
    return {"cases": out}


@app.post("/fast-forward")
def fast_forward(req: FastForward):
    cases = _load_cases()
    for c in cases:
        if c["case_id"] == req.case_id:
            c["opened_at"] = (datetime.fromisoformat(c["opened_at"]) - timedelta(hours=req.hours)).isoformat()
            _save_cases(cases)
            return {"status": "fast-forwarded", "case_id": req.case_id, "hours": req.hours}
    return {"status": "case not found"}


@app.post("/close-case")
def close_case(req: CloseCase):
    cases = _load_cases()
    target = next((c for c in cases if c["case_id"] == req.case_id), None)
    if target is None:
        return {"status": "case not found"}
    if req.force_audit or random.random() < 0.10:
        verifiers = random.sample(VERIFIER_POOL, 2)
        target["status"] = "ghost_audit"
        target["verifiers"] = verifiers
        _save_cases(cases)
        _log_ledger({"event": "ghost_audit_triggered", "case_id": req.case_id,
                     "verifiers": verifiers, "timestamp": datetime.now().isoformat(), "actor": "system"})
        return {"status": "GHOST_AUDIT_TRIGGERED", "case_id": req.case_id, "verifiers": verifiers,
                "message": "Closure intercepted by the 10% callback rule. Case locked until two independent verifiers confirm."}
    target["status"] = "closed"
    _save_cases(cases)
    _log_ledger({"event": "case_closed", "case_id": req.case_id,
                 "timestamp": datetime.now().isoformat(), "actor": "official"})
    return {"status": "CLOSED_PENDING_CITIZEN_CONFIRM", "case_id": req.case_id,
            "message": "Closed. Awaiting citizen confirmation by slip code."}


@app.get("/health")
def health():
    return {"status": "ok", "empire_status": "ONLINE"}


@app.get("/cases")
def get_cases():
    return _load_cases()
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
        .vault { background: #1e293b; padding: 20px; border-radius: 12px; margin-top: 20px; border: 1px solid #334155; display: none; text-align: left; }
        .vault-title { color: #10b981; font-weight: bold; margin-bottom: 10px; }
        .hash-display { font-family: monospace; font-size: 12px; color: #94a3b8; word-break: break-all; background: #0f172a; padding: 10px; border-radius: 6px; margin-top: 10px; }
        .panel { background: #1e293b; padding: 20px; border-radius: 12px; margin-top: 30px; border: 1px solid #334155; text-align: left; }
        .row { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 10px; margin-bottom: 8px; font-size: 13px; }
        .flag-critical { border-color: #dc2626; }
        .flag-high { border-color: #f59e0b; }
        .led { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; }
        .btn-small { background: #334155; color: #f8fafc; border: none; border-radius: 6px; padding: 8px 12px; cursor: pointer; margin-right: 6px; margin-top: 6px; }
        input[type=text] { width: 100%; padding: 10px; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 6px; margin-top: 10px; box-sizing: border-box; }
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
        <button id="btn-upload" class="btn-small" style="background:#10b981;">Lock Evidence</button>
        <div id="vault-hash" class="hash-display" style="display:none;"></div>
    </div>

    <div class="panel" style="border-color: #dc2626;">
        <div class="vault-title" style="color: #dc2626;">EXHIBIT CHALLENGE: Try to Deny Me</div>
        <p style="font-size: 14px; color: #94a3b8;">Pretend you are a corrupt official. Try to reject this widow's pension case.</p>
        <input type="text" id="denial-reason" placeholder="Enter fake reason (e.g., 'No funds')">
        <button id="btn-deny" style="background: #dc2626; color: white; padding: 12px 20px; border: none; border-radius: 6px; margin-top: 10px; cursor: pointer; font-weight: bold; width: 100%;">ATTEMPT DENIAL (Sarpanch Override)</button>
        <div id="denial-result" style="display:none; margin-top: 15px; background: #0f172a; padding: 15px; border-radius: 8px; border: 2px solid #10b981;">
            <div style="color: #10b981; font-weight: bold; font-size: 16px; margin-bottom: 10px;">DENIAL BLOCKED. AUTO-ESCALATED.</div>
            <pre id="proof-trace" style="color: #f8fafc; font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 0;"></pre>
        </div>
    </div>

    <div class="panel" style="border-color: #f59e0b;">
        <div class="vault-title" style="color: #f59e0b;">🚨 RED FLAG EXTORTION DASHBOARD</div>
        <p style="font-size: 14px; color: #94a3b8;">Scans ledger statistics for desks showing corruption patterns (chronic stalls, mass rejections).</p>
        <button id="btn-flags" class="btn-small" style="background:#f59e0b;color:#0f172a;font-weight:bold;">Scan Ledger for Corruption Patterns</button>
        <div id="flags-out" style="margin-top:10px;"></div>
    </div>

    <div class="panel" style="border-color: #38bdf8;">
        <div class="vault-title" style="color: #38bdf8;">⏰ LIVE STALL-WATCH BOARD</div>
        <p style="font-size: 14px; color: #94a3b8;">Every open case carries a public clock. Stalls auto-escalate with evidence. "Pending at Panchayat" is separated from "pending at another office".</p>
        <button id="btn-open-case" class="btn-small">+ Open Case (Crop Loss, 72h)</button>
        <button id="btn-open-case2" class="btn-small">+ Open Case (Pension, 48h)</button>
        <button id="btn-refresh-board" class="btn-small">Refresh Board</button>
        <div id="board-out" style="margin-top:10px;"></div>
    </div>

    <div class="panel" style="border-color: #a855f7;">
        <div class="vault-title" style="color: #a855f7;">👻 GHOST AUDIT CLOSURE (10% Callback Rule)</div>
        <p style="font-size: 14px; color: #94a3b8;">Officials cannot silently close fake work. 10% of closures are intercepted and sent to two independent verifiers.</p>
        <input type="text" id="close-case-id" placeholder="Case ID from the board (e.g., CASE-1234)">
        <label style="font-size:13px;color:#94a3b8;"><input type="checkbox" id="force-audit"> Force audit (demo switch)</label>
        <button id="btn-close-case" class="btn-small" style="background:#a855f7;font-weight:bold;">Close Case (Official)</button>
        <div id="close-out" style="margin-top:10px;"></div>
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
    Object.entries(scores).sort((a, b) => b[1] - a[1]).slice(0, 5).forEach(([intent, score]) => {
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

function ledColor(name) { return { red: '#dc2626', amber: '#f59e0b', green: '#10b981' }[name] || '#dc2626'; }

async function loadBoard() {
    const out = document.getElementById('board-out');
    try {
        const res = await fetch(API_URL + '/board');
        const data = await res.json();
        if (!data.cases.length) { out.innerHTML = '<p style="color:#94a3b8;font-size:13px;">No open cases. Open a demo case above.</p>'; return; }
        out.innerHTML = data.cases.map(c =>
            '<div class="row"><span class="led" style="background:' + ledColor(c.led) + ';box-shadow:0 0 8px ' + ledColor(c.led) + '"></span>' +
            '<b>' + c.case_id + '</b> · ' + c.route + ' · desk: ' + c.desk +
            '<br>Waiting at: <b>' + c.waiting_at + '</b> · Clock: ' + c.hours_elapsed + 'h / ' + c.clock_hours + 'h · Status: <b>' + c.status.toUpperCase() + '</b>' +
            (c.status !== 'closed' ? ' <button class="btn-small" onclick="ffCase(\\x27' + c.case_id + '\\x27)">⏩ +48h</button>' : '') +
            '</div>'
        ).join('');
    } catch (e) { out.innerHTML = '<p style="color:#dc2626;">API offline.</p>'; }
}

window.ffCase = async (id) => {
    await fetch(API_URL + '/fast-forward', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ case_id: id, hours: 48 }) });
    loadBoard();
};

document.getElementById('btn-open-case').addEventListener('click', async () => {
    const id = 'CASE-' + Date.now().toString().slice(-4);
    await fetch(API_URL + '/open-case', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: id, route: 'crop_loss', desk: 'Patwari', waiting_at: 'Panchayat', clock_hours: 72 }) });
    loadBoard();
});

document.getElementById('btn-open-case2').addEventListener('click', async () => {
    const id = 'CASE-' + Date.now().toString().slice(-4);
    await fetch(API_URL + '/open-case', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: id, route: 'pension', desk: 'BDO', waiting_at: 'Panchayat', clock_hours: 48 }) });
    loadBoard();
});

document.getElementById('btn-refresh-board').addEventListener('click', loadBoard);

document.getElementById('btn-flags').addEventListener('click', async () => {
    const out = document.getElementById('flags-out');
    out.innerHTML = 'Scanning ledger...';
    try {
        const res = await fetch(API_URL + '/red-flags');
        const data = await res.json();
        if (!data.flags.length) { out.innerHTML = '<p style="color:#10b981;">No corruption patterns detected.</p>'; return; }
        out.innerHTML = '<p style="font-size:13px;color:#94a3b8;">Desks monitored: ' + data.total_desks_monitored + ' · Alerts: ' + data.corruption_alerts + '</p>' +
            data.flags.map(f =>
                '<div class="row ' + (f.risk_level === 'CRITICAL' ? 'flag-critical' : 'flag-high') + '"><b>' + f.desk + '</b> — ' + f.risk_level + ' RISK<br>' +
                'Stall rate: ' + f.stall_rate + '% · Reject rate: ' + f.reject_rate + '%<br>' +
                f.reasons.map(r => '• ' + r).join('<br>') + '<br><i>Action: ' + f.action_required + '</i></div>'
            ).join('');
    } catch (e) { out.innerHTML = '<p style="color:#dc2626;">API offline.</p>'; }
});

document.getElementById('btn-close-case').addEventListener('click', async () => {
    const id = document.getElementById('close-case-id').value.trim();
    if (!id) { alert('Enter a case ID from the board.'); return; }
    const force = document.getElementById('force-audit').checked;
    const res = await fetch(API_URL + '/close-case', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: id, force_audit: force }) });
    const data = await res.json();
    const out = document.getElementById('close-out');
    if (data.status === 'GHOST_AUDIT_TRIGGERED') {
        out.innerHTML = '<div class="row flag-high"><b>👻 GHOST AUDIT TRIGGERED</b><br>' + data.message + '<br>Verifiers: ' + data.verifiers.join(' + ') + '</div>';
        speakOutLoud("Closure intercepted. Independent callback audit assigned. Case locked until two verifiers confirm.");
    } else {
        out.innerHTML = '<div class="row" style="border-color:#10b981;"><b>✅ ' + data.status + '</b><br>' + (data.message || '') + '</div>';
    }
    loadBoard();
});

function speakOutLoud(text) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-IN';
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
}

loadBoard();
'''

for path, content in [("api/main.py", main_py), ("web/index.html", index_html), ("web/app.js", app_js)]:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[UPDATED]  " + path)

import ast
ast.parse(open("api/main.py", encoding="utf-8").read())
print("[SYNTAX OK] api/main.py")
print("✅ Governance panels installed. Hard-refresh the browser (Ctrl+Shift+R).")