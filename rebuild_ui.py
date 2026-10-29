import os

os.makedirs('web', exist_ok=True)

html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HaqSetu | Agentic Node</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; text-align: center; }
        h1 { color: #38bdf8; margin-bottom: 5px; }
        .tagline { color: #94a3b8; font-style: italic; margin-bottom: 30px; }
        .btn-mic { background: #dc2626; color: white; font-size: 24px; padding: 20px 40px; border-radius: 50px; border: none; cursor: pointer; box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4); }
        .btn-mic:disabled { background: #475569; cursor: not-allowed; }
        #voice-status { font-size: 18px; margin: 20px 0; min-height: 30px; color: #fbbf24; }
        .brain-scan { background: #1e293b; padding: 20px; border-radius: 12px; margin-top: 20px; display: none; text-align: left; border: 1px solid #334155;}
        .brain-title { font-size: 14px; color: #94a3b8; text-transform: uppercase; margin-bottom: 10px; }
        .bar-container { margin-bottom: 8px; }
        .bar-label { font-size: 12px; display: flex; justify-content: space-between; margin-bottom: 2px; }
        .bar-bg { background: #334155; height: 8px; border-radius: 4px; overflow: hidden; }
        .bar-fill { height: 100%; background: #38bdf8; border-radius: 4px; transition: width 0.5s ease; }
        .vault { background: #1e293b; padding: 20px; border-radius: 12px; margin-top: 20px; border: 1px solid #334155; display: none;}
        .vault-title { color: #10b981; font-weight: bold; margin-bottom: 10px;}
        .hash-display { font-family: monospace; font-size: 12px; color: #94a3b8; word-break: break-all; background: #0f172a; padding: 10px; border-radius: 6px; margin-top: 10px;}
    </style>
</head>
<body>
    <h1>🌉 HaqSetu Agentic Node</h1>
    <p class="tagline">The village speaks. The AI listens. The ledger locks.</p>

    <button id="btn-speak" class="btn-mic">🎙️ Speak to HaqSetu</button>
    <div id="voice-status">Click to begin intake...</div>

    <div id="brain-scan" class="brain-scan">
        <div class="brain-title">🧠 AI Brain Scan (Live TF-IDF Confidence Weights)</div>
        <div id="brain-bars"></div>
    </div>

    <div id="vault" class="vault">
        <div class="vault-title">🔒 Cryptographic Evidence Vault</div>
        <p style="font-size: 14px; color: #94a3b8;">Upload a photo. Its SHA-256 pixel hash will be locked in the ledger.</p>
        <input type="file" id="file-input" accept="image/*" style="color: #f8fafc;">
        <button id="btn-upload" style="background: #10b981; color: white; padding: 10px 20px; border: none; border-radius: 6px; margin-top: 10px; cursor: pointer;">Lock Evidence</button>
        <div id="vault-hash" class="hash-display" style="display:none;"></div>
    </div>

    <!-- The Anti-Corruption Challenge -->
    <div class="vault" style="display: block; border-color: #dc2626; margin-top: 30px;">
        <div class="vault-title" style="color: #dc2626;">🛡️ EXHIBIT CHALLENGE: Try to Deny Me</div>
        <p style="font-size: 14px; color: #94a3b8;">Pretend you are a corrupt official. Try to reject this widow's pension case.</p>
        <input type="text" id="denial-reason" placeholder="Enter fake reason (e.g., 'No funds')" style="width: 100%; padding: 10px; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 6px; margin-top: 10px; box-sizing: border-box;">
        <button id="btn-deny" style="background: #dc2626; color: white; padding: 12px 20px; border: none; border-radius: 6px; margin-top: 10px; cursor: pointer; font-weight: bold; width: 100%;">⚠️ ATTEMPT DENIAL (Sarpanch Override)</button>
        <div id="denial-result" style="display:none; margin-top: 15px; background: #0f172a; padding: 15px; border-radius: 8px; border: 2px solid #10b981; text-align: left;">
            <div style="color: #10b981; font-weight: bold; font-size: 16px; margin-bottom: 10px;">✅ DENIAL BLOCKED. AUTO-ESCALATED.</div>
            <pre id="proof-trace" style="color: #f8fafc; font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 0;"></pre>
        </div>
    </div>

    <script src="app.js"></script>
</body>
</html>"""

js_content = """const API_URL = "http://127.0.0.1:8000";
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
    if (!recognition) return voiceStatus.textContent = "Use Chrome or Edge for Voice AI.";
    voiceStatus.textContent = "🔴 Listening...";
    btnSpeak.disabled = true;
    recognition.start();
});

if (recognition) {
    recognition.onresult = async (event) => {
        const transcript = event.results[0][0].transcript;
        voiceStatus.textContent = `🗣️ Heard: "${transcript}"`;
        try {
            const res = await fetch(`${API_URL}/triage`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: transcript })
            });
            const data = await res.json();
            renderBrainScan(data.brain_scan);
            if (data.action === 'ABSTAIN') {
                voiceStatus.innerHTML = `⚠️ <span style="color:#fbbf24">AI Abstained.</span>`;
            } else {
                voiceStatus.innerHTML = `✅ <span style="color:#10b981">Intent: ${data.labels[0]}. Speaking...</span>`;
                speakOutLoud(data.spoken_script);
                vault.style.display = 'block';
            }
        } catch (e) { voiceStatus.textContent = "❌ API Error. Is Uvicorn running?"; }
        btnSpeak.disabled = false;
    };
}

function renderBrainScan(scores) {
    brainScan.style.display = 'block'; brainBars.innerHTML = '';
    const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]).slice(0, 5);
    sorted.forEach(([intent, score]) => {
        const pct = (score * 100).toFixed(1);
        brainBars.innerHTML += `<div class="bar-container"><div class="bar-label"><span>${intent.replace('_', ' ')}</span><span>${pct}%</span></div><div class="bar-bg"><div class="bar-fill" style="width: ${pct}%"></div></div></div>`;
    });
}

document.getElementById('btn-upload').addEventListener('click', async () => {
    const fileInput = document.getElementById('file-input');
    if (!fileInput.files.length) return alert("Select an image first.");
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('case_id', 'LIVE-DEMO-001');
    voiceStatus.textContent = "🔒 Hashing pixels...";
    const res = await fetch(`${API_URL}/upload-evidence`, { method: 'POST', body: formData });
    const data = await res.json();
    voiceStatus.innerHTML = `✅ <span style="color:#10b981">Evidence Locked!</span>`;
    const hashDisplay = document.getElementById('vault-hash');
    hashDisplay.style.display = 'block';
    hashDisplay.textContent = `SHA-256: ${data.sha256}`;
});

document.getElementById('btn-deny').addEventListener('click', async () => {
    const reason = document.getElementById('denial-reason').value || "No reason";
    const resultDiv = document.getElementById('denial-result');
    const proofTrace = document.getElementById('proof-trace');
    const btn = document.getElementById('btn-deny');
    btn.disabled = true; btn.textContent = "⏳ Processing Override...";
    try {
        const res = await fetch(`${API_URL}/attempt-denial`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_id: "WIDOW-PENSION-001", reason: reason })
        });
        const data = await res.json();
        let traceText = "";
        for (const [key, value] of Object.entries(data.proof_trace)) {
            traceText += `${key.replace('_', ' ').toUpperCase()}: ${value}\n`;
        }
        proofTrace.textContent = traceText;
        resultDiv.style.display = 'block';
        btn.textContent = "⚠️ ATTEMPT DENIAL (Sarpanch Override)";
        speakOutLoud("Denial blocked. Automated rejection is precluded by construction. Case auto-escalated.");
    } catch (e) { alert("Error connecting to Anti-Corruption Shield."); }
    btn.disabled = false;
});

function speakOutLoud(text) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-IN'; u.rate = 0.95;
    window.speechSynthesis.speak(u);
}
"""

with open('web/index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

with open('web/app.js', 'w', encoding='utf-8') as f:
    f.write(js_content)

print("✅ UI Files rebuilt perfectly without Notepad extension bugs!")