import re

with open('web_demo/index.html', 'r') as f:
    html = f.read()

# 1. Add CSS for the Apply Button and Modal
css_inject = """
<style>
.apply-btn { background: #4CAF50; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: bold; margin-left: 10px; }
.apply-btn:hover { background: #45a049; }
.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; justify-content: center; align-items: center; }
.modal-content { background: white; padding: 20px; border-radius: 8px; max-width: 500px; width: 90%; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
.close-modal { cursor: pointer; font-size: 20px; color: #999; }
.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
.form-group input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
.submit-application-btn { width: 100%; padding: 10px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
.submit-application-btn:hover { background: #1976D2; }
.status-msg { margin-top: 10px; font-weight: bold; min-height: 20px; }
</style>
"""

# 2. Add HTML for the Modal (Hidden by default)
modal_html = """
<div id="applyModal" class="modal-overlay">
    <div class="modal-content">
        <div class="modal-header">
            <h3 id="modalTitle">Apply for Scheme</h3>
            <span class="close-modal" onclick="closeApplyModal()">&times;</span>
        </div>
        <p>Tell us your details in plain language (English/Hindi):</p>
        <div class="form-group">
            <label>Voice/Input Text:</label>
            <textarea id="appVoiceInput" rows="3" placeholder="e.g., My name is Ramesh, father Suresh, mobile 9876543210..." style="width:100%; padding:8px;"></textarea>
        </div>
        <button class="submit-application-btn" onclick="submitApplication()">🤖 Submit Application</button>
        <div id="appStatus" class="status-msg"></div>
    </div>
</div>
"""

# 3. Add JavaScript Logic
js_logic = """
<script>
let currentSchemeName = "";

function showApplyButton(schemeObj, containerEl) {
    if (!schemeObj.can_apply) return;
    
    const btn = document.createElement('button');
    btn.className = 'apply-btn';
    btn.innerText = "▶ APPLY NOW";
    btn.onclick = () => openApplyModal(schemeObj.name || schemeObj.scheme_id);
    containerEl.appendChild(btn);
}

function openApplyModal(schemeName) {
    currentSchemeName = schemeName;
    document.getElementById('modalTitle').innerText = `Applying for: ${schemeName}`;
    document.getElementById('applyModal').style.display = 'flex';
    document.getElementById('appStatus').innerText = "";
    document.getElementById('appVoiceInput').value = "";
}

function closeApplyModal() {
    document.getElementById('applyModal').style.display = 'none';
}

async function submitApplication() {
    const text = document.getElementById('appVoiceInput').value.trim();
    const statusEl = document.getElementById('appStatus');
    
    if (!text) {
        statusEl.innerText = "❌ Please enter some text.";
        statusEl.style.color = "red";
        return;
    }
    
    statusEl.innerText = "⏳ Processing... Connecting to Govt Portal...";
    statusEl.style.color = "#666";
    
    try {
        const res = await fetch('/apply_scheme', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ text: text, scheme: currentSchemeName })
        });
        
        const data = await res.json();
        
        if (data.status === 'success') {
            statusEl.innerHTML = `<span style="color:green">✅ SUCCESS!<br>Reg ID: ${data.registration_id || 'Generated'}<br>${data.message}</span>`;
            // Optional: Auto-close after 3 seconds
            setTimeout(closeApplyModal, 3000);
        } else {
            statusEl.innerHTML = `<span style="color:red">❌ FAILED: ${data.message || data.error}</span>`;
        }
        
    } catch (e) {
        statusEl.innerText = "❌ Network Error: " + e.message;
        statusEl.style.color = "red";
    }
}

// Hook into existing rendering logic
// We assume there's a function that renders schemes. 
// If you use innerHTML += ..., we need to intercept.
// SAFEST WAY: Override the DOMContentLoaded event to attach listeners to dynamically added elements? 
// No, better to patch the specific render loop if known.
// Since we don't know the exact variable name of your result container, 
// we will add a MutationObserver to watch for new scheme cards appearing.

document.addEventListener('DOMContentLoaded', () => {
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === 1 && node.classList.contains('scheme-item')) { // Assuming class 'scheme-item' exists
                    // Check if it has data-can-apply attribute set by backend? 
                    // Or just check text content for "MGNREGA"?
                    // Let's rely on the backend sending 'can_apply' in JSON, 
                    // but since we are observing DOM, we might miss context.
                    
                    // BETTER APPROACH FOR THIS SCRIPT:
                    // We will manually instruct user to call showApplyButton in their existing JS.
                }
            });
        });
    });
    
    // Observe common result containers
    const targets = ['#results-list', '.scheme-results', '#intake-results'];
    targets.forEach(sel => {
        const el = document.querySelector(sel);
        if(el) observer.observe(el, { childList: true, subtree: true });
    });
});
</script>
"""

# Inject everything
html = html.replace('</head>', css_inject + '</head>')
html = html.replace('</body>', modal_html + js_logic + '\n</body>')

with open('web_demo/index.html', 'w') as f:
    f.write(html)

print("✅ UI Components Injected (CSS, Modal, JS).")
print("\n⚠️ MANUAL STEP REQUIRED:")
print("Find your existing JavaScript code where you loop through `data.schemes`.")
print("Inside that loop, after creating the element for each scheme, add this line:")
print("   showApplyButton(schemeObj, elementContainer);")
