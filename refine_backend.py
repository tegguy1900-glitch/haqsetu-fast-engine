import re

with open('village/server.py', 'r') as f:
    code = f.read()

# --- 1. ADD INPUT SANITIZATION HELPER ---
sanitizer_code = '''
def sanitize_input(text):
    """Removes potentially harmful characters to prevent XSS/Injection."""
    if not text: return ""
    # Allow alphanumeric, spaces, punctuation common in Hindi/English
    clean = re.sub(r'[<>\"\'&]', '', str(text)) 
    return clean.strip()[:500] # Limit length
'''

if 'def sanitize_input' not in code:
    lines = code.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if 'def hash_mobile' in line:
            insert_idx = i
            break
    lines.insert(insert_idx, sanitizer_code)
    code = '\n'.join(lines)
    print("✅ Added Input Sanitizer.")

# --- 2. UPDATE VOICE MATCH TO USE SANITIZER ---
old_voice = r'def handle_voice_match\(self, data\):\s*raw_text = data\.get\("text", ""\)\.strip\(\)'
new_voice = '''    def handle_voice_match(self, data):
        raw_text = sanitize_input(data.get("text", ""))'''
code = re.sub(old_voice, new_voice, code)
print("✅ Secured Voice Match Route.")

# --- 3. UPDATE BOT EXECUTION WITH RETRY LOGIC ---
old_exec = r'def handle_execute_bot\(self, data\):.*?bot = get_bot\(\).*?result = bot\.execute_registration\(scheme_id, user_data, doc_path\)'
new_exec_logic = '''    def handle_execute_bot(self, data):
        scheme_id = data.get("scheme_id")
        user_data = {k: sanitize_input(v) if isinstance(v, str) else v for k,v in data.get("user_data", {}).items()}
        doc_path = data.get("doc_path") 
        
        print(f"🚀 [API] Triggering Bot for {scheme_id}...")
        
        max_retries = 2
        result = None
        
        for attempt in range(max_retries):
            try:
                bot = get_bot()
                result = bot.execute_registration(scheme_id, user_data, doc_path)
                if result["status"] == "success":
                    break # Success, exit loop
                else:
                    print(f"⚠️ Attempt {attempt+1} failed: {result.get('error')}")
            except Exception as e:
                print(f"❌ Bot Crash Attempt {attempt+1}: {e}")
                time.sleep(1) # Wait before retry
        
        if not result or result["status"] != "success":
             self._send_json(500, {"status": "failed", "message": "Bot automation failed after retries."})
             return

        # Save to DB if success
        conn = get_db_conn()
        c = conn.cursor()
        mobile_hash = hash_mobile(user_data.get("mobile", "unknown"))
        
        c.execute("""INSERT INTO applications_scheme 
                     (citizen_mobile_hash, scheme_name, parsed_data_json, bot_status, reg_id_generated, screenshot_path)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (mobile_hash, scheme_id, json.dumps(user_data), "success", result["registration_id"], result["screenshot_path"]))
        conn.commit()
        conn.close()
            
        self._send_json(200, result)'''

code = re.sub(old_exec, new_exec_logic, code, flags=re.DOTALL)
print("✅ Added Retry Logic to Bot Execution.")

with open('village/server.py', 'w') as f:
    f.write(code)
    
print("\n🎉 BACKEND REFINED.")
