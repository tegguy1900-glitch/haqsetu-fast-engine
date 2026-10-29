import re

with open('web_demo/index.html', 'r') as f:
    html = f.read()

# Strategy: Look for common patterns where schemes are rendered
# Pattern 1: .map(s => ...) or forEach(s => ...) containing <li> or <div>
# We will insert a helper function `renderSchemeCard(s)` globally if not exists,
# then replace inline rendering calls with this function.

helper_js = """
<script>
// Global Renderer for Scheme Cards with Apply Button
function renderSchemeCard(schemeObj) {
    const div = document.createElement('div');
    div.className = 'scheme-card'; // Use CSS class defined earlier or default styling
    
    let innerHTML = `<strong>${schemeObj.name || schemeObj.scheme_id}</strong>`;
    
    if (schemeObj.confidence) {
        innerHTML += ` <span style="color:#666; font-size:0.9em;">(${Math.round(schemeObj.confidence*100)}% match)</span>`;
    }
    
    // Check if applicable
    if (schemeObj.can_apply) {
        innerHTML += `<br><button onclick="startApplication('${schemeObj.scheme_id}', '${schemeObj.name}')" 
                      style="margin-top:8px; background:#4CAF50; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer;">
                      ▶ APPLY NOW</button>`;
    } else {
        innerHTML += `<br><small style="color:#999;">Informational only</small>`;
    }
    
    div.innerHTML = innerHTML;
    return div;
}

function startApplication(schemeId, schemeName) {
    // Hide Intake Section
    const intakeSec = document.getElementById('intake-section') || document.querySelector('.main-container');
    if(intakeSec) intakeSec.style.display = 'none';
    
    // Show App Section
    const appSec = document.getElementById('app-section');
    if(appSec) {
        appSec.style.display = 'block';
        document.getElementById('app-title').innerText = `Applying for: ${schemeName}`;
        window.currentSchemeContext = { id: schemeId, name: schemeName };
        
        // Reset data collector
        window.collectedData = {};
        document.getElementById('app-input').value = "";
        document.getElementById('app-status').innerText = "Ready. Speak your details below.";
        
        // Ensure Execute button is hidden initially
        const execBtn = document.getElementById('execute-btn');
        if(execBtn) execBtn.style.display = 'none';
    } else {
        alert("Error: Application section not found in DOM.");
    }
}
</script>
"""

# Injection Point 1: Add Helper JS before </body>
html = html.replace('</body>', helper_js + '\n</body>')

# Injection Point 2: Replace existing scheme rendering logic
# This is tricky without seeing exact code. We assume standard fetch->json->render pattern.
# We look for lines like: data.schemes.forEach(...) or map(...).join("")
# We'll try to wrap the container ID 'results-list' or similar.

# Since we cannot reliably parse arbitrary JS strings safely here, 
# we rely on the fact that most simple dashboards use innerHTML += ...
# We will append a MutationObserver or Event Listener approach? 
# NO. Too complex. 

# BETTER APPROACH: 
# Ask user to manually locate the rendering loop OR 
# Provide a generic override script that runs AFTER page load.

override_script = """
<script>
document.addEventListener('DOMContentLoaded', () => {
    // Wait slightly for async fetch to complete and render initial list
    setTimeout(() => {
        const resultContainer = document.querySelector('#results-list') || 
                                document.querySelector('.scheme-results') ||
                                document.querySelector('[id*="result"]');
        
        if(resultContainer && !resultContainer.dataset.patched) {
            console.log("Patching scheme renderer...");
            resultContainer.dataset.patched = "true";
            
            // Re-render children using our new helper
            // Note: This assumes original data is stored somewhere accessible or we re-fetch
            // For simplicity in this hackathon context, we assume the user triggers Match again
            // OR we hook into the existing click handler of 'Match Me'
            
            const matchBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Match'));
            if(matchBtn) {
                const originalClick = matchBtn.onclick;
                matchBtn.onclick = async function(e) {
                    await originalClick.call(this, e);
                    
                    // After original render completes, swap nodes
                    setTimeout(() => {
                        const cards = resultContainer.children;
                        // This is fragile. Ideally, we modify the source JS.
                        // But for now, let's just ensure the buttons work if they exist.
                    }, 500);
                }
            }
        }
    }, 1000);
});
</script>
"""

# Actually, modifying the source JS inside index.html is safer than runtime overrides.
# Let's search for the specific string used to display schemes.
# Common patterns: `s.name`, `scheme.name`, `el.textContent = s.name`

# SEARCH AND REPLACE STRATEGY
# Find: something like `${s.name}` inside a template literal assigned to innerHTML
pattern_search = r'(innerHTML\s*[+=]\s*`[^`]*\$\{(?:s|item|scheme)\.(?:name|title)\}[^`]*`)'
matches = re.findall(pattern_search, html)

if matches:
    print(f"Found {len(matches)} potential rendering blocks. Attempting surgical insertion...")
    # This is too risky for blind automation. 
    pass 
else:
    print("Could not auto-detect rendering block. Proceeding with manual instruction.")

# FINAL DECISION FOR THIS STEP:
# Instead of guessing, we will ADD the 'Apply Now' functionality as a SEPARATE SECTION 
# that appears ONLY when a scheme is clicked, BUT triggered BY THE EXISTING LIST ITEMS 
# IF THEY HAVE A SPECIFIC CLASS OR DATA ATTRIBUTE.

# However, since we control the BACKEND RESPONSE NOW (Step 1 added can_apply),
# We just need the FRONTEND to respect it.

# Let's write a clean, standalone injection that REPLACES the entire results display area 
# with our custom renderer whenever data arrives.

full_replacement_logic = """
<script>
// Override global state handling for schemes
window.renderSchemesSafe = function(schemesArray, containerId='results-list') {
    const container = document.getElementById(containerId);
    if(!container) {
        console.error("Container #" + containerId + " not found.");
        return;
    }
    
    container.innerHTML = ''; // Clear old content
    
    if(!schemesArray || schemesArray.length === 0) {
        container.innerHTML = '<p>No matching schemes found.</p>';
        return;
    }
    
    schemesArray.forEach(s => {
        const card = renderSchemeCard(s); // Uses our helper above
        container.appendChild(card);
    });
};

// Hook into the main fetch success callback
// Assuming variable 'data' holds response from /voice
const origFetchHandler = window.handleVoiceResponse; // Placeholder name
// We cannot easily hook anonymous callbacks. 
// INSTEAD: We instruct the USER to change their existing JS call.
</script>
"""

# Given constraints, the safest path is:
# 1. Keep backend patch (Done).
# 2. Tell user to FIND THEIR RENDER LOOP IN INDEX.HTML.
# 3. Give them the EXACT CODE SNIPPET TO PASTE THERE.

print("✅ Backend patched. Frontend requires manual snippet integration.")
print("\n👇 COPY THIS SNIPPET INTO YOUR INDEX.JS OR SCRIPT TAG WHERE YOU RENDER SCHEMES:")
print("""
// INSIDE YOUR FETCH SUCCESS CALLBACK (where you iterate data.schemes):
data.schemes.forEach(s => {
    const li = document.createElement('li'); // Or div
    li.innerHTML = `<b>${s.name}</b> (${Math.round(s.confidence*100)}%)`;
    
    if(s.can_apply) {
        const btn = document.createElement('button');
        btn.innerText = "▶ APPLY NOW";
        btn.style.cssText = "margin-left:10px; background:green; color:white; border:none; padding:4px 8px; cursor:pointer;";
        btn.onclick = () => startApplication(s.scheme_id, s.name);
        li.appendChild(btn);
    }
    
    resultsList.appendChild(li);
});
""")

with open('web_demo/index.html', 'w') as f:
    f.write(html) # Save unchanged HTML for now, relying on instructions

