import re

with open('web_demo/index.html', 'r') as f:
    html = f.read()

# --- PART A: REPLACE CAMERA BUTTON WITH FILE INPUT IN RENDER RESULTS ---
# Find the specific line where we render the Infra card
old_infra_card = r'''<div class="card" style="border-left-color:var(--warning)">
            <h3>🚧 Infrastructure Issue Detected</h3>
            <p>Please upload a photo and location to register a ticket.</p>
            <button class="btn btn-warning" onclick="alert\('Opening Camera Module...'\)">📷 Take Photo</button>
        </div>'''

new_infra_card = '''<div class="card" style="border-left-color:var(--warning)">
            <h3>🚧 Infrastructure Issue Detected</h3>
            <p>Upload a photo of the issue and confirm location.</p>
            
            <!-- Hidden File Input -->
            <input type="file" id="infra-photo-input" accept="image/*" style="display:none;" onchange="handleInfraPhoto(this)">
            
            <!-- Visible Button triggering Input -->
            <button class="btn btn-primary" onclick="document.getElementById('infra-photo-input').click()">
                📁 Select Photo / फोटो चुनें
            </button>
            
            <!-- Preview Area (Hidden initially) -->
            <div id="infra-preview-container" style="margin-top:15px; display:none;">
                <img id="infra-preview-img" src="" alt="Preview" style="max-width:100%; border-radius:8px; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
                <br>
                <button class="btn btn-success" style="margin-top:10px; width:100%;" onclick="submitInfraTicket()">✅ Submit Ticket / टिकट जमा करें</button>
            </div>
        </div>'''

if old_infra_card in html:
    html = html.replace(old_infra_card, new_infra_card)
    print("✅ Replaced Camera Button with File Upload UI.")
else:
    # Fallback if formatting differs slightly
    pattern = r'<button class="btn btn-warning" onclick="alert\(\'Opening Camera Module\'\)\'.*?</button>'
    if re.search(pattern, html):
        html = re.sub(pattern, '<input type="file" id="infra-photo-input" accept="image/*" style="display:none;" onchange="handleInfraPhoto(this)">\n<button class="btn btn-primary" onclick="document.getElementById(\'infra-photo-input\').click()">📁 Select Photo</button>', html)
        print("✅ Patched via Regex fallback.")
    else:
        print("⚠️ Could not find exact button match. Manual check needed.")


# --- PART B: ADD JAVASCRIPT HANDLERS ---
js_handler = '''
// --- INFRA UPLOAD LOGIC ---
let currentInfraBase64 = null;
let currentLat = 28.9069; // Default demo coords
let currentLon = 77.7453;

function handleInfraPhoto(input) {
    const file = input.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        currentInfraBase64 = e.target.result; // Data URL
        
        // Show Preview
        document.getElementById('infra-preview-img').src = currentInfraBase64;
        document.getElementById('infra-preview-container').style.display = 'block';
        
        // Try to get GPS
        if(navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(pos => {
                currentLat = pos.coords.latitude;
                currentLon = pos.coords.longitude;
                showToast("📍 Location Captured", "info");
            }, err => {
                console.warn("GPS Denied, using default.", err);
            });
        }
    };
    reader.readAsDataURL(file);
}

async function submitInfraTicket() {
    if(!currentInfraBase64) {
        alert("Please select a photo first.");
        return;
    }
    
    showToast("Creating Ticket...", "info");
    
    try {
        const res = await fetch('/api/infra/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                description: "Reported via HaqSetu App",
                lat: currentLat,
                lon: currentLon,
                photo: currentInfraBase64
            })
        });
        const data = await res.json();
        
        if(data.ticket_id) {
            showToast(`✅ Ticket #${data.ticket_id} Created!`, "success");
            // Reset UI
            document.getElementById('intake-results').innerHTML = '';
            document.getElementById('manual-input').value = '';
        } else {
            throw new Error(data.error || "Creation Failed");
        }
    } catch(e) {
        console.error(e);
        showToast("Error: " + e.message, "error");
    }
}
'''

# Insert JS before closing </script>
if "</script>" in html:
    html = html.replace("</script>", js_handler + "\n</script>")
    print("✅ Added JavaScript Handlers.")
else:
    print("❌ Missing </script> tag.")

with open('web_demo/index.html', 'w') as f:
    f.write(html)

print("\n🎉 INFRA MODULE FIXED FOR FILE UPLOAD.")
