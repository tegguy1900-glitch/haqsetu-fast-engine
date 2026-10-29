// Paste this ENTIRE script content into your web_demo/index.html inside <script> tags
// OR run the python injector below.

const ui_injector = `
<script>
window.collectedData = {}; // Global storage across steps

async function submitAppStep() {
    const text = document.getElementById('app-input').value;
    const res = await fetch('/apply_step', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:text, scheme:'MGNREGA'})});
    const data = await res.json();
    
    // Merge detected data into global collection
    Object.assign(window.collectedData, data.detected);
    
    let msg = "<b>Parsed Data:</b><br>";
    for(let k in window.collectedData) {
        if(window.collectedData[k]) msg += `${k}: ${window.collectedData[k]}<br>`;
    }
    document.getElementById('app-status').innerHTML = msg + "<br><span style='color:green'>Ready for Document Upload.</span>";
}

async function uploadDoc() {
    const fileInput = document.getElementById('doc-upload');
    if(!fileInput.files.length) return alert("Select a file first!");
    
    const fileName = fileInput.files[0].name;
    const res = await fetch('/upload_doc', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({filename:fileName, doc_type:'aadhaar'})});
    const data = await res.json();
    
    if(data.valid) {
        document.getElementById('app-status').innerHTML += "<br><span style='color:green'>📸 Document Verified!</span><br><button onclick='triggerRobot()' style='background:red;color:white;padding:10px;margin-top:10px;border:none;cursor:pointer;'>🤖 EXECUTE REGISTRATION NOW</button>";
    } else {
        document.getElementById('app-status').innerHTML += "<br><span style='color:red'>❌ " + data.message + "</span>";
    }
}

async function triggerRobot() {
    document.getElementById('app-status').innerText = "🤖 Robot is filling forms... wait...";
    const res = await fetch('/execute_registration', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user_data: window.collectedData})});
    const data = await res.json();
    
    if(data.status === 'success') {
        document.getElementById('app-status').innerHTML = 
            \`<h3 style="color:green">✅ SUCCESS!</h3>\` +
            \`<p>Reg ID: <b>${data.registration_id}</b></p>\` +
            \`<img src="${data.screenshot_path}" alt="Proof" style="max-width:100%; border:1px solid #ccc;">\`;
    } else {
        document.getElementById('app-status').innerText = "❌ Error: " + data.message;
    }
}
<\/script>
`;

console.log(ui_injector);
