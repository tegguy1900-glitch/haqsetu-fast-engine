with open('web_demo/index.html', 'r') as f:
    html = f.read()

ui_block = """
<div id="scheme-app" style="margin:40px auto; padding:25px; border:3px solid #4CAF50; border-radius:15px; background:#f9f9f9; max-width:600px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
    <h2 style="color:#2E7D32;">🚀 MGNREGA Voice Application</h2>
    <p id="app-step" style="font-size:18px;"><b>Step 1:</b> Tell me your Name and Mobile Number</p>
    <input type="text" id="app-input" placeholder="e.g., My name is Rahul, mobile 9876543210" style="width:95%; padding:12px; font-size:16px; border:1px solid #ccc; border-radius:5px;">
    <button onclick="submitAppStep()" style="margin-top:10px; padding:12px 25px; font-size:16px; background:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer;">Submit Voice Data</button>
    <hr style="margin:25px 0;">
    <p style="font-size:18px;"><b>Step 2:</b> Scan your Aadhaar Card</p>
    <input type="file" id="doc-upload" accept="image/*" capture="environment" style="margin-top:10px; font-size:16px;">
    <button onclick="uploadDoc()" style="margin-top:10px; padding:12px 25px; font-size:16px; background:#2196F3; color:white; border:none; border-radius:5px; cursor:pointer;">Verify Document</button>
    <p id="app-status" style="color:#1B5E20; font-weight:bold; font-size:18px; margin-top:20px; min-height:24px;"></p>
</div>
<script>
async function submitAppStep() {
    const text = document.getElementById('app-input').value;
    try {
        const res = await fetch('/apply_step', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:text})});
        const data = await res.json();
        document.getElementById('app-status').innerText = "✅ " + data.message + " | Extracted: " + JSON.stringify(data.extracted);
    } catch(e) {
        document.getElementById('app-status').innerText = "❌ Error connecting to server.";
    }
}
async function uploadDoc() {
    try {
        const res = await fetch('/upload_doc', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({doc_type:'aadhaar'})});
        const data = await res.json();
        document.getElementById('app-status').innerText = "📸 " + data.message;
    } catch(e) {
        document.getElementById('app-status').innerText = "❌ Error uploading document.";
    }
}
</script>
"""

if 'scheme-app' not in html:
    html = html.replace('</body>', ui_block + '\n</body>')
    with open('web_demo/index.html', 'w') as f:
        f.write(html)
    print("✅ Frontend UI injected successfully!")
else:
    print("⚠️ UI already exists.")
