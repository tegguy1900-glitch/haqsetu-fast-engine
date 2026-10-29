import re

# Read the current HTML file
with open('web_demo/index.html', 'r') as f:
    html_content = f.read()

# Define the NEW Sarpanch Section HTML
new_sarpanch_html = '''<!-- VIEW: SARPANCH (FULLY FUNCTIONAL) -->
<section id="view-sarpanch" class="view-section" style="display:none;">
    <div class="page-header">
        <h2 class="page-title">Gram Sabha Command Center</h2>
        <p class="page-subtitle">Real-time oversight of village grievances, scheme applications, and meeting minutes.</p>
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
                <!-- Populated via JS -->
                <p style="color:var(--text-muted); text-align:center; padding:20px;">No active items found. Refresh data.</p>
            </div>
        </div>
    </div>
</section>'''

# Find and Replace the OLD Sarpanch Section
# Pattern matches from '<!-- VIEW: SARPANCH' up to the next '</section>'
pattern = r'(<!-- VIEW: SARPANCH.*?</section>)'

if re.search(pattern, html_content, re.DOTALL):
    html_content = re.sub(pattern, new_sarpanch_html, html_content, flags=re.DOTALL)
    
    # Save back to file
    with open('web_demo/index.html', 'w') as f:
        f.write(html_content)
    print("✅ Sarpanch View Updated Successfully.")
else:
    print("⚠️ Could not find existing Sarpanch section. Appending instead...")
    # Fallback: Insert before closing body tag if pattern fails
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", new_sarpanch_html + "\n</body>")
        with open('web_demo/index.html', 'w') as f:
            f.write(html_content)
        print("✅ Sarpanch View Appended.")
    else:
        print("❌ Critical Error: HTML structure invalid.")

