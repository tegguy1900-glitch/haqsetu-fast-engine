with open('village/server.py', 'r') as f:
    code = f.read()

new_routes = """
        elif self.path == "/apply_step":
            text = data.get("text", "")
            # Simulating AI Voice Extraction
            extracted = {"name": "Rahul Kumar", "mobile": "9876543210"} if "rahul" in text.lower() or "987" in text else {"raw_text": text}
            _send(self, 200, {"status": "success", "message": "Voice data captured!", "extracted": extracted})
        elif self.path == "/upload_doc":
            doc_type = data.get("doc_type", "aadhaar")
            # Simulating AI Vision Verification
            _send(self, 200, {"status": "success", "message": f"AI Vision verified {doc_type} successfully! Document is clear and valid."})
"""

if '/apply_step' not in code:
    # Inject right before the final 404 error block
    marker = 'else:\n            _send(self, 404'
    if marker in code:
        code = code.replace(marker, new_routes + '        ' + marker.lstrip())
        with open('village/server.py', 'w') as f:
            f.write(code)
        print("✅ Backend routes injected successfully!")
    else:
        print("❌ Could not find injection point. File structure might be different.")
else:
    print("⚠️ Routes already exist.")
