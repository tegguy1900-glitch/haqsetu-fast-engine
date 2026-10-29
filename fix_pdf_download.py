import re

# Read the current HTML file
with open('web_demo/index.html', 'r') as f:
    html_content = f.read()

# Define the NEW JavaScript Function
new_js_func = '''async function generateSDMReport() {
    showToast("Generating Official SDM PDF...", "info");
    try {
        const res = await fetch('/api/meeting/report', { method: 'POST' });
        const data = await res.json();
        
        if(data.status === 'success') {
            // Trigger Download
            window.location.href = data.download_url;
            showToast("✅ Report Downloaded!", "success");
        } else {
            throw new Error(data.error || "Generation Failed");
        }
    } catch(e) {
        console.error(e);
        showToast("Error: " + e.message, "error");
    }
}'''

# Find and Replace the OLD Function
# Pattern matches from 'function generateSDMReport()' up to the next closing brace '}'
pattern = r'(function generateSDMReport\(\)\s*\{.*?\})'

if re.search(pattern, html_content, re.DOTALL):
    html_content = re.sub(pattern, new_js_func, html_content, flags=re.DOTALL)
    
    # Save back to file
    with open('web_demo/index.html', 'w') as f:
        f.write(html_content)
    print("✅ PDF Download Logic Updated Successfully.")
else:
    print("⚠️ Could not find existing generateSDMReport function. Appending instead...")
    # Fallback: Insert before closing </script> tag if pattern fails
    if "</script>" in html_content:
        html_content = html_content.replace("</script>", "\n" + new_js_func + "\n</script>")
        with open('web_demo/index.html', 'w') as f:
            f.write(html_content)
        print("✅ PDF Download Logic Appended.")
    else:
        print("❌ Critical Error: HTML structure invalid.")

