import re

with open('village/server.py', 'r') as f:
    code = f.read()

# Find the old handle_wizard_step function and replace it
old_func_pattern = r'(    def handle_wizard_step\(self, data\):.*?return)'
new_func_code = '''    def handle_wizard_step(self, data):
        step = int(data.get("step", 1))
        text = data.get("text", "")
        current_data = data.get("accumulated_data", {})
        doc_path = data.get("doc_path") # Absolute path to uploaded file
        
        parsed = {}
        
        # ==========================================
        # ENHANCEMENT: AUTO-FILL VIA OCR AT STEP 1
        # ==========================================
        if step == 1 and doc_path and os.path.exists(doc_path):
            print(f"🔄 [API] Running OCR on: {os.path.basename(doc_path)}...")
            ocr_result = parse_image_input(doc_path)
            
            if ocr_result:
                # Merge OCR results into accumulated data
                for k, v in ocr_result.items():
                    if v: current_data[k] = v
                
                # Return success signal to frontend
                self._send_json(200, {
                    "status": "auto_filled",
                    "message": "✅ Details extracted from ID Card!",
                    "accumulated_data": current_data
                })
                return

        # ==========================================
        # FALLBACK: STANDARD TEXT PARSING
        # ==========================================
        if text:
            parsed = parse_user_input(text)
            for k, v in parsed.items():
                if v: current_data[k] = v
                
        self._send_json(200, {"accumulated_data": current_data})'''

if re.search(old_func_pattern, code, re.DOTALL):
    code = re.sub(old_func_pattern, new_func_code, code, flags=re.DOTALL)
    with open('village/server.py', 'w') as f:
        f.write(code)
    print("✅ Server Patched with OCR Logic.")
else:
    print("⚠️ Could not find exact function pattern. Manual check needed.")
