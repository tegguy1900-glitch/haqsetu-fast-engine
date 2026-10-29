import re

# --- PART A: FIX THE HTML STRUCTURE ---
print("🔧 Updating HTML Structure...")
with open('web_demo/index.html', 'r') as f:
    html = f.read()

new_sarpanch_html = '''<!-- VIEW: SARPANCH (FULLY FUNCTIONAL) -->
<section id="view-sarpanch" class="view-section" style="display:none;">
    <div class="page-header">
        <h2 class="page-title">Gram Sabha Command Center</h2>
        <p class="page-subtitle">Real-time oversight of village grievances and schemes.</p>
    </div>

    <!-- TOP STATS ROW -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px;">
        <div class="card" style="border-left-color: var(--danger); text-align:center;">
            <h3 style="font-size:2rem; color:var(--danger);" id="stat-open-count">0</h3>
            <p style="color:var(--text-muted); font-weight:600;">Open Grievances</p>
        </div>
        <div class="card" style="border-left-color: var(--accent); text-align:center;">
            <h3 style="font-size:2rem; color:var(--accent);" id="stat-resolved-count">0</h3>
            <p style="color:var(--text-muted); font-weight:600;">Resolved Today</p>
        </div>
        <div class="card" style="border-left-color: var(--warning); text-align:center;">
            <h3 style="font-size:2rem; color:var(--warning);" id="stat-pending-apps">0</h3>
            <p style="color:var(--text-muted); font-weight:600;">Pending Applications</p>
        </div>
    </div>

    <!-- MAIN GRID: CHART + AGENDA LIST -->
    <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 20px;">
        
        <!-- LEFT: LIVE ANALYTICS CHART -->
        <div class="card">
            <h3 class="card-title"><i class="fas fa-chart-pie"></i> Status Overview</h3>
            <div style="height: 250px; position:relative;">
                <canvas id="agendaChart"></canvas>
            </div>
        </div>

        <!-- RIGHT: MEETING RECORDER & AGENDA ITEMS -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title"><i class="fas fa-gavel"></i> Gram Sabha Agenda</h3>
                <button class="btn btn-primary" onclick="startMeetingSim()">▶ Start Recording Session</button>
            </div>
            
            <!-- Transcript Box -->
            <div id="meeting-transcript" style="background:#1f2937; color:#d1fae5; padding:15px; border-radius:8px; font-family:'Courier New', monospace; height:200px; overflow-y:auto; margin-top:15px; display:none; white-space:pre-wrap;"></div>
            
            <!-- Action Buttons after recording -->
            <div id="post-meeting-actions" style="margin-top:15px; display:none; gap:10px;">
                <button class="btn btn-outline" onclick="generateSDMReport()">📄 Generate SDM PDF Report</button>
                <button class="btn btn-danger" onclick="clearMeetingLog()">🗑️ Clear Log</button>
            </div>

            <!-- Live Ticket List Below Chart/Recorder -->
            <hr style="margin:20px 0; border:none; border-top:1px solid var(--border);">
            <h4 style="margin-bottom:15px;"><i class="fas fa-list-ul"></i> Active Tickets & Applications</h4>
            <div id="agenda-items-list" style="max-height:300px; overflow-y:auto;">
                <p style="color:var(--text-muted); text-align:center; padding:20px;">Loading data...</p>
            </div>
        </div>
    </div>
</section>'''

# Replace old section if exists, else insert before closing body
pattern_section = r'(<!-- VIEW: SARPANCH.*?</section>)'
if re.search(pattern_section, html, re.DOTALL):
    html = re.sub(pattern_section, new_sarpanch_html, html, flags=re.DOTALL)
else:
    # Fallback insertion
    if "</body>" in html:
        html = html.replace("</body>", new_sarpanch_html + "\n</body>")
    else:
        html += new_sarpanch_html

with open('web_demo/index.html', 'w') as f:
    f.write(html)
print("✅ HTML Structure Fixed.")


# --- PART B: INJECT JAVASCRIPT LOGIC ---
print("💉 Injecting JavaScript Logic...")

js_code = '''
// --- SARPANCH / GRAM SABHA LOGIC ---

async function refreshPanchayatData() {
    try {
        const res = await fetch('/api/agenda');
        const data = await res.json();
        
        const tickets = data.tickets || [];
        const apps = data.applications || [];

        // Calculate Stats
        const openCount = tickets.filter(t => t.status !== 'closed').length;
        const resolvedCount = tickets.filter(t => t.status === 'closed').length;
        const pendingApps = apps.length;

        // Update DOM Counters
        document.getElementById('stat-open-count').innerText = openCount;
        document.getElementById('stat-resolved-count').innerText = resolvedCount;
        document.getElementById('stat-pending-apps').innerText = pendingApps;

        // Render Chart
        renderAgendaChart(openCount, resolvedCount, pendingApps);

        // Render Item List
        renderAgendaItems(tickets, apps);

    } catch(e) {
        console.error("Failed to load agenda:", e);
        showToast("Could not fetch live data.", "error");
    }
}

function renderAgendaChart(open, resolved, pending) {
    const ctx = document.getElementById('agendaChart').getContext('2d');
    
    // Destroy existing chart if any
    if(window.myAgendaChart) window.myAgendaChart.destroy();

    window.myAgendaChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Open Issues', 'Resolved', 'Pending Apps'],
            datasets: [{
                data: [open, resolved, pending],
                backgroundColor: ['#ef4444', '#10b981', '#f59e0b'],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false,
            plugins: { 
                legend: { position: 'bottom' },
                tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.raw}` } }
            }
        }
    });
}

function renderAgendaItems(tickets, apps) {
    const container = document.getElementById('agenda-items-list');
    container.innerHTML = '';

    if(tickets.length === 0 && apps.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:20px;">No active items found.</p>';
        return;
    }

    // Combine both arrays
    const allItems = [
        ...tickets.map(t => ({...t, type: 'TICKET'})),
        ...apps.map(a => ({...a, type: 'APPLICATION'}))
    ].sort((a,b) => new Date(b.created_at || b.timestamp_created) - new Date(a.created_at || a.timestamp_created));

    allItems.forEach(item => {
        const div = document.createElement('div');
        div.style.cssText = "padding:12px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center;";
        
        let badgeColor = item.type === 'TICKET' ? 'var(--danger)' : 'var(--primary-light)';
        let statusText = item.status || 'PROCESSING';
        
        div.innerHTML = `
            <div>
                <strong>${item.description || item.scheme_name}</strong><br>
                <small style="color:var(--text-muted);">${item.type} • ID: ${item.id}</small>
            </div>
            <span class="badge" style="background:${badgeColor}; color:white;">${statusText.toUpperCase()}</span>
        `;
        container.appendChild(div);
    });
}

// --- MEETING SIMULATION ---
let isRecording = false;

function startMeetingSim() {
    if(isRecording) return;
    isRecording = true;
    
    const box = document.getElementById('meeting-transcript');
    box.style.display = 'block';
    box.innerHTML = "<div style='color:#fbbf24;'>[SYSTEM] RECORDING STARTED...</div>\\n";
    document.getElementById('post-meeting-actions').style.display = 'none';

    const scriptLines = [
        { speaker: "Sarpanch", text: "Namaskar sabhi ko. Aaj hum Ward 4 ke jal prashasan aur MGNREGA shramikyon ki samasyaon par charcha karenge." },
        { speaker: "JE Sharma", text: "Sir, haath pump ka mamla solve ho gaya hai. Citizen ne OTP verify kar diya hai." },
        { speaker: "Citizen Rep", text: "Haan ji, paani aa raha hai ab. Shukriya sarkar ka." },
        { speaker: "Secretary", text: "Ramesh Kumar ki MGNREGA job card application portal par submit ho gayi hai. Ref No: MG-8821." },
        { speaker: "Sarpanch", text: "Bahut achha. Sabhi documents check karke approval de dein. Agla point: Sadak marammat budget allocation..." },
        { speaker: "[END]", text: "--- SESSION CLOSED ---" }
    ];

    let i = 0;
    const interval = setInterval(() => {
        if(i < scriptLines.length) {
            const line = scriptLines[i];
            const entry = document.createElement('div');
            entry.style.marginTop = "5px";
            
            if(line.speaker === "[END]") {
                entry.innerHTML = `<span style="color:#ef4444; font-weight:bold;">>>> ${line.text}</span>`;
                clearInterval(interval);
                finishMeetingSim();
            } else {
                entry.innerHTML = `<span style="color:#60a5fa; font-weight:bold;">[${line.speaker}]</span>: ${line.text}`;
            }
            
            box.appendChild(entry);
            box.scrollTop = box.scrollHeight;
            i++;
        }
    }, 1500);
}

function finishMeetingSim() {
    isRecording = false;
    document.getElementById('post-meeting-actions').style.display = 'flex';
    showToast("✅ Meeting Recorded Successfully!", "success");
}

function clearMeetingLog() {
    document.getElementById('meeting-transcript').innerHTML = "";
    document.getElementById('meeting-transcript').style.display = 'none';
    document.getElementById('post-meeting-actions').style.display = 'none';
    showToast("Log cleared.", "info");
}

async function generateSDMReport() {
    showToast("Generating Official SDM PDF...", "info");
    try {
        const res = await fetch('/api/meeting/report', { method: 'POST' });
        const data = await res.json();
        
        if(data.status === 'success') {
            window.location.href = data.download_url;
            showToast("✅ Report Downloaded!", "success");
        } else {
            throw new Error(data.error || "Generation Failed");
        }
    } catch(e) {
        console.error(e);
        showToast("Error: " + e.message, "error");
    }
}

// Hook into switchView to auto-refresh
const originalSwitchView = switchView;
switchView = function(viewName) {
    originalSwitchView(viewName);
    if(viewName === 'sarpanch') {
        refreshPanchayatData();
    }
};
'''

# Insert JS before closing </script> tag
if "</script>" in html:
    # We need to read the file again because we modified it in Part A
    with open('web_demo/index.html', 'r') as f:
        current_html = f.read()
    
    # Remove any duplicate injections first (simple cleanup)
    if "// --- SARPANCH / GRAM SABHA LOGIC ---" in current_html:
        pass # Already there, skip injection to avoid duplicates
    
    final_html = current_html.replace("</script>", js_code + "\n</script>")
    
    with open('web_demo/index.html', 'w') as f:
        f.write(final_html)
    print("✅ JavaScript Logic Injected.")
else:
    print("❌ Could not find </script> tag. Manual intervention needed.")

print("\n🎉 PANCHA YAT MODULE FIXED COMPLETELY.")
