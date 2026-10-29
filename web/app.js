const API_URL = "";
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
            traceText += key.toUpperCase() + ": " + value + "\n";
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
            (c.status !== 'closed' ? ' <button class="btn-small" onclick="ffCase(\x27' + c.case_id + '\x27)">⏩ +48h</button>' : '') +
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
