with open('web_demo/index.html', 'r') as f:
    html = f.read()

# 1. Add CSS for the Unified View
css_addition = """
<style>
.scheme-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px; background: white; display: flex; justify-content: space-between; align-items: center; }
.apply-btn { background: #4CAF50; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; }
.apply-btn:hover { background: #45a049; }
.hidden { display: none !important; }
#app-section { margin-top: 20px; padding: 20px; border: 2px dashed #4CAF50; background: #f9fff9; }
</style>
"""

# 2. Add JS Logic to Switch Views
js_logic = """
<script>
function showApplicationForm(schemeName) {
    // Hide Intake Section
    document.getElementById('intake-section').classList.add('hidden');
    
    // Show App Section
    const appSec = document.getElementById('app-section');
    appSec.classList.remove('hidden');
    
    // Set Context
    window.currentScheme = schemeName;
    document.getElementById('app-title').innerText = `Applying for: ${schemeName}`;
    document.getElementById('app-status').innerText = "Ready. Speak your details below.";
    
    // Reset Data
    window.collectedData = {};
    document.getElementById('app-input').value = "";
}

function backToIntake() {
    document.getElementById('app-section').classList.add('hidden');
    document.getElementById('intake-section').classList.remove('hidden');
}
</script>
"""

# 3. Modify existing HTML structure
# Wrap existing intake content in a div if not already wrapped
if '<div id="intake-section">' not in html:
    # Simple heuristic: Assume everything before </body> is intake unless tagged
    # Better: Inject wrapper around main content area if identifiable. 
    # For safety, we just append the new sections and rely on JS to toggle visibility.
    pass 

# Append the new Application Section at the end of body
app_section_html = """
<div id="app-section" class="hidden">
    <button onclick="backToIntake()" style="background:#ccc; margin-bottom:10px;">← Back to Results</button>
    <h2 id="app-title">Apply for Scheme</h2>
    <p><b>Step 1:</b> Tell me your Name, Father's Name, Mobile, and Aadhaar Last 4.</p>
    <input type="text" id="app-input" placeholder="e.g., My name is Ramesh, father Suresh, mobile 9876543210, last 4 aadhaar 1234" style="width:90%; padding:10px;">
    <button onclick="submitAppStep()" class="apply-btn">Process Voice Data</button>
    
    <hr>
    <p><b>Step 2:</b> Upload Documents</p>
    <input type="file" id="doc-upload" accept="image/*,.pdf">
    <button onclick="uploadDoc()" class="apply-btn">Verify Docs</button>
    
    <div id="app-status" style="margin-top:15px; font-weight:bold;"></div>
    <button id="execute-btn" onclick="triggerRobot()" style="display:none; background:red; color:white; padding:10px; width:100%;">🤖 SUBMIT TO GOVT PORTAL</button>
</div>
"""

# Insert CSS and JS before </head> and </body> respectively
html = html.replace('</head>', css_addition + '</head>')
html = html.replace('</body>', js_logic + app_section_html + '</body>')

with open('web_demo/index.html', 'w') as f:
    f.write(html)

print("✅ UI Unified: Intake and Application are now linked via buttons.")
