import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Add imports if missing
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

# 2. Replace /apply_step route with REAL LOGIC
old_route_pattern = r'(        elif self\.path == "/apply_step":.*?_send\(self, 200, \{[^}]+\}\))'
new_route_code = '''        elif self.path == "/apply_step":
            text = data.get("text", "")
            scheme = data.get("scheme", "MGNREGA")
            
            # USE REAL PARSER
            extracted_data = parse_user_input(text)
            
            # STORE DATA IN SESSION (Simple dict for demo)
            # In production, use Redis or DB. Here we return it to client to hold.
            _send(self, 200, {
                "status": "success",
                "detected": extracted_data,
                "message": f"Parsed input for {scheme}. Fields extracted below."
            })'''

code = re.sub(old_route_pattern, new_route_code, code, flags=re.DOTALL)

# 3. Add /execute_registration route (Triggers Robot)
robot_route = '''
        elif self.path == "/execute_registration":
            user_data = data.get("user_data", {})
            try:
                bot = get_bot()
                result = bot.register_citizen(user_data)
                _send(self, 200, result)
            except Exception as e:
                _send(self, 500, {"status": "error", "message": str(e)})
'''

marker_404 = 'else:\n            _send(self, 404'
if '/execute_registration' not in code:
    code = code.replace(marker_404, robot_route + '        ' + marker_404.lstrip())
    print("✅ Added /execute_registration route.")
else:
    print("ℹ️ /execute_registration already exists.")

with open('village/server.py', 'w') as f:
    f.write(code)

print("✅ SERVER PATCHED WITH REAL LOGIC.")
