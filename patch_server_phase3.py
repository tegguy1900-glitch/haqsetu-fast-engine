import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Ensure Imports are present at top
if 'from core.parser import parse_user_input' not in code:
    code = code.replace(
        "from urllib.parse import urlparse, parse_qs",
        "from urllib.parse import urlparse, parse_qs\nfrom core.parser import parse_user_input"
    )

if 'from core.mgnrega_bot import get_bot' not in code:
    code = code.replace(
        "from ledger import chain as _chain",
        "from ledger import chain as _chain\nfrom core.mgnrega_bot import get_bot"
    )

# 2. Find the place to inject the new route (before the final 404 handler)
marker_404 = 'else:\n            _send(self, 404'

new_route_code = '''
        elif self.path == "/apply_scheme":
            # This is the MAIN ENTRY POINT for the UI
            raw_text = data.get("text", "")
            scheme_name = data.get("scheme", "MGNREGA")
            
            print(f" Received Apply Request for {scheme_name}: '{raw_text}'")
            
            # STEP A: Parse Voice/Text
            extracted_data = parse_user_input(raw_text)
            print(f"   🧠 Parsed Data: {extracted_data}")
            
            # Validate critical fields
            if not extracted_data.get('name') or not extracted_data.get('mobile'):
                _send(self, 400, {
                    "status": "error", 
                    "message": "Missing Name or Mobile Number. Please speak clearly.",
                    "detected": extracted_data
                })
                return

            # STEP B: Run Automation Bot
            try:
                bot = get_bot()
                result = bot.register_citizen(extracted_data)
                
                if result['status'] == 'success':
                    _send(self, 200, {
                        "status": "success",
                        "registration_id": result['registration_id'],
                        "screenshot_path": result['screenshot_path'],
                        "message": f"✅ Registered for {scheme_name}!",
                        "data_used": extracted_data
                    })
                else:
                    _send(self, 500, {
                        "status": "failed",
                        "message": f"❌ Bot Failed: {result.get('error')}",
                        "data_used": extracted_data
                    })
                    
            except Exception as e:
                print(f"💥 CRASH during Bot Execution: {e}")
                _send(self, 500, {"status": "crash", "message": str(e)})
'''

if marker_404 in code and '/apply_scheme' not in code:
    code = code.replace(marker_404, new_route_code + '\n        ' + marker_404.lstrip())
    with open('village/server.py', 'w') as f:
        f.write(code)
    print("✅ Added /apply_scheme route to Server.")
elif '/apply_scheme' in code:
    print("ℹ️ /apply_scheme already exists. Skipping.")
else:
    print("❌ Could not find injection point. Manual edit needed.")
